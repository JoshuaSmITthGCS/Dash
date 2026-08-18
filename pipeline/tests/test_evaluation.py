import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import evaluation as ev


def synthetic_periods(count, signal_strength, *, names=60, seed=11, noise=0.05):
    """Periods where forward return depends on score by ``signal_strength``, plus noise."""
    generator = random.Random(seed)
    periods = []
    for index in range(count):
        scores, forwards = {}, {}
        for position in range(names):
            score = generator.uniform(0, 100)
            scores[f"T{position}"] = score
            forwards[f"T{position}"] = (signal_strength * (score - 50) / 50 * 0.02
                                        + generator.gauss(0, noise))
        periods.append({"date": f"2026-{index + 1:02d}", "scores": scores,
                        "forward_returns": forwards})
    return periods


class RankICTests(unittest.TestCase):
    def test_a_perfectly_ordered_score_has_ic_of_one(self):
        scores = [1, 2, 3, 4, 5, 6]
        self.assertAlmostEqual(ev.rank_ic(scores, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]), 1.0, places=6)
        self.assertAlmostEqual(ev.rank_ic(scores, [0.6, 0.5, 0.4, 0.3, 0.2, 0.1]), -1.0, places=6)

    def test_rank_ic_is_robust_to_a_return_outlier(self):
        # A single 40x return would dominate a Pearson correlation. Spearman only cares
        # about ordering, which is all the model ever claims.
        scores = [1, 2, 3, 4, 5, 6]
        returns = [0.1, 0.2, 0.3, 0.4, 0.5, 40.0]
        self.assertAlmostEqual(ev.rank_ic(scores, returns), 1.0, places=6)

    def test_pairs_with_missing_data_are_dropped_not_imputed(self):
        value = ev.rank_ic([1, 2, 3, 4, 5, None], [0.1, 0.2, 0.3, 0.4, 0.5, 0.9])
        self.assertAlmostEqual(value, 1.0, places=6)

    def test_too_few_names_returns_nothing(self):
        self.assertIsNone(ev.rank_ic([1, 2], [0.1, 0.2]))

    def test_ties_are_ranked_by_their_average(self):
        self.assertEqual(ev.rank([10, 10, 20]), [1.5, 1.5, 3.0])


class ICSummaryTests(unittest.TestCase):
    def test_summary_reports_icir_and_the_multiple_testing_bar(self):
        summary = ev.ic_summary([0.05, 0.04, 0.06, 0.05, 0.04, 0.05])
        self.assertGreater(summary["mean_ic"], 0.04)
        self.assertTrue(summary["meaningful"])
        self.assertTrue(summary["clears_multiple_testing_bar"])

    def test_a_weak_signal_is_marked_not_meaningful(self):
        summary = ev.ic_summary([0.005, -0.004, 0.008, 0.001])
        self.assertFalse(summary["meaningful"])

    def test_an_inconsistent_signal_fails_the_t_stat_bar(self):
        # Same mean IC, wildly different consistency. Only the consistent one should pass.
        erratic = ev.ic_summary([0.30, -0.28, 0.31, -0.27, 0.29, -0.25, 0.30])
        self.assertFalse(erratic["clears_multiple_testing_bar"])

    def test_series_carries_the_filtered_values_a_bootstrap_can_reuse(self):
        summary = ev.ic_summary([0.05, None, 0.04, 0.06])
        self.assertEqual(summary["series"], [0.05, 0.04, 0.06])


class BootstrapIcConfidenceIntervalTests(unittest.TestCase):
    def test_none_below_the_minimum_sample(self):
        self.assertIsNone(ev.bootstrap_ic_confidence_interval([0.03] * 5))

    def test_ci_brackets_a_consistently_positive_ic_series(self):
        generator = random.Random(12)
        series = [generator.gauss(0.04, 0.02) for _ in range(40)]
        result = ev.bootstrap_ic_confidence_interval(series, samples=1000, seed=1)
        lower, upper = result["ic_ci_95"]
        self.assertLess(lower, result["mean_ic"])
        self.assertGreater(upper, result["mean_ic"])
        self.assertGreater(result["probability_ic_positive"], 0.9)

    def test_a_series_straddling_zero_has_a_ci_that_includes_zero(self):
        generator = random.Random(13)
        series = [generator.gauss(0.0, 0.03) for _ in range(40)]
        result = ev.bootstrap_ic_confidence_interval(series, samples=1000, seed=1)
        lower, upper = result["ic_ci_95"]
        self.assertLessEqual(lower, 0)
        self.assertGreaterEqual(upper, 0)

    def test_none_values_are_dropped_not_treated_as_zero(self):
        result = ev.bootstrap_ic_confidence_interval(
            [0.05] * 15 + [None] * 15, samples=200, seed=1)
        self.assertEqual(result["observations"], 15)


