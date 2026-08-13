"""Backtest of trading the swing screen alone, as a held portfolio with an equity curve.

pipeline/backtest_swing.py already measures whether the swing composite *ranks* well - IC,
ICIR, quantile spread, deflated Sharpe, PBO. That is the right question for a factor and the
wrong one for "what if I just did swing trading": a positive rank correlation says nothing
about what a book of twenty names actually returned after paying to rebalance it every week.
This module answers that second question, and deliberately does not touch the first. No
weight is tuned here, no variant is introduced, and backtest_swing.py's registered
statistics remain the model's evidence of record.

Everything is reused rather than rebuilt. The universe loader, the historical row builder
(which slices every price, volume and SUE input to the session being scored), the sector map
and the session calendar all come from backtest_swing.py; the scoring is swing_signals.
swing_scores and the book construction is swing_signals.book_rows, the same functions
build_swing_screen.py calls live; and the portfolio simulation, cost model and SPY leg come
from backtest_monthly.py. The only thing this file owns is the join between them.

**Construction choices, and why.**

* *Equal weight, not score weight.* The other portfolio backtests weight by score because an
  appeal score is a positive quantity. A swing composite is a cross-sectional z-score that is
  negative for half the universe by construction, so score-proportional weighting would
  either flip signs or clamp a third of the book to a tie at zero. Equal weight over the top
  ``--top-n`` of the book is the construction the shadow portfolios already declare, which
  also keeps this measurement and the prospective one comparable.
* *The book, then the top N.* Selection runs through ``swing_signals.book_rows`` first, so
  the entry percentile, the eligibility floor and the sector concentration cap all apply
  exactly as they do live. Ranking the raw scored rows instead would measure a screen nobody
  ships.
* *Weekly signal, next-session execution.* Same lock as every other backtest here: the
  signal is computed at a session close and the trade happens at the next session's close.

**Inherited limitations.** The analyst-revision leg cannot be reconstructed (estimate_
snapshots.py is forward-collection-only), so this walks a four-leg sub-composite of the
registered five-leg model, with the weight renormalized across the legs that did resolve -
swing_signals' declared behavior, not a special case. The market-cap gate is off (no
point-in-time share counts exist in the cache), sector labels are today's applied backward,
and the universe is today's cache walked backward and so carries survivorship bias. Every
one of these is backtest_swing.py's limitation too and is restated in the output.

Usage:
  python pipeline/backtest_swing_portfolio.py --years 3 --top-n 20
  python pipeline/backtest_swing_portfolio.py --years 1 --universe-limit 80   # smoke run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from bisect import bisect_right
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from backtest_monthly import (  # noqa: E402
    committed_benchmark,
    simulate_benchmark,
    simulate_locked_portfolio,
)
from backtest_swing import (  # noqa: E402
    MINIMUM_PRICE_HISTORY_SESSIONS,
    MINIMUM_ROWS_PER_PERIOD,
    current_sector_map,
    entry_index,
    estimates_coverage_note,
    historical_row,
    load_universe,
)
from common import LOG  # noqa: E402
import swing_signals  # noqa: E402

CADENCE_SESSIONS_DEFAULT = 5   # weekly, matching backtest_swing.py's rebalance cadence
BASELINE_VARIANT = "A"
OUTPUT = os.path.join(HERE, "backtest_swing_portfolio_results.json")


def rebalance_pairs(benchmark_dates, years, cadence_sessions):
    """``[(signal_date, execution_date)]`` on the benchmark's own session grid.

    Derived from the benchmark tape rather than the exchange calendar because
    simulate_locked_portfolio marks the book on exactly these dates: a signal session the
    benchmark series does not contain would never match an execution and the plan would be
    silently dropped.
    """
    dates = sorted(benchmark_dates)
    if len(dates) < 2:
        return []
    horizon = int(years * 252)
    start_index = max(0, len(dates) - horizon)
    pairs = []
    for index in range(start_index, len(dates) - 1, max(1, cadence_sessions)):
        pairs.append((dates[index], dates[index + 1]))
    return pairs


def selection_for_session(universe, sectors, as_of, config, current_members, variant, top_n):
    """The equal-weighted book the swing screen would have held at ``as_of``.

    Returns ``(rows, scored_count)``. ``rows`` carry the price the book is entered at, which
    is the same session's close - the *signal* close. Execution then happens at the next
    session's close inside simulate_locked_portfolio, so the entry price used for weighting
    and the price actually paid are correctly different.
    """
    base_rows, prices = [], {}
    for ticker, payload in universe.items():
        index = entry_index(payload["dates"], as_of)
        if index is None or index + 1 < MINIMUM_PRICE_HISTORY_SESSIONS:
            continue
        base_rows.append(historical_row(ticker, payload, index, as_of, sector=sectors.get(ticker)))
        prices[ticker] = payload["closes"][index]
    if len(base_rows) < MINIMUM_ROWS_PER_PERIOD:
        return [], 0, {}

    scored = swing_signals.swing_scores(base_rows, current_members=current_members,
                                        config=config, variant=variant)
    members = {row["ticker"]: True for row in scored if row.get("current_membership")}
    book = swing_signals.book_rows(scored, config)
    book.sort(key=lambda row: (-(row.get("score") or 0), row["ticker"]))
    selected = [row for row in book[:top_n] if prices.get(row["ticker"])]
    rows = [{"ticker": row["ticker"], "score": row.get("score"),
             "percentile": row.get("percentile"), "sector": row.get("sector"),
             "legs_resolved": row.get("legs_resolved"),
             "price": float(prices[row["ticker"]])}
            for row in selected]
    return rows, len(scored), members


def run_backtest(*, years=3, top_n=20, universe_limit=0, cadence_sessions=CADENCE_SESSIONS_DEFAULT,
                 initial_capital=100000.0, transaction_cost_bps=10.0, variant=BASELINE_VARIANT):
    universe = load_universe(universe_limit)
    if not universe:
        LOG.error("No cached price history in pipeline/data/backtest_cache")
        return None
    benchmark = committed_benchmark("SPY")
    if not benchmark:
        LOG.error("public/data/etf/SPY.json carries no usable price series")
        return None

    sectors = current_sector_map()
    config = {**swing_signals.DEFAULT_CONFIG, "minimum_market_cap": 0}
    pairs = rebalance_pairs(benchmark["dates"], years, cadence_sessions)
    if not pairs:
        LOG.error("No rebalance sessions available from the committed SPY history")
        return None

    plans, current_members = [], {}
    periods_with_book = 0
    book_sizes = []
    for index, (signal_date, execution_date) in enumerate(pairs, 1):
        rows, scored_count, members = selection_for_session(
            universe, sectors, signal_date, config, current_members, variant, top_n)
        if scored_count:
            current_members = members
        if not rows:
            plans.append({"signal_date": signal_date, "execution_date": execution_date,
                          "weights": {}, "picks": [], "book_size": 0})
            continue
        periods_with_book += 1
        book_sizes.append(len(rows))
        weight = 1 / len(rows)
        plans.append({
            "signal_date": signal_date,
            "execution_date": execution_date,
            "weights": {row["ticker"]: weight for row in rows},
            "picks": [{"ticker": row["ticker"], "score": row["score"],
                       "percentile": row["percentile"], "weight": round(weight, 8)}
                      for row in rows],
            "book_size": len(rows),
        })
        if index % 20 == 0:
            LOG.info(f"backtest_swing_portfolio: {index}/{len(pairs)} sessions, "
                     f"latest {signal_date} with {len(rows)} holdings")

    portfolio = simulate_locked_portfolio(plans, universe, benchmark, initial_capital,
                                          transaction_cost_bps)
    benchmark_result = simulate_benchmark(benchmark, plans[0]["execution_date"],
                                          initial_capital, transaction_cost_bps)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "screen": "swing",
        "model": "swing-v1.1.0",
        "research_status": "prospective_unvalidated",
        "variant": swing_signals.variant_spec(variant)["id"],
        "measured_legs": ["pead_drift", "high_volume_premium", "high_52w_proximity",
                          "short_term_reversal"],
        "excluded_legs": ["analyst_revision"],
        "method": {
            "signal": "swing_signals.swing_scores at a session close, then swing_signals.book_rows "
                     "(entry percentile, eligibility floor and sector concentration cap applied "
                     "exactly as the live screen applies them)",
            "execution": "next benchmark session close after the signal",
            "selection": f"top {top_n} of the constructed book",
            "weighting": "equal weight (the composite is a signed z-score, so score-proportional "
                        "weighting is not defined for it)",
            "rebalance_cadence_sessions": cadence_sessions,
            "prices": "pipeline/data/backtest_cache adjusted closes; benchmark from committed public/data/etf/SPY.json",
            "transaction_cost_bps_one_way": transaction_cost_bps,
            "cost_model": "flat",
            "rebalances_scheduled": len(pairs),
            "rebalances_with_a_book": periods_with_book,
            "mean_book_size": round(sum(book_sizes) / len(book_sizes), 2) if book_sizes else None,
        },
        "bias_disclosures": {
            "signal_return_lookahead": False,
            "survivorship_bias": True,
            "reason": "the backtest cache is today's universe walked backward, not dated index membership",
            "analyst_revision_leg": estimates_coverage_note(),
            "market_cap_gate": "disabled; no point-in-time share-count series exists in the cache",
            "sector_labels": "today's classification applied retroactively (the cache carries no sector field)",
            "short_interest_screen": "inert; no historical short-interest series exists",
        },
        "universe_usable": len(universe),
        "portfolio": portfolio,
        "benchmark_spy": benchmark_result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=float, default=3)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--universe-limit", type=int, default=0)
    parser.add_argument("--cadence-sessions", type=int, default=CADENCE_SESSIONS_DEFAULT)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--variant", default=BASELINE_VARIANT, choices=("A", "B", "C"))
    parser.add_argument("--out", default=OUTPUT)
    args = parser.parse_args(argv)

    result = run_backtest(years=args.years, top_n=args.top_n,
                          universe_limit=args.universe_limit,
                          cadence_sessions=args.cadence_sessions,
                          initial_capital=args.initial_capital,
                          transaction_cost_bps=args.transaction_cost_bps,
                          variant=args.variant)
    if not result:
        return 1
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    metrics, spy = result["portfolio"]["metrics"], result["benchmark_spy"]["metrics"]
    print(f"Swing portfolio CAGR {metrics.get('cagr', 0):.2%}, max DD "
          f"{metrics.get('maximum_drawdown', 0):.2%}, Sharpe {metrics.get('sharpe_zero_rate') or 0:.3f}")
    print(f"SPY             CAGR {spy.get('cagr', 0):.2%}, max DD {spy.get('maximum_drawdown', 0):.2%}")
    print(f"Held a book in {result['method']['rebalances_with_a_book']}/"
          f"{result['method']['rebalances_scheduled']} rebalances, mean size "
          f"{result['method']['mean_book_size']}, turnover {metrics.get('turnover')}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
