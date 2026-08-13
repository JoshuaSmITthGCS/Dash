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


if __name__ == "__main__":
    unittest.main()
