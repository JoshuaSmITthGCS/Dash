"""pipeline/pit_store.py's append_snapshot(): observation writing, restatement detection,
and the config_hash provenance field (B9: which formula version produced a past observation).

Separate from test_pit_store.py, which covers the unrelated sharded EDGAR-facts store in
pit_fundamentals_store.py.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pit_store


class AppendSnapshotConfigHashTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="pit-store-")
        self._original = pit_store.PIT_DIR
        pit_store.PIT_DIR = self.directory

    def tearDown(self):
        pit_store.PIT_DIR = self._original
        shutil.rmtree(self.directory, ignore_errors=True)

    def _read_observations(self):
        return pit_store._read(pit_store.OBSERVATIONS)

    def test_config_hash_is_omitted_when_not_supplied(self):
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 200.0}], source="test")
        rows = self._read_observations()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("config_hash", rows[0])

    def test_config_hash_is_recorded_on_every_observation_when_supplied(self):
        pit_store.append_snapshot(
            [{"ticker": "AAPL", "price": 200.0}, {"ticker": "MSFT", "price": 300.0}],
            source="test", config_hash="abc123",
        )
        rows = self._read_observations()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["config_hash"] == "abc123" for row in rows))

    def test_a_later_run_under_a_different_config_hash_still_detects_the_restatement(self):
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 200.0}],
                                  source="test", config_hash="config-a")
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 205.0}],
                                  source="test", config_hash="config-b")
        rows = self._read_observations()
        self.assertEqual([row["config_hash"] for row in rows], ["config-a", "config-b"])
        revisions = pit_store._read(pit_store.REVISIONS)
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["previous"], 200.0)
        self.assertEqual(revisions[0]["current"], 205.0)

    def test_observations_and_revisions_are_sharded_by_observation_month(self):
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 200.0}],
                                  observed_at="2026-08-31T20:00:00+00:00")
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 205.0}],
                                  observed_at="2026-09-01T20:00:00+00:00")
        observation_shards = sorted(os.listdir(os.path.join(self.directory, "observations")))
        self.assertEqual(observation_shards, ["2026-08.jsonl", "2026-09.jsonl"])
        self.assertEqual(os.listdir(os.path.join(self.directory, "revisions")), ["2026-09.jsonl"])
        self.assertFalse(os.path.exists(os.path.join(self.directory, pit_store.OBSERVATIONS)))
        # Reads span shards, oldest month first, so as_of and diffing are unchanged.
        self.assertEqual([row["values"]["price"] for row in self._read_observations()], [200.0, 205.0])
        self.assertEqual(pit_store.as_of("AAPL", "2026-08-31")["values"]["price"], 200.0)

    def test_a_legacy_single_file_is_still_read_and_migrates_into_shards(self):
        legacy = os.path.join(self.directory, pit_store.OBSERVATIONS)
        with open(legacy, "w") as handle:
            handle.write('{"ticker": "AAPL", "observed_at": "2026-08-02T00:00:00+00:00", '
                         '"values": {"price": 190.0}}\n')
        pit_store.append_snapshot([{"ticker": "AAPL", "price": 200.0}],
                                  observed_at="2026-09-02T00:00:00+00:00")
        self.assertEqual(len(pit_store._read(pit_store.REVISIONS)), 1)
        self.assertEqual(pit_store.migrate_legacy(), {pit_store.OBSERVATIONS: 2})
        self.assertFalse(os.path.exists(legacy))
        self.assertEqual([row["values"]["price"] for row in self._read_observations()], [190.0, 200.0])
        self.assertEqual(pit_store.migrate_legacy(), {})
