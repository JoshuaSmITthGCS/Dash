import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import composite_attribution as ca  # noqa: E402


def snapshot(date, rows):
    return {"date": date, "rows": rows}


# ---------------- periods_from_snapshots ----------------

def test_a_pair_far_enough_apart_yields_one_period_with_leg_scores_and_returns():
    start = snapshot("2026-01-01", [
        {"ticker": "A", "price": 100.0, "m1": 1.0, "m2": 2.0},
        {"ticker": "B", "price": 50.0, "m1": 0.5, "m2": None},
    ])
    end = snapshot("2026-02-01", [
        {"ticker": "A", "price": 110.0},
        {"ticker": "B", "price": 55.0},
    ])
    periods = ca.periods_from_snapshots([start, end], ["m1", "m2"], horizon_days=14)
    assert len(periods) == 1
    period = periods[0]
    assert period["leg_scores"]["A"] == {"m1": 1.0, "m2": 2.0}
    assert period["leg_scores"]["B"] == {"m1": 0.5}  # m2 was None, dropped rather than imputed
    assert period["forward_returns"]["A"] == pytest.approx(0.1)


def test_a_pair_short_of_the_horizon_contributes_no_period():
    start = snapshot("2026-01-01", [{"ticker": "A", "price": 100.0, "m1": 1.0}])
    end = snapshot("2026-01-05", [{"ticker": "A", "price": 105.0}])
    assert ca.periods_from_snapshots([start, end], ["m1"], horizon_days=14) == []


def test_a_ticker_missing_from_the_end_snapshot_is_excluded_not_imputed():
    start = snapshot("2026-01-01", [{"ticker": "A", "price": 100.0, "m1": 1.0}])
    end = snapshot("2026-02-01", [{"ticker": "B", "price": 55.0}])
    assert ca.periods_from_snapshots([start, end], ["m1"], horizon_days=14) == []


# ---------------- build_attribution_report ----------------

def test_below_minimum_periods_hides_every_number_but_keeps_the_shape():
    periods = [{"leg_scores": {t: {"m1": score} for t, score in zip("ABCDE", (1, 2, 3, 4, 5))},
               "forward_returns": {t: ret for t, ret in zip("ABCDE", (0.1, 0.2, 0.0, -0.1, 0.3))}}]
    report = ca.build_attribution_report(periods, {"m1": 1.0}, minimum_periods=24)
    assert report["status"] == "accumulating"
    assert report["composite"]["mean_rank_ic"] is None
    assert report["metrics"]["m1"]["own_rank_ic"] is None
    assert report["metrics"]["m1"]["weight"] == 1.0


def test_a_perfectly_predictive_metric_and_a_useless_one_are_told_apart():
    tickers = "ABCDE"
    # m1 ranks exactly with forward return every period; m2 is constant (pure noise).
    returns = (0.1, 0.2, 0.3, 0.4, 0.5)
    periods = [{
        "leg_scores": {t: {"m1": ret, "m2": 1.0} for t, ret in zip(tickers, returns)},
        "forward_returns": dict(zip(tickers, returns)),
    } for _ in range(24)]

    report = ca.build_attribution_report(periods, {"m1": 0.5, "m2": 0.5}, minimum_periods=24)
    assert report["status"] == "eligible"
    assert report["metrics"]["m1"]["own_rank_ic"] == 1.0
    assert report["metrics"]["m2"]["own_rank_ic"] is None  # a constant leg has no rank IC
    # Dropping the noisy, constant m2 changes nothing about the composite (it's constant
    # across tickers within every period, so it never affects the cross-sectional rank).
    assert report["metrics"]["m2"]["delta_ic"] == 0.0
    assert report["metrics"]["m2"]["hurts_composite"] is False
