"""Point-in-time research-screen formulas; no provider or current-data look-ahead."""

from __future__ import annotations

import math
from datetime import date, datetime
from statistics import median


MOMENTUM_WEIGHTS = {"momentum_12_1": .40, "momentum_12_7": .20, "momentum_6_1": .15,
                    "high_52w_proximity": .15, "industry_relative_momentum": .10}
TACTICAL_WEIGHTS = {"revision_agreement": .12, "revision_magnitude": .15, "revision_acceleration": .08,
                    "fresh_estimate_delta": .05, "dispersion_trend": .05, "eps_surprise": .08,
                    "surprise_consistency": .04, "revenue_surprise": .03, "post_earnings_drift": .05,
                    "momentum_12_1": .08, "momentum_6_1": .04, "high_52w_proximity": .04,
                    "industry_relative_momentum": .04, "industry_revision_breadth": .10,
                    "risk_tradability": .05}


def month_end_prices(prices, as_of=None):
    """Last valid session in each calendar month, never after as_of."""
    cutoff = str(as_of or date.max)[:10]
    by_month = {}
    for row in sorted(prices or [], key=lambda item: str(item["date"])[:10]):
        day = str(row["date"])[:10]
        value = row.get("adjusted_close")
        if day <= cutoff and value is not None and math.isfinite(float(value)) and float(value) > 0:
            by_month[day[:7]] = (day, float(value))
    return list(by_month.values())


def _return(values, start_from_end, end_from_end=1):
    if len(values) <= start_from_end:
        return None
    start, end = values[-1 - start_from_end], values[-1 - end_from_end]
    return end / start - 1 if start else None


def momentum_factors(prices, industry_return=None, as_of=None):
    """Exact month-end 12-1, 12-7 and 6-1 skip-month returns."""
    months = month_end_prices(prices, as_of)
    values = [value for _, value in months]
    if len(values) < 13:
        return None
    twelve_one = _return(values, 12, 1)
    twelve_seven = _return(values, 12, 7)
    six_one = _return(values, 6, 1)
    daily = [float(row["adjusted_close"]) for row in prices if str(row["date"])[:10] <= str(as_of or date.max)[:10]
             and row.get("adjusted_close") is not None]
    high = max(daily[-252:]) if len(daily) >= 252 else None
    proximity = daily[-1] / high if high else None
    return {"momentum_12_1": twelve_one, "momentum_12_7": twelve_seven,
            "momentum_6_1": six_one, "high_52w_proximity": proximity,
            "industry_relative_momentum": None if industry_return is None else twelve_one - industry_return}


def winsorize(values, lower=.05, upper=.95):
    finite = sorted(value for value in values if value is not None and math.isfinite(value))
    if not finite: return []
    lo = finite[min(len(finite) - 1, int((len(finite) - 1) * lower))]
    hi = finite[min(len(finite) - 1, int((len(finite) - 1) * upper))]
    return [None if value is None else min(hi, max(lo, value)) for value in values]


def zscores(values):
    present = [value for value in values if value is not None]
    if not present: return [None] * len(values)
    center = sum(present) / len(present)
    variance = sum((value - center) ** 2 for value in present) / len(present)
    scale = math.sqrt(variance)
    return [None if value is None else (value - center) / scale if scale else 0 for value in values]


