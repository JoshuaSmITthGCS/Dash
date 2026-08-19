import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import validation.ic_harness as ic_harness_module
from validation.ic_harness import (MixedCoverageRegimeError, append_refresh, build_report,
                                   evaluate_variant, evaluate_variant_sessions, read_snapshots,
                                   sector_residual_returns, snapshot_row)
from validation.trading_calendar import TradingCalendar


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
        "raw_metric_inputs", "normalized_metric_scores", "category_scores", "data_coverage",
        "modifiers", "scores", "model_version", "config_hash", "universe_membership",
    ):
        assert field in row
    assert set(row["modifiers"]["champion"]["all_points"]) == {
        "sector_valuation", "short_interest", "liquidity", "expectations",
        "macro_regime", "insider_activity", "customer_concentration_risk",
        "geographic_concentration", "institutional_13f", "congressional_buying",
    }


def _weekday_calendar(start, days):
    sessions = []
    current = start
    while len(sessions) < days:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return TradingCalendar(sessions)


def test_sector_residual_returns_subtracts_the_peer_group_mean():
    rows = [
        {"ticker": "A", "sector": "Technology", "forward_return": 0.10},
        {"ticker": "B", "sector": "Technology", "forward_return": 0.20},
        {"ticker": "C", "sector": "Technology", "forward_return": 0.30},
        {"ticker": "D", "sector": "Technology", "forward_return": 0.00},
    ]
    labeled = sector_residual_returns(rows, minimum_peers=2)
    by_ticker = {row["ticker"]: row for row in labeled}
    # A's peers are B, C, D (excluding itself): mean = (0.20+0.30+0.00)/3 = 0.1667
    assert round(by_ticker["A"]["sector_residual_return"], 4) == round(0.10 - (0.20 + 0.30 + 0.00) / 3, 4)
    assert by_ticker["A"]["sector_residual_fallback"] is False


def test_sector_residual_falls_back_to_universe_mean_for_a_thin_sector():
    rows = [
        {"ticker": "A", "sector": "Utilities", "forward_return": 0.10},
        {"ticker": "B", "sector": "Technology", "forward_return": 0.20},
        {"ticker": "C", "sector": "Technology", "forward_return": 0.30},
        {"ticker": "D", "sector": "Technology", "forward_return": 0.00},
    ]
    labeled = sector_residual_returns(rows, minimum_peers=2)
    by_ticker = {row["ticker"]: row for row in labeled}
    # A is the only Utilities name (0 peers < minimum_peers=2), so it falls back to the
    # equal-weight mean of every *other* name: (0.20+0.30+0.00)/3.
    assert by_ticker["A"]["sector_residual_fallback"] is True
    assert round(by_ticker["A"]["sector_residual_return"], 4) == round(0.10 - (0.20 + 0.30 + 0.00) / 3, 4)
    # A well-populated sector never falls back.
    assert by_ticker["B"]["sector_residual_fallback"] is False


def test_missing_sector_always_falls_back_to_the_universe_mean():
    rows = [
        {"ticker": "A", "sector": None, "forward_return": 0.10},
        {"ticker": "B", "sector": "Technology", "forward_return": 0.20},
        {"ticker": "C", "sector": "Technology", "forward_return": 0.30},
        {"ticker": "D", "sector": "Technology", "forward_return": 0.00},
    ]
    labeled = sector_residual_returns(rows, minimum_peers=2)
    by_ticker = {row["ticker"]: row for row in labeled}
    assert by_ticker["A"]["sector_residual_fallback"] is True


