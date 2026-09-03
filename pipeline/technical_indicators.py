"""Bounded technical-indicator family (docs/RESEARCH-CONTRACT.md, brief section 2.5).

Deliberately small. The literature on "best" technical indicators (wrapper searches over
100+ indicators on a single stock, small-sample ML studies with no multiple-testing
correction) mostly demonstrates data-snooping, not real signal -- most named indicators are
different nonlinear transformations of the same OHLCV path and are heavily correlated with
each other and with what advisor_engine.technical_factors already scores (12-1 momentum,
Sharpe/Sortino, relative strength, drawdown resilience). Adding many of them would not add
independent information; it would add correlated noise that looks like more breadth.

This module adds exactly one representative from each of four *distinct* economic families
that the existing composite does not already cover, rather than the full zoo:
  * trend      -- moving_average_slope (a different signal than 12-1 momentum: rate of
                  change of the trend itself, not the return)
  * oscillator -- relative_strength_index (mean-reversion/overbought-oversold, a different
                  economic story than trend-following momentum)
  * volatility -- bollinger_percent_b (price position within its own volatility band)
  * volume     -- on_balance_volume_slope (a cumulative, direction-weighted volume measure)

This is a genuine addition, not a swap: advisor_engine.technical_factors still computes its
own up/down volume ratio (volume_confirmation, 8% of market_behavior) separately.
on_balance_volume_slope sits alongside it inside technical_extended (6% of market_behavior,
so roughly 1% of the total composite score once technical_extended's four sub-indicators
are equally weighted against each other) rather than replacing it -- a like-for-like swap of
volume_confirmation itself was considered and would need its own dedicated IC-harness trial
to justify changing an existing production weight; that has not been run, so the existing
metric was left untouched and this is scoped as a small net-new family instead.

Every function is pure (closes/volumes in, a bounded score out) and returns None rather than
a fabricated value when there isn't enough history.

``support_resistance_levels`` below is a deliberate fifth addition that does NOT follow the
same rule: it is never wired into ``technical_extended_score`` or any scored weight in
``advisor_engine.technical_factors``. A 2026 literature review for this repository found no
peer-reviewed evidence that generic support/resistance levels predict single-name US equity
returns after data-snooping correction -- see that function's docstring for the full citation
trail. It is published purely as entry/stop-placement context, the same "computed but not
scored" pattern ``reverse_dcf`` and ``return_attribution`` already use elsewhere in this
pipeline.
"""

from statistics import mean


def moving_average_slope(closes, window=50, lookback=10):
    """Percent change in the ``window``-session moving average over the trailing ``lookback``
    sessions -- the trend's own rate of change, not the price return.
    """
    if len(closes) < window + lookback:
        return None
    averages = [
        mean(closes[index - window:index])
        for index in range(len(closes) - lookback, len(closes) + 1)
    ]
    if not averages[0]:
        return None
    return round((averages[-1] / averages[0] - 1) * 100, 3)


def relative_strength_index(closes, window=14):
    """Classic Wilder RSI, 0-100. Below 30 conventionally "oversold", above 70 "overbought"."""
    if len(closes) < window + 1:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    recent = changes[-window:]
    gains = [change for change in recent if change > 0]
    losses = [-change for change in recent if change < 0]
    average_gain = sum(gains) / window
    average_loss = sum(losses) / window
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return round(100 - (100 / (1 + relative_strength)), 2)


def bollinger_percent_b(closes, window=20, num_std=2):
    """Where price sits within its own rolling volatility band: 0 = lower band, 1 = upper
    band, 0.5 = the moving average itself. Values outside [0, 1] mean price pierced the band.
    """
    if len(closes) < window:
        return None
    recent = closes[-window:]
    average = mean(recent)
    variance = sum((value - average) ** 2 for value in recent) / window
    std_dev = variance ** 0.5
    if std_dev == 0:
        return None
    upper = average + num_std * std_dev
    lower = average - num_std * std_dev
    if upper == lower:
        return None
    return round((closes[-1] - lower) / (upper - lower), 3)


