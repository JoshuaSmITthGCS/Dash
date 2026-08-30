import math
import sys
from datetime import date, timedelta

import pytest

import build_iron_butterfly_screen as module
import iv_archive


@pytest.fixture(autouse=True)
def _isolated_iv_archive(tmp_path, monkeypatch):
    """build_iron_butterfly_row() calls iv_archive.iv_percentile() on every call in this
    module - isolate every test in this file from the real pipeline/data/iv_archive/
    directory, the same way test_build_options_strategies.py isolates ARCHIVE_DIR/MANIFEST.
    This screen only ever READS iv_archive (see module docstring), but iv_percentile()
    still touches disk via load_series(), so the isolation matters here too.
    """
    archive_dir = tmp_path / "iv_archive"
    monkeypatch.setattr(iv_archive, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(iv_archive, "MANIFEST", str(archive_dir / "archive_manifest.json"))


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


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def butterfly_chain(price=100):
    """Calls/puts frames whose Black-Scholes deltas (iv=0.30/0.35, dte=30) give an ATM
    contract right at 100 on both sides, plus a long call/put wing near the screen's 0.08
    target delta: call 113 -> delta ~0.084, put 89 -> delta ~-0.081.
    """
    calls = [
        contract(strike=100, bid=3.08, ask=3.12, iv=0.35),   # ATM (short) call
        contract(strike=113, bid=0.63, ask=0.67, iv=0.30),   # long call wing
    ]
    puts = [
        contract(strike=100, bid=2.98, ask=3.02, iv=0.35),   # ATM (short) put
        contract(strike=89, bid=0.63, ask=0.67, iv=0.30),    # long put wing
    ]
    return FakeChain(calls, puts)


def make_entry(ticker="AAA", market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


def make_setup(entry, chain, price=100, dte=30, trend=0.05, realized=0.25, history_sessions=40,
               generated_at=None, as_of=None, closes=None):
    closes = closes if closes is not None else [price] * history_sessions
    return (entry["ticker"], price, dte, EXPIRATION, trend, realized, chain, entry, history_sessions,
            generated_at, as_of, closes)


def wobble_history():
    """40 sessions ending at close=100 with a nonzero final-week wobble - a perfectly flat
    fake_history() makes realized_volatility_20d() == 0.0 (falsy), which starves any factor
    that depends on a real ratio. Mirrors build_advanced_options_screen.py's wobble_history.
    """
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(40)]
    closes = [100.0] * 38 + [102.0, 100.0]
    volumes = [1_000_000] * 40
    return {"dates": dates, "closes": closes, "volumes": volumes}


# ---------- build_iron_butterfly_row ----------

def test_build_iron_butterfly_row_returns_four_leg_row_with_matching_short_strikes():
    entry = make_entry()
    setup = make_setup(entry, butterfly_chain())
    row = module.build_iron_butterfly_row(setup)

    assert row is not None
    assert row["strategy"] == "iron_butterfly"
    assert row["atm_call"]["strike"] == row["atm_put"]["strike"] == 100
    assert row["long_put"]["strike"] < row["atm_call"]["strike"] < row["long_call"]["strike"]
    assert row["metrics"]["net_credit"] > 0
    assert row["metrics"]["max_loss"] > 0
    assert row["metrics"]["breakeven_up"] == row["atm_call"]["strike"] + row["metrics"]["net_credit"]
    assert row["metrics"]["breakeven_down"] == row["atm_call"]["strike"] - row["metrics"]["net_credit"]


def test_build_iron_butterfly_row_returns_none_when_atm_legs_cannot_be_matched():
    entry = make_entry()
    # Call ATM at 100, put ATM at 105 - neither frame has the other's strike, so the
    # strike-matching fallback (_contract_at_strike) fails on both sides.
    calls = [contract(strike=100, bid=3.00, ask=3.20, iv=0.35)]
    puts = [contract(strike=105, bid=2.90, ask=3.10, iv=0.35)]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_butterfly_row(setup) is None


def test_build_iron_butterfly_row_returns_none_when_a_wing_is_missing():
    entry = make_entry()
    # No long call wing available at all.
    calls = [contract(strike=100, bid=3.08, ask=3.12, iv=0.35)]
    puts = [
        contract(strike=100, bid=2.98, ask=3.02, iv=0.35),
        contract(strike=89, bid=0.63, ask=0.67, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_butterfly_row(setup) is None


def test_build_iron_butterfly_row_returns_none_when_wings_do_not_straddle_atm():
    entry = make_entry()
    # Long call wing strike (95) sits BELOW the ATM strike (100) - fails the
    # long_call > atm_strike > long_put ordering guard.
    calls = [
        contract(strike=100, bid=3.08, ask=3.12, iv=0.35),
        contract(strike=95, bid=5.50, ask=5.70, iv=0.30),
    ]
    puts = [
        contract(strike=100, bid=2.98, ask=3.02, iv=0.35),
        contract(strike=89, bid=0.63, ask=0.67, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_butterfly_row(setup) is None


def test_build_iron_butterfly_row_returns_none_when_net_credit_non_positive():
    entry = make_entry()
    # Wing legs priced richer than the ATM legs -> net credit goes negative.
    calls = [
        contract(strike=100, bid=0.50, ask=0.70, iv=0.35),   # ATM, cheap (wrong)
        contract(strike=113, bid=3.00, ask=3.20, iv=0.30),   # wing, expensive (wrong)
    ]
    puts = [
        contract(strike=100, bid=0.50, ask=0.70, iv=0.35),
        contract(strike=89, bid=3.00, ask=3.20, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_butterfly_row(setup) is None


def test_build_iron_butterfly_row_returns_none_when_max_loss_non_positive():
    entry = make_entry()
    # Net credit exceeds even the wider wing width -> max_loss <= 0.
    calls = [
        contract(strike=100, bid=9.00, ask=9.20, iv=0.35),
        contract(strike=101, bid=0.05, ask=0.10, iv=0.30),
    ]
    puts = [
        contract(strike=100, bid=9.00, ask=9.20, iv=0.35),
        contract(strike=99, bid=0.05, ask=0.10, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    assert module.build_iron_butterfly_row(setup) is None


def test_iron_butterfly_probability_in_range_lands_in_zero_one():
    entry = make_entry()
    setup = make_setup(entry, butterfly_chain())
    row = module.build_iron_butterfly_row(setup)
    probability = row["metrics"]["probability_in_range"]
    assert probability is not None
    assert 0 <= probability <= 1


def test_build_iron_butterfly_row_uses_strike_matching_fallback_when_atm_legs_differ():
    entry = make_entry()
    # select_contract independently picks call=100 (closer to spot) and put=99 (further):
    # the fallback must re-select the put AT strike 100.
    calls = [
        contract(strike=100, bid=3.08, ask=3.12, iv=0.35),
        contract(strike=113, bid=0.63, ask=0.67, iv=0.30),
    ]
    puts = [
        contract(strike=100, bid=2.98, ask=3.02, iv=0.35),
        contract(strike=99, bid=3.50, ask=3.60, iv=0.35),  # closer to spot than 100 but must lose out
        contract(strike=89, bid=0.63, ask=0.67, iv=0.30),
    ]
    setup = make_setup(entry, FakeChain(calls, puts))
    row = module.build_iron_butterfly_row(setup)
    assert row is not None
    assert row["atm_call"]["strike"] == row["atm_put"]["strike"] == 100


# ---------- build_rows ----------

def test_build_rows_collects_only_qualifying_tickers(monkeypatch):
    good = make_entry(ticker="GOOD")
    bad = make_entry(ticker="BAD")
    per_ticker = {"GOOD": fake_history(), "BAD": fake_history()}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "GOOD": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: butterfly_chain()}),
        "BAD": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain([], [])}),
    })

    rows = module.build_rows([good, bad], fake_yf, as_of=TODAY)

    tickers = {row["ticker"] for row in rows}
    assert tickers == {"GOOD"}


# ---------- score_rows ----------

def test_score_rows_gates_small_cap():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"credit_efficiency": 0.5, "probability_in_range": 0.6, "liquidity": 2.0}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"credit_efficiency": 0.4, "probability_in_range": 0.5, "liquidity": 1.0}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_score_rows_gates_insufficient_history():
    rows = [
        {"ticker": "AAA", "price": 50, "market_cap": 5e9, "realized_volatility_20d": None,
         "factors": {"credit_efficiency": 0.5, "probability_in_range": 0.6, "liquidity": 2.0}},
    ]
    scored = module.score_rows(rows)
    assert scored[0]["eligibility"] is False
    assert "INSUFFICIENT_HISTORY" in scored[0]["reason_codes"]


# ---------- to_result ----------

def test_to_result_has_four_legs_in_expected_order():
    entry = make_entry()
    setup = make_setup(entry, butterfly_chain())
    row = module.build_iron_butterfly_row(setup)
    row.update({"eligibility": True, "reason_codes": []})
    result = module.to_result(1, row)

    assert len(result["legs"]) == 4
    actions_and_types = [(leg["action"], leg["option_type"]) for leg in result["legs"]]
    assert actions_and_types == [
        ("buy", "put"), ("sell", "put"), ("sell", "call"), ("buy", "call"),
    ]
    strikes = [leg["strike"] for leg in result["legs"]]
    assert strikes == sorted(strikes)
    # Both "sell" legs share the same (ATM) strike - the defining mechanical trait of a
    # butterfly versus a condor.
    assert result["legs"][1]["strike"] == result["legs"][2]["strike"]


# ---------- run() ----------

def test_run_publishes_scored_results(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60, "confidence": 0.7},
    ]
    per_ticker = {"AAA": wobble_history(), "BBB": fake_history()}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: butterfly_chain()}),
        "BBB": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: butterfly_chain()}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_IRON_BUTTERFLY_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/iron-butterflies.json"] == result
    assert all(row["strategy"] == "iron_butterfly" for row in result["results"])
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_IRON_BUTTERFLY_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_IRON_BUTTERFLY_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/iron-butterflies.json"] == result


