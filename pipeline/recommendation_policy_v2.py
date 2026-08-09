"""Shadow-only recommendation policy with independent company and position decisions.

This module does not replace ``advisor_engine.action_for``.  It publishes a versioned
comparison object so the policy can be observed and backtested before promotion.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(HERE, "config", "recommendation_policy_v2.json")

COMPANY_DISPLAY_LABELS = {
    "buy": "BUY CANDIDATE", "accumulate": "ACCUMULATE", "quality_watch": "QUALITY WATCH",
    "tactical_candidate": "TACTICAL CANDIDATE", "hold_existing_position": "HOLD EXISTING POSITION",
    "watch": "WATCH FOR ENTRY", "avoid": "AVOID NEW ENTRY", "sell_thesis": "SELL THESIS",
    "insufficient_evidence": "INSUFFICIENT EVIDENCE",
}
POSITION_DISPLAY_LABELS = {
    "no_action": "NO ACTION", "hold": "NO ACTION", "trim": "TRIM", "exit": "EXIT", "review": "REVIEW",
}


def load_policy(path=DEFAULT_CONFIG_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _number(value, default=None):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def effective_score(raw_score, confidence):
    """Shrink uncertain scores toward neutral; all company actions use this score."""
    raw = _number(raw_score, 50.0)
    return round(50.0 + _clamp(_number(confidence, 0.0)) * (raw - 50.0), 1)


def _score_layer(layer):
    """Normalize a layer, preserving ``None`` for a layer that did not resolve.

    A layer with no raw score has no effective score. Substituting a neutral here is what
    made the timeliness axis a universe-wide constant that the matrix below then branched
    on -- see ``research/audit/CURRENT_MODEL_AUDIT.md`` section 3.
    """
    layer = layer or {}
    confidence = _clamp(_number(layer.get("evidence_weight_resolved"), 0.0))
    raw = _number(layer.get("raw_score"))
    return {
        **layer,
        "raw_score": raw,
        "effective_score": None if raw is None else effective_score(raw, confidence),
        "evidence_weight_resolved": round(confidence, 3),
        "coverage": round(_clamp(_number(layer.get("coverage"), 0.0)), 3),
    }


def two_axis_classification(structural_score, timeliness_score, cfg):
    """Classify on both axes, or on structural alone when timeliness did not resolve.

    ``timeliness_score is None`` is a distinct state from a low timeliness score: it means
    the timing evidence was never obtained, not that timing looks poor. The
    ``*_timeliness_unavailable`` classifications say exactly that, and deliberately never
    reach ``buy_candidate`` -- a structural score alone cannot establish that now is a
    favourable time to enter.
    """
    matrix = cfg["score_matrix"]
    if structural_score is None:
        return "insufficient_structural_evidence"
    if timeliness_score is None:
        if structural_score >= matrix["structural_strong"]:
            return "quality_watch_timeliness_unavailable"
        if structural_score >= matrix["structural_acceptable"]:
            return "hold_or_watch_timeliness_unavailable"
        return "avoid_or_sell_thesis"
    if structural_score >= matrix["structural_strong"]:
        if timeliness_score >= matrix["timeliness_buy"]:
            return "buy_candidate"
        if timeliness_score >= matrix["timeliness_acceptable"]:
            return "accumulate_or_watch"
        return "quality_watch"
    if structural_score >= matrix["structural_acceptable"]:
        if timeliness_score >= matrix["timeliness_tactical"]:
            return "tactical_candidate"
        if timeliness_score >= matrix["timeliness_weak"]:
            return "hold_or_watch"
        return "avoid_new_entry_or_trim"
    if timeliness_score >= matrix["timeliness_tactical"]:
        return "speculative_tactical_only"
    return "avoid_or_sell_thesis"


def _quality(analysis):
    """Data-quality summary across the layers that actually resolved.

    ``score_confidence`` and ``data_coverage`` are minima over *assessed* layers only. Taking
    the minimum across an unresolved layer as well pinned both to zero for every company in
    the universe, which is what drove ``insufficient_evidence`` on 40 of 40 published rows
    while structural coverage sat at 92%. An unresolved layer is reported through
    ``unassessed_layers`` and the matrix classification, not by zeroing a number that is about
    something else.
    """
    structural = analysis.get("structural") or {}
    timeliness = analysis.get("timeliness") or {}
    layers = {"structural": structural, "timeliness": timeliness}
    assessed = {name: layer for name, layer in layers.items()
                if layer.get("effective_score") is not None}
    missing = sorted(set((structural.get("missing_metrics") or []) + (timeliness.get("missing_metrics") or [])))
    stale = sorted(set((structural.get("stale_metrics") or []) + (timeliness.get("stale_metrics") or [])))
    conflicts = sorted(set((structural.get("provider_conflicts") or []) + (timeliness.get("provider_conflicts") or [])))
    return {
        "unassessed_layers": sorted(set(layers) - set(assessed)),
        "evidence_weight_resolved": round(min((_number(layer.get("evidence_weight_resolved"), 0) for layer in assessed.values()),
                                              default=0.0), 3),
        "data_coverage": round(min((_number(layer.get("coverage"), 0) for layer in assessed.values()),
                                   default=0.0), 3),
        "data_freshness": "stale" if stale else "current_or_unknown",
        "provider_conflicts": conflicts,
        "applicable_metrics_available": round(_number(structural.get("available_weight"), 0) + _number(timeliness.get("available_weight"), 0), 4),
        "stale_metrics": stale,
        "missing_critical_metrics": missing,
        "severe_unresolved": bool(conflicts or stale),
    }


def _critical_field_gaps(profile, analysis, config):
    required = config["critical_fields"].get(profile, config["critical_fields"]["general"])
    declared = analysis.get("critical_fields_available") or {}
    timeliness = analysis.get("timeliness") or {}
    timing_missing = set(timeliness.get("missing_metrics") or [])
    gaps = []
    for field in required:
        if field == "forward_estimates":
            has_revision = "forward_eps_revision_30d" not in timing_missing and timeliness.get("raw_score") is not None
            if not has_revision:
                gaps.append(field)
        elif not declared.get(field, False):
            gaps.append(field)
    return gaps


def _signal(reason_code, severity, confidence, persistence=2, shared=False):
    return {
        "reason_code": reason_code,
        "severity": _clamp(severity),
        "confidence": _clamp(confidence),
        "persistence_periods": max(0, int(persistence)),
        "shared": bool(shared),
    }


def derive_deterioration_groups(analysis, technical=None, sentiment=None, extended=None, overrides=None, config=None):
    """Assign each observation to one primary thesis group.

    Cost-basis loss, trailing stop, drawdown from a user's high-water mark, and portfolio
    drawdown deliberately do not enter this function.
    """
    config = config or load_policy()
    rule = config["deterioration"]
    structural = analysis.get("structural") or {}
    categories = structural.get("categories") or {}
    technical, sentiment, extended = technical or {}, sentiment or {}, extended or {}
    candidates = {"business_fundamentals": [], "market_behavior": [], "positioning_sentiment": []}

    category_map = {
        "profitability": "profitability_weak",
        "financial_health": "financial_health_weak",
        "accounting_quality": "accounting_quality_weak",
        "growth": "business_growth_weak",
    }
    for key, code in category_map.items():
        value = _number(categories.get(key))
        if value is not None and value < 45:
            candidates["business_fundamentals"].append(
                _signal(code, (45 - value) / 45, structural.get("confidence", 0), 2)
            )

    return_20 = _number(technical.get("return_20d"))
    return_60 = _number(technical.get("return_60d"))
    relative = _number(technical.get("relative_strength_20d"))
    volume = _number(technical.get("volume_ratio_60d"))
    technical_conf = _number(technical.get("coverage"), 0)
    if return_20 is not None and return_60 is not None and return_20 < 0 and return_60 < -15:
        candidates["market_behavior"].append(_signal("sustained_price_trend_negative", abs(return_60) / 40, technical_conf, 2))
    if relative is not None and relative < -10:
        candidates["market_behavior"].append(_signal("relative_strength_negative", abs(relative) / 25, technical_conf, 2))
    if volume is not None and volume < 0.70:
        candidates["market_behavior"].append(_signal("downside_volume_confirmation", (0.70 - volume) / 0.70, technical_conf, 2))

    article_count = int(_number(sentiment.get("article_count"), 0))
    average = _number(sentiment.get("average"))
    sentiment_conf = _number(sentiment.get("coverage"), 0)
    if average is not None and average < -0.15 and article_count >= 3:
        candidates["positioning_sentiment"].append(_signal("persistent_negative_news", abs(average) / 0.5, sentiment_conf, 2))
    short_float = _number(extended.get("short_percent_of_float"))
    if short_float is not None and short_float >= 0.15:
        candidates["positioning_sentiment"].append(_signal("crowded_short_positioning", short_float / 0.30, 0.7, 2))

    for group, values in (overrides or {}).items():
        if group in candidates:
            candidates[group] = list(values)

    result = []
    for group, signals in candidates.items():
        eligible = [s for s in signals if s.get("confidence", 0) >= rule["minimum_metric_confidence"]]
        weighted = [s["severity"] * (rule["shared_signal_weight"] if s.get("shared") else 1.0) for s in eligible]
        severity = sum(weighted) / len(weighted) if weighted else 0.0
        confidence = sum(s["confidence"] for s in eligible) / len(eligible) if eligible else 0.0
        persistence = min((s["persistence_periods"] for s in eligible), default=0)
        distinct = len({s["reason_code"] for s in eligible})
        flagged = (
            severity >= rule["group_flag_threshold"]
            and distinct >= rule["minimum_distinct_subfactors"]
            and persistence >= rule["minimum_persistence_periods"]
        )
        state = "deteriorating" if flagged else ("mixed" if eligible else "stable_or_unavailable")
        result.append({
            "group": group,
            "state": state,
            "flagged": flagged,
            "score": round(100 * (1 - severity), 1),
            "direction": "negative" if eligible else "neutral",
            "severity": round(_clamp(severity), 3),
            "confidence": round(_clamp(confidence), 3),
            "freshness": "current_or_unknown",
            "persistence_periods": persistence,
            "reason_codes": [s["reason_code"] for s in eligible],
            "signals": eligible,
        })
    return result


def _thesis_break(events, config):
    rule = config["thesis_break"]
    for event in events or []:
        if (
            event.get("code") in rule["allowed_codes"]
            and event.get("source")
            and event.get("timestamp")
            and event.get("explanation")
            and _number(event.get("confidence"), 0) >= rule["minimum_confidence"]
            and _number(event.get("materiality"), 0) >= rule["minimum_materiality"]
        ):
            return event
    return None


def _company_action(matrix_class, quality, position_exists, thesis_break, config):
    gates = config["confidence_gates"]
    confidence = quality["evidence_weight_resolved"]
    if thesis_break:
        return "sell_thesis", "sell_thesis_" + thesis_break["code"], [thesis_break["code"]]
    if confidence < gates["insufficient"]:
        return "insufficient_evidence", "company_data_quality", ["company_confidence_below_0_40"]
    if confidence < gates["normal"]:
        return ("hold_existing_position" if position_exists else "watch"), "company_data_quality", ["company_confidence_below_0_60"]
    mapping = {
        "buy_candidate": "buy",
        "accumulate_or_watch": "accumulate" if position_exists else "watch",
        "quality_watch": "hold_existing_position" if position_exists else "quality_watch",
        "tactical_candidate": "tactical_candidate",
        "hold_or_watch": "hold_existing_position" if position_exists else "watch",
        "avoid_new_entry_or_trim": "hold_existing_position" if position_exists else "avoid",
        "speculative_tactical_only": "tactical_candidate",
        "avoid_or_sell_thesis": "avoid",
        # Timeliness never resolved. A strong business with no timing evidence is a
        # watch-list entry, never a buy -- structural quality alone does not establish
        # that now is a favourable moment to enter.
        "quality_watch_timeliness_unavailable": "hold_existing_position" if position_exists else "quality_watch",
        "hold_or_watch_timeliness_unavailable": "hold_existing_position" if position_exists else "watch",
        "insufficient_structural_evidence": "insufficient_evidence",
    }
    action = mapping[matrix_class]
    if quality["severe_unresolved"] and action in ("buy", "accumulate"):
        return "watch", "company_data_quality", ["severe_unresolved_data_quality"]
    return action, "company_matrix", [matrix_class]


def classify_portfolio_fit(portfolio, config):
    portfolio = portfolio or {}
    rule = config["portfolio"]
    current = _number(portfolio.get("current_weight"), 0.0)
    target = _number(portfolio.get("target_weight"), rule["default_target_weight"])
    maximum = _number(portfolio.get("maximum_weight"), rule["default_max_weight"])
    if current > maximum * rule["severely_overweight_ratio"]:
        classification = "severely_overweight"
    elif current > max(maximum, target * rule["materially_overweight_ratio"]):
        classification = "overweight"
    elif current < target * 0.75:
        classification = "below_target"
    else:
        classification = "near_target"
    reasons = []
    if classification in ("overweight", "severely_overweight"):
        reasons.append("position_above_target")
    if _number(portfolio.get("sector_weight"), 0) > rule["maximum_sector_weight"]:
        reasons.append("sector_concentration_limit")
    if _number(portfolio.get("theme_weight"), 0) > rule["maximum_theme_weight"]:
        reasons.append("theme_concentration_limit")
    if portfolio.get("look_through_overlap_breached"):
        reasons.append("etf_look_through_overlap")
    if portfolio.get("factor_concentration_breached"):
        reasons.append("factor_concentration_limit")
    if portfolio.get("marginal_risk_limit_breached"):
        reasons.append("marginal_risk_limit")
    return {
        "current_weight": round(current, 5), "target_weight": round(target, 5),
        "maximum_weight": round(maximum, 5), "classification": classification,
        "sector_weight": portfolio.get("sector_weight"), "theme_weight": portfolio.get("theme_weight"),
        "liquidity": portfolio.get("liquidity", "unknown"), "correlation": portfolio.get("correlation"),
        "marginal_contribution_to_risk": portfolio.get("marginal_contribution_to_risk"),
        "reason_codes": reasons,
    }


def _stop_state(position, config):
    if not position:
        return {"classification": "no_position", "profile": None, "rules": {}}
    profile_name = position.get("stop_profile", "default")
    profile = config["stop_profiles"].get(profile_name, config["stop_profiles"]["default"])
    if profile.get("mode") == "none":
        return {"classification": "disabled_by_strategy", "profile": profile_name, "rules": {}}
    current = _number(position.get("current_price"))
    cost = _number(position.get("weighted_cost_basis"))
    high = _number(position.get("adjusted_high_water_mark"))
    price_fresh = position.get("price_fresh", True)
    rules = {}
    if current is None or not price_fresh:
        return {"classification": "unassessed_stale_or_missing_price", "profile": profile_name, "rules": rules}
    if cost and profile.get("hard_cost_basis_pct") is not None:
        threshold = cost * (1 + profile["hard_cost_basis_pct"] / 100)
        rules["hard_cost_basis_stop"] = {
            "triggered": current <= threshold, "threshold_price": round(threshold, 4), "current_price": current,
            "high_water_mark": high, "breach_amount": round(max(0, threshold - current), 4),
            "breach_percentage": round((current / threshold - 1) * 100, 3),
            "first_breached_at": position.get("hard_stop_first_breached_at"),
            "confirmed_at": position.get("hard_stop_confirmed_at"),
            "required_persistence": profile.get("persistence_closes", 1),
            "persistence_rule": f"{profile.get('persistence_closes', 1)} confirming closes",
            "execution_policy": position.get("execution_policy", "next_liquid_close"),
            "action": "exit", "discretionary": False,
        }
    threshold = None
    mode = profile.get("mode")
    if high and mode == "atr_based" and _number(position.get("atr"), 0) > 0:
        threshold = high - profile.get("atr_multiple", 3.0) * position["atr"]
    elif high and mode == "volatility_adjusted" and _number(position.get("realized_volatility"), 0) > 0:
        annualized = position["realized_volatility"]
        decline = -profile.get("volatility_multiple", 3.0) * annualized / (252 ** .5) * 100
        decline = max(profile.get("maximum_trailing_pct", -30),
                      min(profile.get("minimum_trailing_pct", -10), decline))
        threshold = high * (1 + decline / 100)
    elif high and profile.get("trailing_high_water_pct") is not None:
        threshold = high * (1 + profile["trailing_high_water_pct"] / 100)
    if high and threshold is not None:
        rules["trailing_high_water_stop"] = {
            "triggered": current <= threshold, "threshold_price": round(threshold, 4), "current_price": current,
            "high_water_mark": high, "breach_amount": round(max(0, threshold - current), 4),
            "breach_percentage": round((current / threshold - 1) * 100, 3),
            "first_breached_at": position.get("trailing_stop_first_breached_at"),
            "confirmed_at": position.get("trailing_stop_confirmed_at"),
            "required_persistence": profile.get("persistence_closes", 1),
            "execution_policy": position.get("execution_policy", "next_liquid_close"),
            "persistence_rule": f"{profile.get('persistence_closes', 1)} confirming closes",
            "action": position.get("trailing_stop_action", "exit"), "discretionary": True,
        }
    triggered = [name for name, state in rules.items() if state["triggered"]]
    classification = triggered[0] + "_breached" if triggered else "within_stop_rules"
    return {"classification": classification, "profile": profile_name, "rules": rules}


def _severity_label(value, config):
    bands = config["deterioration"]["severity_bands"]
    if value >= bands["severe"] * 0.8:
        return "severe"
    if value >= bands["moderate"]:
        return "moderate"
    return "mild"


def _trim_percent(flagged, portfolio_fit, position, urgent, config):
    rule = config["trim"]
    count = len(flagged)
    base = rule["base_by_flag_count"].get(str(count), 0.0)
    severity = sum(group["severity"] for group in flagged) / count if count else 0.0
    group_confidence = min((group["confidence"] for group in flagged), default=0.0)
    severity_label = _severity_label(severity, config)
    confidence_label = "high" if group_confidence >= 0.8 else ("normal" if group_confidence >= 0.6 else "limited")
    concentration = portfolio_fit["classification"]
    if concentration not in rule["concentration_multipliers"]:
        concentration = "near_target"
    liquidity = (position or {}).get("liquidity", "normal")
    tax_cost = (position or {}).get("tax_cost", "normal")
    friction = 1.0 if urgent else rule["tax_cost_multipliers"].get(tax_cost, rule["tax_cost_multipliers"]["normal"])
    computed = (
        base * rule["severity_multipliers"][severity_label]
        * rule["confidence_multipliers"][confidence_label]
        * rule["concentration_multipliers"][concentration]
        * rule["liquidity_multipliers"].get(liquidity, 1.0) * friction
    )
    if computed <= 0:
        return 0.0, severity_label, confidence_label, {}
    result = min(rule["maximum"], max(rule["minimum"], computed))
    return round(result, 4), severity_label, confidence_label, {
        "base": base, "severity": rule["severity_multipliers"][severity_label],
        "confidence": rule["confidence_multipliers"][confidence_label],
        "concentration": rule["concentration_multipliers"][concentration],
        "liquidity": rule["liquidity_multipliers"].get(liquidity, 1.0), "tax_cost": friction,
    }


def _economic_trade(trim_pct, position, config):
    if not position or trim_pct <= 0:
        return {"economically_material": False, "shares": None, "estimated_value": None}
    shares = _number(position.get("shares"), 0)
    price = _number(position.get("current_price"), 0)
    raw_shares = shares * trim_pct
    precision = config["trim"]["share_precision"]
    rounded = round(raw_shares / precision) * precision if precision else raw_shares
    value = rounded * price
    portfolio_value = _number(position.get("portfolio_value"), 0)
    txn_cost = _number(position.get("estimated_transaction_cost"), 0)
    material = (
        rounded > 0 and value >= config["trim"]["minimum_trade_value"]
        and (not portfolio_value or value / portfolio_value >= config["trim"]["minimum_portfolio_fraction"])
        and (not txn_cost or value >= txn_cost * config["trim"]["transaction_cost_multiple"])
    )
    return {"economically_material": material, "shares": round(rounded, 6), "estimated_value": round(value, 2)}


def _days_since(value, now):
    if not value:
        return None
    try:
        then = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (now - then.astimezone(timezone.utc)).days
    except (TypeError, ValueError):
        return None


def evaluate_entry_rules(company_label, structural, timeliness, portfolio_fit, position,
                         thesis_break, config, now=None):
    """Classify initial entry, additions, averaging down, and post-stop re-entry."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    entry = config["entry"]
    position = position or {}
    shares = _number(position.get("shares"), 0)
    has_position = shares > 0
    blocked = bool(thesis_break or portfolio_fit["classification"] in ("overweight", "severely_overweight"))
    blackout = bool(position.get("earnings_blackout", False) and not position.get("strategy_allows_earnings_entry", False))
    reasons = []
    if blocked:
        reasons.append("portfolio_or_thesis_block")
    if blackout:
        reasons.append("earnings_blackout")
    if not has_position:
        stopped_days = _days_since(position.get("stopped_out_at"), now)
        if stopped_days is not None:
            cooldown = _number(position.get("reentry_cooldown_days"), config["stop_profiles"]["default"]["reentry_cooldown_days"])
            recovered = bool(position.get("recovery_condition_met", False))
            qualified = company_label == "buy" if entry["reentry_requires_score_requalification"] else company_label in ("buy", "accumulate")
            allowed = stopped_days >= cooldown and recovered and qualified and not blocked and not blackout
            return {"type": "reentry_after_stop", "allowed": allowed,
                    "reason_codes": reasons + ([] if stopped_days >= cooldown else ["reentry_cooldown_active"])
                    + ([] if recovered else ["recovery_not_confirmed"])
                    + ([] if qualified else ["score_not_requalified"])}
        allowed = company_label in ("buy", "accumulate", "tactical_candidate") and not blocked and not blackout
        strategy = "tactical_entry" if company_label == "tactical_candidate" else "long_term_entry"
        return {"type": "initial_buy", "strategy": strategy, "allowed": allowed, "reason_codes": reasons}

    current = _number(position.get("current_price"))
    cost = _number(position.get("weighted_cost_basis"))
    losing = current is not None and cost is not None and current < cost
    days_since_add = _days_since(position.get("last_add_at"), now)
    interval_ok = days_since_add is None or days_since_add >= entry["average_down_minimum_interval_days"]
    additions_ok = int(_number(position.get("addition_count"), 0)) < entry["average_down_maximum_additions"]
    if losing:
        # Averaging down into a loss requires positive timing evidence. Unknown timing is not
        # positive timing, so an unresolved timeliness layer blocks the add rather than
        # passing it through on a fabricated neutral.
        timing_score = timeliness.get("effective_score")
        timing_ok = timing_score is not None and timing_score >= config["score_matrix"]["timeliness_weak"]
        structural_score = structural.get("effective_score")
        allowed = (
            structural_score is not None
            and structural_score >= config["score_matrix"]["structural_strong"]
            and timing_ok
            and bool(position.get("valuation_meaningfully_improved", False))
            and interval_ok and additions_ok and not blocked and not blackout
        )
        return {"type": "average_down", "allowed": allowed, "reason_codes": reasons
                + ([] if timing_ok else ["timeliness_unavailable_or_deteriorating"])
                + ([] if position.get("valuation_meaningfully_improved") else ["valuation_improvement_not_confirmed"])
                + ([] if interval_ok else ["minimum_add_interval_not_met"])
                + ([] if additions_ok else ["maximum_additions_reached"])}
    allowed = company_label in ("buy", "accumulate") and not blocked and not blackout
    return {"type": "add_to_winner", "allowed": allowed, "reason_codes": reasons}


