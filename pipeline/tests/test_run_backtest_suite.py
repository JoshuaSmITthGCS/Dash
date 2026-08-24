import argparse
import json
import os
import random
import sys
import tempfile
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


class UniverseLegsTests(unittest.TestCase):
    def test_collects_every_leg_that_appears_anywhere_in_the_panel(self):
        periods = [
            {"leg_scores": {"A": {"x": 1.0, "y": 2.0}}},
            {"leg_scores": {"B": {"z": 3.0}}},
        ]
        self.assertEqual(suite.universe_legs(periods), ["x", "y", "z"])

    def test_empty_periods_give_an_empty_universe(self):
        self.assertEqual(suite.universe_legs([]), [])


class RangeSampledCandidateTests(unittest.TestCase):
    LEGS = ["a", "b", "c", "d"]

    def test_every_declared_leg_is_present_and_weights_sum_to_one(self):
        rng = random.Random(1)
        candidate = suite.range_sampled_candidate(self.LEGS, rng, minimum=0.0, maximum=0.4)
        self.assertEqual(set(candidate), set(self.LEGS))
        self.assertAlmostEqual(sum(candidate.values()), 1.0, places=4)

    def test_a_nonzero_minimum_is_respected_before_normalization(self):
        # Each raw draw before normalization must be >= minimum; normalization can shrink
        # them proportionally but never reorders which leg got the smallest raw draw versus
        # the largest, so if every raw draw is >= minimum, the two smallest normalized
        # weights should reflect that floor relative to each other, not collapse to zero.
        rng = random.Random(2)
        candidate = suite.range_sampled_candidate(self.LEGS, rng, minimum=0.1, maximum=0.1)
        # minimum == maximum: every leg gets an identical raw draw, so after normalization
        # every leg must end up with an exactly equal share.
        for weight in candidate.values():
            self.assertAlmostEqual(weight, 1.0 / len(self.LEGS), places=4)

    def test_the_same_seed_reproduces_the_same_candidate(self):
        first = suite.range_sampled_candidate(self.LEGS, random.Random(5), minimum=0.0, maximum=0.4)
        second = suite.range_sampled_candidate(self.LEGS, random.Random(5), minimum=0.0, maximum=0.4)
        self.assertEqual(first, second)


class RangeSearchCandidatesTests(unittest.TestCase):
    def test_generates_exactly_the_requested_count(self):
        candidates = suite.range_search_candidates(["a", "b"], count=7, seed=0,
                                                    minimum=0.0, maximum=0.4)
        self.assertEqual(len(candidates), 7)

    def test_the_same_seed_reproduces_the_same_batch(self):
        first = suite.range_search_candidates(["a", "b", "c"], count=5, seed=3,
                                              minimum=0.0, maximum=0.4)
        second = suite.range_search_candidates(["a", "b", "c"], count=5, seed=3,
                                               minimum=0.0, maximum=0.4)
        self.assertEqual(first, second)

    def test_a_different_seed_generally_produces_a_different_batch(self):
        first = suite.range_search_candidates(["a", "b", "c"], count=5, seed=3,
                                              minimum=0.0, maximum=0.4)
        second = suite.range_search_candidates(["a", "b", "c"], count=5, seed=4,
                                               minimum=0.0, maximum=0.4)
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


class HoldoutCheckTests(unittest.TestCase):
    def test_evaluates_only_the_holdout_slice_not_train_or_validation(self):
        import optimization_harness as harness
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.03, seed=1)
        panel = harness.Panel(periods, train_fraction=0.5, validation_fraction=0.3)
        candidates = [("champion", {"good": 0.5, "bad": 0.5}), ("winner", {"good": 1.0})]
        results = suite.holdout_check(panel, candidates, trial_count=1)
        names = [row["name"] for row in results]
        self.assertEqual(names, ["champion", "winner"])
        for row in results:
            self.assertLessEqual(row["holdout_periods"], len(panel.holdout))

    def test_a_genuinely_predictive_candidate_reads_a_higher_holdout_ic(self):
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.02, seed=2)
        import optimization_harness as harness
        panel = harness.Panel(periods, train_fraction=0.5, validation_fraction=0.3)
        candidates = [("good_only", {"good": 1.0}), ("bad_only", {"bad": 1.0})]
        results = suite.holdout_check(panel, candidates, trial_count=1)
        by_name = {row["name"]: row for row in results}
        self.assertGreater(by_name["good_only"]["holdout_mean_ic"] or 0,
                           by_name["bad_only"]["holdout_mean_ic"] or 0)

    def test_each_row_carries_a_deflated_sharpe_and_ship_verdict(self):
        import optimization_harness as harness
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.03, seed=3)
        panel = harness.Panel(periods, train_fraction=0.5, validation_fraction=0.3)
        results = suite.holdout_check(panel, [("champion", {"good": 1.0})], trial_count=5)
        row = results[0]
        self.assertIn("deflated_sharpe_probability", row)
        self.assertIn("ship", row)


