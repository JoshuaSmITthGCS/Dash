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


class PanelFromSlicesTests(unittest.TestCase):
    def test_slices_are_preserved_exactly_rather_than_re_split(self):
        panel = harness.Panel.from_slices([{"a": 1}], [{"b": 2}], [{"c": 3}])
        self.assertEqual(panel.train, ({"a": 1},))
        self.assertEqual(panel.validation, ({"b": 2},))
        self.assertEqual(panel.holdout, ({"c": 3},))

    def test_an_empty_slice_is_rejected(self):
        with self.assertRaises(ValueError):
            harness.Panel.from_slices([], [{"b": 2}], [{"c": 3}])


class GrowthQualityFilterTests(unittest.TestCase):
    def _period(self, names):
        return {
            "leg_scores": {t: legs for t, legs in names.items()},
            "forward_returns": {t: 0.01 for t in names},
            "scores": {t: 50.0 for t in names},
        }

    def test_only_names_clearing_every_gate_survive(self):
        # 10 names, everything ascending together -- the 70th-percentile growth gate admits
        # the top 3, and the quality gate (median) does not cut further here.
        names = {f"T{i}": {"growth": float(i * 10), "profitability": float(i * 10),
                           "financial_health": float(i * 10)} for i in range(10)}
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        kept = set(filtered[0]["leg_scores"])
        self.assertEqual(kept, {"T7", "T8", "T9"})
        # forward_returns is filtered in lockstep -- a kept name must stay gradeable.
        self.assertEqual(set(filtered[0]["forward_returns"]), kept)

    def test_a_high_growth_name_that_fails_quality_is_excluded(self):
        names = {f"T{i}": {"growth": float(i), "profitability": float(10 - i),
                           "financial_health": float(10 - i)} for i in range(10)}
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        # Growth and quality are perfectly anticorrelated here, so nothing clears both.
        self.assertEqual(filtered[0]["leg_scores"], {})

    def test_the_quality_gate_averages_its_legs_rather_than_gating_on_each(self):
        # Strong profitability, weak financial_health: the AVERAGE clears the median floor,
        # so this name survives -- where two independent floors would have dropped it.
        names = {f"T{i}": {"growth": float(i * 10), "profitability": float(i * 10),
                           "financial_health": float((9 - i) * 10)} for i in range(10)}
        # T9: growth 90th pct (top), profitability top, financial_health bottom -> avg 0.5.
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        self.assertIn("T9", filtered[0]["leg_scores"])

    def test_a_name_missing_every_leg_in_a_gate_fails_it_rather_than_passing_by_default(self):
        names = {f"T{i}": {"growth": float(i * 10), "profitability": float(i * 10),
                           "financial_health": float(i * 10)} for i in range(10)}
        names["T9"].pop("profitability")
        names["T9"].pop("financial_health")
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        self.assertNotIn("T9", filtered[0]["leg_scores"])

    def test_a_partially_present_gate_scores_on_the_legs_that_do_resolve(self):
        names = {f"T{i}": {"growth": float(i * 10), "profitability": float(i * 10),
                           "financial_health": float(i * 10)} for i in range(10)}
        names["T9"].pop("financial_health")  # profitability alone still tops the quality gate
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        self.assertIn("T9", filtered[0]["leg_scores"])

    def test_ranking_is_per_period_so_a_later_periods_levels_never_leak_backward(self):
        early = self._period({f"T{i}": {"growth": float(i), "profitability": float(i),
                                        "financial_health": float(i)} for i in range(10)})
        # Same relative ordering, wildly different absolute levels.
        late = self._period({f"T{i}": {"growth": float(i * 1000), "profitability": float(i * 1000),
                                       "financial_health": float(i * 1000)} for i in range(10)})
        filtered = harness.filter_periods_by_quality_gates([early, late])
        self.assertEqual(set(filtered[0]["leg_scores"]), set(filtered[1]["leg_scores"]))

    def test_retention_is_roughly_the_product_of_the_two_gates_not_three(self):
        # The reason this is two gates and not three: with ~independent legs, three floats at
        # 0.70/0.50/0.50 keep ~7.5%, too thin per sector to measure. Two keep ~15%.
        generator = random.Random(3)
        names = {f"T{i}": {"growth": generator.uniform(0, 100),
                           "profitability": generator.uniform(0, 100),
                           "financial_health": generator.uniform(0, 100)} for i in range(400)}
        filtered = harness.filter_periods_by_quality_gates([self._period(names)])
        retention = len(filtered[0]["leg_scores"]) / len(names)
        self.assertGreater(retention, 0.10)
        self.assertLess(retention, 0.22)


