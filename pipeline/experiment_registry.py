"""A4 — experiment registry.

The brief's evidence discipline only works if the multiple-testing machinery already built
(``validation_framework.deflated_sharpe_ratio``, ``append_multiple_testing_log``) sees the
real trial count, and the repository has an honest record of what was tried, including
what failed and what is still blocked. Before this module nothing fed those trial counts
anywhere, and the only record of WO-1 through WO-5/Q1/Q2 was prose scattered across
``docs/P0-*.md``.

``REGISTRY`` is a hand-maintained backfill of every experiment already run this project,
in the brief's schema (id, hypothesis, category, configuration, train/validation/test
periods, metrics, number_of_variants_tested, result, decision, reason). It is intentionally
data, not a computed report -- these are historical facts (what was tried, when, and what it
found), not something to re-derive from artifacts on every run. New experiments get appended
here going forward.
"""

import json
import os

from validation_framework import append_multiple_testing_log

REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "experiment_registry.json")
# Deliberately not pipeline/reports/p0_trial_log.jsonl: that file is an existing, unrelated
# ad hoc JSONL log of raw diagnostic numbers, one JSON object per line. This is the JSON-array
# format validation_framework.append_multiple_testing_log actually reads and writes.
MULTIPLE_TESTING_LOG_PATH = os.path.join(os.path.dirname(__file__), "reports", "multiple_testing_log.json")

DECISIONS = {"PROMOTE", "KEEP_AS_CHALLENGER", "ABANDON", "INCONCLUSIVE"}

