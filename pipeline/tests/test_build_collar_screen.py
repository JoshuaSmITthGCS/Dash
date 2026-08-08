import math
import sys
from datetime import date, timedelta

import build_collar_screen as module


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
EXPIRATION = "2024-03-31"  # 30 days out from TODAY, matches TARGET_DAYS_TO_EXPIRATION


def contract(strike, bid, ask, open_interest=200, iv=0.3, volume=10):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def collar_chain(put_strike=92, put_bid=2.0, put_ask=2.2, call_strike=105, call_bid=2.0, call_ask=2.2):
    """A chain with one qualifying put (~7.5% OTM) and one qualifying call (~30 delta)."""
    puts = [contract(strike=put_strike, bid=put_bid, ask=put_ask)]
    calls = [contract(strike=call_strike, bid=call_bid, ask=call_ask)]
    return FakeChain(calls, puts)


def test_build_row_selects_put_and_call_legs_happy_path(monkeypatch):
    universe = {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: collar_chain()})})

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["days_to_expiration"] == 30
    assert row["expiration"] == EXPIRATION
    # put leg sits 5-10% below spot
    put_moneyness = row["put"]["strike"] / row["price"] - 1
    assert -0.105 <= put_moneyness <= -0.045
    # call leg is near 30 delta
    assert abs(row["call"]["delta"] - 0.30) < 0.10
    assert row["call"]["strike"] > row["put"]["strike"]
    assert row["metrics"]["floor_price"] == row["put"]["strike"]
    assert row["metrics"]["cap_price"] == row["call"]["strike"]


def test_build_row_returns_none_with_thin_history(monkeypatch):
    universe = {"ticker": "THIN", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=5)}))
    fake_yf = FakeYf({"THIN": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: collar_chain()})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    universe = {"ticker": "NOOPT", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    universe = {"ticker": "SOON", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"SOON": fake_history()}))
    # 4 days out - below MIN_DAYS_TO_EXPIRATION (15)
    fake_yf = FakeYf({"SOON": FakeTicker(options=["2024-03-05"])})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_put_leg_missing(monkeypatch):
    universe = {"ticker": "NOPUT", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOPUT": fake_history()}))
    chain = FakeChain(calls=[contract(strike=105, bid=2.0, ask=2.2)], puts=[])
    fake_yf = FakeYf({"NOPUT": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: chain})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_call_leg_missing(monkeypatch):
    universe = {"ticker": "NOCALL", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOCALL": fake_history()}))
    chain = FakeChain(calls=[], puts=[contract(strike=92, bid=2.0, ask=2.2)])
    fake_yf = FakeYf({"NOCALL": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: chain})})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_call_strike_not_above_put_strike(monkeypatch):
    """Guard against a degenerate chain where the selected call sits at/below the put strike."""
    universe = {"ticker": "WEIRD", "sector": "Technology", "market_cap": 1e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"WEIRD": fake_history()}))
    fake_yf = FakeYf({"WEIRD": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: collar_chain()})})

    # Force the two selectors to hand back a call strike at/below the put strike, which
    # the real selectors won't do under normal defaults - this exercises the sanity guard.
    monkeypatch.setattr(module, "select_by_target_moneyness",
                         lambda frame, price, target, tolerance: {"strike": 92, "bid": 2.0, "ask": 2.2,
                                                                    "mid": 2.1, "spread_pct": 0.1,
                                                                    "implied_volatility": 0.3,
                                                                    "open_interest": 200, "volume": 10,
                                                                    "moneyness": -0.08})
    monkeypatch.setattr(module, "select_by_target_delta",
                         lambda frame, price, dte, side, target_delta: {"strike": 90, "bid": 2.0, "ask": 2.2,
                                                                          "mid": 2.1, "spread_pct": 0.1,
                                                                          "implied_volatility": 0.3,
                                                                          "open_interest": 200, "volume": 10,
                                                                          "moneyness": -0.10, "delta": 0.30})

    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_metrics_are_internally_consistent_for_debit_and_credit(monkeypatch):
    universe = {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))

    # Net debit: put costs more than the call collects.
    debit_chain = collar_chain(put_bid=2.0, put_ask=2.2, call_bid=1.0, call_ask=1.2)
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: debit_chain})})
    debit_row = module.build_row(universe, fake_yf, as_of=TODAY)
    assert debit_row["metrics"]["net_cost"] > 0

    # Net credit: call collects more than the put costs.
    credit_chain = collar_chain(put_bid=1.0, put_ask=1.2, call_bid=2.0, call_ask=2.2)
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: credit_chain})})
    credit_row = module.build_row(universe, fake_yf, as_of=TODAY)
    assert credit_row["metrics"]["net_cost"] < 0

    for row in (debit_row, credit_row):
        metrics = row["metrics"]
        assert math.isfinite(metrics["max_loss_pct"])
        assert math.isfinite(metrics["max_gain_pct"])
        # max_loss_pct + max_gain_pct always collapses to the floor-to-cap range, regardless
        # of whether the collar was built for a net debit or a net credit.
        assert math.isclose(metrics["max_loss_pct"] + metrics["max_gain_pct"],
                             metrics["range_width_pct"], abs_tol=1e-9)

    # A credit reduces max loss and increases max gain relative to a debit on the same strikes.
    assert credit_row["metrics"]["max_loss_pct"] < debit_row["metrics"]["max_loss_pct"]
    assert credit_row["metrics"]["max_gain_pct"] > debit_row["metrics"]["max_gain_pct"]


