"""The swing-horizon signal layer: 2 trading days to 8 weeks, evidence-ranked.

Every existing screen in this pipeline answers a question at a different horizon. The
momentum screen is monthly and skip-month by construction (research_screens_v2), the
quality-value screen is quarterly, the tactical screen is one-to-three months. Nothing here
ranked the cross-section over the two-day-to-eight-week window, and the retail technical
canon that usually gets pointed at that window (RSI 70/30, MACD crossovers, Bollinger
signals, OBV, candlesticks) has weak-to-no support in US single-stock data once data
snooping and costs are accounted for - see SWING_EVIDENCE below for what survived and what
did not.

Five legs, in descending order of published evidence at this horizon:

  pead_drift            post-earnings-announcement drift, Bernard & Thomas (1989, 1990)
  analyst_revision      the *change* in consensus, Jegadeesh-Kim-Krische-Lee (2004)
  high_volume_premium   the high-volume return premium, Gervais-Kaniel-Mingelgrin (2001)
  high_52w_proximity    nearness to the 52-week high, George & Hwang (2004)
  short_term_reversal   prior-week return, reversed, Jegadeesh (1990) - cost-gated

Three rules this file exists to enforce.

1. **The sign flip is handled explicitly.** The same raw trailing return predicts reversal
   at 2-10 days and continuation at 3-12 months. Feeding one "past return" factor across the
   whole window averages to noise. So the reversal leg reads *only* the last five sessions,
   the continuation leg is 52-week-high proximity (which carries no recent-month return in
   it at all), and no raw trailing return appears twice.

2. **Cost gating is part of the model, not a footnote.** Short-term reversal is a
   liquidity-provision premium: Da-Liu-Schaumburg (2014) reduce the naive three-factor alpha
   to 0.33%/month at t=1.37, and Frazzini-Israel-Moskowitz find reversal the most
   capacity-constrained strategy they measure. The leg is therefore dropped entirely on any
   name below REVERSAL_MIN_DOLLAR_VOLUME rather than scored and quietly eaten by spread.

3. **Short interest is a negative screen, never a leg.** Boehmer-Jones-Zhang (2008) is a
   short-side result and this book is long-only, so heavily-shorted names are suppressed out
   of eligibility with a reason code instead of contributing a factor.

Legs a row cannot fill are dropped and the remaining weights renormalized, exactly as the
ranking models do client-side; the row pays for the gap in published `coverage`, not in a
fabricated middling score. Nothing here fetches: every input is the committed advisor
snapshot plus the on-disk backtest cache, so the screen is re-derivable from the repository.
"""

from __future__ import annotations

import math

from research_screens_v2 import winsorize, zscores

# Declared weights. Starting priors ordered by evidence quality at this horizon, frozen so
# the point-in-time store accumulates observations under one fixed policy - not measured
# optima, and explicitly not claims of expected return.
SWING_WEIGHTS = {
    "pead_drift": .30,
    "analyst_revision": .25,
    "high_volume_premium": .20,
    "high_52w_proximity": .15,
    "short_term_reversal": .10,
}

# The subfactors each leg averages, after each is winsorized and z-scored across the
# cross-section. `negate` flags the ones whose published direction is contrarian.
SWING_SUBFACTORS = {
    "pead_drift": (("earnings_surprise", False),),
    "analyst_revision": (("revision_breadth_30d", False), ("eps_revision_30d_pct", False),
                         ("net_upgrades_90d", False), ("target_change_30d_pct", False)),
    "high_volume_premium": (("volume_ratio_1d_50d", False), ("volume_ratio_5d_50d", False)),
    "high_52w_proximity": (("high_52w_proximity", False),),
    # The one leg whose sign is reversed: last week's winners are next week's laggards.
    "short_term_reversal": (("return_5d", True),),
}

