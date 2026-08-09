import sys
from datetime import date, timedelta

import build_vertical_spread_screen as module


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


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


EXPIRATION = "2024-03-31"  # 30 days out from TODAY, inside [15, 45]

# closes[-1] == 100 for both, via start_price/drift chosen so start + 39*drift == 100:
# UP:   start=61,  drift=+1.0 -> trend_20d = 100/80  - 1 = +0.25
# DOWN: start=139, drift=-1.0 -> trend_20d = 100/120 - 1 = -0.1667
UP_HISTORY = fake_history(start_price=61, drift=1.0)
DOWN_HISTORY = fake_history(start_price=139, drift=-1.0)

# Calibrated against options_common.call_delta(100, strike, 0.4, 30):
#   strike=102 -> delta ~0.4541 (nearest to LONG_LEG_TARGET_DELTA=0.45)
#   strike=111 -> delta ~0.1969 (nearest to SHORT_LEG_TARGET_DELTA=0.20)
GOOD_CALLS = [
    contract(95, 8.08, 8.12), contract(100, 5.58, 5.62),
    contract(102, 4.08, 4.12),  # long leg: mid 4.10
    contract(105, 2.88, 2.92), contract(110, 1.38, 1.42),
    contract(111, 1.08, 1.12),  # short leg: mid 1.10
    contract(115, 0.555, 0.595), contract(120, 0.21, 0.25),
]

# Calibrated against options_common.put_delta(100, strike, 0.4, 30):
#   strike=99 -> delta ~-0.4424 (nearest to LONG_LEG_TARGET_DELTA=0.45)
#   strike=91 -> delta ~-0.1895 (nearest to SHORT_LEG_TARGET_DELTA=0.20)
GOOD_PUTS = [
    contract(80, 0.21, 0.25), contract(85, 0.555, 0.595),
    contract(90, 1.28, 1.32),
    contract(91, 1.08, 1.12),  # short leg: mid 1.10
    contract(95, 2.88, 2.92),
    contract(99, 4.08, 4.12),  # long leg: mid 4.10
]

# Same strikes/deltas as GOOD_CALLS, but priced so the long leg is cheaper than the
# short leg -> net_debit <= 0 (a coherent debit spread should never price this way for
# this delta ordering, but build_row must guard it).
NET_CREDIT_CALLS = [
    contract(95, 8.08, 8.12), contract(100, 5.58, 5.62),
    contract(102, 0.53, 0.57),  # long leg: mid 0.55
    contract(105, 2.88, 2.92), contract(110, 1.38, 1.42),
    contract(111, 1.08, 1.12),  # short leg: mid 1.10
    contract(115, 0.555, 0.595), contract(120, 0.21, 0.25),
]

# Same strikes/deltas as GOOD_CALLS, but priced so net_debit consumes the whole width
# (width=9, net_debit=13) -> width <= net_debit, no room left for profit.
TIGHT_CALLS = [
    contract(95, 8.08, 8.12), contract(100, 5.58, 5.62),
    contract(102, 14.98, 15.02),  # long leg: mid 15.00
    contract(105, 2.88, 2.92), contract(110, 1.38, 1.42),
    contract(111, 1.98, 2.02),  # short leg: mid 2.00
    contract(115, 0.555, 0.595), contract(120, 0.21, 0.25),
]


def make_universe_entry(ticker, market_cap=5e9):
    return {"ticker": ticker, "sector": "Technology", "market_cap": market_cap, "score": 70, "confidence": 0.8}