class RecommendedWeightsTests(unittest.TestCase):
    def test_fundamentals_prefers_reweighted_composite_a_when_registered(self):
        import shadow_portfolios
        registered = shadow_portfolios.research_candidate_strategies()
        if "reweighted_composite_a" not in registered:
            self.skipTest("reweighted_composite_a not currently registered")
        name, weights = suite.recommended_weights("fundamentals")
        self.assertEqual(name, "reweighted_composite_a")
        self.assertGreater(sum(weights.values()), 0)

    def test_swing_returns_the_registered_reversal_b_weights(self):
        name, weights = suite.recommended_weights("swing")
        self.assertEqual(name, "swing-reversal-B")
        self.assertEqual(weights, suite.SWING_REVERSAL_B_WEIGHTS)


class SharedExtraCandidatesTests(unittest.TestCase):
    PERIODS = [{"leg_scores": {"T1": {"valuation": 1.0, "profitability": 2.0}}}]

    def _args(self, **overrides):
        base = {"include_equal_weight": False, "include_blend": False, "blend_ratio": 0.5}
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_neither_flag_set_returns_nothing(self):
        self.assertEqual(suite.shared_extra_candidates(self._args(), "fundamentals", self.PERIODS), [])

    def test_include_equal_weight_adds_exactly_one_candidate_covering_every_panel_leg(self):
        extra = suite.shared_extra_candidates(self._args(include_equal_weight=True),
                                              "fundamentals", self.PERIODS)
        names = [name for name, _ in extra]
        self.assertIn("equal_weight", names)
        weights = dict(extra)["equal_weight"]
        self.assertEqual(set(weights), {"valuation", "profitability"})

    def test_include_blend_adds_a_candidate_covering_every_panel_leg(self):
        extra = suite.shared_extra_candidates(self._args(include_blend=True),
                                              "fundamentals", self.PERIODS)
        self.assertEqual(len(extra), 1)
        name, weights = extra[0]
        self.assertTrue(name.startswith("equal_blend_"))
        self.assertEqual(set(weights), {"valuation", "profitability"})

    def test_both_flags_add_two_distinctly_named_candidates(self):
        extra = suite.shared_extra_candidates(
            self._args(include_equal_weight=True, include_blend=True), "fundamentals", self.PERIODS)
        names = [name for name, _ in extra]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)


class TopCandidatesFromEloTests(unittest.TestCase):
    def _write_elo_results(self, leaderboard, candidates):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"leaderboard": leaderboard, "candidates": candidates}, handle)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return handle.name

    def test_returns_the_top_n_in_leaderboard_order(self):
        path = self._write_elo_results(
            [{"name": "champion", "elo": 1600}, {"name": "b", "elo": 1550},
             {"name": "a", "elo": 1500}],
            {"champion": {"x": 1.0}, "b": {"x": 0.6}, "a": {"x": 0.4}},
        )
        picked = suite.top_candidates_from_elo(path, 2, exclude=set())
        self.assertEqual([name for name, _ in picked], ["champion", "b"])

    def test_excluded_names_are_skipped(self):
        path = self._write_elo_results(
            [{"name": "champion", "elo": 1600}, {"name": "b", "elo": 1550}],
            {"champion": {"x": 1.0}, "b": {"x": 0.6}},
        )
        picked = suite.top_candidates_from_elo(path, 2, exclude={"champion"})
        self.assertEqual([name for name, _ in picked], ["b"])

    def test_a_leaderboard_name_missing_from_candidates_is_skipped_not_raised(self):
        path = self._write_elo_results(
            [{"name": "ghost", "elo": 1600}, {"name": "b", "elo": 1550}],
            {"b": {"x": 0.6}},
        )
        picked = suite.top_candidates_from_elo(path, 2, exclude=set())
        self.assertEqual([name for name, _ in picked], ["b"])


if __name__ == "__main__":
    unittest.main()
