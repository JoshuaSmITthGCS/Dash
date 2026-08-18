import json
import os
import random
import sys
import tempfile
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

    def test_negative_ic_breaches_a_positive_predictive_threshold(self):
        panel = synthetic_panel(periods=12, names=30)
        for period in panel["periods"]:
            period["forward_returns_by_horizon"]["1d"] = {
                ticker: -score for ticker, score in period["scores"].items()
            }
        row = metrics_by_id(sm.signal_metrics(panel))["rank_ic_1d"]
        self.assertLess(row["value"], 0)
        self.assertTrue(row["breached"])

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


def _price_curve_with_beta_regime_shift():
    """A portfolio that tracks the benchmark at beta ~0.5 for 90 sessions, then ~1.8 for
    90 more -- long enough for two non-overlapping 60-day rolling windows on either side
    of the shift, so the swing between them is real and unambiguous rather than noise."""
    benchmark_returns = [0.01 if index % 2 == 0 else -0.008 for index in range(180)]
    regimes = [0.5] * 90 + [1.8] * 90
    portfolio_returns = [regime * value for regime, value in zip(regimes, benchmark_returns)]

    def curve(returns):
        price, points = 100.0, [{"date": "2026-01-01", "value": 100.0}]
        for index, value in enumerate(returns):
            price *= 1 + value
            points.append({"date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}", "value": price})
        return points

    return curve(portfolio_returns), curve(benchmark_returns)


class RollingBetaSwingTests(unittest.TestCase):
    def test_swing_gets_its_own_metric_matching_the_point_estimate_breach(self):
        # rolling_beta_60d's value (a point beta, ~1) and its own kill_threshold (a swing,
        # ~0.3) are on different scales -- a bullet built from that pair would show the
        # point estimate crossing a line that was never about it. rolling_beta_swing
        # publishes the swing itself against its own real threshold instead.
        portfolio_curve, benchmark_curve = _price_curve_with_beta_regime_shift()
        backtest = {"portfolio": {"history": portfolio_curve, "rebalances": []},
                    "benchmark_spy": {"history": benchmark_curve}}
        rows = metrics_by_id(sm.construction_metrics(backtest, None, []))
        point_estimate, swing = rows["rolling_beta_60d"], rows["rolling_beta_swing"]
        self.assertGreater(swing["value"], sm.MAXIMUM_BETA_SWING)
        self.assertEqual(swing["kill_threshold_value"], sm.MAXIMUM_BETA_SWING)
        self.assertEqual(swing["comparison"], "gt")
        self.assertTrue(swing["breached"])
        self.assertEqual(point_estimate["breached"], swing["breached"])
        self.assertIsNone(point_estimate["kill_threshold_value"])

    def test_factor_betas_publishes_its_threshold_on_the_momentum_loadings_own_scale(self):
        # Unlike rolling_beta_60d/sector_active_weights, factor_betas' value (the momentum
        # loading itself) and its kill_threshold (a loading below -0.1) are already the same
        # quantity -- no second metric needed, just the numeric pair. Fitting a real OLS
        # regression to a specific loading needs 24+ months of matched factor data, so this
        # checks the wiring is unconditional rather than fabricating that fixture.
        row = metrics_by_id(sm.construction_metrics(None, None, []))["factor_betas"]
        self.assertEqual(row["kill_threshold_value"], sm.MOMENTUM_LOADING_KILL_THRESHOLD)
        self.assertEqual(row["comparison"], "lt")


