import sys
from datetime import date, timedelta

import pytest

import build_pmcc_screen as module
import iv_archive


@pytest.fixture(autouse=True)
def _isolated_iv_archive(tmp_path, monkeypatch):
    """build_row() calls iv_archive.iv_percentile(ticker) on every call - isolate every test
    in this file from the real pipeline/data/iv_archive/ directory, the same way
    test_build_options_strategies.py isolates its own iv_archive-writing tests. MANIFEST is
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
    """Counts option_chain() calls so tests can confirm the whole point of this module: TWO
    chain fetches per ticker (one per expiration), not one reused for both legs. Already
    supports being asked for option_chain(expiration) with two different expiration strings
    via the `chains: {expiration: FakeChain}` dict - no changes needed for a two-fetch screen.
    """

    def __init__(self, options=None, chains=None, raise_on_options=False, raise_on_chain=False):
        self._options = options or []
        self._chains = chains or {}
        self._raise_on_options = raise_on_options
        self._raise_on_chain = raise_on_chain
        self.option_chain_calls = 0

    @property
    def options(self):
        if self._raise_on_options:
            raise RuntimeError("boom")
        return self._options

    def option_chain(self, expiration):
        self.option_chain_calls += 1
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


def contract(strike, bid, ask, open_interest=200, iv=0.3, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


TODAY = date(2024, 3, 1)
NEAR_EXPIRATION = "2024-03-31"    # 30 days out - exactly NEAR_TARGET_DAYS_TO_EXPIRATION
LEAPS_EXPIRATION = "2024-11-26"   # 270 days out - exactly LEAPS_TARGET_DAYS_TO_EXPIRATION

# price=100, iv=0.3: call_delta(100, 105, 0.3, 30) ~ 0.300 (near short-call target);
# call_delta(100, 83, 0.3, 270) ~ 0.803 (LEAPS target) - see options_common.call_delta.
# moneyness(105) = +0.05 (within select_by_target_delta's default 0.0-0.35 OTM ceiling);
# moneyness(83) = -0.17 (within this module's explicit LEAPS -0.60/0.0 deep-ITM bounds).
NEAR_SHORT_CALL = contract(strike=105, bid=1.54, ask=1.60, iv=0.3)
LEAPS_LONG_CALL = contract(strike=83, bid=20.02, ask=20.42, iv=0.3)


def universe_entry(ticker, market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


def make_ticker(near_calls=None, near_puts=None, leaps_calls=None, leaps_puts=None,
                near_expiration=NEAR_EXPIRATION, leaps_expiration=LEAPS_EXPIRATION):
    near_calls = near_calls if near_calls is not None else [NEAR_SHORT_CALL]
    leaps_calls = leaps_calls if leaps_calls is not None else [LEAPS_LONG_CALL]
    return FakeTicker(
        options=[near_expiration, leaps_expiration],
        chains={
            near_expiration: FakeChain(near_calls, near_puts or []),
            leaps_expiration: FakeChain(leaps_calls, leaps_puts or []),
        },
    )


# --- build_row -------------------------------------------------------------------------------

def test_build_row_builds_valid_pmcc_with_deep_itm_leaps_and_short_call_above_it(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history()}))
    ticker = make_ticker()
    fake_yf = FakeYf({"AAA": ticker})

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["expiration"] == NEAR_EXPIRATION
    assert row["days_to_expiration"] == 30
    assert row["leaps_expiration"] == LEAPS_EXPIRATION
    assert row["leaps_days_to_expiration"] == 270
    assert row["leaps_call"]["strike"] == 83
    assert row["short_call"]["strike"] == 105
    # LEAPS is deep in-the-money (negative moneyness) and high-delta.
    assert row["leaps_call"]["moneyness"] < 0
    assert row["leaps_call"]["delta"] > 0.7
    # Short call sits above the LEAPS strike, at a moderate delta.
    assert row["short_call"]["strike"] > row["leaps_call"]["strike"]
    assert 0.2 < row["short_call"]["delta"] < 0.4
    # Capital efficiency: PMCC capital required is a small fraction of a real covered call's.
    assert row["capital_required"] < row["price"] * 100
    assert row["metrics"]["net_debit"] > 0
    assert row["metrics"]["max_return_if_assigned_pct"] is not None
    assert row["metrics"]["annualized_premium_yield"] is not None
    # Confirms the whole point of this module: two DIFFERENT expirations were actually
    # fetched, not one reused for both legs.
    assert ticker.option_chain_calls == 2


def test_build_row_returns_none_when_leaps_call_not_found_deep_enough_itm(monkeypatch):
    entry = universe_entry("NOLEAPS")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOLEAPS": fake_history()}))
    # Only an out-of-the-money LEAPS-tenor call is on offer (moneyness +0.10) - outside this
    # module's explicit deep-ITM LEAPS_MONEYNESS_FLOOR/CEILING band (-0.60 to 0.0), so
    # select_by_target_delta has nothing to choose from for the LEAPS leg at all.
    shallow_leaps_call = contract(strike=110, bid=9.0, ask=9.2, iv=0.3)
    ticker = make_ticker(leaps_calls=[shallow_leaps_call])
    fake_yf = FakeYf({"NOLEAPS": ticker})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_short_call_strike_not_above_leaps_strike(monkeypatch):
    entry = universe_entry("INVERTED")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"INVERTED": fake_history()}))
    # Short call strike (80) sits BELOW the LEAPS strike (83) - a degenerate setup this
    # screen must reject rather than publish a nonsensical negative strike spread.
    low_short_call = contract(strike=80, bid=21.0, ask=21.4, iv=0.3)
    ticker = make_ticker(near_calls=[low_short_call])
    fake_yf = FakeYf({"INVERTED": ticker})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    entry = universe_entry("NOOPT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    entry = universe_entry("THIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    fake_yf = FakeYf({"THIN": make_ticker()})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_near_expiration(monkeypatch):
    entry = universe_entry("NONEAR")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NONEAR": fake_history()}))
    # Only the LEAPS-window expiration is on offer - select_expiration() finds nothing in
    # the 15-45 day near window, so the whole row must fail.
    ticker = FakeTicker(options=[LEAPS_EXPIRATION],
                        chains={LEAPS_EXPIRATION: FakeChain([LEAPS_LONG_CALL], [])})
    fake_yf = FakeYf({"NONEAR": ticker})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_leaps_expiration(monkeypatch):
    entry = universe_entry("NOLEAPSEXP")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOLEAPSEXP": fake_history()}))
    # Only the near-window expiration is on offer - select_expiration() finds nothing in the
    # 180-365 day LEAPS window, so the whole row must fail.
    ticker = FakeTicker(options=[NEAR_EXPIRATION],
                        chains={NEAR_EXPIRATION: FakeChain([NEAR_SHORT_CALL], [])})
    fake_yf = FakeYf({"NOLEAPSEXP": ticker})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_excludes_when_near_expiration_spans_earnings(monkeypatch):
    entry = universe_entry("EARN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"EARN": fake_history()}))
    ticker = make_ticker()
    fake_yf = FakeYf({"EARN": ticker})
    # An earnings date inside the NEAR window (before near expiration) must blackout the row,
    # even though it's nowhere near the LEAPS expiration - the whole point of applying the
    # check to the near leg only.
    monkeypatch.setattr(module, "next_earnings_date", lambda *a, **k: date(2024, 3, 15))

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


# --- score_rows ------------------------------------------------------------------------------

def test_score_rows_gates_small_cap_and_ranks_better_row_first():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.30, "liquidity": 2.0, "capital_efficiency": -0.1}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"expected_value_pct": 0.10, "liquidity": 0.5, "capital_efficiency": -0.3}},
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
         "factors": {"expected_value_pct": 0.30, "liquidity": 2.0, "capital_efficiency": -0.1}},
    ]
    scored = module.score_rows(rows)
    assert "INSUFFICIENT_HISTORY" in scored[0]["reason_codes"]
    assert scored[0]["eligibility"] is False


# --- to_result ---------------------------------------------------------------------------------

def test_to_result_produces_two_leg_shape_with_per_leg_expiration_fields():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology",
        "peer_group_label": "Software", "peer_group": "sector:technology",
        "percentile": 80.0, "score": 1.23, "structural_score": 70, "data_coverage": 0.9,
        "price": 100, "trend_20d": 0.05,
        "expiration": NEAR_EXPIRATION, "days_to_expiration": 30,
        "leaps_expiration": LEAPS_EXPIRATION, "leaps_days_to_expiration": 270,
        "capital_required": 1865.0,
        "leaps_call": {"strike": 83, "bid": 20.02, "ask": 20.42, "mid": 20.22, "spread_pct": 0.0198,
                      "implied_volatility": 0.3, "open_interest": 200, "delta": 0.8027},
        "short_call": {"strike": 105, "bid": 1.54, "ask": 1.60, "mid": 1.57, "spread_pct": 0.0382,
                      "implied_volatility": 0.3, "open_interest": 200, "delta": 0.3000},
        "metrics": {"net_debit": 18.65, "max_return_if_assigned_pct": 0.1657},
        "reason_codes": [],
    }

    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["peer_group"] == "Software"
    assert result["expiration"] == NEAR_EXPIRATION
    assert result["days_to_expiration"] == 30
    assert result["capital_required"] == 1865.0
    assert result["metrics"] == row["metrics"]
    assert len(result["legs"]) == 2

    buy_leg, sell_leg = result["legs"]
    assert buy_leg["action"] == "buy"
    assert buy_leg["option_type"] == "call"
    assert buy_leg["strike"] == 83
    assert buy_leg["expiration"] == LEAPS_EXPIRATION
    assert buy_leg["days_to_expiration"] == 270

    assert sell_leg["action"] == "sell"
    assert sell_leg["option_type"] == "call"
    assert sell_leg["strike"] == 105
    assert sell_leg["expiration"] == NEAR_EXPIRATION
    assert sell_leg["days_to_expiration"] == 30


# --- run ---------------------------------------------------------------------------------------

def test_run_publishes_scored_results(monkeypatch):
    universe = [
        universe_entry("AAA"),
        universe_entry("BBB", market_cap=4e9, score=60, confidence=0.7),
    ]
    per_ticker = {"AAA": fake_history(), "BBB": fake_history(start_price=90)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    aaa_ticker = make_ticker()
    # BBB priced off 90 instead of 100 - reuse the same relative strikes/deltas is not exact,
    # but the liquidity/delta gates are lenient enough (moneyness tolerance, delta distance
    # minimization) that this still produces a qualifying row; the point of this test is
    # publishing across >1 ticker, not precision-matching BBB's deltas.
    bbb_ticker = make_ticker()
    fake_yf = FakeYf({"AAA": aaa_ticker, "BBB": bbb_ticker})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_PMCC_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/pmcc.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    assert result["window"] == {
        "near_min_days_to_expiration": module.NEAR_MIN_DAYS_TO_EXPIRATION,
        "near_max_days_to_expiration": module.NEAR_MAX_DAYS_TO_EXPIRATION,
        "near_target_days_to_expiration": module.NEAR_TARGET_DAYS_TO_EXPIRATION,
        "near_target_delta": module.NEAR_TARGET_DELTA,
        "leaps_min_days_to_expiration": module.LEAPS_MIN_DAYS_TO_EXPIRATION,
        "leaps_max_days_to_expiration": module.LEAPS_MAX_DAYS_TO_EXPIRATION,
        "leaps_target_days_to_expiration": module.LEAPS_TARGET_DAYS_TO_EXPIRATION,
        "leaps_target_delta": module.LEAPS_TARGET_DELTA,
    }
    assert aaa_ticker.option_chain_calls == 2
    assert bbb_ticker.option_chain_calls == 2


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_PMCC_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_PMCC_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/pmcc.json"] == result


# --- backtest_universe / run_backtest -----------------------------------------------------------
#
# fake_history()'s flat/linear closes make realized_volatility_20d() return 0.0 (falsy), which
# silently skips every walk-forward period - same reasoning as
# test_build_covered_call_screen.py's non_flat_history(). Needs genuinely non-flat price
# history for backtest_universe to produce any trades at all.

def non_flat_history(sessions=320, start_price=100.0):
    import math
    closes = []
    price = start_price
    for index in range(sessions):
        price = price * (1 + 0.02 * math.sin(index * 0.9) + 0.01 * math.sin(index * 0.37) + 0.0005)
        closes.append(round(price, 2))
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    return {"dates": dates, "closes": closes, "volumes": [1_000_000] * sessions}


def test_backtest_universe_returns_stats_with_sane_shape(monkeypatch):
    history = non_flat_history()
    universe = [{"ticker": "AAA"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": history}))

    stats = module.backtest_universe(universe, object(), as_of=TODAY)

    assert stats is not None
    assert stats["num_trades"] > 0
    assert set(stats) == {"num_trades", "total_return", "annualized_return", "sharpe_ratio",
                          "skewness", "kurtosis", "probabilistic_sharpe_ratio", "deflated_sharpe_ratio",
                          "deflated_sharpe_trials", "max_drawdown", "win_rate", "average_pnl_per_trade",
                          "equity_curve"}


def test_backtest_universe_returns_none_when_history_too_short(monkeypatch):
    universe = [{"ticker": "SHORT1"}, {"ticker": "SHORT2"}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({
        "SHORT1": fake_history(sessions=15), "SHORT2": fake_history(sessions=10),
    }))

    assert module.backtest_universe(universe, object(), as_of=TODAY) is None


def test_run_backtest_publishes_success(monkeypatch):
    loaded = {"advisor.json": {"research": [{"ticker": "AAA"}]}}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": non_flat_history()}))
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    result = module.run_backtest(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/pmcc-backtest.json"] == result
    assert result["backtest"]["num_trades"] > 0
    assert "APPROXIMATE" in result["methodology"]
    assert result["window"]["leaps_target_days_to_expiration"] == module.LEAPS_TARGET_DAYS_TO_EXPIRATION


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/pmcc-backtest.json"] == result


def test_run_backtest_ignores_enable_pmcc_screen_flag(monkeypatch):
    # Unlike run(), run_backtest() needs no live option-chain data, so it must execute
    # regardless of whether ENABLE_PMCC_SCREEN is set at all.
    monkeypatch.delenv("ENABLE_PMCC_SCREEN", raising=False)
    loaded = {"advisor.json": {"research": [{"ticker": "AAA"}]}}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": non_flat_history()}))
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    result = module.run_backtest(as_of=TODAY)

    assert result is not None
    assert result["status"] == "success"
