"""Retrospective backtest of the "Emerging growth" screen (prospective, unvalidated).

Reuses every piece of pipeline/backtest_monthly.py's machinery -- the monthly rebalance
calendar, Yahoo fetch/cache, cost model, locked-portfolio simulation, SPY benchmark leg --
and swaps only the ranking step: pipeline/rank_emerging_growth.py's Python port of
src/lib/researchScreens.js::rankEmergingGrowth in place of the champion appeal score. When
fewer than --top-n names qualify in a given month (a strict qualification screen, not a
full-universe ranking), the unallocated weight sits in cash rather than force-filling the
portfolio with names that failed the gates -- see appeal_weights()/simulate_locked_portfolio
in backtest_monthly.py, unmodified here.

This session's network policy blocks the Yahoo fetch this needs, so it could not be run or
verified against live data here. Run it wherever you have network access and upload
pipeline/backtest_emerging_growth_results.json back -- that is the actual measurement this
brief's "no new factors without incremental-IC evidence" rule requires before this screen
could ever be promoted past prospective_unvalidated.

Usage (identical flags to backtest_monthly.py):
  python pipeline/backtest_emerging_growth.py --years 5 --top-n 20 \\
      --out pipeline/backtest_emerging_growth_results.json

Useful comparison once you have a result: run pipeline/backtest_monthly.py with the same
--years/--top-n/--cost-model on the same cached universe (--cache-dir can point at the same
directory both scripts populate, since both use load_or_fetch's per-symbol cache) and diff
the two portfolios' CAGR/Sharpe/max-drawdown against each other and against SPY.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from backtest_historical import (  # noqa: E402
    REPORT_LAG_DAYS_DEFAULT,
    fetch_benchmark,
    load_universe,
    price_index,
)
from backtest_monthly import (  # noqa: E402
    COST_MODELS,
    appeal_weights,
    build_rebalance_calendar,
    load_or_fetch,
    simulate_benchmark,
    simulate_locked_portfolio,
)
from common import LOG  # noqa: E402
from rank_emerging_growth import rank_week_emerging_growth  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--universe-limit", type=int, default=0)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--report-lag-days", type=int, default=REPORT_LAG_DAYS_DEFAULT)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--cost-model", choices=COST_MODELS, default="flat")
    parser.add_argument("--cost-scenario", choices=("optimistic", "base", "stress"), default="base")
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--yfinance-cache-dir", default="")
    parser.add_argument("--cache-dir", default=os.path.join(HERE, "data", "backtest_cache"))
    parser.add_argument("--out", default=os.path.join(HERE, "backtest_emerging_growth_results.json"))
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. Install pipeline/requirements.txt first.")
        return 1
    if args.yfinance_cache_dir:
        os.makedirs(args.yfinance_cache_dir, exist_ok=True)
        yf.set_tz_cache_location(args.yfinance_cache_dir)

    symbols = load_universe(args.universe_limit, args.tickers)
    LOG.info(f"Fetching/caching {len(symbols)} candidates for a {args.years}-year emerging-growth backtest")
    universe_data = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        pending = {
            executor.submit(load_or_fetch, yf, symbol, args.delay, args.cache_dir,
                            args.refresh_cache, args.cache_only): symbol
            for symbol in symbols
        }
        for index, future in enumerate(as_completed(pending), 1):
            symbol = pending[future]
            try:
                data = future.result()
            except Exception as exc:  # noqa: BLE001
                LOG.warn(f"{symbol}: worker failed ({type(exc).__name__}: {exc})")
                data = None
            if data:
                universe_data[symbol] = data
            if index % 25 == 0:
                LOG.info(f"...{index}/{len(symbols)} fetched, {len(universe_data)} usable")

    if args.fetch_only:
        LOG.info(f"Fetch complete: {len(universe_data)}/{len(symbols)} usable")
        return 0

    benchmark = fetch_benchmark(yf, "SPY", args.delay, history_period="10y")
    if not benchmark:
        LOG.error("Could not fetch SPY")
        return 1
    calendar = build_rebalance_calendar(benchmark["dates"], args.years)
    if len(calendar) < args.years * 12:
        LOG.error(f"Only {len(calendar)} monthly execution dates were available")
        return 1

    plans = []
    months_with_zero_qualifiers = 0
    for index, (signal_date, execution_date) in enumerate(calendar, 1):
        spy_idx = price_index(benchmark["dates"], signal_date)
        spy_to_date = benchmark["closes"][:spy_idx + 1] if spy_idx is not None else []
        rows = rank_week_emerging_growth(
            universe_data, spy_to_date, signal_date, args.report_lag_days,
            allow_current_shares=False, allow_empty_fundamentals=True,
        )
        if not rows:
            months_with_zero_qualifiers += 1
        weights = appeal_weights(rows, args.top_n)
        picks = [
            {"ticker": row["ticker"], "appeal_score": row["score"], "weight": round(weights[row["ticker"]], 8),
             "screen": row["screen"]}
            for row in rows[:args.top_n] if row["ticker"] in weights
        ]
        plans.append({
            "signal_date": signal_date.isoformat(),
            "execution_date": execution_date.isoformat(),
            "weights": weights,
            "picks": picks,
            "qualifiers_this_month": len(rows),
        })
        if index % 12 == 0:
            LOG.info(f"Ranked {index}/{len(calendar)} months; latest signal {signal_date}, "
                     f"{len(rows)} qualifiers")

    portfolio = simulate_locked_portfolio(
        plans, universe_data, benchmark, args.initial_capital, args.transaction_cost_bps,
        cost_model=args.cost_model, cost_scenario=args.cost_scenario,
    )
    benchmark_result = simulate_benchmark(
        benchmark, plans[0]["execution_date"], args.initial_capital, args.transaction_cost_bps,
    )
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "screen": "emerging_growth",
        "research_status": "prospective_unvalidated",
        "method": {
            "signal": "rank_emerging_growth.emerging_growth_score at month-end (Python port of "
                     "src/lib/researchScreens.js::rankEmergingGrowth) over rank_week's point-in-time rows",
            "execution": "next SPY trading-day close after signal",
            "selection": f"top {args.top_n} qualifiers (strict screen -- unfilled slots sit in cash, not backfilled)",
            "weighting": "emerging-growth rank score divided by sum of selected rank scores",
            "fundamental_availability": f"quarter end plus {args.report_lag_days} calendar days",
            "prices": "Yahoo adjusted close (split and dividend adjusted)",
            "transaction_cost_bps_one_way": args.transaction_cost_bps,
            "cost_model": args.cost_model,
            "cost_scenario": args.cost_scenario if args.cost_model == "tiered" else None,
            "months_with_zero_qualifiers": months_with_zero_qualifiers,
            "total_months": len(calendar),
        },
        "bias_disclosures": {
            "signal_return_lookahead": False,
            "survivorship_bias": True,
            "reason": "advisor_universe.json is a current candidate list, not dated Russell 1000 membership",
            "filing_date_approximation": True,
        },
        "universe_requested": len(symbols),
        "universe_usable": len(universe_data),
        "portfolio": portfolio,
        "benchmark_spy": benchmark_result,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    strategy = portfolio["metrics"]
    spy = benchmark_result["metrics"]
    print(f"Emerging-growth CAGR {strategy.get('cagr', 0):.2%}, max DD {strategy.get('maximum_drawdown', 0):.2%}, "
          f"Sharpe {strategy.get('sharpe_zero_rate', 0):.3f}")
    print(f"SPY CAGR             {spy.get('cagr', 0):.2%}, max DD {spy.get('maximum_drawdown', 0):.2%}")
    print(f"Qualified in {len(calendar) - months_with_zero_qualifiers}/{len(calendar)} months, "
          f"{strategy.get('unique_tickers_selected', 0)} unique picks, usable universe {len(universe_data)}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
