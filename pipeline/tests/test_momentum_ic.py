import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import momentum_pit_store as mps  # noqa: E402
import momentum_ic as mic  # noqa: E402


def test_zero_snapshots_reports_accumulating_with_no_number_published():
    with tempfile.TemporaryDirectory() as tmp:
        report = mic.build_report(store_dir=tmp)
        assert report["composite"]["status"] == "accumulating"
        assert report["composite"]["mean_rank_ic"] is None
        assert report["attribution"]["status"] == "accumulating"
        assert report["snapshot_dates_recorded"] == 0


def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum():
    with tempfile.TemporaryDirectory() as tmp:
        tickers = "ABCDE"
        candidates = [{"ticker": t, "price": 100.0, "score": score,
                      "standardized_factors": {"momentum_12_1": score}}
                     for t, score in zip(tickers, (1, 2, 3, 4, 5))]
        end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
        end_candidates = [{"ticker": t, "price": price, "score": 0.0, "standardized_factors": {}}
                          for t, price in zip(tickers, end_prices)]
        mps.append_snapshot(candidates, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
        # 1 month plus slack: comfortably past horizons_days['1M'] (30 calendar days).
        mps.append_snapshot(end_candidates, recorded_at=datetime(2026, 2, 15, tzinfo=timezone.utc), store_dir=tmp)

        report = mic.build_report(store_dir=tmp)
        assert report["snapshot_dates_recorded"] == 2
        assert report["composite"]["eligible_periods"] == 1
        assert report["composite"]["status"] == "accumulating"
        assert report["attribution"]["eligible_periods"] == 1
        assert report["attribution"]["metrics"]["momentum_12_1"]["weight"] == mic.MOMENTUM_WEIGHTS["momentum_12_1"]