def momentum_scores(rows, current_members=None, config=None):
    """Cross-sectional score with eligibility, contributions, percentile and hysteresis."""
    config = config or {}
    current_members = current_members or {}
    fields = list(MOMENTUM_WEIGHTS)
    standardized = {field: zscores(winsorize([(row.get("factors") or {}).get(field) for row in rows])) for field in fields}
    output = []
    for index, row in enumerate(rows):
        reasons = []
        if (row.get("price") or 0) < config.get("minimum_price", 5): reasons.append("MINIMUM_PRICE")
        if (row.get("market_cap") or 0) < config.get("minimum_market_cap", 300_000_000): reasons.append("MINIMUM_MARKET_CAP")
        if (row.get("median_dollar_volume_60d") or 0) < config.get("minimum_median_dollar_volume_60d", 2_000_000): reasons.append("MINIMUM_LIQUIDITY")
        if (row.get("history_sessions") or 0) < config.get("minimum_history_sessions", 253): reasons.append("INSUFFICIENT_HISTORY")
        if row.get("binary_event_excluded"): reasons.append("BINARY_EVENT_EXCLUSION")
        if row.get("stale_price"): reasons.append("STALE_PRICE")
        contributions = {field: (standardized[field][index] or 0) * MOMENTUM_WEIGHTS[field] for field in fields}
        score = sum(contributions.values())
        output.append({**row, "score": score, "standardized_factors": {f: standardized[f][index] for f in fields},
                       "contribution_by_factor": contributions, "eligibility": not reasons, "reason_codes": reasons})
    eligible = sorted((row for row in output if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = 100 * rank / max(1, len(eligible) - 1)
    entry, exit_ = config.get("entry_percentile", 90), config.get("exit_percentile", 75)
    for row in output:
        held = bool(current_members.get(row.get("ticker")))
        row.update({"current_membership": held, "previous_membership": held,
                    "entry_threshold": entry, "exit_threshold": exit_,
                    "selected": row["eligibility"] and row.get("percentile", -1) >= (exit_ if held else entry)})
    return sorted(output, key=lambda row: row["score"], reverse=True)


def tactical_score(factors, structural_score=None, snapshot_available=True):
    present = {key: factors.get(key) for key in TACTICAL_WEIGHTS if factors.get(key) is not None}
    coverage = sum(TACTICAL_WEIGHTS[key] for key in present)
    score = sum(float(value) * TACTICAL_WEIGHTS[key] for key, value in present.items()) / coverage if coverage else None
    tactical_high = score is not None and score >= 60
    structural_high = structural_score is not None and structural_score >= 65
    classification = ("high-conviction candidate" if structural_high and tactical_high else
                      "quality company, wait" if structural_high else
                      "tactical-only candidate" if tactical_high else "avoid")
    flags = [] if snapshot_available else ["REVISION_BACKTEST_UNAVAILABLE", "FORWARD_COLLECTION_ONLY"]
    return {"tactical_score": None if score is None else round(score, 4), "structural_score": structural_score,
            "classification": classification, "coverage": round(coverage, 4), "quality_flags": flags,
            "contribution_by_factor": {key: float(value) * TACTICAL_WEIGHTS[key] for key, value in present.items()}}


def historical_percentile(history, current, lower_is_cheaper=True):
    values = [float(value) for value in history if value is not None and math.isfinite(float(value))]
    if current is None or not values: return None
    percentile = sum(value <= float(current) for value in values) / len(values) * 100
    return 100 - percentile if lower_is_cheaper else percentile


def robust_value_score(metrics, applicability=None):
    """Weighted median of applicable own-history cheapness percentiles."""
    applicability = applicability or {key: 1 for key in metrics}
    weighted = []
    raw = {}
    for key, item in metrics.items():
        if not applicability.get(key, 0): continue
        percentile = historical_percentile(item.get("history", []), item.get("current"), item.get("lower_is_cheaper", True))
        raw[key] = percentile
        if percentile is not None:
            weighted.extend([percentile] * max(1, int(applicability[key] * 10)))
    return (median(weighted) if weighted else None), raw


def classify_quality_value(own_history_score, peer_value_score, quality_score, revision_current_year=None,
                           revision_next_year=None, revision_acceleration=None, distressed=False,
                           minimum_history=True):
    if not minimum_history: return "insufficient historical data", ["INSUFFICIENT_HISTORICAL_DATA"]
    severe_revisions = ((revision_current_year is not None and revision_current_year <= 20 and
                         revision_next_year is not None and revision_next_year <= 20) or
                        (revision_acceleration is not None and revision_acceleration <= -2))
    if distressed: return "distressed/value trap", ["SEVERE_DISTRESS"]
    cheap = own_history_score is not None and own_history_score >= 70 and (peer_value_score or 0) >= 40
    quality = quality_score is not None and quality_score >= 65
    if cheap and quality and severe_revisions: return "cheap but deteriorating", ["FORWARD_ESTIMATE_DETERIORATION"]
    if cheap and quality: return "actionable value", []
    if quality: return "high quality but not cheap", ["NOT_CHEAP_VS_OWN_HISTORY"]
    return "distressed/value trap", ["QUALITY_GATE_FAILED"]


def position_size(account_value, price, atr, risk_budget=.005, maximum_position=.05,
                  median_dollar_volume=None, maximum_adv_fraction=.01):
    """ATR risk sizing with position and liquidity caps; never alters the signal score."""
    if not all(value and value > 0 for value in (account_value, price, atr)): return 0
    risk_shares = account_value * risk_budget / atr
    cap_shares = account_value * maximum_position / price
    liquidity_shares = (median_dollar_volume * maximum_adv_fraction / price
                        if median_dollar_volume else math.inf)
    return max(0, int(min(risk_shares, cap_shares, liquidity_shares)))


def sleeve_volatility_scale(forecast_volatility, target=.12, maximum_leverage=1.0):
    """Portfolio-level volatility target, separate from individual signal ranking/sizing."""
    if forecast_volatility is None or forecast_volatility <= 0: return 0
    return min(maximum_leverage, target / forecast_volatility)
