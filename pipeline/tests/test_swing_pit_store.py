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


TOP_ROW = {"ticker": "A", "rank": 3, "price": 100.0}
OUTSIDE_TOP_ROW = {"ticker": "B", "rank": 11, "price": 50.0}


class FirstSeenTests(unittest.TestCase):
    def test_a_ticker_ranking_top_n_is_recorded_with_todays_date_tier_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            seen = sps.update_first_seen({"S": [TOP_ROW]}, recorded_at=recorded, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-01-01", "tier": "S",
                                         "price_at_prediction": 100.0})
            self.assertEqual(sps.load_first_seen(tmp), seen)

    def test_a_ticker_ranking_outside_top_n_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = sps.update_first_seen({"S": [OUTSIDE_TOP_ROW]}, store_dir=tmp)
            self.assertEqual(seen, {})
            self.assertEqual(sps.load_first_seen(tmp), {})

    def test_a_ticker_already_on_file_keeps_its_original_date_tier_and_price(self):
        """The whole point: date_predicted is the first time, never the most recent."""
        with tempfile.TemporaryDirectory() as tmp:
            first = datetime(2026, 1, 1, tzinfo=timezone.utc)
            later = datetime(2026, 2, 1, tzinfo=timezone.utc)
            sps.update_first_seen({"S": [TOP_ROW]}, recorded_at=first, store_dir=tmp)
            seen = sps.update_first_seen({"F": [{"ticker": "A", "rank": 1, "price": 250.0}]},
                                         recorded_at=later, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-01-01", "tier": "S",
                                         "price_at_prediction": 100.0})

    def test_a_ticker_seen_top_n_in_any_tier_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = sps.update_first_seen(
                {"F": [OUTSIDE_TOP_ROW], "M": [], "S": [TOP_ROW]}, store_dir=tmp)
            self.assertIn("A", seen)
            self.assertNotIn("B", seen)

    def test_load_first_seen_on_an_empty_store_is_an_empty_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sps.load_first_seen(tmp), {})


if __name__ == "__main__":
    unittest.main()
