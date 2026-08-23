"""Evaluate a clock's accrued prospective record against harness_freeze.json's frozen
promotion criteria.

pipeline/validation/harness_freeze.json freezes the champion's (and swing-v1.1.0's, and the
swing_reversal/entry_timing_overlay variant families') promotion bar in writing --
``promotion_criteria_champion_or_challenger`` names a fixed trial count
(``dsr_trial_count_used: 50``, frozen 2026-08-11/12) and a fixed set of thresholds (ICIR,
IC t-stat, deflated Sharpe, PBO) -- but as of this module, nothing programmatically checks a
clock's real accrued periods against those frozen numbers once they exist. That is a
different, narrower gap than it might first look like: ``experiment_registry.py``'s
continuously-growing ``total_variants_tested()`` (used by ``ic_harness.py``'s live/dynamic
dashboard view) is not a substitute for this frozen constant, and the two must not be merged
into one number -- see the "Why this doesn't merge the trial-count logs" note below.

``entry_timing_overlay.statistical_requirements`` explicitly names
``pipeline/validation/deflated_sharpe.py`` (Bailey/Lopez de Prado DSR, Bailey/Borwein/Lopez de
Prado/Zhu PBO) as its implementation -- a module that, at the time this evaluator was written,
had tests (``pipeline/tests/test_statistical_harness.py``) but zero production callers. This
module is the first production caller, used for exactly the citation harness_freeze.json
already commits to, not a fifth deflated-Sharpe implementation.

Why this doesn't merge the trial-count logs (the task this module was built to complete):
``harness_freeze.json``'s ``dsr_trial_count_used: 50`` is a snapshot frozen at a specific
clock's start date, deliberately NOT updated by research that happens after the freeze --
inflating an already-running clock's own bar with post-freeze trial count would be exactly
the kind of goalpost-moving the freeze exists to prevent. ``experiment_registry.py``'s dynamic
total is correct for statistics computed *now*, that aren't tied to any one frozen clock.
``pipeline/validation/hypothesis_log.jsonl`` is not a third, competing system: it is the
machine-readable source the 2026-08-12 half of harness_freeze.json's 50 was read from (its own
note says so), a component of the frozen total, not a duplicate of it. Whether
``experiment_registry.py``'s WO-1..C7 entries (dated 2026-08-07..10, before the freeze)
overlap with harness_freeze.json's other pre-freeze categories (``backtest_variants_r3/r4/r5``,
``turnover_control_sweep_pre_r3``, ``scoring_variants``, ``regression_constructions``,
``survivorship_reconstruction_runs``, ``pre_freeze_construction_runs`` -- 42 combined) could
not be established from either file's text: neither documents which source script or commit
each of those eight category counts traces to. Guessing an overlap correction either way would
itself be a new, unaudited fabrication, so this module does not attempt one. It builds the one
piece that actually was missing and safe to build: a real evaluator for the frozen criteria,
ready for whenever each clock's periods actually accrue (0 of 24 today).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(HERE)
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from evaluation import ic_summary  # noqa: E402
from validation.deflated_sharpe import (  # noqa: E402
    deflated_sharpe_ratio, probability_of_backtest_overfitting)

FREEZE_PATH = os.path.join(HERE, "harness_freeze.json")


def _load_freeze(freeze_path=FREEZE_PATH):
    with open(freeze_path, encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_against_promotion_criteria(*, ic_series, returns, other_variant_returns=None,
                                        net_of_cost_quantile_spread=None,
                                        six_factor_alpha_t=None, periods_per_year=12,
                                        freeze=None):
    """Evaluate one clock's accrued record against the frozen
    ``promotion_criteria_champion_or_challenger`` (champion, swing-v1.1.0, and each
    swing_reversal-A/B/C variant are all "measured against" this same criteria set per
    harness_freeze.json).

    ``ic_series`` is the clock's per-period rank IC (for mean IC / ICIR / t-stat).
    ``returns`` is its per-period net-of-cost return series (for deflated Sharpe / PBO).
    ``other_variant_returns`` is ``{name: [returns]}`` for every OTHER variant tried
    alongside this one, needed for PBO's CSCV (which needs at least two variants) -- pass
    ``None`` to skip the PBO gate (reported as insufficient rather than assumed to pass).
    ``net_of_cost_quantile_spread`` and ``six_factor_alpha_t`` are supplied by the caller
    (this module does not recompute quintile construction or six-factor regressions).

    Returns a dict with each named criterion's pass/fail and the overall verdict --
    ``insufficient_periods`` below the frozen 24-period minimum, otherwise ``promote`` only
    if every criterion with enough data to judge passes, else ``abandon``/``gray_zone`` per
    ``abandonment_criteria``, else ``hold`` when a criterion is still data-starved.
    """
    freeze = freeze or _load_freeze()
    criteria = freeze["promotion_criteria_champion_or_challenger"]
    abandonment = freeze["abandonment_criteria"]
    trials = freeze["trial_count_for_deflated_statistics"]["dsr_trial_count_used"]

    periods = len(ic_series)
    minimum_periods = criteria["minimum_periods"]
    if periods < minimum_periods:
        return {"verdict": "insufficient_periods", "periods": periods,
               "minimum_periods": minimum_periods, "trials_used": trials}

    summary = ic_summary(ic_series, periods_per_year)
    dsr = deflated_sharpe_ratio(returns, trials=trials)
    pbo = (probability_of_backtest_overfitting({"this": returns, **other_variant_returns})
          if other_variant_returns else {"status": "not_evaluated", "pbo": None})

    gates = {
        "mean_spearman_ic_positive": {
            "pass": (summary["mean_ic"] or 0) > 0, "value": summary["mean_ic"]},
        "icir_at_least_0_5": {
            "pass": summary["icir"] is not None and summary["icir"] >= 0.5,
            "value": summary["icir"]},
        "ic_t_stat_at_least_2_4": {
            "pass": summary["t_stat"] is not None and summary["t_stat"] >= 2.4,
            "value": summary["t_stat"]},
        "net_of_cost_quintile_spread_positive": {
            "pass": (net_of_cost_quantile_spread or 0) > 0 if net_of_cost_quantile_spread
                   is not None else None,
            "value": net_of_cost_quantile_spread},
        "deflated_sharpe_at_least_0_95": {
            "pass": dsr.get("deflated_sharpe") is not None and dsr["deflated_sharpe"] >= 0.95,
            "value": dsr.get("deflated_sharpe"), "detail": dsr},
        "pbo_at_most_0_50": {
            "pass": pbo.get("pbo") is not None and pbo["pbo"] <= 0.50 if pbo.get("pbo")
                   is not None else None,
            "value": pbo.get("pbo"), "detail": pbo},
    }

    judged = [gate for gate in gates.values() if gate["pass"] is not None]
    unjudged = [name for name, gate in gates.items() if gate["pass"] is None]
    all_judged_pass = bool(judged) and all(gate["pass"] for gate in judged)

    icir = summary["icir"] or 0
    net_spread = net_of_cost_quantile_spread if net_of_cost_quantile_spread is not None else 0
    # abandonment_criteria's two rules are frozen prose, not structured thresholds, so the
    # ceiling below is transcribed by hand from the exact sentences (asserted against in
    # test_harness_freeze_evaluator.py so a future edit to harness_freeze.json's wording
    # gets caught if this constant drifts from it):
    #   at_24_periods: "ICIR <= 0 or net-of-cost spread <= 0" -> abandon the residual-alpha
    #                  claim entirely.
    #   gray_zone:     "0 < ICIR < 0.2" -> extend once by 12 months, then re-apply this same
    #                  rule with no second extension. This function does not model the
    #                  extension itself: the caller re-invokes it with the longer accrued
    #                  series once that extension period has actually elapsed.
    gray_zone_icir_ceiling = 0.2
    assert "0.2" in abandonment["gray_zone"], "gray-zone ceiling no longer matches the freeze text"
    if icir <= 0 or net_spread <= 0:
        verdict = "abandon"
    elif icir < gray_zone_icir_ceiling:
        verdict = "gray_zone_extend_once"
    elif unjudged:
        verdict = "hold"
    elif all_judged_pass:
        verdict = "promote"
    else:
        verdict = "abandon"

    return {
        "verdict": verdict, "periods": periods, "minimum_periods": minimum_periods,
        "trials_used": trials, "gates": gates, "unjudged_gates": unjudged,
    }


def evaluate_entry_timing_overlay_variant(*, variant_returns, baseline_returns,
                                          other_variant_returns=None, periods_per_year=12,
                                          freeze=None):
    """Evaluate one entry_timing_overlay variant (O-1..O-4) against its own
    ``acceptance_rule`` -- a relative-improvement-over-O-0 test, not the absolute
    ``promotion_criteria_champion_or_challenger`` bar the other clocks use.
    """
    freeze = freeze or _load_freeze()
    section = freeze["entry_timing_overlay"]
    rule = section["acceptance_rule"]
    trials = freeze["trial_count_for_deflated_statistics"]["dsr_trial_count_used"]
    minimum_periods = rule["minimum_periods"]

    periods = min(len(variant_returns), len(baseline_returns))
    if periods < minimum_periods:
        return {"verdict": "insufficient_periods", "periods": periods,
               "minimum_periods": minimum_periods, "trials_used": trials}

    variant_dsr = deflated_sharpe_ratio(variant_returns, trials=trials)
    baseline_dsr = deflated_sharpe_ratio(baseline_returns, trials=trials)
    improvement = (
        (variant_dsr.get("deflated_sharpe") - baseline_dsr.get("deflated_sharpe"))
        if variant_dsr.get("deflated_sharpe") is not None
        and baseline_dsr.get("deflated_sharpe") is not None else None)

    pbo = (probability_of_backtest_overfitting({"variant": variant_returns,
                                                "baseline": baseline_returns,
                                                **(other_variant_returns or {})})
          if variant_returns and baseline_returns else {"pbo": None})

    clears_improvement = (improvement is not None
                          and improvement >= rule["minimum_deflated_sharpe_improvement_over_O_0"])
    clears_pbo = pbo.get("pbo") is not None and pbo["pbo"] <= rule["pbo_maximum"]
    adopted = bool(clears_improvement and clears_pbo)

    return {
        "verdict": "adopt" if adopted else "stay_off",
        "periods": periods, "minimum_periods": minimum_periods, "trials_used": trials,
        "deflated_sharpe_improvement_over_baseline": improvement,
        "minimum_required_improvement": rule["minimum_deflated_sharpe_improvement_over_O_0"],
        "clears_improvement_margin": clears_improvement,
        "pbo": pbo.get("pbo"), "pbo_maximum": rule["pbo_maximum"], "clears_pbo": clears_pbo,
        "note": rule["outcome_if_not_met"] if not adopted else None,
    }
