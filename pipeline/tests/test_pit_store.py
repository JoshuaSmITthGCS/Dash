import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pit_store


class PitStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="pit-test-")
        self._original = pit_store.PIT_DIR
        pit_store.PIT_DIR = self.directory

    def tearDown(self):
        pit_store.PIT_DIR = self._original
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_observations_are_appended_with_a_timestamp(self):
        result = pit_store.append_snapshot(
            [{"ticker": "AAA", "price": 10.0, "piotroski_f": 7.0}],
            observed_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(result["observations"], 1)
        snapshot = pit_store.as_of("AAA", "2026-01-01")
        self.assertEqual(snapshot["values"]["price"], 10.0)

    def test_as_of_never_sees_a_later_observation(self):
        # The whole point of the store: a backtest asking what was known in January must
        # not be handed February's restated number.
        pit_store.append_snapshot([{"ticker": "AAA", "price": 10.0}],
                                  observed_at="2026-01-01T00:00:00+00:00")
        pit_store.append_snapshot([{"ticker": "AAA", "price": 25.0}],
                                  observed_at="2026-02-01T00:00:00+00:00")
        self.assertEqual(pit_store.as_of("AAA", "2026-01-15")["values"]["price"], 10.0)
        self.assertEqual(pit_store.as_of("AAA", "2026-02-15")["values"]["price"], 25.0)

    def test_as_of_before_any_observation_returns_nothing(self):
        pit_store.append_snapshot([{"ticker": "AAA", "price": 10.0}],
                                  observed_at="2026-06-01T00:00:00+00:00")
        self.assertIsNone(pit_store.as_of("AAA", "2026-01-01"))

    def test_restatements_are_logged_as_revisions(self):
        pit_store.append_snapshot([{"ticker": "AAA", "accruals_ratio": 0.05}],
                                  observed_at="2026-01-01T00:00:00+00:00")
        pit_store.append_snapshot([{"ticker": "AAA", "accruals_ratio": 0.09}],
                                  observed_at="2026-04-01T00:00:00+00:00")
        revisions = pit_store.revision_log("AAA", "accruals_ratio")
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["previous"], 0.05)
        self.assertEqual(revisions[0]["current"], 0.09)

    def test_an_unchanged_value_is_not_logged_as_a_revision(self):
        for stamp in ("2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"):
            pit_store.append_snapshot([{"ticker": "AAA", "piotroski_f": 7.0}], observed_at=stamp)
        self.assertEqual(pit_store.revision_log("AAA"), [])

    def test_untracked_and_null_fields_are_not_stored(self):
        pit_store.append_snapshot(
            [{"ticker": "AAA", "price": 10.0, "price_to_book": None, "some_ui_field": "x"}],
            observed_at="2026-01-01T00:00:00+00:00")
        values = pit_store.as_of("AAA")["values"]
        self.assertNotIn("price_to_book", values)
        self.assertNotIn("some_ui_field", values)

    def test_rows_without_a_ticker_are_skipped(self):
        result = pit_store.append_snapshot([{"price": 10.0}],
                                           observed_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(result["observations"], 0)

    def test_history_returns_a_field_over_time(self):
        for index, stamp in enumerate(("2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00")):
            pit_store.append_snapshot([{"ticker": "AAA", "price": 10.0 + index}], observed_at=stamp)
        series = pit_store.history("AAA", "price")
        self.assertEqual([row["value"] for row in series], [10.0, 11.0])


class UniverseMembershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="pit-universe-")
        self._original = pit_store.PIT_DIR
        pit_store.PIT_DIR = self.directory

    def tearDown(self):
        pit_store.PIT_DIR = self._original
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_departed_symbols_are_recorded_not_forgotten(self):
        # Survivorship bias in one test: a name that leaves the universe has to stay
        # visible in the record, or a later backtest silently pretends it never existed.
        pit_store.record_universe(["AAA", "BBB", "CCC"],
                                  observed_at="2026-01-01T00:00:00+00:00")
        row = pit_store.record_universe(["AAA", "BBB", "DDD"],
                                        observed_at="2026-02-01T00:00:00+00:00")
        self.assertEqual(row["removed"], ["CCC"])
        self.assertEqual(row["added"], ["DDD"])

    def test_universe_as_of_reconstructs_historical_membership(self):
        pit_store.record_universe(["AAA", "CCC"], observed_at="2026-01-01T00:00:00+00:00")
        pit_store.record_universe(["AAA", "DDD"], observed_at="2026-02-01T00:00:00+00:00")
        self.assertEqual(pit_store.universe_as_of("2026-01-15"), ["AAA", "CCC"])
        self.assertEqual(pit_store.universe_as_of("2026-03-01"), ["AAA", "DDD"])


class StalenessTests(unittest.TestCase):
    def test_fields_past_their_ttl_are_reported(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        observed = {
            "price": (now - timedelta(hours=48)).isoformat(),       # TTL 24h -> stale
            "piotroski_f": (now - timedelta(days=30)).isoformat(),  # quarterly -> fine
        }
        stale = pit_store.stale_fields(observed, now=now)
        self.assertIn("price", stale)
        self.assertNotIn("piotroski_f", stale)

    def test_unparseable_timestamps_do_not_raise(self):
        self.assertEqual(pit_store.stale_fields({"price": "not-a-date"}), {})

    def test_freshness_report_flags_and_grades(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        rows = [
            {"ticker": "AAA", "data_fetched_at": now.isoformat()},
            {"ticker": "BBB", "data_fetched_at": (now - timedelta(hours=100)).isoformat()},
        ]
        report = pit_store.freshness_report(rows, now=now, stale_after_hours=36)
        self.assertEqual(report["stale_count"], 1)
        self.assertEqual(report["stale"][0]["ticker"], "BBB")
        self.assertIn(report["status"], ("degraded", "error"))

    def test_a_fully_fresh_dataset_reads_healthy(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        rows = [{"ticker": "AAA", "data_fetched_at": now.isoformat()}]
        self.assertEqual(pit_store.freshness_report(rows, now=now)["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
