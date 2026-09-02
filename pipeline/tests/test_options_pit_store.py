import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import options_pit_store as ops  # noqa: E402


CANDIDATE = {
    "ticker": "AAPL", "strategy": "buy_call", "score": 72.0, "price": 200.0,
    "expiration": "2026-01-15", "days_to_expiration": 10,
    "legs": [{"action": "buy", "option_type": "call", "strike": 205.0, "mid": 3.5}],
    "standardized_factors": {"iv_value": 0.4, "liquidity": 1.1, "trend_strength": -0.2},
}


class BuildRowsTests(unittest.TestCase):
    def test_a_complete_candidate_is_captured(self):
        rows = ops.build_rows([CANDIDATE])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["ticker"], "AAPL")
        self.assertEqual(row["strike"], 205.0)
        self.assertEqual(row["premium"], 3.5)
        self.assertEqual(row["expiration"], "2026-01-15")
        self.assertEqual(row["factors"], {"iv_value": 0.4, "liquidity": 1.1, "trend_strength": -0.2})

    def test_a_candidate_missing_standardized_factors_records_an_empty_dict_not_a_dropped_row(self):
        rows = ops.build_rows([{**CANDIDATE, "standardized_factors": None}])
        self.assertEqual(rows[0]["factors"], {})

    def test_a_candidate_missing_legs_is_excluded(self):
        self.assertEqual(ops.build_rows([{**CANDIDATE, "legs": []}]), [])

    def test_a_candidate_missing_a_score_is_excluded(self):
        self.assertEqual(ops.build_rows([{**CANDIDATE, "score": None}]), [])

    def test_an_empty_list_produces_no_rows(self):
        self.assertEqual(ops.build_rows([]), [])
        self.assertEqual(ops.build_rows(None), [])


class AppendAndLoadTests(unittest.TestCase):
    def test_a_snapshot_round_trips_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            count = ops.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(count, 1)
            self.assertEqual(ops.snapshot_dates(tmp), ["2026-01-01"])
            self.assertEqual(ops.load_snapshot("2026-01-01", tmp)[0]["ticker"], "AAPL")

    def test_a_second_run_on_the_same_date_replaces_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
            ops.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            ops.append_snapshot([CANDIDATE], recorded_at=recorded, store_dir=tmp)
            self.assertEqual(len(ops.load_snapshot("2026-01-01", tmp)), 1)

    def test_all_rows_pools_every_recorded_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops.append_snapshot([CANDIDATE], recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
            ops.append_snapshot([{**CANDIDATE, "ticker": "MSFT"}],
                               recorded_at=datetime(2026, 1, 2, tzinfo=timezone.utc), store_dir=tmp)
            tickers = sorted(row["ticker"] for row in ops.all_rows(tmp))
            self.assertEqual(tickers, ["AAPL", "MSFT"])


if __name__ == "__main__":
    unittest.main()
