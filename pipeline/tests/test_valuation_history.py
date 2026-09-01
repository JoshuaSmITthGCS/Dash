from datetime import date, timedelta

import valuation_history as module


def statement(periods, rows):
    return {"periods": periods, "rows": rows}


QUARTERS = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30",
            "2025-03-31", "2024-12-31"]


def cache_entry(dates=None, closes=None, shares=1000.0):
    dates = dates or [f"2025-01-{day:02d}" for day in range(1, 11)]
    closes = closes or [10.0] * len(dates)
    return {
        "dates": dates, "closes": closes,
        "income": statement(QUARTERS, {
            "Net Income": [10.0] * 7, "Total Revenue": [100.0] * 7,
            "EBIT": [20.0] * 7, "EBITDA": [30.0] * 7,
            "Diluted Average Shares": [shares] * 7,
        }),
        "balance": statement(QUARTERS, {
            "Total Debt": [50.0] * 7, "Cash And Cash Equivalents": [20.0] * 7,
            "Stockholders Equity": [200.0] * 7, "Tangible Book Value": [150.0] * 7,
            "Ordinary Shares Number": [shares, shares, shares, None, None, None, None],
        }),
        "cashflow": statement(QUARTERS, {"Free Cash Flow": [15.0] * 7}),
    }


def test_trailing_twelve_months_sums_four_consecutive_quarters():
    income = statement(QUARTERS, {"Net Income": [4.0, 3.0, 2.0, 1.0, 5.0, 6.0, 7.0]})

    trailing = module.trailing_twelve_months(income, ("Net Income",))

    assert trailing["2026-06-30"] == 10.0
    assert trailing["2026-03-31"] == 11.0
    # Only four windows exist in seven quarters; the oldest three cannot start one.
    assert set(trailing) == {"2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"}


def test_trailing_twelve_months_skips_windows_with_a_missing_quarter():
    income = statement(QUARTERS, {"Net Income": [4.0, 3.0, None, 1.0, 5.0, 6.0, 7.0]})

    trailing = module.trailing_twelve_months(income, ("Net Income",))

    assert "2026-06-30" not in trailing
    assert trailing["2025-09-30"] == 1.0 + 5.0 + 6.0 + 7.0


def test_annual_periods_are_not_summed_into_a_quadruple_year():
    annual = statement(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                       {"Net Income": [10.0, 9.0, 8.0, 7.0]})

    trailing = module.trailing_twelve_months(annual, ("Net Income",))

    assert trailing == {"2025-12-31": 10.0, "2024-12-31": 9.0,
                        "2023-12-31": 8.0, "2022-12-31": 7.0}


def test_fundamentals_are_only_effective_after_the_filing_deadline():
    fundamentals = module.point_in_time_fundamentals(cache_entry())

    for item in fundamentals:
        expected = date.fromisoformat(item["period_end"]) + timedelta(days=module.REPORTING_LAG_DAYS)
        assert item["effective_from"] == expected.isoformat()
    assert [item["period_end"] for item in fundamentals] == sorted(item["period_end"] for item in fundamentals)


def test_share_count_falls_back_to_the_income_statement_when_the_balance_sheet_is_null():
    fundamentals = module.point_in_time_fundamentals(cache_entry(shares=1000.0))
    oldest = fundamentals[0]

    assert oldest["period_end"] == "2025-09-30"
    assert oldest["balance"]["shares"] == 1000.0


def test_multiple_series_never_prices_a_day_against_a_statement_filed_later():
    # Trading days that all fall before the first statement can legitimately be used.
    entry = cache_entry(dates=["2025-10-01", "2025-10-02"], closes=[10.0, 11.0])

    assert module.multiple_series(entry) == {}


def test_multiple_series_tracks_price_and_reports_its_window():
    days = ["2025-11-14", "2025-11-17", "2025-11-18"]
    entry = cache_entry(dates=days, closes=[10.0, 20.0, 5.0])

    series = module.multiple_series(entry)

    earnings = series["price_to_earnings"]
    # TTM net income of 40 on 1000 shares: a $5 close is a market cap of 5,000, so 125x.
    assert earnings["history"] == [250.0, 500.0, 125.0]
    assert earnings["current"] == 125.0
    assert earnings["sessions"] == 3
    assert earnings["start"] == "2025-11-14"
    assert earnings["fundamental_steps"] == 1
    assert earnings["lower_is_cheaper"] is True


