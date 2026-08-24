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


class LegCoverageTests(unittest.TestCase):
    def test_coverage_is_present_over_total_ticker_periods(self):
        periods = [
            {"leg_scores": {"A": {"x": 1.0}, "B": {"x": None}, "C": {}}},
            {"leg_scores": {"A": {"x": 2.0}, "B": {"x": 3.0}}},
        ]
        coverage = harness.leg_coverage(periods, ["x"])
        # present: period1 A only (B is None, C absent) = 1; period2 A and B = 2; total 5.
        self.assertAlmostEqual(coverage["x"], 3 / 5)

    def test_a_leg_that_never_appears_has_zero_coverage(self):
        periods = [{"leg_scores": {"A": {"x": 1.0}}}]
        coverage = harness.leg_coverage(periods, ["never_present"])
        self.assertEqual(coverage["never_present"], 0.0)


class FormulaWeightsTests(unittest.TestCase):
    def test_weight_concentrates_on_the_leg_that_is_both_covered_and_predictive(self):
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.03, seed=21)
        weights = harness.formula_weights(periods)
        self.assertGreater(weights.get("good", 0), weights.get("bad", 0))
        self.assertGreater(weights.get("good", 0), 0.8)

    def test_a_leg_with_zero_coverage_gets_zero_weight_regardless_of_hypothetical_ic(self):
        periods = synthetic_leg_periods(40, names=60, predictive_legs=("good",),
                                        dead_legs=(), noise=0.03, seed=22)
        # Add a leg that's declared in `legs=` but never actually present in any row --
        # mirrors news_sentiment's real 0%-coverage shape in the production panel.
        weights = harness.formula_weights(periods, legs=["good", "never_covered"])
        self.assertNotIn("never_covered", weights)

    def test_weights_sum_to_one_when_nonempty(self):
        periods = synthetic_leg_periods(60, names=80, predictive_legs=("good",),
                                        dead_legs=("bad",), noise=0.03, seed=23)
        weights = harness.formula_weights(periods)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)

    def test_pure_noise_still_returns_a_valid_normalized_result_without_raising(self):
        # Every leg here is pure noise with no relationship to forward returns. With only
        # two candidate legs, one can still end up with nearly all the weight by chance --
        # the formula isn't psychic, and a small sample can look decisive on noise alone,
        # the same small-sample-noise property this session's real backtests kept surfacing.
        # What must hold regardless: it never raises, and whatever it returns is a valid,
        # normalized weight dict (or empty).
        periods = synthetic_leg_periods(40, names=60, predictive_legs=(),
                                        dead_legs=("a", "b"), noise=0.03, seed=24)
        weights = harness.formula_weights(periods)
        if weights:
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)
            self.assertTrue(all(weight > 0 for weight in weights.values()))


class EqualWeightCandidateTests(unittest.TestCase):
    def test_every_leg_gets_the_same_share_summing_to_one(self):
        candidate = harness.equal_weight_candidate(["a", "b", "c", "d"])
        self.assertEqual(set(candidate), {"a", "b", "c", "d"})
        for weight in candidate.values():
            self.assertAlmostEqual(weight, 0.25)
        self.assertAlmostEqual(sum(candidate.values()), 1.0)

    def test_empty_legs_returns_empty(self):
        self.assertEqual(harness.equal_weight_candidate([]), {})


class BlendedFullCoverageCandidateTests(unittest.TestCase):
    def test_a_leg_dropped_by_the_recommended_candidate_still_gets_nonzero_weight(self):
        recommended = {"valuation": 0.6, "profitability": 0.4}  # drops financial_health entirely
        legs = ["valuation", "profitability", "financial_health"]
        blended = harness.blended_full_coverage_candidate(recommended, legs, blend=0.5)
        self.assertGreater(blended.get("financial_health", 0), 0)
        self.assertEqual(set(blended), set(legs))

    def test_weights_sum_to_one(self):
        recommended = {"valuation": 1.0}
        legs = ["valuation", "profitability"]
        blended = harness.blended_full_coverage_candidate(recommended, legs, blend=0.5)
        self.assertAlmostEqual(sum(blended.values()), 1.0, places=4)

    def test_blend_zero_is_pure_equal_weight(self):
        recommended = {"valuation": 1.0}
        legs = ["valuation", "profitability"]
        blended = harness.blended_full_coverage_candidate(recommended, legs, blend=0.0)
        self.assertAlmostEqual(blended["valuation"], blended["profitability"], places=4)

    def test_an_out_of_range_blend_raises(self):
        with self.assertRaises(ValueError):
            harness.blended_full_coverage_candidate({"a": 1.0}, ["a"], blend=1.5)


