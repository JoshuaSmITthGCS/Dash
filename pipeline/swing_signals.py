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

Five rules this file exists to enforce.

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
   of eligibility with a reason code instead of contributing a factor. Because that result is
   about the *level* of short interest in the top decile, suppression requires the level -
   days-to-cover corroborates it and can never fire alone. Days to cover is short interest
   over average volume, so an absolute threshold on it fires on low-turnover names rather
   than heavily-shorted ones, and that is a liquidity screen wired in backwards.

4. **The 52-week-high leg is measured in the name's own volatility.** Raw price/52-week-high
   is mechanically higher for a quiet stock: a name at 22% annualized volatility is often
   within 2% of its high, one at 64% almost never is. Scored raw, the leg is half a momentum
   signal and half an inverse-volatility bet nobody declared, and it drags a sector tilt
   (REITs, utilities, staples) behind it. The scored subfactor is therefore the drawdown from
   the high expressed in annualized sigmas, which is George & Hwang's ranking with the
   volatility component divided out. Raw proximity stays published as context.

5. **A missing leg contributes nothing; it does not rescale the others.** Renormalizing to
   the weight that resolved keeps a partial row's score on the same 0-centred scale but gives
   it a *wider* one - fewer legs means less cancellation, so partial rows are over-represented
   in both tails, and it is the top tail that gets traded. This is the coverage-score coupling
   Round 4 measured at Spearman 0.554 on the research score and fixed with neutral imputation
   (scorer.py mode ``fixed_feature``). The same fix applies here: an unresolved leg scores 0,
   the cross-sectional mean of a z-score, and the weighted sum divides by the *declared* total.
   Less evidence therefore means a score nearer neutral, never a noisier one. The old
   renormalized value is published beside it as ``composite_z_renormalized`` so the change
   stays auditable against anything computed before it.

Nothing here fetches: every input is the committed advisor snapshot, the on-disk backtest
cache and the EDGAR point-in-time store, so the screen is re-derivable from the repository.
"""

from __future__ import annotations

import math
from statistics import NormalDist

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
    "pead_drift": (("standardized_unexpected_earnings", False),),
    "analyst_revision": (("revision_breadth_30d", False), ("eps_revision_30d_pct", False),
                         ("net_upgrades_90d", False), ("target_change_30d_pct", False)),
    "high_volume_premium": (("volume_ratio_1d_50d", False), ("volume_ratio_5d_50d", False)),
    # Rule 4: the drawdown from the high in the name's own sigmas, not raw proximity.
    "high_52w_proximity": (("high_52w_drawdown_sigmas", False),),
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
                  "SUE is the seasonal-random-walk-with-drift construct (Foster 1977; Foster, "
                  "Olsen & Shevlin 1984) computed from as-filed quarterly net income in the "
                  "EDGAR point-in-time store, standardized by the firm's own history of "
                  "seasonal differences. Drift windows are anchored on the SEC filing date, "
                  "which lags the earnings release by days and so understates window age.",
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
                  "recent-month return, which is what keeps it from cancelling the reversal leg. "
                  "Scored as the drawdown from the high in annualized sigmas rather than as raw "
                  "proximity: raw proximity correlates -0.49 with realized volatility across this "
                  "universe and would import an undeclared low-volatility and sector tilt.",
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
              "the short leg survives borrow fees at all; suppression sidesteps that question. "
              "The published result is about the top decile of short interest *level*, so "
              "suppression requires both an absolute floor on percent of float and top-decile "
              "standing in this cross-section. Days to cover is short interest over average "
              "volume and an absolute threshold on it fires on low-turnover names rather than "
              "heavily-shorted ones, so it corroborates and never suppresses alone.",
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

# Portfolio sizes the published cost block is evaluated at, and the round-trip cost that marks
# the point where the book stops fitting. The ceiling matches the figure the research score's
# capacity was quoted against in Round 5 (~$13M at 50bps/yr) so the two are comparable.
PORTFOLIO_SIZES_FOR_COSTS = (100_000, 1_000_000, 10_000_000, 50_000_000, 250_000_000,
                             1_000_000_000)
CAPACITY_COST_CEILING_BPS = 50.0

# Subfactors standardized by cross-sectional rank rather than by winsorized z-score.
#
# The seasonal-difference SUE is heavy-tailed by construction: it is a difference of earnings
# divided by the standard deviation of eight previous differences, so a firm with a quiet
# history and one loud quarter scores in the tens. Winsorizing that at the 5th and 95th
# percentiles and z-scoring puts every name above the 95th on one identical value - which,
# on a 30%-weight leg, hands the same head start to 5% of the universe and leaves the other
# legs to break the tie. Measured on this universe before the change: 12 of the top 15 rows
# sat on the cap.
#
# Ranking is also what the literature does. Bernard & Thomas form portfolios on SUE deciles
# and report drift monotone *in the rank*, not linear in the scaled surprise, so a
# rank-to-normal-score transform is closer to the published construct than the raw z is.
# Applied only here: the other subfactors are bounded ratios without this tail.
RANK_NORMALIZED_SUBFACTORS = {"standardized_unexpected_earnings"}

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
    # Negative screen. Rule 3: Boehmer-Jones-Zhang is a top-decile *level* result, so a row is
    # suppressed only when it clears the absolute floor AND stands in the top decile of this
    # cross-section. Days to cover is recorded and reported but cannot suppress on its own.
    "short_percent_of_float_limit": .10,
    "short_percent_of_float_percentile": 90,
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

    Published as context, not scored - see `high_52w_drawdown_sigmas` and rule 4.
    """
    series = [close for close in (closes or [])[-window:] if _finite(close) and close > 0]
    if len(series) < 60:
        return None
    peak = max(series)
    return series[-1] / peak if peak else None


