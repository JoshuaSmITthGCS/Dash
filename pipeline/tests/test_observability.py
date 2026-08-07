import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from observability import run_manifest


class RunManifestScoreDistributionTests(unittest.TestCase):
    def _payload(self, rows):
        return {
            "generated_at": "2026-08-07T00:00:00+00:00",
            "schema_version": 5,
            "universe": ["A", "B"],
            "source_status": {},
            "research": rows,
        }

    def test_score_distribution_matches_published_champion_score_not_v2_shadow(self):
        # analysis_v2.structural.effective_score is a shadow-model figure that has run ahead of
        # the published champion score before; the manifest must describe what shipped.
        rows = [
            {"ticker": "A", "score": 83.4,
             "analysis_v2": {"structural": {"effective_score": 73.3}}},
            {"ticker": "B", "score": 71.4,
             "analysis_v2": {"structural": {"effective_score": 60.0}}},
        ]
        manifest = run_manifest(self._payload(rows))
        distribution = manifest["score_distribution"]
        self.assertEqual(distribution["count"], 2)
        self.assertEqual(distribution["minimum"], 71.4)
        self.assertEqual(distribution["maximum"], 83.4)
        self.assertEqual(distribution["mean"], round((83.4 + 71.4) / 2, 2))

    def test_score_distribution_matches_published_advisor_json_champion_range(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "..", "public", "data", "advisor.json")
        path = os.path.normpath(path)
        if not os.path.exists(path):
            self.skipTest("public/data/advisor.json not present in this checkout")
        with open(path) as handle:
            payload = json.load(handle)
        research = payload.get("research", [])
        champion_scores = [row["score"] for row in research if isinstance(row.get("score"), (int, float))]
        manifest = run_manifest(payload)
        distribution = manifest["score_distribution"]
        self.assertAlmostEqual(distribution["minimum"], min(champion_scores), places=6)
        self.assertAlmostEqual(distribution["maximum"], max(champion_scores), places=6)
        self.assertAlmostEqual(distribution["mean"],
                                round(sum(champion_scores) / len(champion_scores), 2), places=2)


if __name__ == "__main__":
    unittest.main()
