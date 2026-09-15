"""Python port of ``src/lib/researchScreens.js``'s ``rankBreakoutInProgress`` and
``rankEmergingGrowth``, line for line, against ``report.json``'s own published rows.

This is a port, not a re-derivation: every gate, weight and formula below is copied from the
JS so that "who is in the top 10 today" always matches exactly what a browser rendering the
same ``report.json`` would show. ``rank_emerging_growth.py`` already has a Python port of the
emerging-growth side, but it exists for backtesting a past date and deliberately reads full
daily closes instead of ``history.closes`` - its own docstring documents that as a real,
accepted divergence from the live page for that purpose. This module exists for a different
purpose (today's actual top 10, not a historical replay), so it reads exactly the same
``history.closes`` field report.json itself publishes, with no divergence risk.
"""

import math


def _finite(value):
    # Excludes bool deliberately: JS's `typeof value === 'number'` is false for a boolean,
    # and Python's isinstance(True, int) is true, so a naive isinstance check would let a
    # stray True/False through as if it were a real number.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _clamp(value, minimum=0, maximum=100):
    return min(maximum, max(minimum, value))


def _weekly_closes(row):
    history = row.get("history") or {}
    return [close for close in (history.get("closes") or []) if _finite(close)]


def trailing_week_return(row):
    closes = _weekly_closes(row)
    if len(closes) < 2 or not closes[-2]:
        return None
    return (closes[-1] / closes[-2] - 1) * 100


def _stocks_only(rows):
    return [row for row in rows if not row.get("is_etf")]


def rank_breakout_in_progress(rows, limit=5):
    """Names already up more than 2% this week whose pace is accelerating, not decelerating.
    See researchScreens.js's own docstring for why this is named for what already happened
    rather than for a forecast.
    """
    candidates = []
    for row in _stocks_only(rows):
        technical = row.get("technical_detail") or {}
        week_return = (technical.get("return_5d") if _finite(technical.get("return_5d"))
                      else trailing_week_return(row))
        month_return = technical.get("return_20d")
        volume_ratio = technical.get("volume_ratio_60d")
        if not (_finite(week_return) and _finite(month_return)) or week_return <= 2 or month_return <= 0:
            continue

        prior_pace_5d = (month_return - week_return) / 15 * 5
        acceleration = week_return - prior_pace_5d
        if acceleration <= 0:
            continue

        burst = _clamp(50 + week_return * 3)
        accel_score = _clamp(50 + acceleration * 2)
        trend = _clamp(50 + month_return * 1.2)
        volume = _clamp(50 + (volume_ratio - 1) * 40) if _finite(volume_ratio) else 50
        candidates.append({
            **row,
            "screen": {
                "weekReturn": week_return, "monthReturn": month_return,
                "acceleration": acceleration, "volumeRatio": volume_ratio,
                "rankScore": burst * .4 + accel_score * .3 + trend * .2 + volume * .1,
            },
        })
    candidates.sort(key=lambda candidate: candidate["screen"]["rankScore"], reverse=True)
    return candidates[:limit]


def rank_emerging_growth(rows, limit=5):
    """Names that have NOT yet cleared rank_breakout_in_progress's weekReturn > 2 gate but
    show real (not invented) measurables that sometimes precede a move: revenue growth,
    a margin inflection, early positive relative strength, and realized volatility
    contraction. Unvalidated - see researchScreens.js's own docstring.
    """
    candidates = []
    for row in _stocks_only(rows):
        technical = row.get("technical_detail") or {}
        fundamental = row.get("fundamental_detail") or {}
        closes = _weekly_closes(row)
        week_return = (technical.get("return_5d") if _finite(technical.get("return_5d"))
                      else trailing_week_return(row))
        revenue_growth = fundamental.get("revenue_growth")
        margin_trend = fundamental.get("operating_margin_trend")
        relative_strength = technical.get("relative_strength_20d")

        # Excludes anything already caught by the breakout screen - a distinct, earlier-stage
        # population, not a relabeled duplicate of that list.
        if not _finite(week_return) or week_return > 2:
            continue
        if not _finite(revenue_growth) or revenue_growth <= 0.05:
            continue
        if not _finite(relative_strength) or relative_strength <= 0:
            continue

        recent_vol = longer_vol = None
        if len(closes) >= 61:
            def _daily_returns(series):
                return [series[index] / series[index - 1] - 1 for index in range(1, len(series))]

            def _stdev(values):
                if len(values) < 2:
                    return None
                mean = sum(values) / len(values)
                return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))

            recent_vol = _stdev(_daily_returns(closes[-11:]))
            longer_vol = _stdev(_daily_returns(closes[-61:]))
        volatility_contracting = (
            recent_vol < longer_vol * 0.85
            if _finite(recent_vol) and _finite(longer_vol) and longer_vol > 0 else None)

        growth_score = _clamp(50 + revenue_growth * 150)
        margin_score = _clamp(50 + margin_trend * 300) if _finite(margin_trend) else 50
        strength_score = _clamp(50 + relative_strength * 4)
        contraction_score = 50 if volatility_contracting is None else (70 if volatility_contracting else 40)
        # Optional bonus only when present - collect_estimates.py covers a small ticker
        # subset today, so this is None on almost every row and never required or penalized.
        revision_breadth = row.get("estimate_revision_breadth")
        revision_score = _clamp(50 + revision_breadth * 50) if _finite(revision_breadth) else None

        weighted = [(growth_score, .35), (margin_score, .2), (strength_score, .2),
                    (contraction_score, .15)]
        if revision_score is not None:
            weighted.append((revision_score, .1))
        total_weight = sum(weight for _, weight in weighted)
        rank_score = sum(value * weight for value, weight in weighted) / total_weight

        candidates.append({
            **row,
            "research_status": "prospective_unvalidated",
            "screen": {
                "weekReturn": week_return, "revenueGrowth": revenue_growth,
                "marginTrend": margin_trend, "relativeStrength": relative_strength,
                "volatilityContracting": volatility_contracting,
                "revisionBreadth": revision_breadth, "rankScore": rank_score,
            },
        })
    candidates.sort(key=lambda candidate: candidate["screen"]["rankScore"], reverse=True)
    return candidates[:limit]