def test_build_row_bull_call_spread_on_uptrend(monkeypatch):
    entry = make_universe_entry("UP")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"UP": UP_HISTORY}))
    fake_yf = FakeYf({"UP": FakeTicker(options=[EXPIRATION],
                                       chains={EXPIRATION: FakeChain(GOOD_CALLS, [])})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["strategy_type"] == "bull_call_spread"
    assert row["long_leg"]["strike"] == 102
    assert row["short_leg"]["strike"] == 111
    assert row["days_to_expiration"] == 30


def test_build_row_bear_put_spread_on_downtrend(monkeypatch):
    entry = make_universe_entry("DOWN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"DOWN": DOWN_HISTORY}))
    fake_yf = FakeYf({"DOWN": FakeTicker(options=[EXPIRATION],
                                         chains={EXPIRATION: FakeChain([], GOOD_PUTS)})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["strategy_type"] == "bear_put_spread"
    assert row["long_leg"]["strike"] == 99
    assert row["short_leg"]["strike"] == 91


def test_build_row_returns_none_when_history_too_thin(monkeypatch):
    entry = make_universe_entry("THIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THIN": fake_history(sessions=10)}))
    fake_yf = FakeYf({"THIN": FakeTicker(options=[EXPIRATION],
                                         chains={EXPIRATION: FakeChain(GOOD_CALLS, [])})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_options_unavailable(monkeypatch):
    entry = make_universe_entry("NOOPT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOOPT": UP_HISTORY}))
    fake_yf = FakeYf({"NOOPT": FakeTicker(raise_on_options=True)})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_chain_unavailable(monkeypatch):
    entry = make_universe_entry("NOCHAIN")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOCHAIN": UP_HISTORY}))
    fake_yf = FakeYf({"NOCHAIN": FakeTicker(options=[EXPIRATION], raise_on_chain=True)})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_without_qualifying_expiration(monkeypatch):
    entry = make_universe_entry("NODATE")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NODATE": UP_HISTORY}))
    # 1 day out, below MIN_DAYS_TO_EXPIRATION=15
    fake_yf = FakeYf({"NODATE": FakeTicker(options=["2024-03-02"])})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_a_leg_cannot_be_found(monkeypatch):
    entry = make_universe_entry("NOLEG")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOLEG": UP_HISTORY}))
    # Uptrend -> calls frame required, but the chain only has puts.
    fake_yf = FakeYf({"NOLEG": FakeTicker(options=[EXPIRATION],
                                          chains={EXPIRATION: FakeChain([], GOOD_PUTS)})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_on_net_credit_spread(monkeypatch):
    entry = make_universe_entry("CREDIT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"CREDIT": UP_HISTORY}))
    fake_yf = FakeYf({"CREDIT": FakeTicker(options=[EXPIRATION],
                                           chains={EXPIRATION: FakeChain(NET_CREDIT_CALLS, [])})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_build_row_returns_none_when_width_leaves_no_room(monkeypatch):
    entry = make_universe_entry("TIGHT")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"TIGHT": UP_HISTORY}))
    fake_yf = FakeYf({"TIGHT": FakeTicker(options=[EXPIRATION],
                                          chains={EXPIRATION: FakeChain(TIGHT_CALLS, [])})})

    assert module.build_row(entry, fake_yf, as_of=TODAY) is None


def test_max_profit_plus_max_loss_equals_width(monkeypatch):
    entry = make_universe_entry("UP")
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"UP": UP_HISTORY}))
    fake_yf = FakeYf({"UP": FakeTicker(options=[EXPIRATION],
                                       chains={EXPIRATION: FakeChain(GOOD_CALLS, [])})})

    row = module.build_row(entry, fake_yf, as_of=TODAY)

    metrics = row["metrics"]
    assert abs((metrics["max_profit"] + metrics["max_loss"]) - metrics["width"]) < 1e-9


def test_score_rows_ranks_by_composite_and_gates_small_caps():
    # winsorize()/zscores() clip the extremes of a tiny sample toward the middle, so with
    # too few rows the top one or two candidates collapse to an identical score. A wider
    # spread of rows (TOP/LOW padding BIG/MID) keeps BIG's own factor values unclipped so
    # the risk_reward + liquidity + trend_strength ordering actually shows up in the score.
    rows = [
        {"ticker": "TOP", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"risk_reward": 3.5, "liquidity": 2.8, "trend_strength": 0.3}},
        {"ticker": "BIG", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"risk_reward": 2.5, "liquidity": 2.0, "trend_strength": 0.2}},
        {"ticker": "MID", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"risk_reward": 1.5, "liquidity": 1.2, "trend_strength": 0.1}},
        {"ticker": "LOW", "price": 50, "market_cap": 5e9, "realized_volatility_20d": 0.3,
         "factors": {"risk_reward": 1.0, "liquidity": 0.8, "trend_strength": 0.05}},
        {"ticker": "SMALL", "price": 50, "market_cap": 1e8, "realized_volatility_20d": 0.3,
         "factors": {"risk_reward": 0.8, "liquidity": 0.5, "trend_strength": 0.02}},
    ]
    scored = module.score_rows(rows)
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["BIG"]["eligibility"] is True
    assert by_ticker["SMALL"]["eligibility"] is False
    assert "MINIMUM_MARKET_CAP" in by_ticker["SMALL"]["reason_codes"]
    assert by_ticker["BIG"]["score"] > by_ticker["MID"]["score"] > by_ticker["SMALL"]["score"]


