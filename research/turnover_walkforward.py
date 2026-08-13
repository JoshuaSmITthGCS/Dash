"""Out-of-sample evaluation of the turnover-control challengers (C4 follow-up).

C4 measured nine turnover-control variants on one in-sample path and kept smooth07 and
hold6 as challengers because they won on that path. This harness applies the promotion
statistics the research contract actually gates on, using the same offline runs
(``backtest_monthly.py --cache-only`` per variant):

1. **Split-half walk-forward.** The variant chosen on the first half of the monthly path
   is scored only on the untouched second half, with one purged period at the boundary
   (monthly rebalances carry one-month labels, so ``label_overlap_periods(21, 21) == 0``;
   the purge is belt and braces).
2. **PBO** via CSCV over the ``[month][variant]`` return matrix
   (``evaluation.probability_of_backtest_overfitting``).
3. **Deflated Sharpe** per variant at the experiment registry's cumulative trial count.

Result on the 860-name cached universe (2021-2026, 60 months), recorded in
``pipeline/reports/turnover_walkforward.json``: the in-sample winner ranked LAST of seven
out-of-sample, PBO was 0.80-0.84 (above the 0.5 "selection is generating winners at
random" line), and no variant's deflated Sharpe probability exceeded 0.43 against the 0.95
gate. The in-sample ordering also disagrees with the earlier 360-name-cache run of
``turnover_control_matrix.py`` (there smooth07/hold6 led; here hold3/margin5 do), which is
the behavior of noise, not of a real effect. Decision: no turnover control is promotable.

Usage:
    for v in champion buffer15 buffer20 hold3 hold6 smooth07 margin5; do
        python pipeline/backtest_monthly.py --cache-only --years 5 <variant flags> \
            --out RUNS_DIR/bt_$v.json
    done
    python research/turnover_walkforward.py --runs-dir RUNS_DIR
"""

import argparse
import json
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from evaluation import deflated_sharpe_ratio, probability_of_backtest_overfitting

# Selection variants only: the tiered_* runs from turnover_control_matrix.py change the
# cost model, not the selection rule, so they are not competitors for "which selection wins".
SELECTION_VARIANTS = ["champion", "buffer15", "buffer20", "hold3", "hold6",
                      "smooth07", "margin5"]
OUT_PATH = os.path.join(REPO, "pipeline", "reports", "turnover_walkforward.json")


def monthly_returns(path):
    payload = json.load(open(path))
    values = [row["portfolio_value"] for row in payload["portfolio"]["rebalances"]]
    initial = payload["portfolio"]["metrics"].get("initial_value") or 100000.0
    series = [initial] + values
    return [series[i + 1] / series[i] - 1.0 for i in range(len(series) - 1)]


def sharpe(rets):
    if len(rets) < 3 or statistics.pstdev(rets) == 0:
        return None
    return statistics.mean(rets) / statistics.pstdev(rets)


def annualize(rets):
    total = 1.0
    for r in rets:
        total *= 1 + r
    years = len(rets) / 12.0
    return total ** (1 / years) - 1 if years > 0 else None


def registry_trials(default=47):
    path = os.path.join(REPO, "pipeline", "reports", "experiment_registry.json")
    try:
        report = json.load(open(path))
        return report.get("total_variants_tested") or default
    except (OSError, ValueError):
        return default


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", required=True,
                        help="directory holding bt_<variant>.json backtest outputs")
    args = parser.parse_args()

    returns = {}
    for name in SELECTION_VARIANTS:
        path = os.path.join(args.runs_dir, f"bt_{name}.json")
        if not os.path.exists(path):
            raise SystemExit(f"missing run: {path}")
        returns[name] = monthly_returns(path)
    n = min(len(r) for r in returns.values())
    returns = {k: v[:n] for k, v in returns.items()}

    half = n // 2
    train, test = slice(0, half), slice(half + 1, n)  # one purged period at the boundary
    train_perf = {k: annualize(v[train]) for k, v in returns.items()}
    test_perf = {k: annualize(v[test]) for k, v in returns.items()}
    winner = max(train_perf, key=train_perf.get)
    oos_rank = sorted(test_perf, key=lambda k: -(test_perf[k] or -9)).index(winner) + 1

    matrix = [[returns[k][i] for k in SELECTION_VARIANTS] for i in range(n)]
    trials = registry_trials()
    out = {
        "months": n,
        "walk_forward": {
            "train_months": half, "purged": 1,
            "in_sample_winner": winner,
            "train_cagr": train_perf, "test_cagr": test_perf,
            "winner_oos_rank": oos_rank,
            "n_selection_variants": len(SELECTION_VARIANTS),
        },
        "pbo_cscv": {str(s): probability_of_backtest_overfitting(matrix, splits=s)
                     for s in (6, 8)},
        "deflated_sharpe": {k: deflated_sharpe_ratio(sharpe(returns[k]), observations=n,
                                                     trials=trials)
                            for k in SELECTION_VARIANTS},
        "trials": trials,
        "interpretation": (
            "Promotion requires the in-sample winner to hold up out-of-sample, PBO below "
            "0.5, and a deflated Sharpe probability above 0.95. A winner that finishes "
            "last out-of-sample with PBO above 0.8 is the selection procedure measuring "
            "itself."),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(out, handle, indent=2)
        handle.write("\n")
    print(f"in-sample winner: {winner}; out-of-sample rank {oos_rank}/{len(SELECTION_VARIANTS)}; "
          f"PBO {out['pbo_cscv']}; wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
