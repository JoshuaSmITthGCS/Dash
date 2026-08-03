"""Canonical, point-in-time ETF/benchmark comparison contract (schema 4)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean, stdev

SCHEMA_VERSION = "4.0.0"
MODEL_VERSION = "etf-v2.0.0"
RANGES = ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX")


def _date(value):
    if hasattr(value, "date") and not isinstance(value, date):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def normalize_prices(rows, source="provider"):
    """Sort, de-duplicate and reject invalid adjusted prices.

    Input accepts mappings with date and adjusted_close (or Adj Close/Close). When a
    provider's auto-adjusted history is used, Close is the total-return-compatible field.
    """
    points = {}
    duplicate_dates = set()
    for row in rows or []:
        day = _date(row.get("date"))
        value = row.get("adjusted_close", row.get("Adj Close", row.get("Close")))
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not day or not math.isfinite(value) or value <= 0:
            continue
        if day in points:
            duplicate_dates.add(day)
        points[day] = value
    ordered = sorted(points.items())
    if not ordered:
        return []
    first = ordered[0][1]
    return [{
        "date": day,
        "adjusted_close": round(value, 8),
        "total_return_index": round(value / first, 8),
        "source": source,
        "quality_flags": (["duplicate_date_resolved"] if day in duplicate_dates else []),
    } for day, value in ordered]


def align_series(fund, benchmark):
    fund_by_date = {point["date"]: point for point in fund}
    benchmark_by_date = {point["date"]: point for point in benchmark}
    dates = sorted(fund_by_date.keys() & benchmark_by_date.keys())
    if not dates:
        return []
    fund_start = fund_by_date[dates[0]]["adjusted_close"]
    benchmark_start = benchmark_by_date[dates[0]]["adjusted_close"]
    fund_peak = benchmark_peak = relative_peak = 1.0
    aligned = []
    for day in dates:
        fund_index = fund_by_date[day]["adjusted_close"] / fund_start
        benchmark_index = benchmark_by_date[day]["adjusted_close"] / benchmark_start
        relative_index = fund_index / benchmark_index
        fund_peak = max(fund_peak, fund_index)
        benchmark_peak = max(benchmark_peak, benchmark_index)
        relative_peak = max(relative_peak, relative_index)
        aligned.append({
            "date": day,
            "fund_index": round(fund_index * 100, 8),
            "benchmark_index": round(benchmark_index * 100, 8),
            "relative_index": round(relative_index * 100, 8),
            "fund_drawdown": round((fund_index / fund_peak - 1) * 100, 8),
            "benchmark_drawdown": round((benchmark_index / benchmark_peak - 1) * 100, 8),
            "relative_drawdown": round((relative_index / relative_peak - 1) * 100, 8),
        })
    return aligned


def _returns(values):
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1]]


def _annualized(total_return, days):
    # A one-year trading window is often 364 calendar days because endpoints land on
    # adjacent weekdays. Treat >=350 days as annualizable, not as an unavailable metric.
    return (1 + total_return) ** (365.25 / days) - 1 if days >= 350 and total_return > -1 else None


def _capture(fund_returns, benchmark_returns, positive, minimum_samples=20):
    pairs = [(f, b) for f, b in zip(fund_returns, benchmark_returns) if (b > 0) == positive and b != 0]
    if len(pairs) < minimum_samples:
        return None, len(pairs)
    benchmark_mean = mean(pair[1] for pair in pairs)
    return (mean(pair[0] for pair in pairs) / benchmark_mean if benchmark_mean else None), len(pairs)


def calculate_metrics(series, benchmark_type="generic_market", *, tracking_metrics_approved=False,
                      capture_min_samples=20):
    if len(series) < 2:
        return None
    fund = [row["fund_index"] for row in series]
    benchmark = [row["benchmark_index"] for row in series]
    fund_returns, benchmark_returns = _returns(fund), _returns(benchmark)
    excess = [f - b for f, b in zip(fund_returns, benchmark_returns)]
    days = (datetime.fromisoformat(series[-1]["date"]) - datetime.fromisoformat(series[0]["date"])).days
    fund_total = fund[-1] / fund[0] - 1
    benchmark_total = benchmark[-1] / benchmark[0] - 1
    fund_mean, benchmark_mean = mean(fund_returns), mean(benchmark_returns)
    variance = sum((value - benchmark_mean) ** 2 for value in benchmark_returns) / max(1, len(benchmark_returns) - 1)
    covariance = sum((f - fund_mean) * (b - benchmark_mean) for f, b in zip(fund_returns, benchmark_returns)) / max(1, len(fund_returns) - 1)
    fund_sd = stdev(fund_returns) if len(fund_returns) > 1 else 0
    benchmark_sd = stdev(benchmark_returns) if len(benchmark_returns) > 1 else 0
    downside = [min(value, 0) for value in fund_returns]
    downside_dev = math.sqrt(mean(value * value for value in downside)) if downside else 0
    tracking_allowed = benchmark_type == "actual_index" or tracking_metrics_approved
    difference_label = "tracking_difference" if tracking_allowed else "relative_return_difference"
    fund_annualized = _annualized(fund_total, days)
    benchmark_annualized = _annualized(benchmark_total, days)
    tracking_difference = ((fund_annualized - benchmark_annualized)
                           if fund_annualized is not None and benchmark_annualized is not None
                           else fund_total - benchmark_total)
    metrics = {
        "fund_start_value": fund[0], "fund_end_value": fund[-1],
        "benchmark_start_value": benchmark[0], "benchmark_end_value": benchmark[-1],
        "fund_return": round(fund_total * 100, 6),
        "benchmark_return": round(benchmark_total * 100, 6),
        "excess_return": round((fund_total - benchmark_total) * 100, 6),
        "fund_annualized_return": None if fund_annualized is None else round(fund_annualized * 100, 6),
        "benchmark_annualized_return": None if benchmark_annualized is None else round(benchmark_annualized * 100, 6),
        difference_label: round(tracking_difference * 100, 6),
        "beta": round(covariance / variance, 6) if variance else None,
        "correlation": round(covariance / (fund_sd * benchmark_sd), 6) if fund_sd and benchmark_sd else None,
        "fund_max_drawdown": min(row["fund_drawdown"] for row in series),
        "benchmark_max_drawdown": min(row["benchmark_drawdown"] for row in series),
        "relative_max_drawdown": min(row["relative_drawdown"] for row in series),
        "sharpe": round(fund_mean / fund_sd * math.sqrt(252), 6) if fund_sd else None,
        "sortino": round(fund_mean / downside_dev * math.sqrt(252), 6) if downside_dev else None,
    }
    if tracking_allowed:
        metrics["tracking_error"] = round(stdev(excess) * math.sqrt(252) * 100, 6) if len(excess) > 1 else None
    up, up_count = _capture(fund_returns, benchmark_returns, True, capture_min_samples)
    down, down_count = _capture(fund_returns, benchmark_returns, False, capture_min_samples)
    metrics.update({
        "up_capture": None if up is None else round(up * 100, 6),
        "down_capture": None if down is None else round(down * 100, 6),
        "up_capture_sample_count": up_count,
        "down_capture_sample_count": down_count,
        "capture_minimum_samples": capture_min_samples,
    })
    return metrics


def _requested_start(key, end):
    if key == "MAX": return date.min
    if key == "YTD": return date(end.year, 1, 1)
    days = {"1M": 31, "3M": 92, "6M": 183, "1Y": 365, "3Y": 1096, "5Y": 1826}[key]
    return end - timedelta(days=days)


def build_contract(ticker, fund_rows, benchmark_rows, benchmark, generated_at=None):
    fund = normalize_prices(fund_rows)
    benchmark_points = normalize_prices(benchmark_rows)
    aligned = align_series(fund, benchmark_points)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    payload = {"schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
               "config_version": "etf-benchmarks-v1.0.0", "generated_at": generated_at,
               "ticker": ticker.upper(), "benchmark": {
                   "display_name": benchmark["benchmark_name"], "identifier": benchmark["benchmark_identifier"],
                   "ticker": benchmark.get("benchmark_ticker"), "type": benchmark["benchmark_type"],
                   "return_type": benchmark["return_type"], "currency": benchmark["currency"],
                   "hedging": benchmark["hedging"], "source": benchmark["source"],
                   "confidence": benchmark["confidence"],
                   "quality_label": "Actual index" if benchmark["benchmark_type"] == "actual_index" else (
                       "Investable proxy" if benchmark["benchmark_type"] == "investable_proxy" else "Generic market comparison")},
               "price_series": {"fund": fund, "benchmark": benchmark_points,
                                "return_basis": "provider_adjusted_close_total_return_compatible"},
               "chart_ranges": {}}
    if not aligned:
        payload["status"] = "unavailable"
        payload["reason_code"] = "NO_OVERLAPPING_DATES"
    else:
        payload["status"] = "success"
    end = date.fromisoformat(aligned[-1]["date"]) if aligned else date.today()
    for key in RANGES:
        requested = _requested_start(key, end)
        selected = [row for row in aligned if date.fromisoformat(row["date"]) >= requested]
        # Re-normalize every selected range to exactly 100.
        if selected:
            f0, b0 = selected[0]["fund_index"], selected[0]["benchmark_index"]
            selected = align_series(
                [{"date": r["date"], "adjusted_close": r["fund_index"] / f0} for r in selected],
                [{"date": r["date"], "adjusted_close": r["benchmark_index"] / b0} for r in selected])
        quality = []
        if len(selected) < 2: quality.append("INSUFFICIENT_OBSERVATIONS")
        if len(selected) > 1:
            gaps = [(date.fromisoformat(selected[i]["date"]) - date.fromisoformat(selected[i - 1]["date"])).days
                    for i in range(1, len(selected))]
            if max(gaps) > 10: quality.append("MATERIAL_MISSING_DATA_GAP")
        metrics = calculate_metrics(
            selected, benchmark["benchmark_type"],
            tracking_metrics_approved=bool(benchmark.get("tracking_metrics_approved", False)),
            capture_min_samples=int(benchmark.get("capture_ratio_minimum_samples", 20)))
        payload["chart_ranges"][key] = {
            "requested_start": None if key == "MAX" else requested.isoformat(),
            "actual_start": selected[0]["date"] if selected else None,
            "end": selected[-1]["date"] if selected else None,
            "observation_count": len(selected), "series": selected, "metrics": metrics,
            "confidence": round(benchmark["confidence"] * min(1, len(selected) / 60), 3),
            "quality_flags": quality,
            "status": "success" if len(selected) >= 2 else "unavailable",
            "reason_code": None if len(selected) >= 2 else "INSUFFICIENT_OBSERVATIONS",
        }
    return payload