def on_balance_volume_slope(closes, volumes, window=20):
    """Percent change in cumulative on-balance volume over the trailing ``window`` sessions.

    OBV adds a session's volume when price closes up and subtracts it when price closes
    down, so its slope reflects whether volume is confirming or diverging from the price
    trend -- a similar economic idea to advisor_engine.volume_confirmation's up/down ratio,
    computed as a running series instead of a fixed-window ratio. See this module's
    docstring for why the two coexist rather than one replacing the other.
    """
    if not volumes or len(volumes) != len(closes) or len(closes) < window + 2:
        return None
    obv = [0.0]
    for index in range(1, len(closes)):
        if closes[index] > closes[index - 1]:
            obv.append(obv[-1] + volumes[index])
        elif closes[index] < closes[index - 1]:
            obv.append(obv[-1] - volumes[index])
        else:
            obv.append(obv[-1])
    window_slice = obv[-window - 1:]
    baseline = window_slice[0]
    scale = mean(volumes[-window:]) or 1.0
    if scale <= 0:
        return None
    # OBV has no natural denominator (it's a running sum, not a ratio) -- normalize the
    # window's net change by average volume over the same window so the result is a
    # comparable, bounded-ish percentage rather than an unscaled cumulative number.
    return round((window_slice[-1] - baseline) / (scale * window), 3)


def technical_extended_score(closes, volumes):
    """Combine the four indicators above into one bounded 0-100 score, equally weighted
    among whichever resolve (missing indicators reweight the rest rather than scoring
    neutral). Returns ``(score, detail)`` where ``detail`` carries every raw indicator value
    for transparency, matching the pattern the rest of advisor_engine.technical_factors uses.
    """
    raw = {
        "moving_average_slope": moving_average_slope(closes),
        "relative_strength_index": relative_strength_index(closes),
        "bollinger_percent_b": bollinger_percent_b(closes),
        "on_balance_volume_slope": on_balance_volume_slope(closes, volumes),
    }
    scored = {
        "moving_average_slope": None if raw["moving_average_slope"] is None
            else max(0.0, min(100.0, 50 + raw["moving_average_slope"] * 4)),
        # RSI centered at 50 is neutral; both overbought (100) and oversold (0) extremes are
        # scored toward the middle here since this is a trend/breadth signal, not a dedicated
        # mean-reversion sleeve (that belongs to the reversal sleeves, not this one).
        "relative_strength_index": raw["relative_strength_index"],
        "bollinger_percent_b": None if raw["bollinger_percent_b"] is None
            else max(0.0, min(100.0, raw["bollinger_percent_b"] * 100)),
        "on_balance_volume_slope": None if raw["on_balance_volume_slope"] is None
            else max(0.0, min(100.0, 50 + raw["on_balance_volume_slope"] * 500)),
    }
    available = [value for value in scored.values() if value is not None]
    if not available:
        return None, {"raw": raw, "scored": scored, "coverage": 0.0}
    score = round(sum(available) / len(available), 1)
    return score, {"raw": raw, "scored": scored, "coverage": round(len(available) / len(scored), 2)}


def _local_pivots(values, window):
    """Indices where ``values[i]`` is the strict extreme of its own ``+/- window`` neighborhood.

    A swing pivot only exists once price has moved away from it on both sides, so the final
    ``window`` sessions can never qualify -- that is inherent to the definition, not a bug:
    the most recent potential turning point is still unconfirmed.
    """
    highs, lows = [], []
    for index in range(window, len(values) - window):
        segment = values[index - window:index + window + 1]
        pivot = values[index]
        if pivot == max(segment):
            highs.append(index)
        if pivot == min(segment):
            lows.append(index)
    return highs, lows


