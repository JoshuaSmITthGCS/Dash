import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import earnings_timeliness_pit_store as etps  # noqa: E402


CANDIDATE = {
    "ticker": "A", "price": 100.0, "tactical_score": 62.5,
    "factors": {"revision_agreement": 70.0, "eps_surprise": 55.0},
}


class BuildRowsTests(unittest.TestCase):
    def test_a_complete_candidate_flattens_its_factors_alongside_the_composite(self):
        rows = etps.build_rows([CANDIDATE])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["tactical_score"], 62.5)
        self.assertEqual(row["revision_agreement"], 70.0)
        self.assertEqual(row["eps_surprise"], 55.0)

    def test_a_candidate_missing_a_composite_is_excluded(self):
        self.assertEqual(etps.build_rows([{**CANDIDATE, "tactical_score": None}]), [])

    def test_a_candidate_missing_a_price_is_excluded(self):
        self.assertEqual(etps.build_rows([{**CANDIDATE, "price": None}]), [])

    def test_an_empty_list_produces_no_rows(self):
        self.assertEqual(etps.build_rows([]), [])
        self.assertEqual(etps.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = etps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(etps.snapshot_dates(tmp), ["2026-01-01"])
            self.assertEqual(etps.load_snapshot("2026-01-01", tmp)[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            etps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            etps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(etps.load_snapshot("2026-01-01", tmp)), 1)


if __name__ == "__main__":
    unittest.main()
