import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "validation"))
sys.path.insert(0, os.path.dirname(HERE))

import weight_lab as lab  # noqa: E402


def test_rank_ic_perfect_and_inverse():
    scores = np.arange(50, dtype=float)
    assert abs(lab.rank_ic(scores, scores * 2) - 1) < 1e-9
    assert abs(lab.rank_ic(scores, -scores) + 1) < 1e-9


def test_rank_ic_needs_minimum_names():
    assert lab.rank_ic(np.arange(5.0), np.arange(5.0)) is None


def test_blend_renormalizes_over_resolved_legs():
    matrix = np.array([[80.0, np.nan], [80.0, 40.0]])
    score = lab.blend(matrix, [0.5, 0.5])
    assert score[0] == 80.0          # missing leg renormalized away, not zero-filled
    assert score[1] == 60.0


def test_blend_all_missing_is_nan():
    assert np.isnan(lab.blend(np.array([[np.nan, np.nan]]), [1.0, 1.0])[0])


def test_newey_west_shrinks_t_for_autocorrelated_series():
    base = np.cumsum(np.random.default_rng(0).normal(size=60)) * 0.01 + 0.05  # strongly persistent
    naive = lab.newey_west_t(base, 0)
    adjusted = lab.newey_west_t(base, 10)
    assert abs(adjusted) < abs(naive)


def test_walk_forward_pick_never_sees_the_scored_period():
    seen = []

    def selector(train):
        seen.append(max(train))
        return 0

    series = [{"ic": list(range(30)), "spread": list(range(30)), "excess": list(range(30))}]
    lab.walk_forward_pick(series, 30, selector, warmup=10)
    scored = list(range(10, 30))
    assert all(last < t - lab.EMBARGO + 0 for last, t in zip(seen, scored))


def test_quintile_spread_orders_correctly():
    scores = np.arange(100, dtype=float)
    assert lab.quintile_spread(scores, scores / 100) > 0
    assert lab.quintile_spread(scores, -scores / 100) < 0


def test_dirichlet_candidates_sum_to_one_on_active_legs():
    vectors = lab.dirichlet_candidates(20, 1, active=["valuation", "market_behavior"])
    assert np.allclose(vectors.sum(axis=1), 1)
    assert (vectors[:, lab.LEGS.index("growth")] == 0).all()