class SectorSignificanceThresholdTests(unittest.TestCase):
    def test_the_bar_rises_with_the_number_of_sectors_searched(self):
        self.assertGreater(harness.sector_significance_threshold(200),
                           harness.sector_significance_threshold(50))

    def test_it_never_drops_below_the_repos_own_multiple_testing_floor(self):
        # Bonferroni at 11 sectors is ~2.84, looser than the repo's standing |t| >= 3 bar --
        # the floor must win, not the adjustment.
        self.assertEqual(harness.sector_significance_threshold(11), 3.0)
        self.assertEqual(harness.sector_significance_threshold(1), 3.0)


class SectorVerdictTests(unittest.TestCase):
    def _candidates(self, *, formula_ic, champion_ic, equal_ic, efficiency, t_stat):
        return [
            {"name": "sector_formula", "validation_mean_ic": formula_ic,
             "walk_forward_efficiency": efficiency, "validation_ic": {"t_stat": t_stat}},
            {"name": "champion", "validation_mean_ic": champion_ic},
            {"name": "equal_weight", "validation_mean_ic": equal_ic},
        ]

    def test_all_gates_passing_reads_real(self):
        verdict = harness.sector_verdict(
            self._candidates(formula_ic=0.05, champion_ic=0.01, equal_ic=0.02,
                             efficiency=0.9, t_stat=3.5),
            significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "REAL")
        self.assertEqual(verdict["failed_gates"], [])

    def test_beating_champion_but_not_equal_weight_is_not_established(self):
        # The case this gate exists for: champion is simply miscalibrated in this sector,
        # which is not the same finding as the sector wanting these particular weights.
        verdict = harness.sector_verdict(
            self._candidates(formula_ic=0.03, champion_ic=0.01, equal_ic=0.05,
                             efficiency=0.9, t_stat=3.5),
            significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "NOT_ESTABLISHED")
        self.assertIn("beats_equal_weight", verdict["failed_gates"])

    def test_a_collapsing_walk_forward_efficiency_is_not_established(self):
        verdict = harness.sector_verdict(
            self._candidates(formula_ic=0.05, champion_ic=0.01, equal_ic=0.02,
                             efficiency=0.05, t_stat=3.5),
            significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "NOT_ESTABLISHED")
        self.assertIn("efficiency_holds", verdict["failed_gates"])

    def test_a_t_stat_below_the_adjusted_bar_is_not_established(self):
        verdict = harness.sector_verdict(
            self._candidates(formula_ic=0.05, champion_ic=0.01, equal_ic=0.02,
                             efficiency=0.9, t_stat=2.1),
            significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "NOT_ESTABLISHED")
        self.assertIn("clears_sector_adjusted_significance", verdict["failed_gates"])

    def test_a_significantly_NEGATIVE_t_stat_does_not_count_as_significance(self):
        # Regression: the gate originally used abs(t_stat), so a candidate that ranked
        # backwards strongly enough passed the "significance" gate. The real Consumer
        # Defensive slice did exactly this (IC -0.2627 at t = -3.457). Here champion and
        # equal_weight are even worse, so the two comparison gates pass -- meaning abs()
        # would have produced a REAL verdict for an actively anti-predictive formula.
        verdict = harness.sector_verdict(
            self._candidates(formula_ic=-0.26, champion_ic=-0.40, equal_ic=-0.38,
                             efficiency=0.9, t_stat=-3.5),
            significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "NOT_ESTABLISHED")
        self.assertIn("clears_sector_adjusted_significance", verdict["failed_gates"])

    def test_no_formula_reports_its_own_verdict_rather_than_raising(self):
        verdict = harness.sector_verdict(
            [{"name": "champion", "validation_mean_ic": 0.01}], significance_threshold=3.0)
        self.assertEqual(verdict["verdict"], "NO_FORMULA")


