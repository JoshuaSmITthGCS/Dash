import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import evaluation as ev
import signal_metrics as sm


def synthetic_panel(periods=60, names=150, seed=7):
    """A panel where one leg predicts, one is noise, and one duplicates the predictor.

    Every group-A metric has a known right answer on this panel, which is the only way to
    tell a working diagnostic from one that returns plausible numbers.
    """
    generator = random.Random(seed)
    weights = {"good": 0.5, "dead": 0.3, "copy": 0.2}
    # Signal-to-noise by horizon: weak intraday, strongest at a month, fading by a quarter.
    # This is the decay shape the curve has to recover, not a rescaling of one series.
    strength = {"1d": 0.25, "5d": 0.6, "21d": 1.0, "63d": 0.8}
    rows = []
    for index in range(periods):
        scores, legs, horizons = {}, {}, {label: {} for label in strength}
        for position in range(names):
            ticker = f"T{position}"
            good = generator.uniform(0, 100)
            legs[ticker] = {
                "good": good,
                "dead": generator.uniform(0, 100),
                # A near-copy of the predictive leg: the redundancy the matrix must catch.
                "copy": max(0.0, min(100.0, good + generator.gauss(0, 4))),
            }
            scores[ticker] = ev.composite_score(legs[ticker], weights)
            for label, factor in strength.items():
                horizons[label][ticker] = ((good - 50) / 50 * 0.03 * factor
                                           + generator.gauss(0, 0.04))
        rows.append({"date": f"2026-{index + 1:02d}-01", "scores": scores, "leg_scores": legs,
                     "forward_returns_by_horizon": horizons, "forward_returns": horizons["21d"]})
    return {"primary_horizon": "21d", "leg_weights": weights, "periods": rows,
            "dollar_volume": {f"T{position}": 5_000_000.0 for position in range(names)}}


def metrics_by_id(rows):
    return {row["id"]: row for row in rows}


class LegDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.panel = synthetic_panel()

    def test_the_predictive_leg_has_ic_and_the_noise_leg_does_not(self):
        legs = ev.per_leg_ic(self.panel["periods"], list(self.panel["leg_weights"]))
        self.assertGreater(legs["good"]["mean_ic"], 0.2)
        self.assertLess(abs(legs["dead"]["mean_ic"]), ev.MEANINGFUL_IC)

    def test_dropping_the_noise_leg_improves_the_composite(self):
        result = ev.drop_one_leg_delta_ic(self.panel["periods"], self.panel["leg_weights"])
        self.assertTrue(result["legs"]["dead"]["hurts_composite"])
        # Dropping the leg that carries the signal must cost the composite, not help it.
        self.assertFalse(result["legs"]["good"]["hurts_composite"])
        self.assertGreater(result["legs"]["good"]["delta_ic"], 0)

    def test_a_duplicated_leg_is_flagged_as_redundant(self):
        result = ev.leg_correlation_matrix(self.panel["periods"])
        pairs = [set(pair["legs"]) for pair in result["redundant_pairs"]]
        self.assertIn({"good", "copy"}, pairs)
        self.assertNotIn({"good", "dead"}, pairs)

    def test_composite_renormalizes_over_present_legs(self):
        # A missing leg must reweight the survivors rather than drag the score toward zero.
        self.assertEqual(ev.composite_score({"a": 80, "b": None}, {"a": 0.5, "b": 0.5}), 80)
        self.assertIsNone(ev.composite_score({"a": None}, {"a": 1.0}))


class HorizonAndCostTests(unittest.TestCase):
    def test_ic_decay_finds_the_horizon_the_edge_lives_at(self):
        panel = synthetic_panel()
        decay = ev.ic_decay_curve(panel["periods"], ["1d", "5d", "21d", "63d"])
        self.assertEqual(decay["peak_horizon"], "21d")
        horizons = decay["horizons"]
        self.assertTrue(all(summary["mean_ic"] is not None for summary in horizons.values()))
        # The point of the curve is the ordering: an edge that is noise intraday and real at
        # a month cannot be traded daily, and only the curve shows that.
        self.assertLess(horizons["1d"]["mean_ic"], horizons["21d"]["mean_ic"])

    def test_short_horizons_pay_their_cost_far_more_often(self):
        crossover = ev.alpha_cost_crossover(
            {"1d": 0.001, "21d": 0.01}, round_trip_cost_bps=20,
            trading_days_by_horizon={"1d": 1, "21d": 21})
        rows = {row["horizon"]: row for row in crossover["rows"]}
        # A daily spread of 10bps is wiped out by paying 20bps to capture it; the same
        # signal held a month clears its cost comfortably.
        self.assertLess(rows["1d"]["net_annualized_spread"], 0)
        self.assertGreater(rows["21d"]["net_annualized_spread"], 0)
        self.assertEqual(crossover["crossover_horizon"], "21d")

    def test_no_horizon_clears_cost_when_the_spread_is_thin(self):
        crossover = ev.alpha_cost_crossover(
            {"5d": 0.0001}, round_trip_cost_bps=50, trading_days_by_horizon={"5d": 5})
        self.assertIsNone(crossover["crossover_horizon"])

    def test_breakeven_alpha_scales_with_turnover(self):
        self.assertEqual(ev.breakeven_gross_alpha(4.0, 20.0), 0.8)
        self.assertIsNone(ev.breakeven_gross_alpha(None, 20.0))

    def test_effective_breadth_counts_bets_not_positions(self):
        self.assertEqual(ev.effective_breadth([0.25] * 4), 4.0)
        self.assertLess(ev.effective_breadth([0.7, 0.1, 0.1, 0.1]), 2.5)

    def test_a_stable_ranking_shows_high_autocorrelation(self):
        stable = [{"scores": {"A": 3, "B": 2, "C": 1, "D": 0, "E": 5}} for _ in range(4)]
        self.assertEqual(ev.rank_autocorrelation(stable)["mean_autocorrelation"], 1.0)
        flipped = [{"scores": {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}},
                   {"scores": {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}}]
        self.assertEqual(ev.rank_autocorrelation(flipped)["mean_autocorrelation"], -1.0)


