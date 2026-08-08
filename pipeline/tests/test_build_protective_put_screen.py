import sys
from datetime import date, timedelta

import build_protective_put_screen as module


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


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=10):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def test_build_row_selects_put_within_five_to_ten_percent_band(monkeypatch):
    universe = {"ticker": "HEDGE", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"HEDGE": fake_history(start_price=100)}))
    expiration = "2024-03-31"  # 30 days out
    # price=100: 7.5% below is 92.5. Offer a range of puts; the closest to -7.5% should win.
    chain_puts = [
        contract(strike=98, bid=1.0, ask=1.1),   # -2% moneyness, outside tolerance band
        contract(strike=93, bid=2.0, ask=2.2),   # -7% moneyness, within band, close to target
        contract(strike=70, bid=0.1, ask=0.15),  # -30% moneyness, far OTM
    ]
    fake_yf = FakeYf({"HEDGE": FakeTicker(options=[expiration], chains={expiration: FakeChain([], chain_puts)})})

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["put"]["strike"] == 93
    moneyness = row["put"]["strike"] / row["price"] - 1
    assert -0.105 <= moneyness <= -0.045
    assert row["days_to_expiration"] == 30


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    universe = {"ticker": "THIN", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    fake_yf = FakeYf({"THIN": FakeTicker(options=["2024-03-31"])})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    universe = {"ticker": "NOOPT", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_chain_unavailable(monkeypatch):
    universe = {"ticker": "BADCHAIN", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"BADCHAIN": fake_history()}))
    fake_yf = FakeYf({"BADCHAIN": FakeTicker(options=["2024-03-31"], raise_on_chain=True)})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    universe = {"ticker": "TOOSOON", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"TOOSOON": fake_history()}))
    # 1 day out, below MIN_DAYS_TO_EXPIRATION (15)
    fake_yf = FakeYf({"TOOSOON": FakeTicker(options=["2024-03-02"])})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_only_atm_puts_available(monkeypatch):
    universe = {"ticker": "ATMONLY", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"ATMONLY": fake_history(start_price=100)}))
    expiration = "2024-03-31"
    chain_puts = [contract(strike=100, bid=2.0, ask=2.1)]  # ATM, 0% moneyness - outside -4.5%..-10.5% band
    fake_yf = FakeYf({"ATMONLY": FakeTicker(options=[expiration], chains={expiration: FakeChain([], chain_puts)})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_only_deep_otm_puts_available(monkeypatch):
    universe = {"ticker": "DEEPOTM", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"DEEPOTM": fake_history(start_price=100)}))
    expiration = "2024-03-31"
    chain_puts = [contract(strike=70, bid=0.1, ask=0.15)]  # -30% moneyness, way outside band
    fake_yf = FakeYf({"DEEPOTM": FakeTicker(options=[expiration], chains={expiration: FakeChain([], chain_puts)})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_score_rows_ranks_by_composite_and_gates_small_caps():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": 1.0, "cost_efficiency": 1.0, "liquidity": 2.0}, "put": {}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": 0.2, "cost_efficiency": 0.1, "liquidity": 0.5}, "put": {}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_score_rows_ranks_cheaper_more_liquid_hedge_above_pricier_thinner_one():
    # Several rows so winsorize's percentile clamp doesn't collapse a 2-row sample to
    # identical values - mirrors the spread build_row would produce across a real universe.
    rows = [
        {"ticker": "CHEAP", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": 1.2, "cost_efficiency": -0.02, "liquidity": 2.0}, "put": {}},
        {"ticker": "MID1", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": 0.3, "cost_efficiency": -0.05, "liquidity": 1.0}, "put": {}},
        {"ticker": "MID2", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": 0.0, "cost_efficiency": -0.06, "liquidity": 0.8}, "put": {}},
        {"ticker": "PRICEY", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": -0.8, "cost_efficiency": -0.10, "liquidity": 0.2}, "put": {}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["CHEAP"]["score"] > by_ticker["PRICEY"]["score"]
    ranks_order = [row["ticker"] for row in scored]
    assert ranks_order[0] == "CHEAP"


def test_to_result_produces_exact_envelope_shape():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology", "peer_group_label": "Software",
        "percentile": 80.0, "score": 0.5, "structural_score": 70, "confidence": 0.8, "price": 100.0,
        "trend_20d": 0.05, "expiration": "2024-03-31", "days_to_expiration": 30, "capital_required": 10200.0,
        "implied_realized_vol_ratio": 0.9,
        "put": {"strike": 93.0, "bid": 2.0, "ask": 2.2, "mid": 2.1, "spread_pct": 0.0952,
                "implied_volatility": 0.4, "open_interest": 200},
        "metrics": {"cost": 2.1, "cost_pct": 0.021, "floor_price": 93.0, "max_loss_with_hedge_pct": 0.091},
        "reason_codes": [],
    }
    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["peer_group"] == "Software"
    assert len(result["legs"]) == 1
    leg = result["legs"][0]
    assert leg["action"] == "buy"
    assert leg["option_type"] == "put"
    assert leg["strike"] == 93.0
    assert leg["open_interest"] == 200
    assert result["metrics"] == row["metrics"]
    assert result["capital_required"] == 10200.0


def test_run_publishes_scored_results(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60, "confidence": 0.7},
    ]
    per_ticker = {"AAA": fake_history(start_price=100, drift=0.05), "BBB": fake_history(start_price=80, drift=0.05)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    expiration = "2024-03-31"
    # AAA closes at 100 + 39*0.05 = 101.95; strike 94 -> moneyness ~ -7.8%, inside the band.
    # BBB closes at 80 + 39*0.05 = 81.95; strike 76 -> moneyness ~ -7.3%, inside the band.
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[expiration],
                          chains={expiration: FakeChain([], [contract(strike=94, bid=2, ask=2.2)])}),
        "BBB": FakeTicker(options=[expiration],
                          chains={expiration: FakeChain([], [contract(strike=76, bid=1.5, ask=1.7)])}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_PROTECTIVE_PUT_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/protective-puts.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_PROTECTIVE_PUT_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_PROTECTIVE_PUT_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