def high_52w_drawdown_sigmas(closes, volatility, window=252):
    """Log drawdown from the 52-week high, divided by the name's annualized volatility.

    Rule 4. Raw proximity is not comparable across the cross-section, because how far a stock
    sits below its own high is mostly a statement about how much it moves: over this universe
    raw proximity correlates -0.49 with 60-day realized volatility, and median proximity falls
    monotonically from 0.94 in the quietest volatility quintile to 0.73 in the loudest. Ranking
    on it cross-sectionally therefore ranks partly on volatility, which is a different factor
    with its own literature and was never in the declared weights.

    Dividing the log drawdown by annualized volatility puts every name on the same scale -
    "how many annual sigmas below its 52-week high" - which is the ordering George & Hwang's
    ranking is trying to express. Zero is at the high; more negative is further below it, so
    higher is still better and the leg's sign is unchanged.
    """
    proximity = high_52w_proximity(closes, window)
    if proximity is None or not _finite(volatility) or volatility <= 0:
        return None
    return math.log(proximity) / volatility


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


def pead_factor(sue=None, config=None):
    """The SUE leg: standardized unexpected earnings, gated to an open drift window.

    `sue` is the dict edgar_sue.sue_for produces from the EDGAR point-in-time store - the
    standardized seasonal surprise plus the filing date that opened its drift window. It
    replaces the advisor snapshot's `earnings_surprise` field, which resolved on 0 of 839
    rows and which was in any case a four-quarter weighted average of *percent* surprise
    built for fundamental-momentum scoring, not the most-recent standardized surprise PEAD
    is a claim about. The two constructs are not interchangeable and are not blended.

    Returns (value, status). `status` is published per row so a dropped leg always says which
    reason applied - no SUE resolvable, the window has closed, or the announcement is undated
    and the surprise is being used anyway.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    value = (sue or {}).get("sue")
    if not _finite(value):
        return None, "NO_SUE_HISTORY"
    age = (sue or {}).get("age_trading_days")
    if not _finite(age):
        return float(value), "WINDOW_UNKNOWN"
    if age > config["pead_window_trading_days"]:
        return None, "DRIFT_WINDOW_CLOSED"
    return float(value), "IN_DRIFT_WINDOW"


def swing_factors(row, closes=None, volumes=None, config=None, sue=None):
    """Every raw subfactor for one row, before any cross-sectional ranking.

    Price and volume subfactors come from the cached daily series; revision subfactors come
    from the row's own published `estimate_detail`; the surprise comes from the EDGAR
    point-in-time store via `sue`. Anything unresolvable stays None, and the leg it belongs to
    scores 0 - the cross-sectional mean - rather than rescaling the legs that did resolve.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    estimates = row.get("estimate_detail") or {}
    surprise, pead_status = pead_factor(sue, config)
    volatility = realized_volatility(closes)
    return {
        "standardized_unexpected_earnings": surprise,
        "pead_status": pead_status,
        "pead_basis": (sue or {}).get("basis"),
        "pead_period_end": (sue or {}).get("period_end"),
        "pead_announced_on": (sue or {}).get("filed"),
        "pead_age_trading_days": (sue or {}).get("age_trading_days"),
        "revision_breadth_30d": estimates.get("revision_breadth_30d"),
        "eps_revision_30d_pct": estimates.get("eps_revision_30d_pct"),
        "net_upgrades_90d": estimates.get("net_upgrades_90d"),
        "target_change_30d_pct": estimates.get("target_change_30d_pct"),
        "volume_ratio_1d_50d": volume_surge(volumes, recent=1),
        "volume_ratio_5d_50d": volume_surge(volumes, recent=5),
        # The scored 52-week subfactor (rule 4); raw proximity rides along as context.
        "high_52w_drawdown_sigmas": high_52w_drawdown_sigmas(closes, volatility),
        "high_52w_proximity": high_52w_proximity(closes),
        "return_5d": trailing_return(closes, 5),
        # Normalization and cost input, never direction: see realized_volatility's docstring.
        "realized_volatility_60d": volatility,
        "return_20d": trailing_return(closes, 20),
    }


