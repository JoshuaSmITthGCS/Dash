import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from fetch_congress import dedupe, normalize_bargo


class CongressNormalizationTests(unittest.TestCase):
    def test_normalizes_live_shape(self):
        row = normalize_bargo({
            "member": "Hon. Jane Doe", "chamber": "house", "state": "CA",
            "ticker": "nvda", "asset": "NVIDIA", "type": "purchase",
            "amount_low": 1001, "amount_high": 15000,
            "amount_range": "$1,001 - $15,000", "transaction_date": "2026-01-01",
            "disclosure_date": "2026-01-20", "filing_portal": "https://example.gov/filing",
        })
        self.assertEqual(row["politician"], "jane doe")
        self.assertEqual(row["chamber"], "House")
        self.assertEqual(row["ticker"], "NVDA")
        self.assertEqual(row["type"], "buy")
        self.assertEqual(row["filing_lag_days"], 19)

    def test_dedupe_preserves_distinct_same_day_filings(self):
        base = {"politician": "jane doe", "ticker": "ABC", "trade_date": "2026-01-01",
                "filing_date": "2026-01-20", "type": "buy", "amount_mid": 8000}
        self.assertEqual(len(dedupe([base, dict(base)])), 1)
        self.assertEqual(len(dedupe([base, {**base, "type": "sell"}])), 2)


if __name__ == "__main__":
    unittest.main()
