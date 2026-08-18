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


def path(daily_returns_series, start=100.0):
    """Build a close series whose daily returns are exactly the ones given."""
    closes = [start]
    for value in daily_returns_series:
        closes.append(closes[-1] * (1 + value))
    return closes


class RelativeAccelerationTests(unittest.TestCase):
    """Fixtures here are built return-by-return rather than as prices, because the thing
    under test is a property of the return series and the price path is only its integral.

    Every stock fixture carries idiosyncratic noise. A stock whose excess return is a pure
    noiseless step has zero residual dispersion, which makes the t-statistic's denominator
    zero and the measurement genuinely undefined - the function returns None for it, which
    is correct behaviour and useless as a fixture.
    """

    # 63-session legs plus a 5-session skip is 131 daily returns, so 132 closes minimum.
    LEG, SKIP = 63, 5
    SESSIONS = 200

    def setUp(self):
        # The last measured session is SKIP back from the end; the recent leg starts LEG
        # before that. Anything indexed at or after this boundary is "the recent leg".
        self.boundary = self.SESSIONS - self.LEG - self.SKIP
        self.market_returns = [0.0004 + (0.006 if step % 2 else -0.006)
                               for step in range(self.SESSIONS)]
        self.market = path(self.market_returns)
        # Period 3 against the market's period 2, so it is close to uncorrelated with it
        # and beta comes back at roughly the exposure the fixture was built with.
        self.noise = [0.004 if step % 3 else -0.008 for step in range(self.SESSIONS)]

    def stock(self, beta=1.0, prior_edge=0.0, recent_edge=0.0):
        """A stock with a given market exposure and a daily excess edge that changes
        between the prior leg and the recent one."""
        return path([beta * market + (prior_edge if step < self.boundary else recent_edge) + noise
                     for step, (market, noise)
                     in enumerate(zip(self.market_returns, self.noise))])

    def reading(self, closes, benchmark=None):
        return rm.relative_acceleration(closes, self.market if benchmark is None else benchmark,
                                        leg=self.LEG, skip=self.SKIP)

    def test_a_stock_pulling_away_faster_reads_positive(self):
        reading = self.reading(self.stock(prior_edge=0.0005, recent_edge=0.0025))
        self.assertGreater(reading["acceleration"], 0)
        self.assertGreater(reading["recent_excess_pct"], reading["prior_excess_pct"])
        self.assertEqual(reading["observations"], 2 * self.LEG)

    def test_a_stock_losing_its_edge_reads_negative(self):
        reading = self.reading(self.stock(prior_edge=0.0025, recent_edge=0.0002))
        self.assertLess(reading["acceleration"], 0)
        self.assertLess(reading["recent_excess_pct"], reading["prior_excess_pct"])

    def test_a_steady_outperformer_is_not_accelerating(self):
        # Beating the market by the same amount every day is momentum, not acceleration.
        # This is the distinction the measure exists to draw.
        steady = self.stock(prior_edge=0.001, recent_edge=0.001)
        self.assertAlmostEqual(self.reading(steady)["acceleration"], 0.0, places=1)

    def test_the_skipped_window_is_excluded(self):
        # A violent last week must not register: it lives inside skip_days, where
        # short-term reversal does, for the same reason momentum_12_1 skips a month.
        calm = self.stock(prior_edge=0.001, recent_edge=0.001)
        spiked = list(calm[:-self.SKIP]) + [close * 1.08 for close in calm[-self.SKIP:]]
        self.assertEqual(self.reading(calm)["acceleration"],
                         self.reading(spiked)["acceleration"])

    def test_market_driven_acceleration_is_stripped_out(self):
        """The audit-section-6 degeneracy check, run as a test.

        ``relative_strength_20d`` subtracts the same benchmark number from every row, so its
        cross-sectional ranking is identical to the raw return's - it cannot tell a stock
        that outran the market from one the market carried. Put both in an *accelerating*
        market: a beta-2 name that added nothing of its own has accelerated in raw price
        terms without beating anything, while a near-market-neutral name with a genuine
        idiosyncratic pickup has. A raw difference ranks them the same way it ranks their
        own returns; this measure must not.
        """
        accelerating = [(0.0002 if step < self.boundary else 0.0018)
                        + (0.006 if step % 2 else -0.006) for step in range(self.SESSIONS)]
        market = path(accelerating)
        rider = path([2 * value + noise for value, noise in zip(accelerating, self.noise)])
        mover = path([0.2 * value + (0.0002 if step < self.boundary else 0.0018) + noise
                      for step, (value, noise) in enumerate(zip(accelerating, self.noise))])

        # Both raw price paths sped up: each earned more over the recent leg than the prior
        # one, which is all a raw own-return acceleration would see.
        for closes in (rider, mover):
            measured = closes[:len(closes) - self.SKIP]
            recent = measured[-1] / measured[-1 - self.LEG]
            prior = measured[-1 - self.LEG] / measured[-1 - 2 * self.LEG]
            self.assertGreater(recent, prior)

        rider_reading = self.reading(rider, market)
        mover_reading = self.reading(mover, market)
        self.assertGreater(rider_reading["beta"], mover_reading["beta"])
        # Only one of them accelerated independently of the market.
        self.assertLess(abs(rider_reading["acceleration"]), 1.0)
        self.assertGreater(mover_reading["acceleration"], rider_reading["acceleration"] + 1.0)

    def test_unavailable_rather_than_guessed_when_the_measurement_cannot_be_made(self):
        stock = self.stock(prior_edge=0.0005, recent_edge=0.0025)
        self.assertIsNone(self.reading(stock[:80]))
        self.assertIsNone(rm.relative_acceleration(stock, None, leg=self.LEG, skip=self.SKIP))
        # A benchmark that never moves has no beta, so there is no market to be relative to.
        self.assertIsNone(self.reading(stock, path([0.0] * self.SESSIONS)))

    def test_excess_returns_never_default_beta_to_one(self):
        returns = [0.01, -0.005] * 30
        series, beta = rm.excess_returns(returns, [0.0] * 60)
        self.assertIsNone(series)
        self.assertIsNone(beta)

    def test_the_reading_is_scale_free_across_volatility_regimes(self):
        """A quiet utility and a loud biotech with the same pickup *in units of their own
        noise* must read the same. Without that, the measure would just rank volatility."""
        shape = [0.0005 if step < self.boundary else 0.0025 for step in range(self.SESSIONS)]
        quiet = path([market + move + noise for market, move, noise
                      in zip(self.market_returns, shape, self.noise)])
        loud = path([market + 4 * move + 4 * noise for market, move, noise
                     in zip(self.market_returns, shape, self.noise)])
        quiet_reading, loud_reading = self.reading(quiet), self.reading(loud)
        # Four times the raw pickup in percentage points...
        self.assertGreater(loud_reading["acceleration_pct"],
                           quiet_reading["acceleration_pct"] * 2)
        # ...and the same reading once each is measured against its own noise.
        self.assertAlmostEqual(loud_reading["acceleration"], quiet_reading["acceleration"],
                               places=1)

    def test_the_score_maps_a_pickup_above_neutral_and_a_fade_below(self):
        self.assertEqual(rm.acceleration_score(0.0), 50.0)
        self.assertGreater(rm.acceleration_score(1.0), 70)
        self.assertLess(rm.acceleration_score(-1.0), 30)
        self.assertIsNone(rm.acceleration_score(None))
        # Saturating, not clipping: one violent quarter cannot pin the reading at 100.
        self.assertLess(rm.acceleration_score(40.0), 100.0)


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


