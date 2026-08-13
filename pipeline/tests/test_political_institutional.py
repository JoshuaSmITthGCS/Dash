from datetime import date

from political_institutional import (coverage, institutional_points, rank_disclosed_trades,
                                     visible_congress_rows, visible_institutional_rows)


def purchase(symbol, disclosure_date, *, representative="Rep A", amount_lower=50000.0,
             transaction_date="2026-01-05", flags=None, transaction_type="Purchase",
             asset_type="Stock"):
    return {"symbol": symbol, "disclosure_date": disclosure_date,
            "transaction_date": transaction_date, "representative": representative,
            "amount_lower": amount_lower, "transaction_type": transaction_type,
            "asset_type": asset_type, "flags": flags or []}


def filing(ticker, as_of, magnitude, *, managers_added=3, flag="ACCUMULATION"):
    return {"ticker": ticker, "as_of": as_of, "undecayed_magnitude": magnitude,
            "managers_added": managers_added, "managers_dropped": 0, "flag": flag}


def test_a_trade_is_visible_on_its_disclosure_date_not_its_transaction_date():
    # The whole point of the gate: this purchase happened in January and became public in
    # July. Reading it in February is the leak that would fabricate a perfect backtest.
    rows = [purchase("AAA", "2026-07-01", transaction_date="2026-01-05")]

    assert visible_congress_rows(rows, "2026-02-01") == []
    assert len(visible_congress_rows(rows, "2026-07-01")) == 1
    assert len(visible_congress_rows(rows, "2026-08-01")) == 1


def test_a_row_without_a_disclosure_date_is_dropped_rather_than_dated_by_its_trade():
    rows = [purchase("AAA", None, transaction_date="2026-01-05")]

    assert visible_congress_rows(rows, "2026-12-31") == []


def test_sales_and_non_equity_disclosures_do_not_enter_a_long_only_selection():
    rows = [
        purchase("AAA", "2026-07-01", transaction_type="Sale (Full)"),
        purchase("BBB", "2026-07-01", asset_type="Corporate Bond"),
        purchase("CCC", "2026-07-01"),
    ]

    assert [row["symbol"] for row in visible_congress_rows(rows, "2026-07-02")] == ["CCC"]


def test_institutional_rows_are_gated_on_filing_date_and_decay_with_lag():
    rows = [filing("AAA", "2026-06-01", 2.0)]

    assert visible_institutional_rows(rows, "2026-05-31") == []
    assert len(visible_institutional_rows(rows, "2026-06-01")) == 1

    fresh = institutional_points(rows[0], "2026-06-01")
    stale = institutional_points(rows[0], "2026-08-01")
    assert fresh > stale >= 0


def test_score_sums_both_sources_and_stays_decomposable():
    congress = [purchase("AAA", "2026-07-01")]
    institutional = [filing("AAA", "2026-07-01", 2.0)]

    (row,) = rank_disclosed_trades(congress, institutional, as_of="2026-07-02")

    assert row["ticker"] == "AAA"
    assert row["political_points"] > 0
    assert row["institutional_points"] > 0
    assert row["score"] == round(row["political_points"] + row["institutional_points"], 4)


def test_tied_scores_break_on_freshness_and_size_rather_than_alphabetically():
    # Every one of these earns identical breadth points from a single member, so score alone
    # leaves them tied and a ticker-only tiebreak would hand the book to ZZZZ's alphabetical
    # neighbours instead of to the freshest, largest disclosures.
    congress = [
        purchase("ZZZZ", "2026-07-20", representative="Rep A", amount_lower=250000.0),
        purchase("AAAA", "2026-07-01", representative="Rep B", amount_lower=250000.0),
        purchase("MMMM", "2026-07-20", representative="Rep C", amount_lower=16000.0),
    ]

    ranked = rank_disclosed_trades(congress, [], as_of="2026-07-21")

    assert [row["ticker"] for row in ranked] == ["ZZZZ", "MMMM", "AAAA"]
    assert [row["rank"] for row in ranked] == [1, 2, 3]


def test_immaterial_purchases_produce_no_selection_at_all():
    # congress_signal declares a $15,000 material floor. Everything below it scores zero, and
    # a period of only such trades must hold cash rather than rank a list of zeros.
    congress = [purchase("AAA", "2026-07-01", amount_lower=1001.0)]

    assert rank_disclosed_trades(congress, [], as_of="2026-07-02") == []


def test_universe_restriction_drops_untradable_disclosed_symbols():
    congress = [purchase("AAA", "2026-07-01"), purchase("BBB", "2026-07-01")]

    ranked = rank_disclosed_trades(congress, [], as_of="2026-07-02", universe={"AAA"})

    assert [row["ticker"] for row in ranked] == ["AAA"]


def test_breadth_across_members_outranks_a_single_disclosure():
    congress = [
        purchase("AAA", "2026-07-20", representative="Rep A"),
        purchase("AAA", "2026-07-20", representative="Rep B"),
        purchase("BBB", "2026-07-20", representative="Rep C"),
    ]

    ranked = rank_disclosed_trades(congress, [], as_of="2026-07-21")

    assert ranked[0]["ticker"] == "AAA"
    assert ranked[0]["members_buying"] == 2
    assert ranked[1]["members_buying"] == 1


def test_coverage_reports_the_history_that_actually_exists():
    congress = [purchase("AAA", "2026-06-10"), purchase("BBB", "2026-07-02")]
    institutional = [filing("AAA", "2026-05-15", 1.0)]

    result = coverage(congress, institutional)

    assert result["congress_disclosures"] == 2
    assert result["congress_first_disclosure"] == "2026-06-10"
    assert result["congress_last_disclosure"] == "2026-07-02"
    assert result["congress_distinct_disclosure_months"] == 2
    assert result["institutional_distinct_filing_dates"] == 1


def test_date_objects_and_strings_are_accepted_interchangeably():
    congress = [purchase("AAA", "2026-07-01")]

    assert rank_disclosed_trades(congress, [], as_of=date(2026, 7, 2)) == \
        rank_disclosed_trades(congress, [], as_of="2026-07-02")
