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
        # Sub-dispatch by declared property type. Self-storage, data-center, net-lease and
        # timber REITs share ambiguous Yahoo industry strings with other specialty/industrial/
        # diversified REITs (there is no distinguishing substring), so those four are resolved
        # exclusively via ticker_overrides above, before we ever reach this text match. Anything
        # not covered below (REIT - Diversified, REIT - Specialty, and any unmatched property
        # type) falls back to the generic "reit" profile, same as before this split existed.
        if "residential" in industry:
            return "residential_reit"
        if "office" in industry:
            return "office_reit"
        if "retail" in industry:
            return "retail_reit"
        if "healthcare" in industry:
            return "healthcare_reit"
        if "hotel" in industry or "motel" in industry or "lodging" in industry:
            return "hotel_reit"
        if "mortgage" in industry:
            return "mortgage_reit"
        if "industrial" in industry:
            return "industrial_reit"
        return "reit"
    if "bank" in industry:
        return "bank"
    # Ahead of the generic insurance branch: "Insurance Brokers" contains "insurance" and was
    # falling into diversified_insurer, which assumes underwriting risk and investment float a
    # broker never carries -- a real misclassification, not just a missing profile.
    if "broker" in industry and "insurance" in text:
        return "insurance_broker"
    # Also ahead of the generic insurance branch: a health-plan filer's industry string is
    # typically "Healthcare Plans", which contains no "insurance" substring at all, but some
    # providers do label it "Health Insurance" -- checked here so either spelling lands on the
    # managed-care profile rather than (in the second case) diversified_insurer.
    if "healthcare plan" in industry or "managed care" in text or "health insurance" in text:
        return "managed_care_insurer"
    # Also ahead of the generic insurance branch: reinsurance economics (large, lumpy per-event
    # losses ceded from primary carriers; no direct policyholder relationship) are close enough
    # to property_casualty_insurer's catastrophe exposure to inherit its rules, but the industry
    # string ("Insurance - Reinsurance") would otherwise fall through to diversified_insurer.
    if "reinsurance" in industry:
        return "reinsurer"
    if "insurance" in text:
        if "life" in industry:
            return "life_insurer"
        if any(term in industry for term in ("property", "casualty", "p&c")):
            return "property_casualty_insurer"
        return "diversified_insurer"
    if "utilit" in sector:
        # Merchant/independent power producers sit in the same GICS sector as regulated
        # utilities but earn nothing like a rate base -- checked first so "Utilities" alone
        # doesn't default them into the regulated profile.
        if "independent power" in industry or "power producer" in industry:
            return "independent_power_producer"
        # CAFD/tax-equity economics (accelerated depreciation, non-cash HLBV allocations
        # distorting GAAP EPS) are a different problem from independent_power_producer's
        # merchant commodity-price exposure, not a generalization of it -- not $inherits'd.
        if "renewable" in industry:
            return "renewable_yieldco_developer"
        # Water utilities trade at a persistent scarcity/ESG premium the regulated-electric
        # multiple bands were not calibrated for -- checked ahead of the plain fallback below.
        if "water" in industry:
            return "water_utility"
        return "utility"
    # Ahead of the generic commodity-producer branch: "Oil & Gas Midstream" contains "gas" and
    # would otherwise be caught by the oil/gas check below, which assumes upstream/production
    # economics a pipeline-and-storage tolling business does not have.
    if "midstream" in industry or "pipeline" in industry:
        return "midstream_mlp"
    # Ahead of the commodity-producer chemical match just below: "Specialty Chemicals" also
    # contains "chemical", but formulation/IP-driven specialty chemistry (and, in this
    # taxonomy, industrial gases -- Linde/Air Products/Air Liquide ADRs have no separate
    # industry code) commands a premium, stable multiple and gets none of commodity_producer's
    # cyclical suppression. A handful of names classify here by industry string but trade like
    # true commodity producers (lithium converters such as Albemarle); those are corrected via
    # ticker_overrides rather than by inventing a fake distinguishing substring.
    if "specialty chemical" in industry:
        return "specialty_chemicals"
    if any(term in text for term in ("oil", "gas", "mining", "gold", "copper", "steel", "coal",
                                     "uranium", "chemical", "aluminum", "paper", "packaging",
                                     "agricultural input", "fertilizer")):
        return "commodity_producer"
    if "airline" in industry:
        return "airline"
    if "aerospace" in industry or "defense" in industry:
        return "aerospace_defense"
    # Long-cycle industrials: each below is checked as a flat, mutually-exclusive block of
    # compound industry-string matches -- none contain "construction" alone (which would wrongly
    # catch "Farm & Heavy Construction Machinery" or the existing residential-construction
    # check above) or any commodity/airline/aerospace term already resolved above.
    if "specialty industrial machinery" in industry or "farm & heavy construction machinery" in industry:
        return "machinery"
    if "electrical equipment & parts" in industry:
        return "electrical_equipment"
    if "building products & equipment" in industry or "building materials" in industry:
        return "building_products"
    if "engineering & construction" in industry:
        return "engineering_construction"
    if "railroads" in industry:
        return "railroad"
    if "trucking" in industry:
        return "trucking"
    if "integrated freight & logistics" in industry:
        return "air_freight_logistics"
    if "marine shipping" in industry:
        return "marine_shipping"
    if "waste management" in industry:
        return "waste_management"
    if "staffing & employment services" in industry:
        return "staffing"
    if "consulting services" in industry:
        return "consulting_services"
    if "industrial distribution" in industry:
        return "industrial_distribution"
    if "capital markets" in industry or "investment banking" in industry:
        return "capital_markets"
    if "asset management" in industry:
        return "asset_manager"
    # Exchanges earn fee-per-transaction/data-subscription revenue with no balance-sheet credit
    # or underwriting risk -- neither a bank's nor an asset manager's economics, but closer to
    # capital_markets' fee-driven model than to anything else already resolved above.
    if "financial data & stock exchanges" in industry:
        return "financial_exchange"
    # Card-network and consumer-lending economics (revolving receivables, charge-offs). Visa,
    # Mastercard and several other payment processors are also filed by Yahoo under "Credit
    # Services" despite taking no consumer credit risk themselves -- resolved via
    # ticker_overrides (checked before any text match), not by inventing a distinguishing
    # substring here.
    if "credit services" in industry:
        return "consumer_finance"
    if "residential construction" in industry or "homebuilding" in industry:
        return "homebuilder"
    # Ahead of the generic semiconductor branch below: capital-equipment makers (ASML/AMAT/
    # LRCX/KLAC) sell tooling into the fab cycle rather than fabricating or designing chips --
    # bookings and litho-cycle timing drive results, not wafer volumes, though the same
    # cyclical capex/inventory suppression logic applies, so this inherits semiconductor rather
    # than duplicating it.
    if "semiconductor equipment" in industry or "semiconductor materials" in industry:
        return "semiconductor_capital_equipment"
    # Ahead of the generic profit-margin branches: a semiconductor company's capex and
    # inventory cycles are not readable through industrial cutoffs regardless of whether it
    # is currently profitable.
    if "semiconductor" in text:
        return "semiconductor"
    # Contract manufacturing/distribution: thin margins, high asset turns -- not readable
    # through semiconductor's fab-cycle lens.
    if "electronics & computer distribution" in industry:
        return "ems_electronic_components"
    if "communication equipment" in industry:
        return "networking_equipment"
    # SaaS: checked ahead of the biotech/pre-profit fallback below (and ahead of "general") so a
    # pre-profit subscription software company doesn't fall into other_pre_profit, which was
    # built around biotech/early-stage burn economics, not deferred-revenue subscription
    # economics.
    if "software - application" in industry or "software - infrastructure" in industry:
        return "saas"
    if "information technology services" in industry:
        return "it_services_consulting"
    # Ahead of the biotech/pre-profit fallback below: each of these is a distinct healthcare
    # sub-industry with its own economics, not a company that merely happens to be
    # profitable or not. Checked as flat industry-string matches; none contain "biotech".
    if "drug manufacturers - general" in industry:
        return "large_cap_pharma"
    if "medical devices" in industry or "medical instruments & supplies" in industry:
        return "medical_devices"
    if "diagnostics & research" in industry:
        return "life_science_tools_diagnostics"
    if "medical distribution" in industry:
        return "pharmacy_healthcare_distribution"
    if "health information services" in industry:
        return "healthcare_it"
    # Communication Services and Consumer Discretionary/Staples sub-industries: each checked as
    # a flat, mutually-exclusive industry-string match, ahead of the biotech/pre-profit
    # fallback below and "general" so none of these silently default into either.
    if "telecom services" in industry:
        return "telecom_carrier"
    if "entertainment" in industry:
        return "media_entertainment"
    if "internet content & information" in industry:
        return "interactive_media_platform"
    if "electronic gaming & multimedia" in industry:
        return "video_games"
    if any(term in industry for term in ("publishing", "broadcasting", "advertising agencies")):
        return "publishing_advertising"
    if any(term in industry for term in ("apparel retail", "apparel manufacturing", "footwear & accessories", "luxury goods")):
        return "retail_apparel"
    if "restaurants" in industry:
        return "restaurants"
    if "internet retail" in industry:
        return "ecommerce_retail"
    if "auto manufacturers" in industry:
        return "automaker"
    if "auto & truck dealerships" in industry:
        return "auto_dealership"
    if "auto parts" in industry:
        return "auto_parts_supplier"
    if "leisure" in industry or "recreational vehicles" in industry:
        return "leisure_products"
    if "education & training services" in industry:
        return "education_services"
    if "farm products" in industry:
        return "agricultural_processor"
    if "packaged foods" in industry:
        return "packaged_food_processor"
    if "beverages" in industry:
        return "beverage_manufacturer"
    if "tobacco" in industry:
        return "tobacco"
    if "food distribution" in industry:
        return "food_distributor"
    if "grocery stores" in industry or "discount stores" in industry:
        return "grocery_staples_retail"
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