def test_run_reports_unavailable_when_yfinance_missing(monkeypatch):
    monkeypatch.setenv("ENABLE_IRON_BUTTERFLY_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: {"research": [make_entry()]})
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))
    monkeypatch.setitem(sys.modules, "yfinance", None)

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "YFINANCE_UNAVAILABLE"


# ---------- backtest_iron_butterfly ----------

def wiggly_closes(n, base=100.0, amplitude=2.5):
    """Non-flat deterministic price series - flat closes make realized_volatility_20d()
    return 0.0 (falsy), which silently skips every period in the backtest loop. amplitude=2.5
    (rather than build_advanced_options_screen.py's 2.0) is deliberate: at the resulting
    entry-day realized vol, synthetic_chain's per-strike rounding lands select_contract's
    tightest-spread pick close enough to spot on both the call and put side that the
    ATM-matching fallback resolves to a strike inside the wings for BOTH walk-forward
    periods below - a lower amplitude can (by the same rounding quirk) land the naive ATM
    pick outside the wings on one side, which correctly returns None for that period as an
    unbuildable structure, but leaves this test with only one trade to assert against.
    """
    return [round(base + amplitude * math.sin(index * 0.9), 4) for index in range(n)]


def backtest_history_two_periods():
    """84 sessions -> exactly two walk-forward periods at (target_dte=30, lookback=21):
    entry=21/expiry=42 and entry=42/expiry=63 (session_step = round(30*5/7) == 21).

    Period 1 settles a hair away from its entry price (100.0 -> 100.1): comfortably inside
    the profitable band around atm_strike, near max profit. Period 2 settles at less than a
    third of its entry price (100.1 -> 30.0): a crash comfortably beyond the put-side long
    wing (synthetic_chain only ever generates strikes out to +/-40%), driving the trade to
    (near) its max loss.
    """
    closes = wiggly_closes(84)
    closes[21] = 100.0   # period 1 entry
    closes[42] = 100.1   # period 1 expiry / period 2 entry - tiny move
    closes[63] = 30.0    # period 2 expiry - crash, well beyond the long put strike
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(84)]
    volumes = [1_000_000] * 84
    return {"dates": dates, "closes": closes, "volumes": volumes}


