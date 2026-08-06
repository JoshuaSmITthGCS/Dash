"""Explainable, fundamentals-first research scoring. No political inputs."""

from datetime import timedelta

from insider_signal import score_insider_activity
from risk_metrics import (annualized_volatility, beta_vs_benchmark, daily_returns,
                          drawdown_score, low_beta_score, max_drawdown, momentum_12_1,
                          ratio_to_score, sharpe_ratio, sortino_ratio)
from scorer import SETTINGS, valuation_score
from news_intelligence import weighted_sentiment
from recommendation_policy_v2 import build_recommendation_v2
from scoring_v2 import build_v2_analysis

# Fundamentals deliberately dominate. News sentiment was cut from 10% because its alpha
# decays in days: Tetlock (2007) finds media pessimism predicts downward price pressure
# "followed by a reversion to fundamentals", so a daily headline snapshot is a tilt, not a
# tenth of a research thesis. The freed weight went to market behavior, which is now built
# on real risk-adjusted math rather than invented constants.
DEFAULT_RANKING_WEIGHTS = {"fundamentals": 0.78, "market_behavior": 0.18, "news_sentiment": 0.04}


def _weights(configured, defaults):
    """Merge a config weight table over defaults, dropping ``_comment``-style annotations."""
    numeric = {key: value for key, value in (configured or {}).items()
               if not key.startswith("_") and isinstance(value, (int, float))}
    return {**defaults, **numeric}


RANKING_WEIGHTS = _weights(SETTINGS.get("ranking_weights"), DEFAULT_RANKING_WEIGHTS)
MODIFIERS = SETTINGS.get("modifiers", {})

# Market-behavior sub-weights, overridable from config.
DEFAULT_TECHNICAL_WEIGHTS = {
    "momentum_12_1": 0.30, "risk_adjusted": 0.26, "relative_strength": 0.16,
    "drawdown_resilience": 0.14, "volume_confirmation": 0.08, "low_beta": 0.06,
}
TECHNICAL_WEIGHTS = _weights((SETTINGS.get("market_behavior") or {}).get("weights"),
                             DEFAULT_TECHNICAL_WEIGHTS)
NEWS_INTELLIGENCE = SETTINGS["news_intelligence"]
SENTIMENT_WINDOW_DAYS = int(NEWS_INTELLIGENCE["window_days"])
FUNDAMENTAL_METRIC_NAMES = {
    metric for weights in SETTINGS["fundamentals"]["metric_weights"].values()
    for metric in weights
}


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def normalized_metric_scores(detail):
    """Project only per-metric 0 to 100 scores from a fundamental detail block."""
    return {metric: detail.get(metric) for metric in sorted(FUNDAMENTAL_METRIC_NAMES)}


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


