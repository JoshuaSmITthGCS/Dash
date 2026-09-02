import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

from validation_framework import append_immutable_snapshot  # noqa: E402

import swing_ic as sic  # noqa: E402
import swing_pit_store as sps  # noqa: E402


def _snapshot(tmp, as_of, rows):
    append_immutable_snapshot(tmp, "swing", as_of, rows)


class DatedSnapshotsTests(unittest.TestCase):
    def test_reads_every_immutable_snapshot_sorted_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            _snapshot(tmp, "2026-01-02", [{"ticker": "A", "signal": 1.0, "price": 10.0}])
            _snapshot(tmp, "2026-01-01", [{"ticker": "A", "signal": 0.5, "price": 9.0}])
            snapshots = sic._dated_snapshots(os.path.join(tmp, "swing"))
            self.assertEqual([snap["date"] for snap in snapshots], ["2026-01-01", "2026-01-02"])

    def test_an_empty_or_missing_store_reports_no_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sic._dated_snapshots(os.path.join(tmp, "does-not-exist")), [])


class SwingIcTests(unittest.TestCase):
    def test_zero_snapshots_reports_accumulating_with_no_number_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = sic.build_report(store_dir=os.path.join(tmp, "swing"),
                                      attribution_store_dir=os.path.join(tmp, "attribution"))
            metric = report["metrics"][sic.GRADED_METRIC]
            self.assertEqual(metric["status"], "accumulating")
            self.assertIsNone(metric["mean_rank_ic"])
            self.assertEqual(report["snapshot_dates_recorded"], 0)

    def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows1 = [{"ticker": t, "signal": signal, "price": 100.0, "rank": rank + 1, "weight": 0.2}
                    for rank, (t, signal) in enumerate(zip("ABCDE", (1.6, 1.2, 0.8, 0.4, 0.1)))]
            rows2 = [{"ticker": t, "signal": 0.0, "price": price, "rank": 1, "weight": 0.2}
                    for t, price in zip("ABCDE", (130.0, 105.0, 115.0, 100.0, 90.0))]
            _snapshot(tmp, "2026-01-01", rows1)
            _snapshot(tmp, "2026-01-20", rows2)  # 19 days later, clears the 14-day horizon

            report = sic.build_report(store_dir=os.path.join(tmp, "swing"),
                                      attribution_store_dir=os.path.join(tmp, "attribution"))
            metric = report["metrics"][sic.GRADED_METRIC]
            self.assertEqual(report["snapshot_dates_recorded"], 2)
            self.assertEqual(metric["eligible_periods"], 1)
            self.assertEqual(metric["status"], "accumulating")
            self.assertIsNone(metric["mean_rank_ic"])

    def test_a_pair_short_of_the_horizon_contributes_no_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"ticker": "A", "signal": 1.0, "price": 100.0, "rank": 1, "weight": 1.0}]
            _snapshot(tmp, "2026-01-01", rows)
            _snapshot(tmp, "2026-01-05", [{"ticker": "A", "signal": 0.0, "price": 110.0, "rank": 1, "weight": 1.0}])
            report = sic.build_report(store_dir=os.path.join(tmp, "swing"),
                                      attribution_store_dir=os.path.join(tmp, "attribution"))
            self.assertEqual(report["metrics"][sic.GRADED_METRIC]["eligible_periods"], 0)


class SwingAttributionTests(unittest.TestCase):
    def test_zero_attribution_snapshots_reports_accumulating(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = sic.build_report(store_dir=os.path.join(tmp, "swing"),
                                      attribution_store_dir=os.path.join(tmp, "attribution"))
            self.assertEqual(report["attribution"]["status"], "accumulating")
            self.assertEqual(set(report["attribution"]["metrics"]), set(sic.SWING_WEIGHTS))

    def test_a_leg_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            attribution_dir = os.path.join(tmp, "attribution")
            tickers = "ABCDE"
            start = [{"ticker": t, "composite_z": score, "price": 100.0,
                     "legs": {"pead_drift": {"z": score}}}
                    for t, score in zip(tickers, (1, 2, 3, 4, 5))]
            end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
            end = [{"ticker": t, "composite_z": 0.0, "price": price, "legs": {}}
                  for t, price in zip(tickers, end_prices)]
            sps.append_snapshot(start, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=attribution_dir)
            sps.append_snapshot(end, recorded_at=datetime(2026, 1, 20, tzinfo=timezone.utc), store_dir=attribution_dir)

            report = sic.build_report(store_dir=os.path.join(tmp, "swing"), attribution_store_dir=attribution_dir)
            self.assertEqual(report["attribution"]["eligible_periods"], 1)
            self.assertEqual(report["attribution"]["status"], "accumulating")
            self.assertEqual(report["attribution"]["metrics"]["pead_drift"]["weight"], sic.SWING_WEIGHTS["pead_drift"])


if __name__ == "__main__":
    unittest.main()
