import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import load_json
from explainability import (anomaly_flags, attach_explainability, attribution_errors,
                            build_score_history, score_attribution)


class ExplainabilityTests(unittest.TestCase):
    def test_attribution_reconciles_through_confidence_and_modifiers(self):
        row = {
            "score": 82.0,
            "components": {"fundamentals": 85.0, "market_behavior": 70.0, "news_sentiment": 55.0},
            "fundamental_categories": {
                "valuation": 70.0, "profitability": 95.0, "financial_health": 80.0,
                "growth": 75.0, "capital_allocation": 65.0, "accounting_quality": 90.0,
            },
            "modifiers": {"applied": {"expectations": 1.1, "short_interest": -0.5}},
        }
        variant = {**row, "raw_score": 81.6, "base_score": 79.5, "score": 82.0}
        result = score_attribution(variant, row)
        self.assertTrue(result["reconciled"])
        self.assertLessEqual(abs(result["reconciliation_error"]), 0.01)
        self.assertEqual({item["key"] for item in result["modifiers"]}, {
            "sector_valuation", "short_interest", "liquidity", "expectations",
            "macro_regime", "insider_activity", "score_rounding",
        })

    def test_anomaly_rules_describe_observed_cash_earnings_divergence(self):
        flags = anomaly_flags({"accruals_ratio": 0.08, "fcf_growth_3y": 0.03, "earnings_growth": 0.2})
        self.assertIn("cash_earnings_divergence", [flag["id"] for flag in flags])

    def test_history_is_accumulating_below_six_distinct_months(self):
        rows = [{
            "ticker": "AAA", "recorded_at": "2026-01-02T00:00:00Z", "refresh_id": "one",
            "scores": {"champion": 70, "challenger": 68},
            "confidence": {"champion": 0.9, "challenger": 0.9},
            "category_scores": {"champion": {"growth": 60}},
        }]
        self.assertEqual(build_score_history(rows)["AAA"]["status"], "accumulating")

    def test_every_published_attribution_reconciles(self):
        payload = load_json("advisor.json") or {}
        rows = payload.get("research") or []
        self.assertTrue(rows)
        for row in rows:
            if not row.get("explainability"):
                attach_explainability(row)
        self.assertEqual(attribution_errors(rows), [])


if __name__ == "__main__":
    unittest.main()
