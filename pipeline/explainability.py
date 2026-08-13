"""Deterministic score attribution, metric context, history, and anomaly narration."""

from collections import defaultdict

from advisor_engine import RANKING_WEIGHTS
from common import load_json


SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS["explainability"]
FUNDAMENTALS = SETTINGS["fundamentals"]
MODIFIER_FIELDS = SETTINGS["validation"]["modifier_fields"]


def _weighted(values, weights):
    available = [(float(values[key]), float(weights[key])) for key in weights
                 if isinstance(values.get(key), (int, float))]
    if not available:
        return None
    return sum(value * weight for value, weight in available) / sum(weight for _, weight in available)


def _normalized_weights(values, weights):
    available = {key: float(weight) for key, weight in weights.items()
                 if isinstance(values.get(key), (int, float))}
    total = sum(available.values())
    return {key: weight / total for key, weight in available.items()} if total else {}


def score_attribution(variant, row, modifier_detail=None):
    """Decompose a published variant from neutral evidence through its exact final score."""
    variant = variant or {}
    components = variant.get("components") or row.get("components") or {}
    categories = variant.get("fundamental_categories") or row.get("fundamental_categories") or {}
    component_weights = _normalized_weights(components, RANKING_WEIGHTS)
    category_weights = _normalized_weights(categories, FUNDAMENTALS["category_weights"])
    raw_score = variant.get("raw_score")
    if not isinstance(raw_score, (int, float)):
        raw_score = _weighted(components, RANKING_WEIGHTS)
    raw_score = float(raw_score if raw_score is not None else CONFIG["attribution_base"])
    base_score = float(variant.get("base_score", raw_score))
    final_value = variant.get("score")
    if not isinstance(final_value, (int, float)):
        final_value = row.get("score")
    final_score = float(final_value if isinstance(final_value, (int, float)) else base_score)
    fundamental_score = components.get("fundamentals")
    fundamental_raw = _weighted(categories, FUNDAMENTALS["category_weights"])
    fundamental_adjustment = (
        float(fundamental_score) - fundamental_raw
        if isinstance(fundamental_score, (int, float)) and fundamental_raw is not None else 0.0
    )
    evidence = []
    for category, normalized_weight in category_weights.items():
        category_score = float(categories[category])
        points = component_weights.get("fundamentals", 0.0) * normalized_weight * (
            category_score - CONFIG["attribution_base"] + fundamental_adjustment
        )
        evidence.append({"key": category, "label": category.replace("_", " "), "points": points})
    for key in ("market_behavior", "news_sentiment"):
        if key in component_weights:
            evidence.append({
                "key": key,
                "label": "market behavior" if key == "market_behavior" else "news",
                "points": component_weights[key] * (float(components[key]) - CONFIG["attribution_base"]),
            })
    evidence_target = raw_score - CONFIG["attribution_base"]
    evidence_total = sum(line["points"] for line in evidence)
    if evidence:
        evidence[-1]["points"] += evidence_target - evidence_total
    for line in evidence:
        line["points"] = round(line["points"], 4)
    rounded_evidence_total = sum(line["points"] for line in evidence)
    if evidence:
        evidence[-1]["points"] = round(evidence[-1]["points"] + evidence_target - rounded_evidence_total, 4)

    modifier_detail = modifier_detail or variant.get("modifiers") or row.get("modifiers") or {}
    applied = modifier_detail.get("all_points") or modifier_detail.get("applied") or {}
    modifiers = [{"key": key, "label": key.replace("_", " "), "points": round(float(applied.get(key, 0.0)), 4)}
                 for key in MODIFIER_FIELDS]
    actual_modifier_delta = final_score - base_score
    modifier_total = sum(line["points"] for line in modifiers)
    modifiers.append({
        "key": "score_rounding",
        "label": "score boundary and rounding",
        "points": round(actual_modifier_delta - modifier_total, 4),
    })
    confidence_points = round(base_score - raw_score, 4)
    calculated = CONFIG["attribution_base"] + sum(line["points"] for line in evidence)
    calculated += confidence_points + sum(line["points"] for line in modifiers)
    error = round(calculated - final_score, 8)
    return {
        "base": CONFIG["attribution_base"],
        "evidence": evidence,
        "raw_evidence_score": round(raw_score, 4),
        "confidence_shrinkage_points": confidence_points,
        "post_confidence_score": round(base_score, 4),
        "modifiers": modifiers,
        "final_score": round(final_score, 4),
        "reconciliation_error": error,
        "reconciled": abs(error) <= CONFIG["reconciliation_tolerance"],
    }


