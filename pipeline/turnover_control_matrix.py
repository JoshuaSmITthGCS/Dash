"""Measure the turnover-control challengers against the champion, offline.

`portfolio_construction.py` shipped four controls with unit tests proving they behave as
specified, and no measurement -- the backtest needed five years of daily prices for the whole
universe, which was not on disk. `pipeline/data/backtest_cache/` now carries 360 symbols with
2,513 sessions each, and `backtest_monthly.committed_benchmark()` supplies SPY from committed
ETF history, so the whole thing runs with no network at all.

**Read the output as a diagnostic, not a promotion.** Three things bound what it can support:

1. **One universe, one period.** 360 cached names, not the 910-name configured universe or the
   860 the published backtest used, so the levels here are not comparable to the published
   11.14% CAGR. Only the *differences between variants* are, because every variant runs on
   exactly the same names over exactly the same months.
2. **In-sample.** No walk-forward split, no holdout. A variant that wins here has won on the
   data it was selected against.
3. **Nine variants tried**, which the experiment registry counts toward the deflation trial
   total. A 2.6pp CAGR spread across nine configurations on one path is well inside what noise
   produces.

The non-monotonic results are the tell and are reported rather than smoothed over: a 3-month
holding floor *hurts* while a 6-month floor helps, and both rank buffers hurt. A real effect
would not usually flip sign with the parameter.

Usage: python pipeline/turnover_control_matrix.py [--runs-dir DIR] [--skip-existing]
Output: pipeline/reports/turnover_control_matrix.json
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT_PATH = os.path.join(HERE, "reports", "turnover_control_matrix.json")
BACKTEST = os.path.join(HERE, "backtest_monthly.py")

# Fixed in advance, and deliberately small. Each entry is one CLI variant of the same backtest.
VARIANTS = {
    "champion": [],
    "buffer15": ["--rank-buffer", "1.5"],
    "buffer20": ["--rank-buffer", "2.0"],
    "hold3": ["--min-holding-months", "3"],
    "hold6": ["--min-holding-months", "6"],
    "smooth07": ["--score-smoothing", "0.7"],
    "margin5": ["--replacement-margin", "5"],
    "tiered_base": ["--cost-model", "tiered", "--cost-scenario", "base"],
    "tiered_stress": ["--cost-model", "tiered", "--cost-scenario", "stress"],
}

DESCRIPTIONS = {
    "champion": "plain top-20 every month, flat 10bps",
    "buffer15": "hold an incumbent while its rank stays inside 1.5x top-n",
    "buffer20": "hold an incumbent while its rank stays inside 2.0x top-n",
    "hold3": "hold each name at least 3 months unless its rank collapses past 3x top-n",
    "hold6": "hold each name at least 6 months unless its rank collapses past 3x top-n",
    "smooth07": "score smoothed as 0.7 x new + 0.3 x prior before ranking",
    "margin5": "a challenger must beat the incumbent it displaces by 5 score points",
    "tiered_base": "champion selection, costs.py base scenario instead of flat 10bps",
    "tiered_stress": "champion selection, costs.py stress scenario instead of flat 10bps",
}


def run_variant(name, flags, runs_dir, years=5, skip_existing=False):
    path = os.path.join(runs_dir, f"bt_{name}.json")
    if skip_existing and os.path.exists(path):
        return path
    command = [sys.executable, BACKTEST, "--cache-only", "--years", str(years),
               *flags, "--out", path]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return path


def summarize(path):
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    portfolio = payload["portfolio"]
    metrics = portfolio["metrics"]
    turnovers = [row["turnover"] for row in portfolio["rebalances"]
                 if row.get("turnover") is not None]
    return {
        "cagr": metrics["cagr"],
        "annualized_volatility": metrics["annualized_volatility"],
        "sharpe_zero_rate": metrics["sharpe_zero_rate"],
        "maximum_drawdown": metrics["maximum_drawdown"],
        "mean_monthly_turnover": round(statistics.mean(turnovers), 4) if turnovers else None,
        "estimated_transaction_cost": metrics["estimated_transaction_cost"],
        "unique_tickers_selected": metrics["unique_tickers_selected"],
        "final_value": metrics["final_value"],
    }


def build_report(results, universe_size=None, benchmark=None):
    champion = results["champion"]
    variants = {}
    for name, summary in results.items():
        variants[name] = {
            "description": DESCRIPTIONS[name],
            **summary,
            "cagr_delta_vs_champion_pp": round((summary["cagr"] - champion["cagr"]) * 100, 3),
            "turnover_delta_vs_champion_pp": (
                round((summary["mean_monthly_turnover"]
                       - champion["mean_monthly_turnover"]) * 100, 2)
                if summary["mean_monthly_turnover"] is not None else None),
            "sharpe_delta_vs_champion": round(
                summary["sharpe_zero_rate"] - champion["sharpe_zero_rate"], 4),
        }
    ranked = sorted(variants.items(), key=lambda item: -item[1]["cagr"])
    return {
        "schema_version": 1,
        "status": "measured_in_sample",
        "universe_size": universe_size,
        "benchmark": benchmark,
        "variants_tried": len(VARIANTS),
        "variants": variants,
        "ranked_by_cagr": [name for name, _ in ranked],
        "interpretation": {
            "comparable": ("differences between variants, which share the same names and the "
                           "same months"),
            "not_comparable": ("levels against the published 11.14% CAGR backtest, which used "
                               "860 names; this cache holds 360"),
            "in_sample": ("no walk-forward split and no holdout -- a variant that wins here "
                          "won on the data it was selected against"),
            "multiple_testing": (f"{len(VARIANTS)} variants tried, counted toward the "
                                 "deflation trial total in the experiment registry"),
            "non_monotonicity_warning": (
                "a 3-month holding floor hurts while a 6-month floor helps, and both rank "
                "buffers hurt. A real effect does not usually flip sign with the parameter, "
                "so treat the winners as noise candidates until walk-forward evidence exists"),
        },
        "promotion": {
            "promoted": [],
            "reason": ("promotion requires out-of-sample rank IC, deflated Sharpe, PBO and a "
                       "walk-forward split per docs/RESEARCH-CONTRACT.md; none of that is "
                       "satisfied by a single in-sample path"),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default=None,
                        help="where to write per-variant backtest artifacts (default: temp)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="reuse a variant's artifact if it is already in --runs-dir")
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args(argv)

    runs_dir = args.runs_dir or tempfile.mkdtemp(prefix="turnover-matrix-")
    os.makedirs(runs_dir, exist_ok=True)
    results = {}
    for name, flags in VARIANTS.items():
        path = run_variant(name, flags, runs_dir, args.years, args.skip_existing)
        results[name] = summarize(path)
        print(f"  {name:<16} CAGR {results[name]['cagr']:>7.2%}  "
              f"turnover {results[name]['mean_monthly_turnover']:>6.1%}")

    with open(os.path.join(runs_dir, "bt_champion.json"), encoding="utf-8") as handle:
        champion_payload = json.load(handle)
    report = build_report(results,
                          universe_size=champion_payload.get("universe_usable"),
                          benchmark="SPY from committed ETF history")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
