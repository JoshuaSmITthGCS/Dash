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
        self.assertEqual(score, 68.2)
        self.assertEqual(parts["peg"], 100.0)
        self.assertEqual(parts["coverage"], 0.09)

    def test_sector_context_changes_forward_pe_score(self):
        tech_score, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 30})
        bank_score, _ = scorer.valuation_score({"is_etf": False, "sector": "Financial Services", "forward_pe": 30})
        self.assertGreater(tech_score, bank_score)

    def test_strong_fundamentals_score_across_all_categories(self):
        score, parts = scorer.valuation_score({
            "is_etf": False, "sector": "Technology", "peg": 0.9, "forward_pe": 24,
            "price_to_sales": 4, "price_to_book": 2.5, "return_on_equity": 0.22,
            "free_cash_flow_yield": 0.08, "profit_margin": 0.20,
            "debt_to_equity": 0.4, "current_ratio": 2.1,
            "revenue_growth": 0.20, "earnings_growth": 0.20,
        })
        self.assertGreaterEqual(score, 95)
        self.assertEqual(parts["coverage"], 1.0)
        self.assertEqual(set(parts["categories"]), {"valuation", "profitability", "financial_health", "growth"})

    def test_suspiciously_low_pe_is_not_automatic_maximum(self):
        suspicious, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 5})
        healthy, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 20})
        self.assertGreater(healthy, suspicious)

    def test_bank_leverage_is_displayed_but_not_scored_with_industrial_cutoffs(self):
        _, parts = scorer.valuation_score({"is_etf": False, "sector": "Financial Services",
                                           "price_to_book": 1.2, "debt_to_equity": 2.5,
                                           "current_ratio": 0.6})
        self.assertIsNone(parts["debt_to_equity"])
        self.assertIsNone(parts["current_ratio"])

    def test_label_thresholds(self):
        self.assertEqual(scorer.label_for(90), "HIGH CONVICTION")
        self.assertEqual(scorer.label_for(0), "LOW")


if __name__ == "__main__":
    unittest.main()