class NumericKillThresholdTests(unittest.TestCase):
    """kill_threshold_value/comparison must be a real, same-scale-as-value pair or absent
    entirely -- never a number derived from the prose kill_threshold string, and never
    populated for a metric where no such pair exists (a bullet chart built from a fabricated
    threshold is worse than no chart)."""

    def test_metric_leaves_the_numeric_pair_unset_unless_the_caller_provides_it(self):
        row = sm.metric("example", "signal", "Example", value=1.0)
        self.assertIsNone(row["kill_threshold_value"])
        self.assertIsNone(row["comparison"])

    def test_metric_carries_the_numeric_pair_through_when_provided(self):
        row = sm.metric("example", "signal", "Example", value=1.0,
                        kill_threshold_value=0.5, comparison="lt")
        self.assertEqual(row["kill_threshold_value"], 0.5)
        self.assertEqual(row["comparison"], "lt")

    def test_rank_ic_publishes_its_threshold_on_the_same_scale_as_its_value(self):
        panel = synthetic_panel()
        row = metrics_by_id(sm.signal_metrics(panel))["rank_ic_1d"]
        self.assertEqual(row["kill_threshold_value"], sm.MINIMUM_MEAN_IC)
        self.assertEqual(row["comparison"], "lt")
        # The pair has to actually agree with `breached`, or a bullet chart drawn from it
        # would show a bar crossing the threshold line while the badge says "not breached".
        self.assertEqual(row["value"] < row["kill_threshold_value"], row["breached"])

    def test_ic_ir_publishes_its_threshold_on_the_same_scale_as_its_value(self):
        panel = synthetic_panel()
        row = metrics_by_id(sm.signal_metrics(panel))["ic_ir"]
        self.assertEqual(row["kill_threshold_value"], sm.MINIMUM_IC_IR)
        self.assertEqual(row["comparison"], "lt")

    def test_metrics_with_no_numeric_form_stay_unset(self):
        # quantile_spread's threshold is a shape condition (monotonic or not), not a
        # magnitude -- there is no number to compare `value` against.
        panel = synthetic_panel()
        row = metrics_by_id(sm.signal_metrics(panel))["quantile_spread"]
        self.assertIsNone(row["kill_threshold_value"])
        self.assertIsNone(row["comparison"])

    def test_leg_count_metrics_publish_zero_as_their_real_threshold(self):
        # per_leg_ic, drop_one_leg and leg_correlation each publish a *count* (of dead
        # legs, harmful legs, redundant pairs) as `value`, and each already treats any
        # nonzero count as breach -- so although the prose kill_threshold names a
        # different per-leg quantity, zero is a real, same-scale threshold for the count.
        panel = synthetic_panel()
        rows = metrics_by_id(sm.signal_metrics(panel))
        for identifier in ("per_leg_ic", "drop_one_leg", "leg_correlation"):
            row = rows[identifier]
            self.assertEqual(row["kill_threshold_value"], 0, identifier)
            self.assertEqual(row["comparison"], "gt", identifier)
            self.assertEqual(row["value"] > 0, row["breached"], identifier)


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

    def test_feature_psi_uses_separated_point_in_time_windows(self):
        with tempfile.TemporaryDirectory() as root:
            for day in range(1, 61):
                month = 1 + (day - 1) // 28
                date = f"2026-{month:02d}-{((day - 1) % 28) + 1:02d}"
                value = float(day % 10) if day <= 20 else (100.0 + day % 10 if day > 40 else 50.0)
                row = {"ticker": "TEST", "refresh_id": f"r{day}",
                       "recorded_at": f"{date}T20:00:00+00:00",
                       "normalized_metric_scores": {"champion": {"valuation": value}}}
                with open(os.path.join(root, f"{date}.jsonl"), "w") as handle:
                    handle.write(json.dumps(row) + "\n")
            result = sm.feature_psi_from_pit(root)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["worst_feature"], "valuation")
        self.assertTrue(result["breached"])


