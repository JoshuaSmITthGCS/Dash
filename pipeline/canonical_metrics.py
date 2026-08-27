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
    # Ahead of the general REIT branch: a mortgage REIT holds a leveraged securities
    # portfolio and distributes net interest spread income, not property NOI, so FFO/AFFO
    # (the equity-REIT earnings measure the general "reit" profile suppresses P/E in favor
    # of) does not describe it. Book value and leverage are its anchors instead.
    if "reit" in text and "mortgage" in industry:
        return "mortgage_reit"
    if "reit" in text or "real estate investment trust" in text:
        return "reit"
    # Ahead of the bank branch: Yahoo's "Capital Markets" and "Asset Management" industries
    # do not contain the substring "bank", so ordering relative to the bank check below does
    # not matter for those two -- but both are fee/AUM-driven businesses (no inventory or
    # receivables, enterprise value is not the standard multiple) that a generic industrial
    # or bank ruleset misreads.
    if industry in ("capital markets", "asset management"):
        return "capital_markets_firm"
    if "bank" in industry:
        return "bank"
    if "insurance" in text:
        if "life" in industry:
            return "life_insurer"
        if any(term in industry for term in ("property", "casualty", "p&c")):
            return "property_casualty_insurer"
        return "diversified_insurer"
    # Ahead of the generic profit-margin/industrial branches: land-banking and long build
    # cycles make homebuilder EPS and inventory turns cycle-distorted the same way a
    # commodity producer's are, but "residential construction" does not match any of the
    # commodity keywords below.
    if "residential construction" in industry:
        return "homebuilder"
    # Ahead of the utility branch: Yahoo already separates "Utilities - Independent Power
    # Producers" from the regulated-electric/gas/water industries, and the two are not
    # interchangeable -- a regulated utility's rate base and allowed-ROE framework does not
    # exist for a merchant generator selling into spot power and capacity markets, which is
    # commodity-cyclical like the producers below instead.
    if "independent power producer" in industry:
        return "independent_power_producer"
    if "utilit" in sector:
        return "utility"
    if any(term in text for term in ("oil", "gas", "mining", "gold", "copper", "steel", "coal",
                                      "lumber", "packaging", "agricultural inputs")):
        return "commodity_producer"
    # "Chemicals" (commodity/diversified) is cycle-driven the same way as the producers
    # above; "Specialty Chemicals" is a formulation-value business with structurally higher,
    # steadier multiples, so it is excluded rather than swept in by a bare "chemical" match.
    if "chemical" in industry and "specialty" not in industry:
        return "commodity_producer"
    # Ahead of the generic profit-margin branches: a semiconductor company's capex and
    # inventory cycles are not readable through industrial cutoffs regardless of whether it
    # is currently profitable.
    if "semiconductor" in text:
        return "semiconductor"
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


# The legacy scorer and the v2 layer name three metrics differently. Applicability is one
# authority, so a rule or registry declaration written under either name must govern both:
# without this, an explicit ``sales_multiple`` suppression never fired on the v2 path (which
# asked about ``price_to_sales``) and the registry's ``trailing_revenue_growth`` declaration
# never reached the legacy path (which asked about ``revenue_growth``).
LEGACY_ALIASES = {
    "revenue_growth": "trailing_revenue_growth",
    "earnings_growth": "trailing_eps_growth",
    "sales_multiple": "price_to_sales",
}
_CANONICAL_ALIASES = {canonical: legacy for legacy, canonical in LEGACY_ALIASES.items()}


def _alias_counterpart(metric_id):
    return LEGACY_ALIASES.get(metric_id) or _CANONICAL_ALIASES.get(metric_id)


def applicability_for(metric_id, profile):
    if profile == "etf":
        return {"status": "suppressed", "replaced_by": None, "reason": "Corporate metric does not apply to ETFs."}
    rules = profile_rules(profile)
    counterpart = _alias_counterpart(metric_id)
    rule = rules.get(metric_id) or (rules.get(counterpart) if counterpart else None)
    if rule:
        return {"status": rule[0], "replaced_by": rule[1], "reason": rule[2]}
    registry = METRIC_REGISTRY["metrics"].get(metric_id)
    if registry is None and counterpart:
        registry = METRIC_REGISTRY["metrics"].get(counterpart)
    if registry and profile not in registry.get("applicability_profiles", []):
        return {"status": "suppressed", "replaced_by": None, "reason": "Metric registry does not declare this profile applicable."}
    return {"status": "applied", "replaced_by": None, "reason": None}


def suppressed_metrics(profile, metric_ids):
    """Metrics this business profile cannot be meaningfully scored on.

    The live scorer used two hardcoded tuples (``FINANCIAL_EXEMPT``,
    ``TANGIBLE_BOOK_SECTORS``) keyed off Yahoo's sector string, while the registry's correct
    per-profile rules governed only the shadow path. That is why an insurer's DSO trend was
    scored at 80/100 with 215 receivable days published beside it, and why its price-to-book
    and debt-to-equity -- the two canonical insurer inputs -- were forced to null. One
    authority now serves both paths: this delegates to ``applicability_for`` so the explicit
    matrix rules *and* the registry's per-profile declarations govern the legacy path too,
    under either metric-ID namespace. Previously only the explicit rules were checked here,
    so a registry-declared inapplicability (an insurer's revenue growth) stayed scored on
    the champion while the shadow path suppressed it.
    """
    if profile == "etf":
        return set(metric_ids)
    return {metric_id for metric_id in metric_ids
            if applicability_for(metric_id, profile)["status"] in ("suppressed", "replaced")}


def required_for_score(profile, category):
    """Metrics whose absence prevents ``category`` from publishing for this profile.

    Renormalizing a category onto whatever happened to resolve is right for a *minor*
    missing input and wrong for a defining one. An insurer's valuation without price-to-book
    is not a thin valuation reading, it is not a valuation reading.
    """
    declared = APPLICABILITY.get("required_for_score", {}).get(profile, {})
    return tuple(declared.get(category, ()))


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
        "price_to_sales": ("priceToSalesTrailing12Months", "multiple", True, False),
        "return_on_equity": ("returnOnEquity", "decimal", True, False),
        "profit_margin": ("profitMargins", "decimal", True, False),
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

    # Yahoo reports debt-to-equity as a percentage (80 means 0.8x); every other consumer of
    # this field (the flat snapshot value, the legacy scorer) expects the ratio itself.
    debt_to_equity_pct = info.get("debtToEquity")
    if debt_to_equity_pct is not None:
        result["debt_to_equity"] = [Observation(
            value=debt_to_equity_pct / 100, unit="multiple", source="yahoo",
            source_field="debtToEquity", observed_at=fetched_at, fetched_at=fetched_at,
            is_ttm=False, is_forward=False, quality_flags=["provider_period_not_supplied"],
        ).to_dict()]

    free_cash_flow, market_cap = info.get("freeCashflow"), info.get("marketCap")
    if free_cash_flow is not None and market_cap:
        result["free_cash_flow_yield"] = [Observation(
            value=free_cash_flow / market_cap, unit="decimal", source="yahoo",
            source_field="freeCashflow/marketCap", observed_at=fetched_at, fetched_at=fetched_at,
            is_ttm=True, is_forward=False, quality_flags=["provider_period_not_supplied"],
        ).to_dict()]
    return result