# What each leg rests on, published into the screen file so the page can state the evidence
# beside the score rather than asserting the score is meaningful. `effect` figures are gross
# (pre-cost, pre-decay) as published; DECAY_HAIRCUT below is the standing discount.
SWING_EVIDENCE = {
    "pead_drift": {
        "label": "Post-earnings drift (SUE)",
        "horizon": "1-8 weeks",
        "direction": "continuation of the surprise",
        "citation": "Bernard & Thomas, Journal of Accounting Research 1989; "
                    "Journal of Accounting and Economics 1990",
        "effect": "CARs drift with the surprise over ~60 trading days, monotone in SUE; "
                  "25-30% of the drift lands in the 3-day window around the next announcement",
        "caveat": "Strongest in small and illiquid names, which is where spreads are widest. "
                  "Coverage here depends on reported surprise history being resolvable for the row.",
    },
    "analyst_revision": {
        "label": "Analyst revision (change, not level)",
        "horizon": "1 week to 6 months",
        "direction": "direction of the revision",
        "citation": "Jegadeesh, Kim, Krische & Lee, Journal of Finance 2004; "
                    "Womack, Journal of Finance 1996; Gleason & Lee, The Accounting Review 2003",
        "effect": "The quarterly change in consensus is a robust predictor orthogonal to a wide "
                  "range of other variables; new sells drift -9.1% over six months, new buys +2.4%",
        "caveat": "The asymmetry favours the short/avoid side, which a long-only book cannot "
                  "harvest. The *level* of consensus adds value only among favourable quant names.",
    },
    "high_volume_premium": {
        "label": "High-volume return premium",
        "horizon": "1-4 weeks",
        "direction": "continuation",
        "citation": "Gervais, Kaniel & Mingelgrin, Journal of Finance 2001; "
                    "Kaniel, Li & Starks (SSRN 474100)",
        "effect": "Stocks with unusually high daily or weekly volume appreciate over the "
                  "following month; unusually low volume depreciates",
        "caveat": "Consistent with an investor-recognition mechanism, not a risk premium. "
                  "On-balance volume, a different construction, has no comparable support.",
    },
    "high_52w_proximity": {
        "label": "52-week-high proximity",
        "horizon": "1-3 months",
        "direction": "continuation",
        "citation": "George & Hwang, Journal of Finance 2004",
        "effect": "US spread ~0.45%/month; international 0.60-0.94%/month, and the forecast "
                  "returns do not reverse in the long run",
        "caveat": "This is the momentum family accessed inside an 8-week ceiling. It carries no "
                  "recent-month return, which is what keeps it from cancelling the reversal leg.",
    },
    "short_term_reversal": {
        "label": "Short-term reversal (prior week, reversed)",
        "horizon": "2-10 days",
        "direction": "contrarian",
        "citation": "Jegadeesh, Journal of Finance 1990; Lehmann, QJE 1990; "
                    "Da, Liu & Schaumburg, Management Science 2014; Nagel, NBER w17653 (2012)",
        "effect": "~2%/month gross in the original sample; 0.33%/month risk-adjusted at t=1.37 "
                  "in modern samples, and near zero once momentum and a refined reversal factor enter",
        "caveat": "A liquidity-provision premium, and the most capacity-constrained strategy in "
                  "Frazzini-Israel-Moskowitz. Cost-gated here to liquid names and held to the "
                  "smallest weight in the composite.",
    },
}

# The negative screen. Boehmer-Jones-Zhang (2008): heavily shorted names underperform lightly
# shorted by ~1.16% over the following 20 trading days. A long-only book cannot take the short
# leg, so this suppresses rather than scores.
SHORT_INTEREST_EVIDENCE = {
    "label": "Short interest / days-to-cover (negative screen)",
    "horizon": "~1 month",
    "direction": "negative - suppression only, never a leg",
    "citation": "Boehmer, Jones & Zhang, Journal of Finance 2008; "
                "Boehmer, Huszár, Wang, Zhang & Zhang, Review of Financial Studies 2022",
    "effect": "-1.16% over 20 trading days for heavily shorted NYSE names (-1.43%/month when "
              "heavily shorted by institutions)",
    "caveat": "Asquith-Pathak-Ritter's larger equal-weighted figure is microcap-driven and "
              "insignificant value-weighted. The short-sale-cost literature conflicts on whether "
              "the short leg survives borrow fees at all; suppression sidesteps that question.",
}

