import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import quality_pit_store as qps  # noqa: E402


ROW = {
    "ticker": "A", "price": 100.0, "is_etf": False,
    "fundamental_categories": {"profitability": 70.0, "financial_health": 60.0,
                               "accounting_quality": 55.0, "capital_allocation": 65.0,
                               "valuation": 40.0, "growth": 50.0},
}


class BuildRowsTests(unittest.TestCase):
    def test_a_row_with_categories_is_captured_and_valuation_growth_are_excluded(self):
        rows = qps.build_rows([ROW])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profitability"], 70.0)
        self.assertEqual(row["capital_allocation"], 65.0)
        self.assertNotIn("valuation", row)
        self.assertNotIn("growth", row)

    def test_an_etf_is_excluded(self):
        self.assertEqual(qps.build_rows([{**ROW, "is_etf": True}]), [])

    def test_a_row_missing_every_category_is_excluded(self):
        self.assertEqual(qps.build_rows([{**ROW, "fundamental_categories": {}}]), [])

    def test_a_row_missing_price_is_excluded(self):
        self.assertEqual(qps.build_rows([{**ROW, "price": None}]), [])

    def test_an_empty_list_produces_no_rows(self):
        self.assertEqual(qps.build_rows([]), [])
        self.assertEqual(qps.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = qps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(qps.snapshot_dates(tmp), ["2026-01-01"])
            self.assertEqual(qps.load_snapshot("2026-01-01", tmp)[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            qps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            qps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(qps.load_snapshot("2026-01-01", tmp)), 1)


if __name__ == "__main__":
    unittest.main()
