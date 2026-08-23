"""Unified CLI for the Round 10/11 backtest workflow: rebuild the monthly signal panel,
diagnose its legs and quantile spread, and run the optimization harness against the
standing shadow-strategy proposal(s) -- one command instead of three scripts run by hand in
the right order against a panel that might be stale.

Stages, each independently skippable:

1. **panel** -- ``backtest_monthly.py --panel-out pipeline/backtest_signal_panel.json``.
   Since Round 11 Priority 4, this is where the EDGAR point-in-time growth fallback
   (``backtest_historical.edgar_pit_growth_fallback``) actually takes effect: rebuilding the
   panel is what lets a fresh run pick up real growth-leg coverage instead of the 0% Round 10
   diagnosed. Needs real network access + yfinance -- same requirement as
   ``backtest_historical.py``/``backtest_monthly.py`` themselves, not meant to run in a
   sandboxed agent session without ``--cache-only`` (uses only what's already cached) or
   ``--skip-panel`` (diagnose/optimize the existing panel file as-is).
2. **diagnosis** -- ``research/audit/round10/leg_diagnosis.py``, read-only over the panel
   file. No network needed.
3. **harness** -- ``pipeline/optimization_harness.py``, comparing the panel's champion
   ``leg_weights`` against the registered shadow-strategy candidate(s)
   (``shadow_portfolios.REWEIGHTED_A_WEIGHTS`` by default, or ``--candidates`` for a
   different, explicitly bounded set -- per the research protocol's own "propose, then
   register, then test" discipline, this is not meant for open-ended search). No network
   needed.

Usage:
    python3 pipeline/run_backtest_suite.py --years 5 --cache-only
    python3 pipeline/run_backtest_suite.py --skip-panel
    python3 pipeline/run_backtest_suite.py --skip-panel --skip-diagnosis \
        --candidates '{"my_candidate": {"valuation": 0.5, "profitability": 0.5}}'
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

PANEL_PATH = os.path.join(HERE, "backtest_signal_panel.json")
LEG_DIAGNOSIS_SCRIPT = os.path.join(REPO, "research", "audit", "round10", "leg_diagnosis.py")
DEFAULT_HARNESS_OUT = os.path.join(REPO, "research", "audit", "round11", "harness_run_results.json")


def run_panel_stage(args):
    cmd = [sys.executable, os.path.join(HERE, "backtest_monthly.py"),
          "--years", str(args.years), "--panel-out", PANEL_PATH]
    if args.cache_only:
        cmd.append("--cache-only")
    if args.refresh_cache:
        cmd.append("--refresh-cache")
    if args.tickers:
        cmd += ["--tickers", args.tickers]
    if args.universe_limit:
        cmd += ["--universe-limit", str(args.universe_limit)]
    print(f"[panel] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=HERE)


def run_diagnosis_stage():
    print(f"[diagnosis] {sys.executable} {LEG_DIAGNOSIS_SCRIPT}")
    subprocess.run([sys.executable, LEG_DIAGNOSIS_SCRIPT], check=True, cwd=HERE)


def default_candidates():
    """The registered research-candidate shadows (shadow_portfolios.research_candidate_
    strategies()) that have a known linear leg-weight vector, via the explicit
    shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS map. A candidate whose selection logic
    isn't a simple weight blend (none exist today) has no entry there and must be passed
    explicitly via --candidates instead.
    """
    import shadow_portfolios
    registered = shadow_portfolios.research_candidate_strategies()
    return [(strategy_id, dict(weights))
           for strategy_id, weights in shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS.items()
           if strategy_id in registered]


def run_harness_stage(args):
    import optimization_harness as harness

    panel_data = json.load(open(PANEL_PATH))
    periods = panel_data["periods"]
    champion_weights = panel_data["leg_weights"]

    candidates = [("champion", champion_weights)]
    if args.candidates:
        candidates += list(json.loads(args.candidates).items())
    else:
        candidates += default_candidates()

    if len(candidates) < 2:
        print("[harness] no candidates beyond champion (pass --candidates), skipping")
        return

    panel = harness.Panel(periods, train_fraction=args.train_fraction,
                          validation_fraction=args.validation_fraction)
    session = harness.OptimizationSession(panel, pbo_splits=args.pbo_splits)
    report = harness.classify(session, candidates)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel_path": PANEL_PATH,
        "panel_periods": len(periods),
        "split": {"train": len(panel.train), "validation": len(panel.validation),
                  "holdout": len(panel.holdout)},
        "trial_count": session.trial_count,
        "search_overfitting": report["search_overfitting"],
        "candidates": [
            {
                "name": candidate["name"],
                "train_mean_ic": candidate["train_mean_ic"],
                "validation_mean_ic": candidate["validation_mean_ic"],
                "walk_forward_efficiency": candidate["walk_forward_efficiency"],
                "deflated_sharpe_probability":
                    candidate["validation_verdict"]["deflated_sharpe_probability"],
                "ship": candidate["validation_verdict"]["ship"],
                "suggested_decision": candidate["suggested_decision"],
                "reason": candidate["reason"],
            }
            for candidate in report["candidates"]
        ],
    }
    os.makedirs(os.path.dirname(args.harness_out), exist_ok=True)
    with open(args.harness_out, "w") as handle:
        json.dump(summary, handle, indent=2)
    print(f"[harness] wrote {args.harness_out}")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-panel", action="store_true",
                        help="Use the existing pipeline/backtest_signal_panel.json as-is")
    parser.add_argument("--skip-diagnosis", action="store_true")
    parser.add_argument("--skip-harness", action="store_true")
    # Panel-stage passthrough (see backtest_monthly.py --help for the full set).
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--tickers", default="")
    parser.add_argument("--universe-limit", type=int, default=0)
    # Harness-stage.
    parser.add_argument("--candidates", default="",
                        help="JSON object {name: {leg: weight}} to test against champion. "
                             "Defaults to the registered shadow-strategy candidate(s).")
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--pbo-splits", type=int, default=8)
    parser.add_argument("--harness-out", default=DEFAULT_HARNESS_OUT)
    args = parser.parse_args()

    if not args.skip_panel:
        run_panel_stage(args)
    else:
        print(f"[panel] skipped, using existing {PANEL_PATH}")

    if not args.skip_diagnosis:
        run_diagnosis_stage()
    else:
        print("[diagnosis] skipped")

    if not args.skip_harness:
        run_harness_stage(args)
    else:
        print("[harness] skipped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
