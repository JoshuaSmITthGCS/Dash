import os
import sys
import unittest
from datetime import date

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from backtest_monthly import (  # noqa: E402
    appeal_weights,
    build_rebalance_calendar,
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


if __name__ == "__main__":
    unittest.main()
