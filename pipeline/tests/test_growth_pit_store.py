import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import growth_pit_store as gps  # noqa: E402


ROW = {
    "ticker": "A", "price": 100.0, "is_etf": False,
    "technical_detail": {"return_5d": 4.0, "return_20d": 10.0, "volume_ratio_60d": 1.5,
                         "relative_strength_20d": 2.0},
    "fundamental_detail": {"revenue_growth": 0.2, "operating_margin_trend": 0.01},
    "history": {"closes": [100 + (i % 5) for i in range(70)]},
}


class BuildRowsTests(unittest.TestCase):
    def test_a_row_with_technical_data_is_captured(self):
        rows = gps.build_rows([ROW])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "A")
        self.assertEqual(rows[0]["return_5d"], 4.0)
        self.assertEqual(rows[0]["revenue_growth"], 0.2)
        self.assertIsNotNone(rows[0]["recent_vol_10d"])
        self.assertIsNotNone(rows[0]["longer_vol_60d"])

    def test_an_etf_is_excluded(self):
        self.assertEqual(gps.build_rows([{**ROW, "is_etf": True}]), [])

    def test_a_row_with_no_growth_relevant_field_is_excluded(self):
        bare = {"ticker": "B", "price": 10.0, "technical_detail": {}, "fundamental_detail": {}}
        self.assertEqual(gps.build_rows([bare]), [])

    def test_short_price_history_yields_no_volatility_reading(self):
        rows = gps.build_rows([{**ROW, "history": {"closes": [100.0, 101.0]}}])
        self.assertIsNone(rows[0]["recent_vol_10d"])
        self.assertIsNone(rows[0]["longer_vol_60d"])

    def test_an_empty_row_list_produces_no_rows(self):
        self.assertEqual(gps.build_rows([]), [])
        self.assertEqual(gps.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = gps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(gps.snapshot_dates(tmp), ["2026-01-01"])
            loaded = gps.load_snapshot("2026-01-01", tmp)
            self.assertEqual(loaded[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            gps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            gps.append_snapshot([ROW], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(gps.load_snapshot("2026-01-01", tmp)), 1)


if __name__ == "__main__":
    unittest.main()
