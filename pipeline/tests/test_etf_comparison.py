import math

from etf_comparison import align_series, build_contract, calculate_metrics, normalize_prices


BENCHMARK = {"benchmark_name": "Synthetic Index", "benchmark_identifier": "SYN",
             "benchmark_ticker": "SYN", "benchmark_type": "investable_proxy",
             "return_type": "total_return", "currency": "USD", "hedging": "not_applicable",
             "source": "test fixture", "confidence": 1.0}


def test_hand_calculated_synthetic_fixture():
    fund = [{"date": "2025-01-02", "adjusted_close": 100}, {"date": "2025-01-03", "adjusted_close": 110},
            {"date": "2025-01-06", "adjusted_close": 99}]
    benchmark = [{"date": "2025-01-02", "adjusted_close": 200}, {"date": "2025-01-03", "adjusted_close": 210},
                 {"date": "2025-01-06", "adjusted_close": 189}]
    series = align_series(normalize_prices(fund), normalize_prices(benchmark))
    assert series[1]["fund_index"] == 110
    assert series[1]["benchmark_index"] == 105
    assert math.isclose(series[1]["relative_index"], 104.76190476)
    assert series[2]["fund_drawdown"] == -10
    assert series[2]["benchmark_drawdown"] == -10
    metrics = calculate_metrics(series, "investable_proxy")
    assert metrics["fund_return"] == -1
    assert metrics["benchmark_return"] == -5.5
    assert metrics["excess_return"] == 4.5
    assert metrics["relative_return_difference"] == 4.5
    assert "tracking_error" not in metrics


def test_alignment_uses_intersection_and_resolves_duplicate_dates():
    fund = normalize_prices([{"date": "2025-01-02", "adjusted_close": 10},
                             {"date": "2025-01-02", "adjusted_close": 11},
                             {"date": "2025-01-03", "adjusted_close": None}])
    benchmark = normalize_prices([{"date": "2025-01-02", "adjusted_close": 20},
                                  {"date": "2025-01-04", "adjusted_close": 21}])
    assert fund[0]["quality_flags"] == ["duplicate_date_resolved"]
    assert len(align_series(fund, benchmark)) == 1


def test_no_overlap_is_explicit_and_generic_comparison_is_not_tracking_difference():
    generic = {**BENCHMARK, "benchmark_type": "generic_market"}
    payload = build_contract("ETF", [{"date": "2025-01-01", "adjusted_close": 10}],
                             [{"date": "2025-02-01", "adjusted_close": 20}], generic)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "NO_OVERLAPPING_DATES"
    series = align_series(normalize_prices([{"date": "2025-01-01", "adjusted_close": 10}, {"date": "2025-01-02", "adjusted_close": 11}]),
                          normalize_prices([{"date": "2025-01-01", "adjusted_close": 20}, {"date": "2025-01-02", "adjusted_close": 21}]))
    metrics = calculate_metrics(series, "generic_market")
    assert "tracking_difference" not in metrics
    assert "relative_return_difference" in metrics
