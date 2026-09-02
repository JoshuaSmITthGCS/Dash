import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import swing_pit_store as sps  # noqa: E402


CANDIDATE = {
    "ticker": "A", "price": 100.0, "composite_z": 1.23,
    "legs": {
        "pead_drift": {"z": 0.5, "weight": 0.3, "applied": True},
        "analyst_revision": {"z": None, "weight": 0.25, "applied": False},
    },
}


class BuildRowsTests(unittest.TestCase):
    def test_a_complete_candidate_flattens_its_leg_zs_alongside_the_composite(self):
        rows = sps.build_rows([CANDIDATE])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["composite_z"], 1.23)
        self.assertEqual(row["pead_drift"], 0.5)
        self.assertNotIn("analyst_revision", row)  # z was None (leg didn't resolve)

    def test_a_candidate_missing_a_composite_is_excluded(self):
        self.assertEqual(sps.build_rows([{**CANDIDATE, "composite_z": None}]), [])

    def test_a_candidate_missing_a_price_is_excluded(self):
        self.assertEqual(sps.build_rows([{**CANDIDATE, "price": None}]), [])

    def test_an_empty_list_produces_no_rows(self):
        self.assertEqual(sps.build_rows([]), [])
        self.assertEqual(sps.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = sps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(sps.snapshot_dates(tmp), ["2026-01-01"])
            self.assertEqual(sps.load_snapshot("2026-01-01", tmp)[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            sps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            sps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(sps.load_snapshot("2026-01-01", tmp)), 1)


if __name__ == "__main__":
    unittest.main()
