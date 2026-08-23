"""Unified CLI for the Round 10/11 backtest workflow: rebuild a signal panel, diagnose its
legs and quantile spread, and run the optimization harness against a bounded, explicitly-
sized set of candidate weight vectors -- one command instead of several scripts run by hand
in the right order against a panel that might be stale.

Two domains, selected with --domain:

- **fundamentals** (default) -- the 8 research-score legs (valuation, profitability,
  financial_health, growth, capital_allocation, accounting_quality, market_behavior,
  news_sentiment), panel built by backtest_monthly.py.
- **swing** -- the 5 swing-model legs (pead_drift, analyst_revision, high_volume_premium,
  high_52w_proximity, short_term_reversal), panel built by backtest_swing.py. Testing a
  candidate here never touches swing_signals.SWING_WEIGHTS or resets the swing-v1.1.0
  prospective clock -- see harness_freeze.json's changes_that_reset_this_clock.

Stages, each independently skippable:

1. **panel** -- rebuilds the domain's panel file. Needs real network access + yfinance, same
   requirement as backtest_historical.py/backtest_monthly.py/backtest_swing.py themselves --
   not meant to run in a sandboxed agent session without --cache-only (fundamentals only,
   uses what's already cached) or --skip-panel (diagnose/optimize the existing panel as-is).
2. **diagnosis** -- research/audit/round10/leg_diagnosis.py, read-only over the panel file.
   fundamentals-domain only (its leg names are hardcoded to that panel's shape); skipped
   automatically for --domain swing. No network needed.
3. **harness** -- pipeline/optimization_harness.py. Two ways to supply candidates, and they
   compose (both can run in the same invocation):
   - --candidates: an explicit, named, JSON weight-vector set you already decided on, plus
     each domain's registered default(s) (shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS for
     fundamentals; harness_freeze.json's registered swing-reversal-B for swing).
   - --auto-search N: N randomly perturbed neighbors of the champion/baseline weights,
     generated from --search-seed (reproducible) so the exact same batch can be regenerated
     from the printed seed alone. This is the "automatically pick weights" mode: run it,
     read the ranked report, hand the good candidates (or the whole report) back for the
     next round's --candidates, or bump --search-seed and go again. N is required, not
     inferred, per the research protocol's own "state up front how many candidates, and why"
     discipline -- this is bounded local search, not open-ended tuning.
   Every candidate in one invocation shares the same train/validation/holdout split and one
   shared PBO computation across the whole batch, matching optimization_harness.classify()'s
   contract. No network needed.

Usage:
    python3 pipeline/run_backtest_suite.py --years 5 --cache-only
    python3 pipeline/run_backtest_suite.py --skip-panel --auto-search 12 --search-seed 1
    python3 pipeline/run_backtest_suite.py --skip-panel --domain swing --auto-search 8
    python3 pipeline/run_backtest_suite.py --skip-panel --skip-diagnosis \
        --candidates '{"my_candidate": {"valuation": 0.5, "profitability": 0.5}}'
"""

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

LEG_DIAGNOSIS_SCRIPT = os.path.join(REPO, "research", "audit", "round10", "leg_diagnosis.py")
DEFAULT_HARNESS_OUT = os.path.join(REPO, "research", "audit", "round11", "harness_run_results.json")

DOMAINS = {
    "fundamentals": {
        "panel_path": os.path.join(HERE, "backtest_signal_panel.json"),
    },
    "swing": {
        "panel_path": os.path.join(HERE, "backtest_swing_signal_panel.json"),
    },
}

# harness_freeze.json's own registered swing-reversal-B weights (reversal leg removed, its
# 10% redistributed proportionally across the four continuation legs) -- transcribed exactly
# rather than re-derived, so a swing-domain run has at least one default candidate without
# guessing at one.
SWING_REVERSAL_B_WEIGHTS = {
    "pead_drift": 0.3333333333333333, "analyst_revision": 0.2777777777777778,
    "high_volume_premium": 0.2222222222222222, "high_52w_proximity": 0.16666666666666666,
}


