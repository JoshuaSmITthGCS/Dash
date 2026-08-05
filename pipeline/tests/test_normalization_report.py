import os
import sys
import tempfile
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from normalization_report import build_normalization_report, write_normalization_report


class NormalizationReportTests(unittest.TestCase):
    def rows(self):
        rows = []
        for index in range(10):
            champion = 80 - index * 3 if index < 5 else 45 + index
            challenger = 70 - index if index < 5 else 58 + index / 2
            rows.append({
                "ticker": f"T{index}",
                "sector": "Technology" if index < 5 else "Energy",
                "score": champion,
                "score_variants": {"challenger": {
                    "score": challenger,
                    "largest_metric_changes": [{"metric": "forward_pe", "delta": index}],
                }},
            })
        return rows

    def test_report_contains_attributed_movers_and_sector_dispersion(self):
        report = build_normalization_report(self.rows(), mover_limit=4, minimum_sector_count=3)
        self.assertEqual(report["universe_count"], 10)
        self.assertEqual(len(report["largest_rank_movers"]), 4)
        self.assertIn("spearman_rank_correlation", report)
        self.assertIn("champion", report["sector_mean_dispersion"])
        self.assertIn("standard_deviation", report["sector_score_statistics"]["Technology"]["champion"])
        self.assertTrue(report["largest_rank_movers"][0]["reasons"])

    def test_writer_creates_requested_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "normalization_diff.json")
            write_normalization_report(self.rows(), 3, 3, path=path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
