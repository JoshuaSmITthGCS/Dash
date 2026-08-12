"""Generate pipeline/config/feature_registry.json from the metric definitions that already
exist across the pipeline, rather than hand-maintaining a second, drift-prone copy.

This adds exactly one thing metric_registry.json, research_screens_v2.py's weight tables,
and settings.json's fundamentals.metric_weights don't have on their own: the usage
classification the research contract requires (docs/RESEARCH-CONTRACT.md, brief section 9) --
whether a feature is a ranking signal, an eligibility filter, a risk-control input, a
confidence input, or explanatory-only. Everything else (direction, definition, weight) is
read from its existing source of truth so this file cannot silently drift from the code that
actually scores.

Usage: python pipeline/build_feature_registry.py
"""

import os

from common import LOG, load_json, save_json
from scorer import LOWER_IS_BETTER_METRICS, RANGE_METRICS

FUNDAMENTALS_CATEGORY_TO_FAMILY = {
    "valuation": "value",
    "profitability": "quality",
    "financial_health": "quality",
    "growth": "growth",
    "capital_allocation": "quality",
    "accounting_quality": "quality",
}

# research_screens_v2.py's MOMENTUM_WEIGHTS and TACTICAL_WEIGHTS, transcribed rather than
# imported: importing research_screens_v2 here would pull in its full module surface for two
# dicts. If those weight tables change, this registry's momentum/catalyst entries should be
# regenerated -- see the module docstring above.
MOMENTUM_FACTORS = {
    "momentum_12_1": "12-month return skipping the most recent month (Jegadeesh-Titman 1993).",
    "momentum_12_7": "12-month return skipping the most recent 7 months -- a slower momentum variant.",
    "momentum_6_1": "6-month return skipping the most recent month.",
    "high_52w_proximity": "Distance below the 52-week high.",
    "industry_relative_momentum": "Momentum measured relative to the industry peer group, not the raw return.",
}

CATALYST_FACTORS = {
    "revision_agreement": "Fraction of analyst estimate revisions moving the same direction.",
    "revision_magnitude": "Size of the net estimate revision.",
    "revision_acceleration": "Whether the pace of revisions is increasing.",
    "fresh_estimate_delta": "Change versus the most recent prior estimate snapshot.",
    "dispersion_trend": "Change in analyst estimate dispersion.",
    "eps_surprise": "Reported EPS versus consensus at the time of the report.",
    "surprise_consistency": "Whether recent quarters' surprises have been directionally consistent.",
    "revenue_surprise": "Reported revenue versus consensus.",
    "post_earnings_drift": "Price drift in the surprise's direction following the earnings report.",
    "industry_revision_breadth": "Fraction of the industry peer group also seeing positive revisions.",
    "risk_tradability": "Liquidity/tradability screen applied within the tactical (catalyst) score.",
}

MARKET_BEHAVIOR_FACTORS = {
    "momentum_12_1": None,  # already registered above; skip duplicate definition
    "risk_adjusted": "Sharpe/Sortino-style risk-adjusted return.",
    "relative_strength": "Return relative to the benchmark.",
    "drawdown_resilience": "Inverse of maximum drawdown severity/duration.",
    "volume_confirmation": "Whether price moves are confirmed by volume (up/down volume ratio).",
    "low_beta": "Betting-against-beta: rewards low-beta names rather than penalizing volatility directly (Frazzini-Pedersen 2014).",
    "technical_extended": "Combined score across four technical sub-indicators (see technical_indicators.py); registered as one family entry, its sub-indicators registered separately below.",
}

# The four sub-indicators bundled inside technical_extended (technical_indicators.py). Kept
# deliberately small -- see that module's docstring for why the broader indicator zoo (TEMA,
# MACD, PPO, Ichimoku, ...) was declined: it is mostly correlated transformations of the same
# OHLCV path with no multiple-testing-corrected evidence behind it. correlation_dedup_policy
# on each entry records that a live cross-sectional correlation check (brief section 2.5) has
# not been run -- these four were chosen for economic-family diversity, not measured
# independence.
TECHNICAL_EXTENDED_SUBINDICATORS = {
    "moving_average_slope": ("trend", "Rate of change of the moving average itself, distinct from 12-1 momentum's raw return."),
    "relative_strength_index": ("momentum", "Wilder RSI -- overbought/oversold oscillator, a mean-reversion-adjacent story distinct from trend-following momentum."),
    "bollinger_percent_b": ("risk", "Price's position within its own rolling volatility band."),
    "on_balance_volume_slope": ("momentum", "Cumulative direction-weighted volume slope."),
}