class QuantileTests(unittest.TestCase):
    def test_monotone_buckets_are_detected(self):
        scores = list(range(50))
        returns = [value * 0.001 for value in scores]
        buckets = ev.quantile_buckets(scores, returns, quantiles=5)
        spread = ev.quantile_spread(buckets)
        self.assertTrue(spread["monotonic"])
        self.assertEqual(spread["inversions"], 0)
        self.assertGreater(spread["top_minus_bottom"], 0)

    def test_a_score_that_only_works_at_the_extremes_is_flagged_non_monotone(self):
        buckets = [
            {"quantile": 1, "mean_forward_return": 0.05, "count": 10, "mean_score": 90},
            {"quantile": 2, "mean_forward_return": -0.02, "count": 10, "mean_score": 70},
            {"quantile": 3, "mean_forward_return": 0.01, "count": 10, "mean_score": 50},
            {"quantile": 4, "mean_forward_return": -0.01, "count": 10, "mean_score": 30},
            {"quantile": 5, "mean_forward_return": -0.04, "count": 10, "mean_score": 10},
        ]
        spread = ev.quantile_spread(buckets)
        self.assertGreater(spread["top_minus_bottom"], 0)
        self.assertFalse(spread["monotonic"])
        self.assertGreater(spread["inversions"], 0)

    def test_too_small_a_universe_produces_no_buckets(self):
        self.assertIsNone(ev.quantile_buckets([1, 2, 3], [0.1, 0.2, 0.3], quantiles=5))


class DeflationTests(unittest.TestCase):
    def test_more_trials_raise_the_bar(self):
        one = ev.deflated_sharpe_ratio(0.5, observations=36, trials=1)
        many = ev.deflated_sharpe_ratio(0.5, observations=36, trials=500)
        self.assertGreater(one, many)

    def test_expected_max_sharpe_grows_with_the_search(self):
        self.assertGreater(ev.expected_max_sharpe(500, 1 / 36),
                           ev.expected_max_sharpe(10, 1 / 36))
        self.assertEqual(ev.expected_max_sharpe(1, 1 / 36), 0.0)

    def test_negative_skew_and_fat_tails_reduce_confidence(self):
        normal = ev.deflated_sharpe_ratio(0.6, observations=60, trials=20)
        fat_tailed = ev.deflated_sharpe_ratio(0.6, observations=60, trials=20,
                                              skew=-1.5, kurtosis=9.0)
        self.assertGreater(normal, fat_tailed)

    def test_too_few_observations_returns_nothing(self):
        self.assertIsNone(ev.deflated_sharpe_ratio(1.0, observations=2, trials=5))


class OverfittingTests(unittest.TestCase):
    def test_pbo_on_pure_noise_sits_near_one_half(self):
        # With no real skill, the in-sample winner should land above and below the
        # out-of-sample median about equally often. Anything far from 0.5 means the
        # statistic itself is biased.
        generator = random.Random(3)
        values = [ev.probability_of_backtest_overfitting(
            [[generator.gauss(0, 1) for _ in range(8)] for _ in range(64)])
            for _ in range(20)]
        mean = sum(values) / len(values)
        self.assertGreater(mean, 0.35)
        self.assertLess(mean, 0.65)

    def test_a_genuinely_dominant_configuration_has_low_pbo(self):
        generator = random.Random(5)
        matrix = []
        for _ in range(64):
            row = [generator.gauss(0, 1) for _ in range(5)]
            row.append(generator.gauss(3.0, 1))   # one configuration with real edge
            matrix.append(row)
        self.assertLess(ev.probability_of_backtest_overfitting(matrix), 0.2)

    def test_degenerate_inputs_return_nothing(self):
        self.assertIsNone(ev.probability_of_backtest_overfitting([[1.0]] * 4))
        self.assertIsNone(ev.probability_of_backtest_overfitting([]))


