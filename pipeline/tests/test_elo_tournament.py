import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import elo_tournament as elo
from optimization_harness import Panel, formula_weights


def synthetic_leg_periods(count, *, names=60, seed=11, noise=0.05,
                          predictive_legs=("good",), dead_legs=("bad",)):
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


class EloArithmeticTests(unittest.TestCase):
    def test_expected_scores_for_a_pair_sum_to_one(self):
        self.assertAlmostEqual(elo.expected_score(1500, 1400) + elo.expected_score(1400, 1500), 1.0)

    def test_equal_ratings_expect_a_coin_flip(self):
        self.assertAlmostEqual(elo.expected_score(1500, 1500), 0.5)

    def test_update_is_zero_sum(self):
        new_a, new_b = elo.update_elo(1500, 1500, 1.0, k=24)
        self.assertAlmostEqual((new_a - 1500) + (new_b - 1500), 0.0)

    def test_a_win_raises_the_winners_rating_and_lowers_the_losers(self):
        new_a, new_b = elo.update_elo(1500, 1500, 1.0, k=24)
        self.assertGreater(new_a, 1500)
        self.assertLess(new_b, 1500)

    def test_a_tie_between_equal_ratings_changes_nothing(self):
        new_a, new_b = elo.update_elo(1500, 1500, 0.5, k=24)
        self.assertAlmostEqual(new_a, 1500)
        self.assertAlmostEqual(new_b, 1500)


class RunTournamentTests(unittest.TestCase):
    def test_a_genuinely_better_candidate_ends_up_rated_higher(self):
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.02, seed=1)
        candidates = [("good_only", {"good": 1.0}), ("bad_only", {"bad": 1.0})]
        result = elo.run_tournament(periods, candidates, rounds=100, seed=0)
        ratings = result["ratings"]
        self.assertGreater(ratings["good_only"], ratings["bad_only"])
        self.assertEqual(result["leaderboard"][0]["name"], "good_only")

    def test_the_same_seed_reproduces_the_same_ratings(self):
        periods = synthetic_leg_periods(40, names=60, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.05, seed=2)
        candidates = [("a", {"good": 1.0}), ("b", {"bad": 1.0})]
        first = elo.run_tournament(periods, candidates, rounds=50, seed=5)
        second = elo.run_tournament(periods, candidates, rounds=50, seed=5)
        self.assertEqual(first["ratings"], second["ratings"])

    def test_a_different_seed_generally_gives_a_different_trajectory(self):
        periods = synthetic_leg_periods(40, names=60, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.05, seed=2)
        candidates = [("a", {"good": 1.0}), ("b", {"bad": 1.0})]
        first = elo.run_tournament(periods, candidates, rounds=50, seed=5)
        second = elo.run_tournament(periods, candidates, rounds=50, seed=6)
        self.assertNotEqual(first["history"], second["history"])

    def test_indistinguishable_candidates_stay_close_rather_than_manufacturing_a_winner(self):
        # Two candidates with the exact same weights on the exact same data must never
        # diverge -- there's no real edge for repeated resampling to find, and the
        # tournament must not fabricate one out of noise alone.
        periods = synthetic_leg_periods(50, names=60, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.04, seed=3)
        candidates = [("x", {"good": 0.6, "bad": 0.4}), ("y", {"good": 0.6, "bad": 0.4})]
        result = elo.run_tournament(periods, candidates, rounds=150, seed=9)
        self.assertLess(abs(result["ratings"]["x"] - result["ratings"]["y"]), 50)

    def test_at_least_two_candidates_are_required(self):
        with self.assertRaises(ValueError):
            elo.run_tournament([{"leg_scores": {}, "forward_returns": {}}],
                               [("solo", {"good": 1.0})], rounds=10)

    def test_at_least_one_round_is_required(self):
        with self.assertRaises(ValueError):
            elo.run_tournament([{"leg_scores": {}, "forward_returns": {}}],
                               [("a", {"good": 1.0}), ("b", {"bad": 1.0})], rounds=0)

    def test_empty_periods_are_rejected_rather_than_dividing_by_zero(self):
        with self.assertRaises(ValueError):
            elo.run_tournament([], [("a", {"good": 1.0}), ("b", {"bad": 1.0})], rounds=10)


class FormulaCandidateIntegrationTests(unittest.TestCase):
    def test_a_formula_candidate_derived_from_train_can_be_entered_into_a_tournament_on_validation(self):
        periods = synthetic_leg_periods(80, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.03, seed=4)
        panel = Panel(periods, train_fraction=0.5, validation_fraction=0.375)
        formula = formula_weights(panel.train)
        self.assertTrue(formula)
        candidates = [("champion", {"good": 0.5, "bad": 0.5}), ("formula", formula)]
        result = elo.run_tournament(panel.validation, candidates, rounds=80, seed=0)
        # The formula candidate (which learned "good" matters from the train slice) should
        # beat an even 50/50 blend on the held-out validation slice.
        self.assertGreater(result["ratings"]["formula"], result["ratings"]["champion"])


if __name__ == "__main__":
    unittest.main()
