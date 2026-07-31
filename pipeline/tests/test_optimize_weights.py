import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import advisor_engine
import optimize_weights as ow
from scorer import SETTINGS


class DirichletTests(unittest.TestCase):
    def test_weights_are_nonnegative_and_sum_to_one(self):
        random.seed(1)
        for _ in range(20):
            weights = ow.random_weights(ow.RANKING_KEYS, concentration=1.0)
            self.assertEqual(set(weights), set(ow.RANKING_KEYS))
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)
            self.assertTrue(all(v >= 0 for v in weights.values()))

    def test_category_weights_cover_all_six_categories(self):
        random.seed(2)
        weights = ow.random_weights(ow.CATEGORY_KEYS, concentration=1.0)
        self.assertEqual(set(weights), set(ow.CATEGORY_KEYS))
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)


class CacheKeyTests(unittest.TestCase):
    def test_symbol_order_does_not_change_the_key(self):
        a = ow.cache_key(["AAPL", "MSFT"], 52, 45, ["SPY"])
        b = ow.cache_key(["MSFT", "AAPL"], 52, 45, ["SPY"])
        self.assertEqual(a, b)

    def test_different_weeks_change_the_key(self):
        a = ow.cache_key(["AAPL"], 52, 45, ["SPY"])
        b = ow.cache_key(["AAPL"], 26, 45, ["SPY"])
        self.assertNotEqual(a, b)


class RunTrialTests(unittest.TestCase):
    def setUp(self):
        self.baseline_ranking = dict(advisor_engine.RANKING_WEIGHTS)
        self.baseline_categories = dict(SETTINGS["fundamentals"]["category_weights"])

    def tearDown(self):
        advisor_engine.RANKING_WEIGHTS = self.baseline_ranking
        SETTINGS["fundamentals"]["category_weights"] = self.baseline_categories

    def test_empty_universe_leaves_contributions_as_idle_cash_without_crashing(self):
        # With no candidates there's nothing to buy, so the monthly contribution just sits
        # as cash -- flat, not a crash and not a loss.
        benchmarks = {"SPY": {"dates": ["2025-01-06", "2025-01-13"], "closes": [500.0, 505.0]}}
        week_dates = [__import__("datetime").date(2025, 1, 6), __import__("datetime").date(2025, 1, 13)]
        result = ow.run_trial(
            {}, benchmarks, week_dates,
            ranking_weights={"fundamentals": 0.5, "market_behavior": 0.3, "news_sentiment": 0.2},
            category_weights=self.baseline_categories,
            top_n=20, monthly_contribution=1000.0, report_lag_days=45,
        )
        self.assertEqual(result["return_pct"], 0.0)
        self.assertEqual(result["final_value"], 1000)

    def test_trial_weights_are_applied_to_the_global_scoring_config(self):
        benchmarks = {"SPY": {"dates": ["2025-01-06"], "closes": [500.0]}}
        week_dates = [__import__("datetime").date(2025, 1, 6)]
        trial_ranking = {"fundamentals": 0.2, "market_behavior": 0.3, "news_sentiment": 0.5}
        trial_categories = {k: 1 / 6 for k in ow.CATEGORY_KEYS}
        ow.run_trial({}, benchmarks, week_dates, trial_ranking, trial_categories,
                     top_n=20, monthly_contribution=1000.0, report_lag_days=45)
        self.assertEqual(advisor_engine.RANKING_WEIGHTS, trial_ranking)
        self.assertEqual(SETTINGS["fundamentals"]["category_weights"], trial_categories)


class RunSweepTests(unittest.TestCase):
    def setUp(self):
        self.baseline_ranking = dict(advisor_engine.RANKING_WEIGHTS)
        self.baseline_categories = dict(SETTINGS["fundamentals"]["category_weights"])

    def tearDown(self):
        advisor_engine.RANKING_WEIGHTS = self.baseline_ranking
        SETTINGS["fundamentals"]["category_weights"] = self.baseline_categories

    def test_first_trial_is_always_the_baseline_configuration(self):
        random.seed(3)
        benchmarks = {"SPY": {"dates": ["2025-01-06"], "closes": [500.0]}}
        week_dates = [__import__("datetime").date(2025, 1, 6)]
        results = ow.run_sweep(
            "blend", ow.RANKING_KEYS, self.baseline_ranking, None, self.baseline_categories,
            {}, benchmarks, week_dates, trials=3, concentration=1.0,
            top_n=20, monthly_contribution=1000.0, report_lag_days=45,
        )
        self.assertEqual(len(results), 4)  # baseline + 3 random trials
        baseline_entries = [r for r in results if r["is_baseline"]]
        self.assertEqual(len(baseline_entries), 1)
        self.assertEqual(baseline_entries[0]["weights"], self.baseline_ranking)


