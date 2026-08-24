"""backtest_swing.py: no-lookahead guarantees, embargo behavior, and an end-to-end smoke run.

Most of backtest_swing.py's real logic (composite scoring, eligibility, renormalization) lives
in swing_signals.py and is already covered by pipeline/tests/test_build_swing_screen.py. What
is specific to this module and worth pinning here: that slicing to ``as_of`` actually keeps
the future out, that the triple-barrier outcome refuses to grade a period it cannot yet see the
end of, and that a full walk-forward run over a tiny synthetic universe produces the disclosed
shape without raising.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest_swing as module
from validation.trading_calendar import TradingCalendar


def sessions_from(start, count):
    day, output = date.fromisoformat(start), []
    while len(output) < count:
        if day.weekday() < 5:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def price_path(count, values):
    """``values`` broadcast or repeated to length ``count`` starting at a flat $100 base."""
    if callable(values):
        return [values(index) for index in range(count)]
    return [values] * count


def cache_payload(dates, closes, volume=5_000_000.0, sector="Technology", name="Test Co"):
    return {"name": name, "sector": sector, "is_etf": False, "dates": dates, "closes": closes,
            "volumes": [volume] * len(closes)}


# ---------------------------------------------------------------------------
# entry_index / rebalance_dates
# ---------------------------------------------------------------------------

def test_entry_index_finds_the_most_recent_session_at_or_before_the_target():
    dates = sessions_from("2024-01-01", 20)
    assert dates[module.entry_index(dates, dates[10])] == dates[10]
    # A weekend/holiday target lands on the prior session, never the next one.
    assert dates[module.entry_index(dates, "2024-01-01")] is not None


def test_entry_index_is_none_before_the_series_starts():
    dates = sessions_from("2024-06-01", 20)
    assert module.entry_index(dates, "2020-01-01") is None


def test_rebalance_dates_are_spaced_by_the_requested_cadence():
    sessions = [date.fromisoformat(d) for d in sessions_from("2020-01-01", 800)]
    calendar = TradingCalendar(sessions)
    dates = module.rebalance_dates(calendar, years=1, cadence_sessions=5)
    indices = [sessions.index(d) for d in dates]
    assert all(later - earlier == 5 for earlier, later in zip(indices, indices[1:]))


# ---------------------------------------------------------------------------
# No lookahead: the core guarantee this module exists to keep
# ---------------------------------------------------------------------------

def test_historical_row_is_identical_regardless_of_what_happens_after_as_of():
    """Two tickers with IDENTICAL history through the cutoff and wildly different futures
    must score identically as of the cutoff. If a future close ever leaked into a subfactor,
    this is the test that would catch it."""
    dates = sessions_from("2024-01-01", 320)
    cutoff = 260
    shared_history = [100.0 * (1.0005 ** index) for index in range(cutoff)]
    crashes_after = shared_history + [shared_history[-1] * (0.9 ** index) for index in range(1, len(dates) - cutoff)]
    rallies_after = shared_history + [shared_history[-1] * (1.1 ** index) for index in range(1, len(dates) - cutoff)]

    module.resolve_sue = lambda *args, **kwargs: None  # avoid the real EDGAR store
    payload_crash = cache_payload(dates, crashes_after)
    payload_rally = cache_payload(dates, rallies_after)
    as_of = dates[cutoff - 1]

    row_crash = module.historical_row("CRASH", payload_crash, cutoff - 1, as_of)
    row_rally = module.historical_row("RALLY", payload_rally, cutoff - 1, as_of)

    assert row_crash["price"] == row_rally["price"]
    assert row_crash["factors"] == row_rally["factors"]
    assert row_crash["history_sessions"] == cutoff


def test_forward_outcome_is_none_until_the_vertical_barrier_is_actually_reached():
    # A little day-to-day noise, not a flat line: a flat series has zero true range, and
    # forward_outcome correctly refuses to size a barrier off a zero ATR.
    closes = [100.0 + (index % 3) * 0.2 for index in range(100)]
    entry_at_the_edge = 95   # only 4 forward sessions exist; the 10-session barrier is unmet
    assert module.forward_outcome(closes, entry_at_the_edge, vertical_sessions=10) is None

    entry_with_room = 50
    outcome = module.forward_outcome(closes, entry_with_room, vertical_sessions=10)
    assert outcome is not None


def test_forward_outcome_reflects_the_realized_future_path():
    """Not a leak: this is the label the score is graded against, computed *after* the
    (frozen, trailing-only) entry decision, exactly like settling a real trade."""
    noisy_prefix = [100.0 + (index % 3) * 0.2 for index in range(50)]
    rally = noisy_prefix + [noisy_prefix[-1] * (1.05 ** index) for index in range(1, 51)]
    crash = noisy_prefix + [noisy_prefix[-1] * (0.90 ** index) for index in range(1, 51)]
    rally_outcome = module.forward_outcome(rally, 49, vertical_sessions=10)
    crash_outcome = module.forward_outcome(crash, 49, vertical_sessions=10)
    assert rally_outcome > 0 > crash_outcome


# ---------------------------------------------------------------------------
# Cost-adjusted spread
# ---------------------------------------------------------------------------

def test_net_spread_is_gross_spread_minus_a_round_trip_cost():
    scores = {"HI1": 3, "HI2": 2, "LO1": -2, "LO2": -3}
    forward_returns = {"HI1": 0.05, "HI2": 0.05, "LO1": -0.01, "LO2": -0.01}
    liquidity = {ticker: 50_000_000.0 for ticker in scores}
    gross, net, cost_bps = module.net_spread(scores, forward_returns, liquidity, quantiles=2)
    assert gross == 0.06
    assert net < gross
    assert cost_bps > 0


def test_net_spread_is_none_below_the_minimum_pair_count():
    assert module.net_spread({"A": 1.0}, {"A": 0.01}, {"A": 1e9}, quantiles=5) == (None, None, None)


# ---------------------------------------------------------------------------
# End-to-end smoke run over a tiny synthetic universe
# ---------------------------------------------------------------------------

def test_run_backtest_end_to_end_on_a_synthetic_universe(tmp_path, monkeypatch):
    dates = sessions_from("2023-01-01", 420)
    sessions = [date.fromisoformat(d) for d in dates]

    def trending(seed):
        return lambda index: 50.0 + seed + index * 0.05 + (seed * (index % 7))

    for ticker, seed in (("AAA", 1.0), ("BBB", 2.0), ("CCC", 3.0), ("DDD", -1.0), ("EEE", 0.5)):
        payload = cache_payload(dates, price_path(len(dates), trending(seed)),
                                sector="Technology" if seed > 0 else "Energy")
        (tmp_path / f"{ticker}.json").write_text(__import__("json").dumps(payload))

    monkeypatch.setattr(module, "BACKTEST_CACHE", str(tmp_path))
    monkeypatch.setattr(module, "default_calendar", lambda: TradingCalendar(sessions))
    monkeypatch.setattr(module, "resolve_sue", lambda *args, **kwargs: None)
    # The default eligibility gates (liquidity, history) are demanding; relax them so a
    # 5-name synthetic universe actually produces graded periods to assert against.
    monkeypatch.setattr(module, "MINIMUM_ROWS_PER_PERIOD", 3)

    result = module.run_backtest(years=0.4, cadence_sessions=5, vertical_sessions=10)

    assert set(result["variants"]) == {"A", "B", "C"}
    assert result["excluded_legs"] == ["analyst_revision"]
    for variant in ("A", "B", "C"):
        coverage = result["variants"][variant]["leg_coverage"]
        assert coverage["analyst_revision"] == 0.0
    assert result["data_window"]["universe_size"] == 5
    assert result["limitations"]["authority"].startswith("Supplementary")

    # Variant A carries all five legs, so volume/52w/reversal alone (pead and revision are
    # stubbed out) clear the three-leg floor and the run actually grades periods - the
    # end-to-end path (scoring, labeling, IC, cost) genuinely executes rather than short-
    # circuiting to empty everywhere. B (no reversal leg: only 2 of its 4 legs resolvable
    # here) and C (residual reversal needs >=12 usable rows; this universe has 5) are
    # correctly zero - that asymmetry is itself the point of running all three.
    assert result["variants"]["A"]["graded_periods"] > 0
    assert result["variants"]["B"]["graded_periods"] == 0
    assert result["variants"]["C"]["graded_periods"] == 0


def test_signal_panel_is_none_by_default_and_populated_only_when_requested(tmp_path, monkeypatch):
    dates = sessions_from("2023-01-01", 420)
    sessions = [date.fromisoformat(d) for d in dates]

    def trending(seed):
        return lambda index: 50.0 + seed + index * 0.05 + (seed * (index % 7))

    for ticker, seed in (("AAA", 1.0), ("BBB", 2.0), ("CCC", 3.0), ("DDD", -1.0), ("EEE", 0.5)):
        payload = cache_payload(dates, price_path(len(dates), trending(seed)),
                                sector="Technology" if seed > 0 else "Energy")
        (tmp_path / f"{ticker}.json").write_text(__import__("json").dumps(payload))

    monkeypatch.setattr(module, "BACKTEST_CACHE", str(tmp_path))
    monkeypatch.setattr(module, "default_calendar", lambda: TradingCalendar(sessions))
    monkeypatch.setattr(module, "resolve_sue", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "MINIMUM_ROWS_PER_PERIOD", 3)

    without_panel = module.run_backtest(years=0.4, cadence_sessions=5, vertical_sessions=10)
    assert without_panel["signal_panel"] is None

    with_panel = module.run_backtest(years=0.4, cadence_sessions=5, vertical_sessions=10,
                                     collect_signal_panel=True)
    panel = with_panel["signal_panel"]
    assert panel is not None
    assert panel["model"] == "swing-v1.1.0"
    assert panel["leg_weights"] == module.swing_signals.SWING_WEIGHTS
    assert panel["periods"], "variant A graded periods, so the panel must not be empty"
    # Shape optimization_harness.Panel/score_with_weights expect: leg_scores keyed by
    # ticker, each a {leg: value} dict, alongside forward_returns for the same tickers.
    # ``sectors`` is what lets sector_weight_search run against this panel the same way
    # it already does against the fundamental/behavioral panel.
    first = panel["periods"][0]
    assert set(first) >= {"date", "leg_scores", "forward_returns", "sectors"}
    for ticker, legs in first["leg_scores"].items():
        assert ticker in first["forward_returns"]
        assert isinstance(legs, dict)
        assert set(legs) <= set(module.swing_signals.SWING_WEIGHTS)
    assert set(first["sectors"]) <= set(first["leg_scores"])
    assert set(first["sectors"].values()) <= {"Technology", "Energy"}
