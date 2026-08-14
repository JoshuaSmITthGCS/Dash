"""Publish the research evidence to the UI, in the shape a reader needs to judge the score.

The pipeline produces a directory of report artifacts; none of them reach the product. A user
looking at "Research Score: 84" has no way to find out that the score has never been calibrated,
that no benchmark in a 14-ETF set is beaten with significant alpha, or that the book turns over
65% a month. That asymmetry -- a confident-looking number in front, all the caveats in JSON
files behind -- is the thing this fixes.

This aggregates the committed reports into one artifact for `/screens/validation`. It reads
only; it computes nothing, so the page cannot disagree with the reports it summarizes. A missing
report is reported as missing rather than defaulted, because "we did not measure this" and "this
measured zero" must not look the same on screen.

Usage: python pipeline/build_research_evidence.py
Output: public/data/validation/research_evidence.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from common import load_json, save_json  # noqa: E402

REPORTS_DIR = os.path.join(HERE, "reports")
PUBLIC_NAME = "validation/research_evidence.json"

SOURCES = {
    "benchmarks": "benchmark_alpha_regressions.json",
    "diagnostics": "strategy_diagnostics.json",
    "costs": "cost_sensitivity.json",
    "calibration": "score_calibration.json",
    "experiments": "experiment_registry.json",
    "enrichment": "enrichment_bias.json",
    "factor_regression": "factor_regression_p0.json",
}


def _read(name):
    path = os.path.join(REPORTS_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _missing(name):
    return {"status": "not_generated", "reason": f"pipeline/reports/{name} has not been built"}


def benchmark_panel(report):
    if not report:
        return _missing(SOURCES["benchmarks"])
    rows = []
    for name, leg in report["benchmarks"].items():
        regression = leg.get("strategy_versus_this_benchmark") or {}
        rows.append({
            "name": name,
            "description": leg.get("description"),
            "cagr": leg.get("cagr"),
            "volatility": leg.get("volatility"),
            "sharpe": leg.get("sharpe"),
            "max_drawdown": leg.get("max_drawdown"),
            "beta": regression.get("beta"),
            "annualized_alpha_pct": regression.get("annualized_alpha_pct"),
            "newey_west_t_statistic": regression.get("newey_west_t_statistic"),
            "significant": abs(regression.get("newey_west_t_statistic") or 0) >= 2.0,
        })
    rows.sort(key=lambda row: -(row["cagr"] or 0))
    return {
        "status": "measured",
        "window": report.get("window"),
        "strategy": report.get("strategy"),
        "rows": rows,
        "summary": report.get("summary"),
    }


def factor_panel(report):
    if not report:
        return _missing(SOURCES["factor_regression"])
    regression = report.get("six_factor_regression") or report.get("regression") or {}
    coefficients = regression.get("coefficients") or {}
    return {
        "status": "measured" if coefficients else "not_generated",
        "months": regression.get("observations") or regression.get("months_count"),
        "r_squared": regression.get("r_squared"),
        "annualized_alpha_pct": regression.get("annualized_alpha_pct"),
        "loadings": [
            {
                "factor": name,
                "estimate": block.get("estimate"),
                "newey_west_t_statistic": block.get("newey_west_t_statistic"),
                "significant": abs(block.get("newey_west_t_statistic") or 0) >= 2.0,
            }
            for name, block in coefficients.items()
        ],
    }


def diagnostics_panel(report):
    if not report:
        return _missing(SOURCES["diagnostics"])
    return {
        "status": "measured",
        "unit_of_account": report.get("unit_of_account"),
        "sample": report.get("sample"),
        "expectancy": report.get("expectancy"),
        "profit_factor": report.get("profit_factor"),
        "streaks": report.get("streaks"),
        "risk_adjusted": report.get("risk_adjusted"),
        "turnover": report.get("turnover"),
        "turnover_adjusted_return": report.get("turnover_adjusted_return"),
        "regime_definitions": report.get("regime_definitions"),
        "regime_attribution": report.get("regime_attribution"),
    }


def cost_panel(report):
    if not report:
        return _missing(SOURCES["costs"])
    scenarios = report.get("scenarios") or {}
    flat = report.get("realized_flat_10bps") or {}
    return {
        "status": "measured",
        "turnover": report.get("turnover"),
        "realized_flat_10bps": flat,
        "scenarios": [
            {"scenario": name,
             "cost_bps": block.get("cost_bps"),
             "total_cost": block.get("total_cost"),
             "drag_vs_realized_flat": block.get("cost_drag_vs_realized_flat_10bps")}
            for name, block in scenarios.items()
        ],
        "per_name_liquidity_legs": report.get("per_name_liquidity_legs"),
        "never_present_gross_as_net": report.get("never_present_gross_as_net"),
    }


def calibration_panel(report):
    if not report:
        return _missing(SOURCES["calibration"])
    return {
        "status": report.get("status"),
        "observations": report.get("observations"),
        "target": report.get("target"),
        "horizon_sessions": report.get("horizon_sessions"),
        "fixed_score_bands": report.get("fixed_score_bands"),
        "publishable": report.get("publishable_to_confidence_detail"),
        "what_would_populate_this": report.get("what_would_populate_this"),
    }


def experiment_panel(report):
    if not report:
        return _missing(SOURCES["experiments"])
    return {
        "status": "measured",
        "summary": {
            "experiments": report.get("total_experiments"),
            "total_variants_tested": report.get("total_variants_tested"),
            "by_decision": report.get("by_decision"),
            "promoted_to_champion": [item["id"] for item in report.get("experiments", [])
                                     if item.get("decision") == "PROMOTE"],
        },
        "experiments": [
            {key: item.get(key) for key in
             ("id", "hypothesis", "category", "result", "decision", "reason",
              "number_of_variants_tested")}
            for item in report.get("experiments", [])
        ],
    }


def enrichment_panel(report):
    if not report:
        return _missing(SOURCES["enrichment"])
    comparison = report.get("full_universe_comparison") or {}
    return {
        "status": "measured",
        "coverage_by_collection": report.get("coverage_by_collection"),
        "enriched_vs_non_enriched": report.get("enriched_vs_non_enriched"),
        "unconstrained_comparison_status": comparison.get("status"),
        "method": report.get("method"),
    }


def build_report():
    loaded = {key: _read(name) for key, name in SOURCES.items()}
    advisor = load_json("advisor.json") or {}
    ic = load_json(os.path.join("validation", "ic_validation.json")) or {}
    settings = load_json("settings.json", from_config=True) or {}
    validation = settings.get("validation") or {}
    primary_horizon = ic.get("primary_horizon") or validation.get("primary_horizon")
    primary_sessions = (validation.get("horizons_sessions") or {}).get(primary_horizon)
    forecast_target = None
    if ic.get("primary_target"):
        forecast_target = {
            "definition": ic["primary_target"],
            "primary_horizon": primary_horizon,
            "primary_horizon_sessions": primary_sessions,
        }
    calibration = calibration_panel(loaded["calibration"])
    return {
        "schema_version": 1,
        "generated_at": advisor.get("generated_at"),
        "model_version": (advisor.get("run_manifest") or {}).get("model_version"),
        "code_commit_hash": (advisor.get("run_manifest") or {}).get("code_commit_hash"),
        "config_hash": (advisor.get("run_manifest") or {}).get("config_hash"),
        "headline": {
            # The one sentence a reader needs before they trust a score.
            "validation_status": ("no calibration history yet"
                                  if calibration.get("status") != "measured"
                                  else "calibrated"),
            "ic_periods_accumulated": ((ic.get("variants") or {}).get("champion", {})
                                       .get("3M", {}).get("periods_accumulated", 0)),
            "ic_periods_required": ((ic.get("variants") or {}).get("champion", {})
                                    .get("3M", {}).get("minimum_periods")),
            "forecast_target": forecast_target,
            "score_is_not_a_probability": (
                "The Research Score ranks attractiveness. Confidence measures how reliable "
                "that rank's evidence is. Neither is a probability that the stock rises, and "
                "no score bucket has enough closed forward windows to state one."),
        },
        "benchmarks": benchmark_panel(loaded["benchmarks"]),
        "factor_exposures": factor_panel(loaded["factor_regression"]),
        "strategy_diagnostics": diagnostics_panel(loaded["diagnostics"]),
        "costs": cost_panel(loaded["costs"]),
        "calibration": calibration,
        "experiments": experiment_panel(loaded["experiments"]),
        "enrichment_bias": enrichment_panel(loaded["enrichment"]),
    }


def main():
    report = build_report()
    save_json(PUBLIC_NAME, report)
    for key in ("benchmarks", "factor_exposures", "strategy_diagnostics", "costs",
                "calibration", "experiments", "enrichment_bias"):
        print(f"  {key:<22} {report[key].get('status')}")
    print(f"validation status: {report['headline']['validation_status']} "
          f"({report['headline']['ic_periods_accumulated']} of "
          f"{report['headline']['ic_periods_required']} IC periods)")
    print(f"wrote public/data/{PUBLIC_NAME}")
    return report


if __name__ == "__main__":
    main()