class WalkForwardTests(unittest.TestCase):
    def test_a_predictive_score_ships_and_noise_does_not(self):
        predictive = ev.evaluate_candidate(synthetic_periods(24, 1.0), trials=40)
        noise = ev.evaluate_candidate(synthetic_periods(24, 0.0, seed=99), trials=40)
        self.assertTrue(predictive["ship"])
        self.assertFalse(noise["ship"])
        self.assertTrue(noise["ship_blockers"])

    def test_a_candidate_must_beat_its_baseline_to_ship(self):
        periods = synthetic_periods(24, 1.0)
        strong_baseline = {"mean_ic": 0.9}
        verdict = ev.evaluate_candidate(periods, trials=10, baseline=strong_baseline)
        self.assertFalse(verdict["ship"])
        self.assertTrue(any("baseline" in reason for reason in verdict["ship_blockers"]))

    def test_walk_forward_reports_one_row_per_period(self):
        result = ev.walk_forward(synthetic_periods(6, 1.0))
        self.assertEqual(len(result["periods"]), 6)
        self.assertEqual(result["ic"]["periods"], 6)

    def test_a_period_with_no_overlap_is_scored_as_unanswered(self):
        periods = [{"date": "2026-01", "scores": {"AAA": 50}, "forward_returns": {"BBB": 0.1}}]
        result = ev.walk_forward(periods)
        self.assertIsNone(result["periods"][0]["rank_ic"])

    def test_purge_periods_default_to_zero_reproducing_the_exact_prior_behavior(self):
        periods = synthetic_periods(6, 1.0)
        default = ev.walk_forward(periods)
        explicit_zero = ev.walk_forward(periods, purge_periods=0, embargo_periods=0)
        self.assertEqual(default, explicit_zero)

    def test_embargo_drops_the_most_recent_periods_whose_label_window_is_unresolved(self):
        periods = synthetic_periods(6, 1.0)
        result = ev.walk_forward(periods, embargo_periods=2)
        self.assertEqual(len(result["periods"]), 4)
        dates = [row["date"] for row in result["periods"]]
        self.assertEqual(dates, [period["date"] for period in periods[:4]])

    def test_purge_keeps_only_non_overlapping_periods_for_a_three_period_label(self):
        periods = synthetic_periods(9, 1.0)
        result = ev.walk_forward(periods, purge_periods=2)
        # A label spanning purge_periods+1=3 periods means adjacent periods' forward windows
        # overlap; only every third period is an independent (non-overlapping) observation.
        self.assertEqual(len(result["periods"]), 3)
        dates = [row["date"] for row in result["periods"]]
        self.assertEqual(dates, [periods[0]["date"], periods[3]["date"], periods[6]["date"]])


class PaperTradingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="paper-")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_logged_quantiles_can_be_graded_once_returns_exist(self):
        scores = {f"T{index}": float(index) for index in range(20)}
        ev.log_paper_period("candidate", "2026-07", scores, directory=self.directory)
        logged = ev.read_paper_log(self.directory)
        self.assertEqual(len(logged), 1)
        self.assertIn("T19", logged[0]["top_quantile"])

        realized = {f"T{index}": index * 0.001 for index in range(20)}
        graded = ev.score_paper_log({"2026-07": realized}, config="candidate",
                                    directory=self.directory)
        self.assertEqual(graded["graded_periods"], 1)
        self.assertAlmostEqual(graded["periods"][0]["rank_ic"], 1.0, places=4)

    def test_ungraded_periods_report_honestly(self):
        ev.log_paper_period("candidate", "2026-07", {"AAA": 50.0}, directory=self.directory)
        self.assertEqual(ev.score_paper_log({}, directory=self.directory)["periods"], 0)


