"""pipeline/pit_store.py's append_snapshot(): observation writing, restatement detection,
and the config_hash provenance field (B9: which formula version produced a past observation).

Separate from test_pit_store.py, which covers the unrelated sharded EDGAR-facts store in
pit_fundamentals_store.py.
"""
import json
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
        path = os.path.join(self.directory, pit_store.OBSERVATIONS)
        with open(path) as handle:
            return [json.loads(line) for line in handle]

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
        revisions_path = os.path.join(self.directory, pit_store.REVISIONS)
        with open(revisions_path) as handle:
            revisions = [json.loads(line) for line in handle]
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["previous"], 200.0)
        self.assertEqual(revisions[0]["current"], 205.0)