def build_recommendation_v2(ticker, analysis, technical=None, sentiment=None, extended=None,
                            portfolio=None, position=None, thesis_events=None,
                            deterioration_overrides=None, config=None, generated_at=None):
    config = config or load_policy()
    structural = _score_layer(analysis.get("structural"))
    timeliness = _score_layer(analysis.get("timeliness"))
    profile = analysis.get("applicability_profile", "general")
    quality = _quality({"structural": structural, "timeliness": timeliness})
    critical_gaps = _critical_field_gaps(profile, {**analysis, "structural": structural, "timeliness": timeliness}, config)
    quality["missing_critical_metrics"] = critical_gaps
    quality["severe_unresolved"] = quality["severe_unresolved"] or bool(critical_gaps)
    position_exists = bool(position and _number(position.get("shares"), 0) > 0)
    matrix_class = two_axis_classification(structural["effective_score"], timeliness["effective_score"], config)
    thesis_break = _thesis_break(thesis_events, config)
    company_label, namespace, company_reasons = _company_action(matrix_class, quality, position_exists, thesis_break, config)
    # Confidence in what was actually assessed. A layer that never resolved contributes no
    # opinion and must not drag the company's confidence to zero -- that is what made every
    # published company read "insufficient evidence" while structural coverage was 92%.
    # The unresolved axis is reported through matrix_class and quality.missing_critical_metrics
    # instead, where a reader can see which axis is missing rather than only that something is.
    assessed_confidence = [layer["evidence_weight_resolved"] for layer in (structural, timeliness)
                           if layer.get("effective_score") is not None]
    company_confidence = min(assessed_confidence) if assessed_confidence else 0.0
    groups = derive_deterioration_groups(analysis, technical, sentiment, extended, deterioration_overrides, config)
    flagged = [group for group in groups if group["flagged"]]
    portfolio_fit = classify_portfolio_fit(portfolio, config)
    stop_state = _stop_state(position, config)

    position_label, reason_namespace, position_reasons = ("no_action", "none", []) if not position_exists else ("hold", "position_supported", [])
    trim_pct, trim_meta = 0.0, {}
    triggered_stops = [name for name, state in stop_state.get("rules", {}).items() if state.get("triggered")]
    if thesis_break and position_exists:
        position_label, reason_namespace, position_reasons = "exit", "sell_thesis", ["sell_thesis_" + thesis_break["code"]]
    elif triggered_stops:
        stop_code = triggered_stops[0]
        position_label, reason_namespace, position_reasons = "exit", "position_rule", ["sell_position_" + stop_code]
    elif position_exists and (portfolio_fit["classification"] in ("overweight", "severely_overweight") or portfolio_fit["reason_codes"]):
        concentration_pct = 0.25 if portfolio_fit["classification"] == "severely_overweight" else 0.15
        position_label, reason_namespace, position_reasons = "trim", "portfolio_concentration", list(portfolio_fit["reason_codes"] or ["position_above_target"])
        trim_pct = concentration_pct
    elif position_exists and len(flagged) >= 2 and company_confidence >= config["confidence_gates"]["insufficient"]:
        trim_pct, severity_label, confidence_label, trim_meta = _trim_percent(flagged, portfolio_fit, position, False, config)
        position_label, reason_namespace = "trim", "company_deterioration"
        position_reasons = [code for group in flagged for code in group["reason_codes"]]
        trim_meta.update({"severity_label": severity_label, "confidence_label": confidence_label})

    economics = _economic_trade(trim_pct, position, config)
    if position_label == "trim" and not economics["economically_material"]:
        position_label = "review"
        position_reasons.append("trim_economically_immaterial")

    if position_label == "exit" and company_confidence < config["confidence_gates"]["insufficient"] and triggered_stops:
        position_reasons.append("position_rule_triggered_despite_insufficient_company_evidence")

    company_action = {"label": company_label, "display_label": COMPANY_DISPLAY_LABELS[company_label],
                      "confidence": round(company_confidence, 3),
                      "reason_namespace": namespace, "reason_codes": company_reasons}
    entry_action = evaluate_entry_rules(
        company_label, structural, timeliness, portfolio_fit, position, thesis_break, config,
        now=datetime.fromisoformat((generated_at or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")),
    )
    return {
        "schema_version": config["output_schema_version"],
        "model_version": config["model_version"],
        "policy_mode": "shadow" if config.get("shadow_mode", True) else "active",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "company_structural_state": structural,
        "company_timeliness_state": timeliness,
        "portfolio_fit_state": portfolio_fit,
        "position_rule_state": stop_state,
        "company": {
            "structural": structural, "timeliness": timeliness,
            "matrix_classification": matrix_class,
            "deterioration_groups": groups,
            "action": company_action,
        },
        "company_action": company_action,
        "portfolio_fit": portfolio_fit,
        "position_rules": stop_state.get("rules", {}),
        "position_action": {
            "label": position_label,
            "display_label": ("DO NOT ADD — PORTFOLIO OVERWEIGHT"
                              if portfolio_fit["classification"] in ("overweight", "severely_overweight")
                              and not position_exists else POSITION_DISPLAY_LABELS[position_label]),
            "trim_percent": trim_pct,
            "shares": economics["shares"], "estimated_value": economics["estimated_value"],
            "confidence": round(company_confidence, 3) if reason_namespace == "company_deterioration" else 1.0,
            "reason_namespace": reason_namespace, "reason_codes": position_reasons,
            "trim_calculation": trim_meta, "economically_material": economics["economically_material"],
        },
        "entry_action": entry_action,
        "data_quality": quality,
        "thesis_break_event": thesis_break,
        "critical_field_requirements": config["critical_fields"].get(profile, config["critical_fields"]["general"]),
        "legacy_recommendation_unchanged": True,
    }