class LiveMonitoringTests(unittest.TestCase):
    def test_divergence_is_computed_from_shadow_and_backtest_returns(self):
        history = [{"date": f"2026-01-{index + 1:02d}", "value": value}
                   for index, value in enumerate([100, 101, 100.5, 102, 101.5, 103, 102.5,
                                                  104, 103.5, 105, 104.5, 106, 105.5, 107,
                                                  106.5, 108, 107.5, 109, 108.5, 110, 109.5])]
        result = sm.live_backtest_divergence(
            {"portfolio": {"history": history}}, {"returns": [0.02] * 20, "periods": []})
        self.assertEqual(result["status"], "ready")
        self.assertGreater(result["value"], 0)
        self.assertTrue(result["breached"])
        # threshold_bps is the same-scale (bps/day) form of the z-test bound above --
        # a breached divergence's magnitude must actually clear it.
        self.assertIsNotNone(result["threshold_bps"])
        self.assertGreater(abs(result["value"]), result["threshold_bps"])

    def test_signed_bound_reproduces_the_absolute_value_test_from_either_side(self):
        # Same underlying |value| > bound test either direction, expressed as the
        # one-sided lt/gt pair the metric contract supports -- never a fabricated number,
        # only a choice of which side of zero the already-real bound applies to.
        self.assertEqual(sm._signed_bound(12.9, 5.0), (5.0, "gt"))
        self.assertEqual(sm._signed_bound(-12.9, 5.0), (-5.0, "lt"))
        self.assertEqual(sm._signed_bound(None, 5.0), (None, None))
        self.assertEqual(sm._signed_bound(1.0, None), (None, None))

    def test_divergence_bullet_threshold_agrees_with_the_real_breach_flag(self):
        for live_returns in ([0.02] * 20, [-0.02] * 20, [0.0007] * 20):
            history = [{"date": f"2026-01-{index + 1:02d}", "value": 100 * (1.001 ** index)}
                       for index in range(40)]
            result = sm.live_backtest_divergence(
                {"portfolio": {"history": history}}, {"returns": live_returns, "periods": []})
            threshold_value, comparison = sm._signed_bound(result["value"], result["threshold_bps"])
            if comparison == "gt":
                bullet_breach = result["value"] > threshold_value
            else:
                bullet_breach = result["value"] < threshold_value
            self.assertEqual(bullet_breach, result["breached"], live_returns)

    def test_live_ic_compares_against_a_real_backtest_confidence_interval(self):
        # The backtest reference has to come from the panel's own IC series (mean +/-
        # z * standard error), not the live estimate's self-referential interval --
        # comparing a value against its own CI would (near-)never breach.
        panel = synthetic_panel()
        low_ic_validation = {"variants": {"champion": {"1M": {
            "mean_rank_ic": -0.5, "periods_accumulated": 6, "minimum_periods": 24,
            "status_message": "accumulating",
        }}}}
        rows = metrics_by_id(sm.monitoring_metrics(
            {"days": 30, "refreshes": 30}, low_ic_validation, panel=panel,
            pit_root="/definitely/missing/pit", universe_path="/definitely/missing/universe.jsonl"))
        row = rows["live_vs_backtest_ic"]
        self.assertIsNotNone(row["kill_threshold_value"])
        self.assertEqual(row["comparison"], "lt")
        self.assertLess(row["value"], row["kill_threshold_value"])
        self.assertTrue(row["breached"])
        self.assertIsNotNone(row["backtest_reference"])
        # A live IC comfortably inside the backtest's own range must not breach.
        healthy_ic_validation = {"variants": {"champion": {"1M": {
            "mean_rank_ic": row["backtest_reference"], "periods_accumulated": 6,
            "minimum_periods": 24, "status_message": "accumulating",
        }}}}
        healthy = metrics_by_id(sm.monitoring_metrics(
            {"days": 30, "refreshes": 30}, healthy_ic_validation, panel=panel,
            pit_root="/definitely/missing/pit",
            universe_path="/definitely/missing/universe.jsonl"))["live_vs_backtest_ic"]
        self.assertFalse(healthy["breached"])

    def test_live_ic_stays_unset_without_a_panel(self):
        # No backtest panel means no backtest-side confidence interval to compare against
        # -- kill_threshold_value must stay unset rather than compare against nothing.
        ic_validation = {"variants": {"champion": {"1M": {
            "mean_rank_ic": 0.01, "periods_accumulated": 6, "minimum_periods": 24,
        }}}}
        row = metrics_by_id(sm.monitoring_metrics(
            {"days": 30, "refreshes": 30}, ic_validation, panel=None,
            pit_root="/definitely/missing/pit",
            universe_path="/definitely/missing/universe.jsonl"))["live_vs_backtest_ic"]
        self.assertIsNone(row["kill_threshold_value"])
        self.assertIsNone(row["comparison"])
        self.assertFalse(row["breached"])

    def test_execution_export_populates_cost_and_reconciliation_metrics(self):
        execution = {
            "orders": [{"ticker": "A", "side": "buy", "decision_price": 100,
                        "fill_price": 100.1, "intended_quantity": 10,
                        "filled_quantity": 8}],
            "intended_positions": {"A": 0.6, "B": 0.4},
            "actual_positions": {"A": 0.59, "B": 0.0},
        }
        rows = metrics_by_id(sm._execution_cost_metrics(execution))
        self.assertAlmostEqual(rows["implementation_shortfall"]["value"], 10.0)
        self.assertAlmostEqual(rows["fill_rate"]["value"], 0.8)
        self.assertEqual(rows["unpositioned_signals"]["detail"]["tickers"], ["B"])
        reconciliation = sm.position_reconciliation(execution)
        self.assertEqual(reconciliation["worst_ticker"], "B")
        self.assertTrue(reconciliation["breached"])

    def test_current_refresh_quality_counters_are_measured(self):
        with tempfile.TemporaryDirectory() as root:
            row = {"ticker": "A", "refresh_id": "r1",
                   "recorded_at": "2026-01-02T20:00:00+00:00",
                   "data_as_of": "2026-01-02T19:00:00+00:00", "price": 10,
                   "quality_flags": []}
            with open(os.path.join(root, "2026-01-02.jsonl"), "w") as handle:
                handle.write(json.dumps(row) + "\n")
            universe = os.path.join(root, "universe.jsonl")
            with open(universe, "w") as handle:
                handle.write(json.dumps({"added": ["A"], "removed": []}) + "\n")
            result = sm.data_quality_from_pit(root, universe)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["universe_churn"]["added"], ["A"])

    def test_position_reconciliation_publishes_its_threshold_in_bps(self):
        # value and kill_threshold are already both "worst unexplained difference, in bps"
        # -- the same quantity, just extracted rather than derived from the prose string.
        execution = {
            "intended_positions": {"A": 0.6, "B": 0.4},
            "actual_positions": {"A": 0.59, "B": 0.0},
        }
        row = metrics_by_id(sm.monitoring_metrics(
            {"days": 30, "refreshes": 30}, None, execution=execution,
            pit_root="/definitely/missing/pit",
            universe_path="/definitely/missing/universe.jsonl"))["position_reconciliation"]
        self.assertEqual(row["kill_threshold_value"], sm.UNEXPLAINED_POSITION_DIFFERENCE_BPS)
        self.assertEqual(row["comparison"], "gt")
        self.assertEqual(row["value"] > row["kill_threshold_value"], row["breached"])

    def test_data_quality_counters_publishes_zero_as_its_real_threshold(self):
        # value is a count of critical issues (missing/stale/duplicate rows) and breach is
        # already "any issue at all" -- same count-vs-zero pattern as per_leg_ic etc.
        with tempfile.TemporaryDirectory() as root:
            rows = [{"ticker": "A", "refresh_id": "r1", "recorded_at": "2026-01-02T20:00:00+00:00",
                     "data_as_of": "2026-01-02T19:00:00+00:00", "price": 10, "quality_flags": []},
                    {"ticker": "B", "refresh_id": "r1", "recorded_at": "2026-01-02T20:00:00+00:00",
                     "price": None, "quality_flags": []}]
            with open(os.path.join(root, "2026-01-02.jsonl"), "w") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            row = metrics_by_id(sm.monitoring_metrics(
                {"days": 30, "refreshes": 30}, None, pit_root=root,
                universe_path="/definitely/missing/universe.jsonl"))["data_quality_counters"]
        self.assertEqual(row["kill_threshold_value"], 0)
        self.assertEqual(row["comparison"], "gt")
        self.assertEqual(row["value"] > 0, row["breached"])


