import json
import os
import unittest

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "baseline_published_rows_2026-08-06.json"
)


class BaselineSnapshotTests(unittest.TestCase):
    """Anchors the pre-quant-upgrade champion output so later scoring changes are diffable
    against real published behavior instead of only against synthetic fixtures."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_PATH) as handle:
            cls.payload = json.load(handle)
        cls.rows = cls.payload["rows"]

    def test_snapshot_has_five_rows(self):
        self.assertEqual(len(self.rows), 5)

    def test_every_row_carries_provenance(self):
        for row in self.rows:
            self.assertEqual(row["is_etf"], False)
            self.assertIsInstance(row["score"], (int, float))
            self.assertIsInstance(row["confidence"], (int, float))
            self.assertTrue(0.0 <= row["confidence"] <= 1.0)

    def test_snapshot_confidence_matches_diagnosed_collapse(self):
        # Confirms the Phase 0 diagnosis (statement_enriched_count=0 -> coverage collapse ->
        # confidence pinned low) so a Phase 1 enrichment fix has something concrete to beat.
        confidences = [row["confidence"] for row in self.rows]
        self.assertTrue(all(c <= 0.5 for c in confidences), confidences)

    def test_champion_variant_present_for_every_row(self):
        for row in self.rows:
            variants = row["score_variants_slim"]
            self.assertIn("champion", variants)
            self.assertEqual(variants["champion"]["score"], row["score"])
