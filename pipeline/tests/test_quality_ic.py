import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import quality_pit_store as qps  # noqa: E402
import quality_ic as qic  # noqa: E402


def test_zero_snapshots_reports_accumulating_with_no_number_published():
    with tempfile.TemporaryDirectory() as tmp:
        report = qic.build_report(store_dir=tmp)
        assert report["composite"]["status"] == "accumulating"
        assert report["composite"]["mean_rank_ic"] is None
        assert report["attribution"]["status"] == "accumulating"
        assert set(report["attribution"]["metrics"]) == set(qic.QUALITY_WEIGHTS)


def test_a_period_far_enough_apart_is_counted_but_stays_ineligible_below_the_minimum():
    with tempfile.TemporaryDirectory() as tmp:
        tickers = "ABCDE"
        start = [{"ticker": t, "price": 100.0, "fundamental_categories": {"profitability": score}}
                for t, score in zip(tickers, (10, 20, 30, 40, 50))]
        end_prices = (130.0, 105.0, 115.0, 100.0, 140.0)
        # Needs at least one category value to be recorded at all (the pit store's own
        # inclusion rule, same as theme/pre-breakout/momentum's) - the value itself is
        # irrelevant here since only its price is read on the "end" side of a period.
        end = [{"ticker": t, "price": price, "fundamental_categories": {"profitability": 0.0}}
              for t, price in zip(tickers, end_prices)]
        qps.append_snapshot(start, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
        # 3 months plus slack: comfortably past horizons_days['3M'] (91 calendar days).
        qps.append_snapshot(end, recorded_at=datetime(2026, 4, 15, tzinfo=timezone.utc), store_dir=tmp)

        report = qic.build_report(store_dir=tmp)
        assert report["snapshot_dates_recorded"] == 2
        assert report["composite"]["eligible_periods"] == 1
        assert report["composite"]["status"] == "accumulating"
        assert report["attribution"]["eligible_periods"] == 1
        assert report["attribution"]["metrics"]["profitability"]["weight"] == qic.QUALITY_WEIGHTS["profitability"]


def test_composite_score_matches_quality_scores_own_renormalized_formula():
    # profitability .35, financial_health .30 present; accounting_quality/capital_allocation
    # missing -> renormalize over the two present weights, exactly what quality_score() does.
    leg_scores = {"profitability": 80.0, "financial_health": 60.0}
    from evaluation import composite_score
    result = composite_score(leg_scores, qic.QUALITY_WEIGHTS)
    expected = (80.0 * 0.35 + 60.0 * 0.30) / (0.35 + 0.30)
    assert abs(result - expected) < 1e-9