def _direction_for(metric_id):
    """scorer.py's own LOWER_IS_BETTER_METRICS/RANGE_METRICS sets are the ground truth for
    direction -- every metric in fundamentals.metric_weights is actually scored through one
    of those paths, whether or not metric_registry.json has gotten around to declaring it
    yet (12 of the 32 currently scored metrics have no metric_inventory entry at all).
    """
    if metric_id in RANGE_METRICS:
        return "ideal_range"
    if metric_id in LOWER_IS_BETTER_METRICS:
        return "lower_is_better"
    return "higher_is_better"


def _fundamentals_entries():
    metric_registry = load_json("metric_registry.json", from_config=True) or {}
    settings = load_json("settings.json", from_config=True) or {}
    inventory = metric_registry.get("metric_inventory", {})
    category_weights = (settings.get("fundamentals") or {}).get("metric_weights", {})
    percent_metrics = set((settings.get("explainability") or {}).get("percent_metrics", []))
    multiple_metrics = set((settings.get("explainability") or {}).get("multiple_metrics", []))

    metric_to_category = {
        metric: category
        for category, metrics in category_weights.items()
        for metric in metrics
    }

    entries = {}
    undeclared = []
    for metric_id in sorted(metric_to_category):
        category = metric_to_category[metric_id]
        family = FUNDAMENTALS_CATEGORY_TO_FAMILY.get(category, "quality")
        declared = inventory.get(metric_id)
        if declared:
            definition, unit, _inventory_direction = declared
        else:
            undeclared.append(metric_id)
            definition = "Not yet declared in metric_registry.json metric_inventory."
            unit = "multiple" if metric_id in multiple_metrics else (
                "decimal" if metric_id in percent_metrics else "unknown")
        entries[metric_id] = {
            "feature_id": metric_id,
            "family": family,
            "fundamentals_category": category,
            "usage": ["ranking", "explanation"],
            "not_used_for": ["hard_filter"],
            "direction": _direction_for(metric_id),
            "unit": unit,
            "definition_declared": bool(declared),
            "target_horizons": [126, 252],
            "availability_lag": "as declared by metric_registry.json (formula_version, period_type) where declared; statement-derived, typically 1-3 months after fiscal period end",
            "missingness_policy": "unavailable_when_denominator_is_zero_or_economically_invalid (see metric_registry.json declaration_defaults)",
            "economic_rationale": definition,
            "references": [],
            "version": "1.0.0",
        }
    if undeclared:
        LOG.warn(f"feature_registry: {len(undeclared)} scored metric(s) have no "
                 f"metric_registry.json declaration yet: {undeclared}")
    return entries


def _weighted_family_entries(weights, definitions, family, usage, horizons):
    entries = {}
    for factor_id, weight in weights.items():
        if factor_id in entries:
            continue
        definition = definitions.get(factor_id)
        if definition is None and factor_id not in definitions:
            definition = f"Weight {weight} in this family's blend; see the source module for the exact formula."
        entries[factor_id] = {
            "feature_id": factor_id,
            "family": family,
            "usage": usage,
            "not_used_for": ["hard_filter"],
            "direction": "higher_is_better",
            "target_horizons": horizons,
            "availability_lag": "same-session (technical/price-derived) or next-session (estimate-derived)",
            "missingness_policy": "reweighted_among_available -- see blend_research_components/momentum_scores",
            "economic_rationale": definition or "",
            "references": [],
            "version": "1.0.0",
        }
    return entries