class BlockBootstrapReturnCiTests(unittest.TestCase):
    def test_none_below_the_minimum_sample(self):
        self.assertIsNone(ev.block_bootstrap_return_ci([0.001] * 10))

    def test_ci_brackets_the_true_mean_on_a_clearly_positive_series(self):
        generator = random.Random(3)
        returns = [generator.gauss(0.003, 0.008) for _ in range(300)]
        result = ev.block_bootstrap_return_ci(returns, samples=500, seed=1)
        lo, hi = result["annualized_return_ci_95_pct"]
        self.assertLess(lo, result["mean_annualized_return_pct"])
        self.assertGreater(hi, result["mean_annualized_return_pct"])
        self.assertGreater(result["probability_return_positive"], 0.8)

    def test_a_clearly_negative_series_has_a_ci_entirely_below_zero(self):
        generator = random.Random(4)
        returns = [generator.gauss(-0.004, 0.004) for _ in range(300)]
        result = ev.block_bootstrap_return_ci(returns, samples=500, seed=1)
        lo, hi = result["annualized_return_ci_95_pct"]
        self.assertLess(hi, 0)
        self.assertLess(result["probability_return_positive"], 0.05)


class VarBacktestTests(unittest.TestCase):
    def test_kupiec_accepts_a_correctly_calibrated_breach_rate(self):
        # Exactly 5% breaches out of 400, evenly spaced -- a textbook well-calibrated model.
        breaches = 20
        result = ev.kupiec_pof_test(breaches, 400, confidence=0.95)
        self.assertFalse(result["miscalibrated_at_95"])
        self.assertAlmostEqual(result["observed_breach_rate"], 0.05)

    def test_kupiec_rejects_a_breach_rate_far_from_the_stated_coverage(self):
        result = ev.kupiec_pof_test(80, 400, confidence=0.95)
        self.assertTrue(result["miscalibrated_at_95"])

    def test_christoffersen_rejects_clustered_breaches(self):
        # All 20 breaches back-to-back in one run: maximally clustered.
        sequence = [0] * 190 + [1] * 20 + [0] * 190
        result = ev.christoffersen_independence_test(sequence)
        self.assertTrue(result["clustered_at_95"])

    def test_christoffersen_accepts_scattered_breaches(self):
        generator = random.Random(14)
        sequence = [1 if generator.random() < 0.1 else 0 for _ in range(400)]
        result = ev.christoffersen_independence_test(sequence)
        self.assertFalse(result["clustered_at_95"])

    def test_var_backtest_none_below_the_minimum_window(self):
        self.assertIsNone(ev.var_backtest([0.001] * 100, window=252))

    def test_var_backtest_runs_end_to_end_on_a_long_series(self):
        generator = random.Random(9)
        returns = [generator.gauss(0.0003, 0.01) for _ in range(600)]
        result = ev.var_backtest(returns, confidence=0.95, window=252)
        self.assertEqual(result["forecasts"], 600 - 252)
        self.assertIsNotNone(result["kupiec_pof"])
        self.assertIsNotNone(result["christoffersen_independence"])
        self.assertAlmostEqual(result["breach_rate"], result["expected_breach_rate"], delta=0.04)


class RealityCheckSpaTests(unittest.TestCase):
    def test_none_with_too_few_periods_or_configurations(self):
        self.assertIsNone(ev.reality_check_spa([[1.0]] * 20))
        self.assertIsNone(ev.reality_check_spa([[1.0, 2.0]] * 5))

    def test_identifies_the_genuinely_better_configuration(self):
        generator = random.Random(6)
        # Config 0 is genuinely better every period; the rest are noise around the same mean.
        matrix = [[generator.gauss(1.0, 0.3) if k == 0 else generator.gauss(0.0, 0.3)
                  for k in range(6)] for _ in range(30)]
        result = ev.reality_check_spa(matrix, samples=400, seed=2)
        self.assertEqual(result["best_configuration_index"], 0)
        self.assertLess(result["p_value"], 0.05)
        self.assertTrue(result["survives_search_at_95"])

    def test_p_value_is_high_when_no_configuration_beats_the_field(self):
        generator = random.Random(8)
        matrix = [[generator.gauss(0.0, 0.3) for _ in range(6)] for _ in range(30)]
        result = ev.reality_check_spa(matrix, samples=400, seed=2)
        self.assertGreater(result["p_value"], 0.05)


if __name__ == "__main__":
    unittest.main()
