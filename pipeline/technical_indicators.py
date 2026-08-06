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
