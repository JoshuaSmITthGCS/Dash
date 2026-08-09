import math
import sys
from datetime import date, timedelta

import build_covered_call_screen as module


class FakeFrame:
    """Minimal stand-in for a pandas DataFrame: iterrows() over plain dicts."""

    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


class FakeChain:
    def __init__(self, calls, puts):
        self.calls = FakeFrame(calls)
        self.puts = FakeFrame(puts)


class FakeTicker:
    def __init__(self, options=None, chains=None, raise_on_options=False, raise_on_chain=False):
        self._options = options or []
        self._chains = chains or {}
        self._raise_on_options = raise_on_options
        self._raise_on_chain = raise_on_chain

    @property
    def options(self):
        if self._raise_on_options:
            raise RuntimeError("boom")
        return self._options

    def option_chain(self, expiration):
        if self._raise_on_chain:
            raise RuntimeError("boom")
        return self._chains[expiration]


class FakeYf:
    def __init__(self, tickers):
        self._tickers = tickers

    def Ticker(self, symbol):  # noqa: N802 - matches yfinance's API
        return self._tickers[symbol]


def fake_history(sessions=40, start_price=100, drift=0.0):
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    closes = [start_price + index * drift for index in range(sessions)]
    volumes = [1_000_000] * sessions
    return {"dates": dates, "closes": closes, "volumes": volumes}


def make_yahoo_history(per_ticker):
    def _yahoo_history(ticker, yf):
        return per_ticker.get(ticker, {"dates": [], "closes": [], "volumes": []})
    return _yahoo_history


TODAY = date(2024, 3, 1)
EXPIRATION = "2024-03-08"  # exactly TARGET_DAYS_TO_EXPIRATION (7) out from TODAY


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


# strike=102, iv=0.3, price=100, dte=7 -> Black-Scholes call delta ~0.32 (see options_common.call_delta)
TARGET_DELTA_CALL = contract(strike=102, bid=2.0, ask=2.08, iv=0.3, open_interest=200)


def test_build_row_selects_call_near_target_delta(monkeypatch):
    universe = {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION],
                          chains={EXPIRATION: FakeChain([TARGET_DELTA_CALL], [])}),
    })

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["expiration"] == EXPIRATION
    assert row["days_to_expiration"] == 7
    assert row["call"]["strike"] == 102
    assert abs(row["call"]["delta"] - module.TARGET_DELTA) < 0.05
    assert row["metrics"]["premium"] == 2.04
    assert row["metrics"]["breakeven"] == 97.96
    assert row["capital_required"] == 10000
    assert row["metrics"]["downside_cushion_pct"] == 0.0204


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    universe = {"ticker": "THIN", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"THIN": fake_history(sessions=10)}))
    fake_yf = FakeYf({"THIN": FakeTicker(options=[EXPIRATION],
                                          chains={EXPIRATION: FakeChain([TARGET_DELTA_CALL], [])})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    universe = {"ticker": "NOOPT", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    universe = {"ticker": "TOOSOON", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"TOOSOON": fake_history()}))
    # Same-day expiration (0 days out) is below MIN_DAYS_TO_EXPIRATION (1)
    fake_yf = FakeYf({"TOOSOON": FakeTicker(options=["2024-03-01"])})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_no_contract_clears_target_delta(monkeypatch):
    universe = {"ticker": "NOMATCH", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOMATCH": fake_history()}))
    # Deep out-of-the-money: moneyness far past the 0.35 ceiling select_by_target_delta enforces.
    far_otm = contract(strike=200, bid=0.05, ask=0.10, iv=0.3, open_interest=200)
    fake_yf = FakeYf({
        "NOMATCH": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([far_otm], [])}),
    })

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_score_rows_gates_small_cap_and_ranks_better_row_first():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.30, "liquidity": 2.0, "cushion": 0.03}, "call": {}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.10, "liquidity": 0.5, "cushion": 0.01}, "call": {}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}

    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]
    assert scored[0]["ticker"] == "BIG"


def test_score_rows_flags_insufficient_history():
    rows = [
        {"ticker": "NOHIST", "price": 50, "market_cap": 5e9, "realized_volatility_20d": None,
         "factors": {"expected_value_pct": 0.30, "liquidity": 2.0, "cushion": 0.03}, "call": {}},
    ]
    scored = module.score_rows(rows)
    assert "INSUFFICIENT_HISTORY" in scored[0]["reason_codes"]
    assert scored[0]["eligibility"] is False


def test_to_result_shape():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology",
        "peer_group_label": "Software", "peer_group": "sector:technology",
        "percentile": 80.0, "score": 1.23, "structural_score": 70, "confidence": 0.8,
        "price": 100, "trend_20d": 0.05, "expiration": EXPIRATION, "days_to_expiration": 30,
        "capital_required": 10000,
        "call": {"strike": 105, "bid": 2.0, "ask": 2.2, "mid": 2.1, "spread_pct": 0.0952,
                 "implied_volatility": 0.3, "open_interest": 200, "delta": 0.3015},
        "metrics": {"premium": 2.1, "breakeven": 97.9, "annualized_yield": 0.2555,
                   "max_return_if_assigned_pct": 0.071, "probability_assigned": 0.3015,
                   "downside_cushion_pct": 0.021},
        "reason_codes": [],
    }

    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["peer_group"] == "Software"
    assert result["capital_required"] == 10000
    assert result["metrics"] == row["metrics"]
    assert result["legs"] == [{
        "action": "sell", "option_type": "call", "strike": 105, "bid": 2.0, "ask": 2.2,
        "mid": 2.1, "spread_pct": 0.0952, "implied_volatility": 0.3, "open_interest": 200,
        "delta": 0.3015,
    }]


