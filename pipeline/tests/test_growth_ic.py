import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import growth_pit_store as gps  # noqa: E402
import growth_ic as gic  # noqa: E402


class BreakoutScoreTests(unittest.TestCase):
    def test_matches_the_hand_computed_javascript_formula(self):
        row = {"return_5d": 5.0, "return_20d": 15.0, "volume_ratio_60d": 1.2}
        self.assertAlmostEqual(gic.breakout_score(row), 61.4, places=6)

    def test_a_flat_week_does_not_clear_the_weekreturn_gate(self):
        self.assertIsNone(gic.breakout_score({"return_5d": 1.0, "return_20d": 15.0}))

    def test_a_negative_month_does_not_clear_the_monthreturn_gate(self):
        self.assertIsNone(gic.breakout_score({"return_5d": 5.0, "return_20d": -1.0}))

    def test_pace_that_was_already_faster_earlier_in_the_month_is_not_acceleration(self):
        # priorPace5d = (30-5)/15*5 = 8.33, which exceeds weekReturn -> acceleration <= 0
        self.assertIsNone(gic.breakout_score({"return_5d": 5.0, "return_20d": 30.0}))

    def test_missing_volume_falls_back_to_a_neutral_50(self):
        row = {"return_5d": 5.0, "return_20d": 15.0}
        # Same as the 1.2-volume-ratio case but with volume pinned to the neutral midpoint (50).
        self.assertAlmostEqual(gic.breakout_score(row), 65 * 0.4 + (50 + (5 - 10 / 3 * 1) * 2) * 0.3
                                + 68 * 0.2 + 50 * 0.1, places=6)


class EmergingScoreTests(unittest.TestCase):
    def test_matches_the_hand_computed_javascript_formula(self):
        row = {"return_5d": 1.0, "revenue_growth": 0.2, "relative_strength_20d": 2.0,
               "operating_margin_trend": 0.01, "recent_vol_10d": 0.01, "longer_vol_60d": 0.02}
        self.assertAlmostEqual(gic.emerging_score(row), 60.7 / 0.9, places=6)

    def test_a_week_return_above_2_is_excluded_it_already_cleared_breakout(self):
        row = {"return_5d": 3.0, "revenue_growth": 0.2, "relative_strength_20d": 2.0}
        self.assertIsNone(gic.emerging_score(row))

    def test_thin_revenue_growth_does_not_clear_the_gate(self):
        row = {"return_5d": 1.0, "revenue_growth": 0.01, "relative_strength_20d": 2.0}
        self.assertIsNone(gic.emerging_score(row))

    def test_missing_margin_trend_falls_back_to_a_neutral_50(self):
        row = {"return_5d": 1.0, "revenue_growth": 0.2, "relative_strength_20d": 2.0}
        expected = (80 * 0.35 + 50 * 0.2 + 58 * 0.2 + 50 * 0.15) / 0.9
        self.assertAlmostEqual(gic.emerging_score(row), expected, places=6)


class GrowthIcReportTests(unittest.TestCase):
    def test_zero_snapshots_reports_accumulating_with_no_number_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = gic.build_report(store_dir=tmp)
            for metric in gic.GRADED_SCREENS:
                self.assertEqual(report["metrics"][metric]["status"], "accumulating")
                self.assertIsNone(report["metrics"][metric]["mean_rank_ic"])

    def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers = "ABCDE"
            weeks = (4.0, 5.0, 6.0, 7.0, 8.0)  # all clear both the weekReturn and acceleration gates
            rows1 = [{"ticker": t, "price": 100.0, "is_etf": False,
                     "technical_detail": {"return_5d": week, "return_20d": 15.0, "volume_ratio_60d": 1.2},
                     "fundamental_detail": {"revenue_growth": 0.2}}
                    for t, week in zip(tickers, weeks)]
            end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
            rows2 = [{"ticker": t, "price": price, "is_etf": False,
                     "technical_detail": {"return_5d": 0.0}, "fundamental_detail": {}}
                    for t, price in zip(tickers, end_prices)]
            gps.append_snapshot(rows1, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
            gps.append_snapshot(rows2, recorded_at=datetime(2026, 3, 1, tzinfo=timezone.utc), store_dir=tmp)

            report = gic.build_report(store_dir=tmp)
            self.assertEqual(report["snapshot_dates_recorded"], 2)
            breakout = report["metrics"]["breakout_in_progress"]
            self.assertEqual(breakout["eligible_periods"], 1)
            self.assertEqual(breakout["status"], "accumulating")
            self.assertIsNone(breakout["mean_rank_ic"])


if __name__ == "__main__":
    unittest.main()
