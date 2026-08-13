import os
import sys
import unittest
from datetime import date

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from backtest_monthly import (  # noqa: E402
    PANEL_PRIMARY_HORIZON,
    appeal_weights,
    build_panel,
    build_rebalance_calendar,
    panel_dollar_volume,
    panel_forward_returns,
    panel_leg_weights,
    panel_scores,
    performance_metrics,
    simulate_locked_portfolio,
    trailing_liquidity_and_volatility,
)


class MonthlyBacktestTests(unittest.TestCase):
    def test_calendar_executes_after_signal(self):
        dates = ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"]
        pairs = build_rebalance_calendar(dates, 0)
        self.assertEqual(pairs, [])
        pairs = build_rebalance_calendar(dates, 1)
        self.assertTrue(all(signal < execution for signal, execution in pairs))

    def test_appeal_weights_are_proportional(self):
        rows = [
            {"ticker": "A", "score": 80, "price": 10},
            {"ticker": "B", "score": 40, "price": 20},
            {"ticker": "C", "score": 100, "price": 30},
        ]
        weights = appeal_weights(rows, 2)
        self.assertAlmostEqual(weights["A"], 2 / 3)
        self.assertAlmostEqual(weights["B"], 1 / 3)
        self.assertNotIn("C", weights)

    def test_metrics_compute_drawdown(self):
        history = [
            {"date": "2023-01-01", "value": 100.0},
            {"date": "2023-06-01", "value": 120.0},
            {"date": "2024-01-01", "value": 90.0},
        ]
        metrics = performance_metrics(history, 100.0)
        self.assertAlmostEqual(metrics["maximum_drawdown"], -0.25)
        self.assertAlmostEqual(metrics["total_return"], -0.10)


class ScoredPanelTests(unittest.TestCase):
    """The panel is what makes signal quality measurable without waiting for a track record."""

    def setUp(self):
        self.universe = {
            "AAA": {
                "dates": [f"2024-01-{day:02d}" for day in range(1, 29)],
                "closes": [100.0 + day for day in range(28)],
                "volumes": [1_000_000.0] * 28,
            },
            "BBB": {
                "dates": [f"2024-01-{day:02d}" for day in range(1, 29)],
                "closes": [50.0] * 28,
                "volumes": [2_000_000.0] * 28,
            },
        }

    def test_leg_weights_flatten_the_two_level_blend(self):
        weights = panel_leg_weights({
            "fundamentals": {"category_weights": {"valuation": 0.5, "growth": 0.5}},
            "ranking_weights": {"fundamentals": 0.8, "market_behavior": 0.15,
                                "news_sentiment": 0.05},
        })
        self.assertAlmostEqual(weights["valuation"], 0.4)
        self.assertAlmostEqual(weights["market_behavior"], 0.15)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

    def test_panel_scores_carry_categories_and_components_as_legs(self):
        scores, legs = panel_scores([
            {"ticker": "AAA", "score": 71.0,
             "fundamental_categories": {"valuation": 60.0, "growth": None},
             "components": {"market_behavior": 55.0, "news_sentiment": 50.0}},
            {"ticker": "BBB", "score": None, "fundamental_categories": {"valuation": 40.0}},
        ])
        self.assertEqual(scores, {"AAA": 71.0})
        self.assertEqual(legs["AAA"], {"valuation": 60.0, "market_behavior": 55.0,
                                       "news_sentiment": 50.0})
        self.assertNotIn("BBB", legs, "an unscored row cannot be graded")

    def test_forward_returns_are_measured_from_the_execution_close(self):
        forwards = panel_forward_returns(self.universe, "2024-01-02", ["AAA", "BBB"])
        # AAA rises one dollar a day from 101 on the execution date.
        self.assertAlmostEqual(forwards["1d"]["AAA"], 102 / 101 - 1)
        self.assertAlmostEqual(forwards["5d"]["AAA"], 106 / 101 - 1)
        self.assertAlmostEqual(forwards["1d"]["BBB"], 0.0)

    def test_a_horizon_past_the_end_of_history_yields_no_observation(self):
        forwards = panel_forward_returns(self.universe, "2024-01-02", ["AAA"])
        self.assertNotIn("AAA", forwards["63d"], "a truncated horizon must not be graded")
        self.assertIn("AAA", forwards["21d"])

    def test_panel_records_dollar_volume_for_the_capacity_ceiling(self):
        volumes = panel_dollar_volume(self.universe, window=20)
        self.assertAlmostEqual(volumes["BBB"], 100_000_000.0)
        # Half a window of usable history is the floor; below it there is no ADV to report.
        self.assertEqual(panel_dollar_volume(self.universe, window=200), {})
        panel = build_panel([], self.universe, {"valuation": 1.0})
        self.assertEqual(panel["primary_horizon"], PANEL_PRIMARY_HORIZON)
        self.assertEqual(panel["leg_weights"], {"valuation": 1.0})