class EvaluateHoldoutTests(unittest.TestCase):
    def setUp(self):
        self.baseline_ranking = dict(advisor_engine.RANKING_WEIGHTS)
        self.baseline_categories = dict(SETTINGS["fundamentals"]["category_weights"])

    def tearDown(self):
        advisor_engine.RANKING_WEIGHTS = self.baseline_ranking
        SETTINGS["fundamentals"]["category_weights"] = self.baseline_categories

    def test_attaches_holdout_fields_to_the_baseline_and_top_finishers_only(self):
        random.seed(4)
        benchmarks = {"SPY": {"dates": ["2025-01-06"], "closes": [500.0]}}
        train_dates = [__import__("datetime").date(2025, 1, 6)]
        test_folds = [[__import__("datetime").date(2025, 2, 3)], [__import__("datetime").date(2025, 3, 3)]]
        results = ow.run_sweep(
            "blend", ow.RANKING_KEYS, self.baseline_ranking, None, self.baseline_categories,
            {}, benchmarks, train_dates, trials=5, concentration=1.0,
            top_n=20, monthly_contribution=1000.0, report_lag_days=45,
        )
        ow.evaluate_holdout("blend", results, top_k=2, other_fixed_ranking=None,
                            other_fixed_categories=self.baseline_categories,
                            universe_data={}, benchmarks=benchmarks, test_folds=test_folds,
                            top_n=20, monthly_contribution=1000.0, report_lag_days=45)

        checked = [r for r in results if "holdout_folds" in r]
        # Top 2 finishers plus the baseline, unless the baseline is already in the top 2.
        self.assertLessEqual(len(checked), 3)
        self.assertTrue(any(r["is_baseline"] for r in checked))
        for r in checked:
            self.assertEqual(len(r["holdout_folds"]), 2)
            self.assertIn("holdout_mean_score", r)
            self.assertIn("holdout_min_score", r)
        non_baseline = [r for r in checked if not r["is_baseline"]]
        for r in non_baseline:
            self.assertIn("holdout_folds_beating_baseline", r)
            self.assertTrue(r["holdout_folds_beating_baseline"].endswith("/2"))

    def test_leaves_scoring_config_at_whatever_the_last_call_set(self):
        # evaluate_holdout doesn't restore state itself -- that's main()'s job via try/finally --
        # but it should still leave the config matching its own last trial, not something stale.
        random.seed(5)
        benchmarks = {"SPY": {"dates": ["2025-01-06"], "closes": [500.0]}}
        results = [{"trial": 0, "is_baseline": True, "weights": self.baseline_ranking,
                   "return_pct": 0.0, "final_value": 0, "score_vs_spy": 5.0}]
        ow.evaluate_holdout("blend", results, top_k=1, other_fixed_ranking=None,
                            other_fixed_categories=self.baseline_categories,
                            universe_data={}, benchmarks=benchmarks,
                            test_folds=[[__import__("datetime").date(2025, 2, 3)]],
                            top_n=20, monthly_contribution=1000.0, report_lag_days=45)
        self.assertEqual(advisor_engine.RANKING_WEIGHTS, self.baseline_ranking)


class SplitIntoFoldsTests(unittest.TestCase):
    def test_single_fold_returns_the_whole_list(self):
        dates = list(range(10))
        self.assertEqual(ow.split_into_folds(dates, 1), [dates])

    def test_splits_into_the_requested_number_of_consecutive_folds(self):
        dates = list(range(10))
        folds = ow.split_into_folds(dates, 3)
        self.assertEqual(len(folds), 3)
        self.assertEqual(sum(folds, []), dates)  # nothing lost or reordered

    def test_remainder_merges_into_the_last_fold_rather_than_dropping(self):
        dates = list(range(7))
        folds = ow.split_into_folds(dates, 3)
        self.assertEqual(len(folds), 3)
        self.assertEqual(sum(folds, []), dates)


if __name__ == "__main__":
    unittest.main()