def panel_path_for(domain):
    return DOMAINS[domain]["panel_path"]


def run_panel_stage(args):
    if args.domain == "fundamentals":
        cmd = [sys.executable, os.path.join(HERE, "backtest_monthly.py"),
              "--years", str(args.years), "--panel-out", panel_path_for(args.domain)]
        if args.cache_only:
            cmd.append("--cache-only")
        if args.refresh_cache:
            cmd.append("--refresh-cache")
        if args.tickers:
            cmd += ["--tickers", args.tickers]
        if args.universe_limit:
            cmd += ["--universe-limit", str(args.universe_limit)]
    else:
        cmd = [sys.executable, os.path.join(HERE, "backtest_swing.py"),
              "--years", str(args.years), "--panel-out", panel_path_for(args.domain)]
        if args.universe_limit:
            cmd += ["--universe-limit", str(args.universe_limit)]
    print(f"[panel] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=HERE)


def run_diagnosis_stage():
    print(f"[diagnosis] {sys.executable} {LEG_DIAGNOSIS_SCRIPT}")
    subprocess.run([sys.executable, LEG_DIAGNOSIS_SCRIPT], check=True, cwd=HERE)


def default_candidates(domain):
    """The registered candidate(s) for this domain with a known linear leg-weight vector.

    fundamentals: shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS, filtered to strategies
    actually registered (research_candidate_strategies()). swing: harness_freeze.json's own
    registered swing-reversal-B weights (see SWING_REVERSAL_B_WEIGHTS above). A candidate
    whose selection logic isn't a simple weight blend (variant C's residualized reversal, for
    instance) has no entry here and must be passed explicitly via --candidates instead.
    """
    if domain == "swing":
        return [("swing-reversal-B", dict(SWING_REVERSAL_B_WEIGHTS))]
    import shadow_portfolios
    registered = shadow_portfolios.research_candidate_strategies()
    return [(strategy_id, dict(weights))
           for strategy_id, weights in shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS.items()
           if strategy_id in registered]


def random_neighbor(base_weights, rng, *, perturbation, drop_probability):
    """One randomly perturbed neighbor of ``base_weights``, renormalized to the same total.

    Each leg's weight is scaled by a factor in ``[1 - perturbation, 1 + perturbation]``, then
    (independently, at ``drop_probability``) a leg may be dropped to 0 entirely -- exploring
    "remove this leg" hypotheses the same shape as R7's reweighted_composite_a proposal, not
    just "nudge every leg a little." At least one leg always survives. The result is
    renormalized so its total matches ``base_weights``'s total, keeping candidates comparable
    under composite_score's own renormalize-over-present-legs behavior.
    """
    scaled = {}
    for leg, weight in base_weights.items():
        if rng.random() < drop_probability:
            continue
        factor = 1 + rng.uniform(-perturbation, perturbation)
        scaled[leg] = max(0.0, weight * factor)
    if not sum(scaled.values()) or not scaled:
        # Degenerate draw (everything dropped or zeroed): fall back to the base weights
        # unchanged rather than emitting an all-zero candidate the harness can't score.
        return dict(base_weights)
    base_total = sum(base_weights.values())
    scaled_total = sum(scaled.values())
    return {leg: round(weight * base_total / scaled_total, 6) for leg, weight in scaled.items()}


def auto_search_candidates(base_weights, *, count, seed, perturbation, drop_probability):
    rng = random.Random(seed)
    return [(f"search-{seed}-{index:03d}",
            random_neighbor(base_weights, rng, perturbation=perturbation,
                            drop_probability=drop_probability))
           for index in range(count)]


def rank_key(candidate):
    # PROMOTE first, then KEEP_AS_CHALLENGER, then ABANDON; within a tier, higher validation
    # IC first. Missing IC sorts last within its tier rather than raising.
    decision_rank = {"PROMOTE": 0, "KEEP_AS_CHALLENGER": 1, "ABANDON": 2}
    return (decision_rank.get(candidate["suggested_decision"], 3),
           -(candidate["validation_mean_ic"] or float("-inf")))


def run_harness_stage(args):
    import optimization_harness as harness

    panel_path = panel_path_for(args.domain)
    panel_data = json.load(open(panel_path))
    periods = panel_data["periods"]
    champion_weights = panel_data["leg_weights"]

    candidates = [("champion", champion_weights)]
    if args.candidates:
        candidates += list(json.loads(args.candidates).items())
    else:
        candidates += default_candidates(args.domain)
    if args.auto_search:
        candidates += auto_search_candidates(
            champion_weights, count=args.auto_search, seed=args.search_seed,
            perturbation=args.search_perturbation, drop_probability=args.search_drop_probability)

    if len(candidates) < 2:
        print("[harness] no candidates beyond champion (pass --candidates or --auto-search), "
             "skipping")
        return

    panel = harness.Panel(periods, train_fraction=args.train_fraction,
                          validation_fraction=args.validation_fraction)
    session = harness.OptimizationSession(panel, pbo_splits=args.pbo_splits)
    report = harness.classify(session, candidates)

    ranked_candidates = [
        {
            "name": candidate["name"],
            "weights": candidate["weights"],
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
    ]
    ranked_candidates.sort(key=rank_key)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": args.domain,
        "panel_path": panel_path,
        "panel_periods": len(periods),
        "split": {"train": len(panel.train), "validation": len(panel.validation),
                  "holdout": len(panel.holdout)},
        "trial_count": session.trial_count,
        "search_overfitting": report["search_overfitting"],
        "auto_search": ({"count": args.auto_search, "seed": args.search_seed,
                        "perturbation": args.search_perturbation,
                        "drop_probability": args.search_drop_probability}
                       if args.auto_search else None),
        "candidates": ranked_candidates,
    }
    os.makedirs(os.path.dirname(args.harness_out), exist_ok=True)
    with open(args.harness_out, "w") as handle:
        json.dump(summary, handle, indent=2)
    print(f"[harness] wrote {args.harness_out}")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", choices=sorted(DOMAINS), default="fundamentals")
    parser.add_argument("--skip-panel", action="store_true",
                        help="Use the existing panel file for this domain as-is")
    parser.add_argument("--skip-diagnosis", action="store_true")
    parser.add_argument("--skip-harness", action="store_true")
    # Panel-stage passthrough.
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--cache-only", action="store_true",
                        help="fundamentals domain only")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="fundamentals domain only")
    parser.add_argument("--tickers", default="", help="fundamentals domain only")
    parser.add_argument("--universe-limit", type=int, default=0)
    # Harness-stage.
    parser.add_argument("--candidates", default="",
                        help="JSON object {name: {leg: weight}} to test against champion. "
                             "Composes with --auto-search; defaults to the domain's "
                             "registered candidate(s) if neither is given.")
    parser.add_argument("--auto-search", type=int, default=0, metavar="N",
                        help="Also generate N randomly perturbed neighbors of the champion "
                             "weights and test them alongside --candidates. Required to be "
                             "explicit (no default count) -- state how many up front.")
    parser.add_argument("--search-seed", type=int, default=0,
                        help="Reproducible: the same seed regenerates the same batch")
    parser.add_argument("--search-perturbation", type=float, default=0.5,
                        help="Each leg's weight is scaled by a factor in "
                             "[1-perturbation, 1+perturbation]")
    parser.add_argument("--search-drop-probability", type=float, default=0.3,
                        help="Chance each leg is dropped to 0 entirely in a given candidate")
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--pbo-splits", type=int, default=8)
    parser.add_argument("--harness-out", default=DEFAULT_HARNESS_OUT)
    args = parser.parse_args()

    if not args.skip_panel:
        run_panel_stage(args)
    else:
        print(f"[panel] skipped, using existing {panel_path_for(args.domain)}")

    if args.skip_diagnosis or args.domain != "fundamentals":
        print("[diagnosis] skipped" + ("" if args.skip_diagnosis else " (fundamentals-only stage)"))
    else:
        run_diagnosis_stage()

    if not args.skip_harness:
        run_harness_stage(args)
    else:
        print("[harness] skipped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