# McLean & Pontiff (Journal of Finance 2016) over 97 predictors: 26% lower out of sample, 58%
# lower post-publication. Every effect size above is gross and pre-decay; this is published
# alongside them so the numbers are never read as live expectations. It is disclosure, not a
# multiplier - the composite is a cross-sectional rank and haircutting a rank means nothing.
DECAY_HAIRCUT = {"out_of_sample": .26, "post_publication": .58,
                 "source": "McLean & Pontiff, Journal of Finance 2016",
                 "note": "Decay is worst in high-idiosyncratic-risk, low-liquidity names, which is "
                         "where the paper alpha concentrates."}

HOLDING_HORIZON = {"minimum_trading_days": 2, "maximum_trading_days": 40,
                   "note": "Legs peak at different points inside this window; the composite is "
                           "ranked daily and is not a hold-to-target instruction."}

# Eligibility gates, deliberately the same shape and defaults as the momentum screen's so the
# two screens exclude the same names for the same stated reasons.
DEFAULT_CONFIG = {
    "minimum_price": 5,
    "minimum_market_cap": 300_000_000,
    "minimum_median_dollar_volume_60d": 2_000_000,
    "minimum_history_sessions": 253,
    # Below this share of the declared weight the composite is an opinion about one or two
    # inputs wearing a composite's clothes. Published and ranked, but not called eligible.
    "minimum_coverage": .35,
    # The reversal leg is only scored where spread cost plausibly leaves something behind.
    "reversal_minimum_dollar_volume": 25_000_000,
    # Negative screen thresholds. Short interest above either line suppresses the row.
    "short_percent_of_float_limit": .10,
    "days_to_cover_limit": 5.0,
    # PEAD drift is a claim about a *recent* announcement. Past this the drift window has
    # closed and the leg is dropped rather than carried on a stale surprise.
    "pead_window_trading_days": 60,
    "entry_percentile": 90,
    "exit_percentile": 75,
}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def trailing_return(closes, sessions):
    """Percent return over the last `sessions` closes, or None when history is too short."""
    series = [close for close in (closes or []) if _finite(close) and close > 0]
    if len(series) <= sessions:
        return None
    start = series[-(sessions + 1)]
    return (series[-1] / start - 1) * 100 if start else None


def high_52w_proximity(closes, window=252):
    """Latest close as a share of the trailing 52-week high, 0-1, George-Hwang's measure.

    Deliberately *not* a return: the whole point of this factor is that it forecasts as well
    as past-return momentum without carrying a recent-month return that would fight the
    reversal leg.
    """
    series = [close for close in (closes or [])[-window:] if _finite(close) and close > 0]
    if len(series) < 60:
        return None
    peak = max(series)
    return series[-1] / peak if peak else None


def volume_surge(volumes, recent=1, reference=50):
    """Recent volume against its own trailing reference average.

    Gervais-Kaniel-Mingelgrin measure a day's or a week's volume against the stock's own
    normal, not against other stocks - a 2-million-share day is unusual for one name and
    quiet for another. The cross-sectional ranking happens afterwards, on this ratio.
    """
    series = [volume for volume in (volumes or []) if _finite(volume) and volume >= 0]
    if len(series) < reference + recent:
        return None
    window = series[-(reference + recent):-recent] if recent else series[-reference:]
    baseline = sum(window) / len(window) if window else 0
    if not baseline:
        return None
    latest = series[-recent:]
    return (sum(latest) / len(latest)) / baseline


def realized_volatility(closes, window=60):
    """Annualized standard deviation of daily log returns - normalization, never direction.

    Ang-Hodrick-Xing-Zhang is a monthly, microcap-heavy result that overlaps reversal, so
    volatility earns no leg here. It is published for position sizing and for reading the
    reversal leg in context.
    """
    series = [close for close in (closes or [])[-(window + 1):] if _finite(close) and close > 0]
    if len(series) < 21:
        return None
    returns = [math.log(series[index + 1] / series[index]) for index in range(len(series) - 1)]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def earnings_event_age(row):
    """Trading days since this row's freshest dated earnings event, or None if undated.

    The advisor snapshot carries dated news events with their event types; an earnings event
    is the only announcement date available on disk. Used to decide whether the drift window
    is still open, never to score direction.
    """
    events = ((row.get("evidence") or {}).get("news_events")
              or (row.get("evidence_summary") or {}).get("news_events") or [])
    ages = [event.get("age_trading_days") for event in events
            if isinstance(event, dict) and "earnings" in (event.get("event_types") or [])
            and _finite(event.get("age_trading_days"))]
    return min(ages) if ages else None


