from datetime import date, timedelta

import pytest

import build_quality_value_screen as module
from valuation_history import MINIMUM_HISTORY_SESSIONS


def universe_row(ticker="AAA", **overrides):
    row = {
        "ticker": ticker, "sector": "Technology", "score": 70.0, "is_etf": False,
        "fundamental_categories": {"profitability": 80.0, "financial_health": 80.0,
                                   "accounting_quality": 80.0, "capital_allocation": 80.0,
                                   "valuation": 55.0, "growth": 10.0},
        "sector_valuation_percentile": 75.0,
        "score_variants": {"champion": {"confidence": .8}},
        "estimate_detail": {"eps_revision_30d_pct": .02, "revision_breadth_30d": .3},
    }
    row.update(overrides)
    return row


def sessions_from(start, count):
    """`count` weekday dates from `start` - enough of a calendar for the history gate."""
    day, output = date.fromisoformat(start), []
    while len(output) < count:
        if day.weekday() < 5:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def cache_entry(cheap_today=True, count=131):
    """A price path long enough to clear the history gate, ending cheap or expensive.

    It starts the day the oldest usable statement takes effect, so two later statements land
    inside the window and the multiples move for a reason other than price.
    """
    closes = [20.0] * (count - 1) + ([5.0] if cheap_today else [40.0])
    dates = sessions_from("2025-11-14", count)
    periods = ["2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31",
               "2024-12-31", "2024-09-30"]
    return {
        "dates": dates, "closes": closes, "volumes": [1_000_000.0] * len(closes),
        "income": {"periods": periods, "rows": {
            "Net Income": [10.0] * 7, "Total Revenue": [100.0] * 7, "EBIT": [20.0] * 7,
            "EBITDA": [30.0] * 7, "Diluted Average Shares": [1000.0] * 7}},
        "balance": {"periods": periods, "rows": {
            "Total Debt": [0.0] * 7, "Cash And Cash Equivalents": [0.0] * 7,
            "Stockholders Equity": [200.0] * 7, "Tangible Book Value": [150.0] * 7}},
        "cashflow": {"periods": periods, "rows": {"Free Cash Flow": [15.0] * 7}},
    }


def test_quality_score_ignores_valuation_so_cheapness_is_not_counted_twice():
    categories = {"profitability": 100.0, "financial_health": 100.0, "accounting_quality": 100.0,
                  "capital_allocation": 100.0, "valuation": 0.0, "growth": 0.0}

    assert module.quality_score(categories) == pytest.approx(100.0)


def test_quality_score_renormalizes_over_the_categories_that_are_present():
    assert module.quality_score({"profitability": 60.0}) == pytest.approx(60.0)
    assert module.quality_score({}) is None


def test_peer_value_prefers_the_peer_percentile_and_says_which_basis_it_used():
    assert module.peer_value(universe_row()) == (75.0, "sector_valuation_percentile")

    row = universe_row(sector_valuation_percentile=None)

    assert module.peer_value(row) == (55.0, "cross_sectional_valuation_score")


def test_distress_reads_solvency_not_cheapness():
    assert module.is_distressed({"altman_z": 1.2}) is True
    assert module.is_distressed({"interest_coverage": .4}) is True
    assert module.is_distressed({"altman_z": 4.0, "interest_coverage": 9.0}) is False
    assert module.is_distressed({}) is False


def test_a_ticker_at_its_own_window_low_scores_cheap_against_its_own_history():
    rows = module.build_rows([universe_row()], {}, entry_for=lambda ticker: cache_entry())

    assert rows[0]["own_history_sessions"] >= MINIMUM_HISTORY_SESSIONS
    assert rows[0]["own_history_score"] > 90


def test_the_same_ticker_at_its_window_high_scores_expensive():
    rows = module.build_rows([universe_row()], {},
                             entry_for=lambda ticker: cache_entry(cheap_today=False))

    assert rows[0]["own_history_score"] < 10


