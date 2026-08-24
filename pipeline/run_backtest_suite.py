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
4. **elo** -- pipeline/elo_tournament.py, opt-in via --elo-rounds N. A single split answers
   "who wins on this one comparison"; this instead runs many bootstrap resamples of the
   validation slice and lets ratings accumulate, revealing whether an apparent edge between
   candidates is robust across resamples of the SAME data, not a way to manufacture more
   information than the panel actually has -- if the panel can't distinguish two candidates
   (as harness stage PBO readings can already tell you), their Elo ratings will stay close
   together round after round rather than one falsely pulling ahead. --include-formula adds
   a coverage-and-signal-derived candidate (optimization_harness.formula_weights(), computed
   from the train slice only): weight_leg proportional to coverage_leg * max(0,
   standalone_ic_leg), directly correcting the common drift where a leg's hand-set weight
   stops tracking its real, currently-measured coverage and predictive power. --elo-search N
   adds N more candidates that each independently sample every leg in the panel's full
   universe from [--elo-search-min, --elo-search-max] and renormalize -- not a perturbation
   around champion (that's --auto-search's job in the harness stage), but a genuine sweep
   across each leg's own declared range, so the leaderboard ranks an actual population of
   candidates rather than a handful of named ones. N is required, no default count, matching
   --auto-search's "state how many up front" discipline. No network needed.

Cross-stage candidate flags (harness AND elo stages):

- --include-equal-weight: adds a 1/N-per-leg candidate -- the no-opinion control every
  weighting scheme should beat.
- --include-blend (with --blend-ratio, default 0.5): adds a candidate blending equal-weight
  with this domain's recommended weights (reweighted_composite_a for fundamentals, if
  registered), so every leg keeps a nonzero share even where the recommended candidate drops
  one to zero.
- --sector-breakdown (harness stage, fundamentals-only): per-sector formula_weights()
  computed independently on the train slice, using each ticker's CURRENT sector applied
  retroactively (same disclosed approximation as backtest_swing.py's current_sector_map) --
  answers whether e.g. tech warrants a different leg weighting than the champion vector
  applies uniformly. Requires a panel rebuilt with sector tagging.
- --top-n-from-elo N --elo-results-in PATH (harness stage): pulls the top N names off a
  previous elo run's leaderboard and adds them as harness (and, with --holdout-check,
  holdout) candidates -- "test the top N" without retyping weight vectors.

Usage:
    python3 pipeline/run_backtest_suite.py --years 5 --cache-only
    python3 pipeline/run_backtest_suite.py --skip-panel --auto-search 12 --search-seed 1
    python3 pipeline/run_backtest_suite.py --skip-panel --domain swing --auto-search 8
    python3 pipeline/run_backtest_suite.py --skip-panel --skip-diagnosis \
        --candidates '{"my_candidate": {"valuation": 0.5, "profitability": 0.5}}'
    python3 pipeline/run_backtest_suite.py --skip-panel --skip-diagnosis --skip-harness \
        --elo-rounds 300 --include-formula
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
DEFAULT_ELO_OUT = os.path.join(REPO, "research", "audit", "round11", "elo_tournament_results.json")
DEFAULT_ELO_K = 24.0

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


def universe_legs(periods):
    """Every leg name that appears anywhere in the panel, not just the ones champion happens
    to declare -- the actual universe a range sweep should draw from.
    """
    return sorted({leg for period in periods
                  for scores in (period.get("leg_scores") or {}).values() for leg in scores})


def range_sampled_candidate(legs, rng, *, minimum, maximum):
    """One weight vector: each leg drawn independently and uniformly from
    ``[minimum, maximum]``, normalized to sum to 1.

    Unlike ``random_neighbor`` (a perturbation *around* one base point), this samples the
    whole declared range for every leg independently -- covering the space a leg's weight
    could plausibly take, not just the neighborhood of whatever champion already does. An
    all-zero draw (possible when ``minimum`` is 0) falls back to an equal-weight vector
    rather than emitting a candidate composite_score can't score at all.
    """
    raw = {leg: rng.uniform(minimum, maximum) for leg in legs}
    total = sum(raw.values())
    if not total:
        return {leg: round(1.0 / len(legs), 6) for leg in legs}
    return {leg: round(weight / total, 6) for leg, weight in raw.items()}


