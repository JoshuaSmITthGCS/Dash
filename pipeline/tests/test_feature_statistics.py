"""The statistics Phase 5 rests on, tested where they are easy to get subtly wrong.

Every per-metric verdict in `research/results/PHASE5-FEATURES.md` is a rank correlation, a
t-statistic, or a significance threshold. Each has a failure mode that produces a plausible
number rather than an error: ties mis-ranked so a coarsely-banded metric looks like it sorts,
a constant column returning zero instead of nothing, or a nominal threshold applied across
thirty-two simultaneous tests.
"""

import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))

from rank_statistics import (bonferroni_threshold, ranks, spearman,  # noqa: E402
                             summarise_series)


# ------------------------------------------------------------------------ rank correlation

def test_a_perfectly_ordered_pair_correlates_at_one():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1.0)


def test_correlation_is_of_ranks_not_levels():
    """A monotone but wildly non-linear relationship is still a perfect ranking."""
    assert spearman([1, 2, 3, 4], [1, 10, 1_000, 1_000_000]) == pytest.approx(1.0)


def test_ties_share_an_averaged_rank():
    """Band scores are coarse and tie constantly. Ranking ties by input order would invent
    an ordering the metric does not have, and make a three-valued score look like it sorts."""
    assert ranks([5, 5, 1, 9]) == [2.5, 2.5, 1.0, 4.0]
    assert ranks([1, 1, 1]) == [2.0, 2.0, 2.0]


def test_a_coarse_band_correlates_below_a_fine_one_on_the_same_ordering():
    fine = list(range(20))
    coarse = [0] * 10 + [1] * 10             # the same ordering, flattened into two buckets
    returns = list(range(20))
    assert spearman(coarse, returns) < spearman(fine, returns)


def test_a_column_with_no_variation_is_absent_rather_than_zero():
    """Every company scoring identically is a band configuration that cannot rank anything.
    Recording it as an information coefficient of zero would average it in as evidence of
    no signal, when it is an absence of measurement."""
    assert spearman([7, 7, 7, 7], [1, 2, 3, 4]) is None
    assert spearman([1, 2, 3, 4], [7, 7, 7, 7]) is None


def test_too_few_observations_yield_nothing():
    assert spearman([1, 2], [1, 2]) is None
    assert spearman([1, 2, 3], [1, 2]) is None


# ------------------------------------------------------------------------- the t-statistic

def test_a_consistent_small_edge_beats_a_large_erratic_one():
    """Which is the whole reason the t-statistic is reported rather than the mean alone."""
    steady = summarise_series([0.02] * 40 + [0.01] * 40)
    erratic = summarise_series([0.30, -0.28] * 40)
    assert steady["mean_ic"] < erratic["mean_ic"] + 0.1
    assert steady["t_statistic"] > erratic["t_statistic"]


def test_the_t_statistic_scales_with_the_number_of_observations():
    short = summarise_series([0.05, 0.01, 0.03, 0.02] * 3)
    long = summarise_series([0.05, 0.01, 0.03, 0.02] * 12)
    assert long["t_statistic"] > short["t_statistic"]
    assert long["mean_ic"] == pytest.approx(short["mean_ic"])


def test_none_coefficients_are_dropped_rather_than_counted():
    assert summarise_series([0.02, None, 0.04, None])["periods"] == 2


def test_a_series_too_short_to_summarise_reports_no_statistic():
    assert summarise_series([0.05]) == {"periods": 1}
    assert summarise_series([]) == {"periods": 0}


# --------------------------------------------------------------------- multiple testing

def test_one_test_reproduces_the_ordinary_five_percent_threshold():
    assert bonferroni_threshold(1) == pytest.approx(1.96, abs=0.01)


def test_thirty_two_simultaneous_tests_need_a_much_higher_bar():
    """At a nominal 1.96, testing thirty-two metrics expects more than one false winner."""
    threshold = bonferroni_threshold(32)
    assert threshold > 3.0
    # A metric at t = 2.5 looks significant alone and is not, once the other thirty-one are
    # acknowledged. That gap is the finding this threshold exists to prevent.
    assert 2.5 < threshold


def test_the_threshold_matches_the_normal_tail_it_claims_to_invert():
    for tests in (1, 8, 32):
        tail = 0.5 * math.erfc(bonferroni_threshold(tests) / math.sqrt(2))
        assert tail == pytest.approx(0.05 / tests / 2, rel=0.01)
