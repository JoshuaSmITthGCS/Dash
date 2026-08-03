"""Canonical metric normalization, applicability and provider reconciliation (v2)."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")


def _load(name):
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as handle:
        return json.load(handle)


METRIC_REGISTRY = _load("metric_registry.json")
APPLICABILITY = _load("applicability_matrix.json")
RECONCILIATION = _load("provider_reconciliation.json")
BUSINESS_PROFILES = _load("business_profiles.json")

# Inventory declarations inherit only mechanical contract defaults; definitions,
# units and scoring directions remain metric-specific in the central registry file.
for _metric_id, (_definition, _unit, _direction) in METRIC_REGISTRY.get("metric_inventory", {}).items():
    if _metric_id in METRIC_REGISTRY["metrics"]:
        continue
    _declaration = dict(METRIC_REGISTRY["declaration_defaults"])
    _declaration.update({
        "human_label": _metric_id.replace("_", " ").title(),
        "definition": _definition,
        "formula_version": f"{_metric_id}.v2",
        "required_normalized_inputs": [_metric_id],
        "accepted_units": [_unit],
        "output_unit": _unit,
        "direction": _direction,
    })
    METRIC_REGISTRY["metrics"][_metric_id] = _declaration


@dataclass(frozen=True)
class Observation:
    value: Any
    unit: str
    source: str
    source_field: str
    period_start: str | None = None
    period_end: str | None = None
    available_at: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None
    fiscal_period: str | None = None
    is_ttm: bool = False
    is_forward: bool = False
    quality_flags: list[str] = field(default_factory=list)
    transform_version: str = "identity.v1"

    def to_dict(self):
        return asdict(self)


def normalize_percentage_points(value, unit):
    """Normalize a declared decimal or percentage-point growth rate."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if unit == "decimal":
        return value * 100
    if unit == "percentage_points":
        return value
    return None


def calculate_peg(forward_pe, growth, growth_unit, *, periods_match=True, definition_known=True):
    """Canonical PEG. Unknown definitions, bad periods and nonpositive growth are unavailable."""
    try:
        pe = float(forward_pe)
    except (TypeError, ValueError):
        return None
    growth_points = normalize_percentage_points(growth, growth_unit)
    if (not math.isfinite(pe) or pe <= 0 or growth_points is None or growth_points <= 0
            or not periods_match or not definition_known):
        return None
    result = pe / growth_points
    return round(result, 4) if -20 <= result <= 50 else None


def classify_profile(snapshot):
    override = BUSINESS_PROFILES.get("ticker_overrides", {}).get(str(snapshot.get("ticker") or "").upper(), {})
    if override.get("profile"):
        return override["profile"]
    sector = str(snapshot.get("sector") or "").lower()
    industry = str(snapshot.get("industry") or "").lower()
    text = f"{sector} {industry}"
    if snapshot.get("is_etf"):
        return "etf"
    if "reit" in text or "real estate investment trust" in text:
        return "reit"
    if "bank" in industry:
        return "bank"
    if "insurance" in text:
        if "life" in industry:
            return "life_insurer"
        if any(term in industry for term in ("property", "casualty", "p&c")):
            return "property_casualty_insurer"
        return "diversified_insurer"
    if "utilit" in sector:
        return "utility"
    if any(term in text for term in ("oil", "gas", "mining", "gold", "copper", "steel", "coal")):
        return "commodity_producer"
    pre_profit = snapshot.get("profit_margin") is not None and snapshot.get("profit_margin") < 0
    if pre_profit and "biotech" in text:
        return "pre_profit_biotechnology"
    if "biotech" in text:
        return "profitable_biotechnology"
    if pre_profit:
        return "other_pre_profit"
    return "general"


def profile_rules(profile):
    rules = dict(APPLICABILITY["rules"].get(profile, {}))
    parent = rules.pop("$inherits", None)
    if parent:
        rules = {**profile_rules(parent), **rules}
    return rules