def test_to_result_shape():
    row = {
        "ticker": "AAA", "eligibility": True, "sector": "Technology", "peer_group_label": "Technology",
        "percentile": 80.0, "score": 1.2345, "structural_score": 70, "confidence": 0.8,
        "price": 100.0, "trend_20d": 0.25, "expiration": EXPIRATION, "days_to_expiration": 30,
        "capital_required": 300.0, "strategy_type": "bull_call_spread",
        "long_leg": {"strike": 102, "bid": 4.0, "ask": 4.2, "mid": 4.1, "spread_pct": 0.0488,
                     "implied_volatility": 0.4, "open_interest": 200, "delta": 0.4541},
        "short_leg": {"strike": 111, "bid": 1.0, "ask": 1.2, "mid": 1.1, "spread_pct": 0.1818,
                      "implied_volatility": 0.4, "open_interest": 200, "delta": 0.1969},
        "metrics": {"net_debit": 3.0, "width": 9.0, "max_profit": 6.0, "max_loss": 3.0, "risk_reward": 2.0},
        "reason_codes": [],
    }

    result = module.to_result(1, row)

    assert result["rank"] == 1
    assert result["ticker"] == "AAA"
    assert result["strategy_type"] == "bull_call_spread"
    assert result["metrics"] == row["metrics"]
    assert result["reason_codes"] == []
    assert len(result["legs"]) == 2
    long_leg_result, short_leg_result = result["legs"]
    assert long_leg_result["action"] == "buy"
    assert short_leg_result["action"] == "sell"
    assert long_leg_result["option_type"] == "call"
    assert short_leg_result["option_type"] == "call"
    assert long_leg_result["strike"] == 102
    assert short_leg_result["strike"] == 111


def test_to_result_uses_put_option_type_for_bear_put_spread():
    row = {
        "ticker": "DOWN", "eligibility": True, "sector": "Technology", "peer_group_label": "Technology",
        "percentile": 40.0, "score": -0.1, "structural_score": 40, "confidence": 0.6,
        "price": 100.0, "trend_20d": -0.1667, "expiration": EXPIRATION, "days_to_expiration": 30,
        "capital_required": 300.0, "strategy_type": "bear_put_spread",
        "long_leg": {"strike": 99, "bid": 4.0, "ask": 4.2, "mid": 4.1, "spread_pct": 0.0488,
                     "implied_volatility": 0.4, "open_interest": 200, "delta": -0.4424},
        "short_leg": {"strike": 91, "bid": 1.0, "ask": 1.2, "mid": 1.1, "spread_pct": 0.1818,
                      "implied_volatility": 0.4, "open_interest": 200, "delta": -0.1895},
        "metrics": {"net_debit": 3.0, "width": 8.0, "max_profit": 5.0, "max_loss": 3.0, "risk_reward": 1.6667},
        "reason_codes": [],
    }

    result = module.to_result(2, row)

    assert result["legs"][0]["option_type"] == "put"
    assert result["legs"][1]["option_type"] == "put"


def test_run_publishes_scored_results(monkeypatch):
    universe = [make_universe_entry("AAA"), make_universe_entry("BBB")]
    per_ticker = {"AAA": UP_HISTORY, "BBB": UP_HISTORY}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))
    fake_yf = FakeYf({
        "AAA": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(GOOD_CALLS, [])}),
        "BBB": FakeTicker(options=[EXPIRATION], chains={EXPIRATION: FakeChain(GOOD_CALLS, [])}),
    })
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setenv("ENABLE_VERTICAL_SPREAD_SCREEN", "1")

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run(as_of=TODAY)

    assert result["status"] == "success"
    assert saved["screens/vertical-spreads.json"] == result
    assert len(result["results"]) == 2
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    assert result["window"]["long_leg_target_delta"] == module.LONG_LEG_TARGET_DELTA
    assert result["window"]["short_leg_target_delta"] == module.SHORT_LEG_TARGET_DELTA


