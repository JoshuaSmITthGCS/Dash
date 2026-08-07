import json
import os
import sys
from datetime import datetime, timedelta, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import validation.ic_harness as ic_harness_module
from validation import trading_calendar
from validation.ic_harness import (TARGET_FIELD, _forward_periods, _sector_residuals,
                                   append_refresh, build_report, evaluate_variant,
                                   read_snapshots)


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
    # Far enough back that all 24 forward windows close inside the committed session
    # calendar. A window running past the last observed session is correctly reported as
    # unfinished, which would silently cost this test a period.
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
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
            # 40 calendar days, not 31. A 21-session window spans up to ~33 calendar days
            # through a holiday-heavy stretch, so 31-day spacing leaves some windows
            # unfinished -- which is the drift this horizon correction exists to remove, and
            # not what this test is about.
            "recorded_at": (start + timedelta(days=40 * period)).isoformat(),
            "rows": rows,
        })
    summary = evaluate_variant(refreshes, "champion", 21)
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
    summary = evaluate_variant(refreshes, "champion", 21)
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
    summary = evaluate_variant(refreshes, "champion", 21)
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
    summary = evaluate_variant(refreshes, "champion", 21)
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


# --- forecast target: 63 trading sessions, sector-residual -------------------------------

def _refresh(refresh_id, recorded_at, rows):
    return {"refresh_id": refresh_id, "recorded_at": recorded_at, "rows": rows}


def _priced(ticker, score, price, sector=None):
    return {"ticker": ticker, "price": price, "scores": {"champion": score},
            "raw_metric_inputs": {"sector": sector} if sector else {}}


def test_the_horizon_is_counted_in_trading_sessions_not_calendar_days():
    """63 sessions and 91 calendar days are the same at the median and differ in general."""
    assert trading_calendar.calendar_days_for_sessions(63) == 91
    # Across a holiday-heavy start of year the same 63 sessions runs past 91 calendar days.
    assert trading_calendar.advance("2023-11-01", 63) > "2024-01-31"
    # And the drift is real rather than a rounding artifact.
    spans = {trading_calendar.sessions_between(start, trading_calendar.advance(start, 63))
             for start in ("2022-01-03", "2022-06-01", "2023-03-01", "2024-09-03")}
    assert spans == {63}


def test_a_window_that_has_not_finished_yields_no_period():
    """The label is only real once the full session count has elapsed."""
    last_session = trading_calendar.sessions()[-1]
    refreshes = [_refresh("a", f"{last_session}T12:00:00+00:00", [_priced("AAA", 60.0, 100.0)])]
    assert _forward_periods(refreshes, "champion", 63) == []


def test_period_records_the_session_horizon_it_actually_realized():
    refreshes = [
        _refresh("a", "2024-01-02T12:00:00+00:00", [_priced("AAA", 60.0, 100.0, "Tech"),
                                                    _priced("BBB", 40.0, 100.0, "Tech")]),
        _refresh("b", "2024-04-10T12:00:00+00:00", [_priced("AAA", 60.0, 110.0, "Tech"),
                                                    _priced("BBB", 40.0, 105.0, "Tech")]),
    ]
    periods = _forward_periods(refreshes, "champion", 63)

    assert len(periods) == 1
    assert periods[0]["horizon_sessions"] == 63
    # The realized window is at least the requested horizon -- snapshots land where they land,
    # so it can overshoot, but it can never be short.
    assert periods[0]["realized_sessions"] >= 63


def test_the_label_is_sector_residual_not_raw_return():
    rows = [
        {"ticker": "A", "score": 9.0, "forward_return": 0.10, "sector": "Tech"},
        {"ticker": "B", "score": 8.0, "forward_return": 0.20, "sector": "Tech"},
        {"ticker": "C", "score": 7.0, "forward_return": 0.30, "sector": "Tech"},
        {"ticker": "D", "score": 6.0, "forward_return": -0.10, "sector": "Utilities"},
        {"ticker": "E", "score": 5.0, "forward_return": 0.00, "sector": "Utilities"},
        {"ticker": "F", "score": 4.0, "forward_return": 0.10, "sector": "Utilities"},
    ]
    residualized = {row["ticker"]: row for row in _sector_residuals(rows)}

    # Tech mean is +0.20, Utilities mean is 0.00.
    assert abs(residualized["A"][TARGET_FIELD] - (-0.10)) < 1e-9
    assert abs(residualized["C"][TARGET_FIELD] - 0.10) < 1e-9
    assert abs(residualized["D"][TARGET_FIELD] - (-0.10)) < 1e-9
    assert all(row["residual_basis"] == "sector" for row in rows)


def test_the_best_raw_performer_can_be_the_worst_residual_performer():
    """The whole point: raw return mostly measures which sector moved."""
    rows = [
        {"ticker": "HOT", "score": 9.0, "forward_return": 0.25, "sector": "Energy"},
        {"ticker": "HOT2", "score": 8.0, "forward_return": 0.35, "sector": "Energy"},
        {"ticker": "HOT3", "score": 7.0, "forward_return": 0.45, "sector": "Energy"},
        {"ticker": "COLD", "score": 6.0, "forward_return": 0.05, "sector": "Staples"},
        {"ticker": "COLD2", "score": 5.0, "forward_return": -0.05, "sector": "Staples"},
        {"ticker": "COLD3", "score": 4.0, "forward_return": -0.15, "sector": "Staples"},
    ]
    residualized = {row["ticker"]: row for row in _sector_residuals(rows)}

    assert residualized["HOT"]["forward_return"] > residualized["COLD"]["forward_return"]
    assert residualized["HOT"][TARGET_FIELD] < residualized["COLD"][TARGET_FIELD]


def test_a_sector_with_too_few_peers_falls_back_to_the_universe_and_says_so():
    rows = [
        {"ticker": "A", "score": 9.0, "forward_return": 0.10, "sector": "Tech"},
        {"ticker": "B", "score": 8.0, "forward_return": 0.20, "sector": "Tech"},
        {"ticker": "C", "score": 7.0, "forward_return": 0.30, "sector": "Tech"},
        {"ticker": "LONE", "score": 6.0, "forward_return": 0.00, "sector": "Utilities"},
        {"ticker": "NOSECTOR", "score": 5.0, "forward_return": 0.40, "sector": None},
    ]
    residualized = {row["ticker"]: row for row in _sector_residuals(rows, minimum_peers=3)}

    assert residualized["A"]["residual_basis"] == "sector"
    assert residualized["LONE"]["residual_basis"] == "universe_fallback"
    assert residualized["NOSECTOR"]["residual_basis"] == "universe_fallback"


def test_report_preregisters_one_primary_horizon_and_labels_the_rest_diagnostic(tmp_path):
    append_refresh([scored_row()], refresh_id="run-1",
                   recorded_at="2026-08-05T12:00:00+00:00", universe={"AAA"}, root=tmp_path)
    target = build_report(read_snapshots(tmp_path))["forecast_target"]

    assert target["primary_horizon"] == "3M"
    assert target["primary_horizon_sessions"] == 63
    assert target["target"] == "residual_forward_return"
    assert target["horizon_basis"] == "trading_sessions"
    assert target["secondary_horizons_are_diagnostic_only"] is True
    assert "3M" not in target["secondary_horizons"]
    assert target["trading_calendar_available"] is True