def range_search_candidates(legs, *, count, seed, minimum, maximum):
    rng = random.Random(seed)
    return [(f"range-{seed}-{index:03d}",
            range_sampled_candidate(legs, rng, minimum=minimum, maximum=maximum))
           for index in range(count)]


def recommended_weights(domain):
    """The (name, weights) pair used as the blend's other pole for --include-blend.

    fundamentals: reweighted_composite_a if it's registered (R7's own pre-registered
    finding), else whatever default_candidates(domain) returns first. swing:
    swing-reversal-B, the domain's only registered default.
    """
    candidates = default_candidates(domain)
    if not candidates:
        return None
    for name, weights in candidates:
        if name == "reweighted_composite_a":
            return name, weights
    return candidates[0]


def shared_extra_candidates(args, domain, periods):
    """--include-equal-weight / --include-blend candidates, shared by the harness and elo
    stages so both "backtest them" paths the user asked for see the same two extra
    candidates.
    """
    import optimization_harness as harness

    extra = []
    legs = universe_legs(periods)
    if getattr(args, "include_equal_weight", False):
        extra.append(("equal_weight", harness.equal_weight_candidate(legs)))
    if getattr(args, "include_blend", False):
        picked = recommended_weights(domain)
        if picked is None:
            print("[candidates] --include-blend requested but no recommended candidate is "
                 "registered for this domain, skipping")
        else:
            name, recommended = picked
            blended = harness.blended_full_coverage_candidate(recommended, legs, blend=args.blend_ratio)
            extra.append((f"equal_blend_{name}", blended))
    return extra


def load_elo_leaderboard(path):
    with open(path) as handle:
        data = json.load(handle)
    return data["leaderboard"], data["candidates"]


def top_candidates_from_elo(path, count, *, exclude):
    """The top ``count`` non-excluded names from a previously-written elo_tournament_results.json,
    as (name, weights) pairs in leaderboard order.

    Lets "test the top N" mean exactly that: rank once in the elo stage, then feed that
    same ranking's winners into a fresh harness (and, with --holdout-check, holdout) pass
    on a later run -- without hand-retyping weight vectors from a printed leaderboard.
    """
    leaderboard, elo_candidates = load_elo_leaderboard(path)
    picked = []
    for row in leaderboard:
        if len(picked) >= count:
            break
        name = row["name"]
        if name in exclude:
            continue
        weights = elo_candidates.get(name)
        if not weights:
            continue
        picked.append((name, weights))
        exclude.add(name)
    return picked


def rank_key(candidate):
    # PROMOTE first, then KEEP_AS_CHALLENGER, then ABANDON; within a tier, higher validation
    # IC first. Missing IC sorts last within its tier rather than raising.
    decision_rank = {"PROMOTE": 0, "KEEP_AS_CHALLENGER": 1, "ABANDON": 2}
    return (decision_rank.get(candidate["suggested_decision"], 3),
           -(candidate["validation_mean_ic"] or float("-inf")))


