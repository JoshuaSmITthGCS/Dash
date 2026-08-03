"""Versioned structural/timeliness scoring without replacing the legacy model."""

from datetime import datetime, timezone

from canonical_metrics import (BUSINESS_PROFILES, METRIC_REGISTRY, applicability_for, calculate_peg,
                               classify_profile, reconcile)

MODEL_VERSION = "structural-timeliness-2.0.0"
CONFIG_VERSION = "canonical-metrics-2.0.0"


def _weighted(values):
    available = [(value, weight) for value, weight in values if value is not None]
    if not available:
        return None
    return sum(value * weight for value, weight in available) / sum(weight for _, weight in available)


def _classification(score, confidence):
    if confidence < 0.40:
        return "insufficient_evidence"
    if confidence < 0.60:
        return "review" if score < 50 else "watch"
    if score >= 75:
        return "strong_business"
    if score >= 60:
        return "quality_watch"
    if score >= 45:
        return "mixed"
    return "weak_business"


def _timeliness_classification(score, confidence):
    if confidence < 0.40:
        return "insufficient_evidence"
    if score >= 60:
        return "improving"
    if score < 45:
        return "weakening"
    return "stable"


def _observations_are_stale(metric_id, rows):
    ttl = (METRIC_REGISTRY["metrics"].get(metric_id) or {}).get("stale_after_days")
    dates = []
    for row in rows:
        stamp = row.get("fetched_at") or row.get("available_at") or row.get("observed_at")
        try:
            dates.append(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")))
        except (TypeError, ValueError):
            pass
    if not ttl or not dates:
        return False
    latest = max(date.astimezone(timezone.utc) for date in dates)
    return (datetime.now(timezone.utc) - latest).days > ttl


ALIASES = {
    "revenue_growth": "trailing_revenue_growth",
    "earnings_growth": "trailing_eps_growth",
}


def build_v2_analysis(snapshot, legacy_parts, observations=None, screen_memberships=None):
    observations = observations or snapshot.get("observations") or {}
    profile = classify_profile(snapshot)
    categories = {}
    metric_status = {}
    available_weight = applicable_weight = stale_weight = conflicted_weight = 0.0
    missing_metrics, suppressed_metrics, stale_metrics, provider_conflicts = [], [], [], []

    # The provider PEG field is diagnostic only. A PEG becomes canonical solely from
    # explicit forward inputs with a declared unit and matching period.
    canonical_peg = calculate_peg(
        snapshot.get("forward_pe"), snapshot.get("expected_eps_growth"),
        snapshot.get("expected_eps_growth_unit"),
        periods_match=snapshot.get("peg_periods_match", False),
        definition_known=snapshot.get("expected_growth_definition_known", False),
    )
    scored = dict(legacy_parts)
    scored["peg"] = None if canonical_peg is None else legacy_parts.get("peg")

    from scorer import SETTINGS  # local import avoids a scorer/advisor import cycle
    cfg = SETTINGS["fundamentals"]
    for category, weights in cfg["metric_weights"].items():
        contributions = []
        for legacy_id, weight in weights.items():
            metric_id = ALIASES.get(legacy_id, legacy_id)
            rule = applicability_for(metric_id, profile)
            share = cfg["category_weights"].get(category, 0) * weight
            status = rule["status"]
            value = scored.get(legacy_id)
            quality_flags = []
            source_rows = observations.get(metric_id, observations.get(legacy_id, []))
            if value is not None and not source_rows:
                quality_flags.append("legacy_value_missing_lineage")
                value = None
            reconciliation = reconcile(metric_id, source_rows) if source_rows else {"conflicts": []}
            if source_rows and reconciliation.get("canonical") is None:
                value = None
                quality_flags.append("no_valid_provider_observation")
            if reconciliation.get("invalid_observations"):
                quality_flags.append("provider_value_outside_valid_range")
            conflicts = [*reconciliation["conflicts"],
                         *[flag for row in source_rows for flag in row.get("quality_flags", []) if "conflict" in flag]]
            if legacy_id == "peg" and canonical_peg is None:
                status = "suppressed" if profile != "general" else "unavailable"
                reason = rule.get("reason") if profile != "general" else "No declared forward growth horizon/unit; provider PEG is not canonical."
                quality_flags.append("provider_peg_rejected")
            else:
                reason = rule.get("reason")
            if status in ("suppressed", "replaced"):
                suppressed_metrics.append(metric_id)
            else:
                applicable_weight += share
                if value is None:
                    missing_metrics.append(metric_id)
                    status = "unavailable"
                else:
                    available_weight += share
                    contributions.append((value, weight))
                    if _observations_are_stale(metric_id, source_rows):
                        stale_weight += share
                        stale_metrics.append(metric_id)
                        quality_flags.append("stale_observation")
            if conflicts:
                conflicted_weight += share
                provider_conflicts.append(metric_id)
                quality_flags.append("provider_conflict")
            metric_status[metric_id] = {
                "status": status,
                "value": canonical_peg if legacy_id == "peg" else snapshot.get(legacy_id),
                "score_contribution": value if status == "applied" else None,
                "replaced_by": rule.get("replaced_by"),
                "reason": reason,
                "quality_flags": sorted(set(quality_flags)),
            }
        value = _weighted(contributions)
        categories[category] = round(value, 1) if value is not None else None

    raw = _weighted((categories.get(name), weight) for name, weight in cfg["category_weights"].items())
    coverage = available_weight / applicable_weight if applicable_weight else 0.0
    # Reliability is distinct from availability. Legacy scalar fields lack dates/periods,
    # so they cannot receive full confidence even when present.
    provenance_reliability = 0.72 if observations else 0.55
    conflict_penalty = min(0.35, conflicted_weight / applicable_weight if applicable_weight else 0)
    stale_penalty = min(0.35, stale_weight / applicable_weight if applicable_weight else 0)
    confidence = max(0.0, min(1.0, coverage * provenance_reliability - conflict_penalty - stale_penalty))
    raw = 50.0 if raw is None else raw
    effective = 50 + confidence * (raw - 50)

    revision = snapshot.get("forward_eps_revision_30d")
    revision_score = None if revision is None else max(0.0, min(100.0, 50 + revision * 5))
    surprise = snapshot.get("earnings_surprise")
    surprise_score = None if surprise is None else max(0.0, min(100.0, 50 + surprise * 2))
    timing_values = [(revision_score, 0.7), (surprise_score, 0.3)]
    timing_raw = _weighted(timing_values)
    timing_coverage = sum(weight for value, weight in timing_values if value is not None)
    timing_confidence = timing_coverage * (0.85 if observations else 0.55)
    timing_raw_for_effective = 50 if timing_raw is None else timing_raw
    timing_effective = 50 + timing_confidence * (timing_raw_for_effective - 50)

    structural = {
        "raw_score": round(raw, 1),
        "effective_score": round(effective, 1),
        "confidence": round(confidence, 2),
        "coverage": round(coverage, 2),
        "coverage_basis": "answered_applicable_weight",
        "confidence_basis": "coverage_x_provenance_reliability_minus_stale_and_conflict_penalties",
        "available_weight": round(available_weight, 4),
        "applicable_weight": round(applicable_weight, 4),
        "stale_weight": round(stale_weight, 4),
        "conflicted_weight": round(conflicted_weight, 4),
        "missing_metrics": sorted(set(missing_metrics)),
        "suppressed_metrics": sorted(set(suppressed_metrics)),
        "stale_metrics": sorted(set(stale_metrics)),
        "provider_conflicts": sorted(set(provider_conflicts)),
        "classification": _classification(effective, confidence),
        "categories": categories,
    }
    timeliness = {
        "raw_score": None if timing_raw is None else round(timing_raw, 1),
        "effective_score": round(timing_effective, 1),
        "confidence": round(timing_confidence, 2),
        "coverage": round(timing_coverage, 2),
        "available_weight": round(timing_coverage, 2),
        "applicable_weight": 1.0,
        "stale_weight": 0.0,
        "conflicted_weight": 0.0,
        "missing_metrics": [name for name, value in (("forward_eps_revision_30d", revision), ("earnings_surprise", surprise)) if value is None],
        "suppressed_metrics": [],
        "stale_metrics": [],
        "provider_conflicts": [],
        "classification": _timeliness_classification(timing_effective, timing_confidence),
        "trailing_growth": {
            "revenue_growth": snapshot.get("revenue_growth"),
            "eps_growth": snapshot.get("earnings_growth"),
        },
        "forward": {
            "fy1_growth": snapshot.get("forward_fy1_growth"),
            "fy2_growth": snapshot.get("forward_fy2_growth"),
            "revision_7d": snapshot.get("forward_eps_revision_7d"),
            "revision_30d": revision,
            "revision_90d": snapshot.get("forward_eps_revision_90d"),
            "revision_acceleration": snapshot.get("revision_acceleration"),
            "analyst_count": snapshot.get("analyst_count"),
            "estimate_dispersion": snapshot.get("estimate_dispersion"),
            "earnings_surprise": surprise,
            "revenue_surprise": snapshot.get("revenue_surprise"),
            "guidance_direction": snapshot.get("guidance_direction"),
        },
    }
    profile_contract = (BUSINESS_PROFILES.get("profiles") or {}).get(profile, {})
    replacement_metrics = list(profile_contract.get("replacement_metrics") or [])
    unavailable_replacements = [metric for metric in replacement_metrics
                                if snapshot.get(metric) is None and not observations.get(metric)]
    critical = list(profile_contract.get("critical_metrics") or [])
    critical_gaps = [metric for metric in critical if snapshot.get(metric) is None and not observations.get(metric)]
    profile_confidence = (0.0 if not critical else (len(critical) - len(critical_gaps)) / len(critical))
    applied_metrics = sorted(metric for metric, detail in metric_status.items() if detail["status"] == "applied")
    return {
        "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION,
        "applicability_profile": profile,
        "structural": structural,
        "timeliness": timeliness,
        "company_classification": structural["classification"],
        "screen_memberships": list(screen_memberships or []),
        "position_action": None,
        "metric_status": metric_status,
        "applicability": {
            "profile_id": profile,
            "profile_confidence": round(profile_confidence, 3),
            "applied_metrics": applied_metrics,
            "suppressed_metrics": sorted(set(suppressed_metrics)),
            "replacement_metrics": replacement_metrics,
            "unavailable_replacement_metrics": unavailable_replacements,
            "critical_data_gaps": critical_gaps,
        },
        "canonical_metrics": {"peg": canonical_peg},
    }
