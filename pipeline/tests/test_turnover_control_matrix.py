import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import turnover_control_matrix as tcm


def summary(cagr, turnover, sharpe=0.7):
    return {
        "cagr": cagr, "annualized_volatility": 0.19, "sharpe_zero_rate": sharpe,
        "maximum_drawdown": -0.24, "mean_monthly_turnover": turnover,
        "estimated_transaction_cost": 3000.0, "unique_tickers_selected": 240,
        "final_value": 170000.0,
    }


class VariantGridTests(unittest.TestCase):
    def test_champion_is_the_no_flag_baseline(self):
        """Every comparison is against a run with no controls at all."""
        self.assertEqual(tcm.VARIANTS["champion"], [])

    def test_every_variant_has_a_description(self):
        self.assertEqual(set(tcm.VARIANTS), set(tcm.DESCRIPTIONS))

    def test_grid_is_small_and_fixed(self):
        """A wide sweep is the data-snooping this whole exercise exists to avoid."""
        self.assertLessEqual(len(tcm.VARIANTS), 12)


class ReportTests(unittest.TestCase):
    RESULTS = {
        "champion": summary(0.142, 0.547, 0.775),
        "smooth07": summary(0.1684, 0.439, 0.905),
        "buffer15": summary(0.1233, 0.442, 0.694),
    }

    def test_deltas_are_measured_against_the_champion(self):
        report = tcm.build_report(self.RESULTS)
        self.assertAlmostEqual(report["variants"]["smooth07"]["cagr_delta_vs_champion_pp"],
                               2.64, places=2)
        self.assertAlmostEqual(report["variants"]["buffer15"]["cagr_delta_vs_champion_pp"],
                               -1.87, places=2)
        self.assertEqual(report["variants"]["champion"]["cagr_delta_vs_champion_pp"], 0.0)

    def test_turnover_delta_is_reported_beside_return(self):
        """A control that lifts return while raising turnover is not a turnover control."""
        variants = tcm.build_report(self.RESULTS)["variants"]
        self.assertLess(variants["smooth07"]["turnover_delta_vs_champion_pp"], 0)

    def test_nothing_is_promoted_from_an_in_sample_run(self):
        report = tcm.build_report(self.RESULTS)
        self.assertEqual(report["promotion"]["promoted"], [])
        self.assertIn("walk-forward", report["promotion"]["reason"])

    def test_the_in_sample_and_multiple_testing_caveats_are_published(self):
        """The result is a diagnostic; the artifact has to say so itself."""
        interpretation = tcm.build_report(self.RESULTS)["interpretation"]
        self.assertIn("in_sample", interpretation)
        self.assertIn("multiple_testing", interpretation)
        self.assertIn("non_monotonicity_warning", interpretation)
        self.assertIn("not_comparable", interpretation)

    def test_ranking_is_by_cagr_descending(self):
        self.assertEqual(tcm.build_report(self.RESULTS)["ranked_by_cagr"],
                         ["smooth07", "champion", "buffer15"])


class CommittedReportTests(unittest.TestCase):
    def test_the_committed_matrix_records_its_own_limitations(self):
        if not os.path.exists(tcm.OUT_PATH):
            self.skipTest("matrix report not present in this checkout")
        with open(tcm.OUT_PATH, encoding="utf-8") as handle:
            report = json.load(handle)

        self.assertEqual(report["status"], "measured_in_sample")
        self.assertEqual(report["promotion"]["promoted"], [])
        # The universe is smaller than the published backtest's, so levels are not comparable.
        self.assertLess(report["universe_size"], 860)

    def test_the_committed_matrix_shows_the_non_monotonic_result(self):
        """Pinned because it is the reason nothing is promoted."""
        if not os.path.exists(tcm.OUT_PATH):
            self.skipTest("matrix report not present in this checkout")
        with open(tcm.OUT_PATH, encoding="utf-8") as handle:
            variants = json.load(handle)["variants"]

        self.assertLess(variants["hold3"]["cagr_delta_vs_champion_pp"], 0)
        self.assertGreater(variants["hold6"]["cagr_delta_vs_champion_pp"], 0)

    def test_tiered_costs_come_in_below_the_flat_assumption_on_this_universe(self):
        """The measured inversion of the cost concern, pinned so it cannot be misquoted."""
        if not os.path.exists(tcm.OUT_PATH):
            self.skipTest("matrix report not present in this checkout")
        with open(tcm.OUT_PATH, encoding="utf-8") as handle:
            variants = json.load(handle)["variants"]

        self.assertLess(variants["tiered_base"]["estimated_transaction_cost"],
                        variants["champion"]["estimated_transaction_cost"])
        self.assertLess(variants["tiered_stress"]["estimated_transaction_cost"],
                        variants["champion"]["estimated_transaction_cost"])


class OfflineBenchmarkTests(unittest.TestCase):
    def test_committed_benchmark_supplies_spy_without_network(self):
        """--cache-only used to load every symbol then fail at the benchmark fetch."""
        from backtest_monthly import committed_benchmark

        benchmark = committed_benchmark("SPY")
        self.assertIsNotNone(benchmark)
        self.assertGreater(len(benchmark["dates"]), 8000)
        self.assertEqual(len(benchmark["dates"]), len(benchmark["closes"]))
        self.assertEqual(benchmark["dates"], sorted(benchmark["dates"]))

    def test_a_missing_series_returns_none_for_the_callers_existing_error_path(self):
        from backtest_monthly import committed_benchmark

        self.assertIsNone(committed_benchmark("NOT-A-REAL-ETF"))


if __name__ == "__main__":
    unittest.main()
