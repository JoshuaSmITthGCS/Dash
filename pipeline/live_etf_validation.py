"""Controlled cross-asset ETF validation; writes staging diagnostics only."""

import hashlib
import json
import os
from datetime import datetime, timezone

from build_etf_comparisons import _rows
from common import CONFIG_DIR, DATA_DIR
from etf_comparison import build_contract

CASES = {"VXUS": "international_equity", "TLT": "bond", "GLD": "commodity",
         "TQQQ": "leveraged", "AVUV": "young", "HEFA": "currency_hedged",
         "SGOV": "sparse_history", "VTI": "proxy_benchmark"}


def run(output=None):
    import yfinance as yf
    with open(os.path.join(CONFIG_DIR, "etf_benchmarks.json")) as handle: registry = json.load(handle)
    generated_at = datetime.now(timezone.utc).isoformat()
    results = []
    for ticker, case in CASES.items():
        benchmark = {**registry["default"], **registry["funds"][ticker]}
        try:
            fund = yf.Ticker(ticker).history(period="max", auto_adjust=True, actions=True)
            peer = yf.Ticker(benchmark["benchmark_ticker"]).history(period="max", auto_adjust=True, actions=True)
            contract = build_contract(ticker, _rows(fund), _rows(peer), benchmark, generated_at)
            one_year = contract["chart_ranges"]["1Y"]
            metrics = one_year.get("metrics") or {}
            honest_proxy = (benchmark["benchmark_type"] == "actual_index"
                            or ("tracking_difference" not in metrics and "tracking_error" not in metrics))
            checks = {"overlap_or_explicit_unavailable": contract["status"] in {"success", "unavailable"},
                      "proxy_label_honest": honest_proxy,
                      "adjusted_total_return_basis": contract["price_series"]["return_basis"].startswith("provider_adjusted_close"),
                      "capture_sample_gate": (metrics.get("up_capture") is None
                                              or metrics.get("up_capture_sample_count", 0) >= metrics.get("capture_minimum_samples", 20))}
            results.append({"ticker": ticker, "case": case, "status": "pass" if all(checks.values()) else "fail",
                            "benchmark": contract["benchmark"], "contract_status": contract["status"],
                            "one_year": {"observation_count": one_year["observation_count"], "metrics": metrics,
                                         "quality_flags": one_year["quality_flags"]}, "checks": checks})
        except Exception as error:
            results.append({"ticker": ticker, "case": case, "status": "fail",
                            "reason_code": type(error).__name__, "message": str(error)[:500]})
    payload = {"schema_version": "1.0.0", "model_version": "etf-v2.0.0", "generated_at": generated_at,
               "run_id": hashlib.sha256(generated_at.encode()).hexdigest()[:16], "production_outputs_replaced": False,
               "results": results, "summary": {"passed": sum(r["status"] == "pass" for r in results),
                                                "failed": sum(r["status"] != "pass" for r in results)}}
    output = output or os.path.join(DATA_DIR, "validation", "live_etf_validation.json")
    os.makedirs(os.path.dirname(output), exist_ok=True); temporary = f"{output}.tmp"
    with open(temporary, "w") as handle: json.dump(payload, handle, indent=2, allow_nan=False); handle.write("\n")
    os.replace(temporary, output)
    print(json.dumps(payload["summary"], sort_keys=True))
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run()["summary"]["failed"] == 0 else 2)
