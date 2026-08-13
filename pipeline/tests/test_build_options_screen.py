import sys
from datetime import date, timedelta

import build_options_screen as module


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


class FakeEarningsFrame:
    def __init__(self, rows):
        self.index = [row[0] for row in rows]
        self.columns = ["Surprise(%)"]
        self.empty = not rows
        self._surprises = [row[1] for row in rows]

    def __getitem__(self, column):
        class _Column:
            def __init__(self, values):
                self._values = values

            def tolist(self):
                return self._values
        return _Column(self._surprises)


NAN = float("nan")


class FakeTicker:
    def __init__(self, options=None, chains=None, raise_on_options=False, raise_on_chain=False,
                earnings_dates=None):
        self._options = options or []
        self._chains = chains or {}
        self._raise_on_options = raise_on_options
        self._raise_on_chain = raise_on_chain
        self.earnings_dates = earnings_dates

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


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def test_select_expiration_prefers_nearest_to_target_within_window():
    expirations = ["2024-03-02", "2024-03-08", "2024-03-15", "2024-04-20"]
    expiration, dte = module.select_expiration(expirations, as_of=TODAY)
    assert expiration == "2024-03-08"
    assert dte == 7


def test_select_expiration_excludes_out_of_window_dates():
    expirations = ["2024-03-01", "2024-03-20", "2024-05-01"]
    expiration, dte = module.select_expiration(expirations, as_of=TODAY)
    assert expiration is None
    assert dte is None


def test_select_contract_picks_tightest_spread_within_atm_band():
    frame = FakeFrame([
        contract(strike=100, bid=1.00, ask=1.60),   # spread 37.5%, too wide
        contract(strike=101, bid=2.00, ask=2.10),   # spread ~4.9%, ATM, liquid
        contract(strike=140, bid=0.05, ask=0.10),   # far OTM, excluded by moneyness
        contract(strike=102, bid=1.90, ask=2.30, open_interest=5),  # illiquid, excluded
    ])
    best = module.select_contract(frame, price=100)
    assert best["strike"] == 101
    assert best["open_interest"] == 200


def test_build_row_selects_call_on_positive_trend_and_put_on_negative(monkeypatch):
    universe_up = {"ticker": "UP", "sector": "Technology", "market_cap": 5e9, "score": 70, "data_coverage": 0.8}
    universe_down = {"ticker": "DOWN", "sector": "Technology", "market_cap": 5e9, "score": 40, "data_coverage": 0.6}
    per_ticker = {
        "UP": fake_history(drift=1.0),
        "DOWN": fake_history(drift=-1.0, start_price=200),
    }
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    expiration = "2024-03-15"
    chain_calls = [contract(strike=138, bid=2.0, ask=2.08)]
    chain_puts = [contract(strike=160, bid=2.0, ask=2.08)]
    fake_yf = FakeYf({
        "UP": FakeTicker(options=[expiration], chains={expiration: FakeChain(chain_calls, [])}),
        "DOWN": FakeTicker(options=[expiration], chains={expiration: FakeChain([], chain_puts)}),
    })

    up_row = module.build_row(universe_up, fake_yf, as_of=TODAY)
    down_row = module.build_row(universe_down, fake_yf, as_of=TODAY)

    assert up_row["option_type"] == "call"
    assert down_row["option_type"] == "put"
    assert up_row["days_to_expiration"] == 14


def test_build_row_populates_sentiment_and_research_confidence_from_the_entry(monkeypatch):
    universe_up = {"ticker": "UP", "sector": "Technology", "market_cap": 5e9, "score": 70, "data_coverage": 0.8,
                  "sentiment_detail": {"average": 0.5, "coverage": 0.6, "article_count": 4}}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"UP": fake_history(drift=1.0)}))
    expiration = "2024-03-15"
    fake_yf = FakeYf({"UP": FakeTicker(options=[expiration],
                                       chains={expiration: FakeChain([contract(strike=138, bid=2.0, ask=2.08)], [])})})

    row = module.build_row(universe_up, fake_yf, as_of=TODAY, generated_at="2024-03-01T00:00:00+00:00")

    assert row["option_type"] == "call"
    assert row["news_sentiment"] == 0.5 * 0.6  # signed mode, call side -> direction=1
    assert row["research_confidence"] == (70 - 50) * 0.8
    assert row["factors"]["news_sentiment"] == row["news_sentiment"]
    assert row["factors"]["research_confidence"] == row["research_confidence"]