class SectorWeightMetricTests(unittest.TestCase):
    def test_coverage_gets_its_own_metric_on_its_own_scale(self):
        # sector_active_weights' value (largest active bet, in pp) and its kill_threshold
        # (classification coverage, a fraction) are different quantities -- coverage needs
        # its own metric to carry a real same-scale threshold rather than being paired
        # against a value that means something else.
        rows = metrics_by_id(sm.construction_metrics(None, None, [{
            "as_of": "2026-08-14T12:00:00+00:00", "strategy": "production",
            "benchmark": "SPY", "strategy_classified_weight": 0.6,
            "benchmark_classified_weight": 1.0,
            "strategy_sector_weights": {"technology": 0.6, "energy": 0.4},
            "benchmark_sector_weights": {"technology": 0.4, "energy": 0.6},
            "active_sector_weights": {"technology": 0.2, "energy": -0.2},
        }]))
        coverage = rows["sector_classification_coverage"]
        self.assertEqual(coverage["value"], 60.0)
        self.assertEqual(coverage["kill_threshold_value"], 80.0)
        self.assertEqual(coverage["comparison"], "lt")
        self.assertTrue(coverage["breached"])
        # Both metrics describe the same underlying coverage shortfall, so their breach
        # flags must agree even though only one of them now has a numeric bullet pair.
        self.assertEqual(rows["sector_active_weights"]["breached"], coverage["breached"])

    def test_latest_prospective_snapshot_publishes_active_weights(self):
        rows = sm.construction_metrics(None, None, [{
            "as_of": "2026-08-14T12:00:00+00:00", "strategy": "production",
            "benchmark": "SPY", "strategy_classified_weight": 1.0,
            "benchmark_classified_weight": 1.0,
            "strategy_sector_weights": {"technology": 0.6, "energy": 0.4},
            "benchmark_sector_weights": {"technology": 0.4, "energy": 0.6},
            "active_sector_weights": {"technology": 0.2, "energy": -0.2},
        }])
        row = metrics_by_id(rows)["sector_active_weights"]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["value"], 20.0)
        self.assertEqual(row["observations"], 1)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.panel = synthetic_panel()
        self.report = sm.build_report(
            backtest=None, optimizer=None, panel=self.panel, factors=None,
            ic_validation=None, live={"days": 18, "refreshes": 18,
                                      "first_date": "2026-07-20", "last_date": "2026-08-13"},
            pit_root="/definitely/missing/pit", shadow_root="/definitely/missing/shadow",
            universe_path="/definitely/missing/universe.jsonl")

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
            self.assertEqual(rows[identifier]["observations"], 0)

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

    def test_new_groups_and_metrics_stay_honest_without_a_backtest_or_optimizer(self):
        report = sm.build_report(backtest=None, optimizer=None, panel=None, factors=None,
                                 ic_validation=None,
                                 live={"days": 0, "refreshes": 0, "first_date": None,
                                       "last_date": None})
        rows = metrics_by_id(report["metrics"])
        self.assertIn("risk_adjusted", {group["id"] for group in report["groups"]})
        self.assertIn("tax_stress", {group["id"] for group in report["groups"]})
        for identifier in ("bootstrap_ci", "reality_check_spa", "var_backtest_95",
                          "var_backtest_99", "treynor_ratio", "jensens_alpha",
                          "after_tax_return", "stress_test_2022", "stress_test_2020"):
            self.assertIsNone(rows[identifier]["value"], identifier)
            self.assertNotEqual(rows[identifier]["status"], "ready", identifier)
        self.assertFalse(rows["treynor_ratio"]["requires_live_sample"])
        self.assertFalse(rows["stress_test_2022"]["requires_live_sample"])