def test_a_ticker_without_cached_history_is_still_published_and_flagged():
    rows = module.classify_rows(module.attach_revision_percentiles(
        module.build_rows([universe_row()], {}, entry_for=lambda ticker: None)))

    assert rows[0]["own_history_sessions"] == 0
    assert rows[0]["classification"] == "insufficient historical data"
    assert rows[0]["reason_codes"] == ["INSUFFICIENT_HISTORICAL_DATA"]
    assert rows[0]["peer_value_score"] == 75.0


def test_etfs_are_not_scored_on_company_valuation_multiples():
    assert module.build_rows([universe_row(is_etf=True)], {}, entry_for=lambda ticker: None) == []


def test_revision_readings_are_ranked_across_the_cross_section():
    rows = module.attach_revision_percentiles(module.build_rows(
        [universe_row("AAA", estimate_detail={"eps_revision_30d_pct": .05, "revision_breadth_30d": .9}),
         universe_row("BBB", estimate_detail={"eps_revision_30d_pct": -.05, "revision_breadth_30d": -.9}),
         universe_row("CCC", estimate_detail={})],
        {}, entry_for=lambda ticker: None))
    ranked = {row["ticker"]: row for row in rows}

    assert ranked["AAA"]["revision_current_year"] == 100.0
    assert ranked["BBB"]["revision_current_year"] == 0.0
    assert ranked["CCC"]["revision_current_year"] is None


def test_a_cheap_high_quality_name_is_actionable_and_a_distressed_one_is_not():
    rows = module.build_rows([universe_row()], {}, entry_for=lambda ticker: cache_entry())
    module.attach_revision_percentiles(rows)
    module.classify_rows(rows)

    assert rows[0]["classification"] == "actionable value"

    distressed = module.build_rows([universe_row()], {"AAA": {"altman_z": 1.0}},
                                   entry_for=lambda ticker: cache_entry())
    module.classify_rows(module.attach_revision_percentiles(distressed))

    assert distressed[0]["classification"] == "distressed/value trap"
    assert distressed[0]["reason_codes"] == ["SEVERE_DISTRESS"]


def test_rows_with_real_own_history_rank_above_rows_without_it():
    with_history = universe_row("AAA")
    without = universe_row("BBB", sector_valuation_percentile=100.0)
    rows = module.build_rows(
        [with_history, without], {},
        entry_for=lambda ticker: cache_entry() if ticker == "AAA" else None)
    module.classify_rows(module.attach_revision_percentiles(rows))
    module.composite_percentiles(rows)

    payload = module.payload(rows, "2026-08-09T00:00:00Z")

    assert [result["ticker"] for result in payload["results"]] == ["AAA", "BBB"]
    assert payload["status"] == "success"
    assert payload["own_history"]["tickers_with_history"] == 1


def test_payload_reports_no_universe_rather_than_an_empty_success():
    payload = module.payload([], "2026-08-09T00:00:00Z")

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "NO_SCORED_UNIVERSE"


def test_coverage_note_states_the_window_it_actually_measured():
    rows = module.build_rows([universe_row()], {}, entry_for=lambda ticker: cache_entry())
    note = module.coverage_note(rows, rows)

    assert str(rows[0]["own_history_sessions"]) in note
    assert rows[0]["own_history_start"] in note


def test_the_published_head_is_capped_and_both_counts_are_stated(monkeypatch):
    monkeypatch.setattr(module, "PUBLISH_LIMIT", 2)
    rows = module.classify_rows(module.attach_revision_percentiles(module.build_rows(
        [universe_row(ticker) for ticker in ("AAA", "BBB", "CCC", "DDD")],
        {}, entry_for=lambda ticker: None)))
    module.composite_percentiles(rows)

    payload = module.payload(rows, "2026-08-09T00:00:00Z")

    assert len(payload["results"]) == 2
    assert payload["universe_scored"] == 4
    assert payload["publish_limit"] == 2
    assert "top 2 of 4" in payload["coverage_note"]
