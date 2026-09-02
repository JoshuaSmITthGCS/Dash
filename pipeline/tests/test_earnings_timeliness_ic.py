import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import earnings_timeliness_pit_store as etps  # noqa: E402
import earnings_timeliness_ic as etic  # noqa: E402


def test_flat_weights_cover_all_fifteen_tactical_factors():
    assert len(etic.TACTICAL_WEIGHTS) == 15
    assert abs(sum(etic.TACTICAL_WEIGHTS.values()) - 1.0) < 1e-9


def test_zero_snapshots_reports_accumulating_with_no_number_published():
    with tempfile.TemporaryDirectory() as tmp:
        report = etic.build_report(store_dir=tmp)
        assert report["composite"]["status"] == "accumulating"
        assert report["composite"]["mean_rank_ic"] is None
        assert report["attribution"]["status"] == "accumulating"
        assert set(report["attribution"]["metrics"]) == set(etic.TACTICAL_WEIGHTS)


def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum():
    with tempfile.TemporaryDirectory() as tmp:
        tickers = "ABCDE"
        start = [{"ticker": t, "price": 100.0, "tactical_score": score,
                 "factors": {"revision_agreement": score}}
                for t, score in zip(tickers, (10, 20, 30, 40, 50))]
        end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
        end = [{"ticker": t, "price": price, "tactical_score": 0.0, "factors": {}}
              for t, price in zip(tickers, end_prices)]
        etps.append_snapshot(start, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
        # 1 month plus slack: comfortably past horizons_days['1M'] (30 calendar days).
        etps.append_snapshot(end, recorded_at=datetime(2026, 2, 15, tzinfo=timezone.utc), store_dir=tmp)

        report = etic.build_report(store_dir=tmp)
        assert report["snapshot_dates_recorded"] == 2
        assert report["composite"]["eligible_periods"] == 1
        assert report["composite"]["status"] == "accumulating"
        assert report["attribution"]["eligible_periods"] == 1
        assert report["attribution"]["metrics"]["revision_agreement"]["weight"] == etic.TACTICAL_WEIGHTS["revision_agreement"]