def holdout_check(panel, candidates, *, trial_count, quantiles=5, periods_per_year=12):
    """A single, one-time evaluation on ``panel.holdout`` -- periods no other stage in this
    file ever reads (``OptimizationSession.evaluate()`` structurally cannot reach them; this
    function is the only place in the whole CLI that does).

    Call this ONLY once you already have a specific, small shortlist you believe in from the
    validation-side search. Running it repeatedly, or calling it before you have a shortlist,
    turns holdout into more validation data and defeats the entire reason it was kept
    separate. There is no flag anywhere that runs this automatically as part of a normal
    search loop -- --holdout-check must be passed explicitly, every time, by a human who has
    decided this is the moment to spend it.
    """
    import optimization_harness as harness
    results = []
    for name, weights in candidates:
        scored = harness.score_with_weights(panel.holdout, weights)
        verdict = harness.evaluate_candidate(scored, trials=trial_count, quantiles=quantiles,
                                             periods_per_year=periods_per_year)
        results.append({
            "name": name, "weights": weights,
            "holdout_mean_ic": verdict["ic"]["mean_ic"], "holdout_periods": verdict["ic"]["periods"],
            "deflated_sharpe_probability": verdict["deflated_sharpe_probability"],
            "ship": verdict["ship"], "ship_blockers": verdict.get("ship_blockers"),
        })
    return results


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
    candidates += shared_extra_candidates(args, args.domain, periods)
    if args.top_n_from_elo:
        if not args.elo_results_in:
            print("[harness] --top-n-from-elo requires --elo-results-in PATH, skipping")
        else:
            existing = {name for name, _ in candidates}
            added = top_candidates_from_elo(args.elo_results_in, args.top_n_from_elo, exclude=existing)
            candidates += added
            print(f"[harness] added top {len(added)} candidates from "
                 f"{args.elo_results_in}'s leaderboard: {[name for name, _ in added]}")

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

    if args.sector_breakdown:
        if args.domain != "fundamentals":
            print("[sector] --sector-breakdown is fundamentals-only (swing panels carry no "
                 "sector labels), skipping")
        else:
            sector_report = harness.sector_weight_report(panel.train)
            if not sector_report:
                print("[sector] no sector labels found in this panel -- rebuild it with the "
                     "current backtest_monthly.py to pick up sector tagging")
            else:
                summary["sector_breakdown"] = sector_report
                print("\n[sector] per-sector formula_weights(), train slice only:")
                for sector, row in sector_report.items():
                    if row["formula_weights"] is None:
                        print(f"  {sector:<28} {row['reason']}")
                    else:
                        weights = ", ".join(f"{leg}={weight}" for leg, weight in
                                            sorted(row["formula_weights"].items(),
                                                  key=lambda item: -item[1]))
                        print(f"  {sector:<28} ({row['usable_periods']} periods) {weights}")

    if args.holdout_check:
        print("\n" + "=" * 70)
        print("[holdout] ONE-TIME CHECK -- spending the holdout slice now.")
        print("[holdout] These periods have never been read by any other stage. Don't pass")
        print("[holdout] --holdout-check again to keep searching on this same panel -- doing")
        print("[holdout] so turns holdout into more validation data and defeats the point.")
        print("=" * 70)
        holdout_results = holdout_check(panel, candidates, trial_count=session.trial_count)
        summary["holdout_check"] = holdout_results
        for row in holdout_results:
            print(f"  {row['name']:<28} holdout_mean_ic={row['holdout_mean_ic']} "
                 f"periods={row['holdout_periods']} "
                 f"deflated_sharpe={row['deflated_sharpe_probability']} ship={row['ship']}")

    os.makedirs(os.path.dirname(args.harness_out), exist_ok=True)
    with open(args.harness_out, "w") as handle:
        json.dump(summary, handle, indent=2)
    print(f"[harness] wrote {args.harness_out}")
    print(json.dumps(summary, indent=2))