def metric_explanations(variant, row, normalization_variant=None):
    categories = variant.get("fundamental_categories") or row.get("fundamental_categories") or {}
    metric_scores = variant.get("normalized_metric_scores") or {}
    normalization = ((normalization_variant or {}).get("fundamental_detail") or {}).get("normalization") or {}
    component_weights = _normalized_weights(
        variant.get("components") or row.get("components") or {}, RANKING_WEIGHTS,
    )
    category_weights = _normalized_weights(categories, FUNDAMENTALS["category_weights"])
    attribution = score_attribution(variant, row, variant.get("modifiers"))
    category_targets = {line["key"]: line["points"] for line in attribution["evidence"]}
    raw_score = attribution["raw_evidence_score"]
    confidence_scale = (
        (attribution["post_confidence_score"] - CONFIG["attribution_base"])
        / (raw_score - CONFIG["attribution_base"])
        if raw_score != CONFIG["attribution_base"] else 0.0
    )
    explanations = []
    for category, weights in FUNDAMENTALS["metric_weights"].items():
        available_weights = _normalized_weights(metric_scores, weights)
        if not available_weights or category not in category_targets:
            continue
        provisional = {
            metric: component_weights.get("fundamentals", 0.0)
                    * category_weights.get(category, 0.0)
                    * weight * (float(metric_scores[metric]) - CONFIG["attribution_base"])
            for metric, weight in available_weights.items()
        }
        residual = category_targets[category] - sum(provisional.values())
        for metric, weight in available_weights.items():
            context = normalization.get(metric) or {}
            raw_value = context.get("raw_value", row.get(
                "ev_to_sales" if metric == "sales_multiple" else metric
            ))
            evidence_points = provisional[metric] + weight * residual
            explanations.append({
                "metric": metric,
                "label": metric.replace("_", " "),
                "category": category,
                "raw_value": raw_value,
                "format": "percent" if metric in CONFIG["percent_metrics"] else
                          ("multiple" if metric in CONFIG["multiple_metrics"] else "number"),
                "sector_percentile": context.get("raw_percentile"),
                "desirability_percentile": context.get("desirability_percentile"),
                "normalization_scope": context.get("normalization_scope"),
                "peer_count": context.get("peer_count"),
                "direction": context.get("direction"),
                "own_history_percentile": context.get("own_history_percentile"),
                "own_history_observations": context.get("own_history_observations"),
                "own_history_years": context.get("own_history_years"),
                "own_history_status": context.get("own_history_status"),
                "normalized_score": metric_scores.get(metric),
                "evidence_point_contribution": round(evidence_points, 4),
                "final_point_contribution": round(evidence_points * confidence_scale, 4),
            })
    return sorted(explanations, key=lambda item: abs(item["final_point_contribution"]), reverse=True)


def factor_bars(row):
    categories = row.get("fundamental_categories") or {}
    technical = row.get("technical_detail") or {}
    components = row.get("components") or {}
    sources = {**categories, **technical, **components}
    bars = {}
    for factor, fields in CONFIG["factor_groups"].items():
        values = [float(sources[field]) for field in fields if isinstance(sources.get(field), (int, float))]
        bars[factor] = round(sum(values) / len(values), 1) if values else None
    return bars


def _condition_holds(row, condition):
    value = row.get(condition["metric"])
    if not isinstance(value, (int, float)):
        return False
    operator = condition["operator"]
    comparison = row.get(condition.get("compared_to")) if condition.get("compared_to") else condition.get("value")
    if not isinstance(comparison, (int, float)):
        return False
    return {
        "gt": value > comparison,
        "gte": value >= comparison,
        "lt": value < comparison,
        "lte": value <= comparison,
        "lt_metric": value < comparison,
        "gt_metric": value > comparison,
    }.get(operator, False)


