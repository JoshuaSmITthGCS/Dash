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

5. **A missing leg rescales the legs that resolved, and a row too thin to rescale is
   excluded.** Spec amendment SA-2026-08-12-04, which reverses the previous rule.

   The previous rule scored an unresolved leg as 0 and divided by the *declared* total
   weight. That kept partial rows off a wider scale, but it bought that at a price nobody had
   declared: zero-filling pulls every thin row toward the cross-sectional mean, and thinness
   is not random. Coverage tracks size and liquidity, so muting thin rows mutes exactly the
   high-idiosyncratic-volatility, low-liquidity names where McLean & Pontiff (Journal of
   Finance 2016) measure post-publication decay to be worst. The screen was therefore running
   an undeclared size and liquidity tilt inside a rule that presented itself as conservative.

   The rule now: renormalize the declared weights across the legs that actually resolved for
   the row, so a resolved leg means what its weight says it means regardless of what else is
   missing. The wider-scale problem the old rule was written against is handled directly
   instead, by a floor: a row scoring on fewer than ``minimum_legs_resolved`` of the five legs
   is excluded from the ranked output entirely rather than scored near neutral and left in.
   Three of five is the default. ``coverage`` stays published and ``legs_resolved`` is
   published beside it as an explicit count, and the old zero-filled value rides along as
   ``composite_z_zero_filled`` so the change stays auditable in both directions.

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
                  "seasonal differences. Drift windows are anchored on the earnings release "
                  "datetime from Form 8-K Item 2.02, which is independent of the 10-Q filing "
                  "date; a period with no resolvable release datetime scores nothing on this "
                  "leg rather than falling back to the filing date.",
        "sign_convention": "a positive surprise scores positive",
        "expectation_model": "seasonal random walk with drift, drift estimated from the firm's "
                             "own history of seasonal differences",
        "announcement_anchor": "earnings_release_datetime_8k_item_202",
    },
    "analyst_revision": {
        "label": "Analyst revision (change, not level)",
        "horizon": "1 week to 6 months",
        "direction": "direction of the revision",
        "sign_convention": "rising consensus scores positive",
        "citation": "Jegadeesh, Kim, Krische & Lee, Journal of Finance 2004; "
                    "Womack, Journal of Finance 1996; Gleason & Lee, The Accounting Review 2003",
        "effect": "The quarterly change in consensus is a robust predictor orthogonal to a wide "
                  "range of other variables; new sells drift -9.1% over six months, new buys +2.4%",
        "caveat": "The asymmetry favours the short/avoid side, which a long-only book cannot "
                  "harvest. The *level* of consensus adds value only among favourable quant names.",
        # Spec amendment SA-2026-08-12-01. Published as machine-readable metadata rather than
        # prose, so no reader and no downstream artifact can quote this leg's weight as if the
        # full published spread were available to a long-only book.
        "warnings": [{
            "code": "LONG_ONLY_ASYMMETRY",
            "severity": "warning",
            "message": ("The published effect concentrates on the downgrade side. Womack "
                        "(Journal of Finance 1996) measures new sell recommendations drifting "
                        "-9.1% over six months against new buys at +2.4% over the same window. "
                        "A long-only book harvests the +2.4% side and cannot harvest the -9.1% "
                        "side, so roughly 79% of the published 11.5-point spread is "
                        "unreachable here. Read this leg's 0.25 weight as a declared prior over "
                        "the reachable side only, never as a claim on the full spread."),
            "citation": "Womack, Journal of Finance 1996",
            "capturable_side_effect_pct": 2.4,
            "unreachable_side_effect_pct": -9.1,
            "published_spread_pct": 11.5,
        }],
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
                         "where the paper alpha concentrates.",
                 # Every leg in this composite rests on a published result, so every leg takes
                 # the post-publication figure, not only the out-of-sample one. Enumerated
                 # rather than implied so a leg added later cannot quietly escape the haircut:
                 # pipeline/tests/test_swing_decay_constants.py asserts this covers SWING_WEIGHTS.
                 "applies_to_legs": ["pead_drift", "analyst_revision", "high_volume_premium",
                                     "high_52w_proximity", "short_term_reversal"],
                 "all_legs_are_published": True}

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
# `announcement_return` joins it for the same reason. An announcement-window return is one of
# the fattest-tailed quantities in equity data - a name can move 40% on a print while the
# median name moves under 2% - so winsorizing at the 5th and 95th percentiles would tie every
# genuinely large surprise at one value, which on the leg that exists precisely to rank
# surprises is the whole signal thrown away. Brandt et al sort into deciles and report drift
# monotone in the rank, so ranking is also the published construct.
RANK_NORMALIZED_SUBFACTORS = {"standardized_unexpected_earnings", "announcement_return"}

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
    # Spec amendment SA-2026-08-12-04. The hard floor that makes renormalization safe: a row
    # resolving fewer legs than this is excluded from the ranked output entirely rather than
    # renormalized onto a wider scale and left in the tails. A count, not a weight share,
    # because the failure mode is few legs rather than light legs.
    "minimum_legs_resolved": 3,
    # Spec amendment SA-2026-08-12-07. Share of the ranked book any one GICS sector may hold.
    # The composite is four-fifths continuation and continuation clusters, so without this the
    # book is a mega-cap technology and communication-services bet wearing a five-leg label.
    "sector_concentration_cap": .30,
    # Spec amendment SA-2026-08-12-06. Share of trailing 20-day ADV a single round trip may
    # take. A position needing more than this is rejected, not scored tradable at a price the
    # impact model was never calibrated to reach.
    "max_adv_participation": .05,
    "max_adv_participation_ceiling": .10,
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
    # The same gate for the announcement-return leg, kept as its own key because the tiers set
    # it differently: a 3-day book wants an announcement that fired this week, an 8-week book
    # wants the whole drift window. Default matches the SUE window so the two earnings legs
    # age together unless a tier deliberately separates them.
    "announcement_window_max_age": 60,
    "entry_percentile": 90,
    "exit_percentile": 75,
}