def test_evaluate_variant_sessions_uses_a_trading_session_horizon_not_calendar_days():
    calendar = _weekday_calendar(date(2024, 1, 1), 400)
    start_date = calendar.sessions[0]
    # Ten trading sessions after start_date lands mid the-following-week; a naive
    # calendar-day version of a "10 trading day" horizon (e.g. +14 calendar days) would
    # pick a different, later refresh as the match.
    ten_sessions_later = calendar.add_sessions(start_date, 10)
    just_under = ten_sessions_later - timedelta(days=1)

    refreshes = [
        {
            "refresh_id": "start",
            "recorded_at": datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            "rows": [
                {"ticker": "A", "price": 100.0, "scores": {"champion": 1.0},
                 "raw_metric_inputs": {"sector": "Technology"}},
                {"ticker": "B", "price": 100.0, "scores": {"champion": 2.0},
                 "raw_metric_inputs": {"sector": "Technology"}},
                {"ticker": "C", "price": 100.0, "scores": {"champion": 3.0},
                 "raw_metric_inputs": {"sector": "Technology"}},
            ],
        },
        {
            # Deliberately one calendar day short of the 10-session target: must NOT match.
            "refresh_id": "too-early",
            "recorded_at": datetime.combine(just_under, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            "rows": [
                {"ticker": "A", "price": 999.0, "scores": {"champion": 1.0}},
                {"ticker": "B", "price": 999.0, "scores": {"champion": 2.0}},
                {"ticker": "C", "price": 999.0, "scores": {"champion": 3.0}},
            ],
        },
        {
            "refresh_id": "target",
            "recorded_at": datetime.combine(ten_sessions_later, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            "rows": [
                {"ticker": "A", "price": 110.0, "scores": {"champion": 1.0}},
                {"ticker": "B", "price": 120.0, "scores": {"champion": 2.0}},
                {"ticker": "C", "price": 130.0, "scores": {"champion": 3.0}},
            ],
        },
    ]
    summary = evaluate_variant_sessions(refreshes, "champion", 10, calendar)
    assert summary["periods_accumulated"] == 1
    ic = summary["monthly_rank_ic"][0]
    assert ic is not None


def _regime_refresh(refresh_id, recorded_at, regime, prices):
    return {
        "refresh_id": refresh_id, "recorded_at": recorded_at,
        "rows": [{"ticker": ticker, "price": price, "scores": {"champion": float(index + 1)},
                 "coverage_regime": regime}
                for index, (ticker, price) in enumerate(prices.items())],
    }


def test_evaluate_variant_raises_on_mixed_coverage_regimes():
    refreshes = [
        _regime_refresh("r1", "2026-01-01T00:00:00+00:00", "pre_enrichment_ladder",
                        {"A": 100.0, "B": 100.0}),
        _regime_refresh("r2", "2026-02-01T00:00:00+00:00", "enrichment_ladder_v1",
                        {"A": 110.0, "B": 120.0}),
    ]
    try:
        evaluate_variant(refreshes, "champion", 30)
        assert False, "expected MixedCoverageRegimeError"
    except MixedCoverageRegimeError as exc:
        assert "pre_enrichment_ladder" in str(exc)
        assert "enrichment_ladder_v1" in str(exc)


def test_evaluate_variant_sessions_raises_on_mixed_coverage_regimes():
    calendar = _weekday_calendar(date(2024, 1, 1), 400)
    refreshes = [
        _regime_refresh("r1", datetime.combine(calendar.sessions[0], datetime.min.time(),
                                               tzinfo=timezone.utc).isoformat(),
                        "pre_enrichment_ladder", {"A": 100.0, "B": 100.0}),
        _regime_refresh("r2", datetime.combine(calendar.sessions[20], datetime.min.time(),
                                               tzinfo=timezone.utc).isoformat(),
                        "enrichment_ladder_v1", {"A": 110.0, "B": 120.0}),
    ]
    try:
        evaluate_variant_sessions(refreshes, "champion", 10, calendar)
        assert False, "expected MixedCoverageRegimeError"
    except MixedCoverageRegimeError:
        pass


def test_evaluate_variant_does_not_raise_when_every_refresh_shares_one_regime():
    refreshes = [
        _regime_refresh("r1", "2026-01-01T00:00:00+00:00", "enrichment_ladder_v1",
                        {"A": 100.0, "B": 100.0}),
        _regime_refresh("r2", "2026-02-01T00:00:00+00:00", "enrichment_ladder_v1",
                        {"A": 110.0, "B": 120.0}),
    ]
    evaluate_variant(refreshes, "champion", 30)  # must not raise


def test_a_row_with_no_coverage_regime_at_all_defaults_to_pre_ladder_not_unknown():
    refreshes = [
        {"refresh_id": "r1", "recorded_at": "2026-01-01T00:00:00+00:00",
         "rows": [{"ticker": "A", "price": 100.0, "scores": {"champion": 1.0}}]},
        _regime_refresh("r2", "2026-02-01T00:00:00+00:00", "pre_enrichment_ladder", {"A": 110.0}),
    ]
    evaluate_variant(refreshes, "champion", 30)  # must not raise: both are pre_enrichment_ladder


def test_snapshot_row_defaults_coverage_regime_when_absent():
    projected = snapshot_row(scored_row(), refresh_id="r1", recorded_at="2026-01-01T00:00:00+00:00",
                             data_as_of="2026-01-01T00:00:00+00:00", universe=(), published=(),
                             model_version="v1", config_hash="hash")
    assert projected["coverage_regime"] == "pre_enrichment_ladder"


def test_snapshot_row_carries_an_explicit_coverage_regime():
    row = {**scored_row(), "coverage_regime": "enrichment_ladder_v1"}
    projected = snapshot_row(row, refresh_id="r1", recorded_at="2026-01-01T00:00:00+00:00",
                             data_as_of="2026-01-01T00:00:00+00:00", universe=(), published=(),
                             model_version="v1", config_hash="hash")
    assert projected["coverage_regime"] == "enrichment_ladder_v1"


def test_build_report_publishes_a_primary_session_based_target(monkeypatch):
    calendar = _weekday_calendar(date(2024, 1, 1), 400)
    monkeypatch.setattr(ic_harness_module, "default_calendar", lambda: calendar)
    report = build_report([])
    assert report["primary_horizon"] == "3M"
    assert report["primary_target"] == "sector_residual_return_over_trading_sessions"
    assert set(report["primary_variants"]["champion"]) == {"1M", "3M", "6M", "12M"}


# --- unavailable provider coverage is not neutral evidence ---------------------------------

def _first_snapshot(path):
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
    modifiers = _first_snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "unavailable"
    assert modifiers["availability"]["macro_regime"] == "available"
    # The numeric contract is unchanged, so nothing reading all_points breaks.
    assert modifiers["all_points"]["insider_activity"] == 0.0


def test_healthy_sec_provider_marks_insider_modifier_available(tmp_path):
    result = append_refresh(
        [scored_row()], refresh_id="live-sec", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
        source_status={"sec_form4": {"status": "healthy"}, "fred": {"status": "healthy"}},
    )
    availability = _first_snapshot(result["path"])["modifiers"]["champion"]["availability"]

    assert availability["insider_activity"] == "available"


def test_absent_source_status_defaults_provider_backed_modifiers_to_unavailable(tmp_path):
    """No provider-health map means we cannot claim the provider answered."""
    result = append_refresh(
        [scored_row()], refresh_id="no-status", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
    )
    availability = _first_snapshot(result["path"])["modifiers"]["champion"]["availability"]

    assert availability["insider_activity"] == "unavailable"
    assert availability["macro_regime"] == "unavailable"
    # Modifiers computed from data the pipeline already holds stay available.
    assert availability["short_interest"] == "available"


def test_a_modifier_that_actually_fired_is_available_even_if_its_provider_reads_dark(tmp_path):
    """Evidence on the row outranks a run-level status flag."""
    row = scored_row()
    row["modifiers"] = {"applied": {"insider_activity": 2.5}, "total": 2.5}
    result = append_refresh(
        [row], refresh_id="fired", recorded_at="2026-08-05T12:00:00+00:00",
        universe={"AAA"}, published={"AAA"}, root=tmp_path,
        source_status={"sec_form4": {"status": "unavailable"}},
    )
    modifiers = _first_snapshot(result["path"])["modifiers"]["champion"]

    assert modifiers["availability"]["insider_activity"] == "available"
    assert modifiers["all_points"]["insider_activity"] == 2.5


# --- deflation uses the whole research programme's trial count -----------------------------

def test_deflation_trial_count_comes_from_the_experiment_registry():
    """Understating trials is the standard way a deflated Sharpe gets re-inflated."""
    from experiment_registry import total_variants_tested

    assert ic_harness_module.research_trial_count() == total_variants_tested()
    assert ic_harness_module.research_trial_count() > ic_harness_module.CONFIG[
        "shadow_strategy_trials"]


def test_trial_count_is_a_floor_never_a_reduction():
    assert ic_harness_module.research_trial_count() >= ic_harness_module.CONFIG[
        "shadow_strategy_trials"]
