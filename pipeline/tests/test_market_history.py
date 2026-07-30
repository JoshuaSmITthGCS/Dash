import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import market_history as mh


def sessions(count, start=date(2025, 1, 1)):
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


class GridTests(unittest.TestCase):
    def test_grid_is_weekly_and_ends_on_the_latest_session(self):
        dates = sessions(200)
        grid = mh.weekly_grid(dates)
        self.assertEqual(grid[-1], dates[-1])
        self.assertLessEqual(len(grid), 53)
        self.assertEqual(len(set(grid)), len(grid))

    def test_grid_of_nothing_is_empty(self):
        self.assertEqual(mh.weekly_grid([]), [])


class ChartGridTests(unittest.TestCase):
    def test_recent_sessions_stay_at_daily_resolution(self):
        dates = sessions(200)
        grid = mh.chart_grid(dates, daily_days=45)
        recent = set(dates[-45:])
        self.assertTrue(recent.issubset(set(grid)))

    def test_older_sessions_fall_back_to_weekly(self):
        dates = sessions(200)
        grid = mh.chart_grid(dates, daily_days=45)
        # Every daily point beyond the recent window would make this basically the full
        # series again; the point of the older half is to stay sparse.
        older_grid_points = [d for d in grid if d < dates[-45]]
        self.assertLess(len(older_grid_points), 200 - 45)

    def test_grid_ends_on_the_latest_session_and_has_no_duplicates(self):
        dates = sessions(200)
        grid = mh.chart_grid(dates)
        self.assertEqual(grid[-1], dates[-1])
        self.assertEqual(len(set(grid)), len(grid))
        self.assertEqual(grid, sorted(grid))

    def test_short_series_is_all_daily(self):
        dates = sessions(10)
        self.assertEqual(mh.chart_grid(dates, daily_days=45), dates)

    def test_grid_of_nothing_is_empty(self):
        self.assertEqual(mh.chart_grid([]), [])


class AlignmentTests(unittest.TestCase):
    def test_gaps_carry_the_last_known_close_forward(self):
        dates = ["2025-01-06", "2025-01-13", "2025-01-27"]
        closes = [100.0, 110.0, 130.0]
        grid = ["2025-01-06", "2025-01-13", "2025-01-20", "2025-01-27"]
        # The missing 20th holds at the prior close rather than inventing a value or a hole.
        self.assertEqual(mh.sample_on(dates, closes, grid), [100.0, 110.0, 110.0, 130.0])

    def test_grid_points_before_the_listing_stay_empty(self):
        aligned = mh.sample_on(["2025-06-02"], [50.0], ["2025-01-06", "2025-06-02"])
        self.assertEqual(aligned, [None, 50.0])

    def test_a_short_overlap_produces_no_series_at_all(self):
        dates, closes = sessions(5), [100.0] * 5
        self.assertIsNone(mh.series_payload(dates, closes, mh.weekly_grid(dates)))


class HypotheticalTests(unittest.TestCase):
    def test_growth_series_starts_at_the_standard_basis(self):
        dates = sessions(200)
        closes = [100.0 + index * 0.5 for index in range(200)]
        payload = mh.series_payload(dates, closes, mh.weekly_grid(dates))
        self.assertEqual(payload["growth"][0], mh.BASIS)
        self.assertGreater(payload["growth"][-1], mh.BASIS)

    def test_beating_the_benchmark_reads_as_dollars_ahead(self):
        result = mh.hypothetical_vs_benchmark([500.0, 600.0, 750.0], [500.0, 520.0, 550.0])
        self.assertEqual(result["stock_value"], 750.0)
        self.assertEqual(result["benchmark_value"], 550.0)
        self.assertEqual(result["stock_return_pct"], 50.0)
        self.assertEqual(result["benchmark_return_pct"], 10.0)
        self.assertEqual(result["excess_return_pct"], 40.0)
        self.assertEqual(result["dollars_ahead"], 200.0)

    def test_lagging_the_benchmark_reads_as_dollars_behind(self):
        result = mh.hypothetical_vs_benchmark([500.0, 400.0], [500.0, 600.0])
        self.assertLess(result["dollars_ahead"], 0)
        self.assertLess(result["excess_return_pct"], 0)

    def test_no_series_means_no_comparison(self):
        self.assertIsNone(mh.hypothetical_vs_benchmark([], [500.0, 600.0]))


class SectorPercentileTests(unittest.TestCase):
    def test_cheapest_in_sector_ranks_highest(self):
        rows = [
            {"ticker": "A", "sector": "Technology", "categories": {"valuation": 90}},
            {"ticker": "B", "sector": "Technology", "categories": {"valuation": 70}},
            {"ticker": "C", "sector": "Technology", "categories": {"valuation": 50}},
            {"ticker": "D", "sector": "Technology", "categories": {"valuation": 30}},
        ]
        percentiles = mh.sector_percentiles(rows)
        self.assertEqual(percentiles["A"], 100.0)
        self.assertEqual(percentiles["D"], 0.0)

    def test_sectors_are_ranked_independently(self):
        rows = [{"ticker": f"T{i}", "sector": "Technology", "categories": {"valuation": 60 + i}} for i in range(4)]
        rows += [{"ticker": f"U{i}", "sector": "Utilities", "categories": {"valuation": 10 + i}} for i in range(4)]
        percentiles = mh.sector_percentiles(rows)
        # A weak utility can still be the cheapest utility; it is not compared against tech.
        self.assertEqual(percentiles["U3"], 100.0)
        self.assertEqual(percentiles["T3"], 100.0)

    def test_thin_sectors_get_no_percentile_rather_than_a_meaningless_one(self):
        rows = [{"ticker": "A", "sector": "Energy", "categories": {"valuation": 80}},
                {"ticker": "B", "sector": "Energy", "categories": {"valuation": 40}}]
        self.assertEqual(mh.sector_percentiles(rows), {})


if __name__ == "__main__":
    unittest.main()
