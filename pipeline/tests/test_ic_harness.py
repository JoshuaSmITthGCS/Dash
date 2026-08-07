import json
import os
import sys
from datetime import datetime, timedelta, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import validation.ic_harness as ic_harness_module
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


def test_cost_model_defaults_to_flat_and_reproduces_the_old_constant_rate():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    refreshes = []
    for period in range(2):
        rows = [{
            "ticker": f"T{index}", "price": 100.0 + period,
            "scores": {"champion": float(index)},
            "raw_metric_inputs": {"average_dollar_volume": 1_000_000.0},
        } for index in range(10)]
        refreshes.append({
            "refresh_id": f"run-{period}",
            "recorded_at": (start + timedelta(days=31 * period)).isoformat(),
            "rows": rows,
        })
    summary = evaluate_variant(refreshes, "champion", 30)
    assert ic_harness_module.CONFIG.get("cost_model", "flat") == "flat"
    assert summary["long_short_top_minus_bottom_quintile"]["cost_model"] == "flat"
    assert summary["long_short_top_minus_bottom_quintile"]["cost_bps"] == 10.0


def test_tiered_cost_model_prices_illiquid_names_above_the_flat_rate(monkeypatch):
    monkeypatch.setitem(ic_harness_module.CONFIG, "cost_model", "tiered")
    monkeypatch.setitem(ic_harness_module.CONFIG, "cost_scenario", "stress")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    refreshes = []
    for period in range(2):
        rows = [{
            "ticker": f"T{index}", "price": 100.0 + period,
            "scores": {"champion": float(index)},
            # $1M/day median volume sits in costs.py's "illiquid" tier (< $5M).
            "raw_metric_inputs": {"average_dollar_volume": 1_000_000.0},
        } for index in range(10)]
        refreshes.append({
            "refresh_id": f"run-{period}",
            "recorded_at": (start + timedelta(days=31 * period)).isoformat(),
            "rows": rows,
        })
    summary = evaluate_variant(refreshes, "champion", 30)
    long_short = summary["long_short_top_minus_bottom_quintile"]
    assert long_short["cost_model"] == "tiered"
    assert long_short["cost_bps"] > 10.0


def test_tiered_cost_model_falls_back_to_flat_rate_when_volume_is_untracked(monkeypatch):
    monkeypatch.setitem(ic_harness_module.CONFIG, "cost_model", "tiered")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    refreshes = []
    for period in range(2):
        rows = [{
            "ticker": f"T{index}", "price": 100.0 + period,
            "scores": {"champion": float(index)},
        } for index in range(10)]
        refreshes.append({
            "refresh_id": f"run-{period}",
            "recorded_at": (start + timedelta(days=31 * period)).isoformat(),
            "rows": rows,
        })
    summary = evaluate_variant(refreshes, "champion", 30)
    assert summary["long_short_top_minus_bottom_quintile"]["cost_bps"] == 10.0


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
    assert set(row["modifiers"]["champion"]["all_points"]) == {
        "sector_valuation", "short_interest", "liquidity", "expectations",
        "macro_regime", "insider_activity",
    }


# --- unavailable provider coverage is not neutral evidence ---------------------------------

def _snapshot(path):
    with open(path) as handle:
        return json.loads(handle.readline())


def test_dark_sec_provider_marks_insider_modifier_unavailable_not_neutral(tmp_path):
    """A dark Form 4 layer must not be snapshotted as reviewed-and-neutral insider activity.

    ``all_points`` records 0.0 for every modifier that did not fire, which is correct for a
    modifier the pipeline evaluated. Without a separate availability channel, an SEC layer
    that was never reachable is indistinguishable in the immutable record from one that was
    reviewed and found neutral -- and later validation would grade it as real evidence.
    """
    result = append_refresh(
        [scored_row()], refresh_id="dark-sec", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
        source_status={"sec_form4": {"status": "unavailable"}, "fred": {"status": "healthy"}},
    )
    modifiers = _snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "unavailable"
    assert modifiers["availability"]["macro_regime"] == "available"
    # The numeric contract is unchanged, so nothing downstream that reads all_points breaks.
    assert modifiers["all_points"]["insider_activity"] == 0.0


def test_healthy_sec_provider_marks_insider_modifier_available(tmp_path):
    result = append_refresh(
        [scored_row()], refresh_id="live-sec", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
        source_status={"sec_form4": {"status": "healthy"}, "fred": {"status": "healthy"}},
    )
    modifiers = _snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "available"


def test_absent_source_status_defaults_provider_backed_modifiers_to_unavailable(tmp_path):
    """No provider-health map means we cannot claim the provider answered."""
    result = append_refresh(
        [scored_row()], refresh_id="no-status", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
    )
    modifiers = _snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "unavailable"
    assert modifiers["availability"]["macro_regime"] == "unavailable"
    # Modifiers computed from data the pipeline already holds stay available.
    assert modifiers["availability"]["short_interest"] == "available"


def test_a_modifier_that_actually_fired_is_available_even_if_its_provider_reads_dark(tmp_path):
    """Evidence on the row outranks a run-level status flag."""
    row = scored_row()
    row["modifiers"] = {"applied": {"insider_activity": 2.5}, "total": 2.5}
    result = append_refresh(
        [row], refresh_id="fired", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
        source_status={"sec_form4": {"status": "unavailable"}},
    )
    modifiers = _snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "available"
    assert modifiers["all_points"]["insider_activity"] == 2.5
