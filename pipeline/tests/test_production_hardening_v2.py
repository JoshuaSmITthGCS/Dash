import json
from datetime import date

import pytest

from canonical_metrics import classify_profile
from estimate_snapshots import estimate_revision_diagnostics, normalize_estimates
from etf_comparison import align_series, calculate_metrics, normalize_prices
from research_screens_v2 import (industry_relative_returns, momentum_boundary_diagnostics,
                                 momentum_correlation_diagnostics)
from validation_framework import (convert_annual_risk_free, deflated_sharpe_ratio,
                                  rank_diagnostics, untouched_holdout)


def monthly_rows():
    rows = []
    for year in (2023, 2024):
        for month in range(1, 13):
            rows.append({"date": date(year, month, 28).isoformat(), "adjusted_close": len(rows) + 100})
    return rows


def test_exact_momentum_boundaries_are_auditable():
    result = momentum_boundary_diagnostics(monthly_rows(), "2024-12-31")
    assert result["momentum_12_1"]["starting_month_end"] == "2023-12-28"
    assert result["momentum_12_1"]["ending_month_end"] == "2024-11-28"
    assert result["momentum_12_1"]["skipped_months"] == ["2024-12"]
    assert result["momentum_12_1"]["included_return_months"] == 11
    assert result["momentum_12_7"]["ending_month_end"] == "2024-05-28"
    assert result["momentum_12_7"]["included_return_months"] == 5
    assert result["momentum_6_1"]["starting_month_end"] == "2024-06-28"


def test_industry_benchmark_is_leave_one_out_and_minimum_sampled():
    rows = [{"ticker": ticker, "peer_group": "software", "momentum_12_1": value}
            for ticker, value in zip("ABCDE", (1, 2, 3, 4, 100))]
    result = industry_relative_returns(rows, minimum_peer_count=4)
    assert result["E"]["industry_return"] == 2.5
    assert result["E"]["peer_count"] == 4
    assert result["E"]["leave_one_out"] is True


def test_correlated_momentum_family_is_detected_and_capped():
    rows = [{"factors": {field: index for field in ("momentum_12_1", "momentum_12_7", "momentum_6_1")}}
            for index in range(10)]
    result = momentum_correlation_diagnostics(rows, fields=["momentum_12_1", "momentum_12_7", "momentum_6_1"])
    assert result["average_pairwise_correlation"] == 1
    assert result["cap_applied"] is True
    assert result["effective_factor_count"] == 1


@pytest.mark.parametrize("ticker,snapshot,profile", [
    ("HIG", {"ticker": "HIG", "sector": "Financial Services"}, "diversified_insurer"),
    ("JPM", {"ticker": "JPM"}, "bank"), ("O", {"ticker": "O"}, "net_lease_reit"),
    ("NEE", {"ticker": "NEE"}, "utility"), ("XOM", {"ticker": "XOM"}, "commodity_producer"),
    ("MRNA", {"ticker": "MRNA", "sector": "Healthcare", "industry": "Biotechnology", "profit_margin": -.2}, "pre_profit_biotechnology"),
    ("BIO", {"ticker": "BIO", "sector": "Healthcare", "industry": "Biotechnology", "profit_margin": .1}, "profitable_biotechnology"),
])
def test_representative_profile_classification(ticker, snapshot, profile):
    assert classify_profile(snapshot) == profile


def test_proxy_etf_never_emits_tracking_metrics_and_capture_is_sample_gated():
    fund = normalize_prices([{"date": f"2025-01-{day:02}", "adjusted_close": 100 + day} for day in range(1, 10)])
    bench = normalize_prices([{"date": f"2025-01-{day:02}", "adjusted_close": 200 + day} for day in range(1, 10)])
    metrics = calculate_metrics(align_series(fund, bench), "investable_proxy")
    assert "tracking_difference" not in metrics and "tracking_error" not in metrics
    assert metrics["up_capture"] is None
    actual = calculate_metrics(align_series(fund, bench), "actual_index", capture_min_samples=2)
    assert "tracking_difference" in actual and "tracking_error" in actual


def test_estimates_remain_forward_only_without_real_history():
    contract = normalize_estimates({"current_year": {"eps_consensus": 5}}, "fixture", "2026-08-03T00:00:00Z")
    snapshot = {"observed_at": "2026-08-03T00:00:00+00:00", "estimates": contract}
    result = estimate_revision_diagnostics([snapshot], as_of="2026-08-03T00:00:00Z")
    assert result["status"] == "FORWARD_COLLECTION_ONLY"
    assert result["revision_30d"] is None


def test_rank_ic_risk_free_holdout_and_deflated_sharpe():
    periods = [{"date": "2026-01-31", "rows": [{"score": x, "forward_return": x / 100} for x in range(1, 11)]}]
    result = rank_diagnostics(periods)
    assert result["mean_rank_ic"] == 1
    assert result["quantile_monotonic"] is True
    assert convert_annual_risk_free(.05, 12) > 0
    assert untouched_holdout(list(range(10)), 2)["holdout"] == [8, 9]
    assert deflated_sharpe_ratio(1, 36, trials=10)["trials"] == 10


def test_shadow_strategy_contract_declares_both_comparison_modes():
    with open("pipeline/config/shadow_strategies.json") as handle: payload = json.load(handle)
    assert set(payload["comparison_modes"]) == {"signal_only", "full_strategy"}
    # Named rather than counted: a bare length check fires on any addition without saying
    # what changed, and passes for a rename that silently drops a declared strategy.
    assert set(payload["strategies"]) == {
        "legacy_production_model", "v2_structural_model", "structural_timeliness_model",
        "momentum_sleeve", "quality_value_sleeve", "swing_only",
        "political_institutional_only", "combined_model", "SPY_benchmark",
        "equal_weight_eligible_universe", "manual_external_rankings",
    }
