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
    {
        "id": "C1-benchmark-suite",
        "declared_at": "2026-08-07T14:20:00+00:00",
        "hypothesis": "The strategy delivers something a liquid, tradeable style ETF could not -- a blunter bar than the academic factor model, and the one a user of this product actually faces.",
        "category": "signal_evidence",
        "configuration": {
            "file": "pipeline/benchmark_suite.py",
            "benchmarks": ["SPY", "RSP", "IWM", "IJH", "IJR", "VB", "IWD", "IWF", "VTV",
                           "VUG", "SCHD", "NOBL", "VXF", "IJH+IWD 50/50"],
            "method": "each leg buy-and-hold from the strategy's own start date with one 10bps entry cost, identical to how backtest_monthly.py prices its SPY leg, then a Newey-West regression of the strategy on each",
        },
        "train_period": None, "validation_period": "2021-09..2026-07", "test_period": None,
        "metrics": {
            "beaten_on_cagr": "9 of 14",
            "significant_positive_alpha_count": 0,
            "largest_absolute_newey_west_t": 1.11,
            "strategy_cagr": 0.1033, "strategy_sharpe": 0.611,
            "vtv_cagr": 0.1217, "vtv_sharpe": 0.899, "vtv_max_drawdown": -0.1534,
        },
        "number_of_variants_tested": 14,
        "result": "No benchmark in the set is beaten with statistically significant alpha; the largest |t| is 1.11. VTV returns more at lower volatility with a shallower drawdown -- better on every dimension.",
        "decision": "ABANDON",
        "reason": "The 'beats the market' framing is not supported against any tradeable alternative. Reposition as a transparent factor tilt. Also caught a defect before publishing: the alpha t-statistic was read under a key ols_newey_west does not emit, and the .get() default published 0.00 for all 14 benchmarks, which reads as a confident null.",
    },
    {
        "id": "C2-strategy-diagnostics-and-regimes",
        "declared_at": "2026-08-07T14:05:00+00:00",
        "hypothesis": "The strategy's edge is stable across market-direction, volatility and rate regimes.",
        "category": "signal_evidence",
        "configuration": {
            "file": "pipeline/strategy_diagnostics.py",
            "regimes": ["market_direction", "volatility", "rates"],
            "defined_from": "benchmark and macro series only, fixed before any strategy performance was inspected",
        },
        "train_period": None, "validation_period": "2021-09..2026-07", "test_period": None,
        "metrics": {
            "expectancy_per_month": 0.00977, "profit_factor": 1.594, "win_rate": 0.61,
            "payoff_ratio": 1.019, "longest_losing_streak_months": 3,
            "bear_excess_pp": 10.3, "bull_excess_pp": -11.2,
            "rising_rates_excess_pp": -16.9, "falling_rates_excess_pp": 10.3,
        },
        "number_of_variants_tested": 3,
        "result": "The edge is not stable. This is a duration-sensitive, defensive book: +10.3pp annualized against SPY in bear markets and in falling rates, -16.9pp in rising rates.",
        "decision": "KEEP_AS_CHALLENGER",
        "reason": "A coherent and useful description of what the strategy is, and it belongs in the model card. Not actionable as a timing overlay without out-of-sample evidence, and turning regimes into an optimization layer is exactly what the brief rules out.",
    },
    {
        "id": "C3-cost-sensitivity-at-realized-turnover",
        "declared_at": "2026-08-07T14:12:00+00:00",
        "hypothesis": "A realistic tiered cost model gives up more than 200bps a year relative to the published flat 10bps.",
        "category": "cost_realism",
        "configuration": {
            "file": "pipeline/cost_sensitivity.py",
            "method": "re-price the backtest's own recorded per-rebalance turnover at every rate costs.py can produce; annual drag = mean_monthly_turnover x one_way_bps x 12, the identity backtest_monthly.py already charges",
        },
        "train_period": None, "validation_period": "2021-08..2026-07", "test_period": None,
        "metrics": {
            "mean_monthly_turnover": 0.649, "published_drag_bps": 78.0,
            "breakeven_one_way_bps": 35.7, "worst_modelled_one_way_bps": 25.0,
            "worst_additional_drag_bps": 116.9,
        },
        "number_of_variants_tested": 9,
        "result": "Resolved, and it inverts the concern. Re-running the backtest with costs.py pricing every leg from its own trailing liquidity and volatility (now possible offline from the committed price cache) *lowers* total cost from $4,194 at flat 10bps to $1,002 base / $2,020 stress -- the cached book is liquid enough that the flat 10bps assumption was conservative, not optimistic. Net CAGR rises 0.55pp under base and 0.39pp under stress.",
        "decision": "ABANDON",
        "reason": "The hypothesis was that realistic costs would give up more than 200bps. They give up less than the flat assumption already charged. This holds for the 360-name cached universe, which is more liquid than the full 910-name configured one, so it is not the last word on the published backtest -- but the direction is the opposite of what was feared.",
    },
    {
        "id": "C4-turnover-controls",
        "declared_at": "2026-08-07T14:35:00+00:00",
        "hypothesis": "Rank buffering, a minimum holding period, score smoothing or a replacement margin improves net-of-cost return by suppressing trades that act on noise rather than information.",
        "category": "portfolio_construction",
        "configuration": {
            "file": "pipeline/portfolio_construction.py",
            "rank_buffer": [1.25, 1.5, 2.0], "minimum_holding_months": [1, 3, 6],
            "score_smoothing_alpha": [0.5, 0.7], "replacement_margin": [2.0, 5.0],
            "note": "wired into backtest_monthly.py behind flags that all default to None, so omitting them reproduces the champion's plain top-N selection exactly",
        },
        "train_period": None, "validation_period": "2021-09..2026-08", "test_period": None,
        "metrics": {
            "universe": 360, "champion_cagr": 0.142, "champion_turnover": 0.547,
            "smooth07_cagr": 0.1684, "smooth07_turnover": 0.439,
            "hold6_cagr": 0.1665, "hold6_turnover": 0.309,
            "buffer15_cagr": 0.1233, "hold3_cagr": 0.1301,
            "cagr_spread_pp": 4.51,
        },
        "number_of_variants_tested": 9,
        "result": "Measured in-sample against the 360-symbol committed price cache. Score smoothing (+2.64pp CAGR, turnover 54.7% -> 43.9%) and a 6-month holding floor (+2.46pp, turnover -> 30.9%) both improve return and cut turnover; both rank buffers *hurt* (-1.85pp) and a 3-month floor hurts (-1.19pp) while a 6-month floor helps.",
        "decision": "KEEP_AS_CHALLENGER",
        "reason": "The non-monotonicity is the tell: a real effect does not usually flip sign with the parameter, and a 4.5pp spread across nine configurations on one in-sample path is well inside what noise produces. Promotion needs out-of-sample rank IC, deflated Sharpe, PBO and a walk-forward split; none of that is satisfied here. Reported as a diagnostic.",
    },
    {
        "id": "C5-score-calibration",
        "declared_at": "2026-08-07T14:50:00+00:00",
        "hypothesis": "Score buckets carry a measurable historical outcome distribution that can give a 0-100 score empirical meaning.",
        "category": "signal_evidence",
        "configuration": {
            "file": "pipeline/score_calibration.py",
            "minimum_observations_per_bucket": 30,
            "buckets": "adaptive quantiles plus the fixed score bands confidence.py reads",
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"observations": 0, "measured_buckets": 0},
        "number_of_variants_tested": 1,
        "result": "Blocked. The harness has 0 of 24 periods and the PIT store is three days deep, so every bucket reports insufficient_data with its shortfall named and confidence_detail.historical_calibration stays null.",
        "decision": "INCONCLUSIVE",
        "reason": "The gate is the deliverable: fabricating calibration would convert an admitted unknown into a false claim. Caught one inconsistency in testing -- publishability was gated on adaptive quintiles while confidence.py reads fixed bands, and the two can disagree.",
    },
    {
        "id": "C6-applicability-unification",
        "declared_at": "2026-08-10T20:00:00+00:00",
        "hypothesis": "The champion and v2 paths resolve metric applicability from the same authority and reach the same answers.",
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/canonical_metrics.py", "pipeline/config/metric_registry.json",
                      "pipeline/config/business_profiles.json"],
            "change": ("suppressed_metrics delegates to applicability_for (explicit matrix rules plus the "
                       "registry's per-profile declarations), rule and registry lookups resolve under either "
                       "metric-ID namespace via a shared LEGACY_ALIASES map, and declaration_defaults gained "
                       "the semiconductor profile (plus profitable_biotechnology/semiconductor additions to "
                       "the eight explicit registry lists and reit to price_to_book, which required_for_score "
                       "already declared required)."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "v2_semiconductor_suppressed_metrics_before": 28, "after": 3,
            "v2_semiconductor_applicable_weight_before": 0.1304, "applicable_weight_after": 0.9428,
            "champion_rows_changed_of_880": 21, "max_champion_fundamentals_delta_pp": 1.7,
        },
        "number_of_variants_tested": 1,
        "result": ("Defect confirmed by direct read: the legacy path checked only explicit rules (an insurer's "
                    "revenue growth stayed scored against a registry that declares it inapplicable) while the v2 "
                    "path's price_to_sales alias dodged the explicit sales_multiple rule, and every "
                    "declaration_defaults-inheriting metric was suppressed for the semiconductor profile because "
                    "the default list predated it -- CRUS's v2 structural score was computed from 3 metrics while "
                    "the champion scored 26. The matrix also required price_to_book for REITs while the registry "
                    "suppressed it."),
        "decision": "PROMOTE",
        "reason": ("Consistency defect fix, not a new signal: one authority now answers both paths under both "
                   "namespaces, pinned by tests (required-vs-applicability invariant, per-profile legacy/v2 "
                   "agreement, semiconductor un-gutting)."),
    },
    {
        "id": "C7-turnover-walkforward",
        "declared_at": "2026-08-10T20:15:00+00:00",
        "hypothesis": "The C4 in-sample turnover-control winners (smooth07, hold6) survive the promotion gates: a walk-forward split, PBO below 0.5, and a deflated Sharpe above 0.95.",
        "category": "signal_evidence",
        "configuration": {
            "file": "research/turnover_walkforward.py",
            "runs": "backtest_monthly.py --cache-only --years 5 per selection variant, 860 usable names, 60 monthly rebalances",
            "walk_forward": "split-half, one purged period at the boundary",
            "pbo": "CSCV over the [month][variant] return matrix, 6 and 8 splits",
            "deflated_sharpe_trials": 47,
        },
        "train_period": "months 1-30 of the cached path", "validation_period": None,
        "test_period": "months 32-60 (one purged)",
        "metrics": {
            "in_sample_winner": "buffer15", "winner_out_of_sample_rank": "7 of 7",
            "pbo_cscv_8_splits": 0.8429, "pbo_cscv_6_splits": 0.80,
            "max_deflated_sharpe_probability": 0.4207,
        },
        "number_of_variants_tested": 7,
        "result": ("Rejected on every gate. The variant chosen on the first half finished last of seven on the "
                    "second half, PBO is 0.80-0.84 (selection is generating winners at random), and no variant's "
                    "deflated Sharpe probability reached even half the 0.95 bar. The in-sample ordering also "
                    "disagrees with the earlier 360-name-cache matrix (smooth07/hold6 led there; hold3/margin5 "
                    "here), which is noise behavior, not a real effect."),
        "decision": "ABANDON",
        "reason": ("The C4 challengers' in-sample edge does not survive its own selection process. Promoting "
                   "smooth07 or hold6 on the earlier evidence would have shipped overfit. Turnover remains a "
                   "cost problem worth attacking, but not through any of these seven selection rules."),
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


def total_variants_tested(registry=REGISTRY):
    """Every configuration searched across the whole research programme.

    ``validation.ic_harness.research_trial_count`` reads this so Deflated Sharpe deflates
    against the real search, not against the handful of live shadow strategies.
    """
    return sum(entry["number_of_variants_tested"] for entry in registry)


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
        "total_variants_tested": total_variants_tested(registry),
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