def test_build_row_leaves_sentiment_and_research_confidence_none_without_source_data(monkeypatch):
    universe_up = {"ticker": "UP", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"UP": fake_history(drift=1.0)}))
    expiration = "2024-03-15"
    fake_yf = FakeYf({"UP": FakeTicker(options=[expiration],
                                       chains={expiration: FakeChain([contract(strike=138, bid=2.0, ask=2.08)], [])})})

    row = module.build_row(universe_up, fake_yf, as_of=TODAY)

    assert row["news_sentiment"] is None
    assert row["research_confidence"] is None


def test_build_row_excludes_a_contract_spanning_a_known_earnings_date(monkeypatch):
    universe = {"ticker": "EARNTEST1", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"EARNTEST1": fake_history(drift=1.0)}))
    expiration = "2024-03-15"
    # Expiration is 14 days out (within window); earnings lands inside that window.
    fake_yf = FakeYf({"EARNTEST1": FakeTicker(
        options=[expiration], chains={expiration: FakeChain([contract(strike=138, bid=2.0, ask=2.08)], [])},
        earnings_dates=FakeEarningsFrame([("2024-03-08", NAN)]))})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_keeps_a_contract_when_earnings_falls_outside_the_expiration(monkeypatch):
    universe = {"ticker": "EARNTEST2", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"EARNTEST2": fake_history(drift=1.0)}))
    expiration = "2024-03-15"
    fake_yf = FakeYf({"EARNTEST2": FakeTicker(
        options=[expiration], chains={expiration: FakeChain([contract(strike=138, bid=2.0, ask=2.08)], [])},
        earnings_dates=FakeEarningsFrame([("2024-04-01", NAN)]))})  # after this expiration

    row = module.build_row(universe, fake_yf, as_of=TODAY)
    assert row is not None
    assert row["ticker"] == "EARNTEST2"


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    universe = {"ticker": "THIN", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history()}))
    fake_yf = FakeYf({"THIN": FakeTicker(options=["2024-03-02"])})  # 1 day out, below MIN_DAYS_TO_EXPIRATION

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    universe = {"ticker": "NOOPT", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_score_rows_ranks_by_composite_and_gates_small_caps():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": -1.0, "liquidity": 2.0, "trend_strength": 0.1}, "contract": {}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": -0.5, "liquidity": 1.0, "trend_strength": 0.05}, "contract": {}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_run_publishes_scored_results(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "data_coverage": 0.8},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60, "data_coverage": 0.7},
    ]
    per_ticker = {"AAA": fake_history(drift=1.0), "BBB": fake_history(drift=0.5, start_price=80)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    expiration = "2024-03-15"
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[expiration],
                          chains={expiration: FakeChain([contract(strike=139, bid=2, ask=2.08)], [])}),
        "BBB": FakeTicker(options=[expiration],
                          chains={expiration: FakeChain([contract(strike=100, bid=2, ask=2.08)], [])}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/options.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"


# --- walk-forward backtest ---------------------------------------------------------

import math


def wavy_history(sessions=320, start_price=100, drift=0.05, amplitude=10, period=17):
    """Non-flat synthetic price history: up/down drift + oscillation, so realized
    volatility is never 0.0 (flat closes make realized_volatility_20d return 0.0, which
    is falsy and breaks IV-dependent code paths downstream).
    """
    dates = [(date(2023, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    closes = [round(start_price + index * drift + amplitude * math.sin(index / period), 2)
              for index in range(sessions)]
    volumes = [1_000_000] * sessions
    return {"dates": dates, "closes": closes, "volumes": volumes}


def test_backtest_universe_produces_trades_with_enough_history(monkeypatch):
    universe = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    per_ticker = {
        "AAA": wavy_history(sessions=320, start_price=100, drift=0.05),
        "BBB": wavy_history(sessions=320, start_price=200, drift=-0.03, period=13),
    }
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))

    stats = module.backtest_universe(universe, yf=object())

    assert stats is not None
    assert stats["num_trades"] > 0
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio",
                "max_drawdown", "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in stats


def test_backtest_universe_returns_none_when_history_too_short(monkeypatch):
    universe = [{"ticker": "SHORT"}]
    per_ticker = {"SHORT": fake_history(sessions=10, drift=1.0)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))

    assert module.backtest_universe(universe, yf=object()) is None


def test_run_backtest_publishes_success(monkeypatch):
    universe = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    per_ticker = {
        "AAA": wavy_history(sessions=320, start_price=100, drift=0.05),
        "BBB": wavy_history(sessions=320, start_price=200, drift=-0.03, period=13),
    }
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/options-backtest.json"] == result
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio",
                "max_drawdown", "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in result["backtest"]


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/options-backtest.json"] == result


def test_run_backtest_uses_expected_output_filename(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    module.run_backtest()

    assert "screens/options-backtest.json" in saved
