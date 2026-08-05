import json
import os
import sys
from datetime import datetime, timedelta, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from validation.ic_harness import append_refresh, build_report, evaluate_variant, read_snapshots


def scored_row(ticker="AAA", champion=60.0, challenger=62.0, price=100.0):
    return {
        "ticker": ticker,
        "price": price,
        "score": champion,
        "confidence": 0.8,
        "fundamental_detail": {"forward_pe": 80.0, "categories": {"valuation": 80.0}},
        "fundamental_categories": {"valuation": 80.0},
        "score_variants": {
            "champion": {"score": champion, "confidence": 0.8},
            "challenger": {
                "score": challenger,
                "confidence": 0.8,
                "normalized_metric_scores": {"forward_pe": 75.0},
                "fundamental_categories": {"valuation": 75.0},
            },
        },
    }


def test_refresh_snapshot_is_append_only_and_idempotent(tmp_path):
    result = append_refresh(
        [scored_row()], refresh_id="run-1", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
    )
    repeated = append_refresh(
        [scored_row()], refresh_id="run-1", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
    )
    rows = read_snapshots(tmp_path)
    assert result["appended"] == 1
    assert repeated["appended"] == 0
    assert len(rows) == 1
    assert rows[0]["scores"] == {"champion": 60.0, "challenger": 62.0}
    assert rows[0]["universe_membership"] is True


def test_one_snapshot_renders_zero_realized_periods(tmp_path):
    append_refresh(
        [scored_row()], refresh_id="run-1", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, root=tmp_path,
    )
    report = build_report(read_snapshots(tmp_path))
    summary = report["variants"]["champion"]["1M"]
    assert summary["periods_accumulated"] == 0
    assert summary["icir"] is None
    assert summary["status_message"] == "accumulating, 0 of 24 periods"
    assert report["reconstructed_history"]["included"] is False


def test_icir_unlocks_only_after_twenty_four_monthly_periods():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    refreshes = []
    prices = {f"T{index}": 100.0 for index in range(10)}
    for period in range(25):
        rows = []
        for index in range(10):
            score = float(index)
            rows.append({
                "ticker": f"T{index}", "price": prices[f"T{index}"],
                "scores": {"champion": score, "challenger": score},
            })
            prices[f"T{index}"] *= 1 + index * 0.001 + period * 0.00001
        refreshes.append({
            "refresh_id": f"run-{period}",
            "recorded_at": (start + timedelta(days=31 * period)).isoformat(),
            "rows": rows,
        })
    summary = evaluate_variant(refreshes, "champion", 30)
    assert summary["periods_accumulated"] == 24
    assert summary["status"] == "eligible"
    assert summary["standard_error"] is not None
    assert summary["confidence_interval_95"][0] is not None
    assert summary["probable_lookahead_flags"]
    assert set(summary["bucket_returns"]) == {"5", "10"}
    assert summary["long_short_top_minus_bottom_quintile"]["cost_bps"] == 10.0
    assert summary["mean_top_quintile_turnover"] == 0.0
    assert summary["mean_rank_stability"] == 1.0


def test_snapshot_jsonl_contains_required_reproducibility_fields(tmp_path):
    append_refresh(
        [scored_row()], refresh_id="run-1", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, root=tmp_path,
    )
    path = next(tmp_path.glob("*.jsonl"))
    row = json.loads(path.read_text().splitlines()[0])
    for field in (
        "raw_metric_inputs", "normalized_metric_scores", "category_scores", "confidence",
        "modifiers", "scores", "model_version", "config_hash", "universe_membership",
    ):
        assert field in row