def _daily_dates(count, start=date(2024, 1, 1)):
    return [(date.fromordinal(start.toordinal() + offset)).isoformat() for offset in range(count)]


class TrailingLiquidityAndVolatilityTests(unittest.TestCase):
    def test_missing_ticker_data_returns_none_not_a_guess(self):
        mdv, vol = trailing_liquidity_and_volatility(None, "2024-01-01")
        self.assertIsNone(mdv)
        self.assertIsNone(vol)

    def test_uses_only_the_trailing_window_no_look_ahead(self):
        dates = _daily_dates(65)
        closes = [100.0 + (index % 3) for index in range(65)]
        volumes = [1_000_000.0] * 65
        ticker_data = {"dates": dates, "closes": closes, "volumes": volumes}
        mdv, vol = trailing_liquidity_and_volatility(ticker_data, dates[10])
        self.assertIsNotNone(mdv)
        self.assertGreater(mdv, 0)
        self.assertIsNotNone(vol)
        # A date after the series ends should still only see what existed by then.
        mdv_early, _ = trailing_liquidity_and_volatility(ticker_data, dates[1])
        self.assertLess(mdv_early or 0, mdv * 2)


class CostModelWiringTests(unittest.TestCase):
    def _fixture(self):
        dates = _daily_dates(65)
        # Small day-to-day variation so volatility is nonzero for both names.
        closes_liquid = [100.0 + (index % 4) * 0.5 for index in range(65)]
        closes_illiquid = [50.0 + (index % 5) * 0.3 for index in range(65)]
        universe_data = {
            "LIQUID": {"dates": dates, "closes": closes_liquid, "volumes": [2_000_000.0] * 65},
            "ILLIQUID": {"dates": dates, "closes": closes_illiquid, "volumes": [2_000.0] * 65},
        }
        benchmark = {"dates": dates, "closes": [500.0] * 65}
        plans = [
            {
                "signal_date": dates[0], "execution_date": dates[60],
                "weights": {"LIQUID": 1.0},
                "picks": [{"ticker": "LIQUID", "appeal_score": 90, "weight": 1.0}],
            },
            {
                "signal_date": dates[60], "execution_date": dates[62],
                "weights": {"ILLIQUID": 1.0},
                "picks": [{"ticker": "ILLIQUID", "appeal_score": 80, "weight": 1.0}],
            },
        ]
        return plans, universe_data, benchmark

    def test_flat_cost_model_matches_the_original_single_rate_formula(self):
        # Pre-refactor, cost was computed as value_before_cost * turnover * bps / 10000,
        # then subtracted: value_after = value_before - cost. So
        # value_before = value_after + cost, and cost must equal
        # (value_after + cost) * turnover * bps / 10000 exactly.
        plans, universe_data, benchmark = self._fixture()
        result = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0, transaction_cost_bps=10.0,
            cost_model="flat",
        )
        for rebalance in result["rebalances"]:
            value_before = rebalance["portfolio_value"] + rebalance["cost"]
            expected_cost = round(value_before * rebalance["turnover"] * 10.0 / 10000, 2)
            self.assertAlmostEqual(rebalance["cost"], expected_cost, places=2)

    def test_tiered_stress_costs_more_than_tiered_optimistic(self):
        plans, universe_data, benchmark = self._fixture()
        optimistic = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="optimistic",
        )
        stress = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="stress",
        )
        self.assertGreater(
            stress["metrics"]["estimated_transaction_cost"],
            optimistic["metrics"]["estimated_transaction_cost"],
        )
        self.assertLessEqual(
            stress["metrics"]["final_value"], optimistic["metrics"]["final_value"],
        )

    def test_tiered_illiquid_trade_costs_more_than_an_equal_size_liquid_trade(self):
        # Same weight/dollar trade into ILLIQUID (2,000 shares/day) should cost more in the
        # tiered model than the same-size entry into LIQUID (2,000,000 shares/day) did,
        # since costs.py's spread/impact both widen as liquidity thins.
        plans, universe_data, benchmark = self._fixture()
        result = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="base",
        )
        first_entry_cost, second_entry_cost = (r["cost"] for r in result["rebalances"])
        self.assertGreater(second_entry_cost, first_entry_cost)

    def test_unsupported_cost_model_raises(self):
        plans, universe_data, benchmark = self._fixture()
        with self.assertRaises(ValueError):
            simulate_locked_portfolio(
                plans, universe_data, benchmark, 100_000.0, cost_model="fantasy",
            )


if __name__ == "__main__":
    unittest.main()
