import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validate_data import enrichment_coverage_errors


class EnrichmentCoverageGateTests(unittest.TestCase):
    """Guards the Phase 1 fix: a full sweep that attempts statement enrichment but enriches
    zero companies (the 2026-08-06 incident) must fail validation, not publish silently."""

    def test_zero_enrichment_on_a_full_sweep_with_attempts_fails(self):
        advisor = {
            "universe_mode": "full",
            "statement_enriched_count": 0,
            "enrichment_diagnostics": {
                "attempted": 23, "info_fetch_failed": 23, "statement_fetch_failed": 0,
                "derivation_failed": 0, "no_statement_data": 0,
            },
        }

        errors = enrichment_coverage_errors(advisor)

        self.assertEqual(len(errors), 1)
        self.assertIn("statement_enriched_count is 0", errors[0])
        self.assertIn("info_fetch_failed=23", errors[0])

    def test_partial_enrichment_on_a_full_sweep_passes(self):
        advisor = {
            "universe_mode": "full",
            "statement_enriched_count": 18,
            "enrichment_diagnostics": {
                "attempted": 23, "info_fetch_failed": 5, "statement_fetch_failed": 0,
                "derivation_failed": 0, "no_statement_data": 0,
            },
        }

        self.assertEqual(enrichment_coverage_errors(advisor), [])

    def test_fast_refresh_with_zero_enrichment_does_not_fail(self):
        # Fast/intraday refreshes intentionally skip enrichment (prior top names carry their
        # existing statement data forward) -- only a full sweep is a real failure signal.
        advisor = {
            "universe_mode": "fast",
            "statement_enriched_count": 0,
            "enrichment_diagnostics": {"attempted": 0, "info_fetch_failed": 0,
                                       "statement_fetch_failed": 0, "derivation_failed": 0,
                                       "no_statement_data": 0},
        }

        self.assertEqual(enrichment_coverage_errors(advisor), [])

    def test_full_sweep_that_never_attempted_enrichment_does_not_false_positive(self):
        advisor = {
            "universe_mode": "full", "statement_enriched_count": 0,
            "enrichment_diagnostics": {"attempted": 0, "info_fetch_failed": 0,
                                       "statement_fetch_failed": 0, "derivation_failed": 0,
                                       "no_statement_data": 0},
        }

        self.assertEqual(enrichment_coverage_errors(advisor), [])

    def test_missing_advisor_payload_is_a_no_op(self):
        self.assertEqual(enrichment_coverage_errors({}), [])
        self.assertEqual(enrichment_coverage_errors(None), [])


if __name__ == "__main__":
    unittest.main()
