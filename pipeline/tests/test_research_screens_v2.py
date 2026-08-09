from datetime import date, timedelta

from research_screens_v2 import (classify_quality_value, historical_percentile, momentum_factors,
                                 momentum_scores, position_size, robust_value_score,
                                 sleeve_volatility_scale, tactical_score, winsorize, zscores)


def test_winsorize_preserves_length_when_every_value_is_none():
    # A factor column can legitimately be all-None (e.g. zero news coverage across an
    # entire batch) - winsorize() must not collapse to [], which desyncs it from
    # zscores()'s own len(values)-preserving None-fill and crashes the caller's
    # standardized[field][index] lookup with an IndexError.
    assert winsorize([None, None, None]) == [None, None, None]


def test_zscores_preserves_length_when_every_value_is_none():
    assert zscores(winsorize([None, None])) == [None, None]


def test_winsorize_still_clips_extremes_with_some_none_values_present():
    result = winsorize([1, None, 100, 50])
    assert result[1] is None
    assert len(result) == 4


def daily_prices(start=date(2023, 1, 1), sessions=520):
    return [{"date": (start + timedelta(days=index)).isoformat(), "adjusted_close": 100 + index}
            for index in range(sessions)]


def test_momentum_uses_month_ends_and_skips_latest_month():
    factors = momentum_factors(daily_prices(), as_of="2024-06-03")
    assert factors["momentum_12_1"] > 0
    changed_latest = daily_prices()
    changed_latest[-1]["adjusted_close"] = 100000
    assert momentum_factors(changed_latest, as_of="2024-06-03")["momentum_12_1"] == factors["momentum_12_1"]


def test_momentum_eligibility_and_hysteresis():
    rows = [{"ticker": key, "price": 10, "market_cap": 1e9, "median_dollar_volume_60d": 3e6,
             "history_sessions": 300, "factors": {field: score for field in
             ("momentum_12_1", "momentum_12_7", "momentum_6_1", "high_52w_proximity", "industry_relative_momentum")}}
            for key, score in (("A", 1), ("B", 2), ("C", 3))]
    rows[0]["stale_price"] = True
    scored = momentum_scores(rows, current_members={"B": True}, config={"entry_percentile": 90, "exit_percentile": 0})
    assert next(row for row in scored if row["ticker"] == "A")["eligibility"] is False
    assert next(row for row in scored if row["ticker"] == "B")["selected"] is True


def test_tactical_weights_are_separate_and_snapshot_limit_is_visible():
    result = tactical_score({key: 80 for key in ("revision_agreement", "revision_magnitude")}, 75, False)
    assert result["tactical_score"] == 80
    assert result["classification"] == "high-conviction candidate"
    assert "REVISION_BACKTEST_UNAVAILABLE" in result["quality_flags"]


def test_own_history_percentiles_and_revision_gate():
    assert historical_percentile([5, 10, 15, 20], 5) == 75
    score, raw = robust_value_score({"forward_pe": {"history": [5, 10, 15, 20], "current": 5},
                                     "ev_ebitda": {"history": [4, 8, 12, 16], "current": 4}})
    assert score == 75 and raw["forward_pe"] == 75
    label, reasons = classify_quality_value(80, 60, 85, 10, 15, 0)
    assert label == "cheap but deteriorating"
    assert reasons == ["FORWARD_ESTIMATE_DETERIORATION"]


def test_position_risk_and_sleeve_volatility_are_separate():
    assert position_size(100_000, 50, 2, maximum_position=.05) == 100
    assert sleeve_volatility_scale(.24, target=.12) == .5