def short_interest_decile(rows, config=None):
    """The cross-sectional short-interest level that marks the top decile, or None.

    Boehmer-Jones-Zhang compare the most heavily shorted decile against the rest, so "heavily
    shorted" has to be read off the cross-section rather than fixed in advance. Returned
    separately so `short_interest_flag` stays a pure function of one row plus this threshold.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    levels = sorted(row.get("short_percent_of_float") for row in rows
                    if _finite(row.get("short_percent_of_float")))
    if not levels:
        return None
    index = int((len(levels) - 1) * config["short_percent_of_float_percentile"] / 100)
    return levels[index]


def short_interest_flag(row, config=None, decile_threshold=None):
    """Whether the negative screen fires on this row, and on what evidence.

    Rule 3. Suppression requires the *level* of short interest to clear both the absolute
    floor and the cross-sectional top decile, which is the population Boehmer-Jones-Zhang
    measure. Days to cover is short interest divided by average volume, so an absolute
    threshold on it selects low-turnover names rather than heavily-shorted ones: against this
    universe a 5.0-day line suppressed 20 names whose float short was 3-7%, a liquidity screen
    wired in backwards and pointed at exactly the quiet names the 52-week leg selects. It is
    now recorded as corroboration and can never suppress on its own.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    short_pct = row.get("short_percent_of_float")
    days = row.get("days_to_cover")
    floor = config["short_percent_of_float_limit"]
    level_hit = (_finite(short_pct) and short_pct >= floor
                 and (decile_threshold is None or short_pct >= decile_threshold))
    reasons, corroboration = [], []
    if level_hit:
        reasons.append(f"{short_pct * 100:.1f}% of float short")
        if _finite(days) and days >= config["days_to_cover_limit"]:
            reasons.append(f"{days:.1f} days to cover")
    elif _finite(days) and days >= config["days_to_cover_limit"]:
        corroboration.append(f"{days:.1f} days to cover, short interest below the suppression level")
    return {"suppressed": bool(reasons), "reasons": reasons,
            "corroborating_only": corroboration,
            "short_percent_of_float": short_pct if _finite(short_pct) else None,
            "days_to_cover": days if _finite(days) else None,
            "decile_threshold": decile_threshold}


