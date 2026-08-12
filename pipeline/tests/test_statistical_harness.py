"""Deflated Sharpe, PBO, triple-barrier labelling, overlap weights and purged CV.

These are prerequisites in this repository, not extras: no variant comparison ships without a
deflated Sharpe and a PBO estimate beside it, and at a 2-to-10-session horizon every forward
window overlaps its neighbours, so an evaluation without purging and overlap weighting is
optimistic by an amount nobody can bound afterwards.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation import hypothesis_log
from validation.deflated_sharpe import (HLZ_T_HURDLE, clears_hlz_hurdle,
                                        deflated_sharpe_ratio, expected_maximum_sharpe,
                                        probability_of_backtest_overfitting, sharpe_ratio,
                                        sharpe_variance_across_trials)
from validation.labeling import (average_true_range, effective_sample_size, label_summary,
                                 overlap_weights, purged_embargoed_splits,
                                 triple_barrier_label)


# ---------------------------------------------------------------------------
# Deflated Sharpe ratio
# ---------------------------------------------------------------------------

def test_the_bar_rises_with_every_variant_tried():
    """The whole point of the deflation: more searching means a higher hurdle."""
    variance = 0.04

    assert expected_maximum_sharpe(variance, 2) < expected_maximum_sharpe(variance, 10)
    assert expected_maximum_sharpe(variance, 10) < expected_maximum_sharpe(variance, 100)


def test_the_same_returns_deflate_further_at_a_higher_trial_count():
    random.seed(11)
    returns = [random.gauss(0.012, 0.03) for _ in range(60)]

    few = deflated_sharpe_ratio(returns, trials=3, trial_variance=0.05)
    many = deflated_sharpe_ratio(returns, trials=200, trial_variance=0.05)

    assert few["observed_sharpe"] == many["observed_sharpe"]
    assert many["benchmark_sharpe"] > few["benchmark_sharpe"]
    assert many["deflated_sharpe"] < few["deflated_sharpe"]


def test_a_strong_record_still_clears_the_deflation():
    random.seed(3)
    returns = [random.gauss(0.05, 0.03) for _ in range(80)]

    result = deflated_sharpe_ratio(returns, trials=40, trial_variance=0.05)

    assert result["status"] == "ok"
    assert result["deflated_sharpe"] > .95


def test_a_noise_record_does_not():
    random.seed(7)
    returns = [random.gauss(0.0, 0.03) for _ in range(80)]

    result = deflated_sharpe_ratio(returns, trials=40, trial_variance=0.05)

    assert result["deflated_sharpe"] < .95


def test_an_assumed_trial_variance_is_labelled_as_optimistic():
    """A DSR computed without the trial return matrix understates the bar and must say so."""
    random.seed(5)
    returns = [random.gauss(0.01, 0.03) for _ in range(40)]

    result = deflated_sharpe_ratio(returns, trials=40)

    assert result["trial_variance_source"] == "assumed_single_trial_sampling_variance_optimistic"


def test_the_non_normality_correction_is_applied():
    """A skewed series makes the Sharpe estimate noisier, and ignoring that inflates the DSR."""
    random.seed(13)
    symmetric = [random.gauss(0.02, 0.03) for _ in range(80)]

    result = deflated_sharpe_ratio(symmetric, trials=10, trial_variance=0.05)

    assert "skew" in result and "kurtosis" in result
    # Reconstruct the statistic from the reported inputs, so the correction is not just named.
    observed, skew, kurtosis = result["observed_sharpe"], result["skew"], result["kurtosis"]
    denominator = math.sqrt(1 - skew * observed + (kurtosis - 1) / 4 * observed ** 2)
    expected = (observed - result["benchmark_sharpe"]) * math.sqrt(79) / denominator
    assert result["t_statistic"] == pytest.approx(expected)


def test_too_few_observations_reports_rather_than_guesses():
    assert deflated_sharpe_ratio([0.01, 0.02], trials=5)["deflated_sharpe"] is None


def test_the_trial_variance_counts_the_abandoned_variants_too():
    """Dropping the losers from the trial count undeflates the statistic again."""
    random.seed(17)
    trials = {f"v{index}": [random.gauss(index / 500, 0.03) for _ in range(40)]
              for index in range(6)}

    all_six = sharpe_variance_across_trials(trials)
    winners_only = sharpe_variance_across_trials(
        {name: series for name, series in list(trials.items())[-2:]})

    assert all_six is not None and winners_only is not None
    assert all_six != winners_only


# ---------------------------------------------------------------------------
# Probability of backtest overfitting
# ---------------------------------------------------------------------------

def test_pbo_is_near_a_coin_flip_when_every_variant_is_noise():
    random.seed(23)
    trials = {f"v{index}": [random.gauss(0.0, 0.03) for _ in range(96)] for index in range(8)}

    result = probability_of_backtest_overfitting(trials, blocks=8)

    assert result["status"] == "ok"
    assert result["splits"] == 70          # C(8,4)
    assert 0.2 < result["pbo"] < 0.8


def test_pbo_is_low_when_one_variant_is_genuinely_better_throughout():
    random.seed(29)
    trials = {f"v{index}": [random.gauss(0.0, 0.03) for _ in range(96)] for index in range(7)}
    trials["winner"] = [random.gauss(0.05, 0.02) for _ in range(96)]

    result = probability_of_backtest_overfitting(trials, blocks=8)

    assert result["pbo"] < 0.2


def test_pbo_needs_enough_variants_and_enough_periods():
    assert probability_of_backtest_overfitting({"only": [0.1] * 40})["pbo"] is None
    assert probability_of_backtest_overfitting({"a": [0.1] * 4, "b": [0.2] * 4})["pbo"] is None


# ---------------------------------------------------------------------------
# The Harvey-Liu-Zhu hurdle
# ---------------------------------------------------------------------------

def test_the_hurdle_is_three_not_two():
    """Harvey, Liu & Zhu (Review of Financial Studies 29(1), 2016). The convention is not used."""
    assert HLZ_T_HURDLE == 3.0
    assert clears_hlz_hurdle(2.5)["clears"] is False
    assert clears_hlz_hurdle(3.4)["clears"] is True
    assert clears_hlz_hurdle(None)["clears"] is False
    assert "Sullivan, Timmermann & White" in clears_hlz_hurdle(1.0)["note"]


# ---------------------------------------------------------------------------
# Triple-barrier labelling
# ---------------------------------------------------------------------------

def test_the_upper_barrier_is_taken_when_it_is_touched_first():
    closes = [100, 101, 103, 106, 100, 95, 90, 88, 87, 86, 85]

    label = triple_barrier_label(closes, 0, atr=2.0, vertical_sessions=10)

    assert label["label"] == 1
    assert label["barrier"] == "upper_atr_barrier"
    assert label["exit_index"] == 3          # first close at or above 104
    assert label["sessions_held"] == 3


def test_the_lower_barrier_is_taken_when_it_is_touched_first():
    closes = [100, 99, 95, 94, 110, 120, 130, 140, 150, 160, 170]

    label = triple_barrier_label(closes, 0, atr=2.0, vertical_sessions=10)

    assert label["label"] == -1
    assert label["barrier"] == "lower_atr_barrier"
    assert label["exit_index"] == 2          # first close at or below 96


def test_the_vertical_barrier_ends_a_path_that_touches_neither():
    closes = [100] * 11

    label = triple_barrier_label(closes, 0, atr=5.0, vertical_sessions=10)

    assert label["label"] == 0
    assert label["barrier"] == "vertical_barrier"
    assert label["sessions_held"] == 10


def test_barriers_scale_with_the_names_own_atr():
    """A 4% move is a large one for a quiet name and noise for a loud one."""
    closes = [100, 102, 104, 104, 104, 104, 104, 104, 104, 104, 104]

    quiet = triple_barrier_label(closes, 0, atr=1.0, vertical_sessions=10)
    loud = triple_barrier_label(closes, 0, atr=10.0, vertical_sessions=10)

    assert quiet["label"] == 1
    assert loud["label"] == 0


def test_a_path_that_has_not_finished_is_unknown_rather_than_zero():
    """Filling the most recent rows with vertical-barrier zeros is a forward-looking error."""
    assert triple_barrier_label([100, 101, 102], 0, atr=5.0, vertical_sessions=10) is None


def test_average_true_range_counts_a_gap_as_movement():
    highs = [10, 12, 20]
    lows = [9, 11, 18]
    closes = [10, 11, 19]

    atr = average_true_range(highs, lows, closes, window=14)

    # Session 2: max(12-11, |12-10|, |11-10|) = 2.
    # Session 3 gapped from an 11 close to an 18 low, so its true range is 9, not the 2 that
    # the high-minus-low range alone would report.
    assert atr == pytest.approx((2 + 9) / 2)


# ---------------------------------------------------------------------------
# Overlap weighting
# ---------------------------------------------------------------------------

def labels_at(windows):
    return [{"window": window, "label": 1, "return_pct": 1.0,
             "entry_index": window[0], "exit_index": window[1],
             "sessions_held": window[1] - window[0]} for window in windows]


def test_non_overlapping_labels_each_count_as_one_observation():
    labels = labels_at([(0, 5), (6, 11), (12, 17)])

    assert overlap_weights(labels) == [1.0, 1.0, 1.0]
    assert effective_sample_size(labels) == 3.0


def test_fully_overlapping_labels_are_worth_one_observation_between_them():
    labels = labels_at([(0, 10), (0, 10), (0, 10), (0, 10)])

    assert overlap_weights(labels) == [.25, .25, .25, .25]
    assert effective_sample_size(labels) == 1.0


def test_the_overlap_inflation_factor_is_reported():
    """Counting raw labels at a 10-session horizon overstates the sample, and by how much."""
    labels = labels_at([(index, index + 10) for index in range(20)])

    summary = label_summary(labels)

    assert summary["labels"] == 20
    assert summary["effective_sample_size"] < 20
    assert summary["overlap_inflation"] > 1


# ---------------------------------------------------------------------------
# Purged, embargoed cross-validation
# ---------------------------------------------------------------------------

def test_training_labels_overlapping_the_test_window_are_purged():
    labels = labels_at([(index * 2, index * 2 + 10) for index in range(50)])

    splits = purged_embargoed_splits(labels, folds=5, embargo_share=0)

    assert len(splits) == 5
    for split in splits:
        test_start = min(labels[index]["window"][0] for index in split["test"])
        test_end = max(labels[index]["window"][1] for index in split["test"])
        for index in split["train"]:
            start, end = labels[index]["window"]
            assert end < test_start or start > test_end
        assert split["purged_count"] > 0


def test_the_embargo_removes_a_band_after_the_test_set():
    """Features are serially correlated even where label windows do not literally touch."""
    labels = labels_at([(index * 20, index * 20 + 5) for index in range(50)])

    without = purged_embargoed_splits(labels, folds=5, embargo_share=0)
    with_embargo = purged_embargoed_splits(labels, folds=5, embargo_share=.06)

    assert all(split["embargoed_count"] == 0 for split in without)
    assert sum(split["embargoed_count"] for split in with_embargo) > 0
    assert (sum(split["train_size"] for split in with_embargo)
            < sum(split["train_size"] for split in without))


def test_train_and_test_never_share_an_index():
    labels = labels_at([(index * 3, index * 3 + 8) for index in range(40)])

    for split in purged_embargoed_splits(labels, folds=4, embargo_share=.02):
        assert not set(split["train"]) & set(split["test"])


# ---------------------------------------------------------------------------
# The hypothesis log
# ---------------------------------------------------------------------------

def test_the_trial_count_is_read_from_the_log_rather_than_recalled(tmp_path):
    path = str(tmp_path / "hypotheses.jsonl")

    hypothesis_log.register(hypothesis_id="X-1", family="demo", description="first",
                            registered_at="2026-08-12T00:00:00+00:00", path=path)
    hypothesis_log.register(hypothesis_id="X-2", family="demo", description="second",
                            registered_at="2026-08-12T00:00:00+00:00", path=path)

    assert hypothesis_log.trial_count(path=path) == 2
    assert hypothesis_log.trial_count(family="demo", path=path) == 2
    assert hypothesis_log.trial_count(family="other", path=path) == 0


def test_registering_the_same_hypothesis_twice_does_not_inflate_the_count(tmp_path):
    path = str(tmp_path / "hypotheses.jsonl")
    for _ in range(3):
        hypothesis_log.register(hypothesis_id="X-1", family="demo", description="first",
                                registered_at="2026-08-12T00:00:00+00:00", path=path)

    assert hypothesis_log.trial_count(path=path) == 1
    assert hypothesis_log.audit(path=path)["duplicate_registrations"] == []


def test_a_hypothesis_without_a_timestamp_cannot_be_registered(tmp_path):
    """Registering after the results exist is the failure this log prevents."""
    path = str(tmp_path / "hypotheses.jsonl")

    with pytest.raises(ValueError, match="registered_at"):
        hypothesis_log.register(hypothesis_id="X-1", family="demo", description="d",
                                registered_at="", path=path)


def test_the_eight_registered_variants_are_on_disk():
    """The 2026-08-12 registration: three reversal variants and five overlay cells."""
    summary = hypothesis_log.audit()

    assert summary["by_family"]["swing_reversal"] == 3
    assert summary["by_family"]["entry_timing_overlay"] == 5
    assert summary["duplicate_registrations"] == []
