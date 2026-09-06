from datetime import date, timedelta

import build_catalyst_screen as module


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
    def __init__(self, options=None, chains=None, earnings_dates=None, raise_on_options=False):
        self._options = options or []
        self._chains = chains or {}
        self._raise_on_options = raise_on_options
        self.earnings_dates = earnings_dates

    @property
    def options(self):
        if self._raise_on_options:
            raise RuntimeError("boom")
        return self._options

    def option_chain(self, expiration):
        return self._chains[expiration]


class FakeYf:
    def __init__(self, tickers):
        self._tickers = tickers

    def Ticker(self, symbol):  # noqa: N802 - matches yfinance's API
        return self._tickers[symbol]


def fake_history(sessions=40, start_price=100):
    dates = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(sessions)]
    closes = [start_price] * sessions
    volumes = [1_000_000] * sessions
    return {"dates": dates, "closes": closes, "volumes": volumes, "highs": closes, "lows": closes}


def make_yahoo_history(per_ticker):
    def _yahoo_history(ticker, yf, ticker_obj=None, **_kwargs):
        return per_ticker.get(ticker, {"dates": [], "closes": [], "volumes": [], "highs": [], "lows": []})
    return _yahoo_history


def contract(strike, bid, ask, open_interest=600, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


TODAY = date(2024, 3, 1)


def test_build_row_none_when_no_confirmed_earnings_date(monkeypatch):
    universe = {"ticker": "NOEARN", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOEARN": fake_history()}))
    fake_yf = FakeYf({"NOEARN": FakeTicker()})  # no earnings_dates at all
    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_none_when_earnings_is_outside_the_window(monkeypatch):
    universe = {"ticker": "FAR", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"FAR": fake_history()}))
    fake_yf = FakeYf({"FAR": FakeTicker(earnings_dates=FakeEarningsFrame([("2024-04-01", NAN)]))})
    # 2024-04-01 is 31 days out - outside the default 14-day window.
    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_never_touches_the_option_chain_outside_the_window(monkeypatch):
    """Cost-control regression: a ticker outside the window must not pay for a chain fetch
    at all - .options raising must not sink build_row when it's never reached."""
    universe = {"ticker": "FAR", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"FAR": fake_history()}))
    fake_yf = FakeYf({"FAR": FakeTicker(raise_on_options=True,
                                        earnings_dates=FakeEarningsFrame([("2024-04-01", NAN)]))})
    assert module.build_row(universe, fake_yf, as_of=TODAY) is None


def test_build_row_computes_an_isolated_expected_move_when_both_expirations_resolve(monkeypatch):
    universe = {"ticker": "EARNCAT", "sector": "Technology", "market_cap": 5e9,
               "score": 70, "data_coverage": 0.8}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"EARNCAT": fake_history(start_price=100)}))
    pre_expiration, post_expiration = "2024-03-08", "2024-03-15"
    # Earnings lands after pre_expiration (7 dte) and before post_expiration (14 dte).
    fake_yf = FakeYf({"EARNCAT": FakeTicker(
        options=[pre_expiration, post_expiration],
        chains={
            pre_expiration: FakeChain([contract(strike=100, bid=1.96, ask=2.00, iv=0.20)],
                                      [contract(strike=100, bid=1.96, ask=2.00, iv=0.20)]),
            post_expiration: FakeChain([contract(strike=100, bid=3.90, ask=4.00, iv=0.40)],
                                       [contract(strike=100, bid=3.90, ask=4.00, iv=0.40)]),
        },
        earnings_dates=FakeEarningsFrame([("2024-03-10", NAN)]))})

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["ticker"] == "EARNCAT"
    assert row["days_to_earnings"] == 9
    assert row["pre_expiration"] == pre_expiration
    assert row["post_expiration"] == post_expiration
    assert row["expected_move_pct"] is not None and row["expected_move_pct"] > 0
    assert row["eligibility"] is True
    assert row["reason_codes"] == []
    # Context fields are populated too, distinctly from the isolated headline number.
    assert row["unisolated_iv_move_pct"] is not None
    assert row["straddle_move_pct"] is not None


def test_build_row_is_ineligible_without_a_prior_expiration_to_isolate_against(monkeypatch):
    """Earnings lands inside the very nearest expiration Yahoo lists - there is nothing
    shorter-dated to difference against, so the isolated move cannot resolve."""
    universe = {"ticker": "NOPRE", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"NOPRE": fake_history(start_price=100)}))
    post_expiration = "2024-03-15"
    fake_yf = FakeYf({"NOPRE": FakeTicker(
        options=[post_expiration],
        chains={post_expiration: FakeChain([contract(strike=100, bid=3.90, ask=4.00, iv=0.40)],
                                           [contract(strike=100, bid=3.90, ask=4.00, iv=0.40)])},
        earnings_dates=FakeEarningsFrame([("2024-03-10", NAN)]))})

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row is not None
    assert row["pre_expiration"] is None
    assert row["expected_move_pct"] is None
    assert row["eligibility"] is False
    assert "EXPECTED_MOVE_UNRESOLVED" in row["reason_codes"]
    # The unisolated single-expiry read still comes through as context.
    assert row["unisolated_iv_move_pct"] is not None


def test_build_row_excludes_a_thin_contract_from_the_iv_read(monkeypatch):
    """A contract below the catalyst screen's own stricter open-interest floor must not
    contribute to the ATM IV average, even though it would pass options_common's own
    (looser) shared gate."""
    universe = {"ticker": "THINOI", "sector": "Technology", "market_cap": 5e9}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history({"THINOI": fake_history(start_price=100)}))
    pre_expiration, post_expiration = "2024-03-08", "2024-03-15"
    fake_yf = FakeYf({"THINOI": FakeTicker(
        options=[pre_expiration, post_expiration],
        chains={
            pre_expiration: FakeChain(
                [contract(strike=100, bid=1.96, ask=2.00, iv=0.20, open_interest=100)],  # below 500 floor
                [contract(strike=100, bid=1.96, ask=2.00, iv=0.20, open_interest=100)]),
            post_expiration: FakeChain([contract(strike=100, bid=3.90, ask=4.00, iv=0.40)],
                                       [contract(strike=100, bid=3.90, ask=4.00, iv=0.40)]),
        },
        earnings_dates=FakeEarningsFrame([("2024-03-10", NAN)]))})

    row = module.build_row(universe, fake_yf, as_of=TODAY)

    assert row["pre_atm_implied_volatility"] is None  # thin contracts excluded, nothing to average
    assert row["expected_move_pct"] is None
    assert row["eligibility"] is False
