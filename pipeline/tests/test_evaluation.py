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


if __name__ == "__main__":
    unittest.main()


# --- unresolved trailing labels are purged ------------------------------------------------

def _period(date, scores, returns):
    return {"date": date, "scores": scores, "forward_returns": returns}


def _series(count):
    return [_period(f"2024-{month:02d}-01",
                    {"A": 90.0, "B": 50.0, "C": 10.0},
                    {"A": 0.05, "B": 0.01, "C": -0.03})
            for month in range(1, count + 1)]


def test_walk_forward_purges_the_trailing_unresolved_periods():
    """A 63-session label observed monthly is unresolved for the last two periods."""
    full = ev.walk_forward(_series(10))
    purged = ev.walk_forward(_series(10), purge_periods=2)

    assert len(full["periods"]) == 10
    assert len(purged["periods"]) == 8
    assert purged["purged_periods"] == 2
    assert purged["periods"][-1]["date"] == "2024-08-01"


def test_purging_defaults_to_off_so_existing_callers_are_unchanged():
    assert ev.walk_forward(_series(6))["purged_periods"] == 0
    assert len(ev.walk_forward(_series(6))["periods"]) == 6


def test_purging_more_periods_than_exist_leaves_nothing_rather_than_wrapping():
    result = ev.walk_forward(_series(3), purge_periods=5)
    assert result["periods"] == []


def test_negative_purge_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        ev.walk_forward(_series(3), purge_periods=-1)


def test_evaluate_candidate_forwards_the_purge():
    verdict = ev.evaluate_candidate(_series(10), trials=3, purge_periods=2)
    assert verdict["purged_periods"] == 2
    assert len(verdict["periods"]) == 8