def _daily_history(days=400, daily_return=0.0006, start="2024-01-01", noise=0.0, seed=1):
    import datetime
    generator = random.Random(seed)
    start_date = datetime.date.fromisoformat(start)
    history, value = [], 100.0
    for index in range(days):
        history.append({"date": (start_date + datetime.timedelta(days=index)).isoformat(),
                        "value": value})
        shock = generator.gauss(0, noise) if noise else 0.0
        value *= 1 + daily_return + shock
    return history


class RiskAdjustedAndTaxStressTests(unittest.TestCase):
    def setUp(self):
        # A shared market shock (via a common seed feeding both series at a fixed ratio) so
        # beta is measurable; the portfolio adds a real excess return on top of it.
        benchmark_history = _daily_history(500, daily_return=0.0003, noise=0.01, seed=21)
        benchmark_returns = [row["value"] for row in benchmark_history]
        portfolio_history, value = [], 100.0
        for index, row in enumerate(benchmark_history):
            market_return = (0 if index == 0 else
                             benchmark_returns[index] / benchmark_returns[index - 1] - 1)
            value *= 1 + 0.0008 + market_return
            portfolio_history.append({"date": row["date"], "value": value})
        self.backtest = {"portfolio": {"history": portfolio_history},
                         "benchmark_spy": {"history": benchmark_history}}

    def test_treynor_and_jensen_read_when_both_histories_exist(self):
        rows = metrics_by_id(sm.risk_adjusted_metrics(self.backtest))
        self.assertEqual(rows["treynor_ratio"]["status"], "ready")
        self.assertEqual(rows["jensens_alpha"]["status"], "ready")
        # The portfolio compounds faster than the benchmark at a comparable beta, so a real
        # single-factor alpha should show up as a positive number, not None.
        self.assertGreater(rows["jensens_alpha"]["value"], 0)

    def test_stress_2022_reads_from_the_backtests_own_history(self):
        history = _daily_history(900, daily_return=-0.0015, start="2021-06-01")
        rows = metrics_by_id(sm.tax_and_stress_metrics({"portfolio": {"history": history}}))
        self.assertEqual(rows["stress_test_2022"]["status"], "ready")
        self.assertLess(rows["stress_test_2022"]["detail"]["return_pct"], 0)
        self.assertEqual(rows["stress_test_2020"]["status"], "awaiting_input")
        self.assertEqual(rows["after_tax_return"]["status"], "awaiting_input")

    def test_stress_2022_is_pending_when_the_backtest_does_not_cover_it(self):
        history = _daily_history(60, daily_return=0.0004, start="2023-01-01")
        rows = metrics_by_id(sm.tax_and_stress_metrics({"portfolio": {"history": history}}))
        self.assertEqual(rows["stress_test_2022"]["status"], "awaiting_input")


