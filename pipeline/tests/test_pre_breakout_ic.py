import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import pre_breakout_pit_store as pbps  # noqa: E402
import pre_breakout_ic as pbic  # noqa: E402


def test_flat_weights_sum_to_one_across_all_fourteen_subfactors():
    assert abs(sum(pbic.FLAT_WEIGHTS.values()) - 1.0) < 1e-9
    assert len(pbic.FLAT_WEIGHTS) == 14


def test_zero_snapshots_reports_accumulating_with_no_number_published():
    with tempfile.TemporaryDirectory() as tmp:
        report = pbic.build_report(store_dir=tmp)
        assert report["composite"]["status"] == "accumulating"
        assert report["composite"]["mean_rank_ic"] is None
        assert report["attribution"]["status"] == "accumulating"
        assert report["snapshot_dates_recorded"] == 0


def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum():
    with tempfile.TemporaryDirectory() as tmp:
        tickers = "ABCDE"
        candidates = [{
            "ticker": t, "price": 100.0, "composite_z": score,
            "sub_scores": {"fundamental_inflection": {"subfactor_z": {"earnings_acceleration": score}}},
        } for t, score in zip(tickers, (1, 2, 3, 4, 5))]
        end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
        end_candidates = [{"ticker": t, "price": price, "composite_z": 0.0, "sub_scores": {}}
                          for t, price in zip(tickers, end_prices)]
        pbps.append_snapshot(candidates, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
        # 3 months plus a few days: comfortably past horizons_days['3M'] (91 calendar days).
        pbps.append_snapshot(end_candidates, recorded_at=datetime(2026, 4, 15, tzinfo=timezone.utc), store_dir=tmp)

        report = pbic.build_report(store_dir=tmp)
        assert report["snapshot_dates_recorded"] == 2
        assert report["composite"]["eligible_periods"] == 1
        assert report["composite"]["status"] == "accumulating"
        assert report["attribution"]["eligible_periods"] == 1
        assert report["attribution"]["metrics"]["earnings_acceleration"]["weight"] == pbic.FLAT_WEIGHTS["earnings_acceleration"]
