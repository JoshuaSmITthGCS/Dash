import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import stress_scenarios as ss


def daily_prices(start, days, daily_return, key="total_return_index"):
    import datetime
    start_date = datetime.date.fromisoformat(start)
    rows, value = [], 1.0
    for index in range(days):
        rows.append({"date": (start_date + datetime.timedelta(days=index)).isoformat(),
                     key: value})
        value *= 1 + daily_return
    return rows


class WindowReturnTests(unittest.TestCase):
    def test_matches_the_simple_ratio_between_window_endpoints(self):
        prices = [{"date": "2020-01-01", "total_return_index": 100.0},
                 {"date": "2020-01-15", "total_return_index": 90.0},
                 {"date": "2020-02-01", "total_return_index": 70.0}]
        self.assertAlmostEqual(ss.window_return(prices, "2020-01-01", "2020-02-01"), -0.30)
        self.assertAlmostEqual(ss.window_return(prices, "2020-01-01", "2020-01-15"), -0.10)

    def test_none_with_fewer_than_two_priced_days_in_window(self):
        prices = [{"date": "2020-01-01", "total_return_index": 100.0}]
        self.assertIsNone(ss.window_return(prices, "2020-01-01", "2020-02-01"))
        self.assertIsNone(ss.window_return(None, "2020-01-01", "2020-02-01"))

    def test_falls_back_to_adjusted_close_when_total_return_missing(self):
        prices = [{"date": "2020-01-01", "adjusted_close": 50.0},
                 {"date": "2020-02-01", "adjusted_close": 55.0}]
        self.assertAlmostEqual(ss.window_return(prices, "2020-01-01", "2020-02-01"), 0.10)


class FactorWindowReturnTests(unittest.TestCase):
    def test_compounds_every_month_touching_the_window(self):
        observations = [{"month": "2022-01", "market_excess": 0.05},
                        {"month": "2022-02", "market_excess": -0.02},
                        {"month": "2022-03", "market_excess": 0.01}]
        # (1.05 * 0.98 * 1.01) - 1
        expected = 1.05 * 0.98 * 1.01 - 1
        value = ss.factor_window_return(observations, "2022-01-15", "2022-03-20", "market_excess")
        self.assertAlmostEqual(value, round(expected, 4))

    def test_none_when_no_month_touches_the_window(self):
        observations = [{"month": "2019-01", "market_excess": 0.05}]
        self.assertIsNone(ss.factor_window_return(observations, "2022-01-01", "2022-03-01", "market_excess"))


class FactorProjectedReturnTests(unittest.TestCase):
    def test_dot_product_of_loadings_and_scenario_returns(self):
        loadings = {"market_excess": 0.8, "size": 0.5, "value": 0.1,
                   "profitability": 0.2, "investment": 0.1, "momentum": 0.3}
        factor_returns = {"market_excess": -0.20, "size": 0.0, "value": -0.05,
                          "profitability": 0.02, "investment": -0.01, "momentum": 0.08}
        expected = round(0.8 * -0.20 + 0.5 * 0.0 + 0.1 * -0.05 + 0.2 * 0.02 + 0.1 * -0.01 + 0.3 * 0.08, 4)
        self.assertAlmostEqual(ss.factor_projected_return(loadings, factor_returns), expected)

    def test_none_without_loadings(self):
        self.assertIsNone(ss.factor_projected_return(None, {"market_excess": -0.1}))

    def test_a_leg_missing_on_either_side_drops_out_rather_than_zeroing(self):
        loadings = {"market_excess": 1.0, "size": 0.5}
        factor_returns = {"market_excess": -0.10}  # no "size" entry
        # Only the market_excess term should count, not size*0.
        self.assertAlmostEqual(ss.factor_projected_return(loadings, factor_returns), -0.10)


