"""Market-wide regime context: breadth, a Hurst-exponent trend/mean-reversion read, and a
passthrough of the already-published VIX regime.

Cross-sectional over the *whole* scored universe, not any one screen's eligible subset - a
different scope than every per-ticker signal in swing_signals.py, so this gets its own module
rather than living inside that file or inline in build_swing_screen.py. Descriptive only:
nothing here enters swing_signals.swing_scores, any tier's ranking, or any other screen's
score - see MARKET_REGIME_EVIDENCE and REGIME_GATE_NOTE below, and
pipeline/swing_signals.py's CONTEXT_NOTE for the same "never a scoring leg" rule applied at
the per-name level instead of the market level.

Named distinctly from src/lib/marketPresentation.js's ``marketType()``, which already
computes and displays a same-day advance/decline breadth on the dashboard - how many names
are up *today*. ``breadth()`` here measures a different thing entirely: how many names sit
above their own 50-day/200-day moving average, a multi-month trend-participation read in the
Zweig/Lowry tradition. The two are not interchangeable and are not meant to agree.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from screen_inputs import backtest_entry
from swing_signals import universe_daily_returns

MARKET_REGIME_EVIDENCE = {
    "breadth_50_200dma": {
        "label": "Market breadth (% of universe above its 50-day / 200-day moving average)",
        "horizon": "regime read, not a per-name signal",
        "direction": "n/a - a market-wide gate, never a per-name score",
        "citation": "Martin Zweig, Winning on Wall Street (1986); Lowry's Reports "
                    "advance-decline breadth tradition",
        "effect": "Broad participation (a high share of names above their 200-day average) is "
                  "read as confirming an uptrend's durability; narrow participation is read as "
                  "a warning even while a cap-weighted index still holds up.",
        "caveat": "An equal-name-count share, not cap-weighted, and it says nothing about "
                  "which names - see swing.json's regime_gate.breadth for the count behind it.",
    },
    "hurst_regime": {
        "label": "Hurst exponent (rescaled-range) trend/mean-reversion read",
        "horizon": "regime read over the trailing window, not a per-name signal",
        "direction": "n/a - a market-wide gate, never a per-name score",
        "citation": "H.E. Hurst, Transactions of the American Society of Civil Engineers 116 "
                    "(1951); Edgar Peters, Fractal Market Analysis (1994)",
        "effect": "H meaningfully above 0.5 reads as a trending regime, historically the "
                  "setting the S tier's continuation legs (pead_drift, analyst_revision, "
                  "high_52w_proximity) are built for; H meaningfully below 0.5 reads as "
                  "mean-reverting, the setting the F tier's short_term_reversal leg and the "
                  "rsi_2/bandwidth_squeeze/narrow_range/atr_compression context signals are "
                  "built for; H near 0.5 reads as a random walk.",
        "caveat": "Classic rescaled-range Hurst is small-sample biased; no Anis-Lloyd/Lo "
                  "(1991) correction is applied here - read the label, not the third decimal.",
    },
    "new_highs_new_lows": {
        "label": "Market breadth (% of universe within threshold_pct of its own trailing-252-"
                 "session high/low)",
        "horizon": "regime read, not a per-name signal",
        "direction": "n/a - a market-wide gate, never a per-name score",
        "citation": "Martin Zweig, Winning on Wall Street (1986); Lowry's Reports "
                    "new-highs/new-lows breadth tradition",
        "effect": "A high share of names near their own 52-week high alongside few near a "
                  "52-week low reads as broad-based strength; the reverse (many near lows, "
                  "few near highs) reads as broad-based weakness, even while a cap-weighted "
                  "index still holds up. A distinct breadth flavor from breadth() above: this "
                  "asks how many names are near a price extreme, not how many sit above a "
                  "moving average.",
        "caveat": "An equal-name-count share, not cap-weighted, over each name's own trailing "
                  "252 sessions rather than a calendar 52-week window, and says nothing about "
                  "which names.",
    },
    "vix_regime": {
        "label": "VIX level/trend regime",
        "horizon": "regime read, not a per-name signal",
        "direction": "n/a - a market-wide gate, never a per-name score",
        "citation": "Derived by pipeline/fred.py::derive_regime from the CBOE VIX via FRED "
                    "(VIXCLS)",
        "effect": "A restrictive/elevated volatility reading has historically favored "
                  "short-horizon mean-reversion setups; a supportive/low reading has "
                  "historically favored continuation setups.",
        "caveat": "Passthrough only - never a raw observation, only the already-published "
                  "0-100 score/label/as_of from advisor.json market.macro.regime."
                  "factors.volatility. See validate_data.py's ban on publishing raw FRED "
                  "observations, which this module never touches.",
    },
}

REGIME_GATE_NOTE = (
    "Reading guidance, never a trigger and never a per-name score - see "
    "MARKET_REGIME_EVIDENCE. Broad breadth and a supportive VIX read have historically "
    "favored the S tier's continuation legs; a mean-reverting Hurst read alongside a "
    "restrictive VIX read is the setting the F tier's short_term_reversal leg and the "
    "reversal-family context signals were built for. None of this changes eligibility, a "
    "score, or a rank anywhere in this screen.")


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def moving_average(closes, window):
    series = [close for close in (closes or [])[-window:] if _finite(close) and close > 0]
    return sum(series) / len(series) if len(series) >= window else None


def _load_entries(universe, entry_for):
    """{ticker: price_archive-style entry} for every non-ETF ticker with cached closes.

    Loaded once and shared by breadth() and regime_gate()'s own daily-return series, rather
    than each re-reading pipeline/data/backtest_cache separately.
    """
    entries = {}
    for row in universe or []:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        entry = entry_for(ticker) or {}
        if entry.get("closes"):
            entries[ticker] = entry
    return entries


def breadth(entries, as_of=None):
    """% of ``entries`` trading above its own 50-day and 200-day moving average.

    ``entries`` is {ticker: {"closes": [...], ...}} - see _load_entries and regime_gate for
    how it's built once and shared rather than re-fetched per function. None when nothing in
    ``entries`` resolves a 50-day or 200-day average.
    """
    above_50 = above_200 = counted = 0
    for entry in (entries or {}).values():
        closes = entry.get("closes") or []
        if not closes or not _finite(closes[-1]):
            continue
        price = closes[-1]
        ma50, ma200 = moving_average(closes, 50), moving_average(closes, 200)
        if ma50 is None and ma200 is None:
            continue
        counted += 1
        if ma50 is not None and price > ma50:
            above_50 += 1
        if ma200 is not None and price > ma200:
            above_200 += 1
    if not counted:
        return None
    return {
        "above_50dma_pct": round(100 * above_50 / counted, 1),
        "above_200dma_pct": round(100 * above_200 / counted, 1),
        "universe_count": counted,
        "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
    }


# How close to its own trailing high/low a name has to be to count as "near" it. 5% mirrors
# the tolerance src/lib's own 52-week-high proximity displays already use elsewhere in the app.
NEW_HIGH_LOW_THRESHOLD_PCT = 5.0


def new_highs_new_lows(entries, threshold_pct=NEW_HIGH_LOW_THRESHOLD_PCT, as_of=None):
    """% of ``entries`` within ``threshold_pct`` of its own trailing-252-session high/low.

    A second breadth flavor beside breadth()'s 50/200dma participation read: the Zweig/Lowry
    breadth tradition also tracks new-highs-versus-new-lows as a separate
    confirmation/divergence signal, not just moving-average participation. Same non-scored,
    market-wide regime-context role as breadth() -- see REGIME_GATE_NOTE and
    MARKET_REGIME_EVIDENCE. Reuses the same per-ticker close series breadth() already receives
    via _load_entries; no new fetch. None when nothing in ``entries`` resolves a high/low.
    """
    near_high = near_low = counted = 0
    for entry in (entries or {}).values():
        closes = entry.get("closes") or []
        if not closes or not _finite(closes[-1]):
            continue
        window = [close for close in closes[-252:] if _finite(close) and close > 0]
        if len(window) < 20:
            continue
        price = closes[-1]
        high, low = max(window), min(window)
        counted += 1
        if price >= high * (1 - threshold_pct / 100):
            near_high += 1
        if price <= low * (1 + threshold_pct / 100):
            near_low += 1
    if not counted:
        return None
    return {
        "near_52w_high_pct": round(100 * near_high / counted, 1),
        "near_52w_low_pct": round(100 * near_low / counted, 1),
        "threshold_pct": threshold_pct,
        "universe_count": counted,
        "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
    }


def hurst_regime(daily_returns, window=252):
    """Classic rescaled-range (R/S) Hurst exponent on an equal-weighted daily return series.

    ``daily_returns`` is swing_signals.universe_daily_returns's output: index 0 is the latest
    session, oldest-to-newest order is reversed here for a standard R/S walk. Small-sample
    biased by construction (no Anis-Lloyd/Lo correction) - see
    MARKET_REGIME_EVIDENCE['hurst_regime']. None below a 60-session floor.
    """
    series = [value for value in (daily_returns or [])[:window] if _finite(value)]
    if len(series) < 60:
        return None
    series = list(reversed(series))
    mean = sum(series) / len(series)
    deviations = [value - mean for value in series]
    cumulative, running = [], 0.0
    for value in deviations:
        running += value
        cumulative.append(running)
    spread = max(cumulative) - min(cumulative)
    variance = sum(value ** 2 for value in deviations) / len(deviations)
    deviation = math.sqrt(variance)
    if not deviation or spread <= 0:
        return None
    rescaled_range = spread / deviation
    hurst = math.log(rescaled_range) / math.log(len(series))
    if hurst > 0.55:
        label = "trending"
    elif hurst < 0.45:
        label = "mean_reverting"
    else:
        label = "random_walk"
    return {"hurst": round(hurst, 3), "label": label, "window": len(series),
           "as_of": datetime.now(timezone.utc).date().isoformat()}


def vix_regime(advisor_macro_regime):
    """Passthrough of the already-published VIX regime score/label - never a raw observation.

    See MARKET_REGIME_EVIDENCE['vix_regime'] and validate_data.py's ban on publishing raw
    FRED observations, neither of which this function ever reads.
    """
    volatility = ((advisor_macro_regime or {}).get("factors") or {}).get("volatility")
    if not volatility:
        return None
    return {"score": volatility.get("score"), "label": volatility.get("label"),
           "as_of": volatility.get("as_of")}


def regime_gate(universe, advisor_macro_regime, entry_for=None):
    """The combined market-wide regime read, computed once per swing-screen run.

    ``universe`` is screen_inputs.universe_rows()'s output. ``advisor_macro_regime`` is
    advisor.json's market.macro.regime dict. ``entry_for`` defaults to
    screen_inputs.backtest_entry - injectable for the same reason build_swing_screen.py's
    build_rows takes the same parameter: a test builds this without touching disk.
    """
    entry_for = entry_for or backtest_entry
    entries = _load_entries(universe, entry_for)
    daily_returns = universe_daily_returns([entry["closes"] for entry in entries.values()])
    return {
        "breadth": breadth(entries),
        "new_highs_new_lows": new_highs_new_lows(entries),
        "hurst": hurst_regime(daily_returns),
        "vix": vix_regime(advisor_macro_regime),
        "evidence": MARKET_REGIME_EVIDENCE,
        "note": REGIME_GATE_NOTE,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }
