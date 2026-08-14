"""Is ValueSignal doing more than repackaging known factor exposure?

`docs/P0-Q1-BENCHMARK.md` established that SPY is the wrong yardstick for a beta-0.79,
small/mid-tilted book, and that against RSP and IWM the strategy is competitive or better. It
also established, via a six-factor Newey-West regression, that no residual alpha survives once
market, size, value, profitability, investment and momentum are controlled for
(annualized alpha -2.57%, |t| = 0.437).

This extends the benchmark side of that work using ETFs already committed to the repository.
The academic factor regression answers "is there alpha versus the factor *model*". A tradeable
style benchmark answers a blunter and more useful question: **could the same result have been
had by buying one liquid ETF?** Those are different bars, and the second is the one a user of
this product actually faces.

Every benchmark leg is priced identically to how `backtest_monthly.py` already prices its SPY
leg -- `simulate_benchmark()`, buy-and-hold from the strategy's own first execution date, one
10bps entry cost, no further trading -- so the legs are directly comparable on start date,
capital and cost treatment. Reuses `p0_q1_benchmark_factor_report`'s loaders and OLS rather
than reimplementing them.

No network access. A sector-neutral composite is still not built, for the reason given in
`docs/P0-Q1-BENCHMARK.md`: only 193 of the 397 tickers that passed through the portfolio have a
sector label anywhere on disk, and fabricating the other 51% is not evidence.

`p0_q1_benchmark_factor_report.py` already publishes buy-and-hold metrics for this benchmark
set to `benchmark_comparison.json`. What it does not publish, and what decides the question
above, is a regression of the strategy *on each individual fund*. That is what this adds, to
its own artifact.

Usage: python pipeline/benchmark_suite.py
Output: pipeline/reports/benchmark_alpha_regressions.json
"""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from backtest_monthly import performance_metrics, simulate_benchmark  # noqa: E402
from p0_q1_benchmark_factor_report import (BACKTEST_PATH, ETF_DIR, load_etf_benchmark,  # noqa: E402
                                           monthly_returns, ols_newey_west)

# Deliberately NOT benchmark_comparison.json: p0_q1_benchmark_factor_report.py owns that
# file and writes buy-and-hold metrics for the same benchmark set. This module adds the one
# thing that report does not have -- a Newey-West regression of the strategy on each
# individual tradeable fund -- so it gets its own path rather than racing for the same one.
OUT_PATH = os.path.join(HERE, "reports", "benchmark_alpha_regressions.json")
ENTRY_COST_BPS = 10.0

# Committed ETFs standing in for the exposures the six-factor regression found significant
# (market t=6.50, size t=2.06, momentum t=2.50) plus the two it did not (value, profitability).
# Chosen for coverage of the whole 2021-08..2026-07 window and for being liquid enough that a
# retail investor could genuinely have bought them instead.
BENCHMARKS = {
    "SPY": "S&P 500 -- the published, least representative comparison",
    "RSP": "S&P 500 equal weight -- breadth-matched",
    "IWM": "Russell 2000 -- small cap",
    "IJH": "S&P MidCap 400 -- the strategy's actual size band",
    "IJR": "S&P SmallCap 600",
    "VB": "CRSP US small cap",
    "IWD": "Russell 1000 Value",
    "IWF": "Russell 1000 Growth",
    "VTV": "CRSP US large value",
    "VUG": "CRSP US large growth",
    "SCHD": "Dow Jones US Dividend 100 -- quality/dividend screen",
    "NOBL": "S&P 500 Dividend Aristocrats -- quality proxy",
    "VXF": "Extended market (completion index) -- everything outside the S&P 500",
}

# A passive two-ETF blend chosen to match the strategy's *measured* exposures rather than its
# stated design: mid-cap size plus large value, which is where the regression said the book
# actually sits. Not optimized -- a fixed 50/50, fixed in advance.
BLEND = {"name": "IJH+IWD 50/50", "weights": {"IJH": 0.5, "IWD": 0.5},
         "rationale": ("matches the realized beta 0.79 / SMB 0.455 profile the six-factor "
                       "regression measured, using a fixed 50/50 rather than a fitted mix")}


def available(ticker):
    return os.path.exists(os.path.join(ETF_DIR, f"{ticker}.json"))


def blended_history(weights, start_date, initial_capital):
    """Monthly-return blend of two buy-and-hold legs, rebalanced never.

    Each leg is simulated exactly as a standalone benchmark, then combined at fixed weights on
    the shared daily grid. A never-rebalanced blend is the honest passive comparison -- adding
    rebalancing would give the benchmark a trading policy the strategy is not being compared
    against.
    """
    legs = {}
    for ticker, weight in weights.items():
        result = simulate_benchmark(load_etf_benchmark(ticker), start_date,
                                    initial_capital * weight, ENTRY_COST_BPS)
        legs[ticker] = {row["date"]: row["value"] for row in result["history"]}
    shared = sorted(set.intersection(*(set(leg) for leg in legs.values())))
    return [{"date": day, "value": sum(leg[day] for leg in legs.values())} for day in shared]


def _metrics_from_history(history, initial_capital):
    """Use the published backtest's daily/calendar metric path for every leg."""
    monthly = monthly_returns([row["date"] for row in history], [row["value"] for row in history])
    measured = performance_metrics(history, initial_capital)
    return {
        "final_value": round(history[-1]["value"], 2),
        "cagr": measured.get("cagr"),
        "volatility": measured.get("annualized_volatility"),
        "sharpe": measured.get("sharpe_zero_rate"),
        "max_drawdown": measured.get("maximum_drawdown"),
    }, monthly


