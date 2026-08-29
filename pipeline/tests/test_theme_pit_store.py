import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import theme_pit_store as tps
import theme_ic as tic


SCREEN = {
    "themes": [{
        "id": "t",
        "rows": [
            {"ticker": "A", "theme_exposure_score": 80, "opportunity_score": 75, "eligible": True},
            {"ticker": "B", "theme_exposure_score": None, "eligible": False},
        ],
    }],
    "connectivity": {
        "by_ticker": {"A": {"connectivity_score": 5.0, "effective_theme_count": 1}},
        "per_theme": {"t": {"structural_rank": {"composite_score": 0.7}}},
    },
}


class BuildRowsTests(unittest.TestCase):
    def test_only_scored_rows_are_captured(self):
        rows = tps.build_rows(SCREEN, {"A": 100.0, "B": 50.0})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "A")
        self.assertEqual(rows[0]["connectivity_score"], 5.0)
        self.assertEqual(rows[0]["structural_rank_composite"], 0.7)
        self.assertEqual(rows[0]["price"], 100.0)

    def test_an_empty_screen_produces_no_rows(self):
        self.assertEqual(tps.build_rows({}), [])
        self.assertEqual(tps.build_rows({"themes": []}), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = tps.append_snapshot(SCREEN, {"A": 100.0}, recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(tps.snapshot_dates(tmp), ["2026-01-01"])
            loaded = tps.load_snapshot("2026-01-01", tmp)
            self.assertEqual(loaded[0]["ticker"], "A")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            tps.append_snapshot(SCREEN, {"A": 100.0}, recorded_at=recorded, store_dir=tmp)
            tps.append_snapshot(SCREEN, {"A": 100.0}, recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(tps.load_snapshot("2026-01-01", tmp)), 1)


class ThemeIcTests(unittest.TestCase):
    def test_zero_snapshots_reports_accumulating_with_no_number_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = tic.build_report(store_dir=tmp)
            for metric in tic.GRADED_METRICS:
                self.assertEqual(report["metrics"][metric]["status"], "accumulating")
                self.assertIsNone(report["metrics"][metric]["mean_rank_ic"])

    def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
            day2 = day1 + timedelta(days=95)
            rows1 = [{"ticker": t, "theme_id": "x", "price": 100.0, "theme_exposure_score": score,
                     "connectivity_score": score / 10, "structural_rank_composite": score / 100}
                    for t, score in zip("ABCDE", (80, 40, 60, 20, 90))]
            rows2 = [{"ticker": t, "theme_id": "x", "price": price}
                    for t, price in zip("ABCDE", (130.0, 105.0, 115.0, 100.0, 140.0))]
            tps.append_snapshot({"themes": [{"id": "x", "rows": [
                {"ticker": r["ticker"], "theme_exposure_score": r["theme_exposure_score"], "eligible": True}
                for r in rows1]}], "connectivity": {"by_ticker": {
                    r["ticker"]: {"connectivity_score": r["connectivity_score"]} for r in rows1},
                    "per_theme": {"x": {"structural_rank": {"composite_score": None}}}}},
                {r["ticker"]: r["price"] for r in rows1}, recorded_at=day1, store_dir=tmp)
            tps.append_snapshot({"themes": [{"id": "x", "rows": [
                {"ticker": r["ticker"], "theme_exposure_score": 1, "eligible": True} for r in rows2]}]},
                {r["ticker"]: r["price"] for r in rows2}, recorded_at=day2, store_dir=tmp)

            report = tic.build_report(store_dir=tmp)
            self.assertEqual(report["snapshot_dates_recorded"], 2)
            metric = report["metrics"]["theme_exposure_score"]
            self.assertEqual(metric["eligible_periods"], 1)
            self.assertEqual(metric["status"], "accumulating")
            self.assertIsNone(metric["mean_rank_ic"])


if __name__ == "__main__":
    unittest.main()
