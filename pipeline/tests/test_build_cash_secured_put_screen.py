import sys
from datetime import date, timedelta

import build_cash_secured_put_screen as module


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
EXPIRATION = "2024-03-08"  # 7 days out from TODAY, matches TARGET_DAYS_TO_EXPIRATION


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=10):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


# Puts at price=100, dte=7: delta(strike=97) ~ -0.282, the closest of these to -0.30.
PUTS_AT_100 = [
    contract(strike=92, bid=0.60, ask=0.70),
    contract(strike=97, bid=1.90, ask=2.10),
    contract(strike=100, bid=4.60, ask=4.90),
]

# Puts at price=80, dte=7: delta(strike=78) ~ -0.314, closest of these to -0.30.
PUTS_AT_80 = [
    contract(strike=74, bid=0.50, ask=0.60),
    contract(strike=78, bid=1.55, ask=1.70),
    contract(strike=80, bid=3.70, ask=3.95),
]


def universe_entry(ticker, market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


def test_build_row_selects_put_near_target_delta(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], PUTS_AT_100)}),
    })

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["put"]["strike"] == 97
    assert row["days_to_expiration"] == 7
    assert row["expiration"] == EXPIRATION
    assert abs(row["put"]["delta"] - (-0.30)) < 0.02
    assert row["capital_required"] == 97 * 100


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    entry = universe_entry("THIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    fake_yf = FakeYf({})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    entry = universe_entry("NOOPT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    entry = universe_entry("SHORTDATED")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"SHORTDATED": fake_history()}))
    # Same-day expiration (0 days out) - below MIN_DAYS_TO_EXPIRATION (1)
    fake_yf = FakeYf({"SHORTDATED": FakeTicker(options=["2024-03-01"])})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_no_contract_clears_target_delta(monkeypatch):
    entry = universe_entry("ILLIQUID")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"ILLIQUID": fake_history()}))
    # All puts fail the open-interest liquidity gate inside contract_liquidity/select_by_target_delta.
    illiquid_puts = [contract(strike=95, bid=1.90, ask=2.10, open_interest=5)]
    fake_yf = FakeYf({
        "ILLIQUID": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], illiquid_puts)}),
    })

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_probability_otm_and_assigned_sum_to_one(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], PUTS_AT_100)}),
    })

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    metrics = row["metrics"]
    assert metrics["probability_otm"] is not None
    assert metrics["probability_assigned"] is not None
    assert abs(metrics["probability_otm"] + metrics["probability_assigned"] - 1.0) < 1e-6


def test_score_rows_gates_small_caps():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"annualized_yield": 0.30, "probability_otm": 0.8, "liquidity": 2.0}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"annualized_yield": 0.10, "probability_otm": 0.6, "liquidity": 0.5}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]
    assert scored[0]["ticker"] == "BIG"


def test_score_rows_ranks_higher_yield_and_liquidity_above_worse():
    # Several eligible rows so winsorize's 5th/95th percentile clipping doesn't collapse
    # a two-point sample - each factor increases monotonically from WORST to BEST.
    tickers = ["WORST", "LOW", "MID", "HIGH", "BEST"]
    rows = [
        {"ticker": ticker, "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"annualized_yield": 0.05 + 0.05 * index,
                     "probability_otm": 0.5 + 0.05 * index,
                     "liquidity": 0.5 + 0.5 * index}}
        for index, ticker in enumerate(tickers)
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert all(row["eligibility"] for row in scored)
    # Winsorization clips the top and bottom 5%, so BEST/HIGH can tie after clipping - assert
    # the unclipped middle ordering strictly, and that BEST/HIGH rank above the bottom.
    assert by_ticker["WORST"]["score"] < by_ticker["LOW"]["score"] < by_ticker["MID"]["score"]
    assert by_ticker["MID"]["score"] <= by_ticker["HIGH"]["score"]
    assert by_ticker["BEST"]["score"] >= by_ticker["HIGH"]["score"]
    assert by_ticker["BEST"]["score"] > by_ticker["WORST"]["score"]
    assert scored[-1]["ticker"] == "WORST"
    assert {row["ticker"] for row in scored[:2]} == {"BEST", "HIGH"}