def pead_factor(row, config=None):
    """The SUE leg: the row's published earnings surprise, gated to an open drift window.

    Returns (value, status). `status` is published per row so a dropped leg always says
    which of the three reasons applied - no surprise resolved, the window has closed, or the
    announcement date is unknown and the surprise is being used anyway.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    surprise = row.get("earnings_surprise")
    if not _finite(surprise):
        return None, "NO_SURPRISE_HISTORY"
    age = earnings_event_age(row)
    if age is None:
        return float(surprise), "WINDOW_UNKNOWN"
    if age > config["pead_window_trading_days"]:
        return None, "DRIFT_WINDOW_CLOSED"
    return float(surprise), "IN_DRIFT_WINDOW"


def swing_factors(row, closes=None, volumes=None, config=None):
    """Every raw subfactor for one row, before any cross-sectional ranking.

    Price and volume subfactors come from the cached daily series; revision subfactors come
    from the row's own published `estimate_detail`. Anything unresolvable stays None so the
    leg it belongs to is dropped rather than filled with a neutral value.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    estimates = row.get("estimate_detail") or {}
    surprise, pead_status = pead_factor(row, config)
    return {
        "earnings_surprise": surprise,
        "pead_status": pead_status,
        "revision_breadth_30d": estimates.get("revision_breadth_30d"),
        "eps_revision_30d_pct": estimates.get("eps_revision_30d_pct"),
        "net_upgrades_90d": estimates.get("net_upgrades_90d"),
        "target_change_30d_pct": estimates.get("target_change_30d_pct"),
        "volume_ratio_1d_50d": volume_surge(volumes, recent=1),
        "volume_ratio_5d_50d": volume_surge(volumes, recent=5),
        "high_52w_proximity": high_52w_proximity(closes),
        "return_5d": trailing_return(closes, 5),
        # Context, published but never scored: see realized_volatility's docstring.
        "realized_volatility_60d": realized_volatility(closes),
        "return_20d": trailing_return(closes, 20),
    }


def short_interest_flag(row, config=None):
    """Whether the negative screen fires on this row, and on which of the two measures."""
    config = {**DEFAULT_CONFIG, **(config or {})}
    short_pct = row.get("short_percent_of_float")
    days = row.get("days_to_cover")
    hits = []
    if _finite(short_pct) and short_pct >= config["short_percent_of_float_limit"]:
        hits.append(f"{short_pct * 100:.1f}% of float short")
    if _finite(days) and days >= config["days_to_cover_limit"]:
        hits.append(f"{days:.1f} days to cover")
    return {"suppressed": bool(hits), "reasons": hits,
            "short_percent_of_float": short_pct if _finite(short_pct) else None,
            "days_to_cover": days if _finite(days) else None}


def _standardized_subfactors(rows, config):
    """{subfactor: [z or None per row]}, winsorized first so one outlier cannot set the scale."""
    standardized = {}
    for leg, subfactors in SWING_SUBFACTORS.items():
        for name, negate in subfactors:
            raw = []
            for row in rows:
                value = (row.get("factors") or {}).get(name)
                if not _finite(value):
                    raw.append(None)
                    continue
                if leg == "short_term_reversal" and not _reversal_tradable(row, config):
                    # Cost-gated out before it is ever ranked, so an untradable name is not
                    # even part of the distribution the tradable ones are measured against.
                    raw.append(None)
                    continue
                raw.append(-float(value) if negate else float(value))
            standardized[name] = zscores(winsorize(raw))
    return standardized


def _reversal_tradable(row, config):
    liquidity = row.get("median_dollar_volume_60d")
    return _finite(liquidity) and liquidity >= config["reversal_minimum_dollar_volume"]


def _leg_values(row_index, standardized):
    """One z per leg: the mean of its resolved subfactor z-scores, or None if none resolved."""
    legs = {}
    for leg, subfactors in SWING_SUBFACTORS.items():
        present = [standardized[name][row_index] for name, _ in subfactors
                   if standardized[name][row_index] is not None]
        legs[leg] = sum(present) / len(present) if present else None
    return legs


