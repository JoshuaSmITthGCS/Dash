"""realized_vol_percentile_backtest must reproduce options_common.realized_vol_percentile's
own values exactly (just computed in one efficient pass instead of one call per day) - the
whole backtest is worthless if its fast path silently drifts from the production definition
it's supposed to be testing.
"""
import json
import math

import options_common
from validation import realized_vol_percentile_backtest as module


def _synthetic_closes(seed=7, n=400):
    """Deterministic pseudo-random-looking walk - varied enough that rolling vol actually
    moves around (a perfectly flat or perfectly linear series makes every window's vol
    identical, which would pass a broken implementation just as easily as a correct one).
    """
    closes = [100.0]
    state = seed
    for _ in range(n - 1):
        state = (state * 1103515245 + 12345) % (2 ** 31)
        step = ((state / (2 ** 31)) - 0.5) * 0.06  # daily moves up to +/-3%
        closes.append(max(1.0, closes[-1] * (1 + step)))
    return closes


def test_percentile_series_matches_the_real_function_at_every_index():
    closes = _synthetic_closes()
    vol_series = module._rolling_realized_vol(closes)
    percentile_series = module._percentile_series(vol_series)
    checked_a_real_value = False
    for i in range(len(closes)):
        expected = options_common.realized_vol_percentile(closes[:i + 1])
        assert percentile_series[i] == expected, f"mismatch at index {i}: {percentile_series[i]} != {expected}"
        if expected is not None:
            checked_a_real_value = True
    assert checked_a_real_value  # the synthetic series must be long enough to clear the sample floor


def test_rolling_realized_vol_matches_the_real_20d_function():
    closes = _synthetic_closes(seed=13, n=100)
    vol_series = module._rolling_realized_vol(closes)
    for i in range(len(closes)):
        expected = options_common.realized_volatility_20d(closes[:i + 1])
        actual = vol_series[i]
        if expected is None:
            assert actual is None
        else:
            assert actual is not None
            assert math.isclose(actual, expected, rel_tol=1e-9)


def test_ticker_observations_pairs_percentile_with_a_real_forward_window(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ARCHIVE_DIR", str(tmp_path))
    closes = _synthetic_closes(seed=21, n=400)
    dates = [f"2020-01-{(i % 28) + 1:02d}" if i < 28 else f"2020-{(i // 28) % 12 + 1:02d}-{(i % 28) + 1:02d}"
            for i in range(len(closes))]
    json.dump({"ticker": "FAKE", "rows": {d: [c, 1000] for d, c in zip(dates, closes)}},
             open(tmp_path / "FAKE.json", "w"))

    def fake_load_series(ticker, directory=None):
        rows = json.load(open(tmp_path / f"{ticker}.json"))["rows"]
        ordered = sorted(rows)
        return {"dates": ordered, "closes": [rows[d][0] for d in ordered]}

    monkeypatch.setattr(module, "load_series", fake_load_series)
    observations = module._ticker_observations("FAKE")
    assert observations  # the synthetic series clears every gate (length, sample floor, forward window)
    for date, percentile, vol_change, forward_return in observations:
        assert 0 <= percentile <= 100
        assert isinstance(vol_change, float)
        assert isinstance(forward_return, float)


def test_run_produces_both_ic_summaries_with_sane_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ARCHIVE_DIR", str(tmp_path))
    tickers = ["AAA", "BBB", "CCC"]
    for index, ticker in enumerate(tickers):
        closes = _synthetic_closes(seed=100 + index, n=350)
        dates = [f"2021-{(i // 28) % 12 + 1:02d}-{(i % 28) + 1:02d}" for i in range(len(closes))]
        json.dump({"ticker": ticker, "rows": {d: [c, 1000] for d, c in zip(dates, closes)}},
                 open(tmp_path / f"{ticker}.json", "w"))

    def fake_load_series(ticker, directory=None):
        rows = json.load(open(tmp_path / f"{ticker}.json"))["rows"]
        ordered = sorted(rows)
        return {"dates": ordered, "closes": [rows[d][0] for d in ordered]}

    monkeypatch.setattr(module, "load_series", fake_load_series)
    result = module.run(tickers=tickers)
    assert result["tickers_sampled"] == 3
    assert result["tickers_with_sufficient_history"] == 3
    assert result["trading_dates_covered"] > 0
    for key in ("mean_reversion", "direction"):
        summary = result[key]["summary"]
        assert "periods_accumulated" in summary
        assert "mean_rank_ic" in summary


def test_run_handles_no_archived_tickers_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ARCHIVE_DIR", str(tmp_path))
    result = module.run(tickers=[])
    assert result["tickers_sampled"] == 0
    assert result["trading_dates_covered"] == 0
    assert result["mean_reversion"]["summary"]["periods_accumulated"] == 0