# ---------------------------------------------------------------------------
# Registered variants (spec amendment SA-2026-08-12-08)
# ---------------------------------------------------------------------------
#
# Raw weekly reversal is a liquidity-provision return earned overnight (Nagel, NBER w17653,
# 2012), while continuation over the same week is earned intraday and with the opposite sign
# (Lou, Polk & Skouras, Journal of Financial Economics 2019). Only the residual component
# survives in modern samples (Da, Liu & Schaumburg, Management Science 2014). The leg is also
# the only contrarian element in a composite that is otherwise four-fifths continuation.
#
# That is an argument for a measurement, not for a deletion. All three variants run forward
# from 2026-09-01 and none of them is chosen on historical data. Variant A is the frozen
# baseline and is not to be modified.
CONTINUATION_LEGS = ("pead_drift", "analyst_revision", "high_volume_premium",
                     "high_52w_proximity")


def _proportionally_redistributed(weights, dropped):
    """``weights`` without ``dropped``, its weight spread across the rest in proportion.

    Proportional rather than equal: the remaining weights are an evidence ordering, and
    spreading the freed weight equally would flatten that ordering as a side effect of
    removing an unrelated leg.
    """
    kept = {leg: weight for leg, weight in weights.items() if leg != dropped}
    total = sum(kept.values())
    return {leg: weight / total for leg, weight in kept.items()} if total else kept


SWING_VARIANTS = {
    "A": {
        "id": "swing-reversal-A",
        "label": "Frozen baseline: raw prior-week reversal at 10%",
        "weights": dict(SWING_WEIGHTS),
        "reversal_subfactor": ("return_5d", True),
        "is_frozen_baseline": True,
    },
    "B": {
        "id": "swing-reversal-B",
        "label": "Reversal leg removed, its 10% redistributed proportionally across the four "
                 "continuation legs",
        "weights": _proportionally_redistributed(SWING_WEIGHTS, "short_term_reversal"),
        "reversal_subfactor": None,
        "is_frozen_baseline": False,
    },
    "C": {
        "id": "swing-reversal-C",
        "label": "Reversal leg replaced with residualized reversal at the same 10%: prior-week "
                 "return orthogonalized against the industry return and the composite's other "
                 "four legs",
        "weights": dict(SWING_WEIGHTS),
        "reversal_subfactor": ("residual_return_5d", True),
        "is_frozen_baseline": False,
    },
}

BASELINE_VARIANT = "A"


def variant_spec(variant):
    if variant not in SWING_VARIANTS:
        raise ValueError(f"unregistered swing variant: {variant!r}. "
                         f"Registered variants are {sorted(SWING_VARIANTS)}.")
    return SWING_VARIANTS[variant]


def variant_weights(variant=BASELINE_VARIANT):
    return dict(variant_spec(variant)["weights"])


def variant_subfactors(variant=BASELINE_VARIANT):
    """SWING_SUBFACTORS as this variant defines them.

    Only the reversal leg differs across variants: A reads the raw prior-week return, B has no
    reversal leg at all, C reads the residualized one.
    """
    spec = variant_spec(variant)
    subfactors = {leg: definition for leg, definition in SWING_SUBFACTORS.items()
                  if leg in spec["weights"]}
    if spec["reversal_subfactor"] and "short_term_reversal" in subfactors:
        subfactors["short_term_reversal"] = (spec["reversal_subfactor"],)
    return subfactors


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


def trailing_dollar_volume(closes, volumes, window=20):
    """Mean daily dollar volume over the last ``window`` sessions - the ADV the cap reads.

    The participation cap is written against 20-day ADV specifically. The eligibility screens
    read a 60-day *median*, which is the right statistic for "is this name normally liquid"
    and the wrong one for "can this trade get done this week": a name whose volume has halved
    in the last month still looks liquid on a 60-day median, and that is exactly the name a
    participation cap exists to stop. Both are published, and neither is used for the other's
    job.
    """
    if not closes or not volumes or len(closes) != len(volumes):
        return None
    paired = [(close, volume) for close, volume in zip(closes[-window:], volumes[-window:])
              if _finite(close) and _finite(volume) and close > 0 and volume >= 0]
    if not paired:
        return None
    return sum(close * volume for close, volume in paired) / len(paired)


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
    reason applied - no SUE resolvable, no earnings release datetime to anchor the window on,
    or the window has closed.

    Spec amendment SA-2026-08-12-02: a row whose earnings release datetime does not resolve
    scores nothing on this leg. It is not carried on the 10-Q filing date, and it is not
    carried on an unknown window. Both of those were ways of trading a drift window whose age
    the model could not state, and the filing-date path understated that age systematically.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    value = (sue or {}).get("sue")
    if not _finite(value):
        return None, "NO_SUE_HISTORY"
    if not (sue or {}).get("release_datetime"):
        return None, "RELEASE_DATE_UNRESOLVED"
    age = (sue or {}).get("age_trading_days")
    if not _finite(age):
        return None, "WINDOW_UNKNOWN"
    if age > config["pead_window_trading_days"]:
        return None, "DRIFT_WINDOW_CLOSED"
    return float(value), "IN_DRIFT_WINDOW"


