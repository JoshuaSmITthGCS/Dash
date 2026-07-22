import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import scorer


class ScorerTests(unittest.TestCase):
    def test_band_score_prefers_lower_valuation(self):
        bands = {"excellent": 1, "good": 2, "fair": 3, "rich": 4}
        self.assertEqual(scorer.band_score(0.8, bands), 100.0)
        self.assertEqual(scorer.band_score(5, bands), 10.0)

    def test_valuation_score_reweights_missing_metrics(self):
        score, parts = scorer.valuation_score({"is_etf": False, "peg": 1.0,
                                               "forward_pe": None, "price_to_sales": None})
        self.assertEqual(score, 100.0)
        self.assertEqual(parts["peg"], 100.0)

    def test_label_thresholds(self):
        self.assertEqual(scorer.label_for(90), "HIGH CONVICTION")
        self.assertEqual(scorer.label_for(0), "LOW")


if __name__ == "__main__":
    unittest.main()
