import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "validation"))
sys.path.insert(0, os.path.dirname(HERE))

import screen_reweight as sr  # noqa: E402


def _panel(periods=60, names=120, seed=0, signal_leg=0, strength=0.5):
    rng = np.random.default_rng(seed)
    out = []
    for n in range(periods):
        legs = rng.normal(size=(names, 3))
        returns = strength * legs[:, signal_leg] + rng.normal(size=names)
        out.append({"date": f"2020-{n:03d}", "legs": legs, "returns": returns * 0.05})
    return out


def test_study_recovers_planted_signal_and_never_peeks():
    periods = _panel()
    legs = ["a", "b", "c"]
    study = sr.run_study("t", legs, periods, {"a": 0.2, "b": 0.4, "c": 0.4}, periods_per_year=12,
                         warmup=20, trials=60, seed=1)
    rows = {r["config"]: r for r in study["oos_window"]["rows"]}
    assert rows["only_a"]["mean_ic"] > rows["only_b"]["mean_ic"]
    assert rows["ic_weighted_wf"]["periods"] == 40            # only periods >= warmup are scored
    assert rows["current"]["periods"] == 40
    assert study["average_walk_forward_weights"]["ic_weighted"]["a"] > 0.5


def test_pure_noise_does_not_validate_a_searched_winner():
    periods = _panel(strength=0.0, seed=3)
    study = sr.run_study("t", ["a", "b", "c"], periods, {"a": 1, "b": 1, "c": 1},
                         periods_per_year=12, warmup=20, trials=80, seed=2)
    row = next(r for r in study["oos_window"]["rows"] if r["config"] == "random_search_best_wf")
    assert row["deflated_sharpe_prob"] is None or row["deflated_sharpe_prob"] < 0.95


def test_blend_matches_weighted_mean():
    score = sr.blend(np.array([[1.0, 3.0]]), [0.25, 0.75])
    assert abs(score[0] - 2.5) < 1e-9
