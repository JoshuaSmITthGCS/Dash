import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from confidence import (completeness_component, confidence_components,
                        freshness_component, model_agreement_component,
                        peer_sample_component, run_source_reliability)


class CompletenessComponentTests(unittest.TestCase):
    def test_matches_the_champion_confidence_formula_exactly(self):
        # completeness must be identical to blend_research_components' confidence blend
        # (0.65 fundamentals + 0.25 market_behavior + 0.10 news_sentiment) -- it is the same
        # number under a different name, not a re-derivation that could drift from it.
        row = {
            "fundamental_detail": {"coverage": 0.8},
            "technical_detail": {"coverage": 0.6},
            "sentiment_detail": {"coverage": 0.5},
        }
        expected = round(0.65 * 0.8 + 0.25 * 0.6 + 0.10 * 0.5, 2)

        self.assertEqual(completeness_component(row), expected)

    def test_missing_detail_blocks_default_to_zero_not_none(self):
        self.assertEqual(completeness_component({}), 0.0)


class FreshnessComponentTests(unittest.TestCase):
    def test_zero_age_is_full_confidence(self):
        now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        row = {"data_fetched_at": now.isoformat()}

        self.assertEqual(freshness_component(row, now=now), 1.0)

    def test_stale_data_decays_below_one(self):
        now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        row = {"data_fetched_at": "2026-08-05T00:00:00+00:00"}  # 36h old

        value = freshness_component(row, now=now)

        self.assertLess(value, 1.0)
        self.assertGreaterEqual(value, 0.0)

    def test_missing_timestamp_is_none_not_a_fabricated_value(self):
        self.assertIsNone(freshness_component({}))


class PeerSampleComponentTests(unittest.TestCase):
    def test_full_peer_group_reaches_one(self):
        row = {"valuation_percentile": {"peer_count_with_valid_data": 25}}

        self.assertEqual(peer_sample_component(row), 1.0)

    def test_thin_peer_group_scores_proportionally(self):
        row = {"valuation_percentile": {"peer_count_with_valid_data": 10}}

        self.assertEqual(peer_sample_component(row), 0.5)

    def test_missing_percentile_is_none(self):
        self.assertIsNone(peer_sample_component({}))


class ModelAgreementComponentTests(unittest.TestCase):
    def test_identical_variant_scores_agree_completely(self):
        row = {"score_variants": {"champion": {"score": 60.0}, "challenger": {"score": 60.0}}}

        self.assertEqual(model_agreement_component(row), 1.0)

    def test_widely_diverging_variants_score_low_agreement(self):
        row = {"score_variants": {"champion": {"score": 80.0}, "challenger": {"score": 20.0}}}

        self.assertEqual(model_agreement_component(row), 0.0)

    def test_single_variant_cannot_measure_agreement(self):
        row = {"score_variants": {"champion": {"score": 60.0}}}

        self.assertIsNone(model_agreement_component(row))


class SourceReliabilityTests(unittest.TestCase):
    def test_all_healthy_configured_sources_score_one(self):
        self.assertEqual(
            run_source_reliability({"sec_form4": "healthy", "fred": "healthy"}), 1.0
        )

    def test_unconfigured_providers_are_excluded_not_penalized(self):
        # An opt-in feature that was never attempted this run must not drag reliability down.
        result = run_source_reliability({
            "sec_form4": "healthy", "options_volatility": "opt_in", "alpha_vantage": "unavailable",
        })

        self.assertEqual(result, 1.0)

    def test_a_universe_wide_failure_scores_zero(self):
        self.assertEqual(run_source_reliability({"yahoo_statement_enrichment": "failed"}), 0.0)

    def test_no_configured_sources_at_all_is_none(self):
        self.assertIsNone(run_source_reliability({}))

    def test_sec_not_configured_is_excluded_like_any_other_unconfigured_source(self):
        # SEC_USER_AGENT unset is an intentional gap, not evidence of an unreliable run.
        result = run_source_reliability({
            "fred": "healthy", "sec_form4": "unavailable_not_configured",
        })
        self.assertEqual(result, 1.0)

    def test_sec_provider_error_counts_against_reliability_unlike_not_configured(self):
        # SEC_USER_AGENT *was* set and EDGAR still failed for every symbol - that is real
        # unreliability and must not be silently excluded the way "not configured" is.
        result = run_source_reliability({
            "fred": "healthy", "sec_form4": "unavailable_provider_error",
        })
        self.assertEqual(result, 0.5)


class ConfidenceComponentsIntegrationTests(unittest.TestCase):
    def test_full_breakdown_reuses_the_existing_confidence_scalar_unchanged(self):
        row = {
            "confidence": 0.44,
            "fundamental_detail": {"coverage": 0.29},
            "technical_detail": {"coverage": 0.7},
            "sentiment_detail": {"coverage": 0.5},
            "valuation_percentile": {"peer_count_with_valid_data": 12},
            "score_variants": {"champion": {"score": 62.3}, "challenger": {"score": 61.8}},
        }

        detail = confidence_components(row, source_reliability=0.5)

        self.assertEqual(detail["confidence"], 0.44)
        self.assertEqual(detail["components"]["completeness"], completeness_component(row))
        self.assertEqual(detail["components"]["source_reliability"], 0.5)
        self.assertIsNone(detail["components"]["historical_calibration"])
        self.assertTrue(any("calibration" in limitation for limitation in detail["limitations"]))

    def test_missing_components_are_listed_as_limitations(self):
        detail = confidence_components({"confidence": 0.4}, source_reliability=None)

        limitation_text = " ".join(detail["limitations"])
        self.assertIn("source_reliability unavailable", limitation_text)
        self.assertIn("freshness unavailable", limitation_text)
        self.assertIn("peer_sample unavailable", limitation_text)


if __name__ == "__main__":
    unittest.main()
