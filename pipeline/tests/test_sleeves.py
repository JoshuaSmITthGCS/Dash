import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sleeves import empty_sleeve, ineligible_sleeve
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


if __name__ == "__main__":
    unittest.main()
