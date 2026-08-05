import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from signal_report import build_signal_report


class SignalReportTests(unittest.TestCase):
    def test_each_change_is_reported_in_isolation(self):
        rows = []
        for index in range(6):
            variants = {
                name: {"score": 50 + index + offset}
                for offset, name in enumerate((
                    "normalization", "short_horizon", "confidence_shrinkage",
                    "modifier_recalibration", "challenger",
                ))
            }
            rows.append({
                "ticker": f"T{index}", "sector": "Technology", "score": 60 - index,
                "market_cap": 1_000_000 * (index + 1), "analyst_count": index + 1,
                "score_variants": variants,
            })
        report = build_signal_report(rows)
        self.assertEqual(set(report["isolated_changes"]), set(variants))
        self.assertEqual(len(report["isolated_changes"]["challenger"]), 6)
        self.assertIn("score_vs_log_market_cap", report["rank_correlation"])


if __name__ == "__main__":
    unittest.main()
