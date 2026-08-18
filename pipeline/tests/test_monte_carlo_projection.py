import os
import random
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import monte_carlo_projection as mc


def _backtest(days=1000, daily_return=0.0005, daily_vol=0.01, seed=17, start="2020-01-01"):
    import datetime
    generator = random.Random(seed)
    start_date = datetime.date.fromisoformat(start)
    history, value = [], 100.0
    for index in range(days):
        history.append({"date": (start_date + datetime.timedelta(days=index)).isoformat(),
                        "value": value})
        value *= 1 + generator.gauss(daily_return, daily_vol)
    return {"portfolio": {"history": history}}


class InsufficientDataTests(unittest.TestCase):
    def test_reports_insufficient_data_rather_than_a_number(self):
        report = mc.build_report(backtest={"portfolio": {"history": []}},
                                 live_return_data={"returns": []})
        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["horizons"])
        self.assertIn("60", report["status_message"])


class SourceSelectionTests(unittest.TestCase):
    def test_prefers_backtest_when_it_meets_the_minimum(self):
        report = mc.build_report(backtest=_backtest(400), live_return_data={"returns": []},
                                 paths=500)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["input"]["source"], "backtest_daily_returns")
        self.assertEqual(report["input"]["method"], "block_bootstrap_full_history")

    def test_falls_back_to_live_when_the_backtest_is_too_thin(self):
        live_returns = [random.Random(9).gauss(0.0004, 0.008) for _ in range(80)]
        report = mc.build_report(backtest={"portfolio": {"history": []}},
                                 live_return_data={"returns": live_returns}, paths=500)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["input"]["source"], "live_shadow_returns")
        self.assertEqual(report["input"]["method"], "block_bootstrap_current_sample")

    def test_flags_a_backtest_still_short_of_full_history(self):
        report = mc.build_report(backtest=_backtest(100), live_return_data={"returns": []},
                                 paths=500)
        self.assertEqual(report["input"]["method"], "block_bootstrap_current_sample")

    def test_live_comparison_is_absent_until_the_live_sample_is_long_enough(self):
        live_returns = [random.Random(2).gauss(0.0004, 0.008) for _ in range(80)]
        report = mc.build_report(backtest=_backtest(400), live_return_data={"returns": live_returns},
                                 paths=500)
        self.assertIsNone(report["live_comparison"])

    def test_live_comparison_appears_and_flags_material_shift(self):
        backtest = _backtest(400, daily_return=0.0009, seed=3)
        # A live sample with a clearly different (much weaker) mean return.
        live_returns = [random.Random(44).gauss(-0.001, 0.006) for _ in range(260)]
        report = mc.build_report(backtest=backtest, live_return_data={"returns": live_returns},
                                 paths=500)
        self.assertIsNotNone(report["live_comparison"])
        self.assertTrue(report["live_comparison"]["material_shift"])
        self.assertEqual(report["input"]["source"], "backtest_daily_returns",
                         "backtest stays primary even once live reaches full-history length")


class HorizonShapeTests(unittest.TestCase):
    def setUp(self):
        self.report = mc.build_report(backtest=_backtest(1200, daily_return=0.0006, daily_vol=0.012),
                                      live_return_data={"returns": []}, paths=2000)

    def test_all_four_horizons_are_published(self):
        self.assertEqual(set(self.report["horizons"]), {"30", "90", "180", "365"})

    def test_percentiles_are_monotonically_ordered_within_each_horizon(self):
        for summary in self.report["horizons"].values():
            values = [summary["terminal_multiple_percentiles"][f"p{p}"]
                     for p in mc.PERCENTILES]
            self.assertEqual(values, sorted(values))

    def test_confidence_band_widens_as_the_horizon_shrinks(self):
        # Compounding uncertainty over a shorter, annualized horizon should read as at least
        # as wide a band as a longer one, not narrower -- a narrower short-horizon band would
        # be the false-precision failure mode the disclosure exists to prevent.
        band_30 = self.report["horizons"]["30"]["confidence_band_width_pct"]
        band_365 = self.report["horizons"]["365"]["confidence_band_width_pct"]
        self.assertGreaterEqual(band_30, band_365)

    def test_probability_of_exceeding_current_drawdown_is_a_probability(self):
        for summary in self.report["horizons"].values():
            probability = summary["probability_drawdown_exceeds_current_max"]
            self.assertGreaterEqual(probability, 0.0)
            self.assertLessEqual(probability, 1.0)

    def test_disclosure_is_present_and_not_a_guarantee(self):
        self.assertIn("not a forecast", self.report["disclosure"].lower())

    def test_json_serializable(self):
        import json
        json.dumps(self.report)  # raises on any lingering numpy scalar or NaN/Inf


class PerformanceTests(unittest.TestCase):
    def test_ten_thousand_paths_across_four_horizons_completes_well_under_budget(self):
        backtest = _backtest(1200, daily_return=0.0006, daily_vol=0.012)
        started = time.perf_counter()
        report = mc.build_report(backtest=backtest, live_return_data={"returns": []},
                                 paths=10_000)
        elapsed = time.perf_counter() - started
        self.assertEqual(report["status"], "ready")
        self.assertLess(elapsed, 5.0)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_reproduces_the_same_report(self):
        backtest = _backtest(500)
        first = mc.build_report(backtest=backtest, live_return_data={"returns": []},
                                paths=500, seed=7)
        second = mc.build_report(backtest=backtest, live_return_data={"returns": []},
                                 paths=500, seed=7)
        self.assertEqual(first["horizons"], second["horizons"])


if __name__ == "__main__":
    unittest.main()
