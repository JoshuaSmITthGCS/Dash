import datetime as dt
import unittest

from evaluate_alerts import evaluate_rule, should_fire


class AlertEvaluationTests(unittest.TestCase):
    def test_price_cross_fires_once_until_condition_resets(self):
        rule = {"type": "price_cross", "ticker": "AAA", "direction": "above", "threshold": 100}
        current = evaluate_rule(rule, {"price": 101})
        self.assertTrue(should_fire(None, current))
        self.assertFalse(should_fire(current, current))
        reset = evaluate_rule(rule, {"price": 99})
        self.assertFalse(reset["active"])
        self.assertTrue(should_fire(reset, current))

    def test_five_day_move_uses_price_history(self):
        rule = {"type": "percent_move", "ticker": "AAA", "direction": "above", "threshold": 5, "periodDays": 5}
        current = evaluate_rule(rule, {"history": {"closes": [100, 100, 100, 100, 100, 106]}})
        self.assertTrue(current["active"])
        self.assertAlmostEqual(current["value"], 6)

    def test_pipeline_stale_uses_configured_hours(self):
        now = dt.datetime(2026, 8, 5, 20, tzinfo=dt.timezone.utc)
        current = evaluate_rule({"type": "pipeline_stale", "staleHours": 36}, generated_at="2026-08-03T00:00:00+00:00", now=now)
        self.assertTrue(current["active"])


if __name__ == "__main__":
    unittest.main()