class HistoricalVarTests(unittest.TestCase):
    def setUp(self):
        generator = random.Random(11)
        self.returns = [generator.gauss(0.0004, 0.012) for _ in range(200)]

    def test_var_is_none_below_the_minimum_sample(self):
        self.assertIsNone(rm.historical_var(self.returns[:50]))

    def test_var_99_is_at_least_as_deep_as_var_95(self):
        var_95 = rm.historical_var(self.returns, confidence=0.95, minimum_observations=100)
        var_99 = rm.historical_var(self.returns, confidence=0.99, minimum_observations=100)
        self.assertGreater(var_99, var_95)

    def test_var_matches_the_empirical_quantile(self):
        # Exactly five values worse than -5%, so the 5% VaR threshold lands on the least
        # negative of them.
        returns = [-0.20, -0.15, -0.10, -0.07, -0.05] + [0.02] * 95
        value = rm.historical_var(returns, confidence=0.95, minimum_observations=100)
        self.assertAlmostEqual(value, 5.0, places=1)


class TreynorAndJensenTests(unittest.TestCase):
    def setUp(self):
        generator = random.Random(5)
        self.benchmark = [generator.gauss(0.0004, 0.01) for _ in range(300)]
        # A market-tracking series with real positive alpha layered on top.
        self.alpha_series = [0.0004 + 0.8 * value for value in self.benchmark]
        # A pure beta-1.6 series with zero alpha.
        self.no_alpha_series = [1.6 * value for value in self.benchmark]

    def test_treynor_rewards_return_per_unit_of_beta(self):
        low_beta = [0.5 * value for value in self.benchmark]
        high_beta = [1.5 * value for value in self.benchmark]
        boosted_low_beta = [value + 0.0005 for value in low_beta]
        self.assertGreater(
            rm.treynor_ratio(boosted_low_beta, self.benchmark),
            rm.treynor_ratio(high_beta, self.benchmark))

    def test_treynor_is_none_without_a_measurable_beta(self):
        self.assertIsNone(rm.treynor_ratio([0.01] * 40, [0.001] * 40))

    def test_jensens_alpha_is_positive_when_alpha_is_added_on_top_of_beta(self):
        self.assertGreater(rm.jensens_alpha(self.alpha_series, self.benchmark), 0)

    def test_jensens_alpha_is_near_zero_for_a_pure_beta_series(self):
        self.assertAlmostEqual(rm.jensens_alpha(self.no_alpha_series, self.benchmark), 0, delta=1.0)

    def test_jensens_alpha_needs_enough_overlap(self):
        self.assertIsNone(rm.jensens_alpha([0.01] * 10, [0.01] * 10))


if __name__ == "__main__":
    unittest.main()
