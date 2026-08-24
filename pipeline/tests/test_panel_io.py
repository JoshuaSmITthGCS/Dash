import gzip
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import panel_io


PANEL = {"periods": [{"date": "2026-01-01", "scores": {"AAA": 71.0}}],
         "leg_weights": {"valuation": 1.0}}


class PanelIoTests(unittest.TestCase):
    def test_plain_json_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "panel.json")
            panel_io.save_panel(path, PANEL)
            self.assertEqual(panel_io.load_panel(path), PANEL)
            # Written compact, not indented -- size is the whole reason this module exists.
            self.assertNotIn("\n  ", open(path).read())

    def test_gz_round_trip_and_actual_compression(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "panel.json.gz")
            panel_io.save_panel(path, PANEL)
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), PANEL)
            self.assertEqual(panel_io.load_panel(path), PANEL)

    def test_a_json_path_falls_back_to_its_gz_sibling(self):
        # The committed-panel case: readers are configured with the .json path, the repo
        # carries only the .gz -- the fallback is what keeps every caller working unchanged.
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "panel.json")
            panel_io.save_panel(path + ".gz", PANEL)
            self.assertEqual(panel_io.load_panel(path), PANEL)

    def test_a_fresh_local_json_wins_over_a_stale_committed_gz(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "panel.json")
            panel_io.save_panel(path + ".gz", {"stale": True})
            panel_io.save_panel(path, PANEL)
            self.assertEqual(panel_io.load_panel(path), PANEL)

    def test_neither_file_returns_none(self):
        self.assertIsNone(panel_io.load_panel("/nonexistent/panel.json"))


if __name__ == "__main__":
    unittest.main()
