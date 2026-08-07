import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from p0_q1_benchmark_factor_report import (month_end_values, monthly_returns,
                                           ols_newey_west, sector_coverage)


class MonthEndValuesTests(unittest.TestCase):
    def test_keeps_the_last_observation_per_month(self):
        dates = ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-29"]
        values = [100.0, 101.0, 102.0, 110.0]
        months, values_out = month_end_values(dates, values)
        self.assertEqual(months, ["2024-01", "2024-02"])
        self.assertEqual(values_out, [101.0, 110.0])


class MonthlyReturnsTests(unittest.TestCase):
    def test_return_is_keyed_by_the_ending_month(self):
        dates = ["2024-01-31", "2024-02-29", "2024-03-31"]
        values = [100.0, 110.0, 99.0]
        returns = monthly_returns(dates, values)
        self.assertEqual(set(returns), {"2024-02", "2024-03"})
        self.assertAlmostEqual(returns["2024-02"], 0.10)
        self.assertAlmostEqual(returns["2024-03"], 99.0 / 110.0 - 1)

    def test_mid_month_start_does_not_taint_the_first_computed_return(self):
        # A position opened mid-January still produces a genuine full-February return once
        # resampled to month-end -- nothing here should need to be dropped as "partial."
        dates = ["2024-01-15", "2024-01-31", "2024-02-29"]
        values = [100.0, 103.0, 106.0]
        returns = monthly_returns(dates, values)
        self.assertEqual(list(returns), ["2024-02"])
        self.assertAlmostEqual(returns["2024-02"], 106.0 / 103.0 - 1)


class OlsNeweyWestTests(unittest.TestCase):
    def test_recovers_a_noiseless_linear_relationship_exactly(self):
        rng = np.linspace(-1, 1, 50)
        y = 0.02 + 2.0 * rng  # alpha=0.02, beta=2.0, no noise
        result = ols_newey_west(y, {"x": rng})
        self.assertAlmostEqual(result["coefficients"]["alpha"]["estimate"], 0.02, places=8)
        self.assertAlmostEqual(result["coefficients"]["x"]["estimate"], 2.0, places=8)
        self.assertAlmostEqual(result["r_squared"], 1.0, places=8)

    def test_a_true_zero_alpha_has_a_small_t_statistic_under_noise(self):
        rng_state = np.random.default_rng(7)
        x = rng_state.normal(size=200)
        noise = rng_state.normal(scale=0.5, size=200)
        y = 0.0 + 1.0 * x + noise  # true alpha is exactly zero
        result = ols_newey_west(y, {"x": x})
        # With a genuinely zero alpha and 200 noisy observations, the t-stat should be
        # comfortably below the conventional significance threshold most of the time --
        # this is a smoke test on the sandwich formula, not a statistical proof.
        self.assertLess(abs(result["coefficients"]["alpha"]["newey_west_t_statistic"]), 3.0)

    def test_newey_west_and_classical_errors_agree_when_there_is_no_autocorrelation(self):
        rng_state = np.random.default_rng(11)
        x = rng_state.normal(size=300)
        y = 0.01 + 0.5 * x + rng_state.normal(scale=0.2, size=300)
        result = ols_newey_west(y, {"x": x}, lags=3)
        classical = result["coefficients"]["x"]["classical_standard_error"]
        nw = result["coefficients"]["x"]["newey_west_standard_error"]
        self.assertAlmostEqual(classical, nw, delta=0.15 * classical)


class SectorCoverageTests(unittest.TestCase):
    def test_counts_found_and_missing_tickers(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "advisor.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({
                    "research": [{"ticker": "AAA", "sector": "Technology"}],
                    "screen_universe": [{"ticker": "BBB", "sector": "Healthcare"}],
                    "portfolio_coverage": [],
                }, handle)
            result = sector_coverage(["AAA", "BBB", "CCC"], advisor_path=path)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["found"], 2)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["missing_sample"], ["CCC"])


if __name__ == "__main__":
    unittest.main()
