import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import backtest_historical as bh


def _edgar_statements(revenue, net_income):
    return {"income": {"rows": {"Total Revenue": [revenue], "Net Income": [net_income]}}}


def _edgar_full_statements(*, revenue_now, revenue_prior, net_income_now, net_income_prior,
                           equity=None, total_debt=None, current_assets=None,
                           current_liabilities=None, diluted_shares=None):
    """A full edgar_ttm_statements() return: index 0 = TTM as-of, index 1 = one year prior --
    everything build_snapshot's start_idx-is-None branch needs to score a period entirely
    outside Yahoo's cached quarterly window.
    """
    periods = ["2024-06-30", "2023-06-30"]
    return {
        "income": {"periods": periods, "rows": {
            "Total Revenue": [revenue_now, revenue_prior],
            "Net Income": [net_income_now, net_income_prior],
            "Diluted Average Shares": [diluted_shares, diluted_shares],
        }},
        "balance": {"periods": periods, "rows": {
            "Stockholders Equity": [equity, equity],
            "Total Debt": [total_debt, total_debt],
            "Current Assets": [current_assets, current_assets],
            "Current Liabilities": [current_liabilities, current_liabilities],
        }},
        "cashflow": {"periods": periods, "rows": {}},
    }


def quarterly_ticker_data(symbol="AAA", *, quarters=4, sector="Technology", industry="Software",
                          revenue_per_quarter=100.0, net_income_per_quarter=10.0):
    """Minimal ticker_data with only ``quarters`` quarters of statement history -- enough for
    one current TTM, not enough for a year-ago TTM (needs 8), matching the real Yahoo
    short-history case Round 11 Priority 4 wires an EDGAR fallback around.
    """
    # Real calendar quarter-ends, newest first, so ``most_recent_known_index`` at
    # as_of=2026-08-15/report_lag_days=45 lands on index 0 (2026-06-30 + 45d = 2026-08-14,
    # already known) -- not some later index a same-day-of-month arithmetic shortcut could
    # accidentally push into the future relative to as_of.
    all_period_ends = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30",
                       "2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30"]
    periods = all_period_ends[:quarters]
    income_rows = {
        "Total Revenue": [revenue_per_quarter] * quarters,
        "Net Income": [net_income_per_quarter] * quarters,
    }
    balance_rows = {
        "Stockholders Equity": [500.0] * quarters,
        "Total Assets": [1000.0] * quarters,
        "Current Assets": [300.0] * quarters,
        "Current Liabilities": [150.0] * quarters,
        "Total Debt": [200.0] * quarters,
    }
    cashflow_rows = {
        "Operating Cash Flow": [15.0] * quarters,
        "Capital Expenditure": [-2.0] * quarters,
    }
    dates = [f"2024-{month:02d}-01" for month in range(1, 13)] + \
            [f"2025-{month:02d}-01" for month in range(1, 13)] + \
            [f"2026-{month:02d}-01" for month in range(1, 9)]
    closes = [10.0 + i * 0.01 for i in range(len(dates))]
    return {
        "symbol": symbol, "name": symbol, "sector": sector, "industry": industry,
        "is_etf": False, "current_shares_outstanding": 100.0,
        "dates": dates, "closes": closes, "raw_closes": closes,
        "volumes": [1000.0] * len(dates),
        "income": {"periods": periods, "rows": income_rows},
        "balance": {"periods": periods, "rows": balance_rows},
        "cashflow": {"periods": periods, "rows": cashflow_rows},
    }


