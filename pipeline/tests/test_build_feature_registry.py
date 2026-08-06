import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from build_feature_registry import build_feature_registry


class FeatureRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_feature_registry()

    def test_every_fundamentals_metric_weight_is_registered(self):
        from common import load_json
        settings = load_json("settings.json", from_config=True)
        for category, metrics in settings["fundamentals"]["metric_weights"].items():
            for metric_id in metrics:
                self.assertIn(metric_id, self.registry["features"],
                             f"{metric_id} (category {category}) missing from feature registry")

    def test_every_entry_has_a_family_and_usage(self):
        for feature_id, entry in self.registry["features"].items():
            self.assertIn(entry["family"], self.registry["families"], feature_id)
            self.assertTrue(entry["usage"], f"{feature_id} has no usage classification")

    def test_risk_family_factors_are_honestly_marked_as_still_feeding_ranking(self):
        # low_beta, risk_adjusted, and drawdown_resilience are live weights in
        # market_behavior.weights today -- claiming they don't feed ranking would
        # misdescribe the current pipeline, even though the brief's target state is
        # risk-control-only.
        for feature_id in ("low_beta", "risk_adjusted", "drawdown_resilience"):
            entry = self.registry["features"][feature_id]
            self.assertEqual(entry["family"], "risk")
            self.assertIn("ranking", entry["usage"])
            self.assertIsNotNone(entry.get("classification_gap"))

    def test_valuation_metrics_are_classified_as_the_value_family(self):
        self.assertEqual(self.registry["features"]["ev_to_ebitda"]["family"], "value")
        self.assertEqual(self.registry["features"]["forward_pe"]["family"], "value")

    def test_no_fundamentals_metric_is_used_as_a_hard_filter(self):
        # Matches the research contract: fundamentals ratios rank and explain; eligibility
        # gating is a separate mechanism (research_screens_v2.py's MINIMUM_* checks).
        for feature_id, entry in self.registry["features"].items():
            if entry.get("fundamentals_category"):
                self.assertIn("hard_filter", entry["not_used_for"], feature_id)


if __name__ == "__main__":
    unittest.main()