def test_multiple_series_counts_each_statement_that_takes_effect_inside_the_window():
    entry = cache_entry(dates=["2025-11-14", "2026-02-17", "2026-05-20"], closes=[10.0, 10.0, 10.0])

    assert module.multiple_series(entry)["price_to_earnings"]["fundamental_steps"] == 3


def test_negative_denominators_are_dropped_rather_than_ranked_as_cheap():
    entry = cache_entry(dates=["2025-11-14"], closes=[10.0])
    entry["income"]["rows"]["Net Income"] = [-10.0] * 7

    series = module.multiple_series(entry)

    assert "price_to_earnings" not in series
    assert "price_to_sales" in series


def test_enterprise_value_adds_debt_and_removes_cash():
    entry = cache_entry(dates=["2025-11-14"], closes=[10.0])

    series = module.multiple_series(entry)

    # Market cap 10,000 + debt 50 - cash 20 = 10,030, over TTM EBIT of 80.
    assert series["ev_to_ebit"]["current"] == 10030 / 80


def test_unreconciled_adr_produces_no_multiples_rather_than_a_wrong_market_cap():
    """Round-12 valuation audit: TSM's balance sheet reports its full ordinary-share count,
    not the ADS-equivalent count its USD ADR price implies (1 ADS = 5 ordinary shares). With
    no verified ratio in adr_registry, this must refuse to reconstruct market_cap = close *
    ordinary_shares (which would overstate it roughly 5x) rather than publish a wrong value.
    """
    entry = cache_entry(dates=["2025-11-14"], closes=[10.0])

    series = module.multiple_series(entry, ticker="TSM")

    assert series == {}


def test_unregistered_ticker_is_unaffected_by_the_adr_guard():
    entry = cache_entry(dates=["2025-11-14"], closes=[10.0])

    series = module.multiple_series(entry, ticker="AAPL")

    assert series == module.multiple_series(entry)


def test_verified_adr_ratio_converts_ordinary_shares_before_pricing(monkeypatch):
    import adr_registry

    monkeypatch.setattr(adr_registry, "_REGISTRY", {
        "FAKE": {"is_adr": True, "adr_ratio": 5, "verified": True}})
    entry = cache_entry(dates=["2025-11-14"], closes=[10.0], shares=5000.0)

    series = module.multiple_series(entry, ticker="FAKE")
    unconverted = module.multiple_series(entry)

    # 5000 ordinary shares / 5-to-1 ratio = 1000 ADS-equivalent shares: market cap 10,000
    # against TTM net income of 40 is a P/E of 250x, one fifth of the unconverted 1250x you'd
    # get by (wrongly) pricing all 5000 ordinary shares at the ADR price.
    assert series["price_to_earnings"]["current"] == 250.0
    assert unconverted["price_to_earnings"]["current"] == 1250.0
    assert unconverted["price_to_earnings"]["current"] == series["price_to_earnings"]["current"] * 5


def test_applicable_metrics_gate_on_both_depth_and_statement_changes():
    available = {"price_to_earnings": {"sessions": 200, "fundamental_steps": 2},
                 "ev_to_ebit": {"sessions": 200, "fundamental_steps": 1},
                 "price_to_sales": {"sessions": 10, "fundamental_steps": 4}}

    applicable = module.applicable_metrics("general", available)

    assert set(applicable) == {"price_to_earnings"}


def test_banks_are_never_measured_on_enterprise_value():
    available = {name: {"sessions": 200, "fundamental_steps": 2}
                 for name in module.LOWER_IS_CHEAPER}

    applicable = module.applicable_metrics("bank", available)

    assert not any(name.startswith("ev_") for name in applicable)
    assert "price_to_book" in applicable


def test_profile_falls_back_to_sector_when_no_industry_label_exists():
    assert module.profile_for({"ticker": "X", "sector": "Financial Services"}) == "financial"
    assert module.profile_for({"ticker": "X", "sector": "Utilities"}) == "utility"
    assert module.profile_for({"ticker": "X", "sector": "Technology"}) == "general"


def test_profile_classifier_wins_over_the_sector_fallback():
    row = {"ticker": "X", "sector": "Financial Services", "industry": "Banks - Regional"}

    assert module.profile_for(row) == "bank"
