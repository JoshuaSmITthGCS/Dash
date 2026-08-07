import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import strategy_diagnostics as sd


class ExpectancyTests(unittest.TestCase):
    def test_expectancy_identity_holds_against_the_plain_mean(self):
        """E = P(win)*avg_win - P(loss)*avg_loss must equal the arithmetic mean."""
        returns = [0.05, -0.02, 0.03, -0.04, 0.01, 0.06, -0.01]
        result = sd.expectancy(returns)
        self.assertAlmostEqual(result["expectancy_per_period"],
                               result["mean_return_per_period"], places=5)

    def test_a_low_win_rate_can_still_carry_positive_expectancy(self):
        """40% wins at +8% against 60% losses at -3% is the brief's own example."""
        returns = [0.08] * 4 + [-0.03] * 6
        result = sd.expectancy(returns)
        self.assertAlmostEqual(result["win_rate"], 0.4)
        self.assertAlmostEqual(result["expectancy_per_period"], 0.014, places=4)
        self.assertGreater(result["payoff_ratio"], 2.6)

    def test_all_winning_periods_report_no_payoff_ratio_rather_than_dividing_by_zero(self):
        result = sd.expectancy([0.01, 0.02, 0.03])
        self.assertIsNone(result["payoff_ratio"])
        self.assertEqual(result["win_rate"], 1.0)

    def test_empty_series_returns_nothing(self):
        self.assertIsNone(sd.expectancy([]))


class ProfitFactorTests(unittest.TestCase):
    def test_profit_factor_is_gross_profit_over_gross_loss(self):
        result = sd.profit_factor([0.10, 0.05, -0.05])
        self.assertAlmostEqual(result["gross_profit"], 0.15)
        self.assertAlmostEqual(result["gross_loss"], 0.05)
        self.assertAlmostEqual(result["profit_factor"], 3.0)

    def test_no_losses_reports_none_rather_than_infinity(self):
        self.assertIsNone(sd.profit_factor([0.01, 0.02])["profit_factor"])


class StreakTests(unittest.TestCase):
    def test_longest_streaks_are_counted_in_both_directions(self):
        result = sd.streaks([0.01, 0.01, 0.01, -0.01, -0.01, 0.01, -0.01, -0.01, -0.01, -0.01])
        self.assertEqual(result["longest_winning_streak"], 3)
        self.assertEqual(result["longest_losing_streak"], 4)

    def test_a_flat_period_breaks_a_streak(self):
        result = sd.streaks([0.01, 0.0, 0.01])
        self.assertEqual(result["longest_winning_streak"], 1)


class DrawdownTests(unittest.TestCase):
    def test_drawdown_measures_peak_to_trough_and_time_underwater(self):
        result = sd.drawdown_profile([0.10, -0.20, -0.10, 0.05, 0.40])
        self.assertLess(result["max_drawdown"], -0.25)
        self.assertEqual(result["longest_underwater_periods"], 3)

    def test_a_monotonically_rising_series_never_goes_underwater(self):
        result = sd.drawdown_profile([0.01] * 10)
        self.assertEqual(result["max_drawdown"], 0.0)
        self.assertEqual(result["longest_underwater_periods"], 0)


class RMultipleTests(unittest.TestCase):
    def test_risk_unit_is_labelled_as_a_portfolio_proxy_not_a_stop(self):
        result = sd.r_multiples([0.05, -0.02, 0.03, -0.04])
        self.assertIn("not per-position stops", result["basis"])
        self.assertIsNotNone(result["risk_unit"])

    def test_too_few_losing_periods_reports_no_risk_unit(self):
        result = sd.r_multiples([0.05, 0.03, -0.01])
        self.assertIsNone(result["risk_unit"])


class TurnoverTests(unittest.TestCase):
    REBALANCES = [{"turnover": 0.6, "cost": 60.0, "portfolio_value": 100_000.0},
                  {"turnover": 0.7, "cost": 70.0, "portfolio_value": 100_000.0}]

    def test_annualized_turnover_scales_the_monthly_mean(self):
        result = sd.turnover_profile(self.REBALANCES)
        self.assertAlmostEqual(result["mean_monthly_turnover"], 0.65)
        self.assertAlmostEqual(result["annualized_turnover"], 7.8)

    def test_gross_return_is_net_plus_the_recorded_cost_drag(self):
        result = sd.turnover_adjusted_return([0.01] * 12, self.REBALANCES)
        self.assertAlmostEqual(
            result["implied_gross_annualized_return"],
            result["net_annualized_return"] + result["annualized_cost_drag"], places=6)
        self.assertGreater(result["share_of_gross_return_consumed_by_costs"], 0)


class RegimeTests(unittest.TestCase):
    def test_regimes_are_defined_from_the_benchmark_never_from_the_strategy(self):
        dates = [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(260)]
        rising = [100.0 * (1.002 ** i) for i in range(260)]
        labels = sd._trend_regime(dates, rising)
        self.assertTrue(labels)
        self.assertEqual(set(labels.values()), {"bull"})

        falling = [100.0 * (0.998 ** i) for i in range(260)]
        self.assertEqual(set(sd._trend_regime(dates, falling).values()), {"bear"})

    def test_rate_regime_reads_the_six_month_change_in_the_risk_free_series(self):
        observations = [{"month": f"2024-{month:02d}", "risk_free": 0.001 * month}
                        for month in range(1, 13)]
        labels = sd._rate_regime(observations)
        self.assertEqual(labels["2024-07"], "rising_rates")
        self.assertNotIn("2024-06", labels)

    def test_attribution_splits_both_legs_by_the_same_regime_labels(self):
        strategy = {"2024-01": 0.05, "2024-02": -0.02, "2024-03": 0.01}
        benchmark = {"2024-01": 0.03, "2024-02": -0.04, "2024-03": 0.02}
        regimes = {"market_direction": {"2024-01": "bull", "2024-02": "bear", "2024-03": "bull"}}
        attribution = sd.regime_attribution(strategy, benchmark, regimes)["market_direction"]

        self.assertEqual(attribution["bull"]["months"], 2)
        self.assertEqual(attribution["bear"]["months"], 1)
        self.assertGreater(attribution["bear"]["excess_annualized"], 0)

    def test_months_with_no_regime_label_are_dropped_not_defaulted(self):
        attribution = sd.regime_attribution(
            {"2024-01": 0.05, "2024-02": -0.02}, {}, {"f": {"2024-01": "bull"}})
        self.assertEqual(attribution["f"]["bull"]["months"], 1)
        self.assertIsNone(attribution["f"]["bull"]["benchmark_annualized"])


class CommittedBacktestTests(unittest.TestCase):
    def test_report_runs_against_the_committed_backtest_and_declares_its_unit(self):
        if not os.path.exists(sd.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        report = sd.build_report()

        self.assertEqual(report["unit_of_account"]["trade"],
                         "one monthly rebalance period holding a 20-name book")
        self.assertIn("per-position R-multiples", report["unit_of_account"]["not_measured"])
        self.assertGreater(report["sample"]["months"], 50)
        self.assertIsNotNone(report["expectancy"]["expectancy_per_period"])
        self.assertIsNotNone(report["profit_factor"]["profit_factor"])
        for family in ("market_direction", "volatility", "rates"):
            self.assertIn(family, report["regime_attribution"])


if __name__ == "__main__":
    unittest.main()
