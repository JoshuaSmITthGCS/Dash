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
DELISTING_LOG = os.path.join("research", "audit", "survivorship", "data", "delisting_log.json")
# The free provider's measured retention window (docs/SURVIVORSHIP-RECONSTRUCTION-2.md):
# 49% hit rate for 2026 delistings, 0% for 2020-2025. A name stops resolving roughly a
# year after it leaves the live universe, so that's the window worth spending calls on.
DELISTING_RETENTION_DAYS = 365


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


def _resolvable_delisted_tickers(universe_tickers, now=None):
    """Tickers that left the live universe recently enough to still resolve.

    Excludes anything still in the live universe (fetch_advisor.py already covers those
    at zero extra cost). Excludes anything past DELISTING_RETENTION_DAYS: the measured
    hit rate for those is 0%, so a call spent there is a call wasted.
    """
    path = os.path.join(REPO, DELISTING_LOG)
    if not os.path.exists(path):
        return set()
    now = now or datetime.now(timezone.utc)
    tickers = set()
    for event in json.load(open(path)):
        ticker = event.get("ticker")
        event_date = event.get("event_date")
        if not ticker or not event_date:
            continue
        ticker = ticker.upper()
        if ticker in universe_tickers:
            continue
        try:
            age_days = (now - datetime.fromisoformat(event_date).replace(tzinfo=timezone.utc)).days
        except ValueError:
            continue
        if 0 <= age_days <= DELISTING_RETENTION_DAYS:
            tickers.add(ticker)
    return tickers


def run_daily(yf=None, cache=None, history_fetcher=None):
    """Append today's closes for the live universe plus recently-delisted names.

    The live-universe leg costs zero additional network calls: yahoo_history() reads the
    on-disk cache fetch_advisor.py already warmed this run, same as build_momentum_screen.py.
    The recently-delisted leg is not in that universe and does cost real calls - that is
    the entire point, capturing a dying name's terminal price action before the free
    provider purges it for good (see DELISTING_RETENTION_DAYS above).
    """
    from common import load_json

    fetch = history_fetcher
    if fetch is None:
        from fetch_advisor import yahoo_history
        if yf is None:
            try:
                import yfinance as yf
            except ImportError:
                yf = None
        fetch = lambda ticker: yahoo_history(ticker, yf, cache=cache)

    payload = load_json("advisor.json") or {}
    universe_tickers = {row["ticker"].upper()
                        for row in [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
                        if row.get("ticker")}
    delisted_tickers = _resolvable_delisted_tickers(universe_tickers)

    total_added = total_conflicts = tickers_seen = 0
    for ticker in sorted(universe_tickers | delisted_tickers):
        history = fetch(ticker)
        dates = history.get("dates") or []
        if not dates:
            continue
        added, conflicts = append_series(
            ticker, dates, history.get("closes", []),
            history.get("volumes", [0] * len(dates)), "run_daily")
        total_added += added
        total_conflicts += conflicts
        tickers_seen += 1

    record_run({"mode": "run_daily", "tickers": tickers_seen, "rows_added": total_added,
                "conflicts": total_conflicts, "universe_tickers": len(universe_tickers),
                "delisted_tickers_polled": len(delisted_tickers)})
    return tickers_seen, total_added


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        tickers, rows = seed_from_disk()
        print(f"seeded {tickers} tickers, {rows} rows")
        print(archive_health())
    elif len(sys.argv) > 1 and sys.argv[1] == "daily":
        tickers, rows = run_daily()
        print(f"archived {tickers} tickers, {rows} new rows")
        print(archive_health())
    else:
        print(archive_health())