def anomaly_flags(row):
    return [{"id": rule["id"], "severity": rule["severity"], "message": rule["message"]}
            for rule in CONFIG["anomaly_rules"]
            if all(_condition_holds(row, condition) for condition in rule["conditions"])]


def stance_band(score, confidence=None):
    if isinstance(confidence, (int, float)) and confidence < CONFIG["minimum_stance_confidence"]:
        return "INSUFFICIENT DATA"
    for band in CONFIG["stance_bands"]:
        if isinstance(score, (int, float)) and score >= band["minimum"]:
            return band["label"]
    return None


def build_score_history(rows):
    grouped = defaultdict(list)
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        scores = row.get("scores") or {}
        data_coverage = row.get("data_coverage") or {}
        categories = row.get("category_scores") or {}
        grouped[ticker].append({
            "recorded_at": row.get("recorded_at"),
            "refresh_id": row.get("refresh_id"),
            "champion_score": scores.get("champion"),
            "challenger_score": scores.get("challenger"),
            "champion_stance": stance_band(scores.get("champion"), data_coverage.get("champion")),
            "challenger_stance": stance_band(scores.get("challenger"), data_coverage.get("challenger")),
            "category_scores": categories,
        })
    result = {}
    for ticker, points in grouped.items():
        points.sort(key=lambda item: str(item.get("recorded_at") or ""))
        months = sorted({str(point.get("recorded_at") or "")[:7] for point in points if point.get("recorded_at")})
        driver = None
        if len(months) >= CONFIG["score_history_minimum_months"] and len(points) >= 2:
            first = (points[0].get("category_scores") or {}).get("champion") or {}
            last = (points[-1].get("category_scores") or {}).get("champion") or {}
            changes = [(key, float(last[key]) - float(first[key])) for key in first
                       if isinstance(first.get(key), (int, float)) and isinstance(last.get(key), (int, float))]
            if changes:
                driver = max(changes, key=lambda item: abs(item[1]))
        result[ticker] = {
            "status": "available" if len(months) >= CONFIG["score_history_minimum_months"] else "accumulating",
            "stored_months": len(months),
            "required_months": CONFIG["score_history_minimum_months"],
            "points": points,
            "largest_category_driver": (
                {"category": driver[0], "change": round(driver[1], 1)} if driver else None
            ),
        }
    return result


def attach_explainability(row, history=None):
    variants = row.get("score_variants") or {}
    champion = variants.get("champion") or row
    challenger = variants.get("challenger") or variants.get("normalization")
    normalization_variant = variants.get("normalization") or challenger
    champion_attribution = score_attribution(champion, row, row.get("modifiers"))
    challenger_attribution = score_attribution(
        challenger, row, (challenger or {}).get("modifiers")
    ) if challenger and isinstance(challenger.get("score"), (int, float)) else None
    row["explainability"] = {
        "active_variant": "champion",
        "attribution": {
            "champion": champion_attribution,
            "challenger": challenger_attribution,
        },
        "factor_bars": factor_bars(row),
        "metrics": {
            "champion": metric_explanations(champion, row, normalization_variant),
            "challenger": metric_explanations(challenger, row, normalization_variant)
                          if challenger and isinstance(challenger.get("score"), (int, float)) else [],
        },
        "score_history": history or {
            "status": "accumulating", "stored_months": 0,
            "required_months": CONFIG["score_history_minimum_months"], "points": [],
        },
        "anomalies": anomaly_flags(row),
    }
    return row


def attribution_errors(rows):
    failures = []
    for row in rows:
        ticker = row.get("ticker")
        for variant, attribution in ((row.get("explainability") or {}).get("attribution") or {}).items():
            if attribution and abs(attribution.get("reconciliation_error", 1)) > CONFIG["reconciliation_tolerance"]:
                failures.append({"ticker": ticker, "variant": variant,
                                 "error": attribution.get("reconciliation_error")})
    return failures