class RobustnessBeyondPboTests(unittest.TestCase):
    def test_bootstrap_and_var_backtest_read_on_a_long_backtest(self):
        generator = random.Random(31)
        history, value = [], 100.0
        rows_history = []
        for index in range(600):
            value *= 1 + generator.gauss(0.0005, 0.01)
            rows_history.append({"date": f"2024-{1 + index // 28:02d}-{1 + index % 28:02d}",
                                 "value": value})
        rows = metrics_by_id(sm.honesty_metrics({"portfolio": {"history": rows_history}}, None))
        self.assertEqual(rows["bootstrap_ci"]["status"], "ready")
        self.assertEqual(rows["rolling_sharpe_60d"]["status"], "ready")
        self.assertEqual(rows["var_backtest_95"]["status"], "ready")
        self.assertEqual(rows["var_backtest_99"]["status"], "ready")
        self.assertIn(rows["var_backtest_95"]["value"], (0, 1, 2))

    def test_search_survival_reads_from_the_same_trial_log_as_pbo(self):
        optimizer = {"sweeps": {"categories": [
            {"holdout_folds": [{"score_vs_spy": 5.0}, {"score_vs_spy": 4.0},
                              {"score_vs_spy": 6.0}, {"score_vs_spy": 5.5},
                              {"score_vs_spy": 4.5}, {"score_vs_spy": 5.2},
                              {"score_vs_spy": 4.8}, {"score_vs_spy": 5.1},
                              {"score_vs_spy": 5.3}, {"score_vs_spy": 4.9}]}
            for _ in range(4)
        ]}}
        rows = metrics_by_id(sm.honesty_metrics(None, optimizer))
        # Ten folds, four near-identical configurations: PBO can run (>=2 configs, >=2
        # folds); the SPA bootstrap needs >=10 periods, which this trial log also supplies.
        self.assertIn(rows["pbo"]["status"], ("ready", "provisional"))
        self.assertEqual(rows["reality_check_spa"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
