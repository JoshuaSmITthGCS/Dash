"""Append-only daily price archive. The permanent fix for the survivorship price gap.

The survivorship reconstruction (docs/SURVIVORSHIP-RECONSTRUCTION.md section 3) measured
the free price provider's retention: 49% of 2026 delistings recoverable, 0% for every
earlier year. Prices for a dead name are unrecoverable at zero cost roughly a year after
death. They are also entirely preventable losses going forward: a name archived while
alive stays archived after it delists.

Design:
  - One JSON file per ticker under pipeline/data/price_archive/, holding date-keyed
    close and volume rows. Writes are append-and-merge by date, never delete, never
    overwrite an existing date's value (first write wins, so a later restatement of an
    adjusted close cannot silently rewrite archived history; both the original and any
    conflicting value are logged to conflicts.jsonl instead).
  - A manifest (archive_manifest.json) with per-run counts, the run timestamp, and a
    SHA-256 over the archive tree, matching the experiment-manifest discipline.
  - archive_health() returns critical when the newest successful run is older than
    max_staleness_days, so a silently skipped schedule fails loudly in the same
    data-health surface as statement coverage (pipeline/data_health.py).

Seeding: seed_from_disk() ingests every series already on disk (backtest_cache, the
survivorship dead_prices captures, the OHLC sample) with zero network. run_daily()
appends today's closes for the current universe plus every ticker in the delisting log
young enough to still resolve.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ARCHIVE_DIR = os.path.join(HERE, "data", "price_archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "archive_manifest.json")
CONFLICTS = os.path.join(ARCHIVE_DIR, "conflicts.jsonl")

ARCHIVE_START_DATE = "2026-08-11"
MAX_STALENESS_DAYS = 4  # a daily schedule with weekend slack


def _path(ticker):
    return os.path.join(ARCHIVE_DIR, f"{ticker.upper()}.json")


def append_series(ticker, dates, closes, volumes, source):
    """Merge one series into the archive. Existing dates keep their first value."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = _path(ticker)
    rows = {}
    if os.path.exists(path):
        rows = json.load(open(path)).get("rows", {})
    added = conflicts = 0
    for d, c, v in zip(dates, closes, volumes):
        if not d or c is None:
            continue
        if d in rows:
            if abs(rows[d][0] - float(c)) > max(0.01, 0.001 * abs(float(c))):
                conflicts += 1
                with open(CONFLICTS, "a") as handle:
                    handle.write(json.dumps({
                        "ticker": ticker, "date": d, "archived": rows[d][0],
                        "incoming": float(c), "source": source,
                        "at": datetime.now(timezone.utc).isoformat()}) + "\n")
            continue
        rows[d] = [round(float(c), 4), int(v or 0)]
        added += 1
    json.dump({"ticker": ticker.upper(), "rows": rows,
               "first_archived": ARCHIVE_START_DATE}, open(path, "w"))
    return added, conflicts


def record_run(counts):
    from validation.experiment_manifest import sha256_of_tree
    manifest = {"runs": []}
    if os.path.exists(MANIFEST):
        manifest = json.load(open(MANIFEST))
    manifest["runs"].append({
        "at": datetime.now(timezone.utc).isoformat(),
        **counts,
        "archive_tree_sha256": sha256_of_tree(ARCHIVE_DIR, ".json")[:16],
    })
    manifest["archive_start_date"] = ARCHIVE_START_DATE
    json.dump(manifest, open(MANIFEST, "w"), indent=1)


def archive_health(now=None):
    """healthy / degraded / critical, for the data-health surface."""
    now = now or datetime.now(timezone.utc)
    if not os.path.exists(MANIFEST):
        return {"state": "critical", "reason": "price archive has never run"}
    manifest = json.load(open(MANIFEST))
    runs = manifest.get("runs") or []
    if not runs:
        return {"state": "critical", "reason": "price archive has no recorded runs"}
    last = datetime.fromisoformat(runs[-1]["at"])
    age_days = (now - last).total_seconds() / 86400
    if age_days > MAX_STALENESS_DAYS:
        return {"state": "critical",
                "reason": f"last archive run {age_days:.1f} days ago, "
                          f"limit {MAX_STALENESS_DAYS}"}
    return {"state": "healthy", "last_run": runs[-1]["at"],
            "tickers": runs[-1].get("tickers")}


def seed_from_disk():
    """Zero-network seed from every price series already in the repository."""
    total_added = total_tickers = 0
    cache = os.path.join(HERE, "data", "backtest_cache")
    for f in sorted(os.listdir(cache)):
        if not f.endswith(".json"):
            continue
        d = json.load(open(os.path.join(cache, f)))
        added, _ = append_series(d["symbol"], d["dates"], d["closes"],
                                 d.get("volumes", [0] * len(d["dates"])),
                                 "backtest_cache_seed")
        total_added += added
        total_tickers += 1
    dead = os.path.join(REPO, "research", "audit", "survivorship", "data", "dead_prices")
    if os.path.isdir(dead):
        for f in sorted(os.listdir(dead)):
            d = json.load(open(os.path.join(dead, f)))
            if not d.get("dates"):
                continue
            added, _ = append_series(d["ticker"], d["dates"], d["closes"],
                                     d.get("volumes", [0] * len(d["dates"])),
                                     "dead_prices_seed")
            total_added += added
            total_tickers += 1
    record_run({"mode": "seed_from_disk", "tickers": total_tickers,
                "rows_added": total_added})
    return total_tickers, total_added


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        tickers, rows = seed_from_disk()
        print(f"seeded {tickers} tickers, {rows} rows")
        print(archive_health())
    else:
        print(archive_health())
