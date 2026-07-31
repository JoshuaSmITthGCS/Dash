"""Explainable, fundamentals-first research scoring. No political inputs."""

from math import sqrt

from scorer import SETTINGS, valuation_score

RANKING_WEIGHTS = {"fundamentals": 0.75, "market_behavior": 0.15, "news_sentiment": 0.10}
MODIFIERS = SETTINGS.get("modifiers", {})


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def max_drawdown(closes):
    """Deepest peak-to-trough fall over the window, in percent. Makes broken charts obvious."""
    if len(closes) < 2:
        return None
    peak, worst = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        if peak:
            worst = min(worst, close / peak - 1)
    return round(worst * 100, 2)


def volume_confirmation(closes, volumes):
    """Ratio of volume on up days to volume on down days over 60 sessions.

    A breakout nobody traded is noise; this separates conviction from drift. 1.0 is neutral.
    """
    if not volumes or len(volumes) < 21 or len(volumes) != len(closes):
        return None
    up = down = 0.0
    for index in range(max(1, len(closes) - 60), len(closes)):
        if closes[index] >= closes[index - 1]:
            up += volumes[index]
        else:
            down += volumes[index]
    if down <= 0:
        return None if up <= 0 else 2.0
    return round(min(up / down, 3.0), 2)


def technical_factors(closes, benchmark_closes=None, volumes=None, extended=None):
    """Score trend, relative strength, volatility, drawdown, and volume confirmation."""
    if len(closes) < 21:
        return None, {"coverage": 0.0}
    extended = extended or {}
    last = closes[-1]
    ret_5 = (last / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    ret_20 = (last / closes[-21] - 1) * 100
    ret_60 = (last / closes[-61] - 1) * 100 if len(closes) >= 61 else None
    ret_252 = (last / closes[-253] - 1) * 100 if len(closes) >= 253 else None
    daily = [(b / a) - 1 for a, b in zip(closes[:-1], closes[1:]) if a]
    recent = daily[-60:]
    mean = sum(recent) / len(recent)
    vol = sqrt(sum((x - mean) ** 2 for x in recent) / len(recent)) * sqrt(252) * 100
    peak = max(closes[-60:])
    drawdown = (last / peak - 1) * 100
    drawdown_252 = max_drawdown(closes[-252:])
    relative = None
    if benchmark_closes and len(benchmark_closes) >= 21:
        bench_ret = (benchmark_closes[-1] / benchmark_closes[-21] - 1) * 100
        relative = ret_20 - bench_ret
    confirmation = volume_confirmation(closes, volumes)
    from_high = extended.get("pct_from_52w_high")
    above_low = extended.get("pct_above_52w_low")
    # Statement enrichment (the source of the fields above) only runs for a shortlist. Every
    # candidate already has two years of closes, so fall back to a price-derived 52-week range
    # rather than leaving the rest of the universe without high/low context.
    if (from_high is None or above_low is None) and len(closes) >= 200:
        year_window = closes[-252:]
        year_high, year_low = max(year_window), min(year_window)
        if from_high is None and year_high:
            from_high = round((last / year_high - 1) * 100, 2)
        if above_low is None and year_low:
            above_low = round((last / year_low - 1) * 100, 2)

    trend_score = clamp(50 + ret_20 * 2 + ((ret_60 or 0) * 0.5))
    risk_score = clamp(100 - max(0, vol - 12) * 2 - abs(min(0, drawdown)) * 1.5)
    relative_score = clamp(50 + (relative or 0) * 3)
    # A one-to-three year max drawdown says more about a broken chart than a 60-day dip does.
    drawdown_score = clamp(100 + (drawdown_252 or 0) * 1.6)
    volume_score = 50.0 if confirmation is None else clamp(35 + (confirmation - 1) * 55)
    parts = {"trend": (trend_score, 0.32), "risk": (risk_score, 0.22),
             "relative_strength": (relative_score, 0.18), "drawdown_resilience": (drawdown_score, 0.16),
             "volume_confirmation": (volume_score, 0.12)}
    score = round(sum(value * weight for value, weight in parts.values()), 1)
    return score, {
        "return_5d": round(ret_5, 2) if ret_5 is not None else None,
        "return_20d": round(ret_20, 2), "return_60d": round(ret_60, 2) if ret_60 is not None else None,
        "return_252d": round(ret_252, 2) if ret_252 is not None else None,
        "annualized_volatility": round(vol, 2), "drawdown_60d": round(drawdown, 2),
        "max_drawdown_252d": drawdown_252,
        "relative_strength_20d": round(relative, 2) if relative is not None else None,
        "volume_ratio_60d": confirmation, "pct_from_52w_high": from_high,
        "pct_above_52w_low": above_low, "beta": extended.get("beta"),
        **{name: round(value, 1) for name, (value, _) in parts.items()},
        "coverage": round(0.7 + (0.15 if volumes else 0) + (0.15 if len(closes) >= 253 else 0), 2),
    }


def sentiment_score(news_items, ticker):
    scores = []
    for item in news_items:
        for row in item.get("ticker_sentiment", []):
            if row.get("ticker") == ticker:
                try:
                    scores.append(float(row.get("ticker_sentiment_score")))
                except (TypeError, ValueError):
                    pass
    if not scores:
        return 50.0, {"article_count": 0, "average": None, "coverage": 0.0}
    avg = sum(scores) / len(scores)
    return round(clamp(50 + avg * 100), 1), {
        "article_count": len(scores), "average": round(avg, 3), "coverage": min(1.0, len(scores) / 5),
    }


# ---------------- post-blend modifiers ----------------

def short_interest_modifier(extended):
    """Penalize crowded shorts. High short interest is not automatically bearish, but it
    raises the cost of being wrong, so it trims the score instead of driving it."""
    cfg = MODIFIERS.get("short_interest", {})
    float_short, days = extended.get("short_percent_of_float"), extended.get("days_to_cover")
    if float_short is None and days is None:
        return 0.0, None
    penalty = 0.0
    note = None
    if float_short is not None and float_short >= cfg.get("float_severe", 0.15):
        penalty, note = cfg.get("max_penalty", 4.0), f"{float_short * 100:.1f}% of float sold short"
    elif float_short is not None and float_short >= cfg.get("float_warning", 0.08):
        penalty, note = cfg.get("max_penalty", 4.0) / 2, f"{float_short * 100:.1f}% of float sold short"
    if days is not None and days >= cfg.get("days_to_cover_warning", 5.0):
        penalty = min(cfg.get("max_penalty", 4.0), penalty + 1.0)
        note = note or f"{days:.1f} days to cover"
    return -round(penalty, 2), note


def liquidity_modifier(extended):
    """Penalize names you cannot exit without moving the price."""
    cfg = MODIFIERS.get("liquidity", {})
    dollar_volume = extended.get("average_dollar_volume")
    if dollar_volume is None:
        return 0.0, None
    if dollar_volume < cfg.get("illiquid_dollar_volume", 5e6):
        return -cfg.get("max_penalty", 3.0), f"Thin tape: ${dollar_volume / 1e6:.1f}M traded daily"
    if dollar_volume < cfg.get("thin_dollar_volume", 25e6):
        return -round(cfg.get("max_penalty", 3.0) / 2, 2), f"Moderate liquidity: ${dollar_volume / 1e6:.0f}M daily"
    return 0.0, None


def expectations_modifier(extended):
    """Analyst target and consensus rating as an expectations check, capped tightly."""
    cfg = MODIFIERS.get("expectations", {})
    cap = cfg.get("max_points", 3.0)
    upside, rating, count = (extended.get("analyst_target_upside"), extended.get("analyst_rating"),
                             extended.get("analyst_count") or 0)
    if count < 3 or (upside is None and rating is None):
        return 0.0, None
    points, notes = 0.0, []
    if upside is not None and upside >= cfg.get("strong_upside", 20.0):
        points += cap / 2
        notes.append(f"consensus target {upside:.0f}% above price")
    elif upside is not None and upside <= cfg.get("weak_upside", -5.0):
        points -= cap / 2
        notes.append(f"trading {abs(upside):.0f}% above consensus target")
    if rating is not None and rating <= cfg.get("bullish_rating", 2.0):
        points += cap / 2
        notes.append(f"{count} analysts average {rating:.1f}/5")
    elif rating is not None and rating >= cfg.get("bearish_rating", 3.5):
        points -= cap / 2
        notes.append(f"{count} analysts average a cautious {rating:.1f}/5")
    return round(max(-cap, min(cap, points)), 2), "; ".join(notes) or None


def sector_percentile_modifier(percentile):
    """Reward being cheap *for its own sector*, which absolute multiples cannot express."""
    cfg = MODIFIERS.get("sector_valuation_percentile", {})
    cap = cfg.get("max_points", 3.0)
    if percentile is None:
        return 0.0, None
    points = round((percentile - 50) / 50 * cap, 2)
    if abs(points) < 0.5:
        return 0.0, None
    label = "cheaper" if points > 0 else "richer"
    return points, f"Valuation {label} than {abs(percentile - 50) * 2:.0f}% of its sector peers"


def macro_regime_modifier(snapshot, macro_regime):
    """Translate macro conditions through sector exposure, with a hard ±3 point cap."""
    cfg = MODIFIERS.get("macro_regime", {})
    if not macro_regime or macro_regime.get("coverage", 0) < cfg.get("min_coverage", 0.7):
        return 0.0, None
    factors = macro_regime.get("factors", {})
    sector = snapshot.get("sector") or "default"
    weights = cfg.get("sector_weights", {}).get(
        sector, cfg.get("sector_weights", {}).get("default", {})
    )
    available = [
        (factors[name]["score"], weight)
        for name, weight in weights.items()
        if factors.get(name, {}).get("score") is not None
    ]
    if not available:
        return 0.0, None
    sector_score = sum(value * weight for value, weight in available) / sum(weight for _, weight in available)
    cap = cfg.get("max_points", 3.0)
    points = round((sector_score - 50) / 50 * cap, 2)
    if abs(points) < 0.25:
        return 0.0, None
    direction = "supportive" if points > 0 else "restrictive"
    return points, f"FRED macro regime is {direction} for {sector} ({sector_score:.0f}/100)"


def apply_modifiers(base, snapshot, extended, sector_percentile=None, macro_regime=None):
    """Blend the bounded refinements onto the evidence score and explain every one."""
    applied = {}
    notes = []
    for name, (points, note) in {
        "sector_valuation": sector_percentile_modifier(sector_percentile),
        "short_interest": short_interest_modifier(extended),
        "liquidity": liquidity_modifier(extended),
        "expectations": expectations_modifier(extended),
        "macro_regime": macro_regime_modifier(snapshot, macro_regime),
    }.items():
        if points:
            applied[name] = points
        if note:
            notes.append(note)
    uncapped_total = round(sum(applied.values()), 2)
    total = round(max(-15.0, min(15.0, uncapped_total)), 2)
    if total != uncapped_total:
        notes.append(f"Combined modifiers capped at {total:+.0f} points")
    return round(clamp(base + total), 1), {
        "applied": applied, "total": total, "uncapped_total": uncapped_total, "notes": notes,
    }


# ---------------- action guidance ----------------

def action_for(score, stance, fundamental_parts, technical_parts, extended, sentiment_parts):
    """Sell / trim / watch guidance that requires two independent factors to agree.

    Price alone never triggers an action. Neither does one bad headline. The rule is the
    same one a disciplined holder would use: the business, the chart, and the narrative
    have to corroborate each other before anyone touches a position.
    """
    categories = fundamental_parts.get("categories", {})
    concerns = {}

    fundamental_reasons = []
    for key, label in (("profitability", "profitability"), ("financial_health", "balance-sheet health"),
                       ("accounting_quality", "accounting quality"), ("growth", "growth")):
        value = categories.get(key)
        if value is not None and value < 45:
            fundamental_reasons.append(f"{label} score {value:.0f}/100")
    if (extended.get("interest_coverage") or 99) < 2:
        fundamental_reasons.append(f"interest coverage only {extended['interest_coverage']:.1f}x")
    if (extended.get("accruals_ratio") or 0) > 0.10:
        fundamental_reasons.append("earnings running well ahead of cash flow")
    if fundamental_reasons:
        concerns["fundamentals"] = fundamental_reasons

    technical_reasons = []
    if (technical_parts.get("max_drawdown_252d") or 0) < -30:
        technical_reasons.append(f"{abs(technical_parts['max_drawdown_252d']):.0f}% peak-to-trough fall this year")
    if (technical_parts.get("relative_strength_20d") or 0) < -10:
        technical_reasons.append(f"trailing SPY by {abs(technical_parts['relative_strength_20d']):.0f} points over 20 days")
    if (technical_parts.get("return_60d") or 0) < -15 and (technical_parts.get("return_20d") or 0) < 0:
        technical_reasons.append("sustained decline across 20- and 60-day windows")
    if technical_reasons:
        concerns["market_behavior"] = technical_reasons

    sentiment_reasons = []
    average = sentiment_parts.get("average")
    if average is not None and average < -0.15 and sentiment_parts.get("article_count", 0) >= 3:
        sentiment_reasons.append(f"{sentiment_parts['article_count']} articles averaging negative coverage")
    if (extended.get("short_percent_of_float") or 0) >= 0.15:
        sentiment_reasons.append(f"{extended['short_percent_of_float'] * 100:.0f}% of float sold short")
    if sentiment_reasons:
        concerns["positioning"] = sentiment_reasons

    agreement = len(concerns)
    reasons = [reason for group in concerns.values() for reason in group]
    if agreement >= 2 and score < 45:
        action, trim, confidence = "SELL", 100, "high"
    elif agreement >= 2:
        action, trim, confidence = "TRIM", 33 if agreement == 2 else 50, "moderate"
    elif agreement == 1:
        action, trim, confidence = "WATCH", 0, "moderate"
    elif stance in ("ATTRACTIVE", "PROMISING"):
        action, trim, confidence = "HOLD", 0, "high"
    else:
        action, trim, confidence = "HOLD", 0, "moderate"

    summary = {
        "SELL": "Two or more independent factors have broken down. Exiting and redeploying is the disciplined response.",
        "TRIM": f"Multiple factors disagree with the thesis. Reducing roughly {trim}% keeps exposure without ignoring the evidence.",
        "WATCH": "One factor has deteriorated. Not enough to act on alone - monitor for a second confirmation.",
        "HOLD": "No multi-factor deterioration. Position stands on its current evidence.",
    }[action]
    return {"action": action, "suggested_trim_pct": trim, "confidence": confidence,
            "agreement_count": agreement, "reasons": reasons[:5], "summary": summary,
            "factors": {name: group for name, group in concerns.items()}}


def stance_for(score, confidence):
    if confidence < 0.45:
        return "INSUFFICIENT DATA"
    if score >= 75:
        return "ATTRACTIVE"
    if score >= 60:
        return "PROMISING"
    if score >= 45:
        return "MIXED"
    return "CAUTION"


def build_evidence(categories, technical_parts, extended):
    """Plain-language strengths and risks drawn from whichever metrics actually resolved."""
    strengths, risks = [], []
    for key, label in (("valuation", "valuation"), ("profitability", "profitability and cash generation"),
                       ("financial_health", "balance-sheet health"), ("growth", "growth"),
                       ("capital_allocation", "capital allocation"), ("accounting_quality", "accounting quality")):
        value = categories.get(key)
        if value is not None and value >= 70:
            strengths.append(f"Strong {label} score ({value:.0f}/100)")
        elif value is not None and value < 45:
            risks.append(f"Weak {label} score ({value:.0f}/100)")

    roic = extended.get("return_on_invested_capital")
    if roic is not None and roic >= 0.15:
        strengths.append(f"Returns {roic * 100:.0f}% on invested capital, not just on leveraged equity")
    conversion = extended.get("cash_conversion")
    if conversion is not None and conversion >= 0.9:
        strengths.append(f"Converts {conversion * 100:.0f}% of net income into free cash flow")
    elif conversion is not None and conversion < 0.6:
        risks.append(f"Only {conversion * 100:.0f}% of reported earnings arrive as cash")
    buybacks = extended.get("net_buyback_yield")
    if buybacks is not None and buybacks >= 0.02:
        strengths.append(f"Share count down {buybacks * 100:.1f}% over the year, net of dilution")
    elif buybacks is not None and buybacks <= -0.02:
        risks.append(f"Share count up {abs(buybacks) * 100:.1f}%, diluting existing holders")
    comp = extended.get("stock_comp_to_revenue")
    if comp is not None and comp >= 0.08:
        risks.append(f"Stock compensation equals {comp * 100:.1f}% of revenue")
    accruals = extended.get("accruals_ratio")
    if accruals is not None and accruals > 0.08:
        risks.append("Net income is running materially ahead of operating cash flow")
    coverage = extended.get("interest_coverage")
    if coverage is not None and coverage < 3:
        risks.append(f"Operating profit covers interest only {coverage:.1f}x")
    dso = extended.get("days_sales_outstanding_trend")
    if dso is not None and dso > 0.15:
        risks.append(f"Receivable days up {dso * 100:.0f}% year over year")

    if (technical_parts.get("max_drawdown_252d") or 0) < -25:
        risks.append(f"Fell {abs(technical_parts['max_drawdown_252d']):.0f}% peak-to-trough over the past year")
    elif technical_parts.get("drawdown_60d", 0) < -10:
        risks.append(f"Down {abs(technical_parts['drawdown_60d']):.1f}% from its 60-day high")
    if (technical_parts.get("relative_strength_20d") or 0) > 3:
        strengths.append("Outperforming SPY over 20 trading days")
    if (technical_parts.get("volume_ratio_60d") or 0) >= 1.3:
        strengths.append("Advances are carrying heavier volume than declines")

    if not strengths:
        strengths.append("No decisive strength cleared the evidence threshold")
    if not risks:
        risks.append("No major quantitative red flag; qualitative risks still require review")
    return strengths[:5], risks[:5]


def build_research(symbol, snapshot, closes, benchmark_closes, news_items,
                   volumes=None, extended=None, sector_percentile=None, macro_regime=None):
    extended = extended or {}
    fundamental, fundamental_parts = valuation_score(snapshot)
    technical, technical_parts = technical_factors(closes, benchmark_closes, volumes, extended)
    sentiment, sentiment_parts = sentiment_score(news_items, symbol)
    components = {"fundamentals": fundamental, "market_behavior": technical, "news_sentiment": sentiment}
    # Fundamentals deliberately dominate the ranking. Price and headlines confirm; they cannot
    # rescue a company with weak valuation/quality evidence.
    weights = RANKING_WEIGHTS
    available = [(components[k], weights[k]) for k in weights if components[k] is not None]
    raw = sum(v * w for v, w in available) / sum(w for _, w in available) if available else 0
    fundamental_coverage = fundamental_parts.get("coverage", 0.0)
    confidence = round(0.65 * fundamental_coverage + 0.25 * technical_parts.get("coverage", 0) +
                       0.10 * sentiment_parts.get("coverage", 0), 2)
    base = round(raw * (0.8 + confidence * 0.2), 1)
    score, modifiers = apply_modifiers(base, snapshot, extended, sector_percentile, macro_regime)
    categories = fundamental_parts.get("categories", {})
    stance = stance_for(score, confidence)
    strengths, risks = build_evidence(categories, technical_parts, extended)
    return {
        **snapshot, "score": score, "base_score": base, "stance": stance, "confidence": confidence,
        "components": components, "fundamental_categories": categories,
        "fundamental_detail": fundamental_parts, "technical_detail": technical_parts,
        "sentiment_detail": sentiment_parts, "modifiers": modifiers,
        "sector_valuation_percentile": sector_percentile,
        "recommendation": action_for(score, stance, fundamental_parts, technical_parts,
                                     extended, sentiment_parts),
        "strengths": strengths, "risks": risks,
    }
