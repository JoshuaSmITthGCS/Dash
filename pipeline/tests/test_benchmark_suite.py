import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import benchmark_suite as bs
from p0_q1_benchmark_factor_report import ols_newey_west


def _monthly(values, start_month=1, start_year=2022):
    """Month-keyed return series."""
    series, month, year = {}, start_month, start_year
    for value in values:
        series[f"{year}-{month:02d}"] = value
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return series


class RegressionKeyTests(unittest.TestCase):
    """Guards the defect where a wrong key silently published 0.00 for every t-statistic."""

    def test_ols_exposes_the_key_this_module_reads(self):
        result = ols_newey_west(np.array([0.01, 0.02, -0.01, 0.03] * 8),
                                {"benchmark": np.array([0.01, 0.015, -0.02, 0.02] * 8)})
        self.assertIn("newey_west_t_statistic", result["coefficients"]["alpha"])
        self.assertIn("classical_t_statistic", result["coefficients"]["alpha"])

    def test_regression_returns_a_real_t_statistic_not_a_default(self):
        strategy = _monthly([0.02, 0.01, -0.01, 0.03] * 8)
        benchmark = _monthly([0.01, 0.01, -0.02, 0.02] * 8)
        regression = bs.regress_on_benchmark(strategy, benchmark)

        self.assertIsNotNone(regression["newey_west_t_statistic"])
        self.assertNotEqual(regression["newey_west_t_statistic"], 0.0)

    def test_a_strategy_that_is_a_constant_uplift_shows_positive_alpha(self):
        benchmark = _monthly([0.01, 0.02, -0.015, 0.005] * 8)
        strategy = {month: value + 0.01 for month, value in benchmark.items()}
        regression = bs.regress_on_benchmark(strategy, benchmark)

        self.assertAlmostEqual(regression["beta"], 1.0, places=3)
        self.assertAlmostEqual(regression["monthly_alpha"], 0.01, places=4)
        self.assertGreater(regression["newey_west_t_statistic"], 2.0)

    def test_a_strategy_identical_to_its_benchmark_has_no_alpha(self):
        benchmark = _monthly([0.01, 0.02, -0.015, 0.005] * 8)
        regression = bs.regress_on_benchmark(dict(benchmark), benchmark)

        self.assertAlmostEqual(regression["monthly_alpha"], 0.0, places=6)
        self.assertAlmostEqual(regression["r_squared"], 1.0, places=6)

    def test_too_little_overlap_reports_a_status_instead_of_a_number(self):
        regression = bs.regress_on_benchmark(_monthly([0.01] * 5), _monthly([0.01] * 5))
        self.assertEqual(regression["status"], "insufficient_overlap")
        self.assertNotIn("newey_west_t_statistic", regression)


class BlendTests(unittest.TestCase):
    def test_blend_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(bs.BLEND["weights"].values()), 1.0)

    def test_blend_is_fixed_in_advance_not_fitted(self):
        self.assertEqual(set(bs.BLEND["weights"].values()), {0.5})


class CommittedDataTests(unittest.TestCase):
    def test_every_configured_benchmark_is_committed(self):
        missing = [ticker for ticker in bs.BENCHMARKS if not bs.available(ticker)]
        self.assertEqual(missing, [], f"missing committed ETF history for {missing}")

    def test_report_prices_every_leg_the_same_way_as_the_published_spy_leg(self):
        if not os.path.exists(bs.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        report = bs.build_report()

        self.assertEqual(report["benchmarks_unavailable"], [])
        self.assertGreaterEqual(report["summary"]["benchmarks_compared"], len(bs.BENCHMARKS))
        for name, leg in report["benchmarks"].items():
            with self.subTest(benchmark=name):
                self.assertIsNotNone(leg["cagr"])
                self.assertIsNotNone(
                    leg["strategy_versus_this_benchmark"]["newey_west_t_statistic"])

    def test_the_published_spy_cagr_is_reproduced_within_rounding(self):
        """A sanity check that this module's return path matches the committed backtest's."""
        if not os.path.exists(bs.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        import json
        with open(bs.BACKTEST_PATH) as handle:
            expected = json.load(handle)["benchmark_spy"]["metrics"]["cagr"]
        report = bs.build_report()
        self.assertAlmostEqual(report["benchmarks"]["SPY"]["cagr"], expected, places=6)

    def test_summary_only_claims_significance_at_the_conventional_bar(self):
        if not os.path.exists(bs.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        report = bs.build_report()
        for name in report["summary"]["significant_positive_alpha_against"]:
            regression = report["benchmarks"][name]["strategy_versus_this_benchmark"]
            self.assertGreaterEqual(abs(regression["newey_west_t_statistic"]), 2.0)
            self.assertGreater(regression["monthly_alpha"], 0)

    def test_sector_neutral_composite_is_declared_unbuilt_with_its_reason(self):
        if not os.path.exists(bs.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        composite = bs.build_report()["sector_neutral_composite"]
        self.assertFalse(composite["built"])
        self.assertIn("fabrication", composite["reason"])


if __name__ == "__main__":
    unittest.main()
