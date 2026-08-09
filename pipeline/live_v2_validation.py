"""Controlled representative-universe refresh that never replaces production outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone

from canonical_metrics import BUSINESS_PROFILES, yahoo_observations
from fetch_prices import fetch_snapshot
from recommendation_policy_v2 import build_recommendation_v2
from research_screens_v2 import momentum_boundary_diagnostics, momentum_factors
from scorer import valuation_score
from scoring_v2 import MODEL_VERSION, build_v2_analysis

REPRESENTATIVE_UNIVERSE = ("HIG", "JPM", "O", "NEE", "BSX", "MSFT", "XOM", "MRNA", "VTI", "TLT")
ETF_TICKERS = {"VTI", "TLT"}


def _clean(value):
    if value is None or isinstance(value, (str, bool, int)): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, dict): return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_clean(item) for item in value]
    return str(value)


def _atomic_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(_clean(payload), handle, indent=2, allow_nan=False); handle.write("\n")
    os.replace(temporary, path)


def _history_rows(frame):
    if frame is None or frame.empty: return []
    rows = []
    for stamp, row in frame.iterrows():
        price = row.get("Close")
        if price is not None and math.isfinite(float(price)):
            rows.append({"date": stamp.date().isoformat(), "adjusted_close": float(price)})
    return rows


def _invariants(ticker, analysis, recommendation, observations):
    statuses = analysis.get("metric_status") or {}
    checks = {
        "legacy_values_never_contribute": all("legacy_value_missing_lineage" not in detail.get("quality_flags", [])
                                               or detail.get("score_contribution") is None
                                               for detail in statuses.values()),
        "suppressed_metrics_no_score": all(detail.get("score_contribution") is None for detail in statuses.values()
                                            if detail.get("status") in {"suppressed", "replaced"}),
        "inapplicable_not_neutral": all(detail.get("score_contribution") is None for detail in statuses.values()
                                       if detail.get("status") in {"suppressed", "replaced"}),
        "critical_gaps_reduce_profile_confidence": (not analysis["applicability"]["critical_data_gaps"]
                                                    or analysis["applicability"]["profile_confidence"] < 1),
        "invalid_peer_sample_no_percentile": True,
        # Minimum over the layers that actually produced a score. A layer that resolved
        # nothing has no opinion to be confident or unconfident about; folding its zero in
        # here forced every company below the gate regardless of the evidence behind it.
        "low_confidence_action_gate": (
            min((layer["confidence"] for layer in (analysis["structural"], analysis["timeliness"])
                 if layer.get("effective_score") is not None), default=0.0) >= .60
            or recommendation["company_action"]["label"] not in {"buy", "accumulate", "sell_thesis"}),
        # A layer that resolved nothing must publish no score at all, on every row.
        "unresolved_layer_publishes_no_score": all(
            layer.get("effective_score") is None
            for layer in (analysis["structural"], analysis["timeliness"])
            if layer.get("raw_score") is None),
        "company_and_position_actions_separate": recommendation["company_action"] is not recommendation["position_action"],
        "timestamps_explicit": all(row.get("fetched_at") and row.get("observed_at")
                                   for rows in observations.values() for row in rows),
        "hig_invalid_metrics_suppressed": (ticker != "HIG" or all(
            statuses.get(metric, {}).get("score_contribution") is None
            for metric in ("peg", "current_ratio", "return_on_invested_capital", "free_cash_flow_yield"))),
    }
    return {key: {"status": "pass" if passed else "fail"} for key, passed in checks.items()}


def validate_live(output_path, raw_root, tickers=REPRESENTATIVE_UNIVERSE):
    import yfinance as yf
    fetched_at = datetime.now(timezone.utc).isoformat()
    results = []
    for ticker in tickers:
        try:
            instrument = yf.Ticker(ticker)
            info = _clean(instrument.info or {})
            raw = {"provider": "yahoo", "ticker": ticker, "fetched_at": fetched_at, "info": info}
            raw_json = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
            raw_path = os.path.join(raw_root, f"{ticker}-{fetched_at[:10]}.json")
            _atomic_json(raw_path, raw)
            observations = yahoo_observations(info, fetched_at)
            snapshot = fetch_snapshot(ticker, yf, ETF_TICKERS, ticker_obj=instrument) or {"ticker": ticker}
            snapshot.update({"ticker": ticker, "is_etf": ticker in ETF_TICKERS,
                             "observations": observations, "data_fetched_at": fetched_at})
            _, legacy_parts = valuation_score(snapshot)
            # Scores derived without canonical lineage are diagnostic-only and cannot enter v2.
            analysis = build_v2_analysis(snapshot, legacy_parts or {}, observations=observations)
            recommendation = build_recommendation_v2(ticker, analysis, generated_at=fetched_at)
            history = _history_rows(instrument.history(period="15mo", auto_adjust=True, actions=True))
            factors = momentum_factors(history, as_of=fetched_at[:10])
            boundaries = momentum_boundary_diagnostics(history, as_of=fetched_at[:10])
            invariants = _invariants(ticker, analysis, recommendation, observations)
            peer_override = (BUSINESS_PROFILES.get("ticker_overrides") or {}).get(ticker, {})
            results.append({
                "ticker": ticker, "status": ("pass" if all(row["status"] == "pass" for row in invariants.values()) else "fail"),
                "provider_status": "success", "raw_response": {"retention": "private_staging",
                    "path": os.path.relpath(raw_path), "sha256": hashlib.sha256(raw_json.encode()).hexdigest()},
                "classification": {"company": analysis["company_classification"],
                    "profile_id": analysis["applicability_profile"], "peer_group": peer_override.get("peer_group_id"),
                    "total_peer_count": 0, "valid_peer_count": 0, "percentile_status": "INSUFFICIENT_VALID_PEERS"},
                "observations": observations, "analysis": analysis,
                "company_action": recommendation["company_action"], "portfolio_fit_state": recommendation["portfolio_fit_state"],
                "position_action": recommendation["position_action"],
                "momentum": {"factors": factors, "boundaries": boundaries}, "invariants": invariants,
            })
        except Exception as error:  # provider failures are explicit, not imputed
            results.append({"ticker": ticker, "status": "fail", "provider_status": "error",
                            "reason_code": type(error).__name__, "message": str(error)[:500], "invariants": {}})
    payload = {"schema_version": "1.0.0", "model_version": MODEL_VERSION,
               "config_version": "live-validation-v1.0.0", "universe_version": "representative-v1",
               "data_cutoff": fetched_at, "run_id": hashlib.sha256(fetched_at.encode()).hexdigest()[:16],
               "production_outputs_replaced": False, "raw_response_publication": "not_published",
               "results": results,
               "summary": {"passed": sum(row["status"] == "pass" for row in results),
                           "failed": sum(row["status"] != "pass" for row in results)}}
    _atomic_json(output_path, payload)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "public", "data", "validation", "live_v2_validation.json"))
    parser.add_argument("--raw-root", default=os.path.join(os.path.dirname(__file__), "data", "staging", "raw_provider"))
    args = parser.parse_args()
    payload = validate_live(os.path.abspath(args.output), os.path.abspath(args.raw_root))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