def universe_daily_returns(all_closes):
    """Equal-weighted universe daily return, indexed from the end: [0] is the latest session.

    The market leg of every abnormal-return construct in this file. Built from the same cached
    closes the factors are built from rather than from an index series, for two reasons. It
    needs no fetch and no new provider, which keeps the screen re-derivable from the
    repository, and it is the benchmark this book is actually measured against - an
    equal-weighted mean of the scored universe, not a cap-weighted index whose mega-cap
    concentration this book does not share.

    Rows are aligned from the *end* rather than the start. Every series in the cache is
    updated to the same latest session, so offset j is the same calendar session for every
    name, while start-alignment would compare a 300-session history against a 5000-session one
    at the same index.
    """
    series = [closes for closes in all_closes if closes and len(closes) > 1]
    if not series:
        return []
    horizon = min(len(closes) for closes in series) - 1
    returns = []
    for offset in range(horizon):
        moves = []
        for closes in series:
            later, earlier = closes[-1 - offset], closes[-2 - offset]
            if _finite(later) and _finite(earlier) and earlier > 0:
                moves.append(later / earlier - 1)
        returns.append(sum(moves) / len(moves) if moves else None)
    return returns


def announcement_return(closes, age_sessions, market_returns=None):
    """The [0,+1] abnormal return around the earnings announcement - the EAR surprise.

    Brandt, Kishore, Santa-Clara & Venkatachalam measure a strategy sorted on the
    announcement-window return earning 7.55%/yr, roughly 1.3 points above the same strategy
    sorted on SUE, and unlike SUE its drift does not reverse after three quarters. The reason
    to carry it here is coverage rather than effect size: it needs no analyst estimate and no
    XBRL line item, only the daily bars and the 8-K Item 2.02 timestamp this pipeline already
    stores, so it resolves on names that fail every analyst-dependent leg. The resolution
    floor screens for size largely because two of the five original legs need analyst data,
    and this leg is the part of the answer that does not require relaxing the floor.

    ``age_sessions`` is sessions elapsed since the release, from the same
    ``announcement_age_trading_days`` anchor the SUE leg is aged on, so a period with no
    resolvable release datetime scores nothing here either rather than falling back to the
    filing date.

    The window spans the close before the announcement to the close one session after it, so
    it needs at least one completed session after the release. An announcement that fired
    today has no measurable window yet and returns None rather than a half-formed one.
    """
    series = closes or []
    if not _finite(age_sessions):
        return None
    age = int(age_sessions)
    if age < 1 or len(series) < age + 3:
        return None
    start, end = series[-(age + 2)], series[-age]
    if not (_finite(start) and _finite(end) and start > 0):
        return None
    raw = end / start - 1
    if not market_returns:
        return raw * 100
    # The same two sessions on the universe: the one ending on the announcement day and the
    # one after it. Compounded rather than summed, so the abnormal return is a difference of
    # like-for-like holding-period returns.
    span = [market_returns[offset] for offset in (age, age - 1)
            if offset < len(market_returns) and market_returns[offset] is not None]
    if len(span) < 2:
        return raw * 100
    market = 1.0
    for move in span:
        market *= 1 + move
    return (raw - (market - 1)) * 100


def abnormal_turnover(volumes, recent=1, reference=50):
    """Volume shock in the name's own trailing sigmas, not as a raw ratio.

    The same correction rule 4 applies to the 52-week leg, applied to the volume leg. A raw
    ratio of recent to average volume is mechanically larger for a name whose baseline volume
    is low and stable, so ranking on it imports an undeclared liquidity tilt in exactly the
    way ranking on raw 52-week proximity imported an undeclared volatility tilt. Standardizing
    the log volume against its own trailing distribution divides that out and leaves the
    surprise, which is the quantity Gervais-Kaniel-Mingelgrin's investor-recognition mechanism
    is about.

    Published beside `volume_ratio_1d_50d` rather than replacing it, so the change stays
    auditable in both directions.
    """
    series = [volume for volume in (volumes or []) if _finite(volume) and volume > 0]
    if len(series) < reference + recent:
        return None
    window = series[-(reference + recent):-recent] if recent else series[-reference:]
    logs = [math.log(volume) for volume in window]
    if len(logs) < 2:
        return None
    mean = sum(logs) / len(logs)
    variance = sum((value - mean) ** 2 for value in logs) / (len(logs) - 1)
    deviation = math.sqrt(variance)
    # A relative floor, not `<= 0`. Fifty identical volumes give a variance of ~1e-30 rather
    # than exactly zero once the mean carries floating-point error, and dividing a comparably
    # tiny numerator by it returns a confident-looking z of ~1 for a name whose volume has not
    # moved at all. Log volumes are order 10, so 1e-9 is far below any real dispersion.
    if deviation < 1e-9:
        return None
    latest = series[-recent:]
    return (math.log(sum(latest) / len(latest)) - mean) / deviation


