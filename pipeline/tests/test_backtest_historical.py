import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import backtest_historical as bh


def _edgar_statements(revenue, net_income):
    return {"income": {"rows": {"Total Revenue": [revenue], "Net Income": [net_income]}}}


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


if __name__ == "__main__":
    unittest.main()
