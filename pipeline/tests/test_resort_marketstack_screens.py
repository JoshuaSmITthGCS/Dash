import resort_marketstack_screens as module


def series(closes):
    return {"dates": [f"2026-01-{i + 1:02d}" for i in range(len(closes))], "closes": closes}


def test_build_rows_skips_tickers_below_the_movers_minimum(monkeypatch):
    monkeypatch.setattr(module, "daily_closes", lambda: {
        "ONE": series([100.0]),
        "TWO": series([100.0, 101.0]),
    })
    rows = module.build_rows()
    assert [row["ticker"] for row in rows] == ["TWO"]
    assert rows[0]["return_1d"] == 1.0


def test_rank_movers_orders_by_absolute_one_day_move():
    rows = [
        {"ticker": "UP", "return_1d": 2.0},
        {"ticker": "DOWN", "return_1d": -8.0},
        {"ticker": "FLAT", "return_1d": 0.1},
    ]
    assert [row["ticker"] for row in module.rank_movers(rows, limit=2)] == ["DOWN", "UP"]


def test_rank_movers_skips_rows_without_a_one_day_return():
    rows = [{"ticker": "NEW", "return_1d": None}, {"ticker": "OK", "return_1d": 1.0}]
    assert [row["ticker"] for row in module.rank_movers(rows)] == ["OK"]


def test_rank_reversal_requires_a_pullback_that_turned_up():
    rows = [
        {"ticker": "BOUNCE", "return_5d": 3.0, "return_20d": -6.0},
        {"ticker": "STILL_FALLING", "return_5d": -1.0, "return_20d": -6.0},
        {"ticker": "STILL_RISING", "return_5d": 3.0, "return_20d": 6.0},
    ]
    assert [row["ticker"] for row in module.rank_reversal(rows)] == ["BOUNCE"]


def test_rank_reversal_ranks_the_sharpest_reversal_first():
    rows = [
        {"ticker": "MILD", "return_5d": 1.0, "return_20d": -2.0},
        {"ticker": "SHARP", "return_5d": 6.0, "return_20d": -10.0},
    ]
    assert [row["ticker"] for row in module.rank_reversal(rows)] == ["SHARP", "MILD"]


def test_run_reports_accumulating_before_the_reversal_minimum_is_reached(monkeypatch):
    monkeypatch.setattr(module, "daily_closes", lambda: {
        "AAA": series([100.0 + index for index in range(10)]),
    })
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["movers"]["status"] == "success"
    assert result["movers"]["results"]
    assert result["reversal"]["status"] == "accumulating"
    assert result["reversal"]["results"] == []
    assert result["reversal"]["reason_code"] == "MARKETSTACK_HISTORY_ACCUMULATING"
    assert saved["screens/marketstack-movers.json"] == result["movers"]
    assert saved["screens/marketstack-reversal.json"] == result["reversal"]


def test_run_scores_reversal_once_enough_sessions_exist(monkeypatch):
    # 20 flat days, then a pullback, then a bounce - enough sessions for both screens.
    closes = [100.0] * 40 + [100.0 - index for index in range(1, 21)] + [80.0, 81.0, 83.0, 86.0, 90.0]
    monkeypatch.setattr(module, "daily_closes", lambda: {"AAA": series(closes)})
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)

    result = module.run()

    assert result["reversal"]["status"] == "success"
    assert result["reversal"]["sessions_collected"] == len(closes)