REGISTRY = [
    {
        "id": "WO-1",
        "declared_at": "2026-08-07T05:29:54+00:00",
        "hypothesis": "run_manifest.score_distribution reports the champion score shown in the UI and used for ranking, not a shadow scoring variant.",
        "category": "data_integrity",
        "configuration": {
            "file": "pipeline/observability.py",
            "change": "run_manifest.score_distribution built from row['score'] instead of row['analysis_v2']['structural']['effective_score'] (the v2 shadow canonical-metrics score).",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {},
        "number_of_variants_tested": 1,
        "result": "Defect confirmed by direct source read: line 30 pulled the wrong field.",
        "decision": "PROMOTE",
        "reason": "One-line fix; pipeline/tests/test_observability.py locks score_distribution to row['score'] with a synthetic divergence case and a full advisor.json replay.",
    },
    {
        "id": "WO-2",
        "declared_at": "2026-08-07T05:43:04+00:00",
        "hypothesis": "The insider (SEC Form 4) layer is dark because SEC_USER_AGENT is unset, and unavailable insider evidence is read as neutral rather than absent.",
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/sec_edgar.py", "pipeline/insider_signal.py"],
            "note": "SecEdgarClient.available == bool(os.getenv('SEC_USER_AGENT')). .env.example, refresh-advisor.yml, and SYSTEM-SETUP.md already documented the variable before this session.",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {},
        "number_of_variants_tested": 1,
        "result": "insider_signal.py already returned 0.0 points with available: False on empty input (correct behavior); the gate is genuinely just the missing secret, which is the repository owner's action, not a code defect.",
        "decision": "PROMOTE",
        "reason": "Locked with pipeline/tests/test_insider_signal.py::test_no_transactions_reports_unavailable_rather_than_neutral_zero. A3 session additionally split source_status.sec_form4.status into unavailable_not_configured vs. unavailable_provider_error so confidence.py never conflates the two.",
    },
    {
        "id": "WO-3",
        "declared_at": "2026-08-07T05:43:29+00:00",
        "hypothesis": "ic_harness.py and backtest_monthly.py price every trade at a flat 10bps, ignoring costs.py's liquidity- and volatility-aware cost model entirely.",
        "category": "validation_infrastructure",
        "configuration": {
            "files": ["pipeline/backtest_monthly.py", "pipeline/validation/ic_harness.py", "pipeline/pit_store.py"],
            "change": "Added --cost-model {flat,tiered} / --cost-scenario {optimistic,base,stress}; tracked average_dollar_volume in pit_store snapshots (schema v1 -> v2).",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {},
        "number_of_variants_tested": 1,
        "result": "Confirmed and wired. The three-regime backtest re-run under tiered costs remains blocked_network_policy: no committed per-name price/volume cache exists to price the tiered leg without a live fetch.",
        "decision": "PROMOTE",
        "reason": "7 new regression tests (4 in test_backtest_monthly.py, 3 in test_ic_harness.py); flat model proved byte-identical to the pre-existing formula.",
    },
    {
        "id": "WO-4",
        "declared_at": "2026-08-07T08:54:31+00:00",
        "hypothesis": "After controlling for the six standard factors (market, size, value, profitability, investment, momentum), ValueSignal's realized return stream shows residual alpha.",
        "category": "factor_regression",
        "configuration": {
            "script": "pipeline/p0_q1_benchmark_factor_report.py",
            "method": "OLS with Newey-West HAC standard errors (Bartlett kernel, 3 lags), Ken French five factors + momentum, monthly resample of the cost-aware 60-rebalance backtest.",
        },
        "train_period": None, "validation_period": None,
        "test_period": "2021-09 to 2026-06 (n=58 months; full-sample regression, no walk-forward split)",
        "metrics": {
            "annualized_alpha_pct": -2.57, "monthly_alpha_pct": -0.217,
            "newey_west_t_alpha": -0.437, "r_squared": 0.589,
            "capm_beta": 0.793, "capm_beta_newey_west_t": 6.44,
            "significant_loadings_newey_west_t": {"market_excess": 6.50, "smb_size": 2.06, "momentum": 2.50},
            "not_significant_newey_west_t": {"hml_value": 1.00, "rmw_profitability": 0.70, "cma_investment": 0.31},
        },
        "number_of_variants_tested": 1,
        "result": "|t| = 0.437, below the brief's own 1.0 threshold for 'no residual alpha, factor tilt is the leading candidate' (Verdict B). Significant loadings are market, size, and momentum -- not value or profitability, despite the score being 78% fundamentals by construction.",
        "decision": "ABANDON",
        "reason": "The hypothesis under test -- 'ValueSignal generates residual alpha beyond known factor exposure' -- is rejected by this sample. This is the decisive result the rest of this session's honesty framing (docs/ALGORITHM-RESEARCH-RESULTS.md) is built on.",
    },
    {
        "id": "WO-5",
        "declared_at": "2026-08-07T09:21:38+00:00",
        "hypothesis": "Band/quantization artifacts (a metric crossing a scoring-band boundary on a small raw move) are the primary driver of the backtest's 64.9%-per-month rank churn.",
        "category": "turnover_attribution",
        "configuration": {
            "script": "pipeline/p0_q2_turnover_attribution.py",
            "method": "decompose_score_delta (stability_report.py) applied to pipeline/pit_store/*.jsonl consecutive-refresh transitions -- live intraday churn, not the blocked monthly-backtest churn.",
        },
        "train_period": None, "validation_period": None,
        "test_period": "pipeline/pit_store, 2 days deep, 4 refresh-to-refresh transitions",
        "metrics": {
            "band_crossing_pct": 0.42, "genuine_change_pct": 2.86, "availability_flicker_pct": 96.72,
            "band_crossing_events": 19, "genuine_change_events": 131, "availability_flicker_events": 4426,
        },
        "number_of_variants_tested": 1,
        "result": "Availability flicker dominates every single transition (96.7% of events), not band quantization (0.4%). The brief's leading hypothesis is very likely wrong, though this measures live intraday churn as a proxy for the blocked monthly-backtest churn, not the backtest itself.",
        "decision": "ABANDON",
        "reason": "Band-quantization hypothesis rejected by the closest available evidence. Availability flicker is the real driver and needs its own follow-up (why does per-name data availability flip refresh-to-refresh?), out of scope for this registry entry.",
    },
    {
        "id": "A1-NEWS-NEUTRAL",
        "declared_at": "2026-08-07T00:00:00+00:00",
        "hypothesis": "news_intelligence.py::weighted_sentiment returning the configured neutral_score (50.0) for zero-coverage names, instead of signaling unavailability, distorts published scores for the 373 of 374 screen-universe names with no cleared news coverage.",
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/news_intelligence.py", "pipeline/advisor_engine.py", "src/components/StockCard.jsx"],
            "change": "weighted_sentiment returns None (not neutral_score) with news_available: False when coverage is zero; blend_research_components already renormalizes over non-None components. Publishes news_available on every row. Fixed a downstream consumer (StockCard.jsx) that treated null the same as undefined.",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {},
        "number_of_variants_tested": 1,
        "result": "See pipeline/reports/news_fix_score_delta.json (generated by pipeline/rescore.py) for the measured before/after score delta on the committed universe.",
        "decision": "PROMOTE",
        "reason": "Lands on the champion per explicit user decision, with the before/after delta committed alongside it, not silently applied.",
    },
    {
        "id": "A3-FULL-UNIVERSE-ENRICHMENT",
        "declared_at": "2026-08-07T00:00:00+00:00",
        "hypothesis": "Seeding statement enrichment from the prior refresh's top 20 + 5 challengers (select_enrichment_priority) starves the model of statement-derived metrics for names a weaker prior model never surfaced, biasing which names can ever earn a high capital_allocation/accounting_quality score.",
        "category": "selection_bias",
        "configuration": {
            "files": ["pipeline/fetch_advisor.py", "pipeline/enrichment_bias.py"],
            "change": "FULL_UNIVERSE_RESEARCH=true env var makes select_enrichment_priority ignore previous_top entirely and enrich every preliminary candidate; not the default production path.",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "screen_universe_capital_allocation_coverage": "84/374",
            "enriched_population_mean_score": 66.31, "enriched_population_n": 124,
            "non_enriched_population_mean_score": 41.77, "non_enriched_population_n": 290,
        },
        "number_of_variants_tested": 1,
        "result": "Offline coverage/composition gap confirmed and quantified (docs/ENRICHMENT-BIAS-ANALYSIS.md). The causal question -- would full-universe enrichment surface different top-40 names -- is blocked_network_policy.",
        "decision": "INCONCLUSIVE",
        "reason": "Code path implemented and unit-tested (byte-identical priority regardless of previous_top, in pipeline/tests/test_fetch_advisor.py). The measurement that would resolve PROMOTE vs. ABANDON needs a live run: FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py.",
    },
]


def _validate(entry):
    required = {"id", "hypothesis", "category", "configuration", "train_period",
               "validation_period", "test_period", "metrics", "number_of_variants_tested",
               "result", "decision", "reason"}
    missing = required - set(entry)
    if missing:
        raise ValueError(f"{entry.get('id', '<unknown>')}: missing registry fields {sorted(missing)}")
    if entry["decision"] not in DECISIONS:
        raise ValueError(f"{entry['id']}: decision '{entry['decision']}' not in {sorted(DECISIONS)}")


def backfill_multiple_testing_log(registry=REGISTRY, path=MULTIPLE_TESTING_LOG_PATH):
    """Feed every registry entry's trial count into the deflated-Sharpe multiple-testing
    log, so validation_framework.deflated_sharpe_ratio can see the real number of trials
    instead of assuming one. Idempotent: entries already logged (by test_id) are skipped
    rather than raising, since append_multiple_testing_log rejects duplicate test_ids and
    this function is meant to be safe to call on every run.
    """
    appended = 0
    for entry in registry:
        test = {
            "test_id": entry["id"],
            "declared_at": entry["declared_at"],
            "hypothesis": entry["hypothesis"],
            "holdout_start": entry.get("test_period") or entry.get("validation_period") or "not_applicable",
            "number_of_variants_tested": entry["number_of_variants_tested"],
            "decision": entry["decision"],
        }
        try:
            append_multiple_testing_log(path, test)
            appended += 1
        except FileExistsError:
            continue
    return appended


def build_report(registry=REGISTRY):
    for entry in registry:
        _validate(entry)
    return {
        "schema": ["id", "hypothesis", "category", "configuration", "train_period",
                  "validation_period", "test_period", "metrics", "number_of_variants_tested",
                  "result", "decision", "reason"],
        "total_experiments": len(registry),
        "by_decision": {
            decision: sum(1 for entry in registry if entry["decision"] == decision)
            for decision in sorted(DECISIONS)
        },
        "total_variants_tested": sum(entry["number_of_variants_tested"] for entry in registry),
        "experiments": registry,
    }


def write_report(registry=REGISTRY, path=REPORT_PATH):
    report = build_report(registry)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report


def main():
    report = write_report()
    appended = backfill_multiple_testing_log()
    print(f"Wrote {REPORT_PATH}: {report['total_experiments']} experiments, "
          f"{report['total_variants_tested']} variants tested, by decision: {report['by_decision']}")
    print(f"Multiple-testing log: {appended} new entries appended to {MULTIPLE_TESTING_LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