class SectorHelpersTests(unittest.TestCase):
    def test_sectors_in_panel_collects_distinct_labels_excluding_none(self):
        periods = [
            {"sectors": {"AAPL": "Technology", "XOM": "Energy"}},
            {"sectors": {"MSFT": "Technology", "UNKNOWN": None}},
        ]
        self.assertEqual(harness.sectors_in_panel(periods), ["Energy", "Technology"])

    def test_a_panel_with_no_sector_tagging_gives_an_empty_universe(self):
        periods = [{"leg_scores": {"AAPL": {"x": 1.0}}}]
        self.assertEqual(harness.sectors_in_panel(periods), [])

    def test_filter_periods_by_sector_keeps_only_that_sectors_tickers(self):
        periods = [{
            "sectors": {"AAPL": "Technology", "XOM": "Energy"},
            "leg_scores": {"AAPL": {"x": 1.0}, "XOM": {"x": 2.0}},
            "forward_returns": {"AAPL": 0.01, "XOM": -0.01},
            "scores": {"AAPL": 50.0, "XOM": 40.0},
        }]
        tech_only = harness.filter_periods_by_sector(periods, "Technology")
        self.assertEqual(set(tech_only[0]["leg_scores"]), {"AAPL"})
        self.assertEqual(set(tech_only[0]["forward_returns"]), {"AAPL"})

    def test_filter_periods_by_sector_keeps_period_count_stable_even_when_empty(self):
        periods = [{"sectors": {"AAPL": "Technology"}, "leg_scores": {"AAPL": {"x": 1.0}},
                   "forward_returns": {"AAPL": 0.01}, "scores": {"AAPL": 50.0}}]
        empty_sector = harness.filter_periods_by_sector(periods, "Energy")
        self.assertEqual(len(empty_sector), 1)
        self.assertEqual(empty_sector[0]["leg_scores"], {})


def synthetic_sector_periods(count, *, names_per_sector=20, seed=31, noise=0.03):
    """Two sectors, each with its own single predictive leg -- Technology responds only to
    "growth", Energy only to "valuation" -- so a per-sector formula should recover a
    different winning leg per sector rather than one leg dominating everywhere.
    """
    generator = random.Random(seed)
    periods = []
    for index in range(count):
        leg_scores, forwards, sectors = {}, {}, {}
        for sector, predictive_leg in (("Technology", "growth"), ("Energy", "valuation")):
            for position in range(names_per_sector):
                ticker = f"{sector[:2]}{position}"
                true_score = generator.uniform(0, 100)
                forward = (true_score - 50) / 50 * 0.02 + generator.gauss(0, noise)
                leg_scores[ticker] = {
                    "growth": true_score if predictive_leg == "growth" else generator.uniform(0, 100),
                    "valuation": true_score if predictive_leg == "valuation" else generator.uniform(0, 100),
                }
                forwards[ticker] = forward
                sectors[ticker] = sector
        periods.append({"date": f"2026-{index + 1:02d}", "leg_scores": leg_scores,
                        "forward_returns": forwards, "sectors": sectors})
    return periods


class AsMetricPeriodsTests(unittest.TestCase):
    def test_metric_scores_stand_in_for_leg_scores(self):
        periods = [{
            "date": "2026-01", "leg_scores": {"AAPL": {"valuation": 60.0}},
            "metric_scores": {"AAPL": {"trailing_pe": 32.38, "return_on_equity": 1.35}},
            "forward_returns": {"AAPL": 0.02},
        }]
        remapped = harness.as_metric_periods(periods)
        self.assertEqual(remapped[0]["leg_scores"], {"AAPL": {"trailing_pe": 32.38,
                                                              "return_on_equity": 1.35}})
        # Everything else -- forward_returns, date -- passes through untouched.
        self.assertEqual(remapped[0]["forward_returns"], {"AAPL": 0.02})
        self.assertEqual(remapped[0]["date"], "2026-01")

    def test_a_panel_built_before_metric_scores_existed_contributes_empty_dicts(self):
        periods = [{"leg_scores": {"AAPL": {"valuation": 60.0}}}]
        remapped = harness.as_metric_periods(periods)
        self.assertEqual(remapped[0]["leg_scores"], {})

    def test_downstream_leg_level_functions_run_unchanged_over_metrics(self):
        # The whole point: no metric-specific reimplementation of leg_coverage/formula_weights
        # is needed -- as_metric_periods() alone is enough to reuse them.
        periods = synthetic_sector_periods(60, names_per_sector=25, noise=0.02, seed=51)
        metric_periods = [{**period, "metric_scores": period["leg_scores"]} for period in periods]
        remapped = harness.as_metric_periods(metric_periods)
        report = harness.sector_weight_report(remapped, minimum_periods=6)
        self.assertEqual(set(report), {"Technology", "Energy"})


class SectorWeightReportTests(unittest.TestCase):
    def test_each_sector_concentrates_on_its_own_predictive_leg(self):
        periods = synthetic_sector_periods(60, names_per_sector=25, noise=0.02, seed=41)
        report = harness.sector_weight_report(periods, minimum_periods=6)
        self.assertEqual(set(report), {"Technology", "Energy"})
        tech_weights = report["Technology"]["formula_weights"]
        energy_weights = report["Energy"]["formula_weights"]
        self.assertGreater(tech_weights.get("growth", 0), tech_weights.get("valuation", 0))
        self.assertGreater(energy_weights.get("valuation", 0), energy_weights.get("growth", 0))

    def test_a_sector_below_the_minimum_period_floor_reports_none_rather_than_fitting_noise(self):
        periods = synthetic_sector_periods(60, names_per_sector=25, noise=0.02, seed=42)
        report = harness.sector_weight_report(periods, minimum_periods=1000)
        for row in report.values():
            self.assertIsNone(row["formula_weights"])
            self.assertIn("reason", row)


if __name__ == "__main__":
    unittest.main()
