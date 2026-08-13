"""Raw-versus-banded comparison: the logic that decides which remedy a weak metric needs.

The whole point of Phase 5b is to separate "this metric does not rank stocks" from "these
cutoffs do not rank stocks", because they look identical from outside and lead opposite
places. Both of the pieces that make that separation possible fail quietly rather than loudly:
a direction inferred with the wrong sign inverts an information coefficient, and a threshold
set too loosely calls a two-tailed metric monotone and manufactures a signal out of a sign
choice.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "research"))

from bands import MATERIAL_GAP, infer_direction, verdict  # noqa: E402


def series(count=40):
    return {f"t{index}": float(index) for index in range(count)}


# ------------------------------------------------------------------ direction inference

def test_a_higher_is_better_metric_reads_as_positive():
    """Return on invested capital: the band score rises with the value."""
    raw = series()
    scored = {ticker: value * 2 for ticker, value in raw.items()}
    assert infer_direction(raw, scored) == 1


def test_a_lower_is_better_metric_reads_as_negative():
    """EV/EBITDA: the band score falls as the multiple rises."""
    raw = series()
    scored = {ticker: 100.0 - value for ticker, value in raw.items()}
    assert infer_direction(raw, scored) == -1


def test_a_two_tailed_metric_has_no_direction_to_infer():
    """Asset growth penalises both aggressive expansion and shrinkage.

    Forcing a sign on it would produce an information coefficient that is an artifact of the
    choice rather than a property of the metric.
    """
    raw = series()
    scored = {ticker: -abs(value - 20.0) for ticker, value in raw.items()}
    assert infer_direction(raw, scored) is None


def test_direction_survives_the_coarseness_of_a_real_band():
    """Band scores take a handful of distinct values. Direction must still be readable."""
    raw = series()
    scored = {ticker: float(int(value // 10) * 25) for ticker, value in raw.items()}
    assert infer_direction(raw, scored) == 1


def test_a_cross_section_too_small_to_trust_yields_no_direction():
    raw = {f"t{index}": float(index) for index in range(10)}
    scored = {ticker: value for ticker, value in raw.items()}
    assert infer_direction(raw, scored) is None


def test_direction_is_read_from_the_model_not_declared_here():
    """Inverting the bands inverts the inferred direction, with no table to update.

    A hardcoded direction map would drift out of step with settings.json the first time a
    cutoff was edited, and would silently flip the sign of that metric's result.
    """
    raw = series()
    rising = {ticker: value for ticker, value in raw.items()}
    falling = {ticker: -value for ticker, value in raw.items()}
    assert infer_direction(raw, rising) == 1
    assert infer_direction(raw, falling) == -1


# ------------------------------------------------------------------------------ verdicts

def test_raw_clearly_ahead_of_scored_blames_the_bands():
    assert verdict(0.030, 0.005) == "bands_cost_information"


def test_scored_clearly_ahead_of_raw_credits_the_bands():
    """Cutoffs can add information by capping outliers a rank correlation would chase."""
    assert verdict(0.005, 0.030) == "bands_add_information"


def test_a_difference_too_small_to_act_on_is_not_a_finding():
    assert verdict(0.020, 0.020 + MATERIAL_GAP / 2) == "bands_faithful"
    assert verdict(0.020, 0.020 - MATERIAL_GAP / 2) == "bands_faithful"


def test_a_missing_side_is_not_comparable_rather_than_zero():
    assert verdict(None, 0.01) == "not_comparable"
    assert verdict(0.01, None) == "not_comparable"
    assert verdict(None, None) == "not_comparable"
