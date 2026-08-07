"""A durable record of every research attempt, including the failures.

Two problems this solves.

**Rediscovery.** Without a registry, an idea that was tried and rejected gets tried again by
whoever forgets. The most expensive version of that is re-running a search that already failed
and stopping at the run that happens to look good.

**Honest deflation.** `evaluation.deflated_sharpe_ratio` and
`probability_of_backtest_overfitting` both take a trial count, and understating it is the
single most common way a deflated Sharpe gets quietly re-inflated. That count has to come from
somewhere durable. It comes from here: `total_variants_tested()` sums the variants across every
recorded experiment, so the deflation reflects the whole research programme rather than the one
configuration being written up.

Entries are append-or-update by id and carry their own evidence status, so a blocked experiment
is recorded as blocked rather than omitted -- an absent experiment and a failed one are
different facts.

Usage: python pipeline/experiment_registry.py   (rebuilds the registry from RECORDED)
Output: pipeline/reports/experiment_registry.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT_PATH = os.path.join(HERE, "reports", "experiment_registry.json")

RESULTS = {"supported", "rejected", "inconclusive", "blocked"}
DECISIONS = {"promote", "retain_shadow", "abandon", "pending_data", "shipped_as_fix"}
CATEGORIES = {"diagnostic", "corrective"}


def entry(*, id, hypothesis, category, result, decision, reason, model_version="3.2.0",
          configuration=None, training_period=None, validation_period=None, test_period=None,
          metrics=None, number_of_variants_tested=0, artifacts=None):
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
    if result not in RESULTS:
        raise ValueError(f"result must be one of {sorted(RESULTS)}")
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    if number_of_variants_tested < 0:
        raise ValueError("number_of_variants_tested must be non-negative")
    return {
        "id": id,
        "hypothesis": hypothesis,
        "category": category,
        "model_version": model_version,
        "configuration": configuration or {},
        "training_period": training_period,
        "validation_period": validation_period,
        "test_period": test_period,
        "metrics": metrics or {},
        "number_of_variants_tested": number_of_variants_tested,
        "result": result,
        "decision": decision,
        "reason": reason,
        "artifacts": artifacts or [],
    }


# Every experiment run against this system to date, including the ones that produced nothing.
# Backfilled from docs/P0-*.md and this session's work so the trial count is honest rather than
# starting from whatever was measured most recently.
RECORDED = [
    entry(
        id="wo1-manifest-reports-champion",
        hypothesis="run_manifest.score_distribution describes the shadow v2 score, not the "
                   "published champion, so the manifest certifies a different model than shipped",
        category="corrective",
        configuration={"file": "pipeline/observability.py"},
        metrics={"published_mean_before": 68.85, "published_mean_after": 75.05,
                 "affected_committed_manifests": 14},
        number_of_variants_tested=1,
        result="supported",
        decision="shipped_as_fix",
        reason="confirmed by reading the source and by regenerating the manifest from the "
               "committed artifact; the buggy distribution undershot the real range by 7-11 "
               "points at every quantile",
        artifacts=["docs/P0-REPAIRS.md"],
    ),
    entry(
        id="wo2-sec-insider-layer",
        hypothesis="the Form 4 insider layer is dark solely because SEC_USER_AGENT is unset",
        category="diagnostic",
        configuration={"file": "pipeline/sec_edgar.py"},
        number_of_variants_tested=1,
        result="blocked",
        decision="pending_data",
        reason="the gate is confirmed to be the single environment variable, but no refresh "
               "can run from an environment with no route to sec.gov; the secret's value is "
               "the repository owner's action, outside any commit",
        artifacts=["docs/P0-REPAIRS.md"],
    ),
    entry(
        id="wo3-tiered-costs-wired",
        hypothesis="a realistic tiered cost model materially changes net performance at 64.9% "
                   "monthly turnover",
        category="corrective",
        configuration={"cost_model": "tiered", "scenarios": ["optimistic", "base", "stress"]},
        number_of_variants_tested=3,
        result="blocked",
        decision="pending_data",
        reason="costs.py is wired into both backtest_monthly.py and ic_harness.py and proved "
               "equivalent to the old flat rate by default, but the three-regime re-run needs "
               "five years of daily price and volume history for ~860 names",
        artifacts=["docs/P0-REPAIRS.md", "pipeline/reports/cost_regime_comparison.json"],
    ),
    entry(
        id="q1-benchmark-and-factor-regression",
        hypothesis="the strategy's SPY shortfall is a benchmark artifact, and residual alpha "
                   "survives controlling for the six factors the model is built from",
        category="diagnostic",
        configuration={"benchmarks": ["SPY", "RSP", "IWM"], "factors": 6,
                       "standard_errors": "newey_west_3_lag"},
        validation_period="2021-09..2026-06",
        metrics={"annualized_alpha_pct": -2.57, "newey_west_t": -0.437, "r_squared": 0.589,
                 "capm_beta": 0.793, "market_t": 6.50, "size_t": 2.06, "momentum_t": 2.50},
        number_of_variants_tested=2,
        result="rejected",
        decision="abandon",
        reason="half supported, half rejected. SPY is genuinely the wrong yardstick -- the "
               "strategy beats RSP and IWM on CAGR. But no residual alpha survives the "
               "six-factor control, at |t| = 0.437, well inside the brief's own 'no residual "
               "alpha' band. The significant loadings are market, size and momentum, not the "
               "value and profitability the score is built from",
        artifacts=["docs/P0-Q1-BENCHMARK.md", "pipeline/reports/factor_regression_p0.json"],
    ),
    entry(
        id="q2-turnover-attribution",
        hypothesis="band quantization drives the 64.9% monthly turnover, so a continuous "
                   "normalizer would materially reduce it",
        category="diagnostic",
        configuration={"source": "pipeline/pit_store/*.jsonl", "transitions": 4},
        metrics={"band_crossing_share": 0.0042, "genuine_change_share": 0.0286,
                 "availability_flicker_share": 0.9672},
        number_of_variants_tested=1,
        result="rejected",
        decision="abandon",
        reason="the leading hypothesis is probably wrong. Band crossings on effectively "
               "unchanged inputs are the smallest bucket at 0.42%; metric availability "
               "flicker dominates at 96.72%. Measured at the refresh-to-refresh horizon, not "
               "the monthly one, so it shifts the prior rather than settling the question",
        artifacts=["docs/P0-Q2-TURNOVER.md", "pipeline/reports/turnover_attribution.json"],
    ),
    entry(
        id="news-weight-is-inert",
        hypothesis="the 4% news component is neutral for essentially the whole universe and so "
                   "moves score levels without ordering anything",
        category="corrective",
        configuration={"file": "pipeline/news_intelligence.py",
                       "change": "return None instead of the neutral score when uncovered"},
        metrics={"names_at_neutral_before": "373 of 374", "mean_score_delta": 1.005,
                 "maximum_score_delta": 1.40, "names_changing_rank_position": 10},
        number_of_variants_tested=1,
        result="supported",
        decision="shipped_as_fix",
        reason="confirmed against the last published refresh. The weight now leaves the "
               "denominator when there is no coverage, which raises uncovered names above 50 "
               "and lowers those below it -- removing a pull toward neutral in both directions",
        artifacts=["pipeline/reports/news_availability_impact.json"],
    ),
    entry(
        id="enrichment-shortlist-bias",
        hypothesis="shortlist gating materially changes which names can reach the top of the "
                   "ranking",
        category="diagnostic",
        configuration={"source": "2026-08-06 full-universe refresh",
                       "research_mode": "FULL_UNIVERSE_RESEARCH"},
        metrics={"universe_enrichment_rate": 0.397, "top_100_enriched_share": 1.0,
                 "mean_score_gap": 25.29, "non_statement_category_gap_range": "11.8..19.8"},
        number_of_variants_tested=1,
        result="inconclusive",
        decision="pending_data",
        reason="the structural half is settled -- no unenriched name reaches the top 100, and "
               "two categories worth 20% of the fundamental weight cannot contribute for 60% "
               "of the universe. The cost is not: the score gap is mostly circular, since "
               "enriched names already lead on the categories needing no enrichment. The "
               "unseeded comparison needs network access",
        artifacts=["docs/ENRICHMENT-BIAS-ANALYSIS.md", "pipeline/reports/enrichment_bias.json"],
    ),
    entry(
        id="tradeable-benchmark-suite",
        hypothesis="the strategy delivers something a liquid style ETF could not",
        category="diagnostic",
        configuration={"benchmarks": 14, "standard_errors": "newey_west_3_lag"},
        validation_period="2021-09..2026-07",
        metrics={"beaten_on_cagr": "9 of 14", "significant_positive_alpha_count": 0,
                 "largest_absolute_t": 1.11, "vtv_sharpe": 0.899, "strategy_sharpe": 0.611},
        number_of_variants_tested=14,
        result="rejected",
        decision="abandon",
        reason="no benchmark in the set is beaten with statistically significant alpha. VTV "
               "returns more at lower volatility with a shallower drawdown -- a user could "
               "have bought the ETF instead",
        artifacts=["pipeline/reports/benchmark_comparison.json"],
    ),
    entry(
        id="cost-sensitivity-at-realized-turnover",
        hypothesis="a realistic cost model gives up more than 200bps a year relative to the "
                   "published flat 10bps",
        category="diagnostic",
        configuration={"method": "re-price recorded turnover across every costs.py rate"},
        metrics={"mean_monthly_turnover": 0.649, "breakeven_one_way_bps": 35.7,
                 "worst_modelled_one_way_bps": 25.0, "worst_additional_drag_bps": 116.9},
        number_of_variants_tested=9,
        result="rejected",
        decision="pending_data",
        reason="the spread-and-fee floor does not cross the threshold at 64.9% turnover; the "
               "breakeven rate is ~36bps and the model's worst case without a volatility "
               "input is 25bps. Adding the omitted market-impact term could still cross it",
        artifacts=["pipeline/reports/cost_sensitivity.json"],
    ),
    entry(
        id="turnover-controls",
        hypothesis="rank buffering, a minimum holding period, score smoothing or a "
                   "replacement margin improves net-of-cost return by suppressing trades that "
                   "act on noise",
        category="corrective",
        configuration={"rank_buffer": [1.25, 1.5, 2.0], "minimum_holding_months": [1, 3, 6],
                       "score_smoothing_alpha": [0.5, 0.7], "replacement_margin": [2.0, 5.0]},
        number_of_variants_tested=10,
        result="blocked",
        decision="pending_data",
        reason="all four are implemented as challengers behind flags that default to the "
               "champion's plain top-N selection, and each is proved to behave exactly as "
               "specified. Whether any improves net return needs a backtest re-run over ~860 "
               "names of daily history",
        artifacts=["pipeline/portfolio_construction.py"],
    ),
    entry(
        id="regime-conditional-performance",
        hypothesis="the strategy's edge is stable across market, volatility and rate regimes",
        category="diagnostic",
        configuration={"regimes": ["market_direction", "volatility", "rates"],
                       "defined_from": "benchmark and macro series only, fixed before "
                                       "inspecting strategy performance"},
        validation_period="2021-09..2026-07",
        metrics={"bear_excess_pp": 10.3, "bull_excess_pp": -11.2,
                 "rising_rates_excess_pp": -16.9, "falling_rates_excess_pp": 10.3},
        number_of_variants_tested=3,
        result="rejected",
        decision="retain_shadow",
        reason="the edge is not stable -- it is a duration and direction bet. The book is "
               "defensive in drawdowns and in falling rates and lags badly in rising rates "
               "and high volatility. Useful for describing the strategy honestly; not "
               "actionable as a timing overlay without out-of-sample evidence",
        artifacts=["pipeline/reports/strategy_diagnostics.json"],
    ),
    entry(
        id="forecast-target-correction",
        hypothesis="measuring raw calendar-day forward returns instead of the contract's "
                   "63-session sector-residual target changes what the IC statistics mean",
        category="corrective",
        configuration={"horizon_basis": "trading_sessions", "primary_horizon_sessions": 63,
                       "target": "residual_forward_return"},
        number_of_variants_tested=1,
        result="supported",
        decision="shipped_as_fix",
        reason="the medians coincide (63 sessions spans 91 calendar days) which is why the "
               "gap went unnoticed, but a fixed calendar horizon spans a varying session "
               "count, so label length drifted. Sector residualization changes the ranking "
               "outright: the best raw performer can be the worst residual performer",
        artifacts=["docs/RESEARCH-CONTRACT.md"],
    ),
]


def total_variants_tested(entries=None):
    """The honest trial count for Deflated Sharpe and PBO."""
    return sum(item["number_of_variants_tested"] for item in (entries or RECORDED))


def build_report(entries=None):
    entries = list(entries if entries is not None else RECORDED)
    identifiers = [item["id"] for item in entries]
    duplicates = sorted({key for key in identifiers if identifiers.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate experiment ids: {duplicates}")
    by_result = {}
    for item in entries:
        by_result.setdefault(item["result"], []).append(item["id"])
    return {
        "schema_version": 1,
        "purpose": ("a durable record of every research attempt, so failed ideas are not "
                    "rediscovered and the trial count feeding Deflated Sharpe and PBO reflects "
                    "the whole programme rather than the configuration being written up"),
        "experiments": entries,
        "summary": {
            "experiments": len(entries),
            "total_variants_tested": total_variants_tested(entries),
            "by_result": {key: sorted(value) for key, value in sorted(by_result.items())},
            "blocked_on_network_access": sorted(
                item["id"] for item in entries if item["decision"] == "pending_data"),
            "promoted_to_champion": sorted(
                item["id"] for item in entries if item["decision"] == "promote"),
        },
    }


def main():
    report = build_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    summary = report["summary"]
    print(f"{summary['experiments']} experiments, "
          f"{summary['total_variants_tested']} variants tested in total")
    for result, ids in summary["by_result"].items():
        print(f"  {result:<13} {len(ids)}  {', '.join(ids)}")
    print(f"promoted to champion: {summary['promoted_to_champion'] or 'none'}")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
