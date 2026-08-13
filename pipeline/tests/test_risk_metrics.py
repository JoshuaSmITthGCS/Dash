import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import risk_metrics as rm


def compounding(days, daily_gain=0.001, start=100.0):
    closes = [start]
    for _ in range(days - 1):
        closes.append(closes[-1] * (1 + daily_gain))
    return closes


class MomentumTests(unittest.TestCase):
    def test_12_1_momentum_excludes_the_most_recent_month(self):
        # Eleven months up, one month sharply down. Raw 12-month return is dragged under;
        # 12-1 momentum, the construction the literature uses, still reads positive.
        closes = compounding(300, 0.002)
        closes = closes[:-21] + [closes[-21] * (1 - 0.01 * step) for step in range(1, 22)]
        self.assertGreater(rm.momentum_12_1(closes), 0)
        self.assertLess(rm.period_return(closes, 252), rm.momentum_12_1(closes))

    def test_momentum_needs_a_full_lookback_plus_skip(self):
        self.assertIsNone(rm.momentum_12_1(compounding(200)))
        self.assertIsNotNone(rm.momentum_12_1(compounding(300)))

    def test_period_return_matches_the_arithmetic(self):
        self.assertEqual(rm.period_return([100, 101, 102, 103, 104, 105], 5), 5.0)
        self.assertIsNone(rm.period_return([100, 101], 5))


class RiskRatioTests(unittest.TestCase):
    def test_sortino_ignores_upside_volatility(self):
        upside = [0.02, 0.05, -0.001, 0.025] * 10
        downside = [0.02, -0.05, -0.001, 0.025] * 10
        self.assertGreater(rm.sortino_ratio(upside), rm.sortino_ratio(downside))

    def test_sharpe_is_none_without_enough_observations(self):
        self.assertIsNone(rm.sharpe_ratio([0.01, -0.01]))

    def test_a_series_has_beta_one_against_itself(self):
        returns = [0.01, -0.005, 0.02, -0.012] * 15
        self.assertEqual(rm.beta_vs_benchmark(returns, returns), 1.0)

    def test_beta_is_none_when_the_benchmark_never_moves(self):
        # A constant benchmark has zero variance, so beta is undefined rather than 1.0.
        self.assertIsNone(rm.beta_vs_benchmark([0.01] * 40, [0.001] * 40))

    def test_max_drawdown_finds_the_deepest_fall(self):
        self.assertAlmostEqual(rm.max_drawdown([100, 120, 60, 90]), -50.0, places=1)
        self.assertIsNone(rm.max_drawdown([100]))

    def test_annualized_volatility_scales_by_root_252(self):
        flat = rm.annualized_volatility([0.0] * 60)
        noisy = rm.annualized_volatility([0.02, -0.02] * 30)
        self.assertEqual(flat, 0.0)
        self.assertGreater(noisy, 20)


class TrackingTests(unittest.TestCase):
    def test_tracking_difference_is_the_signed_gap(self):
        self.assertEqual(rm.tracking_difference(10.0, 10.5), -0.5)
        self.assertIsNone(rm.tracking_difference(10.0, None))

    def test_tracking_error_is_zero_for_a_perfect_tracker(self):
        returns = rm.daily_returns(compounding(120, 0.001))
        self.assertEqual(rm.tracking_error(returns, returns), 0.0)

    def test_tracking_error_rises_with_divergence(self):
        fund = rm.daily_returns(compounding(120, 0.001))
        index = rm.daily_returns(compounding(120, 0.0011))
        drifting = [value * (1.5 if position % 2 else 0.5)
                    for position, value in enumerate(fund)]
        self.assertGreater(rm.tracking_error(drifting, index),
                           rm.tracking_error(fund, index))