class EdgarPitGrowthFallbackTests(unittest.TestCase):
    def test_fills_revenue_and_earnings_growth_when_both_are_missing(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            mocked.side_effect = [
                _edgar_statements(440.0, None),   # revenue, as_of
                _edgar_statements(400.0, None),   # revenue, one year prior
                _edgar_statements(None, 44.0),    # earnings, as_of
                _edgar_statements(None, 40.0),    # earnings, one year prior
            ]
            revenue_growth, earnings_growth = bh.edgar_pit_growth_fallback(
                ticker_data, date(2026, 8, 1), need_revenue=True, need_earnings=True)
        self.assertAlmostEqual(revenue_growth, 0.1)
        self.assertAlmostEqual(earnings_growth, 0.1)

    def test_skips_revenue_growth_but_not_earnings_growth_for_an_excluded_profile(self):
        ticker_data = quarterly_ticker_data(sector="Financial Services",
                                            industry="Insurance - Property & Casualty")
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            mocked.side_effect = [
                _edgar_statements(None, 44.0),
                _edgar_statements(None, 40.0),
            ]
            revenue_growth, earnings_growth = bh.edgar_pit_growth_fallback(
                ticker_data, date(2026, 8, 1), need_revenue=True, need_earnings=True)
        self.assertIsNone(revenue_growth)
        self.assertAlmostEqual(earnings_growth, 0.1)
        # Only the two earnings calls were made -- no revenue lookup attempted at all.
        self.assertEqual(mocked.call_count, 2)

    def test_a_disabled_flag_short_circuits_before_any_edgar_call(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "DISABLE_EDGAR_PIT_BACKTEST_GROWTH", True), \
             patch.object(bh, "edgar_ttm_statements") as mocked:
            revenue_growth, earnings_growth = bh.edgar_pit_growth_fallback(
                ticker_data, date(2026, 8, 1), need_revenue=True, need_earnings=True)
        self.assertIsNone(revenue_growth)
        self.assertIsNone(earnings_growth)
        mocked.assert_not_called()

    def test_nothing_needed_short_circuits_before_any_edgar_call(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            result = bh.edgar_pit_growth_fallback(
                ticker_data, date(2026, 8, 1), need_revenue=False, need_earnings=False)
        self.assertEqual(result, (None, None))
        mocked.assert_not_called()

    def test_a_pit_store_read_failure_never_raises(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "edgar_ttm_statements", side_effect=RuntimeError("boom")):
            revenue_growth, earnings_growth = bh.edgar_pit_growth_fallback(
                ticker_data, date(2026, 8, 1), need_revenue=True, need_earnings=True)
        self.assertIsNone(revenue_growth)
        self.assertIsNone(earnings_growth)


class EdgarPitStatementFallbackTests(unittest.TestCase):
    def test_returns_the_full_income_balance_cashflow_dicts_when_edgar_has_data(self):
        ticker_data = quarterly_ticker_data()
        fixture = _edgar_full_statements(revenue_now=440.0, revenue_prior=400.0,
                                         net_income_now=44.0, net_income_prior=40.0)
        with patch.object(bh, "edgar_ttm_statements", return_value=fixture):
            income, balance, cashflow = bh.edgar_pit_statement_fallback(
                ticker_data, date(2020, 1, 1))
        self.assertEqual(income, fixture["income"])
        self.assertEqual(balance, fixture["balance"])
        self.assertEqual(cashflow, fixture["cashflow"])

    def test_a_disabled_flag_short_circuits_before_any_edgar_call(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS", True), \
             patch.object(bh, "edgar_ttm_statements") as mocked:
            result = bh.edgar_pit_statement_fallback(ticker_data, date(2020, 1, 1))
        self.assertEqual(result, (None, None, None))
        mocked.assert_not_called()

    def test_no_edgar_history_reaching_back_that_far_returns_all_none(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "edgar_ttm_statements", return_value=None):
            result = bh.edgar_pit_statement_fallback(ticker_data, date(2020, 1, 1))
        self.assertEqual(result, (None, None, None))

    def test_a_pit_store_read_failure_never_raises(self):
        ticker_data = quarterly_ticker_data()
        with patch.object(bh, "edgar_ttm_statements", side_effect=RuntimeError("boom")):
            result = bh.edgar_pit_statement_fallback(ticker_data, date(2020, 1, 1))
        self.assertEqual(result, (None, None, None))


class BuildSnapshotEdgarStatementWiringTests(unittest.TestCase):
    """Round 11 Priority 7: an as_of entirely outside Yahoo's cached window (start_idx None)
    used to leave income_ttm/balance_now/cashflow_ttm empty, so every ratio besides growth
    and price-based technicals silently went to None. These cover the fix.
    """

    def test_ratios_beyond_growth_populate_from_edgar_when_yahoo_has_no_quarters_at_all(self):
        ticker_data = quarterly_ticker_data(quarters=0)
        fixture = _edgar_full_statements(
            revenue_now=440.0, revenue_prior=400.0, net_income_now=44.0, net_income_prior=40.0,
            equity=500.0, total_debt=200.0, current_assets=300.0, current_liabilities=150.0,
            diluted_shares=50.0)
        with patch.object(bh, "edgar_ttm_statements", return_value=fixture) as mocked:
            snap, _, _ = bh.build_snapshot(ticker_data, date(2024, 6, 15), report_lag_days=45,
                                           allow_current_shares=False, allow_empty_fundamentals=True)
        # One call for the statements themselves -- growth reads off the same income_ttm,
        # so it must not need a second, separate edgar_pit_growth_fallback lookup.
        self.assertEqual(mocked.call_count, 1)
        self.assertAlmostEqual(snap["revenue_growth"], 0.1)
        self.assertAlmostEqual(snap["earnings_growth"], 0.1)
        self.assertAlmostEqual(snap["return_on_equity"], 44.0 / 500.0)
        self.assertAlmostEqual(snap["debt_to_equity"], 200.0 / 500.0, places=2)
        self.assertAlmostEqual(snap["current_ratio"], 300.0 / 150.0, places=2)
        self.assertAlmostEqual(snap["profit_margin"], 44.0 / 440.0)

    def test_market_cap_falls_back_to_diluted_shares_when_no_balance_sheet_share_count_exists(self):
        # edgar_enrichment.BALANCE_ROWS never carries a shares-outstanding concept, so
        # balance_shares alone would leave market_cap (and every ratio needing it) at None.
        ticker_data = quarterly_ticker_data(quarters=0)
        fixture = _edgar_full_statements(
            revenue_now=440.0, revenue_prior=400.0, net_income_now=44.0, net_income_prior=40.0,
            diluted_shares=50.0)
        with patch.object(bh, "edgar_ttm_statements", return_value=fixture):
            snap, _, _ = bh.build_snapshot(ticker_data, date(2024, 6, 15), report_lag_days=45,
                                           allow_current_shares=False, allow_empty_fundamentals=True)
        self.assertAlmostEqual(snap["market_cap"], snap["price"] * 50.0)

    def test_still_falls_back_to_empty_statements_when_edgar_has_nothing_either(self):
        ticker_data = quarterly_ticker_data(quarters=0)
        with patch.object(bh, "edgar_ttm_statements", return_value=None):
            snap, _, _ = bh.build_snapshot(ticker_data, date(2024, 6, 15), report_lag_days=45,
                                           allow_empty_fundamentals=True)
        self.assertIsNone(snap["return_on_equity"])
        self.assertIsNone(snap["revenue_growth"])

    def test_a_yahoo_native_quarter_never_consults_edgar_statements_at_all(self):
        ticker_data = quarterly_ticker_data(quarters=8)
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45)
        mocked.assert_not_called()


class BuildSnapshotEdgarWiringTests(unittest.TestCase):
    def test_build_snapshot_fills_growth_from_edgar_when_yahoo_history_is_too_short(self):
        # Only 4 quarters of Yahoo history -- enough for the current TTM, not the year-ago
        # one, so Yahoo alone leaves both growth figures None.
        ticker_data = quarterly_ticker_data(quarters=4)
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            mocked.side_effect = [
                _edgar_statements(440.0, None),
                _edgar_statements(400.0, None),
                _edgar_statements(None, 44.0),
                _edgar_statements(None, 40.0),
            ]
            snap, _, _ = bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45)
        self.assertAlmostEqual(snap["revenue_growth"], 0.1)
        self.assertAlmostEqual(snap["earnings_growth"], 0.1)

    def test_build_snapshot_never_overwrites_growth_yahoo_already_resolved(self):
        # 8 quarters: both the current and year-ago TTM are available from Yahoo alone, so
        # the EDGAR fallback must not be consulted at all.
        ticker_data = quarterly_ticker_data(quarters=8, revenue_per_quarter=100.0,
                                            net_income_per_quarter=10.0)
        with patch.object(bh, "edgar_ttm_statements") as mocked:
            snap, _, _ = bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45)
        mocked.assert_not_called()
        # Flat quarter-over-quarter values: TTM(now) == TTM(year-ago), so growth is exactly 0.
        self.assertAlmostEqual(snap["revenue_growth"], 0.0)
        self.assertAlmostEqual(snap["earnings_growth"], 0.0)


