import os
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import run_backtest_suite as suite


class DefaultCandidatesTests(unittest.TestCase):
    def test_fundamentals_reads_the_explicit_weight_map_not_a_guessed_attribute_name(self):
        # Regression: an earlier draft guessed the attribute name from the strategy id
        # (f"{strategy_id.upper()}_WEIGHTS") -- for "reweighted_composite_a" that guesses
        # "REWEIGHTED_COMPOSITE_A_WEIGHTS", which does not exist (the real constant is
        # shadow_portfolios.REWEIGHTED_A_WEIGHTS), so the guess silently returned nothing.
        candidates = suite.default_candidates("fundamentals")
        names = [name for name, _ in candidates]
        self.assertIn("reweighted_composite_a", names)
        weights = dict(candidates)["reweighted_composite_a"]
        self.assertGreater(sum(weights.values()), 0)

    def test_a_candidate_not_currently_registered_is_excluded(self):
        import shadow_portfolios
        with patch.object(shadow_portfolios, "RESEARCH_CANDIDATE_WEIGHTS",
                          {**shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS,
                           "not_registered": {"valuation": 1.0}}):
            names = [name for name, _ in suite.default_candidates("fundamentals")]
        self.assertNotIn("not_registered", names)

    def test_swing_domain_returns_the_registered_reversal_b_weights_verbatim(self):
        candidates = suite.default_candidates("swing")
        names = [name for name, _ in candidates]
        self.assertIn("swing-reversal-B", names)
        weights = dict(candidates)["swing-reversal-B"]
        self.assertEqual(weights, suite.SWING_REVERSAL_B_WEIGHTS)
        self.assertNotIn("short_term_reversal", weights)


class RandomNeighborTests(unittest.TestCase):
    BASE = {"a": 0.5, "b": 0.3, "c": 0.2}

    def test_preserves_the_total_weight_mass(self):
        rng = random.Random(1)
        neighbor = suite.random_neighbor(self.BASE, rng, perturbation=0.5, drop_probability=0.0)
        self.assertAlmostEqual(sum(neighbor.values()), sum(self.BASE.values()), places=4)

    def test_zero_drop_probability_never_drops_a_leg(self):
        rng = random.Random(2)
        for _ in range(50):
            neighbor = suite.random_neighbor(self.BASE, rng, perturbation=0.3, drop_probability=0.0)
            self.assertEqual(set(neighbor), set(self.BASE))

    def test_a_guaranteed_drop_still_returns_a_usable_nonempty_candidate(self):
        # drop_probability=1.0 would zero every leg; the degenerate-draw fallback must kick
        # in rather than emit a candidate the harness can't score.
        rng = random.Random(3)
        neighbor = suite.random_neighbor(self.BASE, rng, perturbation=0.5, drop_probability=1.0)
        self.assertTrue(neighbor)
        self.assertGreater(sum(neighbor.values()), 0)

    def test_the_same_seed_reproduces_the_same_batch(self):
        first = suite.auto_search_candidates(self.BASE, count=5, seed=7, perturbation=0.4,
                                             drop_probability=0.2)
        second = suite.auto_search_candidates(self.BASE, count=5, seed=7, perturbation=0.4,
                                              drop_probability=0.2)
        self.assertEqual(first, second)

    def test_a_different_seed_generally_produces_a_different_batch(self):
        first = suite.auto_search_candidates(self.BASE, count=5, seed=7, perturbation=0.4,
                                             drop_probability=0.2)
        second = suite.auto_search_candidates(self.BASE, count=5, seed=8, perturbation=0.4,
                                              drop_probability=0.2)
        self.assertNotEqual(first, second)


class RankKeyTests(unittest.TestCase):
    def test_promote_sorts_before_keep_as_challenger_before_abandon(self):
        candidates = [
            {"suggested_decision": "ABANDON", "validation_mean_ic": 0.5},
            {"suggested_decision": "PROMOTE", "validation_mean_ic": 0.01},
            {"suggested_decision": "KEEP_AS_CHALLENGER", "validation_mean_ic": 0.3},
        ]
        candidates.sort(key=suite.rank_key)
        self.assertEqual([c["suggested_decision"] for c in candidates],
                         ["PROMOTE", "KEEP_AS_CHALLENGER", "ABANDON"])

    def test_within_a_tier_higher_validation_ic_sorts_first(self):
        candidates = [
            {"suggested_decision": "KEEP_AS_CHALLENGER", "validation_mean_ic": 0.01},
            {"suggested_decision": "KEEP_AS_CHALLENGER", "validation_mean_ic": 0.05},
        ]
        candidates.sort(key=suite.rank_key)
        self.assertEqual([c["validation_mean_ic"] for c in candidates], [0.05, 0.01])

    def test_a_missing_ic_does_not_raise_and_sorts_last_in_its_tier(self):
        candidates = [
            {"suggested_decision": "ABANDON", "validation_mean_ic": None},
            {"suggested_decision": "ABANDON", "validation_mean_ic": -0.02},
        ]
        candidates.sort(key=suite.rank_key)
        self.assertEqual([c["validation_mean_ic"] for c in candidates], [-0.02, None])


if __name__ == "__main__":
    unittest.main()
