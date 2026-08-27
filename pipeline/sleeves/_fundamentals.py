"""Shared wrapper for sleeves built directly from one or more scorer.py fundamental
categories (value, quality, growth). Not a public sleeve itself -- see value.py, quality.py,
growth.py for the sleeves that use this.

Extracted after the second near-identical sleeve (growth) started duplicating value.py's
~50 lines; a third (quality) would have made that three copies of the same coverage/warning/
explanation logic with only the family and subscore categories differing.
"""

from common import load_json
from scorer import valuation_score
from sleeves import empty_sleeve, ineligible_sleeve


def _family_metric_ids(family):
    registry = load_json("feature_registry.json", from_config=True) or {}
    return sorted(
        feature_id for feature_id, entry in registry.get("features", {}).items()
        if entry.get("family") == family
    )


def score_fundamentals_family_sleeve(sleeve_id, family, subscore_categories, version,
                                     target_horizon_days, snapshot, as_of=None):
    """Score one company against one or more scorer.py fundamental categories, reshaped into
    the sleeve contract. ``subscore_categories`` are the scorer.py category keys (e.g.
    ("valuation",) for value, ("profitability", "financial_health", "capital_allocation",
    "accounting_quality") for quality) whose scores populate ``subscores``.
    """
    if snapshot.get("is_etf"):
        return ineligible_sleeve(sleeve_id, version, target_horizon_days, ["unsupported_security_type"])

    score, detail = valuation_score(snapshot)
    metric_ids = _family_metric_ids(family)
    result = empty_sleeve(sleeve_id, version, target_horizon_days, as_of)

    if score is None:
        result["eligibility"] = {"eligible": False, "reasons": ["missing_provider_data"]}
        result["warnings"].append("No fundamental category resolved for this snapshot.")
        return result

    raw_features = {metric_id: snapshot.get(metric_id) for metric_id in metric_ids}
    sales_basis = detail.get("sales_multiple_basis")
    if "sales_multiple" in raw_features and sales_basis:
        raw_features["sales_multiple"] = snapshot.get(sales_basis)
    normalized_features = {metric_id: detail.get(metric_id) for metric_id in metric_ids}
    categories = detail.get("categories", {})

    # Confidence is answered-share of what could apply to this profile, not of the whole
    # family: a metric this company's business profile suppresses (detail["suppressed_metrics"],
    # the same registry scorer.valuation_score already consulted) is never going to resolve and
    # must leave the denominator entirely, the same way scorer.weighted_coverage already treats
    # it. Counting it as unresolved evidence understated confidence for every business profile
    # with any suppressed value-family metric -- a bank's forward_pe/peg, a REIT's price_to_ffo
    # for a non-REIT -- not just the metric that happened to expose it here.
    suppressed = set(detail.get("suppressed_metrics") or ())
    applicable_metric_ids = [metric_id for metric_id in metric_ids if metric_id not in suppressed]
    resolved = sum(1 for metric_id in applicable_metric_ids if raw_features.get(metric_id) is not None)

    result["raw_features"] = raw_features
    result["normalized_features"] = normalized_features
    result["subscores"] = {category: categories.get(category) for category in subscore_categories}
    resolved_subscores = [value for value in result["subscores"].values() if value is not None]
    result["raw_score"] = round(sum(resolved_subscores) / len(resolved_subscores), 1) if resolved_subscores else None
    result["confidence"] = round(resolved / len(applicable_metric_ids), 2) if applicable_metric_ids else None
    if resolved == 0:
        result["eligibility"] = {"eligible": False, "reasons": ["missing_provider_data"]}
    elif applicable_metric_ids and resolved < len(applicable_metric_ids) // 2:
        result["warnings"].append(
            f"Only {resolved}/{len(applicable_metric_ids)} applicable {family} metrics resolved for this company.")
    negative_denominator_flags = [
        metric_id for metric_id in ("ev_to_ebitda", "ev_to_ebit", "ev_to_fcf")
        if raw_features.get(metric_id) is not None and raw_features[metric_id] <= 0
    ]
    if negative_denominator_flags:
        result["warnings"].append(
            f"Non-positive denominator excluded from scoring: {', '.join(negative_denominator_flags)}"
        )
    result["explanation"] = [
        f"{metric_id}: raw={raw_features[metric_id]}, normalized={normalized_features[metric_id]}"
        for metric_id in metric_ids
        if raw_features.get(metric_id) is not None
    ]
    return result