def test_run_skips_when_flag_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_VERTICAL_SPREAD_SCREEN", raising=False)
    assert module.run() is None


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setenv("ENABLE_VERTICAL_SPREAD_SCREEN", "1")
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/vertical-spreads.json"] == result


# ---------------------------------------------------------------------------
# backtest_universe / run_backtest
# ---------------------------------------------------------------------------

# Non-flat (so realized_volatility_20d isn't 0.0/falsy) noisy trend patterns, one net
# up and one net down over each 10-session cycle - used to build long walk-forward
# price histories exercising both the bull-call and bear-put paths.
BT_UP_PATTERN = [3, -1, 2, -1.5, 2.5, -1, 3, -2, 2, -0.5]
BT_DOWN_PATTERN = [-3, 1, -2, 1.5, -2.5, 1, -3, 2, -2, 0.5]


def build_walk_series(base, pattern, sessions):
    closes = [base]
    for index in range(sessions - 1):
        closes.append(closes[-1] + pattern[index % len(pattern)])
    return closes


# One walk-forward period's worth of entry history: 22 closes (indices 0-21), noisy and
# trending, so realized_volatility_20d/trend_20d are both defined and non-zero at the
# entry index (21) - matches walk_periods' lookback=21 default.
BT_UP_ENTRY_HISTORY = build_walk_series(100, BT_UP_PATTERN, 22)   # price=116.0 at index 21
BT_DOWN_ENTRY_HISTORY = build_walk_series(100, BT_DOWN_PATTERN, 22)  # price=84.0 at index 21

# Calibrated against synthetic_chain(116.0, realized_volatility_20d(BT_UP_ENTRY_HISTORY), 30)
# + select_by_target_delta: long call strike=118.32 (mid 2.80), short call strike=125.28
# (mid 0.935) -> net_debit=1.865, width=6.96, cost=187.8 (incl. 2*CONTRACT_FEE).
BT_UP_LONG_STRIKE, BT_UP_SHORT_STRIKE = 118.32, 125.28
BT_UP_COST = 187.8
BT_UP_MAX_PROFIT_PNL = BT_UP_SHORT_STRIKE * 0 + (BT_UP_SHORT_STRIKE - BT_UP_LONG_STRIKE) * 100 - BT_UP_COST  # 508.2
BT_UP_MAX_LOSS_PNL = -BT_UP_COST  # -187.8

# Calibrated against synthetic_chain(84.0, realized_volatility_20d(BT_DOWN_ENTRY_HISTORY), 30)
# + select_by_target_delta: long put strike=84.0 (mid 3.28), short put strike=77.28
# (mid 0.86) -> net_debit=2.42, width=6.72, cost=243.3.
BT_DOWN_LONG_STRIKE, BT_DOWN_SHORT_STRIKE = 84.0, 77.28
BT_DOWN_COST = 243.3
BT_DOWN_MAX_PROFIT_PNL = (BT_DOWN_LONG_STRIKE - BT_DOWN_SHORT_STRIKE) * 100 - BT_DOWN_COST  # 428.7
BT_DOWN_MAX_LOSS_PNL = -BT_DOWN_COST  # -243.3

STATS_KEYS = {"num_trades", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
             "win_rate", "average_pnl_per_trade", "equity_curve"}


def single_period_closes(entry_history, settle_price, filler_sessions=20):
    """entry_history (len 22, price at index 21) + filler (unused by the one period) +
    one real settle close at the expiry index (42) - exactly 43 closes, so walk_periods
    yields exactly one (entry=21, expiry=42) period."""
    return entry_history + [entry_history[-1]] * filler_sessions + [settle_price]


def test_backtest_universe_pools_trades_from_up_and_down_trending_tickers(monkeypatch):
    up_closes = build_walk_series(100, BT_UP_PATTERN, 100)
    down_closes = build_walk_series(200, BT_DOWN_PATTERN, 100)
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"UP": {"closes": up_closes}, "DOWN": {"closes": down_closes}}))
    universe = [make_universe_entry("UP"), make_universe_entry("DOWN")]

    stats = module.backtest_universe(universe, FakeYf({}))

    assert stats is not None
    assert set(stats.keys()) == STATS_KEYS
    assert stats["num_trades"] > 0


