"""Explainable, fundamentals-first research scoring. No political inputs."""

from math import sqrt

from scorer import valuation_score


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def technical_factors(closes, benchmark_closes=None):
    """Score trend, relative strength, volatility, and drawdown from daily closes."""
    if len(closes) < 21:
        return None, {"coverage": 0.0}
    last = closes[-1]
    ret_20 = (last / closes[-21] - 1) * 100
    ret_60 = (last / closes[-61] - 1) * 100 if len(closes) >= 61 else None
    daily = [(b / a) - 1 for a, b in zip(closes[:-1], closes[1:]) if a]
    recent = daily[-60:]
    mean = sum(recent) / len(recent)
    vol = sqrt(sum((x - mean) ** 2 for x in recent) / len(recent)) * sqrt(252) * 100
    peak = max(closes[-60:])
    drawdown = (last / peak - 1) * 100
    relative = None
    if benchmark_closes and len(benchmark_closes) >= 21:
        bench_ret = (benchmark_closes[-1] / benchmark_closes[-21] - 1) * 100
        relative = ret_20 - bench_ret

    trend_score = clamp(50 + ret_20 * 2 + ((ret_60 or 0) * 0.5))
    risk_score = clamp(100 - max(0, vol - 12) * 2 - abs(min(0, drawdown)) * 1.5)
    relative_score = clamp(50 + (relative or 0) * 3)
    score = round(trend_score * 0.45 + risk_score * 0.35 + relative_score * 0.20, 1)
    return score, {
        "return_20d": round(ret_20, 2), "return_60d": round(ret_60, 2) if ret_60 is not None else None,
        "annualized_volatility": round(vol, 2), "drawdown_60d": round(drawdown, 2),
        "relative_strength_20d": round(relative, 2) if relative is not None else None,
        "trend": round(trend_score, 1), "risk": round(risk_score, 1),
        "relative_strength": round(relative_score, 1), "coverage": 1.0,
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


def build_research(symbol, snapshot, closes, benchmark_closes, news_items):
    fundamental, fundamental_parts = valuation_score(snapshot)
    technical, technical_parts = technical_factors(closes, benchmark_closes)
    sentiment, sentiment_parts = sentiment_score(news_items, symbol)
    components = {"fundamentals": fundamental, "market_behavior": technical, "news_sentiment": sentiment}
    weights = {"fundamentals": 0.60, "market_behavior": 0.25, "news_sentiment": 0.15}
    available = [(components[k], weights[k]) for k in weights if components[k] is not None]
    raw = sum(v * w for v, w in available) / sum(w for _, w in available) if available else 0
    fundamental_coverage = fundamental_parts.get("coverage", 0.0)
    confidence = round(0.65 * fundamental_coverage + 0.25 * technical_parts.get("coverage", 0) +
                       0.10 * sentiment_parts.get("coverage", 0), 2)
    score = round(raw * (0.8 + confidence * 0.2), 1)
    categories = fundamental_parts.get("categories", {})
    strengths, risks = [], []
    for key, label in (("valuation", "valuation"), ("profitability", "profitability and cash generation"),
                       ("financial_health", "balance-sheet health"), ("growth", "growth")):
        value = categories.get(key)
        if value is not None and value >= 70:
            strengths.append(f"Strong {label} score ({value:.0f}/100)")
        elif value is not None and value < 45:
            risks.append(f"Weak {label} score ({value:.0f}/100)")
    if technical_parts.get("drawdown_60d", 0) < -10:
        risks.append(f"Down {abs(technical_parts['drawdown_60d']):.1f}% from its 60-day high")
    if technical_parts.get("relative_strength_20d") is not None and technical_parts["relative_strength_20d"] > 3:
        strengths.append("Outperforming SPY over 20 trading days")
    if not strengths:
        strengths.append("No decisive strength cleared the evidence threshold")
    if not risks:
        risks.append("No major quantitative red flag; qualitative risks still require review")
    return {
        **snapshot, "score": score, "stance": stance_for(score, confidence), "confidence": confidence,
        "components": components, "fundamental_categories": categories,
        "fundamental_detail": fundamental_parts, "technical_detail": technical_parts,
        "sentiment_detail": sentiment_parts, "strengths": strengths[:3], "risks": risks[:3],
    }