def rank_normal_scores(values):
    """Cross-sectional rank mapped onto a standard normal, preserving None.

    For a heavy-tailed subfactor this is what winsorize-then-z is trying and failing to be:
    it is monotone in the raw value, ties nothing at a clip point, and lands on the same
    roughly-unit scale the z-scored subfactors use so the weights still mean what they say.
    """
    present = sorted((value, index) for index, value in enumerate(values) if value is not None)
    if not present:
        return [None] * len(values)
    if len(present) == 1:
        scores = [None] * len(values)
        scores[present[0][1]] = 0.0
        return scores
    normal = NormalDist()
    scores = [None] * len(values)
    for rank, (_value, index) in enumerate(present):
        scores[index] = normal.inv_cdf((rank + 0.5) / len(present))
    return scores


def _standardized_subfactors(rows, config):
    """{subfactor: [standardized value or None per row]}.

    Winsorized-then-z for the bounded subfactors, so one outlier cannot set the scale;
    rank-to-normal for the ones in RANK_NORMALIZED_SUBFACTORS, whose tails are heavy enough
    that clipping would tie a large block of the cross-section at one value.
    """
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
            standardized[name] = (rank_normal_scores(raw) if name in RANK_NORMALIZED_SUBFACTORS
                                  else zscores(winsorize(raw)))
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

    Each leg is standardized across the universe, combined at its declared weight with
    unresolved legs contributing zero (rule 5), and ranked among eligible rows only.
    Suppressed (heavily shorted) and gated rows keep their score and their percentile stays
    None, so the file always says what it saw rather than quietly shortening.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    current_members = current_members or {}
    rows = list(rows)
    standardized = _standardized_subfactors(rows, config)
    total_weight = sum(SWING_WEIGHTS.values())

    decile_threshold = short_interest_decile(rows, config)

    output = []
    for index, row in enumerate(rows):
        legs = _leg_values(index, standardized)
        applied = {leg: value for leg, value in legs.items() if value is not None}
        applied_weight = sum(SWING_WEIGHTS[leg] for leg in applied)
        coverage = applied_weight / total_weight if total_weight else 0
        # Rule 5: an unresolved leg contributes 0 - the cross-sectional mean of a z-score -
        # and the divisor is the *declared* total weight, not the resolved weight. A partial
        # row therefore lands nearer neutral instead of on a wider scale that would push it
        # into both tails. `composite_z_renormalized` keeps the old divisor for comparison.
        weighted = sum(SWING_WEIGHTS[leg] * value for leg, value in applied.items())
        score = weighted / total_weight if total_weight else 0.0
        renormalized = weighted / applied_weight if applied_weight else 0.0
        contributions = {leg: (SWING_WEIGHTS[leg] * value / total_weight) if total_weight else 0.0
                         for leg, value in applied.items()}
        short_interest = short_interest_flag(row, config, decile_threshold)
        reasons = _gate_reasons(row, coverage, config)
        dropped = [leg for leg in SWING_WEIGHTS if leg not in applied]
        if "short_term_reversal" in dropped and not _reversal_tradable(row, config):
            reasons.append("REVERSAL_LEG_COST_GATED")
        if short_interest["suppressed"]:
            reasons.append("SHORT_INTEREST_SUPPRESSED")
        output.append({
            **row,
            "score": score,
            "score_renormalized": renormalized,
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


def cost_profile(row, position_dollar_value, scenario="base"):
    """Round-trip cost in basis points for one position, from the shared cost model.

    One-way costs.estimate_cost_bps doubled: entering and leaving are both trades, and at a
    2-to-40-session horizon the round trip is the unit that matters. Volatility is the same
    60-day realized figure the 52-week leg normalizes by, so the cost model and the signal
    cannot silently disagree about how much a name moves.
    """
    from costs import estimate_cost_bps

    one_way = estimate_cost_bps(
        median_dollar_volume_60d=row.get("median_dollar_volume_60d"),
        annualized_volatility=(row.get("factors") or {}).get("realized_volatility_60d"),
        trade_dollar_value=position_dollar_value, scenario=scenario)
    return {**one_way, "round_trip_bps": round(one_way["total_bps"] * 2, 2),
            "position_dollar_value": position_dollar_value}


def capacity_profile(scored, config=None, portfolio_sizes=PORTFOLIO_SIZES_FOR_COSTS,
                     scenario="base"):
    """What the entry-percentile book costs to trade, and where it stops fitting.

    The screen ranks a cross-section but the thing that gets traded is the book above
    `entry_percentile`, held for somewhere inside a 2-to-40-session window. Published gross
    effect sizes with a McLean-Pontiff haircut beside them are still gross of *this*, and a
    2-to-40-session horizon turns over an order of magnitude faster than the monthly research
    score - so this block reports the median round-trip cost of that book at several portfolio
    sizes, and the size at which the median round trip passes CAPACITY_COST_CEILING_BPS.

    Turnover is the missing multiplier and is deliberately not invented here: annual drag is
    round-trip cost times the number of round trips a year, and that number is a measurement
    the prospective harness has to produce, not an assumption this file gets to make.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    book = [row for row in scored
            if row.get("eligibility") and (row.get("percentile") or 0) >= config["entry_percentile"]]
    if not book:
        return {"status": "no_book_at_entry_percentile"}

    def median_round_trip(portfolio_value):
        per_position = portfolio_value / len(book)
        costs = sorted(cost_profile(row, per_position, scenario)["round_trip_bps"] for row in book)
        return costs[len(costs) // 2]

    by_size = {f"{int(size):d}": {"portfolio_value": size,
                                  "position_dollar_value": round(size / len(book), 2),
                                  "median_round_trip_bps": median_round_trip(size)}
               for size in portfolio_sizes}
    capacity = next((size for size in portfolio_sizes
                     if median_round_trip(size) > CAPACITY_COST_CEILING_BPS), None)
    return {
        "book_size": len(book),
        "entry_percentile": config["entry_percentile"],
        "scenario": scenario,
        "by_portfolio_size": by_size,
        "cost_ceiling_bps": CAPACITY_COST_CEILING_BPS,
        "first_size_over_ceiling": capacity,
        "median_position_capacity_at_2pct_adv": _median_position_capacity(book),
        "note": ("Round-trip (two-way) cost per position at the canonical square-root impact "
                 "law, costs.py IMPACT_SCENARIOS['base']. Annual drag is this times the number "
                 "of round trips a year, which this screen has not yet measured - the 2-to-40 "
                 "session horizon implies materially more than the monthly research score's "
                 "24-50% turnover, and the prospective harness is what will pin it down."),
        "spread_source": "liquidity_tiered_proxy_not_measured",
    }


def _median_position_capacity(book):
    """Median largest position the 2%-of-ADV participation cap allows across the book."""
    from costs import max_trade_for_adv_participation

    sizes = sorted(value for value in
                   (max_trade_for_adv_participation(row.get("median_dollar_volume_60d"))
                    for row in book) if value)
    return sizes[len(sizes) // 2] if sizes else None


def leg_coverage(scored):
    """Share of rows each leg actually resolved on - the honest header for a thin leg.

    A composite whose highest-weighted leg is empty across the universe is not the same
    screen as one where it is full, and the page has to be able to say which it is looking at.
    """
    total = len(scored) or 1
    return {leg: round(sum(1 for row in scored if (row.get("leg_scores") or {}).get(leg) is not None) / total, 3)
            for leg in SWING_WEIGHTS}
