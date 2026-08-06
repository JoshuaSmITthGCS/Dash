import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sleeves import empty_sleeve, ineligible_sleeve
from sleeves.growth import score_growth_sleeve
from sleeves.quality import score_quality_sleeve
from sleeves.value import score_value_sleeve

STRONG_VALUE_SNAPSHOT = {
    # Real Estate is in scorer.TANGIBLE_BOOK_SECTORS, so price_to_tangible_book is actually
    # scored (not structurally not-applicable) -- lets a "fully populated" fixture reach all
    # 8 value-family metrics instead of one being inapplicable by sector.
    "is_etf": False, "sector": "Real Estate",
    "peg": 0.9, "forward_pe": 14, "price_to_sales": 2.0, "price_to_book": 2.5,
    "price_to_tangible_book": 2.8, "ev_to_ebitda": 6, "ev_to_ebit": 7, "ev_to_fcf": 10,
    "return_on_equity": 0.22, "profit_margin": 0.2,
}

STRONG_QUALITY_SNAPSHOT = {
    "is_etf": False, "sector": "Technology",
    "gross_profits_to_assets": 0.38, "return_on_invested_capital": 0.24,
    "return_on_equity": 0.22, "free_cash_flow_yield": 0.08, "profit_margin": 0.2,
    "cash_conversion": 1.1, "interest_coverage": 20, "net_debt_to_ebitda": 0.2,
    "debt_to_equity": 0.4, "current_ratio": 2.1, "altman_z": 5.5,
    "net_buyback_yield": 0.04, "stock_comp_to_revenue": 0.008, "capex_to_depreciation": 1.2,
    "asset_growth": 0.05, "accruals_ratio": -0.05, "piotroski_f": 8.5,
    "days_sales_outstanding_trend": -0.06, "inventory_days_trend": -0.06,
}

STRONG_GROWTH_SNAPSHOT = {
    "is_etf": False, "sector": "Technology",
    "revenue_growth": 0.20, "earnings_growth": 0.20, "fcf_growth_3y": 0.18,
    "operating_margin_trend": 0.03, "earnings_surprise": 9.0,
}


class EmptySleeveTests(unittest.TestCase):
    def test_matches_the_research_contract_shape_exactly(self):
        result = empty_sleeve("momentum", "1.0.0", 63)

        self.assertEqual(set(result), {
            "sleeve_id", "version", "target_horizon_days", "raw_features",
            "normalized_features", "subscores", "raw_score", "confidence",
            "eligibility", "warnings", "explanation", "as_of", "config_hash",
        })
        self.assertEqual(result["eligibility"], {"eligible": True, "reasons": []})
        self.assertTrue(result["config_hash"])

    def test_ineligible_sleeve_records_reasons_instead_of_raising(self):
        result = ineligible_sleeve("value", "1.0.0", 63, ["unsupported_security_type"])

        self.assertFalse(result["eligibility"]["eligible"])
        self.assertEqual(result["eligibility"]["reasons"], ["unsupported_security_type"])
        # Still a complete, schema-valid result -- not a partial/exceptional shape.
        self.assertIn("raw_features", result)
        self.assertIn("config_hash", result)


class ValueSleeveTests(unittest.TestCase):
    def test_an_etf_is_ineligible_with_the_correct_reason(self):
        result = score_value_sleeve({"is_etf": True, "sector": "Diversified"})

        self.assertFalse(result["eligibility"]["eligible"])
        self.assertEqual(result["eligibility"]["reasons"], ["unsupported_security_type"])

    def test_a_fully_populated_snapshot_scores_and_reports_full_confidence(self):
        result = score_value_sleeve(STRONG_VALUE_SNAPSHOT)

        self.assertTrue(result["eligibility"]["eligible"])
        self.assertIsInstance(result["raw_score"], (int, float))
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["warnings"], [])
        self.assertTrue(result["explanation"])

    def test_a_snapshot_with_no_value_metrics_is_ineligible_not_silently_neutral(self):
        result = score_value_sleeve({"is_etf": False, "sector": "Technology"})

        self.assertFalse(result["eligibility"]["eligible"])
        self.assertEqual(result["eligibility"]["reasons"], ["missing_provider_data"])

    def test_partial_coverage_is_flagged_as_a_warning_not_hidden(self):
        thin_snapshot = {"is_etf": False, "sector": "Technology", "peg": 0.9}

        result = score_value_sleeve(thin_snapshot)

        self.assertTrue(result["eligibility"]["eligible"])
        self.assertLess(result["confidence"], 1.0)
        self.assertTrue(any("resolved" in warning for warning in result["warnings"]))

    def test_every_result_carries_model_version_and_config_hash(self):
        result = score_value_sleeve(STRONG_VALUE_SNAPSHOT)

        self.assertEqual(result["version"], "1.0.0")
        self.assertTrue(result["config_hash"])
        self.assertTrue(result["as_of"])

    def test_target_horizon_matches_the_research_contract_primary(self):
        result = score_value_sleeve(STRONG_VALUE_SNAPSHOT)

        self.assertEqual(result["target_horizon_days"], 63)


class QualitySleeveTests(unittest.TestCase):
    def test_a_fully_populated_snapshot_scores_across_all_four_categories(self):
        result = score_quality_sleeve(STRONG_QUALITY_SNAPSHOT)

        self.assertTrue(result["eligibility"]["eligible"])
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(
            set(result["subscores"]),
            {"profitability", "financial_health", "capital_allocation", "accounting_quality"},
        )
        self.assertTrue(all(value is not None for value in result["subscores"].values()))

    def test_an_etf_is_ineligible(self):
        result = score_quality_sleeve({"is_etf": True})

        self.assertFalse(result["eligibility"]["eligible"])
        self.assertEqual(result["eligibility"]["reasons"], ["unsupported_security_type"])

    def test_cheap_and_expensive_are_independent_of_quality(self):
        # The whole point of separating value and quality: a company can be cheap-and-
        # high-quality or cheap-and-low-quality, and the value sleeve alone cannot tell you
        # which.
        cheap_and_high_quality = {**STRONG_VALUE_SNAPSHOT, **STRONG_QUALITY_SNAPSHOT}

        value_result = score_value_sleeve(cheap_and_high_quality)
        quality_result = score_quality_sleeve(cheap_and_high_quality)

        self.assertNotEqual(value_result["subscores"], quality_result["subscores"])
        self.assertEqual(value_result["sleeve_id"], "value")
        self.assertEqual(quality_result["sleeve_id"], "quality")


class GrowthSleeveTests(unittest.TestCase):
    def test_a_fully_populated_snapshot_scores_full_confidence(self):
        result = score_growth_sleeve(STRONG_GROWTH_SNAPSHOT)

        self.assertTrue(result["eligibility"]["eligible"])
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(set(result["subscores"]), {"growth"})

    def test_target_horizon_is_the_long_horizon(self):
        result = score_growth_sleeve(STRONG_GROWTH_SNAPSHOT)

        self.assertEqual(result["target_horizon_days"], 252)

    def test_no_growth_data_is_ineligible_not_silently_neutral(self):
        result = score_growth_sleeve({"is_etf": False, "sector": "Technology"})

        self.assertFalse(result["eligibility"]["eligible"])
        self.assertEqual(result["eligibility"]["reasons"], ["missing_provider_data"])


if __name__ == "__main__":
    unittest.main()
