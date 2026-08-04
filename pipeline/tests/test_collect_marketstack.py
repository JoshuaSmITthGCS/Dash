import json
import os
import tempfile
import unittest
from unittest.mock import Mock

import collect_marketstack as module
from marketstack import MarketstackPlanRestricted


class TopSymbolsTests(unittest.TestCase):
    def test_takes_the_rank_sorted_research_list_then_coverage_tail(self):
        payload = {
            "research": [{"ticker": "AAA"}, {"ticker": "BBB"}],
            "portfolio_coverage": [{"ticker": "BBB"}, {"ticker": "CCC"}],
        }
        self.assertEqual(module.top_symbols(payload, limit=100), ["AAA", "BBB", "CCC"])

    def test_respects_the_limit(self):
        payload = {"research": [{"ticker": f"T{i}"} for i in range(10)]}
        self.assertEqual(len(module.top_symbols(payload, limit=3)), 3)

    def test_empty_payload_returns_no_symbols(self):
        self.assertEqual(module.top_symbols(None), [])


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_dir = module.MARKETSTACK_DIR
        module.MARKETSTACK_DIR = os.path.join(self.tmp, "marketstack")

    def tearDown(self):
        module.MARKETSTACK_DIR = self._orig_dir

    def test_collect_prefers_intraday_and_appends_point_in_time(self):
        client = Mock()
        client.intraday.return_value = [{"symbol": "AAPL", "last": 200.0}]

        summary = module.collect(["AAPL"], client=client, observed_at="2026-08-04T21:00:00+00:00")

        self.assertEqual(summary["mode"], "intraday")
        self.assertEqual(summary["collected"], 1)
        client.eod_latest.assert_not_called()
        with open(os.path.join(module.MARKETSTACK_DIR, module.COLLECTED)) as handle:
            row = json.loads(handle.readline())
        self.assertEqual(row["symbol"], "AAPL")
        self.assertEqual(row["mode"], "intraday")
        self.assertEqual(row["observed_at"], "2026-08-04T21:00:00+00:00")

    def test_collect_falls_back_to_eod_latest_when_intraday_is_plan_restricted(self):
        client = Mock()
        client.intraday.side_effect = MarketstackPlanRestricted("nope")
        client.eod_latest.return_value = [{"symbol": "AAPL", "close": 199.5}]

        summary = module.collect(["AAPL"], client=client)

        self.assertEqual(summary["mode"], "eod_latest")
        self.assertEqual(summary["collected"], 1)

    def test_depth_reports_rows_modes_and_last_observed(self):
        self.assertEqual(module.depth(), {"rows": 0, "modes": [], "last_observed": None})
        client = Mock()
        client.intraday.return_value = [{"symbol": "AAPL"}]
        module.collect(["AAPL"], client=client, observed_at="2026-08-04T12:00:00+00:00")
        module.collect(["AAPL"], client=client, observed_at="2026-08-04T21:00:00+00:00")

        info = module.depth()

        self.assertEqual(info["rows"], 2)
        self.assertEqual(info["modes"], ["intraday"])
        self.assertEqual(info["last_observed"], "2026-08-04T21:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