class AlignedDailyReturnsTests(unittest.TestCase):
    def test_zips_by_shared_date_not_by_index(self):
        portfolio_history = [{"date": "2024-01-01", "value": 100.0},
                             {"date": "2024-01-02", "value": 101.0},
                             {"date": "2024-01-04", "value": 103.0}]  # no Jan 3rd
        benchmark_prices = [{"date": "2024-01-01", "total_return_index": 50.0},
                            {"date": "2024-01-02", "total_return_index": 51.0},
                            {"date": "2024-01-03", "total_return_index": 52.0},  # portfolio lacks this day
                            {"date": "2024-01-04", "total_return_index": 49.0}]
        portfolio_returns, benchmark_returns = ss.aligned_daily_returns(portfolio_history, benchmark_prices)
        # Shared dates: Jan 1, 2, 4 -- Jan 3rd must not silently enter either series.
        self.assertEqual(len(portfolio_returns), 2)
        self.assertEqual(len(benchmark_returns), 2)
        self.assertAlmostEqual(portfolio_returns[0], 0.01, places=4)
        self.assertAlmostEqual(benchmark_returns[1], 49.0 / 51.0 - 1, places=4)

    def test_empty_on_no_overlap(self):
        portfolio_returns, benchmark_returns = ss.aligned_daily_returns(
            [{"date": "2024-01-01", "value": 100.0}],
            [{"date": "2019-01-01", "total_return_index": 10.0}])
        self.assertEqual(portfolio_returns, [])
        self.assertEqual(benchmark_returns, [])


class NamedScenariosTests(unittest.TestCase):
    def test_every_named_scenario_is_covered_by_synthetic_data_spanning_all_three_events(self):
        # 2007-01-01 through 2023-01-01 covers all three NAMED_SCENARIOS windows.
        spy_prices = daily_prices("2007-01-01", 6000, -0.0002)
        tlt_prices = daily_prices("2007-01-01", 6000, 0.0001)
        factor_observations = [
            {"month": f"{year}-{month:02d}", "market_excess": -0.01, "size": 0.001,
             "value": 0.002, "profitability": -0.001, "investment": 0.0, "momentum": 0.003}
            for year in range(2007, 2023) for month in range(1, 13)
        ]
        loadings = {"market_excess": 0.8, "size": 0.5, "value": 0.1,
                   "profitability": 0.2, "investment": 0.1, "momentum": 0.3}
        results = ss.named_scenarios(spy_prices=spy_prices, tlt_prices=tlt_prices,
                                     factor_observations=factor_observations,
                                     loadings=loadings, beta_spy=0.65)
        self.assertEqual(set(results), set(ss.NAMED_SCENARIOS))
        for scenario_id, row in results.items():
            self.assertIsNotNone(row["spy_return_pct"], scenario_id)
            self.assertIsNotNone(row["market_beta_projection_pct"], scenario_id)
            self.assertIsNotNone(row["factor_model_projection_pct"], scenario_id)
            # A declining SPY/factor series at 0.65 beta must produce a negative projection.
            self.assertLess(row["market_beta_projection_pct"], 0, scenario_id)

    def test_missing_price_history_reports_none_rather_than_a_guess(self):
        results = ss.named_scenarios(spy_prices=None, tlt_prices=None, factor_observations=[],
                                     loadings=None, beta_spy=None)
        for row in results.values():
            self.assertIsNone(row["spy_return_pct"])
            self.assertIsNone(row["market_beta_projection_pct"])
            self.assertIsNone(row["factor_model_projection_pct"])


class HypotheticalShocksTests(unittest.TestCase):
    def test_spy_shock_scales_linearly_with_beta(self):
        shocks = ss.hypothetical_shocks(beta_spy=0.5, rate_beta=0.0, spy_shock_pct=-30.0)
        self.assertAlmostEqual(shocks["spy_shock"]["projected_return_pct"], -15.0)

    def test_rate_shock_uses_the_stated_duration_assumption(self):
        shocks = ss.hypothetical_shocks(beta_spy=0.0, rate_beta=1.0, rate_shock_bps=200,
                                        tlt_duration_years=17.0)
        # -17 years * 2.0 percentage points = -34% TLT price impact, times rate_beta 1.0.
        self.assertAlmostEqual(shocks["rate_shock"]["implied_tlt_price_impact_pct"], -34.0)
        self.assertAlmostEqual(shocks["rate_shock"]["projected_return_pct"], -34.0)

    def test_none_projection_when_the_relevant_beta_is_unmeasured(self):
        shocks = ss.hypothetical_shocks(beta_spy=None, rate_beta=None)
        self.assertIsNone(shocks["spy_shock"]["projected_return_pct"])
        self.assertIsNone(shocks["rate_shock"]["projected_return_pct"])
        # The duration assumption is still reported even when there's no beta to apply it to.
        self.assertIsNotNone(shocks["rate_shock"]["implied_tlt_price_impact_pct"])


if __name__ == "__main__":
    unittest.main()