def run_elo_stage(args):
    import elo_tournament
    import optimization_harness as harness

    panel_path = panel_path_for(args.domain)
    panel_data = json.load(open(panel_path))
    periods = panel_data["periods"]
    champion_weights = panel_data["leg_weights"]

    panel = harness.Panel(periods, train_fraction=args.train_fraction,
                          validation_fraction=args.validation_fraction)

    candidates = [("champion", champion_weights)]
    if args.candidates:
        candidates += list(json.loads(args.candidates).items())
    else:
        candidates += default_candidates(args.domain)
    if args.include_formula:
        formula = harness.formula_weights(panel.train)
        if formula:
            candidates.append(("formula", formula))
        else:
            print("[elo] formula_weights() returned nothing usable on the train slice, "
                 "skipping that candidate")
    candidates += shared_extra_candidates(args, args.domain, periods)
    if args.elo_search:
        legs = universe_legs(periods)
        candidates += range_search_candidates(
            legs, count=args.elo_search, seed=args.elo_search_seed,
            minimum=args.elo_search_min, maximum=args.elo_search_max)
        print(f"[elo] added {args.elo_search} range-sampled candidates over {len(legs)} legs "
             f"(each leg drawn from [{args.elo_search_min}, {args.elo_search_max}], "
             f"seed={args.elo_search_seed})")

    if len(candidates) < 2:
        print("[elo] no candidates beyond champion (pass --candidates or --include-formula), "
             "skipping")
        return

    result = elo_tournament.run_tournament(
        panel.validation, candidates, rounds=args.elo_rounds, seed=args.elo_seed,
        k=args.elo_k, sample_size=args.elo_sample_size or None)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["domain"] = args.domain
    result["panel_path"] = panel_path
    result["candidates"] = {name: weights for name, weights in candidates}

    os.makedirs(os.path.dirname(args.elo_out), exist_ok=True)
    with open(args.elo_out, "w") as handle:
        json.dump(result, handle, indent=2)
    print(f"[elo] wrote {args.elo_out}")
    print(f"[elo] leaderboard after {args.elo_rounds} rounds, {len(candidates)} candidates "
         f"(pool={result['pool_size']} validation periods, sample={result['sample_size']}):")
    board = result["leaderboard"]
    shown = board if len(board) <= 25 else board[:15] + board[-5:]
    for index, row in enumerate(shown):
        if len(board) > 25 and index == 15:
            print(f"  ... {len(board) - 20} more in {args.elo_out} ...")
        print(f"  {row['elo']:>7.1f}  {row['name']}")


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
    parser.add_argument("--include-equal-weight", action="store_true",
                        help="Also test a 1/N-per-leg candidate -- the no-opinion baseline. "
                             "Available in both the harness and elo stages.")
    parser.add_argument("--include-blend", action="store_true",
                        help="Also test a candidate blending equal-weight with this domain's "
                             "recommended weights (reweighted_composite_a for fundamentals if "
                             "registered) -- unlike the recommended candidate alone, every leg "
                             "keeps a nonzero share. See --blend-ratio. Available in both the "
                             "harness and elo stages.")
    parser.add_argument("--blend-ratio", type=float, default=0.5,
                        help="Weight given to the recommended candidate in --include-blend "
                             "(the rest goes to equal-weight); 0.5 = an even split")
    parser.add_argument("--sector-breakdown", action="store_true",
                        help="Fundamentals-only. Print/record formula_weights() computed "
                             "independently per sector (train slice only) -- whether tech, "
                             "say, warrants a different leg weighting than the champion "
                             "vector applies uniformly. Requires a panel rebuilt with sector "
                             "tagging (current backtest_monthly.py).")
    parser.add_argument("--top-n-from-elo", type=int, default=0, metavar="N",
                        help="Pull the top N names off a previous elo run's leaderboard "
                             "(--elo-results-in PATH) and add them as harness candidates -- "
                             "'test the top N' without retyping weight vectors by hand.")
    parser.add_argument("--elo-results-in", default="",
                        help="Path to a previously-written elo_tournament_results.json, read "
                             "by --top-n-from-elo")
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--pbo-splits", type=int, default=8)
    parser.add_argument("--harness-out", default=DEFAULT_HARNESS_OUT)
    parser.add_argument("--holdout-check", action="store_true",
                        help="Spend the one-time holdout evaluation on this run's candidates. "
                             "Only pass this once you have a specific shortlist you already "
                             "believe in from validation-side search -- see holdout_check()'s "
                             "own docstring for why this must never become routine.")
    # Elo-stage. Opt-in: only runs when --elo-rounds is set above 0.
    parser.add_argument("--elo-rounds", type=int, default=0, metavar="N",
                        help="Run pipeline/elo_tournament.py for N bootstrap rounds over the "
                             "same candidates as the harness stage. 0 (default) skips it.")
    parser.add_argument("--elo-seed", type=int, default=0)
    parser.add_argument("--elo-k", type=float, default=DEFAULT_ELO_K)
    parser.add_argument("--elo-sample-size", type=int, default=0,
                        help="0 = same as the validation pool size (standard bootstrap)")
    parser.add_argument("--include-formula", action="store_true",
                        help="Also enter optimization_harness.formula_weights() (derived "
                             "from the train slice) as a candidate in the Elo tournament.")
    parser.add_argument("--elo-search", type=int, default=0, metavar="N",
                        help="Also enter N candidates that independently sample every leg in "
                             "the panel's full universe from [--elo-search-min, "
                             "--elo-search-max] (not a perturbation around champion -- the "
                             "whole declared range for every leg). Required to be explicit "
                             "(no default count), matching --auto-search's discipline: state "
                             "how many up front. This is what turns the leaderboard from a "
                             "handful of named candidates into an actual ranked sweep.")
    parser.add_argument("--elo-search-seed", type=int, default=0)
    parser.add_argument("--elo-search-min", type=float, default=0.0)
    parser.add_argument("--elo-search-max", type=float, default=0.4,
                        help="Per-leg cap so a single leg can't be handed the whole budget "
                             "by construction -- 0.4 leaves room for at least 3 legs")
    parser.add_argument("--elo-out", default=DEFAULT_ELO_OUT)
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

    if args.elo_rounds:
        run_elo_stage(args)
    else:
        print("[elo] skipped (pass --elo-rounds N to run)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