class SectorCandidateReportTests(unittest.TestCase):
    """The validation-side follow-up to sector_weight_report -- does a sector-fitted formula
    generalize to data it was never fit on, or was the train-slice pattern noise.
    """

    def test_never_touches_the_holdout_slice(self):
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=61)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        original_holdout = panel.holdout
        harness.sector_candidate_report(
            panel, champion_weights={"growth": 0.5, "valuation": 0.5}, trial_count=10)
        self.assertEqual(panel.holdout, original_holdout)

    def test_a_genuinely_stable_sector_pattern_beats_a_mismatched_champion_on_validation(self):
        # synthetic_sector_periods' relationship is the SAME in every period (Technology
        # always driven by "growth"), so it holds in both train and validation -- a real,
        # generalizing pattern, not train-sample luck. champion is deliberately mismatched
        # (all weight on the leg that does NOT predict Technology) so sector_formula, which
        # learns "growth" matters from Technology's own train slice, should win on validation.
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=62)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        report = harness.sector_candidate_report(
            panel, champion_weights={"growth": 0.0, "valuation": 1.0}, trial_count=10)
        tech = {c["name"]: c for c in report["Technology"]["candidates"]}
        self.assertGreater(tech["sector_formula"]["validation_mean_ic"],
                           tech["champion"]["validation_mean_ic"])

    def test_a_sector_below_the_minimum_period_floor_reports_no_candidates(self):
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=63)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        report = harness.sector_candidate_report(
            panel, champion_weights={"growth": 0.5, "valuation": 0.5}, trial_count=10,
            minimum_periods=1000)
        for row in report.values():
            self.assertIsNone(row["candidates"])
            self.assertIn("reason", row)

    def test_candidates_within_a_sector_are_sorted_by_validation_ic_descending(self):
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=64)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        report = harness.sector_candidate_report(
            panel, champion_weights={"growth": 0.5, "valuation": 0.5}, trial_count=10)
        for row in report.values():
            ics = [c["validation_mean_ic"] or float("-inf") for c in row["candidates"]]
            self.assertEqual(ics, sorted(ics, reverse=True))

    def test_extra_candidates_are_evaluated_alongside_champion_and_the_sector_formula(self):
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=65)
        panel = harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)
        report = harness.sector_candidate_report(
            panel, champion_weights={"growth": 0.5, "valuation": 0.5}, trial_count=10,
            extra_candidates=[("reweighted_composite_a", {"growth": 1.0})])
        for sector, row in report.items():
            names = {c["name"] for c in row["candidates"]}
            self.assertIn("reweighted_composite_a", names, sector)


class SectorWeightSearchTests(unittest.TestCase):
    """The actual per-sector search: many candidates per sector, selection inside train,
    only the winner graded on validation, deflation charged for the whole pool.
    """

    def _panel(self, seed=71):
        periods = synthetic_sector_periods(90, names_per_sector=25, noise=0.02, seed=seed)
        return harness.Panel(periods, train_fraction=0.4, validation_fraction=0.4)

    CHAMPION = {"growth": 0.5, "valuation": 0.5}

    def test_recovers_a_different_dominant_leg_per_sector(self):
        # The user's core claim, planted as ground truth: Technology is driven by growth,
        # Energy by valuation. A real search must find DIFFERENT weights per sector.
        report = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=40, seed=1, trial_count=10)
        tech = {c["name"]: c for c in report["Technology"]["candidates"]}["search_winner"]
        energy = {c["name"]: c for c in report["Energy"]["candidates"]}["search_winner"]
        self.assertEqual(max(tech["weights"], key=tech["weights"].get), "growth")
        self.assertEqual(max(energy["weights"], key=energy["weights"].get), "valuation")

    def test_a_genuinely_planted_pattern_reads_real_under_all_four_gates(self):
        report = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=40, seed=1, trial_count=10)
        for sector in ("Technology", "Energy"):
            self.assertEqual(report[sector]["verdict"]["verdict"], "REAL", sector)

    def test_never_touches_the_holdout_slice(self):
        panel = self._panel()
        original_holdout = panel.holdout
        harness.sector_weight_search(panel, champion_weights=self.CHAMPION, count=10,
                                     seed=0, trial_count=10)
        self.assertEqual(panel.holdout, original_holdout)

    def test_the_same_seed_reproduces_the_same_winner(self):
        first = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=15, seed=9, trial_count=10)
        second = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=15, seed=9, trial_count=10)
        for sector in first:
            self.assertEqual(
                {c["name"]: c["weights"] for c in first[sector]["candidates"]},
                {c["name"]: c["weights"] for c in second[sector]["candidates"]}, sector)

    def test_deflation_is_charged_for_the_whole_pool_not_one_trial(self):
        report = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=25, seed=2, trial_count=10)
        row = report["Technology"]
        winner = {c["name"]: c for c in row["candidates"]}["search_winner"]
        self.assertGreaterEqual(row["pool_size"], 26)  # 25 random + at least equal_weight
        self.assertEqual(winner["trials_considered"], 10 + row["pool_size"])

    def test_a_thin_sector_reports_a_reason_rather_than_searching_noise(self):
        report = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=10, seed=0,
            trial_count=10, minimum_periods=1000)
        for sector, row in report.items():
            self.assertIsNone(row["candidates"], sector)
            self.assertIn("reason", row)

    def test_search_pbo_is_reported_per_sector(self):
        report = harness.sector_weight_search(
            self._panel(), champion_weights=self.CHAMPION, count=20, seed=3, trial_count=10)
        for sector, row in report.items():
            self.assertIn("search_pbo", row, sector)


if __name__ == "__main__":
    unittest.main()
