"""One-time(-ish) backfill of daily high/low into the price archive.

pipeline/price_archive.py's seed_from_disk() had already back-filled close/volume for every
ticker's entire available backtest_cache history (back to the 1980s for some names) before
SA-2026-08-28-01 added high/low capture at all - so on this archive, "a date it already has"
describes essentially every historical date on day one, not just the ~17 sessions the daily job
had appended since 2026-08-11. The first real run against this archive confirmed it: with
append_series's original all-or-nothing first-write-wins rule, a full backfill upgraded exactly
one row per ticker (today's, the only genuinely new date) and silently discarded the high/low
for every historical date, because every one of those already had a close/volume-only row.
append_series now upgrades an existing row in place - close and volume untouched, a missing
high/low filled in - whenever the incoming close agrees with what is already archived (not a
restatement, just previously-uncaptured data); see its docstring. That is what actually makes
this script a backfill instead of a slower version of the daily job.

This fills that gap in one pass: a ~2-year yfinance history per ticker, same shape and same
window fetch_advisor.yahoo_history() already uses for the live universe sweep, appended through
the same append_series() the daily job uses. Idempotent by construction - a date the archive
already has a high/low for is a no-op here, so an interrupted or re-run backfill costs nothing
beyond the wasted network calls, and it never overwrites a price the daily job already recorded.

Deliberately does not touch pipeline/data/backtest_cache/: that tree is a pinned fixture, and
writing through its symlinks has corrupted it once already (docs/SESSION-HANDOFF.md,
docs/SURVIVORSHIP-RECONSTRUCTION-2.md section 3a). Every row this script writes lands in the
separate, actively-growing price_archive instead.

Usage:
    python pipeline/backfill_price_ranges.py            # the whole live universe
    python pipeline/backfill_price_ranges.py --limit 25  # a sample, for a first look
"""
from __future__ import annotations

import argparse
import json

from common import LOG, load_json
from price_archive import append_series, record_run


def live_universe_tickers(payload=None):
    """Every ticker the daily job also archives - see price_archive.run_daily."""
    payload = payload if payload is not None else (load_json("advisor.json") or {})
    return sorted({
        row["ticker"].upper()
        for row in [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
        if row.get("ticker")
    })


def backfill(tickers, history_fetcher, limit=None):
    """Fetch and archive one ~2-year history per ticker. Returns a JSON-printable summary."""
    if limit:
        tickers = tickers[:limit]
    tickers_seen = total_added = total_conflicts = total_upgraded = failures = 0
    for ticker in tickers:
        history = history_fetcher(ticker) or {}
        dates = history.get("dates") or []
        if not dates:
            failures += 1
            LOG.warn(f"{ticker}: no history returned, skipping")
            continue
        added, conflicts, upgraded = append_series(
            ticker, dates, history.get("closes", []),
            history.get("volumes", [0] * len(dates)), "backfill_ohlc",
            highs=history.get("highs"), lows=history.get("lows"))
        tickers_seen += 1
        total_added += added
        total_conflicts += conflicts
        total_upgraded += upgraded
    return {"tickers_requested": len(tickers), "tickers_archived": tickers_seen,
            "rows_added": total_added, "rows_upgraded": total_upgraded,
            "conflicts": total_conflicts, "failures": failures}


def _default_history_fetcher():
    from fetch_advisor import yahoo_history
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    return lambda ticker: yahoo_history(ticker, yf)


def run(limit=None):
    tickers = live_universe_tickers()
    summary = backfill(tickers, _default_history_fetcher(), limit=limit)
    record_run({"mode": "backfill_price_ranges", **summary})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="Backfill only the first N tickers - for a sample run.")
    args = parser.parse_args()
    print(json.dumps(run(limit=args.limit), indent=1))