def _cluster_levels(prices, tolerance_pct):
    """Merge nearby prices into levels, ascending by price.

    A sorted-adjacent-gap clustering: walk prices low to high and start a new level whenever
    the next price is more than ``tolerance_pct`` away from the current level's running
    average. This is the one-dimensional analogue of the "levels" a chart reader draws by eye,
    made mechanical and reproducible so it needs no discretion to compute.
    """
    if not prices:
        return []
    ordered = sorted(prices)
    levels = [[ordered[0]]]
    for price in ordered[1:]:
        average = mean(levels[-1])
        if average and abs(price - average) / average * 100 <= tolerance_pct:
            levels[-1].append(price)
        else:
            levels.append([price])
    return [{"price": round(mean(level), 4), "touches": len(level)} for level in levels]


def support_resistance_levels(closes, lookback=126, pivot_window=5, cluster_tolerance_pct=1.5):
    """Nearest computed support (below price) and resistance (above price), from clustered
    swing pivots over the trailing ``lookback`` sessions.

    INFORMATIONAL ONLY -- see this module's docstring. This is deliberately excluded from
    ``technical_extended_score`` and every scored weight in ``advisor_engine.technical_factors``.
    A 2026 literature review for this repository found no peer-reviewed evidence that generic
    support/resistance levels predict single-name US equity returns after data-snooping
    correction: the rigorous version of this idea (Osler, "Support for Resistance," Federal
    Reserve Bank of New York Economic Policy Review, 2000; Osler, Journal of Finance, 2003) is a
    currency order-book mechanism -- clustered take-profit/stop-loss orders at round numbers in
    a dealer market -- with no equivalent, observable order book in fragmented single-name US
    equities. Marshall, Cahan & Cahan (Journal of Empirical Finance, 2008) tested 7,846
    technical rules, including a support-and-resistance family, on US equities and found none
    profitable after data-snooping adjustment. The one reference-point effect with genuine US
    single-stock evidence -- nearness to the 52-week high (George & Hwang, Journal of Finance,
    2004) -- is a distinct, already-scored signal (see swing_signals.high_52w_drawdown_sigmas),
    not this function.

    This exists as entry/stop-placement CONTEXT: how far price sits from a level where it has
    previously reversed, and how many times that level has been tested -- not a return
    forecast. Pivots are detected from closing prices alone (this pipeline does not carry
    intraday highs/lows for every row), a coarser read than a true wick-based level, but it
    keeps the definition mechanical and reproducible from the same series every other function
    in this module already uses.

    Returns ``None`` if there isn't enough history to find a single pivot. Otherwise a dict
    with the nearest support/resistance price, their distance from the current close as a
    percent, and each level's touch count. Either side can be ``None`` on its own -- a name
    making new highs has no resistance above it yet, one making new lows has no support below.
    """
    if len(closes) < pivot_window * 2 + 10:
        return None
    window = closes[-lookback:] if len(closes) > lookback else closes
    high_idx, low_idx = _local_pivots(window, pivot_window)
    if not high_idx and not low_idx:
        return None
    current = window[-1]
    resistance_levels = _cluster_levels([window[index] for index in high_idx], cluster_tolerance_pct)
    support_levels = _cluster_levels([window[index] for index in low_idx], cluster_tolerance_pct)

    resistance_above = [level for level in resistance_levels if level["price"] > current]
    support_below = [level for level in support_levels if level["price"] < current]
    nearest_resistance = min(resistance_above, key=lambda level: level["price"], default=None)
    nearest_support = max(support_below, key=lambda level: level["price"], default=None)
    if nearest_resistance is None and nearest_support is None:
        return None

    return {
        "nearest_support": nearest_support["price"] if nearest_support else None,
        "support_distance_pct": round((current / nearest_support["price"] - 1) * 100, 2)
            if nearest_support else None,
        "support_touch_count": nearest_support["touches"] if nearest_support else None,
        "nearest_resistance": nearest_resistance["price"] if nearest_resistance else None,
        "resistance_distance_pct": round((nearest_resistance["price"] / current - 1) * 100, 2)
            if nearest_resistance else None,
        "resistance_touch_count": nearest_resistance["touches"] if nearest_resistance else None,
        "lookback_sessions": len(window),
    }
