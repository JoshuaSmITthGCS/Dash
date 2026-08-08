import sys
from datetime import date, timedelta

import build_advanced_options_screen as module


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
EXPIRATION = "2024-03-31"  # 30 days out from TODAY


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=10):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def condor_chain(price=100):
    """Calls/puts frames whose Black-Scholes deltas (iv=0.30, dte=30) land close to the
    screen's 0.18/0.08 target deltas, so select_by_target_delta resolves four distinct legs:
    call 108 -> delta ~0.197 (short call), call 113 -> delta ~0.084 (long call),
    put 93 -> delta ~-0.188 (short put), put 89 -> delta ~-0.081 (long put).
    """
    calls = [
        contract(strike=108, bid=2.00, ask=2.20, iv=0.30),   # short call
        contract(strike=113, bid=0.55, ask=0.75, iv=0.30),   # long call
    ]
    puts = [
        contract(strike=93, bid=1.95, ask=2.15, iv=0.30),    # short put
        contract(strike=89, bid=0.55, ask=0.75, iv=0.30),    # long put
    ]
    return FakeChain(calls, puts)


def straddle_chain(price=100):
    calls = [contract(strike=100, bid=3.00, ask=3.20, iv=0.35)]
    puts = [contract(strike=100, bid=2.90, ask=3.10, iv=0.35)]
    return FakeChain(calls, puts)


def combined_chain(price=100):
    """Everything condor_chain() and straddle_chain() need, from one chain fetch."""
    calls = [
        contract(strike=100, bid=3.00, ask=3.20, iv=0.35),   # ATM, straddle leg
        contract(strike=108, bid=2.00, ask=2.20, iv=0.30),   # short call
        contract(strike=113, bid=0.55, ask=0.75, iv=0.30),   # long call
    ]
    puts = [
        contract(strike=100, bid=2.90, ask=3.10, iv=0.35),   # ATM, straddle leg
        contract(strike=93, bid=1.95, ask=2.15, iv=0.30),    # short put
        contract(strike=89, bid=0.55, ask=0.75, iv=0.30),    # long put
    ]
    return FakeChain(calls, puts)


def make_entry(ticker="AAA", market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


def make_setup(entry, chain, price=100, dte=30, trend=0.05, realized=0.25, history_sessions=40):
    return (entry["ticker"], price, dte, EXPIRATION, trend, realized, chain, entry, history_sessions)


def wobble_history():
    """40 sessions ending at close=100 with a nonzero final-week wobble.

    A perfectly flat fake_history() has realized_volatility_20d() == 0.0, which is falsy and
    makes `iv_avg and realized` short-circuit to None even when both values exist - fine for
    the iron condor factors (they don't depend on realized vol) but it starves the
    straddle's iv_value factor in any test that needs a real ratio.
    """
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(40)]
    closes = [100.0] * 38 + [102.0, 100.0]
    volumes = [1_000_000] * 40
    return {"dates": dates, "closes": closes, "volumes": volumes}


# ---------- iron condor ----------

def test_build_iron_condor_row_returns_ordered_four_leg_row():
    entry = make_entry()
    setup = make_setup(entry, condor_chain())
    row = module.build_iron_condor_row(setup)

    assert row is not None
    assert row["strategy"] == "iron_condor"
    assert row["long_put"]["strike"] < row["short_put"]["strike"] < row["price"] < row["short_call"]["strike"] < row["long_call"]["strike"]
    assert row["metrics"]["net_credit"] > 0
    assert row["metrics"]["max_loss"] > 0


def test_build_iron_condor_row_returns_none_when_a_leg_is_missing():
    entry = make_entry()
    # No puts at all -> short_put/long_put selection fails.
    chain = FakeChain(condor_chain().calls.rows, [])
    setup = make_setup(entry, chain)
    assert module.build_iron_condor_row(setup) is None