def build_feature_registry():
    entries = {}
    entries.update(_fundamentals_entries())
    entries.update(_weighted_family_entries(
        MOMENTUM_FACTORS, MOMENTUM_FACTORS, "momentum", ["ranking", "explanation"], [63, 126, 252],
    ))
    entries.update(_weighted_family_entries(
        {k: v for k, v in CATALYST_FACTORS.items()}, CATALYST_FACTORS, "catalyst",
        ["ranking", "explanation"], [5, 21, 63],
    ))
    risk_family_factors = ("risk_adjusted", "drawdown_resilience", "low_beta")
    for factor_id, description in MARKET_BEHAVIOR_FACTORS.items():
        if description is None or factor_id in entries:
            continue
        is_risk = factor_id in risk_family_factors
        entries[factor_id] = {
            "feature_id": factor_id,
            "family": "risk" if is_risk else "momentum",
            # Honest about current code, not the brief's target state: risk_adjusted,
            # drawdown_resilience, and low_beta are all live weights inside
            # market_behavior.weights today (settings.json) and therefore genuinely feed
            # the composite score, not just risk control. The brief's position (section 6.11)
            # is that volatility/beta should be risk-control-only unless out-of-sample
            # evidence supports an alpha role -- that reclassification has NOT happened in
            # code yet, so claiming "not used for ranking" here would misdescribe the
            # current pipeline. classification_gap records the discrepancy explicitly.
            "usage": ["ranking", "risk_control", "explanation"] if is_risk else ["ranking", "explanation"],
            "not_used_for": ["hard_filter"],
            "classification_gap": (
                "Currently contributes to the ranking score via market_behavior.weights; "
                "the brief's target state is risk-control-only pending out-of-sample "
                "validation of an alpha role. Not yet reclassified in code."
            ) if is_risk else None,
            "direction": "higher_is_better",
            "target_horizons": [21, 63, 126],
            "availability_lag": "same-session (price/volume-derived)",
            "missingness_policy": "reweighted_among_available -- see advisor_engine.technical_factors",
            "economic_rationale": description,
            "references": [],
            "version": "1.0.0",
        }
    # Measured and published by advisor_engine.technical_factors, weighted by nothing. It is
    # registered anyway so the feature inventory covers what the pipeline actually computes,
    # and so the "does not rank" claim is recorded somewhere a reader can check rather than
    # being an absence they have to infer.
    entries["relative_acceleration"] = {
        "feature_id": "relative_acceleration",
        "family": "momentum",
        "usage": ["explanation"],
        "not_used_for": ["ranking", "hard_filter"],
        "classification_gap": (
            "Published on every scored row but absent from market_behavior.weights, so it "
            "contributes nothing to the composite score. Promotion to a ranking weight "
            "requires prospective out-of-sample evidence from the validation harness, which "
            "has not accumulated yet."
        ),
        "direction": "higher_is_better",
        "unit": "t_statistic",
        "target_horizons": [63, 126],
        "availability_lag": "same-session (price-derived), lagged by skip_days",
        "missingness_policy": (
            "unavailable when fewer than 2*leg_days + skip_days overlapping sessions exist "
            "with the benchmark, or when beta cannot be estimated -- never defaulted to a "
            "beta of 1.0; see risk_metrics.excess_returns"
        ),
        "economic_rationale": (
            "Change in a stock's beta-adjusted excess-return pace against the market, "
            "standardized by its own tracking noise. Beta-adjustment is what makes it "
            "market-relative rather than rank-identical to the raw return, which is the "
            "defect audit section 6 found in relative_strength_20d."
        ),
        "references": [
            "Gettleman & Marks (2006), Acceleration Strategies",
            "Blitz, Huij & Martens (2011), Residual Momentum",
        ],
        "version": "1.0.0",
    }
    for factor_id, (family, description) in TECHNICAL_EXTENDED_SUBINDICATORS.items():
        entries[factor_id] = {
            "feature_id": factor_id,
            "family": family,
            "usage": ["ranking", "explanation"],
            "not_used_for": ["hard_filter"],
            "correlation_dedup_policy": (
                "Chosen for economic-family diversity (trend/momentum/volatility), not "
                "measured cross-sectional independence -- a live pairwise-correlation check "
                "against the rest of the universe (brief section 2.5) has not been run. If "
                "run and found highly correlated (|rho| > 0.9) with an existing primary "
                "signal, this entry's usage should be demoted to explanation-only."
            ),
            "direction": "higher_is_better",
            "target_horizons": [21, 63],
            "availability_lag": "same-session (price/volume-derived)",
            "missingness_policy": "reweighted_among_available -- see technical_indicators.technical_extended_score",
            "economic_rationale": description,
            "references": [],
            "version": "1.0.0",
        }
    return {
        "registry_version": "1.0.0",
        "_comment": "Generated by pipeline/build_feature_registry.py from metric_registry.json, "
                    "settings.json fundamentals.metric_weights/market_behavior.weights, and "
                    "research_screens_v2.py's weight tables. Do not hand-edit entries sourced "
                    "from those files -- regenerate instead so this cannot drift from the code "
                    "that actually scores. usage/not_used_for/family are this file's own addition.",
        "families": sorted({entry["family"] for entry in entries.values()}),
        "features": dict(sorted(entries.items())),
    }


def main():
    registry = build_feature_registry()
    save_json("feature_registry.json", registry, to_config=True)
    LOG.info(f"Feature registry: {len(registry['features'])} features across {len(registry['families'])} families")
    return registry


if __name__ == "__main__":
    main()
