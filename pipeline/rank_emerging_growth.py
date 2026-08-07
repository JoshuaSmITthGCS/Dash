"""Python port of src/lib/researchScreens.js::rankEmergingGrowth, for backtesting.

The live "Emerging growth" screen (src/pages/FastGrowthScreen.jsx) is explicitly labeled
``research_status: prospective_unvalidated`` in the frontend -- nothing in this codebase has
ever measured whether it predicts a subsequent move (see docs/BASELINE-2026-08-06.md: the IC
harness has 0 of 24 eligible periods for the champion score, let alone this screen). This
module ports the exact same qualification gates and weighted score to Python so
``pipeline/backtest_emerging_growth.py`` can measure it retrospectively, reusing
``backtest_historical.rank_week``'s point-in-time-built rows (real historical
fundamental_detail/technical_detail, the same ``advisor_engine.build_research`` the live
pipeline uses) rather than re-deriving fundamentals from scratch.

One deliberate deviation from the live JS, noted rather than silently matched: the JS
volatility-contraction leg operates on ``row.history.closes``, which is the frontend's
weekly-sampled series (market_history.py's ``weekly_grid``) -- its own docstring says "last
10 sessions vs the trailing 60" but the data it actually reads is weekly, not daily. This
backtest has genuine daily closes already in memory (``closes_to_date`` from
``build_snapshot``), so it uses daily sessions (last 10 vs last 60), which is what the
docstring describes and is more granular than what the live screen currently computes from.
"""

import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from backtest_historical import build_snapshot, rank_week  # noqa: E402

RECENT_WINDOW = 10
LONGER_WINDOW = 60
CONTRACTION_RATIO = 0.85


def _clamp(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, value))


def _stdev(values):
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    return (sum((value - average) ** 2 for value in values) / len(values)) ** 0.5


def _daily_returns(series):
    return [series[i] / series[i - 1] - 1 for i in range(1, len(series)) if series[i - 1]]


def volatility_contracting(closes_to_date):
    """True when the trailing RECENT_WINDOW-session realized volatility is meaningfully
    below the trailing LONGER_WINDOW-session volatility. None (not False) when there is not
    enough history to judge -- an unmeasured leg must never look like a negative measurement.
    """
    if not closes_to_date or len(closes_to_date) < LONGER_WINDOW + 1:
        return None
    recent = _stdev(_daily_returns(closes_to_date[-(RECENT_WINDOW + 1):]))
    longer = _stdev(_daily_returns(closes_to_date[-(LONGER_WINDOW + 1):]))
    if recent is None or not longer:
        return None
    return recent < longer * CONTRACTION_RATIO


def emerging_growth_score(row, closes_to_date=None):
    """Score one already-built row (from rank_week) against the emerging-growth gates.

    Returns ``None`` when the row is an ETF or fails any qualification gate (identical
    thresholds to researchScreens.js::rankEmergingGrowth); otherwise ``(rank_score, detail)``.
    """
    if row.get("is_etf"):
        return None
    technical = row.get("technical_detail") or {}
    fundamental = row.get("fundamental_detail") or {}

    week_return = technical.get("return_5d")
    revenue_growth = fundamental.get("revenue_growth")
    relative_strength = technical.get("relative_strength_20d")
    margin_trend = fundamental.get("operating_margin_trend")

    if not isinstance(week_return, (int, float)) or week_return > 2:
        return None
    if not isinstance(revenue_growth, (int, float)) or revenue_growth <= 0.05:
        return None
    if not isinstance(relative_strength, (int, float)) or relative_strength <= 0:
        return None

    contracting = volatility_contracting(closes_to_date)

    growth_score = _clamp(50 + revenue_growth * 150)
    margin_score = _clamp(50 + margin_trend * 300) if isinstance(margin_trend, (int, float)) else 50.0
    strength_score = _clamp(50 + relative_strength * 4)
    contraction_score = 50.0 if contracting is None else (70.0 if contracting else 40.0)
    revision_breadth = row.get("estimate_revision_breadth")
    revision_score = (_clamp(50 + revision_breadth * 50)
                      if isinstance(revision_breadth, (int, float)) else None)

    weighted = [(growth_score, 0.35), (margin_score, 0.2), (strength_score, 0.2),
               (contraction_score, 0.15)]
    if revision_score is not None:
        weighted.append((revision_score, 0.1))
    total_weight = sum(weight for _, weight in weighted)
    rank_score = sum(value * weight for value, weight in weighted) / total_weight

    return rank_score, {
        "week_return": week_return,
        "revenue_growth": revenue_growth,
        "margin_trend": margin_trend,
        "relative_strength": relative_strength,
        "volatility_contracting": contracting,
        "revision_breadth": revision_breadth if isinstance(revision_breadth, (int, float)) else None,
        "rank_score": rank_score,
    }


def rank_week_emerging_growth(universe_data, benchmark_closes_to_date, as_of, report_lag_days,
                              allow_current_shares=False, allow_empty_fundamentals=True):
    """Drop-in replacement for backtest_historical.rank_week: same signature and same
    best-first-sorted return shape, ranked by the emerging-growth score instead of the
    champion score. Names that don't clear every gate are excluded entirely (a screen, not a
    universe re-ranking) rather than assigned score 0 and appearing at the bottom.
    """
    base_rows = rank_week(universe_data, benchmark_closes_to_date, as_of, report_lag_days,
                          allow_current_shares, allow_empty_fundamentals)
    scored = []
    for row in base_rows:
        ticker_data = universe_data.get(row["ticker"])
        closes_to_date = None
        if ticker_data is not None:
            built = build_snapshot(ticker_data, as_of, report_lag_days, allow_current_shares,
                                   allow_empty_fundamentals)
            if built is not None:
                _, closes_to_date, _ = built
        result = emerging_growth_score(row, closes_to_date)
        if result is None:
            continue
        score, detail = result
        scored.append({
            **row,
            "score": round(score, 2),
            "screen": detail,
            "research_status": "prospective_unvalidated",
        })
    scored.sort(key=lambda entry: (-entry["score"], entry["ticker"]))
    return scored
