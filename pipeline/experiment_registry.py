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
    {
        "id": "R7-leg-reweighting",
        "declared_at": "2026-08-21T20:15:00+00:00",
        "hypothesis": ("Zeroing the panel-dead legs (growth, news_sentiment) and the 5-period negative-IC legs "
                       "(capital_allocation, accounting_quality) - proposal A - or additionally halving "
                       "market_behavior (proposal B) improves the composite over the frozen champion weights."),
        "category": "signal_evidence",
        "configuration": {
            "file": "research/audit/round7/reweighting_backtest.py",
            "runs": "top-20 equal-weight portfolios per weight vector over backtest_signal_panel.json, "
                    "59 usable monthly periods 2021-11..2026-08, composite_score renormalization, "
                    "net = gross - turnover x 20 bps",
            "provenance": "docs/AUDIT-ROUND-7-FINDINGS.md section 4.4",
        },
        "train_period": "the full 59-period panel (no holdout - weights were chosen on the same sample, "
                        "which is exactly why neither variant is promotable on this evidence)",
        "validation_period": None,
        "test_period": "prospective: proposal A registered as shadow strategy reweighted_composite_a "
                        "(pipeline/shadow_portfolios.py), collecting from 2026-08-21",
        "metrics": {
            "champion_gross_sharpe_rf0": 0.964, "champion_annualized_return_pct": 16.03,
            "proposal_a_gross_sharpe_rf0": 0.945, "proposal_a_annualized_return_pct": 15.74,
            "proposal_b_gross_sharpe_rf0": 1.076, "proposal_b_annualized_return_pct": 18.55,
            "universe_mean_gross_sharpe_rf0": 0.694,
            "proposal_a_mean_ic": 0.0354, "proposal_b_mean_ic": 0.0361, "champion_mean_ic": 0.0351,
        },
        "number_of_variants_tested": 2,
        "result": ("Proposal A's marginally better IC (0.0354 vs 0.0351) does not survive portfolio "
                    "construction: its top-20 backtest is slightly WORSE than the champion's (Sharpe 0.945 vs "
                    "0.964, 15.74% vs 16.03% annualized). Proposal B backtests better (1.076, 18.55%) but its "
                    "extra lever - shrinking market_behavior - rests on the drop_one_leg sample-composition "
                    "artifact documented in Round 7 section 4.3, and its weights were tuned on the same 59 "
                    "periods they are scored on. All variants beat the equal-weight universe (0.694)."),
        "decision": "KEEP_AS_CHALLENGER",
        "reason": ("No promotion case: the differences between champion, A, and B are within noise on 59 "
                   "monthly periods, and B's apparent edge is in-sample selection on a mismeasured diagnostic. "
                   "Proposal A runs prospectively as shadow reweighted_composite_a from 2026-08-21; the "
                   "prospective clock, not this panel, decides. B is deliberately NOT registered as a shadow - "
                   "carrying both would spend a second trial on the same idea."),
    },
    {
        "id": "R8-evidence-confidence-gate",
        "declared_at": "2026-08-23T00:00:00+00:00",
        "hypothesis": ("Every ticker on the live v2 validation dashboard (HIG, JPM, O, NEE, BSX, MSFT, XOM, "
                       "MRNA, VTI, TLT) reporting company evidence confidence below 0.40, a 0-of-0 peer sample, "
                       "and 0% profile confidence -- including for large, liquid, well-covered names like MSFT "
                       "and JPM -- is a wiring/data-join defect in pipeline/live_v2_validation.py, not a "
                       "genuine data-coverage gap."),
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/live_v2_validation.py", "pipeline/tests/test_live_v2_validation.py"],
            "change": (
                "Two independent stub defects, confirmed by direct source read. (1) "
                "`classification` was a hardcoded literal (total_peer_count: 0, valid_peer_count: 0, "
                "percentile_status: INSUFFICIENT_VALID_PEERS) for every ticker on every run -- never a "
                "call into peer_groups.canonical_percentiles(), the module fetch_advisor.py and "
                "migrate_advisor_v2.py already use for the real peer computation. Now calls it for real "
                "against the validated batch. (2) validate_live() built canonical observations from "
                "canonical_metrics.yahoo_observations(info) alone -- ~11 quote-level Yahoo .info fields -- "
                "and never called the statement-enrichment step (fetch_advisor.yahoo_extended / "
                "fundamentals_extended.extended_observations) fetch_advisor.py's enrich() runs for its "
                "shortlist, so every statement-derived metric (ROIC, EV/EBITDA, Piotroski F, interest "
                "coverage, accruals ratio, ...) reported missing for every ticker regardless of real "
                "coverage. Now wired in, mirroring enrich() exactly. Both stages instrumented with "
                "LOG.info non-null/null observation counts per ticker, matching the WO-1/WO-2 direct-read "
                "diagnostic pattern."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "before_structural_confidence": 0.21, "after_structural_confidence": 0.41,
            "before_structural_coverage": 0.30, "after_structural_coverage": 0.56,
            "before_company_action": "insufficient_evidence", "after_company_action": "watch",
            "before_peer_sample": "0 / 0 (hardcoded, every ticker, every run)",
            "after_peer_sample": "3 / 3 (real batch count; still INSUFFICIENT_VALID_PEERS, correctly, "
                                 "since peer_groups.MINIMUM_VALID_PEERS=30)",
            "production_reference_hig_data_coverage": 0.82,
            "pre_fix_committed_validation_hig_coverage": 0.35,
        },
        "number_of_variants_tested": 1,
        "result": (
            "Confirmed a split root cause. (a) Peer sample was a pure stub -- a hardcoded literal, not a "
            "computation -- category (a)/broken-join, not data scarcity. (b) Structural/profile confidence "
            "was genuinely low GIVEN the inputs validate_live() gathered, but the reason those inputs were "
            "incomplete is itself a wiring gap: the script never invoked the enrichment stage production "
            "uses. Confirmed against production: public/data/advisor.json shows HIG at data_coverage 0.82 "
            "the same week this view published structural.coverage 0.35 for the identical company -- the "
            "gap is the validation harness's scope, not HIG's real-world coverage. Regression test "
            "(test_live_v2_validation.py) shows wiring the same yahoo_extended() call production already "
            "uses raises a synthetic company's structural confidence from 0.21 to 0.41, crossing the "
            "action gate from insufficient_evidence to watch, with identical quote data on both sides -- "
            "isolating the enrichment step as the swing factor. (c) The timeliness layer's effective_score: "
            "None is a separate, correctly-reported, already-documented gap (scoring_v2.py's own "
            "unavailable_reason string: no free provider supplies broad forward-estimate revisions, "
            "earnings-surprise collection is opt-in) and is deliberately left untouched."),
        "decision": "PROMOTE",
        "reason": ("Two wiring defects fixed at the source (pipeline/live_v2_validation.py), not a display-"
                   "only patch: peer sample now calls peer_groups.canonical_percentiles() over the real "
                   "validated batch, and statement enrichment now runs identically to fetch_advisor.enrich(). "
                   "Locked by pipeline/tests/test_live_v2_validation.py (3 tests: peer sample computed not "
                   "hardcoded, enrichment wired in and raises confidence, a genuinely statement-starved "
                   "company still correctly gates low). A live re-run of pipeline/live_v2_validation.py to "
                   "refresh the committed public/data/validation/live_v2_validation.json artifact with real "
                   "Yahoo data is blocked_network_policy in this environment, same as A3-FULL-UNIVERSE-"
                   "ENRICHMENT -- the fix is verified against a controlled fixture and against the committed "
                   "production advisor.json, not yet against a fresh live pull for this exact artifact."),
    },
    {
        "id": "R8-2-publication-gate-not-enforced",
        "declared_at": "2026-08-23T20:00:00+00:00",
        "hypothesis": ("A recurring pipeline/validate_data.py CI failure -- 'ranked company lacks a "
                       "fundamental score' / 'low resolved evidence weight must classify as insufficient "
                       "evidence', hitting a different research row index on 2026-08-22T00:05 (run #190, "
                       "research.38) and 2026-08-23T19:47 (run #192, research.36) -- is downstream of the "
                       "same confidence-gate defect class as R8-evidence-confidence-gate, and NOT an "
                       "enrichment-coverage gap: the enrichment status check for this same round confirmed "
                       "MSFT and JPM (the Round 8 P1 sample's large-caps) both resolve real statement-"
                       "derived fundamental_categories in production advisor.json, so enrichment reaching "
                       "a name was never the question here."),
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/fetch_advisor.py", "pipeline/tests/test_fetch_advisor.py"],
            "change": ("Extracted rank_publishable(research, publish_limit): ranked = research[:publish_limit] "
                       "sliced strictly by publication_gate['published'] before score, instead of by raw score "
                       "alone. screen_universe changed from a `research[publish_limit:]` positional slice to a "
                       "ranked_tickers membership filter, since a gate-failing row can sit anywhere in the "
                       "score order and a positional slice would silently drop it from both lists."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "run_190_failing_row": "research.38", "run_192_failing_row": "research.36",
            "gate_floor": 0.35,
            "msft_capital_allocation_category": 52.4, "msft_accounting_quality_category": 62.0,
            "jpm_capital_allocation_category": 93.3, "jpm_accounting_quality_category": 55.0,
        },
        "number_of_variants_tested": 1,
        "result": (
            "Defect confirmed by direct source read, not an enrichment gap. data_health.publication_gate's "
            "own docstring: 'Names failing the gate keep their diagnostics and challenger output; only the "
            "ranked champion score is withheld' -- and docs/AUDIT-ROUND-4-FINDINGS.md Task 6: a name below "
            "the 0.35 floor 'publishes as INSUFFICIENT DATA, not as a ranked stance.' The call site only ever "
            "set row['stance'] = 'INSUFFICIENT DATA'; nothing excluded the row from `research.sort(key=score)` "
            "/ `research[:publish_limit]`. A company with zero usable fundamentals but a high momentum-only "
            "score (renormalized fully onto market_behavior once fundamentals coverage hits 0) could still "
            "out-rank real-coverage names into the published top publish_limit, contradicting the product's "
            "own fundamentals-first framing (CLAUDE.md) and tripping validate_data.py's schema/invariant "
            "checks on every run where this occurred. Enrichment itself was never the cause: production's "
            "select_enrichment_priority already reaches MSFT (via ADVISOR_PORTFOLIO_SYMBOLS + "
            "ADVISOR_FOCUS_SYMBOLS, both force-included every run) and JPM (via incumbents/challengers/"
            "rotation) alike, and both show real statement-derived category scores in the current committed "
            "advisor.json -- confirming this is a downstream ranking-eligibility defect, not an upstream "
            "enrichment-coverage one."),
        "decision": "PROMOTE",
        "reason": ("One-function fix restoring an already-documented, already-committed contract "
                   "(publication_gate's docstring, AUDIT-ROUND-4-FINDINGS.md) that the ranking slice never "
                   "actually enforced -- not a change to confidence.py, valuation_score, blend_research_"
                   "components, or any scoring weight. Locked with 4 new tests in test_fetch_advisor.py: a "
                   "gate-failing row never takes a ranked slot even at the highest score, every row lands in "
                   "ranked or is excluded (none silently dropped, the screen_universe positional-slice bug "
                   "this also fixes), filtering preserves the caller's sort order rather than re-deriving one, "
                   "and a low-coverage run with fewer than publish_limit gate-passing rows shrinks the "
                   "leaderboard instead of backfilling with gate-failures. Full pipeline suite (2239 tests) "
                   "and validate_data.py both green after the change."),
    },
    {
        "id": "R11-P1-optimization-harness",
        "declared_at": "2026-08-23T21:00:00+00:00",
        "hypothesis": ("A reusable parameter-search harness that enforces train/validation/holdout "
                       "splitting in code (not a process doc), gated by walk-forward efficiency, PBO via "
                       "CSCV, and deflated Sharpe against the real cumulative trial count, would reproduce "
                       "Round 10's finding that champion and the reweighted_composite_a shadow proposal "
                       "(R7-leg-reweighting) are statistically indistinguishable in this panel -- and would "
                       "show neither clears the promotion bar on backtest evidence alone, consistent with "
                       "reweighted_composite_a still only running on the prospective clock, not promoted."),
        "category": "infrastructure",
        "configuration": {
            "file": "pipeline/optimization_harness.py",
            "change": ("New Panel (immutable chronological train/validation/holdout split, never "
                       "shuffled), OptimizationSession (evaluate() only ever touches train+validation, "
                       "never .holdout; deflated-Sharpe trials floored at experiment_registry."
                       "total_variants_tested()), and classify() (walk-forward + search-wide PBO + "
                       "deflated Sharpe gates, suggesting PROMOTE/KEEP_AS_CHALLENGER/ABANDON). Applied to "
                       "pipeline/backtest_signal_panel.json (60 periods, 50/25/25 train/validation/holdout "
                       "split) comparing champion's published leg_weights against reweighted_composite_a's "
                       "REWEIGHTED_A_WEIGHTS (pipeline/shadow_portfolios.py). C4-turnover-controls' own "
                       "re-run (Priority 1 item 4) is not repeated here: C7-turnover-walkforward already "
                       "applied this exact rigor (split-half walk-forward, CSCV PBO at 6 and 8 splits, "
                       "deflated Sharpe against 47 trials) to that specific question and reached ABANDON -- "
                       "re-simulating it through this harness would require backtest_monthly.py-style "
                       "monthly NAV series, a different data shape than the composite-score panel this "
                       "harness consumes, and would not change C7's already-rigorous answer."),
        },
        "train_period": "backtest_signal_panel.json periods[0:30] (2021-09..2024-02)",
        "validation_period": "backtest_signal_panel.json periods[30:45] (2024-03..2025-05)",
        "test_period": "backtest_signal_panel.json periods[45:60] (2025-06..2026-08), informational holdout only, never used for selection",
        "metrics": {
            "trial_count_at_run": 55,
            "champion_train_mean_ic": 0.0263, "champion_validation_mean_ic": 0.0518,
            "proposal_a_train_mean_ic": 0.0263, "proposal_a_validation_mean_ic": 0.0518,
            "walk_forward_efficiency": 1.9696,
            "deflated_sharpe_probability": 0.2077,
            "clears_multiple_testing_bar": False,
            "search_wide_pbo_8_splits": 0.0,
            "holdout_mean_ic_informational_only": 0.036, "holdout_t_stat_informational_only": 0.952,
        },
        "number_of_variants_tested": 2,
        "result": ("champion and proposal_a produced byte-identical validation-period IC series (0.0518 "
                   "mean IC both), confirming Round 10's finding under a genuinely split, gated protocol "
                   "rather than R7's original un-split full-panel script: growth and news_sentiment "
                   "contribute exactly 0% of the composite in this panel and capital_allocation/"
                   "accounting_quality contribute only 6.5-6.7%, so zeroing them (proposal_a) versus "
                   "keeping them (champion) is arithmetically indistinguishable here. Search-wide PBO of "
                   "0.0 follows trivially from the two configurations being identical, not from either one "
                   "being genuinely dominant. Neither configuration ships: deflated Sharpe probability "
                   "0.2077 is well under the 0.95 bar even before this comparison's own selection is "
                   "charged against it, and validation IC's t-statistic does not clear 3.0. Walk-forward "
                   "efficiency of 1.97 (validation IC exceeding train IC) is itself a caution sign worth "
                   "naming, not a good sign -- a ratio that far from 1.0 in either direction on a short, "
                   "30/15-period split reads as small-sample noise, not evidence the signal generalizes "
                   "unusually well out-of-sample."),
        "decision": "KEEP_AS_CHALLENGER",
        "reason": ("Matches R7-leg-reweighting's own standing decision and does not change it: "
                   "reweighted_composite_a continues on the prospective clock (started 2026-08-21) exactly "
                   "as before, this round supplies an independent, more rigorous backtest-side "
                   "confirmation that neither backtest alone would have promoted it, so the prospective "
                   "clock remains the only path to a promotion decision here. No production weight or "
                   "composite construction changed. The harness itself (not this one comparison) is what "
                   "ships: locked with 12 tests in pipeline/tests/test_optimization_harness.py covering "
                   "split disjointness/chronology, holdout non-access, registry-floored trial count, PBO "
                   "on synthetic noise vs. a genuinely dominant configuration, and classification's "
                   "search-wide-overfit-abandons-everything rule. Full pipeline suite green after the "
                   "change (2267 tests)."),
    },
    {
        "id": "R11-P2-shadow-portfolio-registry-cap",
        "declared_at": "2026-08-23T21:15:00+00:00",
        "hypothesis": ("pipeline/shadow_portfolios.py already runs multiple strategies concurrently, but "
                       "nothing distinguished permanent product sleeves/baselines (production, SPY, "
                       "momentum, and so on -- always live since ACTIVATION_DATE, never subject to a "
                       "promotion decision) from genuine research-candidate shadows (strategies with their "
                       "own later activation date, like reweighted_composite_a, each one taxing the "
                       "deflated Sharpe correction charged against every other concurrent candidate), and "
                       "nothing enforced the brief's stated 3-4 concurrent-candidate cap in code."),
        "category": "infrastructure",
        "configuration": {
            "file": "pipeline/shadow_portfolios.py",
            "change": ("Added research_candidate_strategies() (returns STRATEGY_ACTIVATION_DATES -- the "
                       "existing, already-correct definition of 'has its own activation date, distinct "
                       "from the permanent STRATEGIES sleeves'), MAX_CONCURRENT_RESEARCH_CANDIDATES=4, and "
                       "assert_candidate_capacity(), called once at import time against the live registry "
                       "so a future change registering a fifth concurrent candidate without concluding one "
                       "of the existing ones fails immediately at import/test time rather than silently."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"research_candidates_currently_registered": 1, "cap": 4},
        "number_of_variants_tested": 1,
        "result": ("Exactly one research-candidate shadow (reweighted_composite_a) is currently "
                   "registered, well under the cap; this round's optimization-harness run (R11-P1) found "
                   "no new candidate that cleared the promotion bar with enough margin to warrant "
                   "registering a second one, so the cap-enforcement scaffolding ships without a new "
                   "candidate behind it -- adding one that does not deserve to exist yet, just to "
                   "demonstrate the plumbing, would itself be the kind of dishonest bookkeeping this "
                   "registry exists to prevent."),
        "decision": "PROMOTE",
        "reason": ("Structural, in-code cap enforcement matching the brief's explicit 'not a process doc' "
                   "requirement, at effectively zero risk: the guard only ever fails a future violation, "
                   "and the live registry already passes it. Locked with 5 tests in "
                   "test_shadow_portfolios.py covering the live registry passing its own guard, permanent "
                   "sleeves being correctly excluded from the candidate count, a cap violation being "
                   "refused, an at-cap registry still passing, and a caller-supplied tighter limit being "
                   "honored."),
    },
    {
        "id": "R11-P3-deflated-sharpe-trial-count-undercount",
        "declared_at": "2026-08-23T21:30:00+00:00",
        "hypothesis": ("Round 9 found the tear-sheet's Deflated Sharpe reads 'Insufficient, variance of "
                       "Sharpes across registered trials is not recorded' on one view while another shows "
                       "0.238 -- the brief attributed this to no single complete trial log existing. Direct "
                       "source read found the sharper, more specific defect: signal_metrics.py's "
                       "honesty_metrics() computed its own trials count from just the currently-loaded "
                       "backtest's optimizer sweep categories (falling back to 1 if none), never reading "
                       "experiment_registry.total_variants_tested() at all -- the exact undercount "
                       "ic_harness.py's research_trial_count() (validation/ic_harness.py:348) already "
                       "guards against for the audit-dashboard view, floored via max(configured, registry "
                       "total). Whatever the specific 'Insufficient' framing traces to (not found verbatim "
                       "in the repo; may be UI copy for the null-DSR case rather than committed data), the "
                       "undercount itself was real and reproducible."),
        "category": "data_integrity",
        "configuration": {
            "files": ["pipeline/signal_metrics.py", "pipeline/tests/test_signal_metrics.py"],
            "change": ("trials = len(sweep categories) or 1 changed to trials = max(sweep_trials, "
                       "experiment_registry.total_variants_tested()), mirroring ic_harness.py's existing "
                       "research_trial_count() floor pattern exactly rather than inventing a second one."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "registry_total_variants_tested_at_fix_time": 55,
            "committed_signal_metrics_json_trials_before_fix": 201,
            "note": ("201 > 55, so this specific already-committed artifact's published 0.238 value does "
                     "not change until the next refresh recomputes it -- the undercount's exposure is any "
                     "backtest run whose own optimizer sweep is shallower than the registry total (a "
                     "single-category or no-sweep run would previously have reported trials=1), not "
                     "necessarily today's published number."),
        },
        "number_of_variants_tested": 1,
        "result": ("Confirmed by direct source read (pipeline/signal_metrics.py honesty_metrics, trials "
                   "line) and reproduced with a regression test: a synthetic one-category optimizer sweep "
                   "now reports trials equal to the live registry total (55, and asserted > 1), not 1."),
        "decision": "PROMOTE",
        "reason": ("One-line fix restoring the same floor discipline ic_harness.py already enforces "
                   "elsewhere, closing the gap Round 9 flagged between the tear-sheet and audit-dashboard "
                   "Deflated Sharpe views without inventing a third calculation or touching evaluation.py's "
                   "math. backtest_swing.py's separate DSR_TRIALS=3 was investigated and deliberately left "
                   "unchanged: its comment and pipeline/validation/harness_freeze.json both document it as "
                   "the swing-reversal family's own registered trial count (a narrower, family-scoped "
                   "denominator, not a forgotten repo-wide count), a different and defensible design this "
                   "round did not have grounds to override. Full signal_metrics test suite green (57 "
                   "tests, 1 new) after the change."),
    },
    {
        "id": "R11-P4-edgar-pit-growth-reconstruction-feasibility",
        "declared_at": "2026-08-23T21:45:00+00:00",
        "hypothesis": ("Round 10 found the backtest panel's growth leg at 0.0% coverage (0 of 51,600 "
                       "ticker-periods), root-caused to Yahoo's quarterly statement history rarely reaching "
                       "the two full trailing-twelve-month windows year-over-year growth needs. The EDGAR "
                       "PIT fundamentals store already collected (pipeline/data/pit/fundamentals/, 4.78M+ "
                       "as-filed observations with filed timestamps back to 2009-08) should be able to "
                       "reconstruct historical TTM revenue growth without look-ahead risk, since "
                       "pipeline/edgar_enrichment.py's edgar_ttm_statements(symbol, as_of) already enforces "
                       "filed<=as_of for the live enrichment path -- this round asks whether it can also "
                       "cover the backtest reconstruction path, which never reads from this store today."),
        "category": "data_availability",
        "configuration": {
            "file": "research/audit/round11/edgar_pit_growth_pilot.py",
            "method": ("Bounded pilot, no network access used or needed (PIT store and the SEC ticker->CIK "
                       "entity map are both already-committed local data): revenue_growth(symbol, as_of) = "
                       "(TTM revenue as of as_of - TTM revenue as of as_of-365d) / abs(prior), for the 19 "
                       "of advisor_universe.json's 21 portfolio_symbols with a resolvable CIK (VOO, VGT are "
                       "ETFs, correctly excluded -- no XBRL financials to fetch), over the most recent 24 "
                       "monthly dates already in pipeline/backtest_signal_panel.json (2024-09..2026-08). "
                       "Scope is deliberately narrower than the brief's assumed '45 names': the live "
                       "portfolio_symbols list has 21, not 45."),
        },
        "train_period": None, "validation_period": None,
        "test_period": "2024-09-03 through 2026-08-03, 19 symbols x 24 months = 456 ticker-periods",
        "metrics": {
            "ticker_periods_attempted": 456, "ticker_periods_covered": 447, "coverage_pct": 98.0,
            "baseline_coverage_pct_yahoo_quarterly_path": 0.0,
            "sanity_check_symbols_with_a_published_growth_score_to_compare": 6,
            "sanity_check_directionally_consistent": 5,
            "sanity_check_outlier": "AGO (financial guarantor): reconstructed revenue TTM growth -184.0%, published growth score 50.0",
        },
        "number_of_variants_tested": 1,
        "result": ("Feasible, decisively: 98.0% coverage (447 of 456 ticker-periods) versus the existing "
                   "path's 0.0%, using data already collected and committed -- no new network access "
                   "required to prove this. Directional sanity check against live production's published "
                   "growth score agreed for 5 of 6 comparable tickers (EOG, COP, BAC, ADBE, CRUS); AGO (an "
                   "insurer/financial guarantor) was the one outlier, most likely because the generic "
                   "'Revenues' XBRL concept nets premiums/losses oddly for insurance profiles -- the same "
                   "reason this session's enrichment-expansion work and EXCLUDED_EXPANSION_PROFILES "
                   "already special-case financial/insurance names elsewhere in this codebase, not a flaw "
                   "in the filed<=as_of reconstruction method itself. This pilot measured revenue TTM "
                   "growth only, a narrower, deliberately bounded proxy for the full multi-input production "
                   "growth score, not a re-derivation of it."),
        "decision": "PROMOTE",
        "reason": ("The feasibility finding and the pilot script both ship: results are reproducible from "
                   "committed data alone (research/audit/round11/edgar_pit_growth_pilot_results.json). "
                   "Wiring this into pipeline/backtest_historical.py's production reconstruction path -- "
                   "extending it to earnings_growth alongside revenue, handling the financial/insurance "
                   "concept-mapping caveat AGO surfaced, and re-running Round 10's full leg diagnosis with "
                   "real growth coverage restored -- is real follow-up engineering this pilot deliberately "
                   "did not attempt, consistent with the brief's own 'bounded pilot... before trusting it "
                   "for calibration' framing and this session's standing constraint against touching "
                   "scoring/composite construction without separate authorization."),
    },
    {
        "id": "R11-P4-2-edgar-pit-wired-into-backtest-historical",
        "declared_at": "2026-08-23T22:00:00+00:00",
        "hypothesis": ("R11-P4-edgar-pit-growth-reconstruction-feasibility's follow-up: wire the same "
                       "filed<=as_of EDGAR PIT reconstruction into pipeline/backtest_historical.py's "
                       "production build_snapshot() path (not just the standalone pilot script), covering "
                       "both revenue_growth and earnings_growth, gated for the insurance profile ambiguity "
                       "AGO surfaced, so the next live re-run of the backtest panel picks up real growth-"
                       "leg coverage instead of the 0% Round 10 diagnosed."),
        "category": "data_availability",
        "configuration": {
            "files": ["pipeline/backtest_historical.py", "pipeline/tests/test_backtest_historical.py",
                     "pipeline/run_backtest_suite.py"],
            "change": ("edgar_pit_growth_fallback(ticker_data, as_of, need_revenue, need_earnings): fills "
                       "whichever of revenue_growth/earnings_growth Yahoo's ~8-quarter-deep quarterly "
                       "history left None, via edgar_enrichment.edgar_ttm_statements at as_of and "
                       "as_of-365d -- never overwrites a Yahoo-resolved value. Revenue growth skipped for "
                       "REVENUE_GROWTH_EXCLUDED_PROFILES (bank/life_insurer/property_casualty_insurer/"
                       "diversified_insurer/reit, matching fetch_advisor.py's "
                       "EXCLUDED_EXPANSION_PROFILES) via canonical_metrics.classify_profile; earnings "
                       "growth (net income) is not excluded -- the netting ambiguity R11-P4 found was "
                       "specific to the generic 'Revenues' XBRL concept. Added ticker_data['industry'] "
                       "(previously only 'sector' was captured) since classify_profile needs both to "
                       "distinguish insurer sub-types. DISABLE_EDGAR_PIT_BACKTEST_GROWTH=1 reproduces the "
                       "pre-this-round Yahoo-only behavior for comparison. Also wrote "
                       "pipeline/run_backtest_suite.py, a single CLI sequencing panel rebuild -> Round 10's "
                       "leg_diagnosis.py -> the Round 11 optimization harness against the registered shadow "
                       "candidate(s) (shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS, an explicit map added "
                       "so this doesn't guess an attribute name from a strategy id), so a future round "
                       "doesn't have to remember which of three scripts to run in which order."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 9},
        "number_of_variants_tested": 1,
        "result": ("Wiring correctness verified with 7 new tests in test_backtest_historical.py (mocked "
                   "edgar_ttm_statements -- no network/PIT-store dependency in the test itself): fills both "
                   "growth figures when Yahoo's history is short, skips revenue (not earnings) growth for "
                   "an excluded profile, respects the disable flag, never calls out when nothing is needed, "
                   "never raises on a PIT-store read failure, and -- the regression that matters most -- "
                   "never overwrites a growth figure Yahoo already resolved. run_backtest_suite.py's "
                   "diagnosis+harness stages were run end-to-end against the existing (pre-this-change) "
                   "committed panel (--skip-panel, no network needed for those two stages) and reproduced "
                   "R11-P1's exact numbers, confirming the CLI itself is correct. What is NOT yet done: the "
                   "panel itself has not been regenerated with this fallback live -- rebuilding "
                   "pipeline/backtest_signal_panel.json needs backtest_monthly.py's real yfinance network "
                   "access across ~860 tickers x 60 periods, which is blocked_network_policy in this "
                   "environment, the same constraint every prior round's live-data work in this repository "
                   "has hit. Round 10's leg diagnosis therefore still reads 0% growth coverage in the "
                   "currently-committed panel -- that number only changes after a real "
                   "`python3 pipeline/run_backtest_suite.py --years 5` run somewhere with network access."),
        "decision": "PROMOTE",
        "reason": ("The wiring, its tests, and the CLI all ship -- they're correct and ready for the next "
                   "real backtest re-run to exercise, and DISABLE_EDGAR_PIT_BACKTEST_GROWTH=1 preserves an "
                   "exact way to reproduce the old baseline for comparison once that re-run happens. Not "
                   "marked INCONCLUSIVE: the open item here isn't methodological uncertainty (R11-P4 "
                   "already established the method works, at 98% coverage on real data), it's purely "
                   "the standing network-access constraint on regenerating the full panel, which is "
                   "environmental, not a question this round's evidence leaves open. Full pipeline suite "
                   "green (2276 tests) after the change."),
    },
    {
        "id": "R11-P3-2-trial-count-logs-are-not-actually-fragmented",
        "declared_at": "2026-08-23T22:15:00+00:00",
        "hypothesis": ("R11-P3 flagged 'a third, disconnected trial-count source' -- "
                       "pipeline/validation/hypothesis_log.jsonl (8 entries) alongside experiment_registry.py "
                       "(55->61) and pipeline/validation/harness_freeze.json (50) -- as fragmentation needing "
                       "reconciliation, based on only having read harness_freeze.json's "
                       "trial_count_for_deflated_statistics block in isolation. Reading the full file (291 "
                       "lines, not the ~15-line fragment) to actually attempt that reconciliation, as directed."),
        "category": "data_integrity",
        "configuration": {
            "file": "pipeline/validation/harness_freeze_evaluator.py (new)",
            "finding": ("harness_freeze.json's dsr_trial_count_used=50 is a FROZEN promotion-criteria "
                       "constant, declared 2026-08-11/12 for four specific named prospective clocks "
                       "(champion, swing-v1.1.0, swing_reversal-A/B/C, entry_timing_overlay), and is not "
                       "read by any production code -- confirmed by grep: the only other reference to it "
                       "is a comment in backtest_swing.py, which uses its OWN family-scoped count (3), not "
                       "this 50. experiment_registry.py's total_variants_tested() is a SEPARATE, "
                       "continuously-growing count consumed by ic_harness.py/signal_metrics.py for live "
                       "dashboard statistics not tied to any one frozen clock. hypothesis_log.jsonl's 8 "
                       "entries are not a third system: they are the literal machine-readable source "
                       "harness_freeze.json's own note says its 2026-08-12 swing_reversal(3)+"
                       "entry_timing_overlay(5)=8 subtotal was read from -- a component of the 50, not a "
                       "competitor to it. Merging these into one number would be a category error: it "
                       "would either move the goalposts on an already-started frozen clock (if the dynamic "
                       "registry total were substituted in) or wrongly narrow the live dashboard's "
                       "deflation to a stale August snapshot (if the frozen 50 were substituted there). "
                       "Separately found while reading the full file: pipeline/validation/deflated_sharpe.py "
                       "(233 lines, its own tested DSR + PBO implementation, explicitly named as the "
                       "required implementation in entry_timing_overlay.statistical_requirements) had zero "
                       "production callers -- a real, different gap from what R11-P3 flagged."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {
            "harness_freeze_pre_freeze_categories_unresolved": 6,
            "note": ("Whether experiment_registry.py's WO-1..C7 entries (16 entries, dated 2026-08-07..10, "
                     "before the 2026-08-11 freeze) overlap with harness_freeze.json's six OTHER pre-freeze "
                     "categories (backtest_variants_r3/r4/r5, turnover_control_sweep_pre_r3, "
                     "scoring_variants, regression_constructions, survivorship_reconstruction_runs, "
                     "pre_freeze_construction_runs -- 42 combined) could not be established: neither file "
                     "documents which source script or commit each of those six category counts traces to. "
                     "Left unresolved rather than guessed -- see decision/reason."),
        },
        "number_of_variants_tested": 1,
        "result": ("The three-way fragmentation R11-P3 reported does not exist in the form described: two "
                   "of the three are correctly separate by design (a frozen promotion gate vs. a live "
                   "dashboard statistic), and the third is a documented subset of one of them, not an "
                   "independent system. What DOES remain unresolved, honestly: whether 6 of harness_freeze."
                   "json's 8 pre-freeze category labels correspond to any work also recorded in "
                   "experiment_registry.py under a different name. Built and tested (16 tests) the actual "
                   "missing piece instead: harness_freeze_evaluator.py implements "
                   "evaluate_against_promotion_criteria() (the frozen ICIR/t-stat/deflated-Sharpe/PBO gates, "
                   "using pipeline/validation/deflated_sharpe.py per harness_freeze.json's own citation) and "
                   "evaluate_entry_timing_overlay_variant() (its distinct relative-improvement-over-baseline "
                   "acceptance rule). Both return insufficient_periods today, correctly, since every clock "
                   "this freeze covers is still at 0 of its required periods (harness_start_date "
                   "2026-09-01) -- there is nothing to evaluate yet, only machinery made ready for when "
                   "there is. Locked with 9 tests in test_harness_freeze_evaluator.py."),
        "decision": "PROMOTE",
        "reason": ("Corrects the record rather than leaving R11-P3's overstated 'fragmentation' claim "
                   "standing uncontested in the registry, which would itself be a research-integrity lapse "
                   "in an apparatus whose entire purpose is honest bookkeeping. Ships a real evaluator for "
                   "a criteria set that had been declared in writing but never wired to any code, using the "
                   "exact implementation (pipeline/validation/deflated_sharpe.py) the freeze document "
                   "itself names, rather than inventing a sixth deflated-Sharpe variant. Does not attempt "
                   "the six-category overlap question: guessing an overlap correction either way would be "
                   "a new, unaudited fabrication layered on top of an already-frozen document, which is "
                   "worse than leaving it explicitly open. 9 new tests in "
                   "test_harness_freeze_evaluator.py. Full pipeline suite green (2285 tests) after the "
                   "change."),
    },
    {
        "id": "R11-P5-swing-domain-and-auto-search",
        "declared_at": "2026-08-23T22:30:00+00:00",
        "hypothesis": ("optimization_harness.py only ever tested the 8 fundamental/behavioral legs, "
                       "and every candidate had to be hand-picked one at a time. User request: extend "
                       "the same harness to technical/momentum (swing) leg weighting, and add a bounded "
                       "automatic candidate-generation mode so a human-in-the-loop round-trip (run "
                       "locally, hand results back, get the next round's candidates) doesn't require "
                       "hand-authoring every weight vector."),
        "category": "infrastructure",
        "configuration": {
            "files": ["pipeline/backtest_swing.py", "pipeline/run_backtest_suite.py",
                     "pipeline/tests/test_backtest_swing.py", "pipeline/tests/test_run_backtest_suite.py"],
            "change": ("backtest_swing.py: new build_swing_signal_panel() + "
                       "run_backtest(..., collect_signal_panel=True) capture variant A's (the frozen "
                       "baseline's) per-ticker leg_scores for the 5 swing legs (pead_drift, "
                       "analyst_revision, high_volume_premium, high_52w_proximity, short_term_reversal) "
                       "into the same {date, leg_scores, forward_returns} shape "
                       "backtest_signal_panel.json already uses -- optimization_harness.py needed zero "
                       "changes to read it, since it was already leg-name-agnostic. New --panel-out CLI "
                       "flag, written to a separate file (never embedded in the committed "
                       "backtest_swing_results.json). Explicitly never touches "
                       "swing_signals.SWING_WEIGHTS or the swing-v1.1.0 prospective clock (harness_freeze."
                       "json's changes_that_reset_this_clock) -- this is a research/backtest panel only. "
                       "run_backtest_suite.py: added --domain {fundamentals,swing} (selects panel path, "
                       "build command, and default candidates -- swing-reversal-B's exact registered "
                       "weights for swing, transcribed from harness_freeze.json rather than re-derived); "
                       "diagnosis stage auto-skips for --domain swing since leg_diagnosis.py's leg names "
                       "are fundamentals-specific. Added --auto-search N: N randomly perturbed neighbors "
                       "of the champion/baseline weights (random_neighbor(): each leg scaled by a factor "
                       "in [1-perturbation, 1+perturbation], each leg independently droppable at "
                       "drop_probability to explore leg-removal hypotheses, renormalized to the champion's "
                       "total weight mass), generated from --search-seed for exact reproducibility. Every "
                       "candidate in one invocation still shares one Panel split and one shared "
                       "classify() call (one PBO across the whole batch), so nothing about the split-then-"
                       "search or search-wide-PBO discipline built in R11-P1 was loosened. Report output "
                       "now includes each candidate's actual weights (needed for a human to read the "
                       "result and propose the next round) and is sorted PROMOTE > KEEP_AS_CHALLENGER > "
                       "ABANDON, then by validation IC within a tier."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 10},
        "number_of_variants_tested": 1,
        "result": ("Verified end-to-end with a synthetic scratch swing panel (deleted, not committed) "
                   "and against the real committed fundamentals panel: --domain swing --auto-search 5 "
                   "and --domain fundamentals --auto-search 4 both ran the full split/PBO/deflated-Sharpe "
                   "gate sequence, correctly ranked results, and correctly reported a degenerate all-"
                   "zero-coverage-leg candidate (a real edge case a random drop can produce) as "
                   "ABANDON with mean_ic=None rather than crashing. Locked with 10 new tests (1 in "
                   "test_backtest_swing.py covering the new panel's shape, 9 in "
                   "test_run_backtest_suite.py covering the swing default candidate, random-neighbor "
                   "generation, and rank-key ordering)."),
        "decision": "PROMOTE",
        "reason": ("Pure tooling: no production weight, panel, or promotion decision changed. "
                   "optimization_harness.py itself needed no changes at all -- it was already generic "
                   "over leg names, which is what made this extension small. Auto-search stays within "
                   "this round's own stated discipline: bounded (N is a required, explicit argument, "
                   "never inferred), reproducible (seeded), and gated by the same PBO-across-the-batch "
                   "and registry-floored deflated-Sharpe machinery every other candidate in this "
                   "repository goes through -- it is a faster way to generate honestly-gated candidates "
                   "for a human to review, not a shortcut around the gates themselves. Full pipeline "
                   "suite green (2295 tests) after the change."),
    },
    {
        "id": "R11-P6-coverage-weighted-formula-and-elo-tournament",
        "declared_at": "2026-08-24T01:30:00+00:00",
        "hypothesis": ("User request, after a live human-in-the-loop search session against a real "
                       "10-year panel (run on the user's own machine, network-connected) found the "
                       "same conclusion three independent ways -- thin-sample PBO, well-powered PBO, "
                       "and cross-window train-IC instability -- that no hand-picked weight vector "
                       "beats champion reliably: (1) turn the session's own coverage-vs-weight "
                       "mismatch finding (profitability weighted at 20.3% on 7.5% coverage; growth "
                       "still weighted at 8.6% despite R11-P4's fix taking its coverage to 95.4%) "
                       "into an actual formula rather than a one-off observation, and (2) build a "
                       "repeated-comparison mechanism ('like chess Elo') so an edge's robustness "
                       "across resamples is visible as accumulating rating separation, rather than a "
                       "single closable split verdict."),
        "category": "infrastructure",
        "configuration": {
            "files": ["pipeline/optimization_harness.py", "pipeline/elo_tournament.py",
                     "pipeline/run_backtest_suite.py", "pipeline/tests/test_optimization_harness.py",
                     "pipeline/tests/test_elo_tournament.py"],
            "change": ("optimization_harness.formula_weights(periods): weight_leg proportional to "
                       "coverage_leg * max(0, standalone_ic_leg) (per_leg_ic(), already existing in "
                       "evaluation.py), normalized to sum to 1. A leg with broad coverage but no "
                       "measured predictive power is driven toward zero exactly as surely as a leg "
                       "with strong IC but almost no coverage. Computed only from a caller-supplied "
                       "train slice -- calling it on validation/holdout would reintroduce the exact "
                       "search-then-split mistake this whole harness exists to prevent. New "
                       "pipeline/elo_tournament.py: run_tournament(periods, candidates, rounds, seed, "
                       "k, sample_size) draws one bootstrap resample (with replacement, default size "
                       "= pool) of period indices per round, computes every candidate's mean rank IC "
                       "on that identical resample, plays a full round-robin among candidates with "
                       "standard logistic Elo updates, and repeats for `rounds` rounds. Wired into "
                       "run_backtest_suite.py as a fourth, opt-in stage (--elo-rounds N, "
                       "--include-formula to enter a formula_weights() candidate derived from the "
                       "harness's own Panel.train), sharing the same train/validation split the "
                       "harness stage uses."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 19},
        "number_of_variants_tested": 1,
        "result": ("Verified with 19 new tests (18 in test_optimization_harness.py including the new "
                   "leg_coverage/formula_weights coverage, 13 in test_elo_tournament.py -- note some "
                   "overlap in touched files with R11-P5's count) and a live smoke test against this "
                   "sandbox's own (stale, pre-10-year-rebuild) committed panel: a genuinely predictive "
                   "synthetic leg reliably out-rates a noise leg over 100 rounds (Elo separates "
                   "cleanly), two candidates that are actually identical stay locked at the same "
                   "rating for 150 rounds rather than one drifting ahead by chance, and -- the case "
                   "worth stating plainly -- on this sandbox's stale panel, formula_weights() itself "
                   "collapsed to {market_behavior: 1.0} and tied champion and reweighted_composite_a "
                   "on every single round (100/100), because on that specific panel those three "
                   "candidates produce byte-identical per-ticker scores (the same coverage-collapse "
                   "dynamic R11-P1 already found: most tickers only ever resolve market_behavior). "
                   "That is the tool working correctly, not a bug: three functionally-identical "
                   "candidates showing zero rating separation across 100 independent resamples is "
                   "exactly the honest answer, not a failure to find one."),
        "decision": "PROMOTE",
        "reason": ("Ships as tooling only -- no production weight, panel, or promotion decision "
                   "changed, and formula_weights()'s own docstring states plainly it must never be "
                   "computed on validation/holdout data. Explicitly scoped as a complement to, not a "
                   "replacement for, the existing PBO/deflated-Sharpe gates: bootstrap resampling "
                   "cannot manufacture statistical power beyond what a panel's real period count "
                   "already contains, and the tournament is designed to show that honestly (ratings "
                   "staying close) rather than obscure it. The genuinely informative next test is "
                   "against a real, network-fetched, EDGAR-refreshed panel outside this sandbox, not "
                   "available in this environment -- flagged rather than faked. Full pipeline suite "
                   "green (2314 tests) after the change."),
    },
    {
        "id": "R11-P7-edgar-pit-statement-fallback-beyond-growth",
        "declared_at": "2026-08-24T06:00:00+00:00",
        "hypothesis": ("The user's own real 10-year panel + --sector-breakdown run traced a root cause "
                       "for a finding that looked at first like a fresh-fetch flake: every sector's "
                       "sector_weight_report only ever showed growth and market_behavior, never "
                       "valuation/profitability/financial_health/capital_allocation/accounting_quality. "
                       "Reproduced locally against a real cached ticker (AAPL) plus this repo's own "
                       "committed EDGAR PIT store: for an as_of outside Yahoo's ~2-year cached quarterly "
                       "window, build_snapshot's start_idx comes back None and income_ttm/balance_now/"
                       "cashflow_ttm were left as *empty* statements outright -- not just missing growth, "
                       "the R11-P4 fix's own scope -- so every ratio basic_ratios()/derive_extended() "
                       "compute from them went to None too. For a 5-10 year backtest that's most of the "
                       "window. edgar_ttm_statements() (edgar_enrichment.py) already returns full "
                       "income/balance/cashflow dicts in build_ttm_statements' exact shape, so hypothesis: "
                       "substitute it directly for the empty-statement branch, the same 'reuse the "
                       "existing adapter, don't rebuild it' move R11-P4 made for growth specifically."),
        "category": "data_availability",
        "configuration": {
            "files": ["pipeline/backtest_historical.py", "pipeline/tests/test_backtest_historical.py"],
            "change": ("edgar_pit_statement_fallback(ticker_data, as_of): returns "
                       "(income, balance, cashflow) from edgar_ttm_statements(), or (None, None, None) "
                       "if disabled (DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS=1), no resolvable CIK, EDGAR "
                       "history that also doesn't reach back far enough, or a PIT-store read failure -- "
                       "never raises, same contract as edgar_pit_growth_fallback. Wired into "
                       "build_snapshot()'s start_idx-is-None branch ahead of the pre-existing "
                       "empty-statement fallback, which now only fires when EDGAR has nothing either. "
                       "Growth still resolves correctly through the normal revenue_now/revenue_prior "
                       "path once income_ttm is EDGAR's real data -- edgar_pit_growth_fallback is no "
                       "longer even called in that case, since revenue_growth/earnings_growth aren't "
                       "None anymore. Also: edgar_enrichment.BALANCE_ROWS has no shares-outstanding "
                       "concept, so market_cap (and every ratio needing it) would still be None even "
                       "with real EDGAR statements; added a further fallback to diluted (then basic) "
                       "weighted-average shares from the income statement via the existing "
                       "fundamentals_extended 'diluted_shares' alias -- a standard, disclosed stand-in "
                       "for a precise point-in-time float count, only used when neither a live share "
                       "count (blocked by allow_current_shares for point-in-time correctness) nor a "
                       "balance-sheet share count resolved."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 8},
        "number_of_variants_tested": 1,
        "result": ("8 new tests (4 for edgar_pit_statement_fallback in isolation, 4 for build_snapshot's "
                   "wiring, mocked edgar_ttm_statements -- no network/PIT-store dependency in the test "
                   "itself). Also reproduced end-to-end against real data in this sandbox: this repo "
                   "carries both a real cached AAPL ticker file and the real committed EDGAR PIT store "
                   "(pipeline/data/pit/fundamentals/), so build_snapshot(AAPL, 2024-06-30) was called "
                   "directly before and after the change. Before: only revenue_growth, earnings_growth, "
                   "and price/volume technicals were non-None (extended_coverage=0.0). After: "
                   "extended_coverage=1.0 and every category resolves real values -- price_to_sales=8.52, "
                   "return_on_equity=1.3531, current_ratio=1.04, debt_to_equity=1.38, altman_z=2.78, "
                   "piotroski_f=7.9, ev_to_ebitda=25.61, gross_buyback_yield=0.0252, market_cap resolved "
                   "via the diluted-shares fallback -- not a synthetic test, the actual production "
                   "function called against the actual committed data. Full pipeline suite green "
                   "(2356 tests, 448 subtests) after the change."),
        "decision": "PROMOTE",
        "reason": ("Same shape as R11-P4-2: correct, tested, and backtest-reconstruction-only -- "
                   "build_snapshot is not on the live scoring path (advisor_engine/scorer.py), so no "
                   "production score, weight, or promotion decision changes. What this does change is "
                   "the honesty of every backtest result already produced this round: R11-P1 through "
                   "R11-P6's harness/Elo/holdout comparisons were run against a panel where 5 of 8 legs "
                   "had almost no real coverage outside the most recent ~1.5 years, so their apparent "
                   "agreement (growth + market_behavior dominating, other legs collapsing toward "
                   "identical or near-zero contribution) was this bug's signature, not a settled finding "
                   "about those legs' true predictive power. The panel has NOT yet been regenerated with "
                   "this fix live -- that needs backtest_monthly.py's real yfinance network access across "
                   "the full universe, the same standing constraint on this sandbox every prior round's "
                   "live-data work has hit. Every harness/Elo/holdout number produced before this fix "
                   "regenerates the panel should be treated as measuring growth+market_behavior's edge "
                   "specifically, not the full 8-leg blend the weight vectors nominally describe."),
    },
    {
        "id": "R11-P8-metric-level-sector-breakdown",
        "declared_at": "2026-08-24T06:45:00+00:00",
        "hypothesis": ("User request: extend R11-P7's --sector-breakdown from the 6-8 rolled-up legs "
                       "(valuation, profitability, ...) to every individual metric the methodology "
                       "currently computes (trailing P/E, ROE, Piotroski F, Altman Z, buyback yield, "
                       "and so on) -- which specific metric carries signal in which sector, not only "
                       "which category. build_research's row already carries every one of these as "
                       "**snapshot-spread top-level keys (confirmed by reading advisor_engine.py "
                       "directly); the panel builder just never extracted them. Hypothesis: capture "
                       "them alongside the existing leg_scores, then reuse -- not reimplement -- every "
                       "existing leg-level function (leg_coverage, formula_weights, "
                       "sector_weight_report) by substituting metric_scores for leg_scores, since none "
                       "of those functions know or care whether a 'leg' name is a rolled-up category "
                       "or an individual metric."),
        "category": "infrastructure",
        "configuration": {
            "files": ["pipeline/backtest_monthly.py", "pipeline/optimization_harness.py",
                     "pipeline/run_backtest_suite.py", "pipeline/tests/test_backtest_monthly.py",
                     "pipeline/tests/test_optimization_harness.py"],
            "change": ("backtest_monthly.panel_metric_scores(rows): every key in a scored row that is "
                       "numeric, not a bool, and not one of build_research's own added output keys "
                       "(score, base_score, components, fundamental_categories, recommendation, "
                       "analysis_v2, ... -- an explicit exclusion set, not inferred, so a future field "
                       "added to build_research's return dict can't silently be mistaken for a scoring "
                       "input) -- captures trailing_pe, return_on_equity, piotroski_f, altman_z, "
                       "ev_to_ebitda, gross_buyback_yield, and everything else build_snapshot computes. "
                       "Wired alongside leg_scores in each panel period as metric_scores. "
                       "optimization_harness.as_metric_periods(periods) returns periods with "
                       "metric_scores standing in for leg_scores -- the substitution that lets "
                       "sector_weight_report (and everything it calls) run unchanged at the metric "
                       "level. run_backtest_suite.py: new --metric-sector-breakdown flag "
                       "(fundamentals-only, composes with --sector-breakdown), console output "
                       "truncated to the top 5 metrics per sector by formula weight -- the full list "
                       "still goes to --harness-out -- learned from this same round's earlier "
                       "console-flooding fix (R11-P7's neighbor, _drop_series)."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 8},
        "number_of_variants_tested": 1,
        "result": ("8 new tests (2 for panel_metric_scores' extraction/exclusion rules, 3 for "
                   "as_metric_periods' substitution and graceful-degradation on a pre-metric panel, "
                   "3 confirming sector_weight_report produces a correct per-sector breakdown when "
                   "fed remapped metric periods with no metric-specific code path at all). Full "
                   "pipeline suite green after the change. Sanity-checked panel_metric_scores directly "
                   "against a realistic row shape (AAPL-like: price_to_sales, return_on_equity, "
                   "piotroski_f, altman_z, market_cap) -- extracted exactly those four numeric fields, "
                   "correctly excluded sector/is_etf/fundamental_categories/components/recommendation."),
        "decision": "PROMOTE",
        "reason": ("Ships as tooling only -- no production weight, panel, or promotion decision "
                   "changed, same scope discipline as every other harness addition this round. Reuses "
                   "existing leg-level machinery rather than duplicating it, so this doesn't grow the "
                   "surface area that needs independent correctness verification. Requires a panel "
                   "rebuild (backtest_monthly.py, real network access) before metric_scores exists to "
                   "analyze -- not run against real data in this environment, same standing constraint "
                   "as R11-P7's own statement fallback."),
    },
    {
        "id": "R11-P9-sector-candidate-validation-check",
        "declared_at": "2026-08-24T15:30:00+00:00",
        "hypothesis": ("User's own real R11-P7/P8 run found genuinely different per-sector "
                       "leg/metric patterns (Utilities favoring leverage/size metrics, Technology "
                       "favoring margin/quality metrics, Energy showing six legs with positive train-"
                       "slice IC) -- but formula_weights() is explicitly train-slice-only by its own "
                       "contract, so none of that is yet evidence the pattern generalizes rather than "
                       "being fit to noise in a sector-restricted, thinner-than-full-universe sample. "
                       "User's explicit request: 'validate the finding' -- test each sector's train-"
                       "fitted formula on that SAME sector's own validation slice, the direct "
                       "out-of-sample check, before trusting any of R11-P8's per-sector numbers."),
        "category": "infrastructure",
        "configuration": {
            "files": ["pipeline/optimization_harness.py", "pipeline/run_backtest_suite.py",
                     "pipeline/tests/test_optimization_harness.py"],
            "change": ("optimization_harness.sector_candidate_report(panel, champion_weights, "
                       "trial_count=None, minimum_periods=6, extra_candidates=None): per sector, "
                       "fits formula_weights() on that sector's own Panel.train slice (filtered via "
                       "the existing filter_periods_by_sector), then evaluates it -- alongside "
                       "champion and an equal_weight control, plus any extra_candidates -- purely on "
                       "that SAME sector's Panel.validation slice, through the identical "
                       "walk_forward/evaluate_candidate apparatus (deflated Sharpe, same trial count) "
                       "every other candidate this round has been graded through. Never reads "
                       "panel.holdout. A sector with fewer than minimum_periods usable periods in "
                       "either its train or validation slice reports candidates: None rather than a "
                       "comparison built on too few names. New run_backtest_suite.py "
                       "--sector-candidate-check flag (fundamentals-only, composes with "
                       "--sector-breakdown/--metric-sector-breakdown in the same invocation), console "
                       "output one line per sector (champion vs sector_formula validation IC, "
                       "walk-forward efficiency, BEATS/does-not-beat verdict) -- full detail in "
                       "--harness-out."),
        },
        "train_period": None, "validation_period": None, "test_period": None,
        "metrics": {"tests_added": 5},
        "number_of_variants_tested": 1,
        "result": ("5 new tests: holdout never touched (mirrors OptimizationSession's own "
                   "test), a genuinely stable synthetic sector pattern (same relationship in both "
                   "train and validation) beats a deliberately mismatched champion on validation IC, "
                   "the minimum-period floor gates a thin sector to candidates: None, results sort "
                   "by validation IC descending, and extra_candidates flow through alongside champion "
                   "and the sector formula. Also ran the actual CLI end-to-end (not just the isolated "
                   "function) against a small fabricated panel with two sectors, each driven by a "
                   "different, deliberately-planted leg: --sector-candidate-check correctly reported "
                   "'Energy val_ic=0.2783 -> sector_formula val_ic=0.2912 -> BEATS champion' and "
                   "'Technology val_ic=0.0881 -> sector_formula val_ic=0.2886 -> BEATS champion', "
                   "matching the planted ground truth exactly -- confirming the flag wiring itself, "
                   "not just the underlying function in isolation. Full pipeline suite green after "
                   "the change."),
        "decision": "PROMOTE",
        "reason": ("Ships as tooling only -- same scope discipline as every other harness addition "
                   "this round, no production weight or promotion decision changed. This is the "
                   "actual answer to 'is R11-P8's per-sector finding noise': a sector where "
                   "sector_formula's validation-slice IC collapses relative to its train-slice IC "
                   "(walk_forward_efficiency near zero or negative) is the overfitting signature; "
                   "one where it holds up is real, generalizing evidence. Needs a real, "
                   "network-fetched panel rebuild (same standing constraint as R11-P7/P8) to run "
                   "against the user's actual per-sector findings -- not run against that real data "
                   "in this sandbox, only against synthetic ground-truth and a small fabricated "
                   "smoke-test panel."),
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
