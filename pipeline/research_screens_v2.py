"""Point-in-time research-screen formulas; no provider or current-data look-ahead."""

from __future__ import annotations

import math
from datetime import date, datetime
from statistics import mean, median


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


def momentum_boundary_diagnostics(prices, as_of=None):
    """Return auditable month-end boundaries for every skip-month signal.

    ``end`` is the last completed month before the skipped month(s). The diagnostics
    deliberately name every skipped calendar month so fixtures can prove that a partial
    formation month never leaks into a signal.
    """
    months = month_end_prices(prices, as_of)
    specs = {"momentum_12_1": (12, 1), "momentum_12_7": (12, 7), "momentum_6_1": (6, 1)}
    output = {}
    for signal, (start_offset, end_offset) in specs.items():
        if len(months) <= start_offset:
            output[signal] = {"status": "unavailable", "reason_code": "INSUFFICIENT_MONTH_ENDS"}
            continue
        start_index, end_index = len(months) - 1 - start_offset, len(months) - 1 - end_offset
        start, end = months[start_index], months[end_index]
        skipped = [day[:7] for day, _ in months[end_index + 1:]]
        output[signal] = {
            "status": "success",
            "formation_date": str(as_of or months[-1][0])[:10],
            "starting_month_end": start[0],
            "ending_month_end": end[0],
            "skipped_months": skipped,
            "included_return_months": end_index - start_index,
            "return": round(end[1] / start[1] - 1, 12),
        }
    return output


def momentum_path_smoothness(prices, as_of=None, lookback_sessions=252, skip_sessions=21):
    """Frog-in-the-pan path smoothness over the momentum formation window.

    Da, Gurun & Warachka ("Frog in the Pan: Continuous Information and Momentum", Review of
    Financial Studies 27(7), 2014) find momentum profits concentrate in names whose
    formation-period gain accrues through many small, same-signed daily moves rather than a
    few large jumps - "continuous information" earns more than "discrete information" at the
    same cumulative return. This is a simplified, one-sided reading of their information
    discreteness measure: the fraction of formation-window daily returns whose sign matches
    the sign of the window's own total return. 1.0 is a monotonic path; a path with as many
    up days as down days scores near 0.5 regardless of which direction it netted out.

    Unlike ``momentum_factors``, which measures 12-1 on exact month-end boundaries, this
    needs daily granularity to see individual up/down days, so the formation window here is
    approximated in trading sessions (default 252 ~ 12 months, skipping the most recent 21
    ~ 1 month) rather than calendar months. Duplicates ``momentum_factors``' own as-of
    cutoff rather than trusting the caller to have pre-filtered ``prices``.
    """
    cutoff = str(as_of or date.max)[:10]
    daily = [float(row["adjusted_close"]) for row in prices
             if str(row["date"])[:10] <= cutoff and row.get("adjusted_close") is not None]
    needed = lookback_sessions + skip_sessions
    if len(daily) < needed + 1:
        return None
    window = daily[-needed:-skip_sessions] if skip_sessions else daily[-needed:]
    if len(window) < 2 or not window[0]:
        return None
    total_return = window[-1] / window[0] - 1
    if total_return == 0:
        return None
    direction = total_return > 0
    daily_returns = [window[index] / window[index - 1] - 1 for index in range(1, len(window))
                     if window[index - 1]]
    if not daily_returns:
        return None
    same_sign = sum(1 for value in daily_returns if value != 0 and (value > 0) == direction)
    return same_sign / len(daily_returns)


def industry_relative_returns(rows, minimum_peer_count=4, weighting="median"):
    """Compute a leave-one-out industry benchmark; a company never benchmarks itself."""
    if weighting not in {"median", "equal_weight"}:
        raise ValueError("weighting must be median or equal_weight")
    output = {}
    for row in rows or []:
        ticker, group = row.get("ticker"), row.get("peer_group")
        peers = [float(peer["momentum_12_1"]) for peer in rows
                 if peer.get("ticker") != ticker and peer.get("peer_group") == group
                 and peer.get("momentum_12_1") is not None
                 and math.isfinite(float(peer["momentum_12_1"]))]
        if len(peers) < minimum_peer_count:
            output[ticker] = {"status": "unavailable", "reason_code": "INSUFFICIENT_VALID_PEERS",
                              "peer_group": group, "peer_count": len(peers),
                              "minimum_peer_count": minimum_peer_count, "leave_one_out": True}
            continue
        benchmark = median(peers) if weighting == "median" else mean(peers)
        own = row.get("momentum_12_1")
        output[ticker] = {"status": "success", "peer_group": group, "peer_count": len(peers),
                          "minimum_peer_count": minimum_peer_count, "leave_one_out": True,
                          "weighting": weighting, "industry_return": benchmark,
                          "industry_relative_momentum": None if own is None else float(own) - benchmark}
    return output


def _correlation(xs, ys):
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None
             and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(pairs) < 3:
        return None
    left, right = [x for x, _ in pairs], [y for _, y in pairs]
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in pairs)
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale) if left_scale and right_scale else None


def momentum_correlation_diagnostics(rows, fields=None, threshold=.80, family_cap=.60):
    """Monitor cross-sectional dependence and declare the enforced family cap."""
    fields = list(fields or MOMENTUM_WEIGHTS)
    matrix, pairs = {}, []
    for left in fields:
        matrix[left] = {}
        for right in fields:
            value = 1.0 if left == right else _correlation(
                [(row.get("factors") or row).get(left) for row in rows],
                [(row.get("factors") or row).get(right) for row in rows])
            matrix[left][right] = None if value is None else round(value, 6)
            if fields.index(right) > fields.index(left) and value is not None:
                pairs.append(abs(value))
    average = mean(pairs) if pairs else None
    # Equicorrelation approximation: transparent, bounded, and stable without a
    # numerical dependency. It prevents five near-duplicates from posing as five facts.
    n = len(fields)
    effective = n if average is None else n / (1 + (n - 1) * max(0, average))
    concentrated = average is not None and average > threshold
    return {"correlation_matrix": matrix,
            "average_pairwise_correlation": None if average is None else round(average, 6),
            "effective_factor_count": round(effective, 3),
            "momentum_family_concentration": "high" if concentrated else "normal",
            "correlation_threshold": threshold,
            "family_contribution_cap": family_cap,
            "cap_applied": concentrated}


def winsorize(values, lower=.05, upper=.95):
    finite = sorted(value for value in values if value is not None and math.isfinite(value))
    if not finite: return [None] * len(values)
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
    diagnostics = momentum_correlation_diagnostics(
        rows, threshold=config.get("correlation_threshold", .80),
        family_cap=config.get("family_contribution_cap", config.get("price_family_cap", .90)))
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
        gross_score = sum(contributions.values())
        cap = diagnostics["family_contribution_cap"]
        scale = min(1.0, cap / abs(gross_score)) if diagnostics["cap_applied"] and gross_score else 1.0
        contributions = {field: value * scale for field, value in contributions.items()}
        score = sum(contributions.values())
        output.append({**row, "score": score, "standardized_factors": {f: standardized[f][index] for f in fields},
                       "uncapped_score": gross_score, "contribution_by_factor": contributions,
                       "momentum_correlation": diagnostics,
                       "eligibility": not reasons, "reason_codes": reasons})
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
