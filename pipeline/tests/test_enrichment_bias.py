import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from enrichment_bias import build_enrichment_bias_report, is_statement_enriched


class StatementEnrichedTests(unittest.TestCase):
    def test_row_with_both_statement_categories_is_enriched(self):
        row = {"fundamental_categories": {"capital_allocation": 60.0, "accounting_quality": 55.0}}
        self.assertTrue(is_statement_enriched(row))

    def test_row_missing_one_statement_category_is_not_enriched(self):
        row = {"fundamental_categories": {"capital_allocation": 60.0, "accounting_quality": None}}
        self.assertFalse(is_statement_enriched(row))

    def test_row_with_only_screen_categories_is_not_enriched(self):
        row = {"fundamental_categories": {"growth": 50.0, "valuation": 40.0}}
        self.assertFalse(is_statement_enriched(row))


class EnrichmentBiasReportTests(unittest.TestCase):
    def _payload(self):
        enriched = {
            "ticker": "ENR", "sector": "Technology", "score": 80.0, "market_cap": 1e9,
            "fundamental_categories": {"capital_allocation": 70.0, "accounting_quality": 65.0,
                                       "growth": 60.0},
        }
        non_enriched = {
            "ticker": "NON", "sector": "Healthcare", "score": 40.0,
            "fundamental_categories": {"growth": 45.0, "valuation": 30.0},
        }
        return {"research": [enriched], "screen_universe": [non_enriched]}

    def test_coverage_by_collection_counts_only_populated_categories(self):
        report = build_enrichment_bias_report(self._payload())
        research_coverage = report["coverage_by_collection"]["research"]["categories"]
        self.assertEqual(research_coverage["capital_allocation"]["scored"], 1)
        screen_coverage = report["coverage_by_collection"]["screen_universe"]["categories"]
        self.assertNotIn("capital_allocation", screen_coverage)

    def test_enriched_and_non_enriched_populations_are_split_correctly(self):
        report = build_enrichment_bias_report(self._payload())
        split = report["enriched_vs_non_enriched"]
        self.assertEqual(split["enriched_count"], 1)
        self.assertEqual(split["non_enriched_count"], 1)
        self.assertEqual(split["score"]["enriched"]["mean"], 80.0)
        self.assertEqual(split["score"]["non_enriched"]["mean"], 40.0)

    def test_market_cap_comparison_is_flagged_not_measurable_when_one_side_lacks_it(self):
        report = build_enrichment_bias_report(self._payload())
        self.assertEqual(
            report["enriched_vs_non_enriched"]["market_cap_comparison"]["status"],
            "not_measurable",
        )

    def test_full_universe_comparison_is_marked_blocked_with_a_reproduction_command(self):
        report = build_enrichment_bias_report(self._payload())
        blocked = report["full_universe_comparison"]
        self.assertEqual(blocked["status"], "blocked_network_policy")
        self.assertIn("FULL_UNIVERSE_RESEARCH=true", blocked["reproduction_command"])

    def test_never_fabricates_a_score_for_an_empty_population(self):
        report = build_enrichment_bias_report({"research": [], "screen_universe": []})
        split = report["enriched_vs_non_enriched"]
        self.assertIsNone(split["score"]["enriched"]["mean"])
        self.assertIsNone(split["score"]["non_enriched"]["mean"])


if __name__ == "__main__":
    unittest.main()
