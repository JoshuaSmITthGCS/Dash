import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import rank_picks


class RankPicksTests(unittest.TestCase):
    def test_momentum_is_bounded(self):
        self.assertEqual(rank_picks.momentum_score(1000), 100.0)
        self.assertEqual(rank_picks.momentum_score(-1000), 0.0)
        self.assertEqual(rank_picks.momentum_score(None), 50.0)

    def test_broad_etf_outranks_single_stock_stability(self):
        etf = {"ticker": "VTI", "is_etf": True, "expense_ratio": 0.03}
        stock = {"ticker": "XYZ", "is_etf": False, "market_cap": 1e12,
                 "dividend_yield": 0.05, "price_to_sales": 1}
        self.assertGreater(rank_picks.stability_score(etf), rank_picks.stability_score(stock))

    def test_tiers_are_research_labels(self):
        self.assertEqual(rank_picks.tier(90), "HIGH CONVICTION")
        self.assertEqual(rank_picks.tier(0), "LOW")


if __name__ == "__main__":
    unittest.main()
