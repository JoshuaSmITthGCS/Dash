import json
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


def _seed_day(store_dir, date, rows):
    """Write a daily composite snapshot directly, bypassing append_snapshot, so a test can
    control exactly which tickers/scores/prices land on which date."""
    with open(os.path.join(store_dir, f"{date}.jsonl"), "w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class LegacyBackfillTests(unittest.TestCase):
    """The honest, bounded backfill: real pre-launch composite log, never the days after."""

    def test_a_ticker_top_ranked_before_the_cutoff_is_backfilled_as_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed_day(tmp, "2026-09-02", [{"ticker": "AMZN", "composite_z": 1.3, "price": 254.98}])
            seen = sps.update_first_seen({}, store_dir=tmp)
            self.assertEqual(seen["AMZN"], {"date_predicted": "2026-09-02", "tier": "legacy",
                                            "price_at_prediction": 254.98})

    def test_only_the_days_top_n_by_composite_z_qualify(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"ticker": f"T{i}", "composite_z": float(i), "price": 10.0} for i in range(15)]
            _seed_day(tmp, "2026-09-02", rows)
            seen = sps.update_first_seen({}, store_dir=tmp, top_n=10)
            # T14 down to T5 are the top 10 by composite_z; T4 and below are not.
            self.assertIn("T14", seen)
            self.assertIn("T5", seen)
            self.assertNotIn("T4", seen)

    def test_the_earliest_pre_cutoff_date_wins_across_multiple_qualifying_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed_day(tmp, "2026-09-02", [{"ticker": "A", "composite_z": 1.0, "price": 50.0}])
            _seed_day(tmp, "2026-09-05", [{"ticker": "A", "composite_z": 2.0, "price": 60.0}])
            seen = sps.update_first_seen({}, store_dir=tmp)
            self.assertEqual(seen["A"]["date_predicted"], "2026-09-02")
            self.assertEqual(seen["A"]["price_at_prediction"], 50.0)

    def test_a_snapshot_dated_on_or_after_the_cutoff_is_never_treated_as_legacy(self):
        """The bounded window that keeps append_snapshot's own ongoing daily log from quietly
        turning into a second, competing first-seen tracker forever after launch."""
        with tempfile.TemporaryDirectory() as tmp:
            _seed_day(tmp, sps.LEGACY_BACKFILL_CUTOFF,
                     [{"ticker": "LATE", "composite_z": 5.0, "price": 10.0}])
            seen = sps.update_first_seen({}, store_dir=tmp)
            self.assertNotIn("LATE", seen)

    def test_a_legacy_backfilled_date_is_never_overwritten_by_a_later_live_tier_sighting(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed_day(tmp, "2026-09-02", [{"ticker": "A", "composite_z": 1.0, "price": 50.0}])
            recorded = datetime(2026, 9, 12, tzinfo=timezone.utc)
            seen = sps.update_first_seen({"S": [{"ticker": "A", "rank": 1, "price": 90.0}]},
                                         recorded_at=recorded, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-09-02", "tier": "legacy",
                                         "price_at_prediction": 50.0})

    def test_no_jsonl_history_backfills_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sps.update_first_seen({}, store_dir=tmp), {})


if __name__ == "__main__":
    unittest.main()