def technical_factors(closes, benchmark_closes=None, volumes=None, extended=None,
                      short_horizon_treatment=None, reversal_weight=None):
    """Score market behavior on the same risk math the ETF model uses.

    The previous version scored two invented linear formulas - a trend of
    ``50 + 20d_return*2 + 60d_return*0.5`` and a risk penalty of
    ``100 - max(0, vol-12)*2 - |drawdown|*1.5``. Those constants were arbitrary: they are
    not comparable across volatility regimes, they cannot be validated against any published
    result, and they measured something no two people would agree on. What replaced them:

      * **12-1 momentum** (Jegadeesh & Titman 1993) instead of raw recent return, skipping
        the most recent month to avoid the short-term reversal that runs against momentum.
      * **Sortino and Sharpe** on the stock's own return series instead of a hand-tuned
        volatility penalty - the identical functions the ETF screen scores funds with, so a
        risk reading means the same thing on either side of the platform.
      * **Low beta rewarded** rather than volatility punished, following the
        betting-against-beta result (Frazzini & Pedersen 2014).

    Relative strength versus SPY and volume confirmation are kept as they were; both were
    already reasonable.
    """
    if len(closes) < 21:
        return None, {"coverage": 0.0}
    extended = extended or {}
    last = closes[-1]
    ret_5 = (last / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    ret_20 = (last / closes[-21] - 1) * 100
    ret_60 = (last / closes[-61] - 1) * 100 if len(closes) >= 61 else None
    ret_252 = (last / closes[-253] - 1) * 100 if len(closes) >= 253 else None
    momentum = momentum_12_1(closes)
    returns = daily_returns(closes)
    volatility = annualized_volatility(returns, window=60)
    sortino = sortino_ratio(returns[-252:] if len(returns) >= 252 else returns)
    sharpe = sharpe_ratio(returns[-252:] if len(returns) >= 252 else returns)
    peak = max(closes[-60:])
    drawdown = (last / peak - 1) * 100
    drawdown_252 = max_drawdown(closes[-252:])

    benchmark_returns = daily_returns(benchmark_closes) if benchmark_closes else []
    beta = extended.get("beta")
    if beta is None and benchmark_returns:
        beta = beta_vs_benchmark(returns, benchmark_returns)
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

    # A stock without a full year of history has no 12-1 momentum. Rather than score it
    # neutral and pretend, fall back to the 60-day return and mark coverage down for it.
    momentum_input = momentum if momentum is not None else ret_60
    momentum_score = None if momentum_input is None else clamp(50 + momentum_input * 1.2)
    # Sortino leads (downside deviation is the risk worth avoiding); Sharpe cross-checks it.
    risk_adjusted = None
    if sortino is not None or sharpe is not None:
        components = [(ratio_to_score(sortino), 0.65), (ratio_to_score(sharpe), 0.35)]
        present = [(value, weight) for value, weight in components if value is not None]
        risk_adjusted = round(sum(value * weight for value, weight in present)
                              / sum(weight for _, weight in present), 1)
    relative_score = None if relative is None else clamp(50 + relative * 3)
    # A one-to-three year max drawdown says more about a broken chart than a 60-day dip does.
    resilience = drawdown_score(drawdown_252 if drawdown_252 is not None else drawdown)
    volume_score = None if confirmation is None else clamp(35 + (confirmation - 1) * 55)
    beta_score = low_beta_score(beta)

    parts = {
        name: None if value is None else round(value, 1)
        for name, value in (
            ("momentum_12_1", momentum_score), ("risk_adjusted", risk_adjusted),
            ("relative_strength", relative_score), ("drawdown_resilience", resilience),
            ("volume_confirmation", volume_score), ("low_beta", beta_score),
        )
    }
    treatment = short_horizon_treatment or SETTINGS.get(
        "short_horizon_treatment", "legacy_momentum"
    )
    score, variant = technical_score_from_parts(parts, treatment, reversal_weight)
    if score is None:
        return None, {"coverage": 0.0}

    return score, {
        "return_5d": round(ret_5, 2) if ret_5 is not None else None,
        "return_20d": round(ret_20, 2), "return_60d": round(ret_60, 2) if ret_60 is not None else None,
        "return_252d": round(ret_252, 2) if ret_252 is not None else None,
        "momentum_12_1_pct": momentum,
        "annualized_volatility": volatility, "drawdown_60d": round(drawdown, 2),
        "max_drawdown_252d": drawdown_252,
        "sharpe_ratio": sharpe, "sortino_ratio": sortino,
        "relative_strength_20d": round(relative, 2) if relative is not None else None,
        "volume_ratio_60d": confirmation, "pct_from_52w_high": from_high,
        "pct_above_52w_low": above_low, "beta": beta,
        **{name: value for name, value in parts.items() if value is not None},
        "coverage": variant["coverage"],
        "short_horizon_treatment": treatment,
    }


def technical_score_from_parts(parts, treatment, reversal_weight=None):
    """Recombine already-calculated market signals under a short-horizon treatment.

    ``legacy_momentum`` retains the current relative-strength term. ``neutral`` removes
    it and renormalizes the remaining weights to sum to one. ``reversal`` maps the same
    signal to ``100 - legacy_score`` and uses the configured reduced weight.
    """
    if treatment not in {"legacy_momentum", "neutral", "reversal"}:
        raise ValueError(f"unsupported short-horizon treatment: {treatment}")
    weights = dict(TECHNICAL_WEIGHTS)
    values = {name: parts.get(name) for name in weights}
    if treatment == "neutral":
        weights.pop("relative_strength", None)
        values.pop("relative_strength", None)
    elif treatment == "reversal":
        if reversal_weight is None:
            raise ValueError("reversal treatment requires a configured reversal weight")
        weights["relative_strength"] = reversal_weight
        if values.get("relative_strength") is not None:
            values["relative_strength"] = round(100 - values["relative_strength"], 1)
    answered = [(value, weights[name]) for name, value in values.items()
                if value is not None]
    if not answered:
        return None, {"coverage": 0.0, "weights": weights}
    score = round(sum(value * weight for value, weight in answered)
                  / sum(weight for _, weight in answered), 1)
    coverage = round(sum(weight for _, weight in answered) / sum(weights.values()), 2)
    return score, {"coverage": coverage, "weights": weights, "parts": values}


def sentiment_score(news_items, ticker, *, window_days=None, now=None):
    """Aggregate entity-level headline sentiment over a window, not a single snapshot.

    Tetlock (2007) finds high media pessimism predicts downward price pressure "followed by
    a reversion to fundamentals" - the effect on any one day largely unwinds within days,
    while aggregating over a week extends the horizon over which it carries information.
    So this aggregates a week of coverage and the blend weights it as a tilt (4%), not as a
    core component.
    """
    config = {**NEWS_INTELLIGENCE}
    config["window_days"] = SENTIMENT_WINDOW_DAYS if window_days is None else window_days
    config["window_delta"] = timedelta(days=config["window_days"])
    return weighted_sentiment(news_items, ticker, config, now=now)


# ---------------- post-blend modifiers ----------------

def short_interest_modifier(extended):
    """Penalize crowded shorts.

    Short interest is one of the strongest documented cross-sectional predictors there is:
    Boehmer, Jones & Zhang (*JF* 2008) find heavily shorted stocks underperform lightly
    shorted ones by a risk-adjusted 1.16% over the following 20 trading days - about 15.6%
    annualized. The old -4 cap under-used a signal that strong, so it is now -6. It stays a
    bounded modifier rather than a ranking factor because high short interest is not
    automatically bearish; it raises the cost of being wrong.
    """
    cfg = MODIFIERS.get("short_interest", {})
    cap = cfg.get("max_penalty", 6.0)
    float_short, days = extended.get("short_percent_of_float"), extended.get("days_to_cover")
    if float_short is None and days is None:
        return 0.0, None
    penalty = 0.0
    note = None
    if float_short is not None and float_short >= cfg.get("float_severe", 0.15):
        penalty, note = cap, f"{float_short * 100:.1f}% of float sold short"
    elif float_short is not None and float_short >= cfg.get("float_warning", 0.08):
        penalty, note = cap / 2, f"{float_short * 100:.1f}% of float sold short"
    if days is not None and days >= cfg.get("days_to_cover_warning", 5.0):
        penalty = min(cap, penalty + 1.5)
        note = note or f"{days:.1f} days to cover"
    return -round(penalty, 2), note


def insider_modifier(insider_activity):
    """Reward fresh opportunistic cluster buying; penalize opportunistic cluster selling.

    The scoring itself lives in ``insider_signal`` (Cohen-Malloy-Pomorski routine/
    opportunistic split, buys weighted above sells, decaying over one to three months).
    This adapter accepts either raw parsed Form 4 transactions or an already-scored
    summary, so the pipeline can compute it once and reuse it.
    """
    if not insider_activity:
        return 0.0, None
    cfg = MODIFIERS.get("insider_activity", {})
    if insider_activity.get("score_points") is not None:
        points = insider_activity["score_points"]
        notes = insider_activity.get("notes") or []
    else:
        transactions = insider_activity.get("transactions") or []
        if not transactions:
            return 0.0, None
        points, detail = score_insider_activity(transactions, config=cfg)
        notes = detail.get("notes") or []
    if not points:
        return 0.0, None
    cap = cfg.get("max_points", 5.0)
    floor = -cfg.get("max_penalty", 3.0)
    return round(max(floor, min(cap, points)), 2), ("; ".join(notes) or None)


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
    if points > 0:
        return points, f"Valuation cheaper than {percentile:.0f}% of its canonical peers"
    return points, f"Valuation richer than {100 - percentile:.0f}% of its canonical peers"


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


def apply_modifiers(base, snapshot, extended, sector_percentile=None, macro_regime=None,
                    insider_activity=None):
    """Blend the bounded refinements onto the evidence score and explain every one."""
    applied = {}
    notes = []
    for name, (points, note) in {
        "sector_valuation": sector_percentile_modifier(sector_percentile),
        "short_interest": short_interest_modifier(extended),
        "liquidity": liquidity_modifier(extended),
        "expectations": expectations_modifier(extended),
        "macro_regime": macro_regime_modifier(snapshot, macro_regime),
        "insider_activity": insider_modifier(insider_activity),
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


def apply_challenger_modifiers(base, snapshot, extended, config, sector_percentile=None,
                               short_interest_rank=None, macro_regime=None,
                               insider_activity=None):
    """Apply fractionally allocated modifiers under the configured combined cap.

    Each individual maximum is ``combined_cap * configured_fraction``. The final sum is
    clamped once to plus or minus ``combined_cap`` so changing one allocation never changes
    another modifier's implicit scale.
    """
    cap = float(config["modifier_cap"])
    fractions = config["modifier_fractions"]
    applied, notes = {}, []

    if sector_percentile is not None:
        allocation = cap * fractions["sector_valuation"]
        points = round((sector_percentile - 50) / 50 * allocation, 2)
        if points:
            applied["sector_valuation"] = points

    short_cfg = MODIFIERS.get("short_interest", {})
    float_short = extended.get("short_percent_of_float")
    days = extended.get("days_to_cover")
    short_points = 0.0
    rank_value = (short_interest_rank or {}).get("percentile")
    if rank_value is not None and rank_value <= config["low_short_interest_percentile"]:
        short_points += cap * fractions["short_interest_reward"]
        notes.append("Short interest is in the lowest sector decile")
    penalty_allocation = cap * fractions["short_interest_penalty"]
    if float_short is not None and float_short >= short_cfg.get("float_severe"):
        short_points -= penalty_allocation
    elif float_short is not None and float_short >= short_cfg.get("float_warning"):
        short_points -= penalty_allocation / 2
    if days is not None and days >= short_cfg.get("days_to_cover_warning"):
        short_points -= penalty_allocation * config["days_to_cover_penalty_fraction"]
    short_points = max(-penalty_allocation, short_points)
    if short_points:
        applied["short_interest"] = round(short_points, 2)

    liquidity_points, liquidity_note = liquidity_modifier(extended)
    if liquidity_points:
        old_cap = MODIFIERS.get("liquidity", {}).get("max_penalty")
        applied["liquidity"] = round(
            liquidity_points / old_cap * cap * fractions["liquidity"], 2
        )
    if liquidity_note:
        notes.append(liquidity_note)

    expectations_points, expectations_note = expectations_modifier(extended)
    if expectations_points:
        old_cap = MODIFIERS.get("expectations", {}).get("max_points")
        applied["expectations"] = round(
            expectations_points / old_cap * cap * fractions["expectations"], 2
        )
    if expectations_note:
        notes.append(expectations_note.replace(";", ","))

    macro_points, macro_note = macro_regime_modifier(snapshot, macro_regime)
    if macro_points:
        old_cap = MODIFIERS.get("macro_regime", {}).get("max_points")
        applied["macro_regime"] = round(
            macro_points / old_cap * cap * fractions["macro_regime"], 2
        )
    if macro_note:
        notes.append(macro_note)

    insider_points, insider_note = insider_modifier(insider_activity)
    if insider_points:
        fraction_key = "insider_positive" if insider_points > 0 else "insider_negative"
        old_key = "max_points" if insider_points > 0 else "max_penalty"
        old_cap = MODIFIERS.get("insider_activity", {}).get(old_key)
        applied["insider_activity"] = round(
            insider_points / old_cap * cap * fractions[fraction_key], 2
        )
    if insider_note:
        notes.append(insider_note.replace(";", ","))

    uncapped_total = round(sum(applied.values()), 2)
    total = round(max(-cap, min(cap, uncapped_total)), 2)
    if total != uncapped_total:
        notes.append(f"Combined modifiers capped at {total:+.0f} points")
    return round(clamp(base + total), 1), {
        "applied": applied,
        "total": total,
        "uncapped_total": uncapped_total,
        "cap": cap,
        "fractions": fractions,
        "short_interest_rank": short_interest_rank,
        "notes": notes,
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


def blend_research_components(components, coverage, modifier_points=0.0, weights=None):
    """Return the legacy evidence blend, confidence pull, and bounded final score.

    Formula for the current champion is ``raw = sum(score_i * weight_i) / sum(weight_i)``
    over available components, then ``base = raw * (0.8 + 0.2 * confidence)`` and
    ``final = clamp(base + modifier_points)``. Keeping this in one function lets a
    challenger replace one component without changing any other part of the comparison.
    """
    weights = weights or RANKING_WEIGHTS
    available = [(components[key], weights[key]) for key in weights
                 if components.get(key) is not None]
    raw = sum(value * weight for value, weight in available) / sum(
        weight for _, weight in available
    ) if available else 0.0
    confidence = round(
        0.65 * coverage.get("fundamentals", 0.0)
        + 0.25 * coverage.get("market_behavior", 0.0)
        + 0.10 * coverage.get("news_sentiment", 0.0),
        2,
    )
    base = round(raw * (0.8 + confidence * 0.2), 1)
    return {
        "raw_score": round(raw, 1),
        "base_score": base,
        "score": round(clamp(base + modifier_points), 1),
        "confidence": confidence,
    }


def shrink_research_components(components, coverage, config, modifier_points=0.0,
                               weights=None):
    """Apply one confidence shrinkage toward a configurable neutral prior.

    Formula: ``effective = target + strength * (raw - target)``, where
    ``strength = 1 - max_pull * (1 - confidence)``. At the default maximum pull of one,
    strength equals confidence exactly and missing evidence moves a score toward neutral.
    """
    weights = weights or RANKING_WEIGHTS
    available = [(components[key], weights[key]) for key in weights
                 if components.get(key) is not None]
    raw = sum(value * weight for value, weight in available) / sum(
        weight for _, weight in available
    ) if available else config["shrinkage_target"]
    confidence = round(
        0.65 * coverage.get("fundamentals", 0.0)
        + 0.25 * coverage.get("market_behavior", 0.0)
        + 0.10 * coverage.get("news_sentiment", 0.0),
        2,
    )
    strength = clamp(1 - config["shrinkage_max_pull"] * (1 - confidence), 0.0, 1.0)
    target = config["shrinkage_target"]
    base = round(target + strength * (raw - target), 1)
    return {
        "raw_score": round(raw, 1),
        "base_score": base,
        "score": round(clamp(base + modifier_points), 1),
        "confidence": confidence,
        "shrinkage_strength": round(strength, 3),
        "shrinkage_target": target,
    }


def cross_sectional_challenger(row, snapshot, normalizer):
    """Replace only the fundamental component and publish an attributable challenger."""
    fundamental, detail = valuation_score(
        snapshot, mode="cross_sectional", normalizer=normalizer,
    )
    components = {**row.get("components", {}), "fundamentals": fundamental}
    blended = blend_research_components(
        components,
        {
            "fundamentals": detail.get("coverage", 0.0),
            "market_behavior": (row.get("technical_detail") or {}).get("coverage", 0.0),
            "news_sentiment": (row.get("sentiment_detail") or {}).get("coverage", 0.0),
        },
        (row.get("modifiers") or {}).get("total", 0.0),
    )
    champion_metrics = row.get("fundamental_detail") or {}
    deltas = sorted(
        (
            {
                "metric": metric,
                "champion": champion_metrics.get(metric),
                "challenger": value,
                "delta": round(value - champion_metrics[metric], 1),
            }
            for metric, value in detail.items()
            if isinstance(value, (int, float))
            and isinstance(champion_metrics.get(metric), (int, float))
            and metric not in {"coverage", "raw_score"}
        ),
        key=lambda item: abs(item["delta"]),
        reverse=True,
    )
    return {
        "variant": "cross_sectional_normalization",
        "normalization_mode": "cross_sectional",
        **blended,
        "components": components,
        "fundamental_categories": detail.get("categories", {}),
        "fundamental_detail": detail,
        "normalized_metric_scores": normalized_metric_scores(detail),
        "largest_metric_changes": deltas[:5],
    }


def signal_correction_variants(row, snapshot, normalizer, config, short_interest_rank=None,
                               macro_regime=None, insider_activity=None):
    """Build isolated signal edits plus the cumulative challenger beside the champion."""
    normalization = cross_sectional_challenger(row, snapshot, normalizer)
    champion_components = row.get("components") or {}
    technical, technical_detail = technical_score_from_parts(
        row.get("technical_detail") or {},
        config["short_horizon_treatment"],
        config["reversal_weight"],
    )
    neutral_components = {**champion_components, "market_behavior": technical}
    coverage = {
        "fundamentals": (row.get("fundamental_detail") or {}).get("coverage", 0.0),
        "market_behavior": technical_detail.get("coverage", 0.0),
        "news_sentiment": (row.get("sentiment_detail") or {}).get("coverage", 0.0),
    }
    legacy_modifier_total = (row.get("modifiers") or {}).get("total", 0.0)
    short_horizon = {
        "variant": "neutral_short_horizon",
        "short_horizon_treatment": config["short_horizon_treatment"],
        **blend_research_components(
            neutral_components, coverage, legacy_modifier_total,
        ),
        "components": neutral_components,
    }

    champion_raw_fundamental = (row.get("fundamental_detail") or {}).get(
        "raw_score", champion_components.get("fundamentals")
    )
    raw_components = {**champion_components, "fundamentals": champion_raw_fundamental}
    shrinkage = {
        "variant": "single_confidence_shrinkage",
        **shrink_research_components(
            raw_components,
            {**coverage, "market_behavior": (row.get("technical_detail") or {}).get("coverage", 0.0)},
            config,
            legacy_modifier_total,
        ),
        "components": raw_components,
    }

    modifier_score, modifier_detail = apply_challenger_modifiers(
        row.get("base_score", 0.0), snapshot, snapshot, config,
        row.get("sector_valuation_percentile"), short_interest_rank,
        macro_regime, insider_activity,
    )
    modifier_recalibration = {
        "variant": "fractional_modifier_cap",
        "score": modifier_score,
        "base_score": row.get("base_score"),
        "confidence": row.get("confidence"),
        "modifiers": modifier_detail,
    }

    cross_raw = (normalization.get("fundamental_detail") or {}).get(
        "raw_score", normalization["components"].get("fundamentals")
    )
    final_components = {
        **neutral_components,
        "fundamentals": cross_raw,
    }
    final_base = shrink_research_components(final_components, coverage, config)
    final_score, final_modifiers = apply_challenger_modifiers(
        final_base["base_score"], snapshot, snapshot, config,
        row.get("sector_valuation_percentile"), short_interest_rank,
        macro_regime, insider_activity,
    )
    challenger = {
        "variant": "signal_corrections_cumulative",
        "normalization_mode": "cross_sectional",
        "short_horizon_treatment": config["short_horizon_treatment"],
        **final_base,
        "score": final_score,
        "components": final_components,
        "fundamental_categories": normalization.get("fundamental_categories"),
        "normalized_metric_scores": normalization.get("normalized_metric_scores"),
        "largest_metric_changes": normalization.get("largest_metric_changes"),
        "modifiers": final_modifiers,
    }
    return {
        "normalization": normalization,
        "short_horizon": short_horizon,
        "confidence_shrinkage": shrinkage,
        "modifier_recalibration": modifier_recalibration,
        "challenger": challenger,
    }


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
                   volumes=None, extended=None, sector_percentile=None, macro_regime=None,
                   insider_activity=None):
    extended = extended or {}
    fundamental, fundamental_parts = valuation_score(snapshot)
    technical, technical_parts = technical_factors(closes, benchmark_closes, volumes, extended)
    sentiment, sentiment_parts = sentiment_score(news_items, symbol)
    components = {"fundamentals": fundamental, "market_behavior": technical, "news_sentiment": sentiment}
    fundamental_coverage = fundamental_parts.get("coverage", 0.0)
    blended = blend_research_components(components, {
        "fundamentals": fundamental_coverage,
        "market_behavior": technical_parts.get("coverage", 0),
        "news_sentiment": sentiment_parts.get("coverage", 0),
    })
    confidence, base, raw_score = blended["confidence"], blended["base_score"], blended["raw_score"]
    score, modifiers = apply_modifiers(base, snapshot, extended, sector_percentile, macro_regime,
                                       insider_activity)
    categories = fundamental_parts.get("categories", {})
    stance = stance_for(score, confidence)
    strengths, risks = build_evidence(categories, technical_parts, extended)
    analysis_v2 = build_v2_analysis(snapshot, fundamental_parts)
    recommendation_v2 = build_recommendation_v2(
        symbol,
        analysis_v2,
        technical=technical_parts,
        sentiment=sentiment_parts,
        extended=extended,
    )
    return {
        **snapshot, "score": score, "base_score": base, "raw_score": raw_score, "stance": stance,
        "confidence": confidence,
        "components": components, "fundamental_categories": categories,
        "fundamental_detail": fundamental_parts, "technical_detail": technical_parts,
        "sentiment_detail": sentiment_parts, "modifiers": modifiers,
        "sector_valuation_percentile": sector_percentile,
        "recommendation": action_for(score, stance, fundamental_parts, technical_parts,
                                     extended, sentiment_parts),
        "strengths": strengths, "risks": risks,
        "analysis_v2": analysis_v2,
        # Shadow only: legacy ``recommendation`` remains the production field until the
        # new policy has passed prospective, net-of-cost validation.
        "recommendation_v2": recommendation_v2,
    }
