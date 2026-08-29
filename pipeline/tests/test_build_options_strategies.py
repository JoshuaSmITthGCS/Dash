import sys
from datetime import date, timedelta

import pytest

import build_options_strategies as module
import iv_archive


@pytest.fixture(autouse=True)
def _isolated_iv_archive(tmp_path, monkeypatch):
    """fetch_chain() writes to iv_archive.py on every call in this module - isolate every
    test in this file from the real pipeline/data/iv_archive/ directory, the same way
    test_price_archive.py isolates price_archive's ARCHIVE_DIR/CONFLICTS. MANIFEST is
    derived from ARCHIVE_DIR at import time, so it needs its own monkeypatch too.
    """
    archive_dir = tmp_path / "iv_archive"
    monkeypatch.setattr(iv_archive, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(iv_archive, "MANIFEST", str(archive_dir / "archive_manifest.json"))


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


class FakeChain:
    def __init__(self, calls, puts):
        self.calls = FakeFrame(calls)
        self.puts = FakeFrame(puts)


class FakeTicker:
    """Counts option_chain() calls so tests can assert the whole point of this module:
    ONE chain fetch per ticker feeding all three mechanisms, not three separate fetches.
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


TODAY = date(2024, 3, 1)
EXPIRATION = "2024-03-08"  # 7 days out, matches TARGET_DAYS_TO_EXPIRATION


def contract(strike, bid, ask, open_interest=200, iv=0.3, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


# price=100, iv=0.3, dte=7: call_delta(102)~0.32 (sell_call target), put_delta(98)~-0.31 (sell_put
# target); strike=100 is ATM on either side (buy mechanism, whichever side trend picks).
RICH_CALLS = [contract(100, 3.08, 3.12), contract(102, 2.08, 2.12)]
RICH_PUTS = [contract(98, 1.98, 2.02), contract(100, 3.08, 3.12)]


def universe_entry(ticker, market_cap=5e9, sector="Technology", score=70, confidence=0.8):
    return {"ticker": ticker, "sector": sector, "market_cap": market_cap, "score": score, "confidence": confidence}


def test_fetch_chain_returns_shared_setup(monkeypatch):
    entry = universe_entry("AAA")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history(drift=0.05)}))
    fake_yf = FakeYf({"AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(RICH_CALLS, RICH_PUTS)})})

    setup = module.fetch_chain(entry, fake_yf, as_of=TODAY)

    assert setup is not None
    assert setup["ticker"] == "AAA"
    assert setup["expiration"] == EXPIRATION
    assert setup["dte"] == 7
    assert setup["calls"].rows == RICH_CALLS
    assert setup["puts"].rows == RICH_PUTS


def test_fetch_chain_returns_none_for_thin_history_or_no_options(monkeypatch):
    entry = universe_entry("THIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    assert module.fetch_chain(entry, FakeYf({}), as_of=TODAY) is None

    entry2 = universe_entry("NOOPT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": fake_history()}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})
    assert module.fetch_chain(entry2, fake_yf, as_of=TODAY) is None


def test_build_rows_derives_all_three_mechanisms_from_one_fetch(monkeypatch):
    entry = universe_entry("AAA")
    # Flat history (drift=0) keeps price exactly at 100 so the target-delta strikes match
    # the RICH_CALLS/RICH_PUTS comment's assumptions precisely; trend_20d==0 still counts
    # as the "call" side per build_options_screen.py's own "calls otherwise" convention.
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"AAA": fake_history(drift=0.0)}))
    ticker = FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(RICH_CALLS, RICH_PUTS)})
    fake_yf = FakeYf({"AAA": ticker})

    grouped = module.build_rows([entry], fake_yf, as_of=TODAY)

    assert len(grouped["buy"]) == 1
    assert len(grouped["sell_call"]) == 1
    assert len(grouped["sell_put"]) == 1
    assert grouped["buy"][0]["option_type"] == "call"  # flat/non-negative trend
    assert grouped["sell_call"][0]["call"]["strike"] == 102
    assert grouped["sell_put"][0]["put"]["strike"] == 98
    # The whole point of this module: one option_chain() call feeds all three mechanisms.
    assert ticker.option_chain_calls == 1


def test_build_buy_row_picks_put_on_negative_trend(monkeypatch):
    entry = universe_entry("DOWN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"DOWN": fake_history(drift=-0.05)}))
    fake_yf = FakeYf({"DOWN": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(RICH_CALLS, RICH_PUTS)})})

    setup = module.fetch_chain(entry, fake_yf, as_of=TODAY)
    row = module.build_buy_row(setup)

    assert row is not None
    assert row["option_type"] == "put"
    assert row["contract"]["strike"] == 100


def test_score_group_gates_small_cap_and_ranks_better_row_first():
    rows = [
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"annualized_yield": 0.30, "liquidity": 2.0, "cushion": 0.03}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"annualized_yield": 0.10, "liquidity": 0.5, "cushion": 0.01}},
    ]
    scored = module.score_group(rows, {"annualized_yield": .45, "liquidity": .30, "cushion": .25})
    by_ticker = {row["ticker"]: row for row in scored}

    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]
    assert scored[0]["ticker"] == "BIG"


def test_select_best_per_ticker_picks_highest_percentile_mechanism():
    buy = [{"ticker": "AAA", "eligibility": True, "percentile": 40.0}]
    sell_call = [{"ticker": "AAA", "eligibility": True, "percentile": 90.0}]
    sell_put = [{"ticker": "AAA", "eligibility": True, "percentile": 10.0}]

    best = module.select_best_per_ticker(buy, sell_call, sell_put)

    assert len(best) == 1
    strategy, row = best[0]
    assert strategy == "sell_call"
    assert row["percentile"] == 90.0


def test_select_best_per_ticker_skips_ineligible_and_missing_percentile():
    buy = [{"ticker": "AAA", "eligibility": False, "percentile": 99.0}]
    sell_call = [{"ticker": "AAA", "eligibility": True, "percentile": None}]
    sell_put = [{"ticker": "AAA", "eligibility": True, "percentile": 55.0}]

    best = module.select_best_per_ticker(buy, sell_call, sell_put)

    assert len(best) == 1
    strategy, row = best[0]
    assert strategy == "sell_put"


def test_to_result_short_term_shapes_each_mechanism():
    buy_row = {"ticker": "AAA", "sector": "Technology", "peer_group": "sector:technology",
              "percentile": 80.0, "score": 1.1, "structural_score": 70, "confidence": 0.8,
              "price": 100, "trend_20d": 0.05, "expiration": EXPIRATION, "days_to_expiration": 7,
              "option_type": "call", "realized_volatility_20d": 0.3, "implied_realized_vol_ratio": 1.1,
              "contract": {"strike": 102, "bid": 2.0, "ask": 2.2, "mid": 2.1, "spread_pct": 0.095,
                          "implied_volatility": 0.3, "open_interest": 200, "moneyness": 0.02},
              "reason_codes": []}
    result = module.to_result_short_term(1, "buy", buy_row)
    assert result["strategy"] == "buy_call"
    assert result["legs"] == [{"action": "buy", "option_type": "call", "strike": 102, "bid": 2.0,
                               "ask": 2.2, "mid": 2.1, "spread_pct": 0.095, "implied_volatility": 0.3,
                               "open_interest": 200}]
    assert result["capital_required"] == 210.0

    sell_call_row = {"ticker": "BBB", "sector": "Technology", "peer_group": "sector:technology",
                     "percentile": 70.0, "score": 0.9, "structural_score": 60, "confidence": 0.7,
                     "price": 100, "trend_20d": 0.01, "expiration": EXPIRATION, "days_to_expiration": 7,
                     "capital_required": 10000, "call": {"strike": 102, "bid": 2.0, "ask": 2.2, "mid": 2.1,
                     "spread_pct": 0.095, "implied_volatility": 0.3, "open_interest": 200, "delta": 0.32},
                     "metrics": {"premium": 2.1}, "reason_codes": []}
    result = module.to_result_short_term(2, "sell_call", sell_call_row)
    assert result["strategy"] == "sell_call"
    assert result["legs"][0]["action"] == "sell"
    assert result["capital_required"] == 10000

    sell_put_row = {**sell_call_row, "ticker": "CCC", "put": sell_call_row["call"], "capital_required": 10200}
    result = module.to_result_short_term(3, "sell_put", sell_put_row)
    assert result["strategy"] == "sell_put"
    assert result["legs"][0]["option_type"] == "put"


def test_run_publishes_all_four_files_from_one_fetch_per_ticker(monkeypatch):
    universe = [universe_entry("AAA"), universe_entry("BBB", market_cap=4e9)]
    per_ticker = {"AAA": fake_history(drift=0.05), "BBB": fake_history(start_price=90, drift=0.05)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    aaa_ticker = FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(RICH_CALLS, RICH_PUTS)})
    bbb_calls = [contract(90, 2.78, 2.82), contract(92, 1.88, 1.92)]
    bbb_puts = [contract(88, 1.78, 1.82), contract(90, 2.78, 2.82)]
    bbb_ticker = FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(bbb_calls, bbb_puts)})
    fake_yf = FakeYf({"AAA": aaa_ticker, "BBB": bbb_ticker})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result is not None
    for name in ("screens/options.json", "screens/covered-calls.json",
                "screens/cash-secured-puts.json", "screens/short-term-trades.json"):
        assert saved[name]["status"] == "success"
        assert len(saved[name]["results"]) >= 1
    assert aaa_ticker.option_chain_calls == 1
    assert bbb_ticker.option_chain_calls == 1
    short_term_ranks = [row["rank"] for row in saved["screens/short-term-trades.json"]["results"]]
    assert short_term_ranks == sorted(short_term_ranks)
    for row in saved["screens/short-term-trades.json"]["results"]:
        assert row["strategy"] in {"buy_call", "buy_put", "sell_call", "sell_put"}

    # iv_archive.py: this run() is its sole write path. A fresh two-ticker/one-day run
    # writes today's ATM IV for each, publishes a healthy archive_health() (a run just
    # happened), and correctly withholds iv_percentile - miles short of the 60-sample floor.
    assert saved["screens/options.json"]["iv_archive_health"]["state"] == "healthy"
    assert iv_archive.load_series("AAA")["dates"] == [TODAY.isoformat()]
    assert saved["screens/options.json"]["results"][0]["iv_percentile"] is None
    assert saved["screens/covered-calls.json"]["results"][0]["metrics"]["iv_percentile"] is None


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_on_all_four_files_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    assert module.run() is None
    for name in ("screens/options.json", "screens/covered-calls.json",
                "screens/cash-secured-puts.json", "screens/short-term-trades.json"):
        assert saved[name]["status"] == "unavailable"
        assert saved[name]["reason_code"] == "NO_PUBLISHED_UNIVERSE"


# --- backtest -----------------------------------------------------------------------------

def wiggly_history(sessions=200, start_price=100, amplitude=3, drift=0.05):
    closes = [start_price + amplitude * ((-1) ** index) + index * drift for index in range(sessions)]
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    return {"dates": dates, "closes": closes, "volumes": [1_000_000] * sessions}


def test_backtest_universe_pools_all_three_mechanisms(monkeypatch):
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
    universe = [universe_entry("SHORT1"), universe_entry("SHORT2")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({
        "SHORT1": fake_history(sessions=15), "SHORT2": fake_history(sessions=10),
    }))
    assert module.backtest_universe(universe, yf=object()) is None


def test_run_backtest_publishes_success(monkeypatch):
    per_ticker = {"AAA": wiggly_history(), "BBB": wiggly_history(start_price=80, amplitude=2)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    universe = [universe_entry("AAA"), universe_entry("BBB")]
    monkeypatch.setitem(sys.modules, "yfinance", object())
    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "success"
    assert saved["screens/short-term-trades-backtest.json"] == result
    assert "backtest" in result
    assert result["backtest"]["num_trades"] > 0


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
