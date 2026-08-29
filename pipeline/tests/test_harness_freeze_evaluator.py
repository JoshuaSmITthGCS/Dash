import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation.harness_freeze_evaluator import (
    evaluate_against_promotion_criteria, evaluate_entry_timing_overlay_variant, _load_freeze)


def strong_series(seed, *, mean=0.06, spread=0.01, n=24):
    generator = random.Random(seed)
    return [mean + generator.gauss(0, spread) for _ in range(n)]


def weak_series(seed, *, n=24):
    generator = random.Random(seed)
    return [generator.gauss(0, 0.02) for _ in range(n)]


def test_the_real_committed_freeze_file_loads_and_has_the_expected_shape():
    freeze = _load_freeze()
    assert freeze["trial_count_for_deflated_statistics"]["dsr_trial_count_used"] == 50
    assert freeze["promotion_criteria_champion_or_challenger"]["minimum_periods"] == 24


def test_every_additional_model_registration_carries_the_required_fields():
    """No automated check previously caught a malformed additional_models entry -- this
    would have let a registration like pre-breakout-v0.1.0's silently drift from swing-
    v1.1.0's own shape. Structural only: it does not evaluate the content, just that a
    reader (or a future evaluator) can rely on every entry exposing the same fields."""
    required = {"model", "registered_at", "definition", "why_registered", "weights_are",
               "clock_start", "expected_completion_at_monthly_frequency", "measured_against",
               "open_questions_the_clock_must_answer", "changes_that_reset_this_clock"}
    freeze = _load_freeze()
    models = freeze["additional_models"]
    assert len(models) >= 2  # swing-v1.1.0 and pre-breakout-v0.1.0, at minimum
    for entry in models:
        missing = required - set(entry)
        assert not missing, f"{entry.get('model')} is missing {missing}"
        assert entry["open_questions_the_clock_must_answer"]
        assert entry["changes_that_reset_this_clock"]
    ids = [entry["model"] for entry in models]
    assert len(ids) == len(set(ids)), "duplicate model id in additional_models"
    assert "pre-breakout-v0.1.0" in ids


def test_fewer_than_the_minimum_periods_is_reported_as_insufficient_not_guessed_at():
    result = evaluate_against_promotion_criteria(
        ic_series=strong_series(1, n=10), returns=strong_series(2, n=10),
        net_of_cost_quantile_spread=0.01)
    assert result["verdict"] == "insufficient_periods"
    assert result["periods"] == 10


def test_a_strong_clean_record_on_every_gate_promotes():
    result = evaluate_against_promotion_criteria(
        ic_series=strong_series(3), returns=strong_series(4),
        other_variant_returns={"other": weak_series(5)},
        net_of_cost_quantile_spread=0.015)
    assert result["verdict"] == "promote"
    assert all(gate["pass"] for gate in result["gates"].values())


def test_a_negative_icir_abandons_regardless_of_the_other_gates():
    negative_ic = [-value for value in strong_series(3)]
    result = evaluate_against_promotion_criteria(
        ic_series=negative_ic, returns=strong_series(4),
        other_variant_returns={"other": weak_series(5)},
        net_of_cost_quantile_spread=0.015)
    assert result["verdict"] == "abandon"


def test_a_non_positive_net_of_cost_spread_abandons_even_with_a_strong_ic():
    result = evaluate_against_promotion_criteria(
        ic_series=strong_series(3), returns=strong_series(4),
        other_variant_returns={"other": weak_series(5)},
        net_of_cost_quantile_spread=-0.002)
    assert result["verdict"] == "abandon"


def test_an_icir_between_zero_and_the_gray_zone_ceiling_extends_once_rather_than_abandoning():
    # mean/deviation ratio of ~0.05 puts ICIR at ~0.05 * sqrt(12) ~= 0.17, inside (0, 0.2).
    thin_ic = [0.01 + 0.2 * ((index % 2) * 2 - 1) for index in range(24)]
    result = evaluate_against_promotion_criteria(
        ic_series=thin_ic, returns=strong_series(4),
        other_variant_returns={"other": weak_series(5)},
        net_of_cost_quantile_spread=0.01)
    assert result["verdict"] == "gray_zone_extend_once"


def test_missing_other_variant_returns_leaves_pbo_unjudged_and_holds_rather_than_promotes():
    result = evaluate_against_promotion_criteria(
        ic_series=strong_series(3), returns=strong_series(4),
        other_variant_returns=None, net_of_cost_quantile_spread=0.015)
    assert result["verdict"] == "hold"
    assert "pbo_at_most_0_50" in result["unjudged_gates"]


def test_entry_timing_overlay_variant_that_clears_the_registered_margin_is_adopted():
    result = evaluate_entry_timing_overlay_variant(
        variant_returns=strong_series(10, mean=0.10), baseline_returns=weak_series(11))
    assert result["verdict"] == "adopt"
    assert result["clears_improvement_margin"]
    assert result["clears_pbo"]


def test_entry_timing_overlay_variant_indistinguishable_from_baseline_stays_off():
    same_seed_variant = strong_series(20, mean=0.02, spread=0.02)
    same_seed_baseline = strong_series(21, mean=0.02, spread=0.02)
    result = evaluate_entry_timing_overlay_variant(
        variant_returns=same_seed_variant, baseline_returns=same_seed_baseline)
    assert result["verdict"] == "stay_off"
    assert result["note"] is not None