class SharpeHonestyTests(unittest.TestCase):
    def test_probabilistic_sharpe_rises_with_sample_length(self):
        short = ev.probabilistic_sharpe_ratio(0.05, observations=30)
        long = ev.probabilistic_sharpe_ratio(0.05, observations=1000)
        self.assertLess(short, long)
        self.assertGreater(long, 0.9)

    def test_negative_skew_and_fat_tails_lengthen_the_required_record(self):
        normal = ev.minimum_track_record_length(0.05)
        skewed = ev.minimum_track_record_length(0.05, skew=-1.5, kurtosis=8.0)
        self.assertGreater(skewed, normal)

    def test_no_track_record_length_is_defined_without_an_edge(self):
        self.assertIsNone(ev.minimum_track_record_length(-0.01))
        self.assertIsNone(ev.probabilistic_sharpe_ratio(None, observations=100))


class PopulationStabilityTests(unittest.TestCase):
    def test_an_unmoved_distribution_scores_near_zero(self):
        generator = random.Random(3)
        baseline = [generator.gauss(0, 1) for _ in range(500)]
        current = [generator.gauss(0, 1) for _ in range(500)]
        self.assertLess(sm.population_stability_index(baseline, current), 0.1)

    def test_a_shifted_distribution_breaches_the_alarm(self):
        generator = random.Random(3)
        baseline = [generator.gauss(0, 1) for _ in range(500)]
        current = [generator.gauss(2.5, 1) for _ in range(500)]
        self.assertGreater(sm.population_stability_index(baseline, current), 0.25)

    def test_too_small_a_sample_returns_nothing_rather_than_a_number(self):
        self.assertIsNone(sm.population_stability_index([1, 2, 3], [1, 2, 3]))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.panel = synthetic_panel()
        self.report = sm.build_report(
            backtest=None, optimizer=None, panel=self.panel, factors=None,
            ic_validation=None, live={"days": 18, "refreshes": 18,
                                      "first_date": "2026-07-20", "last_date": "2026-08-13"})

    def test_every_metric_declares_whether_it_needs_a_live_sample(self):
        for row in self.report["metrics"]:
            self.assertIsInstance(row["requires_live_sample"], bool, row["id"])
            self.assertIn(row["group"], {group["id"] for group in self.report["groups"]})
            self.assertIsNotNone(row["status"], row["id"])

    def test_signal_metrics_compute_without_any_live_data(self):
        rows = metrics_by_id(self.report["metrics"])
        self.assertEqual(rows["rank_ic_21d"]["status"], "ready")
        self.assertGreater(rows["rank_ic_21d"]["value"], ev.MEANINGFUL_IC)
        self.assertFalse(rows["rank_ic_21d"]["requires_live_sample"])
        self.assertTrue(rows["per_leg_ic"]["breached"], "one leg is pure noise")
        self.assertTrue(rows["leg_correlation"]["breached"], "two legs are near-duplicates")

    def test_distribution_metrics_stay_unread_until_the_sample_exists(self):
        rows = metrics_by_id(self.report["metrics"])
        for identifier in ("omega", "ulcer_index", "cvar_95", "gain_to_pain"):
            self.assertTrue(rows[identifier]["requires_live_sample"])
            self.assertEqual(rows[identifier]["status"], "accumulating")
            self.assertIsNone(rows[identifier]["value"])
            self.assertEqual(rows[identifier]["observations"], 18)

    def test_a_missing_backtest_is_reported_rather_than_guessed(self):
        rows = metrics_by_id(self.report["metrics"])
        self.assertIsNone(rows["deflated_sharpe"]["value"])
        self.assertIsNone(rows["factor_betas"]["value"])
        self.assertNotEqual(rows["factor_betas"]["status"], "ready")

    def test_summary_counts_split_by_sample_requirement(self):
        summary = self.report["summary"]
        self.assertEqual(summary["total"], len(self.report["metrics"]))
        self.assertEqual(summary["sample_free_total"] + summary["needs_sample_total"],
                         summary["total"])
        self.assertGreaterEqual(summary["sample_free_ready"], 8)


class PendingInputTests(unittest.TestCase):
    def test_without_a_panel_the_signal_group_says_what_to_run(self):
        report = sm.build_report(backtest=None, optimizer=None, panel=None, factors=None,
                                 ic_validation=None,
                                 live={"days": 0, "refreshes": 0, "first_date": None,
                                       "last_date": None})
        rows = metrics_by_id(report["metrics"])
        self.assertEqual(rows["rank_ic_21d"]["status"], "awaiting_input")
        self.assertIn("--panel-out", rows["rank_ic_21d"]["status_message"])
        self.assertFalse(rows["rank_ic_21d"]["requires_live_sample"],
                         "the panel is backtest data, not live data")


if __name__ == "__main__":
    unittest.main()