def too_short_history():
    closes = wiggly_closes(15)  # < lookback (21) -> walk_periods() yields no periods at all
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(15)]
    volumes = [1_000_000] * 15
    return {"dates": dates, "closes": closes, "volumes": volumes}


def period_returns_from_equity_curve(equity_curve):
    return [equity_curve[index] / equity_curve[index - 1] - 1 for index in range(1, len(equity_curve))]


def test_backtest_iron_butterfly_returns_performance_stats_shape_with_trades(monkeypatch):
    universe = [make_entry(ticker="AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))

    stats = module.backtest_iron_butterfly(universe, yf=None)

    assert stats is not None
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in stats
    assert stats["num_trades"] > 0
    assert len(stats["equity_curve"]) == stats["num_trades"] + 1


def test_backtest_iron_butterfly_spot_checks_settlement_scenarios(monkeypatch):
    universe = [make_entry(ticker="AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))

    stats = module.backtest_iron_butterfly(universe, yf=None)
    assert stats["num_trades"] == 2

    period_returns = period_returns_from_equity_curve(stats["equity_curve"])
    near_atm_return, beyond_wing_return = period_returns

    # Settling near the ATM strike -> near max profit.
    assert near_atm_return > 0
    # Settling far beyond the wing -> capped, near-max loss (bounded at -1 minus fees),
    # scaled down to roughly -0.05 by performance_stats' 5%-of-account position weighting.
    assert beyond_wing_return < -0.5 * 0.05


def test_backtest_iron_butterfly_returns_none_when_history_too_short(monkeypatch):
    universe = [make_entry(ticker="AAA"), make_entry(ticker="BBB")]
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"AAA": too_short_history(), "BBB": too_short_history()}))
    assert module.backtest_iron_butterfly(universe, yf=None) is None


def test_backtest_iron_butterfly_skips_entries_without_a_ticker(monkeypatch):
    universe = [{"sector": "Technology"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({}))
    assert module.backtest_iron_butterfly(universe, yf=None) is None


# ---------- run_backtest() ----------

def test_run_backtest_publishes_end_to_end(monkeypatch):
    universe = [{"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "success"
    assert saved["screens/iron-butterflies-backtest.json"] == result
    assert result["backtest"]["num_trades"] > 0


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/iron-butterflies-backtest.json"] == result


def test_run_backtest_ignores_the_live_screen_opt_in_flag(monkeypatch):
    universe = [{"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 70, "confidence": 0.8}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))
    monkeypatch.setattr(module, "load_json", lambda name: {"research": universe})
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)

    # No ENABLE_IRON_BUTTERFLY_SCREEN set at all - unlike run(), run_backtest() must still execute.
    monkeypatch.delenv("ENABLE_IRON_BUTTERFLY_SCREEN", raising=False)
    result = module.run_backtest()
    assert result is not None
    assert result["status"] == "success"

    # Even explicitly disabled, run_backtest() has no flag check to honor.
    monkeypatch.setenv("ENABLE_IRON_BUTTERFLY_SCREEN", "0")
    result = module.run_backtest()
    assert result is not None
    assert result["status"] == "success"
