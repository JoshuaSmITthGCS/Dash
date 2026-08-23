import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import optimization_harness as harness


def synthetic_leg_periods(count, *, names=60, seed=11, noise=0.05,
                          predictive_legs=("good",), dead_legs=("bad",)):
    """Periods with two-leg ``leg_scores``: legs in ``predictive_legs`` actually predict the
    forward return, legs in ``dead_legs`` are pure noise unrelated to it.
    """
    generator = random.Random(seed)
    periods = []
    for index in range(count):
        leg_scores, forwards = {}, {}
        for position in range(names):
            ticker = f"T{position}"
            true_score = generator.uniform(0, 100)
            forward = (true_score - 50) / 50 * 0.02 + generator.gauss(0, noise)
            legs = {}
            for leg in predictive_legs:
                legs[leg] = true_score
            for leg in dead_legs:
                legs[leg] = generator.uniform(0, 100)
            leg_scores[ticker] = legs
            forwards[ticker] = forward
        periods.append({"date": f"2026-{index + 1:02d}", "leg_scores": leg_scores,
                        "forward_returns": forwards})
    return periods


class PanelTests(unittest.TestCase):
    def test_split_is_chronological_and_disjoint(self):
        periods = synthetic_leg_periods(20)
        panel = harness.Panel(periods, train_fraction=0.5, validation_fraction=0.25)
        self.assertEqual(len(panel.train), 10)
        self.assertEqual(len(panel.validation), 5)
        self.assertEqual(len(panel.holdout), 5)
        # No shuffling: train is a prefix, validation the next slice, holdout the remainder.
        self.assertEqual(panel.train, tuple(periods[:10]))
        self.assertEqual(panel.validation, tuple(periods[10:15]))
        self.assertEqual(panel.holdout, tuple(periods[15:]))

    def test_fractions_outside_zero_one_are_rejected(self):
        periods = synthetic_leg_periods(10)
        with self.assertRaises(ValueError):
            harness.Panel(periods, train_fraction=1.0, validation_fraction=0.1)
        with self.assertRaises(ValueError):
            harness.Panel(periods, train_fraction=0.8, validation_fraction=0.3)

    def test_a_panel_too_short_for_the_split_is_rejected_rather_than_silently_empty(self):
        periods = synthetic_leg_periods(2)
        with self.assertRaises(ValueError):
            harness.Panel(periods, train_fraction=0.5, validation_fraction=0.4)


class ScoreWithWeightsTests(unittest.TestCase):
    def test_scores_are_the_weighted_blend_and_leg_scores_survive(self):
        periods = synthetic_leg_periods(3, names=4)
        scored = harness.score_with_weights(periods, {"good": 1.0})
        self.assertIn("scores", scored[0])
        self.assertIn("leg_scores", scored[0])
        for ticker, legs in periods[0]["leg_scores"].items():
            self.assertAlmostEqual(scored[0]["scores"][ticker], legs["good"])


class OptimizationSessionTests(unittest.TestCase):
    def test_evaluate_never_touches_the_holdout_slice(self):
        periods = synthetic_leg_periods(20)
        panel = harness.Panel(periods)
        session = harness.OptimizationSession(panel, trial_count=10)
        original_holdout = panel.holdout
        session.evaluate("good-only", {"good": 1.0})
        # The holdout slice object itself must be unread and unmodified.
        self.assertEqual(panel.holdout, original_holdout)

    def test_a_predictive_leg_beats_a_dead_leg_on_validation_ic(self):
        periods = synthetic_leg_periods(40, names=80)
        panel = harness.Panel(periods)
        session = harness.OptimizationSession(panel, trial_count=10)
        good = session.evaluate("good-only", {"good": 1.0})
        bad = session.evaluate("bad-only", {"bad": 1.0})
        self.assertGreater(good["validation_mean_ic"], bad["validation_mean_ic"])

    def test_trial_count_defaults_to_the_experiment_registry_total(self):
        import experiment_registry
        periods = synthetic_leg_periods(20)
        panel = harness.Panel(periods)
        session = harness.OptimizationSession(panel)
        self.assertEqual(session.trial_count, experiment_registry.total_variants_tested())

    def test_walk_forward_efficiency_is_the_validation_over_train_ic_ratio(self):
        periods = synthetic_leg_periods(30, names=80)
        panel = harness.Panel(periods)
        session = harness.OptimizationSession(panel, trial_count=10)
        record = session.evaluate("good-only", {"good": 1.0})
        if record["train_mean_ic"]:
            expected = round(record["validation_mean_ic"] / record["train_mean_ic"], 4)
            self.assertEqual(record["walk_forward_efficiency"], expected)


class ProbabilityOfOverfittingTests(unittest.TestCase):
    def test_noise_only_candidates_land_near_the_overfitting_line(self):
        periods = synthetic_leg_periods(80, names=40, predictive_legs=(), dead_legs=("a", "b", "c"))
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.5)
        session = harness.OptimizationSession(panel, trial_count=10, pbo_splits=8)
        candidates = [(f"cfg-{leg}", {leg: 1.0}) for leg in ("a", "b", "c")]
        result = session.probability_of_overfitting(candidates)
        self.assertIsNotNone(result["pbo"])
        self.assertGreater(result["pbo"], 0.25)

    def test_one_genuinely_dominant_candidate_has_low_pbo(self):
        periods = synthetic_leg_periods(80, names=40, predictive_legs=("good",),
                                        dead_legs=("noise1", "noise2"), noise=0.2)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.5)
        session = harness.OptimizationSession(panel, trial_count=10, pbo_splits=8)
        candidates = [("winner", {"good": 1.0}), ("noise-a", {"noise1": 1.0}),
                     ("noise-b", {"noise2": 1.0})]
        result = session.probability_of_overfitting(candidates)
        self.assertIsNotNone(result["pbo"])
        self.assertLess(result["pbo"], 0.5)


class ClassifyTests(unittest.TestCase):
    def test_a_search_wide_overfit_result_abandons_every_candidate_regardless_of_its_own_numbers(self):
        # Three legs, all pure noise: any apparent "winner" among them is selection, not skill.
        periods = synthetic_leg_periods(80, names=40, predictive_legs=(), dead_legs=("a", "b", "c"), seed=7)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.5)
        session = harness.OptimizationSession(panel, trial_count=10, pbo_splits=8)
        candidates = [(f"cfg-{leg}", {leg: 1.0}) for leg in ("a", "b", "c")]
        report = harness.classify(session, candidates)
        if report["search_overfitting"]["pbo"] is not None and \
                report["search_overfitting"]["pbo"] >= harness.OVERFITTING_LINE:
            for candidate in report["candidates"]:
                self.assertEqual(candidate["suggested_decision"], "ABANDON")
                self.assertIn("PBO", candidate["reason"])

    def test_a_genuinely_predictive_candidate_is_not_classified_abandon_for_lack_of_signal(self):
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("noise",), noise=0.03, seed=13)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        session = harness.OptimizationSession(panel, trial_count=1, pbo_splits=8)
        candidates = [("winner", {"good": 1.0}), ("loser", {"noise": 1.0})]
        report = harness.classify(session, candidates)
        winner = next(c for c in report["candidates"] if c["name"] == "winner")
        self.assertIn(winner["suggested_decision"], ("PROMOTE", "KEEP_AS_CHALLENGER"))


if __name__ == "__main__":
    unittest.main()