def applicability_for(metric_id, profile):
    if profile == "etf":
        return {"status": "suppressed", "replaced_by": None, "reason": "Corporate metric does not apply to ETFs."}
    rule = profile_rules(profile).get(metric_id)
    if rule:
        return {"status": rule[0], "replaced_by": rule[1], "reason": rule[2]}
    registry = METRIC_REGISTRY["metrics"].get(metric_id)
    if registry and profile not in registry.get("applicability_profiles", []):
        return {"status": "suppressed", "replaced_by": None, "reason": "Metric registry does not declare this profile applicable."}
    return {"status": "applied", "replaced_by": None, "reason": None}


def reconcile(metric_id, observations):
    """Preserve all observations and choose by configured precedence; never average."""
    policy = RECONCILIATION["canonical_fields"].get(metric_id, {})
    preferred = policy.get("preferred_sources", [])
    numeric_range = (METRIC_REGISTRY["metrics"].get(metric_id) or {}).get("valid_numeric_range")
    invalid = []
    valid = []
    for row in observations:
        value = row.get("value")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            invalid.append({"source": row.get("source"), "value": value, "reason": "not_numeric"})
            continue
        if not math.isfinite(numeric) or (numeric_range and not numeric_range[0] <= numeric <= numeric_range[1]):
            invalid.append({"source": row.get("source"), "value": value, "reason": "outside_valid_range"})
            continue
        valid.append(row)
    valid.sort(key=lambda row: preferred.index(row.get("source")) if row.get("source") in preferred else len(preferred))
    chosen = valid[0] if valid else None
    conflicts = []
    tolerance = policy.get("discrepancy_tolerance_pct", 0)
    if chosen:
        for row in valid[1:]:
            try:
                denominator = max(abs(float(chosen["value"])), 1e-12)
                discrepancy = abs(float(row["value"]) - float(chosen["value"])) / denominator * 100
            except (TypeError, ValueError):
                continue
            if discrepancy > tolerance:
                conflicts.append({"source": row.get("source"), "value": row.get("value"),
                                  "discrepancy_pct": round(discrepancy, 2)})
    return {
        "canonical": chosen,
        "observations": observations,
        "conflicts": conflicts,
        "invalid_observations": invalid,
        "policy": policy.get("on_disagreement", "use_only_observation"),
        "confidence_penalty": min(0.5, 0.1 * len(conflicts)),
    }


def yahoo_observations(info, fetched_at=None):
    """Raw Yahoo fields with explicit semantics. Ambiguous PEG is retained but not canonical."""
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    specs = {
        "price": ("currentPrice", "usd", False, False),
        "market_cap": ("marketCap", "usd", False, False),
        "forward_pe": ("forwardPE", "multiple", False, True),
        "provider_peg": ("trailingPegRatio", "multiple", False, False),
        "current_ratio": ("currentRatio", "multiple", False, False),
        "price_to_book": ("priceToBook", "multiple", False, False),
        "trailing_revenue_growth": ("revenueGrowth", "decimal", True, False),
        "quarterly_eps_growth": ("earningsGrowth", "decimal", True, False),
    }
    result = {}
    for metric_id, (source_field, unit, is_ttm, is_forward) in specs.items():
        value = info.get(source_field)
        if value is None:
            continue
        flags = [] if metric_id in ("price", "market_cap") else ["provider_period_not_supplied"]
        if metric_id == "provider_peg":
            flags.append("unknown_growth_definition_and_horizon")
        if metric_id == "quarterly_eps_growth":
            flags.append("not_forward_growth")
        result.setdefault(metric_id, []).append(Observation(
            value=value, unit=unit, source="yahoo", source_field=source_field,
            observed_at=fetched_at, fetched_at=fetched_at, is_ttm=is_ttm,
            is_forward=is_forward, quality_flags=flags,
        ).to_dict())
    return result