def test_to_result_matches_expected_envelope_shape():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology",
        "peer_group": "sector:technology", "peer_group_label": "Technology",
        "percentile": 87.5, "score": 1.234, "structural_score": 70, "confidence": 0.8,
        "price": 100, "trend_20d": 0.01, "expiration": EXPIRATION, "days_to_expiration": 30,
        "capital_required": 9500.0,
        "put": {"strike": 95, "bid": 1.9, "ask": 2.1, "mid": 2.0, "spread_pct": 0.1,
                "implied_volatility": 0.4, "open_interest": 200, "delta": -0.3069},
        "metrics": {"premium": 2.0, "collateral": 9500.0, "effective_cost_basis": 93.0,
                    "annualized_yield": 0.2564, "probability_otm": 0.6517, "probability_assigned": 0.3483},
        "reason_codes": [],
    }

    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["peer_group"] == "Technology"
    assert result["capital_required"] == 9500.0
    assert result["legs"] == [{"action": "sell", "option_type": "put", "strike": 95,
                               "bid": 1.9, "ask": 2.1, "mid": 2.0, "spread_pct": 0.1,
                               "implied_volatility": 0.4, "open_interest": 200, "delta": -0.3069}]
    assert result["metrics"] == row["metrics"]
    assert result["reason_codes"] == []


def test_run_publishes_scored_results(monkeypatch):
    universe = [universe_entry("AAA"), universe_entry("BBB", market_cap=4e9)]
    per_ticker = {"AAA": fake_history(start_price=100), "BBB": fake_history(start_price=80)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], PUTS_AT_100)}),
        "BBB": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], PUTS_AT_80)}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_CASH_SECURED_PUT_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/cash-secured-puts.json"] == result
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
    monkeypatch.delenv("ENABLE_CASH_SECURED_PUT_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_CASH_SECURED_PUT_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/cash-secured-puts.json"] == result


# --- backtest -----------------------------------------------------------------------------

def wiggly_history(sessions=200, start_price=100, amplitude=3, drift=0.05):
    """Non-flat close series: flat closes make realized_volatility_20d return 0.0 (falsy),
    which silently skips every period in backtest_universe. The alternating +/- amplitude
    plus a small drift keeps realized volatility non-zero and prices positive throughout.
    """
    closes = [start_price + amplitude * ((-1) ** index) + index * drift for index in range(sessions)]
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    return {"dates": dates, "closes": closes, "volumes": [1_000_000] * sessions}


def test_backtest_universe_returns_stats_with_trades(monkeypatch):
    per_ticker = {"AAA": wiggly_history(), "BBB": wiggly_history(start_price=80, amplitude=2)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    universe = [universe_entry("AAA"), universe_entry("BBB")]

    stats = module.backtest_universe(universe, yf=object())

    assert stats is not None
    assert stats["num_trades"] > 0
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in stats


def test_backtest_universe_returns_none_when_history_too_short(monkeypatch):
    per_ticker = {"AAA": fake_history(sessions=10), "BBB": fake_history(sessions=15)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    universe = [universe_entry("AAA"), universe_entry("BBB")]

    assert module.backtest_universe(universe, yf=object()) is None


def test_run_backtest_publishes_success(monkeypatch):
    universe = [universe_entry("AAA"), universe_entry("BBB", market_cap=4e9)]
    per_ticker = {"AAA": wiggly_history(start_price=100), "BBB": wiggly_history(start_price=80, amplitude=2)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/cash-secured-puts-backtest.json"] == result
    backtest = result["backtest"]
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in backtest
    assert backtest["num_trades"] > 0
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
    assert saved["screens/cash-secured-puts-backtest.json"] == result


def test_run_backtest_ignores_enable_flag(monkeypatch):
    # Unlike run(), run_backtest() has no opt-in flag gate - it should still execute (and not
    # return None) even when ENABLE_CASH_SECURED_PUT_SCREEN is unset/deleted.
    monkeypatch.delenv("ENABLE_CASH_SECURED_PUT_SCREEN", raising=False)
    universe = [universe_entry("AAA")]
    per_ticker = {"AAA": wiggly_history()}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)

    result = module.run_backtest()

    assert result is not None
    assert result["status"] == "success"