def swing_factors(row, closes=None, volumes=None, config=None, sue=None, market_returns=None):
    """Every raw subfactor for one row, before any cross-sectional ranking.

    Price and volume subfactors come from the cached daily series; revision subfactors come
    from the row's own published `estimate_detail`; the surprise comes from the EDGAR
    point-in-time store via `sue`. Anything unresolvable stays None, and the leg it belongs to
    scores 0 - the cross-sectional mean - rather than rescaling the legs that did resolve.

    ``market_returns`` is the equal-weighted universe daily return series from
    universe_daily_returns, needed only by the announcement-return leg. Omitted, that leg
    falls back to the raw window return and says so by scoring an unadjusted number, which is
    the right degradation for a caller that has one row and no cross-section.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    estimates = row.get("estimate_detail") or {}
    surprise, pead_status = pead_factor(sue, config)
    volatility = realized_volatility(closes)
    age = (sue or {}).get("age_trading_days")
    # Deliberately ungated here. The window this leg is allowed to look back over is a *tier*
    # decision, not a factor decision: the 3-day book wants an announcement from this week and
    # the 13-week book wants the whole drift window. Factors are built once per row and shared
    # across all three tiers, so gating at this point would silently apply one tier's window to
    # every tier. The gate lives in _standardized_subfactors, which runs per tier with that
    # tier's config. Raw factors stay raw.
    return {
        "announcement_return": announcement_return(closes, age, market_returns),
        "announcement_age_sessions": age if _finite(age) else None,
        "abnormal_turnover_1d": abnormal_turnover(volumes, recent=1),
        "abnormal_turnover_5d": abnormal_turnover(volumes, recent=5),
        "standardized_unexpected_earnings": surprise,
        "pead_status": pead_status,
        "pead_basis": (sue or {}).get("basis"),
        "pead_period_end": (sue or {}).get("period_end"),
        # The anchor the drift window is aged from: the earnings release, not the filing.
        "pead_announced_on": (sue or {}).get("release_date"),
        "pead_release_datetime": (sue or {}).get("release_datetime"),
        "pead_release_source": (sue or {}).get("release_source"),
        "pead_release_precision": (sue or {}).get("release_precision"),
        "pead_anchor_status": (sue or {}).get("anchor_status"),
        # The periodic filing date, kept as provenance only. It is never the anchor.
        "pead_filed": (sue or {}).get("filed"),
        "pead_expectation_model": (sue or {}).get("expectation_model"),
        "pead_drift_term": (sue or {}).get("drift"),
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


def _least_squares(design, targets, tolerance=1e-10):
    """OLS coefficients by Gauss-Jordan on the normal equations, or None if degenerate.

    Six regressors at most, so the normal equations are cheap and there is no reason to pull a
    linear-algebra dependency into the signal path. A near-zero pivot means a collinear column
    - every row in one sector, say, so the industry return is a constant - and the answer is
    None rather than an arbitrary solution, which the caller reads as "this leg does not
    resolve for this cross-section".
    """
    width = len(design[0])
    matrix = [[sum(row[i] * row[j] for row in design) for j in range(width)]
              + [sum(row[i] * target for row, target in zip(design, targets))]
              for i in range(width)]
    scale = max((abs(value) for line in matrix for value in line), default=0.0)
    if not scale:
        return None
    for column in range(width):
        pivot_row = max(range(column, width), key=lambda index: abs(matrix[index][column]))
        if abs(matrix[pivot_row][column]) < tolerance * scale:
            return None
        matrix[column], matrix[pivot_row] = matrix[pivot_row], matrix[column]
        pivot = matrix[column][column]
        matrix[column] = [value / pivot for value in matrix[column]]
        for index in range(width):
            if index == column:
                continue
            factor = matrix[index][column]
            if factor:
                matrix[index] = [value - factor * other
                                 for value, other in zip(matrix[index], matrix[column])]
    return [line[width] for line in matrix]


def _industry_returns(rows):
    """Mean prior-week return of each row's own sector, or None where the sector is unknown.

    The industry leg of the residualization. Sector rather than a factor-model industry
    because sector is what this universe carries point-in-time, and it is the same field the
    concentration cap reads, so the two controls cannot silently disagree about what an
    industry is.
    """
    groups = {}
    for row in rows:
        sector = row.get("sector")
        value = (row.get("factors") or {}).get("return_5d")
        if sector and _finite(value):
            groups.setdefault(sector, []).append(float(value))
    means = {sector: sum(values) / len(values) for sector, values in groups.items()}
    return [means.get(row.get("sector")) for row in rows]


def _continuation_leg_values(rows, standardized, subfactors_by_leg):
    """Per row, the four continuation leg z-scores as regressors, missing read as 0."""
    columns = []
    for index in range(len(rows)):
        row_values = []
        for leg in CONTINUATION_LEGS:
            present = [standardized[name][index] for name, _ in subfactors_by_leg.get(leg, ())
                       if standardized.get(name) and standardized[name][index] is not None]
            # A missing leg enters the regression at 0, the cross-sectional mean of a z-score.
            # That is the neutral regressor value, and it is a different decision from how a
            # missing leg is treated in the composite itself, where it is renormalized away.
            row_values.append(sum(present) / len(present) if present else 0.0)
        columns.append(row_values)
    return columns


def residual_reversal_values(rows, standardized, subfactors_by_leg):
    """Prior-week return orthogonalized against the industry return and the other four legs.

    Variant C. Da, Liu & Schaumburg (Management Science 2014) find that what survives of
    short-term reversal in modern samples is the residual after removing the component other
    signals already explain, not the raw weekly return. This is that construction: one
    cross-sectional OLS of the prior-week return on a constant, the row's own sector mean
    prior-week return, and the four continuation leg z-scores; the residual is what the leg
    scores.

    Returns a list aligned with ``rows``, None wherever the row was not in the regression.
    """
    industry = _industry_returns(rows)
    legs = _continuation_leg_values(rows, standardized, subfactors_by_leg)
    usable = [index for index, row in enumerate(rows)
              if _finite((row.get("factors") or {}).get("return_5d"))
              and industry[index] is not None]
    # Six coefficients need more than six observations before a residual means anything.
    if len(usable) < 2 * (2 + len(CONTINUATION_LEGS)):
        return [None] * len(rows)
    full = [[1.0, industry[index]] + legs[index] for index in usable]
    # Drop regressors that do not vary across the usable rows. A leg that resolved nowhere
    # enters as a column of zeros and a universe sitting in one sector makes the industry
    # return a constant; either one is collinear with the intercept and makes the normal
    # equations singular. Dropping them residualizes against the controls that carry
    # information rather than refusing to residualize at all.
    keep = [0] + [column for column in range(1, len(full[0]))
                  if len({round(row[column], 12) for row in full}) > 1]
    design = [[row[column] for column in keep] for row in full]
    targets = [float((rows[index].get("factors") or {})["return_5d"]) for index in usable]
    coefficients = _least_squares(design, targets)
    if coefficients is None:
        return [None] * len(rows)
    residuals = [None] * len(rows)
    for position, index in enumerate(usable):
        fitted = sum(value * coefficient
                     for value, coefficient in zip(design[position], coefficients))
        residuals[index] = targets[position] - fitted
    return residuals


def _standardize(name, raw):
    return (rank_normal_scores(raw) if name in RANK_NORMALIZED_SUBFACTORS
            else zscores(winsorize(raw)))


def _raw_column(rows, name, negate, config, *, cost_gate=False, values=None):
    raw = []
    for index, row in enumerate(rows):
        value = values[index] if values is not None else (row.get("factors") or {}).get(name)
        if not _finite(value):
            raw.append(None)
            continue
        if cost_gate and not _reversal_tradable(row, config):
            # Cost-gated out before it is ever ranked, so an untradable name is not even part
            # of the distribution the tradable ones are measured against.
            raw.append(None)
            continue
        raw.append(-float(value) if negate else float(value))
    return raw


def _announcement_window_gated(rows, config):
    """announcement_return, nulled on rows whose announcement is older than this tier allows.

    Applied here rather than in swing_factors because the factors are built once and scored
    three times. A 3-day book asking for an announcement from this week and a 13-week book
    asking for the whole drift window are reading the same stored number through different
    windows, and gating at factor time would apply whichever config built the row to all three.
    Ranked cross-sectionally afterwards, so a name gated out is not part of the distribution the
    names inside the window are measured against, which is the same treatment the cost-gated
    reversal leg gets.
    """
    limit = config["announcement_window_max_age"]
    values = []
    for row in rows:
        factors = row.get("factors") or {}
        age = factors.get("announcement_age_sessions")
        stale = _finite(age) and age > limit
        values.append(None if stale else factors.get("announcement_return"))
    return values


def _standardized_subfactors(rows, config, subfactors_by_leg=None):
    """{subfactor: [standardized value or None per row]}.

    Winsorized-then-z for the bounded subfactors, so one outlier cannot set the scale;
    rank-to-normal for the ones in RANK_NORMALIZED_SUBFACTORS, whose tails are heavy enough
    that clipping would tie a large block of the cross-section at one value.

    Two passes, because variant C's reversal subfactor is a residual against the other four
    legs and therefore cannot be standardized until they have been.
    """
    subfactors_by_leg = subfactors_by_leg or SWING_SUBFACTORS
    standardized = {}
    for leg, subfactors in subfactors_by_leg.items():
        if leg == "short_term_reversal":
            continue
        for name, negate in subfactors:
            values = (_announcement_window_gated(rows, config)
                      if name == "announcement_return" else None)
            standardized[name] = _standardize(
                name, _raw_column(rows, name, negate, config, values=values))

    reversal = subfactors_by_leg.get("short_term_reversal")
    if reversal:
        name, negate = reversal[0]
        values = (residual_reversal_values(rows, standardized, subfactors_by_leg)
                  if name == "residual_return_5d" else None)
        standardized[name] = _standardize(
            name, _raw_column(rows, name, negate, config, cost_gate=True, values=values))
    return standardized


def _reversal_tradable(row, config):
    liquidity = row.get("median_dollar_volume_60d")
    return _finite(liquidity) and liquidity >= config["reversal_minimum_dollar_volume"]


def _leg_values(row_index, standardized, subfactors_by_leg=None):
    """One z per leg: the mean of its resolved subfactor z-scores, or None if none resolved."""
    subfactors_by_leg = subfactors_by_leg or SWING_SUBFACTORS
    legs = {}
    for leg, subfactors in subfactors_by_leg.items():
        present = [standardized[name][row_index] for name, _ in subfactors
                   if standardized.get(name) and standardized[name][row_index] is not None]
        legs[leg] = sum(present) / len(present) if present else None
    return legs


def _gate_reasons(row, coverage, config, legs_resolved=None):
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
    if legs_resolved is not None and legs_resolved < config["minimum_legs_resolved"]:
        # Spec amendment SA-2026-08-12-04. Renormalization makes a two-leg row's score
        # comparable in centre but not in dispersion, so a row this thin is excluded from the
        # ranked output rather than renormalized and left to compete in the tails.
        reasons.append("INSUFFICIENT_LEGS_RESOLVED")
    if row.get("stale_price"):
        reasons.append("STALE_PRICE")
    return reasons


def swing_scores(rows, current_members=None, config=None, variant=BASELINE_VARIANT,
                 weights=None, subfactors=None):
    """Score and rank the cross-section. One row in, one scored row out - nothing is dropped.

    Each leg is standardized across the universe and combined at its declared weight,
    renormalized across the legs that actually resolved for the row (rule 5). Rows resolving
    fewer than ``minimum_legs_resolved`` legs are excluded from the ranked output by an
    eligibility reason rather than scored near neutral and left in. Suppressed (heavily
    shorted) and gated rows keep their score and their percentile stays None, so the file
    always says what it saw rather than quietly shortening.

    ``variant`` selects a registered weight and subfactor set - see SWING_VARIANTS. The
    default is the frozen baseline.

    ``weights`` and ``subfactors`` override the variant's, for callers that rank the same
    cross-section under a different leg set - the horizon tiers in swing_tiers.py are the
    only ones. They are parameters rather than new SWING_VARIANTS entries deliberately: the
    variant registry is what harness_freeze.json registers on the prospective clock, and a
    tier is a different book rather than a competing specification of the same one. Adding
    tiers there would inflate the registered search path by three for no measurement gain.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    current_members = current_members or {}
    rows = list(rows)
    spec = variant_spec(variant)
    weights = dict(weights) if weights else variant_weights(variant)
    subfactors_by_leg = ({leg: definition for leg, definition in subfactors.items()
                          if leg in weights} if subfactors else variant_subfactors(variant))
    standardized = _standardized_subfactors(rows, config, subfactors_by_leg)
    total_weight = sum(weights.values())
    leg_count = len(weights)

    decile_threshold = short_interest_decile(rows, config)

    output = []
    for index, row in enumerate(rows):
        legs = _leg_values(index, standardized, subfactors_by_leg)
        applied = {leg: value for leg, value in legs.items() if value is not None}
        applied_weight = sum(weights[leg] for leg in applied)
        coverage = applied_weight / total_weight if total_weight else 0
        legs_resolved = len(applied)
        # Rule 5, as amended: the divisor is the weight that *resolved*, so a leg that did
        # resolve carries the influence its declared weight promises no matter what else is
        # missing. The old zero-filled value rides along as `score_zero_filled` so the
        # amendment stays auditable in both directions.
        weighted = sum(weights[leg] * value for leg, value in applied.items())
        score = weighted / applied_weight if applied_weight else 0.0
        zero_filled = weighted / total_weight if total_weight else 0.0
        contributions = {leg: (weights[leg] * value / applied_weight) if applied_weight else 0.0
                         for leg, value in applied.items()}
        short_interest = short_interest_flag(row, config, decile_threshold)
        reasons = _gate_reasons(row, coverage, config, legs_resolved)
        dropped = [leg for leg in weights if leg not in applied]
        if "short_term_reversal" in weights and "short_term_reversal" in dropped \
                and not _reversal_tradable(row, config):
            reasons.append("REVERSAL_LEG_COST_GATED")
        if short_interest["suppressed"]:
            reasons.append("SHORT_INTEREST_SUPPRESSED")
        output.append({
            **row,
            "variant": variant,
            "variant_id": spec["id"],
            "score": score,
            "score_zero_filled": zero_filled,
            "leg_scores": legs,
            "leg_contributions": contributions,
            "dropped_legs": dropped,
            "coverage": round(coverage, 3),
            "legs_resolved": legs_resolved,
            "legs_declared": leg_count,
            "renormalization_factor": round(total_weight / applied_weight, 4) if applied_weight else None,
            "short_interest": short_interest,
            "reversal_cost_gated": not _reversal_tradable(row, config),
            "eligibility": not reasons,
            "reason_codes": reasons,
            "percentile": None,
        })

    eligible = sorted((row for row in output if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = 100 * rank / max(1, len(eligible) - 1)

    apply_sector_concentration_cap(output, config)

    # Same hysteresis the momentum screen uses: enter high, leave only once well below, so a
    # name does not flicker in and out of the list on a rounding difference day to day.
    entry, exit_ = config["entry_percentile"], config["exit_percentile"]
    for row in output:
        percentile = row.get("percentile")
        was_member = bool(current_members.get(row.get("ticker")))
        if percentile is None or not row["eligibility"] or row.get("sector_capped"):
            row["current_membership"] = False
        elif was_member:
            row["current_membership"] = percentile >= exit_
        else:
            row["current_membership"] = percentile >= entry

    return sorted(output, key=lambda row: (row["eligibility"], row["score"]), reverse=True)


def book_rows(scored, config=None):
    """The rows that would actually be held: eligible, above the entry percentile, uncapped."""
    config = {**DEFAULT_CONFIG, **(config or {})}
    return [row for row in scored
            if row.get("eligibility") and not row.get("sector_capped")
            and (row.get("percentile") or 0) >= config["entry_percentile"]]


def apply_sector_concentration_cap(scored, config=None):
    """Trim the ranked book until no GICS sector holds more than its capped share.

    Spec amendment SA-2026-08-12-07. Four of the five legs are continuation signals and
    continuation clusters by sector, so the top of this ranking concentrates in mega-cap
    technology and communication services. A cap declared as a constraint is a different thing
    from a sector bet arrived at by accident, and only the first can be reasoned about.

    Applied after ranking, never before: the ranking is the model's opinion and the cap is a
    portfolio constraint on top of it. The trim removes the *lowest-scoring* member of the
    over-represented sector, so the constraint costs the book its weakest expressions of the
    crowded view rather than reshuffling the ranking.

    Every trim is logged onto the row it removed and returned as a list. A sector is always
    allowed at least one name: on a book of three, a 30% cap is otherwise unsatisfiable and
    the loop would trim to nothing.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    cap = config["sector_concentration_cap"]
    for row in scored:
        row.setdefault("sector_capped", False)
    if not cap or cap >= 1:
        return []

    book = sorted((row for row in scored
                   if row.get("eligibility")
                   and (row.get("percentile") or 0) >= config["entry_percentile"]),
                  key=lambda row: row["score"], reverse=True)
    trims = []
    while book:
        counts = {}
        for row in book:
            counts[row.get("sector") or "UNCLASSIFIED"] = counts.get(row.get("sector") or "UNCLASSIFIED", 0) + 1
        allowed = max(1, int(cap * len(book)))
        over = {sector: count for sector, count in counts.items() if count > allowed}
        if not over:
            break
        sector = max(over, key=lambda name: (over[name], name))
        victim = min((row for row in book
                      if (row.get("sector") or "UNCLASSIFIED") == sector),
                     key=lambda row: row["score"])
        book.remove(victim)
        victim["sector_capped"] = True
        victim["reason_codes"] = list(victim.get("reason_codes") or []) + ["SECTOR_CONCENTRATION_CAP"]
        trim = {"ticker": victim.get("ticker"), "sector": sector,
                "score": round(victim["score"], 4),
                "percentile": round(victim["percentile"], 2) if victim.get("percentile") is not None else None,
                "sector_count_before": counts[sector], "book_size_before": len(book) + 1,
                "allowed_at_cap": allowed, "cap": cap}
        victim["sector_trim"] = trim
        trims.append(trim)
    return trims


def sector_cap_log(scored):
    """Every trim the sector cap made, read back off the rows it marked."""
    return [row["sector_trim"] for row in scored if row.get("sector_trim")]


def cost_profile(row, position_dollar_value, scenario="base", config=None):
    """Round-trip cost in basis points for one position, from the shared cost model.

    One-way costs.estimate_cost_bps doubled: entering and leaving are both trades, and at a
    2-to-40-session horizon the round trip is the unit that matters. Volatility is the same
    60-day realized figure the 52-week leg normalizes by, so the cost model and the signal
    cannot silently disagree about how much a name moves.

    ``position_dollar_value`` is the size of *one position*, never the size of the book. The
    two are not interchangeable and conflating them is what makes a capacity conclusion wrong
    by the number of names held. Both are labelled explicitly on the way out.

    Spec amendment SA-2026-08-12-06: the participation cap is evaluated here and a position
    that breaches it is returned with ``tradable`` false. It is not scored as a tradable
    position at a cost the impact model was never calibrated to reach.
    """
    from costs import estimate_cost_bps, participation_check

    config = {**DEFAULT_CONFIG, **(config or {})}
    adv_20d = row.get("adv_20d_dollar_volume")
    one_way = estimate_cost_bps(
        median_dollar_volume_60d=row.get("median_dollar_volume_60d"),
        annualized_volatility=(row.get("factors") or {}).get("realized_volatility_60d"),
        trade_dollar_value=position_dollar_value, scenario=scenario)
    participation = participation_check(
        trade_dollar_value=position_dollar_value,
        adv_20d_dollar_volume=adv_20d if adv_20d is not None else row.get("median_dollar_volume_60d"),
        max_participation=config["max_adv_participation"],
        ceiling=config["max_adv_participation_ceiling"],
        adv_source=("trailing_20d_mean_dollar_volume" if adv_20d is not None
                    else "median_dollar_volume_60d_fallback"))
    return {**one_way, "round_trip_bps": round(one_way["total_bps"] * 2, 2),
            "position_dollar_value": position_dollar_value,
            "participation": participation,
            "tradable": not participation["breaches_cap"]}


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
    book = book_rows(scored, config)
    if not book:
        return {"status": "no_book_at_entry_percentile"}

    def positions(book_dollar_value):
        """One cost profile per name, at the position size this book size implies.

        book_dollar_value is the whole book. position_dollar_value is book_dollar_value
        divided by the number of names held. Every label downstream says which of the two it
        is quoting, because the capacity conclusion is exactly the ratio between them.
        """
        per_position = book_dollar_value / len(book)
        return [cost_profile(row, per_position, scenario, config) for row in book]

    def summary(book_dollar_value):
        profiles = positions(book_dollar_value)
        costs = sorted(profile["round_trip_bps"] for profile in profiles)
        rejected = [profile for profile in profiles if not profile["tradable"]]
        return {
            "book_dollar_value": book_dollar_value,
            "position_dollar_value": round(book_dollar_value / len(book), 2),
            "positions_held": len(book),
            "median_position_round_trip_bps": costs[len(costs) // 2],
            "positions_rejected_on_participation_cap": len(rejected),
            "rejected_share": round(len(rejected) / len(book), 4),
        }

    by_size = {f"{int(size):d}": summary(size) for size in portfolio_sizes}
    capacity = next((size for size in portfolio_sizes
                     if by_size[f"{int(size):d}"]["median_position_round_trip_bps"]
                     > CAPACITY_COST_CEILING_BPS), None)
    first_rejection = next((size for size in portfolio_sizes
                            if by_size[f"{int(size):d}"]["positions_rejected_on_participation_cap"]),
                           None)
    return {
        "book_size": len(book),
        "entry_percentile": config["entry_percentile"],
        "scenario": scenario,
        "by_book_dollar_value": by_size,
        "cost_ceiling_bps": CAPACITY_COST_CEILING_BPS,
        "first_book_size_over_cost_ceiling": capacity,
        "first_book_size_rejecting_a_position_on_participation": first_rejection,
        "participation_cap": {
            "max_participation": config["max_adv_participation"],
            "hard_ceiling": config["max_adv_participation_ceiling"],
            "basis": "trailing 20-session mean dollar volume, per round trip",
        },
        "median_position_capacity_at_participation_cap":
            _median_position_capacity(book, config["max_adv_participation"]),
        "curve_consistency": cost_curve_consistency(book, portfolio_sizes, scenario),
        "size_labels": ("book_dollar_value is the whole book. position_dollar_value is one "
                        "position, book_dollar_value divided by positions_held. Costs and "
                        "participation are always per position, never per book."),
        "note": ("Round-trip (two-way) cost per position at the canonical square-root impact "
                 "law, costs.py IMPACT_SCENARIOS['base']. Annual drag is this times the number "
                 "of round trips a year, which this screen has not yet measured - the 2-to-40 "
                 "session horizon implies materially more than the monthly research score's "
                 "24-50% turnover, and the prospective harness is what will pin it down."),
        "spread_source": "liquidity_tiered_proxy_not_measured",
        "spread_caveat": ("The spread term is a liquidity-tiered proxy, not a measured quoted "
                          "spread and not an effective spread. No provider in this pipeline "
                          "serves either. Every cost figure here inherits that limitation."),
    }


def cost_curve_consistency(book, portfolio_sizes, scenario="base", tolerance=.02):
    """Whether every quoted round-trip point sits on one square-root impact curve.

    Spec amendment SA-2026-08-12-06. The impact term is proportional to the square root of
    participation, so quadrupling the position must double the impact component. Quoting a
    set of round-trip figures that do not satisfy that is quoting two different cost models
    under one heading, and the capacity conclusion then depends on which point a reader
    happens to take. This checks the published points against the law rather than trusting
    that one function produced them.

    Compares the impact component only. The half-spread term is a fixed per-name tier and
    does not scale with size, so including it would make a correct curve look wrong.
    """
    from costs import estimate_cost_bps

    if not book or len(portfolio_sizes) < 2:
        return {"status": "not_enough_points"}
    reference = book[len(book) // 2]
    volatility = (reference.get("factors") or {}).get("realized_volatility_60d")
    liquidity = reference.get("median_dollar_volume_60d")
    if not volatility or not liquidity:
        return {"status": "reference_name_missing_volatility_or_liquidity"}

    points, deviations = [], []
    base_size = portfolio_sizes[0] / len(book)
    base_impact = estimate_cost_bps(median_dollar_volume_60d=liquidity,
                                   annualized_volatility=volatility,
                                   trade_dollar_value=base_size, scenario=scenario)["impact_bps"]
    for size in portfolio_sizes:
        position = size / len(book)
        impact = estimate_cost_bps(median_dollar_volume_60d=liquidity,
                                   annualized_volatility=volatility,
                                   trade_dollar_value=position, scenario=scenario)["impact_bps"]
        expected = base_impact * math.sqrt(position / base_size) if base_impact else impact
        deviation = abs(impact - expected) / expected if expected else 0.0
        deviations.append(deviation)
        points.append({"book_dollar_value": size, "position_dollar_value": round(position, 2),
                       "impact_bps": impact, "square_root_law_impact_bps": round(expected, 2),
                       "relative_deviation": round(deviation, 4)})
    worst = max(deviations)
    return {
        "status": "consistent" if worst <= tolerance else "inconsistent",
        "law": "impact proportional to volatility times sqrt(participation)",
        "reference_ticker": reference.get("ticker"),
        "max_relative_deviation": round(worst, 4),
        "tolerance": tolerance,
        "points": points,
        "note": ("Participation saturates at 100% of ADV by construction in costs.py, so a "
                 "position larger than one day's volume leaves the curve. The participation "
                 "cap rejects those positions before they are quoted."),
    }


def _median_position_capacity(book, max_participation):
    """Median largest position the participation cap allows across the book."""
    from costs import max_trade_for_adv_participation

    sizes = sorted(value for value in
                   (max_trade_for_adv_participation(
                       row.get("adv_20d_dollar_volume") or row.get("median_dollar_volume_60d"),
                       max_participation)
                    for row in book) if value)
    return sizes[len(sizes) // 2] if sizes else None


def leg_coverage(scored, variant=BASELINE_VARIANT, weights=None):
    """Share of rows each leg actually resolved on - the honest header for a thin leg.

    A composite whose highest-weighted leg is empty across the universe is not the same
    screen as one where it is full, and the page has to be able to say which it is looking at.

    ``weights`` reports coverage over an arbitrary leg set rather than the variant's, for the
    horizon tiers, whose leg sets differ from the frozen five.
    """
    total = len(scored) or 1
    legs = weights or variant_weights(variant)
    return {leg: round(sum(1 for row in scored if (row.get("leg_scores") or {}).get(leg) is not None) / total, 3)
            for leg in legs}


# The PEAD leg's coverage under the superseded filing-date anchor, measured on this universe
# before spec amendment SA-2026-08-12-02. The re-anchoring cannot raise coverage, only lower
# it, so this is the reference the loss is quoted against rather than a target.
PEAD_COVERAGE_BEFORE_RELEASE_ANCHOR = .85


def pead_anchor_diagnostic(scored, reference_coverage=PEAD_COVERAGE_BEFORE_RELEASE_ANCHOR):
    """What re-anchoring the drift window on the earnings release cost in coverage.

    Spec amendment SA-2026-08-12-02 refuses to date a drift window from the 10-Q filing date.
    That is the correct anchor, and it is not free: every fiscal period with no Form 8-K Item
    2.02 in the point-in-time store now scores nothing on the highest-weighted leg. Trading
    fewer names on a correct window is a defensible choice and trading more names on a window
    that is systematically too young is not, but the size of the trade has to be stated rather
    than absorbed into a coverage number that quietly fell.
    """
    statuses = {}
    for row in scored:
        status = (row.get("factors") or {}).get("pead_status")
        if status:
            statuses[status] = statuses.get(status, 0) + 1
    total = len(scored) or 1
    with_surprise = total - statuses.get("NO_SUE_HISTORY", 0)
    unresolved = statuses.get("RELEASE_DATE_UNRESOLVED", 0)
    scored_now = statuses.get("IN_DRIFT_WINDOW", 0)
    coverage_now = round(scored_now / total, 4)
    delta = round(coverage_now - reference_coverage, 4)
    return {
        "anchor": "earnings_release_datetime_8k_item_202",
        "superseded_anchor": "sec_filing_date",
        "rows_scored": total,
        "rows_with_a_resolvable_surprise": with_surprise,
        "rows_without_a_release_datetime": unresolved,
        "rows_in_an_open_drift_window": scored_now,
        "pead_coverage_now": coverage_now,
        "pead_coverage_before_re_anchoring": reference_coverage,
        "coverage_delta": delta,
        "coverage_dropped_below_reference": coverage_now < reference_coverage,
        "note": ("A row without a release datetime is unresolved for this leg. It is never "
                 "carried on the 10-Q filing date. Where coverage_delta is negative, that is "
                 "the price of the correct anchor and it is quoted here rather than absorbed."),
        "remedy": ("Coverage rises by extending the Form 8-K Item 2.02 store, not by relaxing "
                   "the anchor: run pipeline/collect_earnings_releases.py."),
    }


def legs_resolved_distribution(scored, config=None):
    """How many rows resolved 0, 1, 2, ... legs, and how many the floor excluded.

    The counterpart to `leg_coverage`: coverage says which legs are thin, this says how thin
    the rows are. Renormalization is only defensible alongside a floor, and a floor is only
    reviewable if the number of rows it removes is published rather than inferred from a
    shrinking table.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    counts = {}
    for row in scored:
        resolved = row.get("legs_resolved")
        if resolved is None:
            continue
        counts[resolved] = counts.get(resolved, 0) + 1
    excluded = sum(1 for row in scored
                   if "INSUFFICIENT_LEGS_RESOLVED" in (row.get("reason_codes") or []))
    return {
        "minimum_legs_resolved": config["minimum_legs_resolved"],
        "rows_by_legs_resolved": {str(key): counts[key] for key in sorted(counts)},
        "rows_excluded_below_floor": excluded,
        "rows_scored": len(scored),
    }
