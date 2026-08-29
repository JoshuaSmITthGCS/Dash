"""Append-only daily archive of each ticker's ATM implied volatility. The data an IV
rank/percentile needs, that this pipeline never used to persist.

Every options screen fetches a live option chain fresh on every run and discards it
afterward - options_common.py's implied/realized-vol-ratio and skew signals only ever need
today's snapshot. An IV rank or IV percentile is a different kind of question ("is today's
reading rich or cheap *relative to this ticker's own recent history*"), and answering it
needs that history archived somewhere, since no free provider available to this pipeline
serves historical implied volatility - only the current live chain.

Design mirrors price_archive.py deliberately: one JSON file per ticker under
pipeline/data/iv_archive/, date-keyed rows, a manifest with per-run counts and a staleness
health check, first-write-wins on an already-archived date. Two differences from that
module, both explained below:

1. No seed_from_disk(). price_archive.py can backfill instantly because Yahoo serves
   decades of historical closes today; there is no equivalent for implied volatility - the
   options endpoint only ever returns the CURRENT chain. This archive starts genuinely
   empty on the day it ships and can only grow one trading day at a time. With
   MINIMUM_IV_PERCENTILE_SAMPLES=60 below, that means iv_percentile() reads as None for
   every ticker for roughly the first three months after deployment, then fills in
   gradually per ticker as each one crosses 60 archived sessions. This is a real, stated
   cold-start cost, not a bug to be papered over - see research/STATE.md's identical
   disclosure for the PIT store's own "8 calendar days" bootstrap gap.

2. No conflicts.jsonl. price_archive logs archived-vs-incoming mismatches because Yahoo's
   adjusted close for an already-archived HISTORICAL date keeps drifting as later dividends
   change the adjustment factor - a real, permanent record worth keeping. An IV observation
   is only ever written for TODAY (see append_observation's `date` parameter, always the
   run's own as_of), so a same-day mismatch is just duplicate-run noise, not the kind of
   drift that needs a permanent log.

Only pipeline/build_options_strategies.py writes to this archive (see that module's
fetch_chain) - it's the one options-screen script the scheduled refresh-advisor.yml job
runs unconditionally, at a fixed ~7-day-to-expiration target shared across every mechanism
it derives. The other options screens (protective-put, collar, vertical-spread,
advanced-strategies) fetch chains at different target expirations and are not scheduled
with their ENABLE_*_SCREEN flags on; if they also wrote here, the archived series would mix
tenors and "percentile vs. its own history" would stop meaning anything. Every screen may
still READ iv_percentile() - it's a ticker-level number, independent of which screen shows
it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(HERE, "data", "iv_archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "archive_manifest.json")

MAX_STALENESS_DAYS = 4  # matches price_archive.py - a daily schedule with weekend slack
MINIMUM_IV_PERCENTILE_SAMPLES = 60  # ~3 trading months - never rank off a handful of points
DEFAULT_LOOKBACK = 252  # ~1 trading year


def _path(ticker):
    return os.path.join(ARCHIVE_DIR, f"{ticker.upper()}.json")


def append_observation(ticker, date, iv, dte, source):
    """Records one ticker's ATM IV for `date` (always the run's own as_of - never a
    historical backfill, since none is possible - see module docstring). First-write-wins:
    a second call for a date already on file changes nothing and reports it as not added,
    the same append-only contract price_archive.append_series uses for prices.

    Returns True if the row was newly added, False if that date was already archived or
    `iv` isn't a usable number.
    """
    if iv is None or not (iv == iv) or iv <= 0:  # iv == iv is false for NaN
        return False
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = _path(ticker)
    rows = {}
    if os.path.exists(path):
        rows = json.load(open(path)).get("rows", {})
    if date in rows:
        return False
    rows[date] = [round(float(iv), 4), int(dte) if dte is not None else None]
    json.dump({"ticker": ticker.upper(), "rows": rows, "source": source}, open(path, "w"))
    return True


def load_series(ticker):
    """This ticker's archived (dates, ivs, dtes), oldest first. All-empty when the ticker
    has never been archived - the same "no fabricated value" shape every reader in this
    pipeline returns on missing history, not an exception.
    """
    path = _path(ticker)
    if not os.path.exists(path):
        return {"dates": [], "ivs": [], "dtes": []}
    rows = json.load(open(path)).get("rows", {})
    dates = sorted(rows)
    ivs = [rows[d][0] for d in dates]
    dtes = [rows[d][1] if len(rows[d]) > 1 else None for d in dates]
    return {"dates": dates, "ivs": ivs, "dtes": dtes}


def iv_percentile(ticker, lookback=DEFAULT_LOOKBACK, minimum_samples=MINIMUM_IV_PERCENTILE_SAMPLES):
    """Percentile rank (0-100) of this ticker's most recently archived ATM IV among its own
    trailing `lookback` archived readings. None below `minimum_samples` - see module
    docstring for why that floor takes roughly three months to clear after this ships.

    This is the real thing realized_vol_percentile (options_common.py) was always a stand-in
    for: a genuine IV rank/percentile, not a realized-volatility proxy for one. Keep both
    published fields distinct in every caller - never let this collapse into that one.
    """
    series = load_series(ticker)["ivs"]
    series = series[-lookback:]
    if len(series) < minimum_samples:
        return None
    current = series[-1]
    return round(100 * sum(1 for value in series if value <= current) / len(series), 2)


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
    json.dump(manifest, open(MANIFEST, "w"), indent=1)


def archive_health(now=None):
    """healthy / degraded / critical, for the data-health surface - same contract as
    price_archive.archive_health(). "critical" here does not mean iv_percentile is broken;
    a brand-new archive is expected to read unhealthy until its first run, same as every
    other archive in this pipeline before its first write.
    """
    now = now or datetime.now(timezone.utc)
    if not os.path.exists(MANIFEST):
        return {"state": "critical", "reason": "IV archive has never run"}
    manifest = json.load(open(MANIFEST))
    runs = manifest.get("runs") or []
    if not runs:
        return {"state": "critical", "reason": "IV archive has no recorded runs"}
    last = datetime.fromisoformat(runs[-1]["at"])
    age_days = (now - last).total_seconds() / 86400
    if age_days > MAX_STALENESS_DAYS:
        return {"state": "critical",
                "reason": f"last IV archive run {age_days:.1f} days ago, limit {MAX_STALENESS_DAYS}"}
    return {"state": "healthy", "last_run": runs[-1]["at"], "tickers": runs[-1].get("tickers_seen")}