class ScoreMappingTests(unittest.TestCase):
    def test_ratio_to_score_saturates_instead_of_clipping(self):
        self.assertEqual(rm.ratio_to_score(0.0), 50.0)
        self.assertGreater(rm.ratio_to_score(1.5), 70)
        self.assertLess(rm.ratio_to_score(-1.5), 30)
        # An extraordinary reading must not run away with a blended bucket.
        self.assertLess(rm.ratio_to_score(50.0), 100.0)
        self.assertGreater(rm.ratio_to_score(50.0), rm.ratio_to_score(5.0))

    def test_low_beta_scores_above_high_beta(self):
        self.assertGreater(rm.low_beta_score(0.85), rm.low_beta_score(1.9))
        self.assertGreater(rm.low_beta_score(1.0), rm.low_beta_score(2.5))
        self.assertIsNone(rm.low_beta_score(None))

    def test_drawdown_score_falls_as_the_hole_deepens(self):
        self.assertEqual(rm.drawdown_score(0.0), 100.0)
        self.assertEqual(rm.drawdown_score(-25.0), 50.0)
        self.assertLess(rm.drawdown_score(-60.0), 30.0)

    def test_volatility_percentile_rewards_the_calmer_name(self):
        peers = [10.0, 20.0, 30.0, 40.0]
        self.assertGreater(rm.volatility_percentile(12.0, peers),
                           rm.volatility_percentile(38.0, peers))
        self.assertIsNone(rm.volatility_percentile(12.0, [10.0]))


class DistributionShapeTests(unittest.TestCase):
    """The shape family. Every one of these must refuse to answer on a short sample."""

    def setUp(self):
        generator = random.Random(19)
        self.symmetric = [generator.gauss(0.0005, 0.01) for _ in range(500)]
        # Same mean, but the losses arrive in a few large pieces instead of many small ones.
        self.crash_prone = [generator.gauss(0.0015, 0.006)
                            if index % 50 else generator.gauss(-0.05, 0.01)
                            for index in range(500)]
        self.closes = [100.0]
        for value in self.symmetric:
            self.closes.append(self.closes[-1] * (1 + value))

    def test_short_samples_return_nothing_rather_than_a_reading(self):
        short = self.symmetric[:30]
        for value in (rm.omega_ratio(short), rm.ulcer_index(short), rm.skewness(short),
                      rm.excess_kurtosis(short), rm.tail_ratio(short),
                      rm.gain_to_pain(short), rm.conditional_value_at_risk(short),
                      rm.martin_ratio(short, short)):
            self.assertIsNone(value)

    def test_omega_falls_as_the_threshold_rises(self):
        self.assertGreater(rm.omega_ratio(self.symmetric, 0.0),
                           rm.omega_ratio(self.symmetric, 0.002))

    def test_a_crash_prone_series_reads_worse_on_every_shape_measure(self):
        self.assertLess(rm.skewness(self.crash_prone), rm.skewness(self.symmetric))
        self.assertGreater(rm.excess_kurtosis(self.crash_prone),
                           rm.excess_kurtosis(self.symmetric))
        self.assertLess(rm.conditional_value_at_risk(self.crash_prone),
                        rm.conditional_value_at_risk(self.symmetric))

    def test_gain_to_pain_falls_when_the_same_gain_costs_more_loss(self):
        gentle = [0.01 if index % 2 else -0.002 for index in range(400)]
        painful = [0.02 if index % 2 else -0.012 for index in range(400)]
        self.assertAlmostEqual(sum(gentle), sum(painful), places=6)
        self.assertGreater(rm.gain_to_pain(gentle), rm.gain_to_pain(painful))

    def test_ulcer_index_measures_time_underwater_not_just_the_worst_day(self):
        rising = [100.0 * (1.001 ** day) for day in range(400)]
        sagging = [100.0 - day * 0.05 for day in range(400)]
        self.assertLess(rm.ulcer_index(rising), rm.ulcer_index(sagging))
        self.assertIsNotNone(rm.martin_ratio(self.symmetric, self.closes))

    def test_tail_ratio_is_undefined_when_a_tail_is_missing(self):
        self.assertIsNone(rm.tail_ratio([0.01] * 300))


if __name__ == "__main__":
    unittest.main()