def test_run_publishes_scored_results(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60, "confidence": 0.7},
    ]
    per_ticker = {"AAA": fake_history(), "BBB": fake_history(start_price=80)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    aaa_call = contract(strike=102, bid=2.0, ask=2.08, iv=0.3, open_interest=200)
    bbb_call = contract(strike=82, bid=1.6, ask=1.66, iv=0.3, open_interest=200)
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([aaa_call], [])}),
        "BBB": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([bbb_call], [])}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_COVERED_CALL_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/covered-calls.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    assert result["window"] == {
        "min_days_to_expiration": module.MIN_DAYS_TO_EXPIRATION,
        "max_days_to_expiration": module.MAX_DAYS_TO_EXPIRATION,
        "target_days_to_expiration": module.TARGET_DAYS_TO_EXPIRATION,
        "target_delta": module.TARGET_DELTA,
    }


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_COVERED_CALL_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_COVERED_CALL_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/covered-calls.json"] == result


# --- backtest_universe / run_backtest -------------------------------------------------------
#
# fake_history()'s flat/linear closes make realized_volatility_20d() return 0.0 (falsy), which
# silently skips every walk-forward period. These tests need genuinely non-flat price history,
# with one deliberate large jump so a period settles far above the strike of the call sold at
# entry (a spot check that the covered-call return gets capped at the strike, not left uncapped
# like plain stock ownership).
JUMP_INDEX = 90
JUMP_MULTIPLIER = 1.6


def non_flat_history(sessions=130, jump_index=JUMP_INDEX, jump_multiplier=JUMP_MULTIPLIER):
    closes = []
    price = 100.0
    for index in range(sessions):
        price = price * (1 + 0.02 * math.sin(index * 0.9) + 0.01 * math.sin(index * 0.37) + 0.0005)
        if index == jump_index:
            price *= jump_multiplier
        closes.append(round(price, 2))
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    return {"dates": dates, "closes": closes, "volumes": [1_000_000] * sessions}


def test_backtest_universe_returns_stats_with_capped_gain(monkeypatch):
    history = non_flat_history()
    closes = history["closes"]
    universe = [{"ticker": "AAA"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": history}))

    stats = module.backtest_universe(universe, object(), as_of=TODAY)

    assert stats is not None
    assert stats["num_trades"] > 0
    assert set(stats) == {"num_trades", "total_return", "annualized_return", "sharpe_ratio",
                          "max_drawdown", "win_rate", "average_pnl_per_trade", "equity_curve"}

    # The jump at JUMP_INDEX (90) lands inside the walk-forward period entered at index 86 and
    # settled at index 91 - recompute what backtest_universe would have sold at that entry
    # (same helpers, same inputs) so we can spot-check the settlement was capped at the strike.
    periods = module.walk_periods(closes, module.TARGET_DAYS_TO_EXPIRATION)
    period_index = periods.index((86, 91))
    entry_index, expiry_index = periods[period_index]
    price, settle_price = closes[entry_index], closes[expiry_index]
    iv = module.realized_volatility_20d(closes[:entry_index + 1])
    calls, _ = module.synthetic_chain(price, iv, module.TARGET_DAYS_TO_EXPIRATION)
    call = module.select_by_target_delta(calls, price, module.TARGET_DAYS_TO_EXPIRATION,
                                         side="call", target_delta=module.TARGET_DELTA)
    assert call is not None
    uncapped_stock_return = (settle_price - price) / price
    capped_upper_bound = (call["strike"] - price) / price + 0.05  # + generous premium/fee slack

    equity = stats["equity_curve"]
    period_return = equity[period_index + 1] / equity[period_index] - 1

    assert settle_price > call["strike"]  # confirms this period actually exercises the cap
    assert period_return < capped_upper_bound
    assert period_return < uncapped_stock_return / 2  # nowhere near the uncapped stock move


def test_backtest_universe_returns_none_when_history_too_short(monkeypatch):
    universe = [{"ticker": "SHORT1"}, {"ticker": "SHORT2"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({
        "SHORT1": fake_history(sessions=15),
        "SHORT2": fake_history(sessions=10),
    }))

    assert module.backtest_universe(universe, object(), as_of=TODAY) is None


BACKTEST_STATS_KEYS = {"num_trades", "total_return", "annualized_return", "sharpe_ratio",
                       "max_drawdown", "win_rate", "average_pnl_per_trade", "equity_curve"}


def test_run_backtest_publishes_success(monkeypatch):
    loaded = {"advisor.json": {"research": [{"ticker": "AAA"}]}}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": non_flat_history()}))
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    result = module.run_backtest(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/covered-calls-backtest.json"] == result
    assert result["backtest"]["num_trades"] > 0
    assert set(result["backtest"]) == BACKTEST_STATS_KEYS
    assert result["window"] == {
        "min_days_to_expiration": module.MIN_DAYS_TO_EXPIRATION,
        "max_days_to_expiration": module.MAX_DAYS_TO_EXPIRATION,
        "target_days_to_expiration": module.TARGET_DAYS_TO_EXPIRATION,
        "target_delta": module.TARGET_DELTA,
    }


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/covered-calls-backtest.json"] == result


def test_run_backtest_ignores_enable_covered_call_screen_flag(monkeypatch):
    # Unlike run(), run_backtest() needs no live option-chain data, so it must execute
    # regardless of whether ENABLE_COVERED_CALL_SCREEN is set at all.
    monkeypatch.delenv("ENABLE_COVERED_CALL_SCREEN", raising=False)
    loaded = {"advisor.json": {"research": [{"ticker": "AAA"}]}}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": non_flat_history()}))
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    result = module.run_backtest(as_of=TODAY)

    assert result is not None
    assert result["status"] == "success"
