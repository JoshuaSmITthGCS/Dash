import sys
from datetime import date, timedelta

import pytest

import build_jade_lizard_screen as module
import iv_archive
from backtest_common import SyntheticFrame


@pytest.fixture(autouse=True)
def _isolated_iv_archive(tmp_path, monkeypatch):
    """build_row() reads iv_archive.iv_percentile() on every call in this module - isolate
    every test in this file from the real pipeline/data/iv_archive/ directory, the same way
    test_build_options_strategies.py isolates iv_archive's ARCHIVE_DIR/MANIFEST. MANIFEST is
    derived from ARCHIVE_DIR at import time, so it needs its own monkeypatch too.
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
EXPIRATION = "2024-03-31"  # 30 days out from TODAY, matches TARGET_DAYS_TO_EXPIRATION


def contract(strike, bid, ask, open_interest=200, iv=0.30, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def universe_entry(ticker, market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


# Strikes chosen so their Black-Scholes deltas (iv=0.30, dte=30, price=100) land close to
# this screen's own target deltas: put@96 -> delta ~-0.302 (target 0.30), call@108 ->
# delta ~0.197 (target 0.18, short call), call@113 -> delta ~0.084 (target 0.08, long
# call) - same strikes build_advanced_options_screen's condor_chain() fixture already uses
# for its own 0.18/0.08 wings, reused here for the same reason.
#
# Premiums are set explicitly (not derived from the deltas above) so each fixture can
# freely dial net_credit up or down relative to call_spread_width (5 = 113 - 108) without
# touching strike/delta selection at all.

def jade_lizard_chain():
    """net_credit (5.50) >= call_spread_width (5) - a genuine, publishable jade lizard.

    Bid/ask spreads are kept to $0.06 on every leg (well under contract_liquidity's
    MAXIMUM_ABSOLUTE_SPREAD of $0.10) so the cheap long call - relatively wide on a
    PERCENTAGE basis at a $0.50 mid - still clears the liquidity gate on the absolute-
    dollar branch, same as a real cheap deep-OTM contract would.
    """
    calls = [
        contract(strike=108, bid=2.97, ask=3.03),   # short call, mid 3.00
        contract(strike=113, bid=0.47, ask=0.53),   # long call, mid 0.50
    ]
    puts = [
        contract(strike=96, bid=2.97, ask=3.03),    # put, mid 3.00
    ]
    return FakeChain(calls, puts)


def insufficient_credit_chain():
    """Same strikes as jade_lizard_chain(), but net_credit (2.33) < call_spread_width (5) -
    every gate before the defining constraint passes; only that constraint fails.
    """
    calls = [
        contract(strike=108, bid=0.87, ask=0.93),   # short call, mid 0.90
        contract(strike=113, bid=0.27, ask=0.33),   # long call, mid 0.30
    ]
    puts = [
        contract(strike=96, bid=1.70, ask=1.76),    # put, mid 1.73
    ]
    return FakeChain(calls, puts)


def non_positive_credit_chain():
    """Long call priced richer than the rest of the structure -> net_credit goes negative."""
    calls = [
        contract(strike=108, bid=0.07, ask=0.13),   # short call, cheap (wrong), mid 0.10
        contract(strike=113, bid=4.97, ask=5.03),   # long call, expensive (wrong), mid 5.00
    ]
    puts = [
        contract(strike=96, bid=0.07, ask=0.13),    # put, mid 0.10
    ]
    return FakeChain(calls, puts)


def single_call_strike_chain():
    """Only one call strike on offer: short_call and long_call both resolve to it, so the
    strict "long_call.strike > short_call.strike" ordering guard trips. The put leg is a
    normal, otherwise-qualifying contract, isolating the failure to the call-side ordering.
    """
    calls = [contract(strike=108, bid=2.97, ask=3.03)]
    puts = [contract(strike=96, bid=2.97, ask=3.03)]
    return FakeChain(calls, puts)


# ---------- build_row ----------

def test_build_row_returns_valid_jade_lizard_with_correct_ordering_and_math(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["put"]["strike"] < row["short_call"]["strike"] < row["long_call"]["strike"]
    assert row["price"] < row["short_call"]["strike"]
    assert row["metrics"]["net_credit"] == 5.5
    assert row["metrics"]["call_spread_width"] == 5.0
    assert row["metrics"]["net_credit"] >= row["metrics"]["call_spread_width"]
    assert row["metrics"]["effective_cost_basis"] == 96 - 5.5
    assert row["capital_required"] == 96 * 100


def test_build_row_returns_none_when_net_credit_non_positive(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: non_positive_credit_chain()})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_net_credit_below_call_spread_width(monkeypatch):
    """The single most important gate in this module: a candidate that collects a real,
    positive credit but LESS than the call spread's width still carries real upside risk,
    so it must not publish as a jade lizard.
    """
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: insufficient_credit_chain()})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_call_strikes_out_of_order(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: single_call_strike_chain()})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_put_leg_missing(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    chain = FakeChain(jade_lizard_chain().calls.rows, [])  # no puts at all
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: chain})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_call_legs_missing(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    chain = FakeChain([], jade_lizard_chain().puts.rows)  # no calls at all
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: chain})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    entry = universe_entry("THIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    assert module.build_row(entry, FakeYf({}), as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    entry = universe_entry("NOOPT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})
    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    entry = universe_entry("SHORTDATED")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"SHORTDATED": fake_history()}))
    # Same-day expiration (0 days out) - below MIN_DAYS_TO_EXPIRATION (15).
    fake_yf = FakeYf({"SHORTDATED": FakeTicker(options=["2024-03-01"])})
    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_probability_otm_lands_in_zero_one(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)
    probability = row["metrics"]["probability_otm"]
    assert probability is not None
    assert 0 <= probability <= 1


def test_build_row_metrics_carry_the_full_published_field_set(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)
    for field in ("net_credit", "collateral", "effective_cost_basis", "annualized_yield",
                  "expected_value_pct", "probability_otm", "call_spread_width",
                  "suggested_position_pct", "iv_skew", "put_call_oi_ratio",
                  "realized_volatility_percentile", "iv_percentile", "single_expiration_gex",
                  "news_sentiment", "research_confidence"):
        assert field in row["metrics"]


# ---------- build_rows ----------

def test_build_rows_skips_tickers_without_a_qualifying_jade_lizard(monkeypatch):
    qualifies = universe_entry("QUALIFIES")
    fails = universe_entry("FAILS")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({
        "QUALIFIES": fake_history(), "FAILS": fake_history(),
    }))
    fake_yf = FakeYf({
        "QUALIFIES": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()}),
        "FAILS": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: insufficient_credit_chain()}),
    })

    rows = module.build_rows([qualifies, fails], fake_yf, as_of=TODAY)

    tickers = {row["ticker"] for row in rows}
    assert tickers == {"QUALIFIES"}


# ---------- score_rows ----------

def test_score_rows_gates_small_caps():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.30, "probability_otm": 0.8, "liquidity": 2.0}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.10, "probability_otm": 0.6, "liquidity": 0.5}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]


def test_score_rows_gates_low_price():
    rows = [
        {"ticker": "OK", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.2, "probability_otm": 0.7, "liquidity": 1.0}},
        {"ticker": "PENNY", "price": 1, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.2, "probability_otm": 0.7, "liquidity": 1.0}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["PENNY"]["eligibility"] is False
    assert "MINIMUM_PRICE" in by_ticker["PENNY"]["reason_codes"]


def test_score_rows_gates_insufficient_history():
    rows = [
        {"ticker": "OK", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.2, "probability_otm": 0.7, "liquidity": 1.0}},
        {"ticker": "NEW", "price": 50, "market_cap": 5e9, "realized_volatility_20d": None,
         "factors": {"expected_value_pct": 0.2, "probability_otm": 0.7, "liquidity": 1.0}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["NEW"]["eligibility"] is False
    assert "INSUFFICIENT_HISTORY" in by_ticker["NEW"]["reason_codes"]


# ---------- to_result ----------

def test_to_result_has_three_legs_sell_put_sell_call_buy_call(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()})})
    row = module.build_row(entry, fake_yf, as_of=TODAY)
    row.update({"eligibility": True, "reason_codes": []})

    result = module.to_result(1, row)

    assert len(result["legs"]) == 3
    actions_and_types = [(leg["action"], leg["option_type"]) for leg in result["legs"]]
    assert actions_and_types == [("sell", "put"), ("sell", "call"), ("buy", "call")]
    assert result["legs"][0]["strike"] == 96
    assert result["legs"][1]["strike"] == 108
    assert result["legs"][2]["strike"] == 113
    assert result["metrics"] == row["metrics"]


# ---------- run() ----------

def test_run_publishes_scored_results(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: jade_lizard_chain()})})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_JADE_LIZARD_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/jade-lizards.json"] == result
    assert len(result["results"]) == 1
    assert result["results"][0]["ticker"] == "AAA"
    assert result["window"] == {
        "min_days_to_expiration": module.MIN_DAYS_TO_EXPIRATION,
        "max_days_to_expiration": module.MAX_DAYS_TO_EXPIRATION,
        "target_days_to_expiration": module.TARGET_DAYS_TO_EXPIRATION,
        "put_target_delta": module.PUT_TARGET_DELTA,
        "short_call_target_delta": module.SHORT_CALL_TARGET_DELTA,
        "long_call_target_delta": module.LONG_CALL_TARGET_DELTA,
    }


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_JADE_LIZARD_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_JADE_LIZARD_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/jade-lizards.json"] == result


def test_run_reports_unavailable_when_yfinance_missing(monkeypatch):
    monkeypatch.setenv("ENABLE_JADE_LIZARD_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: {"research": [universe_entry("AAA")]})
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))
    monkeypatch.setitem(sys.modules, "yfinance", None)

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "YFINANCE_UNAVAILABLE"
    assert saved["screens/jade-lizards.json"] == result


def test_run_reports_unavailable_with_no_qualifying_contracts(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    # A chain that fails the defining net_credit >= call_spread_width constraint - no
    # ticker in the universe produces a publishable row.
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: insufficient_credit_chain()})})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_JADE_LIZARD_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: {"research": universe})
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_QUALIFYING_CONTRACTS"
    assert saved["screens/jade-lizards.json"] == result


# ---------- backtest ----------

def wiggly_closes(n, base=100.0, amplitude=2.0):
    """Non-flat deterministic price series - flat closes make realized_volatility_20d()
    return 0.0 (falsy), which silently skips every period in backtest_universe.
    """
    import math
    return [round(base + amplitude * math.sin(index * 0.9), 4) for index in range(n)]


def backtest_history_two_periods():
    """84 sessions -> exactly two walk-forward periods at (target_dte=30, lookback=21):
    entry=21/expiry=42 and entry=42/expiry=63 (session_step = round(30*5/7) == 21).

    Both entries sit at 100.0/100.1 so the FAKE synthetic chain below (whose strikes are
    fixed dollar amounts, not derived from these prices) keeps selecting the same three
    legs at deltas close to this screen's own targets on both entries. Period 1 settles
    just above the put strike (no assignment, full credit kept); period 2 settles well
    below it (assigned, a real downside loss) - the same "one clean win, one real loss"
    shape build_cash_secured_put_screen's own backtest tests use.
    """
    closes = wiggly_closes(84)
    closes[21] = 100.0    # period 1 entry
    closes[42] = 100.1    # period 1 expiry / period 2 entry
    closes[63] = 70.0     # period 2 expiry - well below the 96 put strike
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(84)]
    volumes = [1_000_000] * 84
    return {"dates": dates, "closes": closes, "volumes": volumes}


def too_short_history():
    closes = wiggly_closes(15)  # < lookback (21) -> walk_periods() yields no periods at all
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(15)]
    volumes = [1_000_000] * 15
    return {"dates": dates, "closes": closes, "volumes": volumes}


def fake_synthetic_chain_factory():
    """Replaces backtest_common.synthetic_chain for these tests only.

    Under a single flat implied volatility (no skew), this screen's own defining
    constraint - net_credit >= call_spread_width, at these specific target deltas
    (0.30 put / 0.18 short call / 0.08 long call) - is structurally very hard to clear
    (checked analytically: the achievable credit/width ratio tops out well under 1 across
    a wide sweep of iv/dte/price combinations, since it takes a real put-side implied-vol
    richness - the same reverse skew iv_skew()'s own docstring describes - to fund a
    loss-free call spread this wide). That richness is exactly what a flat, single-iv
    synthetic chain cannot express (backtest_common.synthetic_chain prices both sides off
    one iv value), so this fake stands in for it here: fixed strikes/premiums (mirroring
    jade_lizard_chain() above) that DO clear the constraint, so backtest_universe's
    aggregation/PnL/settlement mechanics can be verified end-to-end. Production code is
    untouched - run_backtest() still uses the real, disclosed-flat-vol synthetic_chain,
    and will legitimately publish very few (or zero) backtested trades as a result; that
    is a real, stated limitation of this specific screen's backtest, not a bug.
    """
    calls = [
        contract(strike=108, bid=2.97, ask=3.03),   # short call, mid 3.00
        contract(strike=113, bid=0.47, ask=0.53),   # long call, mid 0.50
    ]
    puts = [
        contract(strike=96, bid=2.97, ask=3.03),    # put, mid 3.00
    ]

    def _synthetic_chain(price, iv, dte):
        return SyntheticFrame(calls), SyntheticFrame(puts)

    return _synthetic_chain


def test_backtest_universe_returns_performance_stats_shape_with_trades(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setattr(module, "synthetic_chain", fake_synthetic_chain_factory())

    stats = module.backtest_universe(universe, yf=None)

    assert stats is not None
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in stats
    assert stats["num_trades"] == 2
    assert len(stats["equity_curve"]) == stats["num_trades"] + 1


def test_backtest_universe_spot_checks_settlement_scenarios(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setattr(module, "synthetic_chain", fake_synthetic_chain_factory())

    stats = module.backtest_universe(universe, yf=None)
    equity = stats["equity_curve"]
    period_returns = [equity[index] / equity[index - 1] - 1 for index in range(1, len(equity))]
    otm_return, assigned_return = period_returns

    # Settling above the put strike -> full credit kept, no assignment -> a gain.
    assert otm_return > 0
    # Settling well below the put strike -> assigned, a real downside loss.
    assert assigned_return < 0


def test_backtest_universe_returns_none_when_history_too_short(monkeypatch):
    universe = [universe_entry("AAA"), universe_entry("BBB")]
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"AAA": too_short_history(), "BBB": too_short_history()}))
    monkeypatch.setattr(module, "synthetic_chain", fake_synthetic_chain_factory())
    assert module.backtest_universe(universe, yf=None) is None


def test_backtest_universe_skips_entries_without_a_ticker(monkeypatch):
    universe = [{"sector": "Technology"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({}))
    assert module.backtest_universe(universe, yf=None) is None


def test_run_backtest_publishes_success_end_to_end(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setattr(module, "synthetic_chain", fake_synthetic_chain_factory())
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "success"
    assert saved["screens/jade-lizards-backtest.json"] == result
    backtest = result["backtest"]
    for key in ("num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "average_pnl_per_trade", "equity_curve"):
        assert key in backtest
    assert backtest["num_trades"] > 0
    assert result["window"] == {
        "min_days_to_expiration": module.MIN_DAYS_TO_EXPIRATION,
        "max_days_to_expiration": module.MAX_DAYS_TO_EXPIRATION,
        "target_days_to_expiration": module.TARGET_DAYS_TO_EXPIRATION,
        "put_target_delta": module.PUT_TARGET_DELTA,
        "short_call_target_delta": module.SHORT_CALL_TARGET_DELTA,
        "long_call_target_delta": module.LONG_CALL_TARGET_DELTA,
    }


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/jade-lizards-backtest.json"] == result


def test_run_backtest_ignores_the_live_screen_opt_in_flag(monkeypatch):
    universe = [universe_entry("AAA")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": backtest_history_two_periods()}))
    monkeypatch.setattr(module, "synthetic_chain", fake_synthetic_chain_factory())
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))
    monkeypatch.setattr(module, "load_json", lambda name: {"research": universe})
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)

    # No ENABLE_JADE_LIZARD_SCREEN set at all - unlike run(), run_backtest() must still execute.
    monkeypatch.delenv("ENABLE_JADE_LIZARD_SCREEN", raising=False)
    result = module.run_backtest()
    assert result is not None
    assert result["status"] == "success"

    # Even explicitly disabled, run_backtest() has no flag check to honor.
    monkeypatch.setenv("ENABLE_JADE_LIZARD_SCREEN", "0")
    result = module.run_backtest()
    assert result is not None
    assert result["status"] == "success"