class AdrShareCountGuardTests(unittest.TestCase):
    """Round-12 valuation audit: a balance-sheet share count is an ADR's ordinary-share
    count, not the ADS-equivalent count its USD price implies. build_snapshot must not
    silently multiply the two together for a known, unreconciled ADR.
    """

    def _ticker_data_with_balance_shares(self, symbol, ordinary_shares):
        ticker_data = quarterly_ticker_data(symbol=symbol, quarters=4)
        ticker_data["balance"]["rows"]["Ordinary Shares Number"] = [ordinary_shares] * 4
        return ticker_data

    def test_known_unreconciled_adr_leaves_market_cap_unresolved(self):
        ticker_data = self._ticker_data_with_balance_shares("TSM", 5_000_000_000.0)
        snap, _, _ = bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45,
                                       allow_current_shares=False)
        self.assertIsNone(snap["market_cap"])

    def test_ordinary_us_ticker_is_unaffected(self):
        ticker_data = self._ticker_data_with_balance_shares("AAA", 100.0)
        snap, _, _ = bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45,
                                       allow_current_shares=False)
        self.assertAlmostEqual(snap["market_cap"], snap["price"] * 100.0)

    def test_verified_ratio_converts_rather_than_blocking(self):
        import adr_registry
        original = adr_registry._REGISTRY
        adr_registry._REGISTRY = {"FAKE": {"is_adr": True, "adr_ratio": 5, "verified": True}}
        try:
            ticker_data = self._ticker_data_with_balance_shares("FAKE", 500.0)
            snap, _, _ = bh.build_snapshot(ticker_data, date(2026, 8, 15), report_lag_days=45,
                                           allow_current_shares=False)
        finally:
            adr_registry._REGISTRY = original
        self.assertAlmostEqual(snap["market_cap"], snap["price"] * 100.0)  # 500 / 5 = 100


if __name__ == "__main__":
    unittest.main()
