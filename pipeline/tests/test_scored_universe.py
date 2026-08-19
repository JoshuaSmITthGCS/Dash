import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scored_universe import ScoredUniverseViolation, assert_scored_universe_immutable


class ScoredUniverseGuardTests(unittest.TestCase):
    def test_a_no_op_before_the_freeze_date_even_if_a_name_is_dropped(self):
        previous = [{"ticker": "AAPL", "in_scored_universe": True}]
        new = []  # AAPL dropped entirely
        assert_scored_universe_immutable(previous, new, as_of="2026-08-19T00:00:00Z")  # no raise

    def test_raises_when_a_frozen_name_is_dropped_on_the_freeze_date(self):
        previous = [{"ticker": "AAPL", "in_scored_universe": True},
                   {"ticker": "MSFT", "in_scored_universe": True}]
        new = [{"ticker": "MSFT", "in_scored_universe": True}]
        with self.assertRaises(ScoredUniverseViolation) as ctx:
            assert_scored_universe_immutable(previous, new, as_of="2026-09-01T00:00:00Z")
        self.assertIn("AAPL", str(ctx.exception))

    def test_raises_after_the_freeze_date_too(self):
        previous = [{"ticker": "AAPL", "in_scored_universe": True}]
        new = []
        with self.assertRaises(ScoredUniverseViolation):
            assert_scored_universe_immutable(previous, new, as_of="2027-01-15T00:00:00Z")

    def test_a_name_explicitly_marked_not_in_scored_universe_is_not_protected(self):
        previous = [{"ticker": "AAPL", "in_scored_universe": False}]
        new = []
        assert_scored_universe_immutable(previous, new, as_of="2026-09-01T00:00:00Z")  # no raise

    def test_a_name_that_stays_present_but_becomes_enrichment_ineligible_is_fine(self):
        # enrichment_eligible=false only opts a name out of the REFRESH queue; it must
        # still count as in_scored_universe.
        previous = [{"ticker": "AAPL", "in_scored_universe": True, "enrichment_eligible": True}]
        new = [{"ticker": "AAPL", "in_scored_universe": True, "enrichment_eligible": False}]
        assert_scored_universe_immutable(previous, new, as_of="2026-09-01T00:00:00Z")  # no raise

    def test_rows_missing_in_scored_universe_entirely_default_to_protected(self):
        # Pre-Phase-5 rows never had this field at all; treat their silent absence as
        # "yes, scored" rather than accidentally exempting every legacy row.
        previous = [{"ticker": "AAPL"}]
        new = []
        with self.assertRaises(ScoredUniverseViolation):
            assert_scored_universe_immutable(previous, new, as_of="2026-09-01T00:00:00Z")

    def test_an_empty_previously_scored_universe_is_a_no_op(self):
        assert_scored_universe_immutable([], [], as_of="2026-09-01T00:00:00Z")  # no raise


if __name__ == "__main__":
    unittest.main()