def test_score_rows_gates_small_cap_as_ineligible():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"cost_efficiency": -0.01, "range_width": 0.25, "liquidity": 2.0},
         "put": {}, "call": {}, "metrics": {}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"cost_efficiency": -0.05, "range_width": 0.10, "liquidity": 1.0},
         "put": {}, "call": {}, "metrics": {}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_score_rows_ranks_cheaper_wider_more_liquid_collar_higher():
    # Padding rows keep winsorize's small-sample clamping from tying GOOD/MID/BAD together;
    # they aren't asserted on individually, just present so the composite z-scores separate.
    def row(ticker, cost_efficiency, range_width, liquidity):
        return {"ticker": ticker, "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
                "factors": {"cost_efficiency": cost_efficiency, "range_width": range_width,
                            "liquidity": liquidity},
                "put": {}, "call": {}, "metrics": {}}

    rows = [
        row("GOOD", -0.005, 0.25, 2.5),
        row("MID", -0.03, 0.15, 1.0),
        row("BAD", -0.08, 0.05, 0.2),
        row("PAD1", -0.04, 0.12, 0.8),
        row("PAD2", -0.02, 0.20, 1.5),
        row("PAD3", -0.06, 0.08, 0.5),
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["GOOD"]["score"] > by_ticker["MID"]["score"] > by_ticker["BAD"]["score"]


def test_to_result_shape():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology", "peer_group": "sector:technology",
        "peer_group_label": "Technology", "percentile": 80.0, "score": 1.23,
        "structural_score": 70, "confidence": 0.8, "price": 100.0, "trend_20d": 0.02,
        "expiration": EXPIRATION, "days_to_expiration": 30, "capital_required": 10100.0,
        "put": {"strike": 92.0, "bid": 2.0, "ask": 2.2, "mid": 2.1, "spread_pct": 0.095,
                "implied_volatility": 0.3, "open_interest": 200},
        "call": {"strike": 105.0, "bid": 2.0, "ask": 2.2, "mid": 2.1, "spread_pct": 0.095,
                 "implied_volatility": 0.3, "open_interest": 200, "delta": 0.30},
        "metrics": {"net_cost": 0.0, "net_cost_pct": 0.0, "floor_price": 92.0, "cap_price": 105.0,
                    "range_width_pct": 0.13, "max_loss_pct": 0.08, "max_gain_pct": 0.05},
        "reason_codes": [],
    }
    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["peer_group"] == "Technology"
    assert len(result["legs"]) == 2
    put_leg, call_leg = result["legs"]
    assert put_leg["action"] == "buy" and put_leg["option_type"] == "put"
    assert put_leg["strike"] == 92.0
    assert call_leg["action"] == "sell" and call_leg["option_type"] == "call"
    assert call_leg["strike"] == 105.0
    assert call_leg["delta"] == 0.30
    assert result["metrics"] == row["metrics"]
    assert result["reason_codes"] == []


def test_run_publishes_scored_results(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60, "confidence": 0.7},
    ]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({
        "AAA": fake_history(), "BBB": fake_history(),
    }))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION],
                          chains={EXPIRATION: collar_chain(put_bid=2.0, put_ask=2.2,
                                                            call_bid=1.0, call_ask=1.2)}),
        "BBB": FakeTicker(options=[EXPIRATION],
                          chains={EXPIRATION: collar_chain(put_bid=1.0, put_ask=1.2,
                                                            call_bid=2.0, call_ask=2.2)}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_COLLAR_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/collars.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    assert result["window"]["target_delta_call"] == module.TARGET_DELTA_CALL
    assert result["window"]["target_moneyness_put"] == module.TARGET_MONEYNESS_PUT


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_COLLAR_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_COLLAR_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
