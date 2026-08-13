"""Backtest of following disclosed political and institutional trades and nothing else.

Same walk-forward machinery as every other portfolio backtest here - build_rebalance_
calendar, simulate_locked_portfolio, simulate_benchmark and the SPY leg all come from
backtest_monthly.py unchanged - with the ranking step replaced by political_institutional.
rank_disclosed_trades. Prices come from pipeline/data/backtest_cache and the benchmark from
the committed public/data/etf/SPY.json, so this runs with no network access at all.

**Read the coverage block before reading the returns.** The two disclosure stores this
strategy is made of are shallow in opposite ways:

  congressional disclosures   collected forward only, and the published screen carries a
                              rolling 120-day publication window. At the time of writing
                              that is five distinct disclosure months, and the earliest two
                              contain no purchase above congress_signal's $15,000 material
                              floor - so the strategy holds cash through them, correctly,
                              and the tradable history is shorter still.
  13F institutional filings   two quarter-ends in the store, which is exactly one
                              quarter-over-quarter change, which is one signal date. A
                              breadth-of-accumulation factor cannot be measured from one
                              observation, and this file does not pretend otherwise.

So the honest output of this module today is a coverage report with a return series far too
short to interpret, and ``status`` says so rather than leaving the reader to infer it from a
period count. That is the point: the strategy is measurable *going forward* through the
shadow portfolio (``shadow_portfolios.py``'s ``political_institutional``), and this file is
what gets rerun as the disclosure stores deepen. Nothing here should be quoted as evidence
that following disclosed trades does or does not work.

The dates are handled the one way that matters: a disclosure is visible on the date it was
*disclosed*, never the date it was traded. See political_institutional.visible_congress_rows
- the lag in this store runs past a year, and reading transaction dates would produce a
gorgeous, entirely fictional backtest.

Usage:
  python pipeline/backtest_political_institutional.py --years 5 --top-n 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from backtest_monthly import (  # noqa: E402
    appeal_weights,
    build_rebalance_calendar,
    committed_benchmark,
    simulate_benchmark,
    simulate_locked_portfolio,
)
from backtest_swing import entry_index, load_universe  # noqa: E402
from common import LOG  # noqa: E402
from political_institutional import coverage, rank_disclosed_trades  # noqa: E402

REPO_ROOT = os.path.dirname(HERE)
SCREENS = os.path.join(REPO_ROOT, "public", "data", "screens")
OUTPUT = os.path.join(HERE, "backtest_political_institutional_results.json")

# Below this many months carrying at least one qualifying disclosure, the return series is
# reported as a coverage measurement rather than a performance one. Twelve is not a
# statistical threshold -- no threshold this file could pick would make a five-month window
# interpretable -- it is the point below which publishing a CAGR would be actively
# misleading, so the metrics stay in the payload and the status flag governs how they read.
MINIMUM_MONTHS_WITH_SIGNAL = 12


def _read_json(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback if fallback is not None else {}


def load_disclosures(screens_dir=SCREENS):
    """The two published disclosure screens' result rows.

    The *published screens* are read rather than the raw jsonl stores because
    congress_signal.score_congressional_buying scores off ``flags`` (EXTRAORDINARY_BUY),
    which build_congress_screen.classify attaches and the raw store does not carry.
    """
    congress = _read_json(os.path.join(screens_dir, "congress-trades.json")).get("results") or []
    institutional = _read_json(os.path.join(screens_dir, "institutional-13f.json")).get("results") or []
    return congress, institutional


def priced_rows(ranked, universe, as_of):
    """Attach each ranked ticker's close as of ``as_of``, dropping names with no price.

    A disclosed ticker with no cached price series is not tradable in this simulation, so
    it is dropped here rather than silently weighted at a stale or absent price. ETFs and
    fixed-income tickers members disclose fall out this way too, since the cache holds the
    equity universe only.
    """
    rows = []
    for row in ranked:
        payload = universe.get(row["ticker"])
        if not payload:
            continue
        index = entry_index(payload["dates"], as_of)
        if index is None:
            continue
        price = payload["closes"][index]
        if not price or price <= 0:
            continue
        rows.append({**row, "price": float(price)})
    return rows


def run_backtest(*, years=5, top_n=20, universe_limit=0, initial_capital=100000.0,
                 transaction_cost_bps=10.0, screens_dir=SCREENS):
    universe = load_universe(universe_limit)
    if not universe:
        LOG.error("No cached price history in pipeline/data/backtest_cache")
        return None
    congress, institutional = load_disclosures(screens_dir)
    benchmark = committed_benchmark("SPY")
    if not benchmark:
        LOG.error("public/data/etf/SPY.json carries no usable price series")
        return None

    calendar = build_rebalance_calendar(benchmark["dates"], years)
    if not calendar:
        LOG.error("No monthly execution dates available from the committed SPY history")
        return None

    plans = []
    months_with_signal = 0
    for signal_date, execution_date in calendar:
        as_of = signal_date.isoformat()
        ranked = rank_disclosed_trades(congress, institutional, as_of=as_of,
                                       universe=set(universe))
        rows = priced_rows(ranked, universe, as_of)
        weights = appeal_weights(rows, top_n)
        if weights:
            months_with_signal += 1
        picks = [{"ticker": row["ticker"], "score": row["score"],
                  "political_points": row["political_points"],
                  "institutional_points": row["institutional_points"],
                  "members_buying": row["members_buying"],
                  "managers_added": row["managers_added"],
                  "weight": round(weights[row["ticker"]], 8)}
                 for row in rows[:top_n] if row["ticker"] in weights]
        plans.append({
            "signal_date": as_of,
            "execution_date": execution_date.isoformat(),
            "weights": weights,
            "picks": picks,
            "qualifiers_this_month": len(rows),
        })

    portfolio = simulate_locked_portfolio(plans, universe, benchmark, initial_capital,
                                          transaction_cost_bps)
    benchmark_result = simulate_benchmark(benchmark, plans[0]["execution_date"],
                                          initial_capital, transaction_cost_bps)
    disclosure_coverage = coverage(congress, institutional)
    sufficient = months_with_signal >= MINIMUM_MONTHS_WITH_SIGNAL
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "screen": "political_institutional",
        "research_status": "prospective_unvalidated",
        "status": "measured" if sufficient else "insufficient_disclosure_history",
        "status_detail": (
            f"{months_with_signal} of {len(calendar)} monthly rebalances carried at least one "
            f"qualifying disclosure. Below {MINIMUM_MONTHS_WITH_SIGNAL} the return series is a "
            "coverage measurement, not a performance measurement, and no annualized figure "
            "derived from it should be quoted."
        ) if not sufficient else f"{months_with_signal} of {len(calendar)} monthly rebalances carried a signal.",
        "method": {
            "signal": "political_institutional.rank_disclosed_trades: reward-only congressional "
                     "purchase points (congress_signal) plus lag-decayed 13F breadth "
                     "(institutional_ownership), summed at their native scale",
            "visibility_gate": "congressional disclosure_date and 13F filing date; transaction "
                              "dates and quarter ends are never read",
            "execution": "next SPY trading-day close after the month-end signal",
            "selection": f"top {top_n} disclosed names (unfilled slots sit in cash, not backfilled)",
            "weighting": "disclosure score divided by sum of selected scores",
            "prices": "pipeline/data/backtest_cache adjusted closes; benchmark from committed public/data/etf/SPY.json",
            "transaction_cost_bps_one_way": transaction_cost_bps,
            "cost_model": "flat",
            "months_with_signal": months_with_signal,
            "total_months": len(calendar),
        },
        "disclosure_coverage": disclosure_coverage,
        "bias_disclosures": {
            "signal_return_lookahead": False,
            "survivorship_bias": True,
            "reason": "the backtest cache is today's universe walked backward, not dated index membership",
            "congressional_source_coverage": "senate-efd only in the current store; the House "
                                             "and FMP mirrors are dark, so member breadth is "
                                             "understated and the breadth term is compressed",
            "institutional_history": "two 13F quarter-ends in the store, so at most one "
                                     "quarter-over-quarter accumulation signal exists across "
                                     "the whole window",
            "disclosure_window": "the published congress screen keeps a rolling publication "
                                 "window, so early history is not merely thin, it is absent",
        },
        "universe_usable": len(universe),
        "portfolio": portfolio,
        "benchmark_spy": benchmark_result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--universe-limit", type=int, default=0)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--out", default=OUTPUT)
    args = parser.parse_args(argv)

    result = run_backtest(years=args.years, top_n=args.top_n,
                          universe_limit=args.universe_limit,
                          initial_capital=args.initial_capital,
                          transaction_cost_bps=args.transaction_cost_bps)
    if not result:
        return 1
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    method, metrics = result["method"], result["portfolio"]["metrics"]
    print(f"Political + institutional: signal in {method['months_with_signal']}/"
          f"{method['total_months']} months ({result['status']})")
    print(f"  congressional disclosures {result['disclosure_coverage']['congress_disclosures']} "
          f"over {result['disclosure_coverage']['congress_distinct_disclosure_months']} month(s); "
          f"13F filing dates {result['disclosure_coverage']['institutional_distinct_filing_dates']}")
    print(f"  total return {metrics.get('total_return', 0):.2%}, "
          f"max DD {metrics.get('maximum_drawdown', 0):.2%}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
