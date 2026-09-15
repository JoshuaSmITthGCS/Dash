import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import momentum_pit_store as mps  # noqa: E402


CANDIDATE = {
    "ticker": "A", "price": 100.0, "score": 1.23,
    "standardized_factors": {"momentum_12_1": 0.5, "momentum_6_1": 0.2},
}


class BuildRowsTests(unittest.TestCase):
    def test_a_complete_candidate_flattens_its_standardized_factors_alongside_the_score(self):
        rows = mps.build_rows([CANDIDATE])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["score"], 1.23)
        self.assertEqual(row["momentum_12_1"], 0.5)
        self.assertEqual(row["momentum_6_1"], 0.2)

    def test_a_candidate_missing_a_score_is_excluded(self):
        self.assertEqual(mps.build_rows([{**CANDIDATE, "score": None}]), [])

    def test_a_candidate_missing_a_price_is_excluded(self):
        self.assertEqual(mps.build_rows([{**CANDIDATE, "price": None}]), [])

    def test_an_empty_list_produces_no_rows(self):
        self.assertEqual(mps.build_rows([]), [])
        self.assertEqual(mps.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = mps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(mps.snapshot_dates(tmp), ["2026-01-01"])
            self.assertEqual(mps.load_snapshot("2026-01-01", tmp)[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            mps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            mps.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(mps.load_snapshot("2026-01-01", tmp)), 1)


TOP_ROW = {"ticker": "A", "rank": 3, "price": 100.0}
OUTSIDE_TOP_ROW = {"ticker": "B", "rank": 11, "price": 50.0}


class FirstSeenTests(unittest.TestCase):
    """Eviction-based, unlike swing's permanent record - see update_first_seen's docstring."""

    def test_a_ticker_ranking_top_n_is_recorded_with_todays_date_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            seen = mps.update_first_seen([TOP_ROW], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-01-01", "price_at_prediction": 100.0})
            self.assertEqual(mps.load_first_seen(tmp), seen)

    def test_a_ticker_ranking_outside_top_n_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = mps.update_first_seen([OUTSIDE_TOP_ROW], store_dir=tmp)
            self.assertEqual(seen, {})

    def test_a_ticker_still_top_n_on_a_later_run_keeps_its_original_date_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = datetime(2026, 1, 1, tzinfo=timezone.utc)
            later = datetime(2026, 2, 1, tzinfo=timezone.utc)
            mps.update_first_seen([TOP_ROW], recorded_at=first, store_dir=tmp)
            seen = mps.update_first_seen([{"ticker": "A", "rank": 1, "price": 250.0}],
                                         recorded_at=later, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-01-01", "price_at_prediction": 100.0})

    def test_a_ticker_that_falls_out_of_top_n_is_evicted(self):
        with tempfile.TemporaryDirectory() as tmp:
            mps.update_first_seen([TOP_ROW], store_dir=tmp)
            seen = mps.update_first_seen([], store_dir=tmp)
            self.assertEqual(seen, {})

    def test_re_entering_later_starts_a_fresh_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = datetime(2026, 1, 1, tzinfo=timezone.utc)
            later = datetime(2026, 2, 1, tzinfo=timezone.utc)
            mps.update_first_seen([TOP_ROW], recorded_at=first, store_dir=tmp)
            mps.update_first_seen([], store_dir=tmp)
            seen = mps.update_first_seen([{"ticker": "A", "rank": 1, "price": 200.0}],
                                         recorded_at=later, store_dir=tmp)
            self.assertEqual(seen["A"], {"date_predicted": "2026-02-01", "price_at_prediction": 200.0})


if __name__ == "__main__":
    unittest.main()
