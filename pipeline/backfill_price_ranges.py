"""One-time(-ish) backfill of daily high/low into the price archive.

pipeline/price_archive.py has grown one real session of close and volume per live-universe
ticker on every scheduled refresh since 2026-08-11 (see its module docstring), and, from
SA-2026-08-28-01, high and low alongside them - but only for sessions recorded *after* that
change ships. First-write-wins means the archive never retroactively adds a high/low to a date
it already has (see append_series's docstring), so an ordinary daily run alone would need
months to build the trailing history pipeline/swing_signals.py's atr_compression wants.

This fills that gap in one pass: a ~2-year yfinance history per ticker, same shape and same
window fetch_advisor.yahoo_history() already uses for the live universe sweep, appended through
the same append_series() the daily job uses. Append-only and idempotent by construction - a
date the archive already has (from a prior backfill run or from a daily run) is a no-op here,
so an interrupted or re-run backfill costs nothing beyond the wasted network calls, and never
overwrites a value the daily job already recorded.

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
    tickers_seen = total_added = total_conflicts = failures = 0
    for ticker in tickers:
        history = history_fetcher(ticker) or {}
        dates = history.get("dates") or []
        if not dates:
            failures += 1
            LOG.warn(f"{ticker}: no history returned, skipping")
            continue
        added, conflicts = append_series(
            ticker, dates, history.get("closes", []),
            history.get("volumes", [0] * len(dates)), "backfill_ohlc",
            highs=history.get("highs"), lows=history.get("lows"))
        tickers_seen += 1
        total_added += added
        total_conflicts += conflicts
    return {"tickers_requested": len(tickers), "tickers_archived": tickers_seen,
            "rows_added": total_added, "conflicts": total_conflicts, "failures": failures}


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