def test_build_iron_condor_row_returns_none_when_strikes_out_of_order():
    entry = make_entry()
    # Only one call strike available: short_call and long_call both resolve to it, so the
    # strict "long_call > short_call" ordering guard trips.
    calls = [contract(strike=108, bid=2.00, ask=2.20, iv=0.30)]
    puts = [
        contract(strike=93, bid=1.95, ask=2.15, iv=0.30),
        contract(strike=89, bid=0.55, ask=0.75, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_condor_row(setup) is None


def test_build_iron_condor_row_returns_none_when_net_credit_non_positive():
    entry = make_entry()
    # Long legs priced richer than short legs -> net credit goes negative.
    calls = [
        contract(strike=108, bid=0.50, ask=0.70, iv=0.30),   # short call, cheap (wrong)
        contract(strike=113, bid=3.00, ask=3.20, iv=0.30),   # long call, expensive (wrong)
    ]
    puts = [
        contract(strike=93, bid=0.50, ask=0.70, iv=0.30),
        contract(strike=89, bid=3.00, ask=3.20, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_condor_row(setup) is None


def test_iron_condor_probability_in_range_lands_in_zero_one():
    entry = make_entry()
    setup = make_setup(entry, condor_chain())
    row = module.build_iron_condor_row(setup)
    probability = row["metrics"]["probability_in_range"]
    assert probability is not None
    assert 0 <= probability <= 1


# ---------- straddle ----------

def test_build_straddle_row_returns_two_leg_row_with_matching_strikes():
    entry = make_entry()
    setup = make_setup(entry, straddle_chain())
    row = module.build_straddle_row(setup)

    assert row is not None
    assert row["strategy"] == "straddle"
    assert row["call"]["strike"] == row["put"]["strike"] == 100
    assert row["metrics"]["cost"] > 0


def test_build_straddle_row_returns_none_without_matching_strike_in_both_frames():
    entry = make_entry()
    calls = [contract(strike=100, bid=3.00, ask=3.20, iv=0.35)]
    puts = [contract(strike=105, bid=2.90, ask=3.10, iv=0.35)]  # no 100-strike put, no 105-strike call
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_straddle_row(setup) is None


def test_build_straddle_row_returns_none_when_cost_non_positive():
    entry = make_entry()
    calls = [contract(strike=100, bid=0, ask=0, iv=0.35, open_interest=0)]
    puts = [contract(strike=100, bid=0, ask=0, iv=0.35, open_interest=0)]
    setup = make_setup(entry, FakeChain(calls, puts))
    # contract_liquidity itself rejects a zero bid/ask, so select_contract returns None first.
    assert module.build_straddle_row(setup) is None


def test_straddle_probability_of_profit_lands_in_zero_one():
    entry = make_entry()
    setup = make_setup(entry, straddle_chain())
    row = module.build_straddle_row(setup)
    probability = row["metrics"]["probability_of_profit"]
    assert probability is not None
    assert 0 <= probability <= 1


# ---------- build_rows ----------

def test_build_rows_splits_by_strategy_availability(monkeypatch):
    both = make_entry(ticker="BOTH")
    condor_only = make_entry(ticker="CONDORONLY")
    neither = make_entry(ticker="NEITHER")
    per_ticker = {
        "BOTH": fake_history(),
        "CONDORONLY": fake_history(),
        "NEITHER": fake_history(),
    }
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "BOTH": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: combined_chain()}),
        "CONDORONLY": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: condor_chain()}),
        "NEITHER": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], [])}),
    })

    condor_rows, straddle_rows = module.build_rows([both, condor_only, neither], fake_yf, as_of=TODAY)

    condor_tickers = {row["ticker"] for row in condor_rows}
    straddle_tickers = {row["ticker"] for row in straddle_rows}
    assert "BOTH" in condor_tickers and "BOTH" in straddle_tickers
    assert "CONDORONLY" in condor_tickers
    assert "CONDORONLY" not in straddle_tickers
    assert "NEITHER" not in condor_tickers
    assert "NEITHER" not in straddle_tickers


# ---------- score_rows ----------

def test_score_rows_gates_small_cap_for_iron_condor_shaped_row():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"credit_efficiency": 0.5, "probability_in_range": 0.6, "liquidity": 2.0}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"credit_efficiency": 0.4, "probability_in_range": 0.5, "liquidity": 1.0}},
    ]
    scored = module.score_rows(rows, module.IRON_CONDOR_WEIGHTS)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_score_rows_gates_small_cap_for_straddle_shaped_row():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": -0.9, "probability_of_profit": 0.5, "liquidity": 2.0}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"iv_value": -0.5, "probability_of_profit": 0.4, "liquidity": 1.0}},
    ]
    scored = module.score_rows(rows, module.STRADDLE_WEIGHTS)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


# ---------- to_result ----------

def test_to_result_iron_condor_has_four_legs_in_expected_order():
    entry = make_entry()
    setup = make_setup(entry, condor_chain())
    row = module.build_iron_condor_row(setup)
    row.update({"eligibility": True, "reason_codes": []})
    result = module.to_result(1, row)

    assert len(result["legs"]) == 4
    actions_and_types = [(leg["action"], leg["option_type"]) for leg in result["legs"]]
    assert actions_and_types == [
        ("buy", "put"), ("sell", "put"), ("sell", "call"), ("buy", "call"),
    ]


def test_to_result_straddle_has_two_buy_legs():
    entry = make_entry()
    setup = make_setup(entry, straddle_chain())
    row = module.build_straddle_row(setup)
    row.update({"eligibility": True, "reason_codes": []})
    result = module.to_result(1, row)

    assert len(result["legs"]) == 2
    assert all(leg["action"] == "buy" for leg in result["legs"])
    assert {leg["option_type"] for leg in result["legs"]} == {"call", "put"}


# ---------- run() ----------

def test_run_publishes_scored_results_with_both_strategies(monkeypatch):
    universe = [
        {"ticker": "BOTH", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8},
        {"ticker": "CONDORONLY", "sector": "Technology", "market_cap": 4e9, "score": 60, "confidence": 0.7},
    ]
    per_ticker = {"BOTH": wobble_history(), "CONDORONLY": fake_history()}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "BOTH": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: combined_chain()}),
        "CONDORONLY": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: condor_chain()}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_ADVANCED_OPTIONS_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/advanced-strategies.json"] == result
    strategies_present = {row["strategy"] for row in result["results"]}
    assert strategies_present == {"iron_condor", "straddle"}

    condor_ranks = [row["rank"] for row in result["results"] if row["strategy"] == "iron_condor"]
    straddle_ranks = [row["rank"] for row in result["results"] if row["strategy"] == "straddle"]
    assert condor_ranks == sorted(condor_ranks)
    assert condor_ranks[0] == 1
    assert straddle_ranks == sorted(straddle_ranks)
    assert straddle_ranks[0] == 1


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_ADVANCED_OPTIONS_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_ADVANCED_OPTIONS_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/advanced-strategies.json"] == result