def test_backtest_universe_call_spread_max_profit_at_or_above_short_strike(monkeypatch):
    closes = single_period_closes(BT_UP_ENTRY_HISTORY, settle_price=BT_UP_SHORT_STRIKE + 50)
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"X": {"closes": closes}}))

    stats = module.backtest_universe([make_universe_entry("X")], FakeYf({}))

    assert stats["num_trades"] == 1
    assert abs(stats["average_pnl_per_trade"] - BT_UP_MAX_PROFIT_PNL) < 0.5


def test_backtest_universe_call_spread_max_loss_at_or_below_long_strike(monkeypatch):
    closes = single_period_closes(BT_UP_ENTRY_HISTORY, settle_price=BT_UP_LONG_STRIKE - 50)
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"X": {"closes": closes}}))

    stats = module.backtest_universe([make_universe_entry("X")], FakeYf({}))

    assert stats["num_trades"] == 1
    assert abs(stats["average_pnl_per_trade"] - BT_UP_MAX_LOSS_PNL) < 0.5


def test_backtest_universe_put_spread_max_profit_at_or_below_short_strike(monkeypatch):
    closes = single_period_closes(BT_DOWN_ENTRY_HISTORY, settle_price=max(0.01, BT_DOWN_SHORT_STRIKE - 50))
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"Y": {"closes": closes}}))

    stats = module.backtest_universe([make_universe_entry("Y")], FakeYf({}))

    assert stats["num_trades"] == 1
    assert abs(stats["average_pnl_per_trade"] - BT_DOWN_MAX_PROFIT_PNL) < 1.0


def test_backtest_universe_put_spread_max_loss_at_or_above_long_strike(monkeypatch):
    closes = single_period_closes(BT_DOWN_ENTRY_HISTORY, settle_price=BT_DOWN_LONG_STRIKE + 50)
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"Y": {"closes": closes}}))

    stats = module.backtest_universe([make_universe_entry("Y")], FakeYf({}))

    assert stats["num_trades"] == 1
    assert abs(stats["average_pnl_per_trade"] - BT_DOWN_MAX_LOSS_PNL) < 1.0


def test_backtest_universe_returns_none_when_no_ticker_has_enough_history(monkeypatch):
    universe = [make_universe_entry("SHORT1"), make_universe_entry("SHORT2")]
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"SHORT1": fake_history(sessions=30), "SHORT2": fake_history(sessions=10)}))

    assert module.backtest_universe(universe, FakeYf({})) is None


def test_run_backtest_publishes_success(monkeypatch):
    up_closes = build_walk_series(100, BT_UP_PATTERN, 100)
    down_closes = build_walk_series(200, BT_DOWN_PATTERN, 100)
    universe = [make_universe_entry("UP"), make_universe_entry("DOWN")]
    monkeypatch.setattr(module, "yahoo_history",
                        make_yahoo_history({"UP": {"closes": up_closes}, "DOWN": {"closes": down_closes}}))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))

    loaded = {"advisor.json": {"research": universe}}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "success"
    assert saved["screens/vertical-spreads-backtest.json"] == result
    assert set(result["backtest"].keys()) == STATS_KEYS
    assert result["backtest"]["num_trades"] > 0
    assert result["window"]["target_days_to_expiration"] == module.TARGET_DAYS_TO_EXPIRATION


def test_run_backtest_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    saved = {}
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run_backtest()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "NO_PUBLISHED_UNIVERSE"
    assert saved["screens/vertical-spreads-backtest.json"] == result


def test_run_backtest_ignores_enable_flag_env_state(monkeypatch):
    up_closes = build_walk_series(100, BT_UP_PATTERN, 100)
    universe = [make_universe_entry("UP")]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"UP": {"closes": up_closes}}))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYf({}))
    monkeypatch.setattr(module, "load_json", lambda name: {"research": universe})
    monkeypatch.setattr(module, "save_json", lambda name, payload: None)

    monkeypatch.delenv("ENABLE_VERTICAL_SPREAD_SCREEN", raising=False)
    result_without_flag = module.run_backtest()
    assert result_without_flag is not None
    assert result_without_flag["status"] == "success"

    monkeypatch.setenv("ENABLE_VERTICAL_SPREAD_SCREEN", "0")
    result_with_flag_off = module.run_backtest()
    assert result_with_flag_off is not None
    assert result_with_flag_off["status"] == "success"