def _gate_reasons(row, coverage, config):
    reasons = []
    if (row.get("price") or 0) < config["minimum_price"]:
        reasons.append("MINIMUM_PRICE")
    if (row.get("market_cap") or 0) < config["minimum_market_cap"]:
        reasons.append("MINIMUM_MARKET_CAP")
    if (row.get("median_dollar_volume_60d") or 0) < config["minimum_median_dollar_volume_60d"]:
        reasons.append("MINIMUM_LIQUIDITY")
    if (row.get("history_sessions") or 0) < config["minimum_history_sessions"]:
        reasons.append("INSUFFICIENT_HISTORY")
    if coverage < config["minimum_coverage"]:
        reasons.append("INSUFFICIENT_SIGNAL_COVERAGE")
    if row.get("stale_price"):
        reasons.append("STALE_PRICE")
    return reasons


def swing_scores(rows, current_members=None, config=None):
    """Score and rank the cross-section. One row in, one scored row out - nothing is dropped.

    Each leg is standardized across the universe, averaged into a composite over the weight
    that actually resolved, and ranked among eligible rows only. Suppressed (heavily shorted)
    and gated rows keep their score and their percentile stays None, so the file always says
    what it saw rather than quietly shortening.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    current_members = current_members or {}
    rows = list(rows)
    standardized = _standardized_subfactors(rows, config)
    total_weight = sum(SWING_WEIGHTS.values())

    output = []
    for index, row in enumerate(rows):
        legs = _leg_values(index, standardized)
        applied = {leg: value for leg, value in legs.items() if value is not None}
        applied_weight = sum(SWING_WEIGHTS[leg] for leg in applied)
        coverage = applied_weight / total_weight if total_weight else 0
        score = (sum(SWING_WEIGHTS[leg] * value for leg, value in applied.items()) / applied_weight
                 if applied_weight else 0.0)
        contributions = {leg: (SWING_WEIGHTS[leg] * value / applied_weight) if applied_weight else 0.0
                         for leg, value in applied.items()}
        short_interest = short_interest_flag(row, config)
        reasons = _gate_reasons(row, coverage, config)
        dropped = [leg for leg in SWING_WEIGHTS if leg not in applied]
        if "short_term_reversal" in dropped and not _reversal_tradable(row, config):
            reasons.append("REVERSAL_LEG_COST_GATED")
        if short_interest["suppressed"]:
            reasons.append("SHORT_INTEREST_SUPPRESSED")
        output.append({
            **row,
            "score": score,
            "leg_scores": legs,
            "leg_contributions": contributions,
            "dropped_legs": dropped,
            "coverage": round(coverage, 3),
            "short_interest": short_interest,
            "reversal_cost_gated": not _reversal_tradable(row, config),
            "eligibility": not reasons,
            "reason_codes": reasons,
            "percentile": None,
        })

    eligible = sorted((row for row in output if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = 100 * rank / max(1, len(eligible) - 1)

    # Same hysteresis the momentum screen uses: enter high, leave only once well below, so a
    # name does not flicker in and out of the list on a rounding difference day to day.
    entry, exit_ = config["entry_percentile"], config["exit_percentile"]
    for row in output:
        percentile = row.get("percentile")
        was_member = bool(current_members.get(row.get("ticker")))
        if percentile is None or not row["eligibility"]:
            row["current_membership"] = False
        elif was_member:
            row["current_membership"] = percentile >= exit_
        else:
            row["current_membership"] = percentile >= entry

    return sorted(output, key=lambda row: (row["eligibility"], row["score"]), reverse=True)


def leg_coverage(scored):
    """Share of rows each leg actually resolved on - the honest header for a thin leg.

    A composite whose highest-weighted leg is empty across the universe is not the same
    screen as one where it is full, and the page has to be able to say which it is looking at.
    """
    total = len(scored) or 1
    return {leg: round(sum(1 for row in scored if (row.get("leg_scores") or {}).get(leg) is not None) / total, 3)
            for leg in SWING_WEIGHTS}