def regress_on_benchmark(strategy_monthly, benchmark_monthly):
    """Single-benchmark OLS with Newey-West errors: alpha against one tradeable fund.

    A positive, significant alpha here means the strategy did something this ETF could not.
    An insignificant one means a user could have bought the ETF instead.
    """
    months = sorted(set(strategy_monthly) & set(benchmark_monthly))
    if len(months) < 24:
        return {"status": "insufficient_overlap", "months": len(months)}
    result = ols_newey_west(
        np.array([strategy_monthly[month] for month in months]),
        {"benchmark": np.array([benchmark_monthly[month] for month in months])},
    )
    alpha = result["coefficients"]["alpha"]
    # Read the key directly rather than with a default: a silently-defaulted t-statistic
    # publishes "0.00" for every benchmark, which reads as a real (and very confident) result.
    newey_west_t = alpha["newey_west_t_statistic"]
    return {
        "months": len(months),
        "beta": round(result["coefficients"]["benchmark"]["estimate"], 4),
        "monthly_alpha": round(alpha["estimate"], 6),
        "annualized_alpha_pct": round(((1 + alpha["estimate"]) ** 12 - 1) * 100, 3),
        "newey_west_t_statistic": round(newey_west_t, 3) if newey_west_t is not None else None,
        "classical_t_statistic": (round(alpha["classical_t_statistic"], 3)
                                  if alpha["classical_t_statistic"] is not None else None),
        "r_squared": round(result["r_squared"], 4),
    }


def build_report(backtest=None):
    if backtest is None:
        with open(BACKTEST_PATH, encoding="utf-8") as handle:
            backtest = json.load(handle)
    portfolio = backtest["portfolio"]
    start_date = portfolio["metrics"]["start_date"]
    initial_capital = portfolio["metrics"]["initial_value"]
    strategy_metrics, strategy_monthly = _metrics_from_history(
        portfolio["history"], initial_capital)

    legs, missing = {}, []
    for ticker, description in BENCHMARKS.items():
        if not available(ticker):
            missing.append(ticker)
            continue
        result = simulate_benchmark(load_etf_benchmark(ticker), start_date,
                                    initial_capital, ENTRY_COST_BPS)
        metrics, monthly = _metrics_from_history(result["history"], initial_capital)
        legs[ticker] = {
            "description": description,
            **metrics,
            "strategy_versus_this_benchmark": regress_on_benchmark(strategy_monthly, monthly),
        }

    if all(available(ticker) for ticker in BLEND["weights"]):
        metrics, monthly = _metrics_from_history(
            blended_history(BLEND["weights"], start_date, initial_capital), initial_capital)
        legs[BLEND["name"]] = {
            "description": BLEND["rationale"],
            **metrics,
            "strategy_versus_this_benchmark": regress_on_benchmark(strategy_monthly, monthly),
        }

    beaten = [name for name, leg in legs.items() if strategy_metrics["cagr"] > leg["cagr"]]
    significant = [
        name for name, leg in legs.items()
        if abs(leg["strategy_versus_this_benchmark"].get("newey_west_t_statistic") or 0) >= 2.0
        and (leg["strategy_versus_this_benchmark"].get("monthly_alpha") or 0) > 0
    ]
    return {
        "schema_version": 1,
        "generated_at": backtest.get("generated_at"),
        "source": "pipeline/backtest_monthly_results.json + public/data/etf/*.json",
        "method": ("every leg is buy-and-hold from the strategy's first execution date with one "
                   "10bps entry cost, identical to how backtest_monthly.py prices its SPY leg"),
        "window": {"start": start_date, "initial_capital": initial_capital},
        "strategy": strategy_metrics,
        "benchmarks": legs,
        "benchmarks_unavailable": missing,
        "sector_neutral_composite": {
            "built": False,
            "reason": ("only 193 of 397 tickers that passed through the portfolio carry a "
                       "sector label anywhere on disk; labelling the rest would be fabrication"),
        },
        "summary": {
            "benchmarks_compared": len(legs),
            "beaten_on_cagr": sorted(beaten),
            "beaten_on_cagr_count": f"{len(beaten)} of {len(legs)}",
            "significant_positive_alpha_against": sorted(significant),
            "verdict": (
                "no tradeable benchmark in this set is beaten with statistically significant "
                "alpha" if not significant else
                f"significant positive alpha against {len(significant)} benchmark(s)"),
        },
    }


def main():
    report = build_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    strategy = report["strategy"]
    print(f"{'benchmark':<16} {'CAGR':>8} {'vol':>8} {'Sharpe':>7} {'maxDD':>8} "
          f"{'beta':>6} {'alpha%':>8} {'NW t':>6}")
    print(f"{'STRATEGY':<16} {strategy['cagr']:>7.2%} {strategy['volatility']:>7.2%} "
          f"{strategy['sharpe']:>7.3f} {strategy['max_drawdown']:>7.2%}")
    for name, leg in report["benchmarks"].items():
        regression = leg["strategy_versus_this_benchmark"]
        print(f"{name:<16} {leg['cagr']:>7.2%} {leg['volatility']:>7.2%} "
              f"{leg['sharpe']:>7.3f} {leg['max_drawdown']:>7.2%} "
              f"{regression.get('beta', float('nan')):>6.2f} "
              f"{regression.get('annualized_alpha_pct', float('nan')):>8.2f} "
              f"{regression.get('newey_west_t_statistic', float('nan')):>6.2f}")
    print(f"\nbeaten on CAGR: {report['summary']['beaten_on_cagr_count']}")
    print(f"verdict: {report['summary']['verdict']}")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
