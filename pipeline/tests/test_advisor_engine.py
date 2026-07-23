import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import RANKING_WEIGHTS, build_research, technical_factors


class AdvisorEngineTests(unittest.TestCase):
    def test_ranking_is_fundamentals_dominant(self):
        self.assertEqual(RANKING_WEIGHTS, {
            "fundamentals": 0.75, "market_behavior": 0.15, "news_sentiment": 0.10,
        })

    def test_peg_pe_and_price_to_sales_change_the_rank_score(self):
        base = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "price_to_book": 3, "return_on_equity": 0.18, "free_cash_flow_yield": 0.06,
            "profit_margin": 0.15, "debt_to_equity": 0.6, "current_ratio": 1.5,
            "revenue_growth": 0.10, "earnings_growth": 0.10,
        }
        attractive = {**base, "peg": 0.9, "forward_pe": 20, "price_to_sales": 4}
        expensive = {**base, "peg": 3.2, "forward_pe": 55, "price_to_sales": 26}
        closes = [100 + index * 0.1 for index in range(100)]
        good = build_research("TEST", attractive, closes, closes, [])
        bad = build_research("TEST", expensive, closes, closes, [])
        self.assertGreater(good["components"]["fundamentals"], bad["components"]["fundamentals"])
        self.assertGreater(good["score"], bad["score"])

    def test_technical_score_has_risk_and_relative_strength(self):
        closes = [100 + index * 0.4 for index in range(100)]
        benchmark = [100 + index * 0.1 for index in range(100)]
        score, detail = technical_factors(closes, benchmark)
        self.assertGreater(score, 50)
        self.assertGreater(detail["relative_strength_20d"], 0)
        self.assertEqual(detail["coverage"], 1.0)

    def test_fundamentals_drive_research_score_and_explanations(self):
        snap = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 0.9, "forward_pe": 22, "price_to_sales": 4, "price_to_book": 2.5,
            "return_on_equity": 0.22, "free_cash_flow_yield": 0.08, "profit_margin": 0.21,
            "debt_to_equity": 0.4, "current_ratio": 2.0, "revenue_growth": 0.15,
            "earnings_growth": 0.18,
        }
        closes = [100 + index * 0.3 for index in range(100)]
        row = build_research("TEST", snap, closes, closes, [])
        self.assertGreater(row["components"]["fundamentals"], 75)
        self.assertIn(row["stance"], ("ATTRACTIVE", "PROMISING"))
        self.assertTrue(any("valuation" in item.lower() for item in row["strengths"]))
        self.assertGreater(row["confidence"], 0.8)

    def test_missing_evidence_lowers_confidence(self):
        sparse = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False, "forward_pe": 20}
        row = build_research("TEST", sparse, [100 + i for i in range(100)], None, [])
        self.assertLess(row["confidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
