"""Pre-breakout composite: formulas, weights, gates and evidence. No I/O.

docs/PRE-BREAKOUT-SCREEN-RESEARCH.md is the design brief this implements: a composite of
three equal-weighted, evidence-ranked sub-scores rather than a pass/fail checklist gate
(Grinold-Kahn's Fundamental Law -- gating destroys breadth), validated prospectively rather
than backtested because point-in-time acceleration data has no prior history in this
codebase to backtest against. Registered on the prospective clock in
pipeline/validation/harness_freeze.json -- see build_pre_breakout_screen.py's payload().

The three sub-scores and what they are built from (Tier ranking per the research brief):

* ``fundamental_inflection`` -- earnings acceleration, revenue acceleration (both new,
  Tier A: He & Narayanamoorthy, JAE 2020), ROA turn and margin turn (Tier A/B: Novy-Marx,
  JFE 2013; Piotroski 2000), standardized unexpected earnings (Tier A: Foster 1977; Foster,
  Olsen & Shevlin 1984; Bernard & Thomas 1989/1990).
* ``momentum_rs`` -- 12-1 momentum and industry-relative momentum (Tier A/B: Jegadeesh &
  Titman 1993; Moskowitz & Grinblatt 1999), frog-in-the-pan path smoothness (Tier B: Da,
  Gurun & Warachka, RFS 2014), and a volatility-contraction/squeeze reading (Tier C -- the
  weakest-evidenced, most-foldable subfactor, weighted lowest inside this leg and the first
  candidate the prospective clock is expected to drop or reweight).
* ``flow_sentiment`` -- insider cluster buying (Tier A: Cohen, Malloy & Pomorski, JF 2012)
  and short-interest change (Tier B: Boehmer, Huszar & Jordan 2009).

Every raw subfactor here is oriented so that a higher value is more bullish before it is
standardized. Two of them need a deliberate transform to make that true and are called out
where they are computed: ``signed_path_smoothness`` (smoothness alone carries no direction --
see its docstring) and ``volatility_contraction_score``, which is left *unsigned* on purpose
(a squeeze is directionless by construction; it is scored as an additive setup-conviction
term, not a directional one -- see its docstring).

Dropping a leg or a subfactor later (the volatility-contraction reading is the one the
research brief itself flags as likely to go): delete its entry from
``PRE_BREAKOUT_SUBFACTORS``/the matching ``*_SUBWEIGHTS`` dict, renormalize the remaining
weights in that dict to sum to 1. Nothing else in this module or in
build_pre_breakout_screen.py needs to change -- every blend below already renormalizes over
whichever subfactors/legs actually resolved on a given row.
"""

from __future__ import annotations

import math

from build_quality_value_screen import DISTRESS_ALTMAN_Z, DISTRESS_INTEREST_COVERAGE, is_distressed
from research_screens_v2 import winsorize, zscores
from swing_signals import atr_compression, bandwidth_squeeze

# ---------------------------------------------------------------------------
# Composite structure
# ---------------------------------------------------------------------------

# Which subfactors roll into which of the 3 named legs, and whether the raw value is negated
# before standardizing (none are, today -- every raw factor below is already computed in
# "higher is more bullish" orientation; kept as (name, negate) tuples for the same reason
# swing_signals.SWING_SUBFACTORS is, so a future subfactor that needs negating is a one-word
# change here rather than a new code path).
PRE_BREAKOUT_SUBFACTORS = {
    "fundamental_inflection": (
        ("earnings_acceleration", False),
        ("revenue_acceleration", False),
        ("roa_delta", False),
        ("margin_turn", False),
        ("standardized_unexpected_earnings", False),
    ),
    "momentum_rs": (
        ("momentum_12_1", False),
        ("path_smoothness", False),
        ("industry_relative_momentum", False),
        ("volatility_contraction", False),
    ),
    "flow_sentiment": (
        ("insider_cluster_score", False),
        ("short_interest_change", False),
    ),
}

# Equal-weighted across the 3 named sub-scores, per the research brief -- a declared prior
# ordered by evidence quality, not a fitted optimum. validate_data.py's
# pre_breakout_screen_errors() checks no leg exceeds this by more than a rounding epsilon.
PRE_BREAKOUT_WEIGHTS = {
    "fundamental_inflection": 1 / 3,
    "momentum_rs": 1 / 3,
    "flow_sentiment": 1 / 3,
}

FUNDAMENTAL_INFLECTION_SUBWEIGHTS = {
    "earnings_acceleration": .30,
    "revenue_acceleration": .20,
    "roa_delta": .20,
    "margin_turn": .15,
    "standardized_unexpected_earnings": .15,
}

MOMENTUM_RS_SUBWEIGHTS = {
    "momentum_12_1": .40,
    "path_smoothness": .25,
    "industry_relative_momentum": .25,
    # Tier C, weakest evidence -- weighted lowest inside its own leg even before any decision
    # to drop it entirely once the prospective clock reports. See module docstring.
    "volatility_contraction": .10,
}

FLOW_SENTIMENT_SUBWEIGHTS = {
    "insider_cluster_score": .60,
    "short_interest_change": .40,
}

SUBWEIGHTS_BY_LEG = {
    "fundamental_inflection": FUNDAMENTAL_INFLECTION_SUBWEIGHTS,
    "momentum_rs": MOMENTUM_RS_SUBWEIGHTS,
    "flow_sentiment": FLOW_SENTIMENT_SUBWEIGHTS,
}

# ---------------------------------------------------------------------------
# Evidence, published alongside the score so a reader sees the citation and effect size
# behind each leg rather than a bare number. Mirrors swing_signals.SWING_EVIDENCE's shape.
# ---------------------------------------------------------------------------

PRE_BREAKOUT_EVIDENCE = {
    "fundamental_inflection": {
        "label": "Fundamental inflection (earnings/revenue acceleration, ROA/margin turn, SUE)",
        "horizon": "1-3 quarters",
        "direction": "continuation of the inflection",
        "citation": "He & Narayanamoorthy, Journal of Accounting and Economics 2020 (SSRN "
                    "3057632); Novy-Marx, Journal of Financial Economics 2013; Piotroski 2000; "
                    "Foster, Olsen & Shevlin, The Accounting Review 1984; Bernard & Thomas, "
                    "Journal of Accounting Research 1989 and Journal of Accounting and "
                    "Economics 1990",
        "effect": "Earnings acceleration: ~1.8% market-adjusted over 1 month, ~3.4% over a "
                  "quarter (top-minus-bottom decile). SUE/PEAD: ~4.2% over 60 trading days, "
                  "attenuated in modern samples (Martineau 2022 finds it near-zero outside "
                  "microcaps since ~2006).",
        "caveat": "Acceleration is a genuinely new construct in this codebase with zero prior "
                  "validation history here -- see harness_freeze.json's open_questions for "
                  "this model. Novy-Marx's evidence is for the *level* of profitability, not "
                  "specifically the *turn* used here for margin_turn/roa_delta.",
    },
    "momentum_rs": {
        "label": "Momentum / relative strength (12-1, path smoothness, industry-relative, "
                "volatility contraction)",
        "horizon": "1-6 months",
        "direction": "continuation",
        "citation": "Jegadeesh & Titman, Journal of Finance 1993; Moskowitz & Grinblatt, "
                    "Journal of Finance 1999; Da, Gurun & Warachka, Review of Financial "
                    "Studies 2014",
        "effect": "Classic 3-12 month momentum ~1%/month; industry momentum accounts for much "
                  "of individual-stock momentum; smooth ('continuous information') formation "
                  "paths earn materially more than choppy ones at the same cumulative return.",
        "caveat": "volatility_contraction (Bollinger/ATR squeeze) is Tier C: no peer-reviewed "
                  "base rate exists for squeeze-to-directional-breakout, the squeeze is "
                  "non-directional by construction, and published practitioner 'success "
                  "rates' are marketing with unstated methodology. Included as an unvalidated "
                  "hypothesis to test, weighted lowest in this leg -- see module docstring.",
    },
    "flow_sentiment": {
        "label": "Flow / sentiment (insider cluster buying, short-interest change)",
        "horizon": "1-3 months",
        "direction": "continuation",
        "citation": "Cohen, Malloy & Pomorski, Journal of Finance 2012; Kang, Kim & Wang 2018; "
                    "Boehmer, Huszar & Jordan 2009",
        "effect": "Opportunistic insider cluster buying: ~82bps/month value-weighted "
                  "(~9.8% annualized, t=2.15). Low/declining short interest in heavily-traded "
                  "names: significant positive abnormal returns.",
        "caveat": "Short-interest change is framed as removal of an informed-seller headwind, "
                  "not a squeeze thesis, which is a distinct and more speculative mechanism "
                  "not modeled here.",
    },
}

# ---------------------------------------------------------------------------
# Gates -- hard exclusions only (liquidity, price, history, solvency). Never gate on any of
# the composite signals themselves: gating on a signal destroys Grinold-Kahn breadth, which
# is exactly what the research brief says to avoid.
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    # Same numbers research_screens_v2.momentum_scores()/swing_signals.DEFAULT_CONFIG use.
    # Not an importable shared constant anywhere in this codebase today -- each screen
    # module declares its own copy of these four; this one does too, deliberately.
    "minimum_price": 5,
    "minimum_market_cap": 300_000_000,
    "minimum_median_dollar_volume_60d": 2_000_000,
    "minimum_history_sessions": 253,
    # A row resolving fewer than this many of the 3 named legs is excluded from the ranked
    # output entirely rather than renormalized onto a wider scale and left in the tails --
    # same rationale as swing_signals' minimum_legs_resolved (SA-2026-08-12-04), adapted to
    # a 3-leg rather than 5-leg composite.
    "minimum_legs_resolved": 2,
    "entry_percentile": 90,
    "exit_percentile": 75,
    # SUE/PEAD is a claim about a *recent* announcement (same reasoning as
    # swing_signals.DEFAULT_CONFIG's pead_window_trading_days). Past this many trading
    # sessions since the earnings release, the drift window has closed and
    # build_pre_breakout_screen.py drops the subfactor to None rather than scoring a stale
    # surprise as if it were fresh.
    "sue_window_trading_days": 60,
}


def _gate_reasons(row, legs_resolved, config):
    reasons = []
    if (row.get("price") or 0) < config["minimum_price"]:
        reasons.append("MINIMUM_PRICE")
    if (row.get("market_cap") or 0) < config["minimum_market_cap"]:
        reasons.append("MINIMUM_MARKET_CAP")
    if (row.get("median_dollar_volume_60d") or 0) < config["minimum_median_dollar_volume_60d"]:
        reasons.append("MINIMUM_LIQUIDITY")
    if (row.get("history_sessions") or 0) < config["minimum_history_sessions"]:
        reasons.append("INSUFFICIENT_HISTORY")
    if legs_resolved < config["minimum_legs_resolved"]:
        reasons.append("INSUFFICIENT_LEGS_RESOLVED")
    # Reused directly from build_quality_value_screen.py rather than a new threshold: the
    # research brief's "hard quality/solvency floors (e.g., not distressed by Altman Z)" is
    # exactly what that function already gates on (DISTRESS_ALTMAN_Z, DISTRESS_INTEREST_COVERAGE).
    if is_distressed(row.get("observed") or {}):
        reasons.append("DISTRESSED")
    if row.get("stale_price"):
        reasons.append("STALE_PRICE")
    return reasons


# ---------------------------------------------------------------------------
# Subfactor-level transforms that need more than a raw provider value
# ---------------------------------------------------------------------------

def signed_path_smoothness(smoothness, momentum_12_1):
    """Frog-in-the-pan path smoothness, signed by the direction of 12-1 momentum.

    ``research_screens_v2.momentum_path_smoothness`` on its own carries no direction -- it
    measures what fraction of formation-window days matched the sign of the window's own
    total return, so a smooth decline scores exactly as high as a smooth advance. Multiplying
    by the sign of the row's own 12-1 momentum turns it into what the composite actually
    needs: high and positive for a smooth uptrend, high and negative (a genuinely bearish
    reading) for a smooth downtrend, and near zero for a choppy path in either direction --
    the same relationship Da, Gurun & Warachka's information-discreteness measure carries to
    the formation-period return's sign.
    """
    if smoothness is None or momentum_12_1 is None:
        return None
    if momentum_12_1 > 0:
        return smoothness
    if momentum_12_1 < 0:
        return -smoothness
    return 0.0


def volatility_contraction_score(closes, highs=None, lows=None):
    """Continuous 0-1 "how squeezed" reading, from swing_signals' own percentile-of-own-
    history squeeze functions -- called directly rather than through
    swing_signals.contraction_setup, which bundles in rsi_2 (a directional mean-reversion
    read out of scope for this leg) and returns swing's own five-key descriptive shape rather
    than the one scored value this needs.

    1.0 sits at the tightest point in a name's own trailing history (maximally contracted);
    0.0 sits at its widest. Deliberately left *unsigned*: a squeeze says a move is coming, not
    which way (the research brief: "the squeeze is non-directional by construction"), so it
    is scored as an additive setup-conviction term on top of whatever direction the other,
    genuinely directional subfactors already carry -- never as its own bullish/bearish claim.

    Averages whichever of the close-based (Bollinger bandwidth) and range-based (ATR)
    readings resolve, so a name missing the separate, younger price_archive highs/lows series
    atr_compression needs still scores on bandwidth alone rather than losing the subfactor.
    """
    readings = []
    bandwidth = bandwidth_squeeze(closes)
    if bandwidth is not None:
        readings.append(1 - bandwidth["percentile_of_own_history"])
    if highs is not None and lows is not None:
        atr = atr_compression(highs, lows, closes)
        if atr is not None:
            readings.append(1 - atr["percentile_of_own_history"])
    return sum(readings) / len(readings) if readings else None


STAGE_THRESHOLDS = {
    # z-score cutoffs on the cross-sectionally standardized momentum_12_1 and
    # volatility_contraction subfactors already computed for the momentum_rs leg -- this is a
    # coarser read of two inputs that already exist, not a new signal or a fourth leg.
    "extended_momentum_z": 1.5,   # already run far -- a raging trend, not a setup
    "breakout_momentum_z": 0.25,  # meaningfully positive and rising, not yet extended
    "coiling_contraction_z": 0.5, # unusually tight versus the name's own trailing history
}


def classify_stage(momentum_z, contraction_z, thresholds=None):
    """Coarse stage read from two already-standardized subfactors -- not scored into the
    composite, published purely so a reader can tell "about to move" from "already moving",
    which the blended composite score alone cannot: a row can reach the same score via strong
    existing momentum, a tight squeeze with no move yet, or some mix of both, and nothing in
    the composite itself distinguishes which happened.

    - ``"extended"``: momentum_z at or above extended_momentum_z -- already run far.
    - ``"breaking_out"``: momentum_z between breakout_momentum_z and extended_momentum_z --
      meaningfully positive, not yet extended.
    - ``"coiling"``: momentum_z below breakout_momentum_z AND contraction_z at or above
      coiling_contraction_z -- flat-to-quiet price action, but unusually tight versus the
      name's own trailing volatility history. The literal "pre-breakout" case: hasn't moved
      yet, but coiled tighter than its own history.
    - ``"unclassified"``: momentum_z unresolved, or neither condition above is met (flat
      momentum with no meaningful squeeze either -- no stage signal either way).
    """
    thresholds = thresholds or STAGE_THRESHOLDS
    if momentum_z is None:
        return "unclassified"
    if momentum_z >= thresholds["extended_momentum_z"]:
        return "extended"
    if momentum_z >= thresholds["breakout_momentum_z"]:
        return "breaking_out"
    if contraction_z is not None and contraction_z >= thresholds["coiling_contraction_z"]:
        return "coiling"
    return "unclassified"


def short_interest_change(history, as_of, lookback_observations=6):
    """Percent decline off the trailing local high in short-interest-as-percent-of-float.

    Positive = short interest has come down off a recent high (Boehmer, Huszar & Jordan
    2009's "good news in short interest" framing: removal of an informed-seller headwind, not
    a squeeze thesis). ``history`` is the raw ``[{observed_at, value}]`` series
    pit_store.history() returns -- unfiltered by date -- so this filters to
    ``observed_at <= as_of`` itself rather than trusting the caller to have pre-filtered; that
    is the one easy-to-miss look-ahead trap in this module (pit_store.history(), unlike
    pit_store.as_of(), does no cutoff filtering of its own).
    """
    cutoff = str(as_of)[:10]
    observed = sorted(
        (row for row in (history or [])
         if row.get("observed_at") and str(row["observed_at"])[:10] <= cutoff
         and row.get("value") is not None),
        key=lambda row: row["observed_at"])
    if len(observed) < 2:
        return None
    window = [row["value"] for row in observed[-lookback_observations:]]
    recent_high, current = max(window[:-1]), window[-1]
    if not recent_high or not math.isfinite(recent_high):
        return None
    return (recent_high - current) / recent_high


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def _standardized_subfactors(rows, subfactors_by_leg=None):
    """{subfactor_name: [z-score or None per row]}, winsorized then z-scored across the rows.

    Reads each row's already-computed ``raw_factors`` dict -- this module does not fetch or
    derive anything itself, matching research_screens_v2.py's own "no provider or
    current-data look-ahead" contract. build_pre_breakout_screen.py is where the raw values
    (earnings_acceleration.acceleration_for, signed_path_smoothness,
    volatility_contraction_score, short_interest_change, etc.) actually get computed.
    """
    subfactors_by_leg = subfactors_by_leg or PRE_BREAKOUT_SUBFACTORS
    standardized = {}
    for subfactors in subfactors_by_leg.values():
        for name, negate in subfactors:
            raw = [(row.get("raw_factors") or {}).get(name) for row in rows]
            if negate:
                raw = [None if value is None else -value for value in raw]
            standardized[name] = zscores(winsorize(raw))
    return standardized


def _leg_score(index, standardized, subfactors, subweights):
    """One leg's score: the subweight-weighted mean of its resolved subfactor z-scores,
    renormalized across whichever subfactors actually resolved on this row -- the same
    renormalize-over-what-resolved rule swing_scores applies at the leg level, applied here
    one level further down, at the subfactor level.

    Returns (score, contributions, subfactors_resolved, coverage, renormalization_factor).
    ``score`` is None when nothing on this leg resolved for this row.
    """
    applied = {name: standardized[name][index] for name, _negate in subfactors
              if standardized.get(name) is not None and standardized[name][index] is not None}
    declared_weight = sum(subweights.values())
    if not applied or not declared_weight:
        return None, {}, 0, 0.0, None
    applied_weight = sum(subweights[name] for name in applied)
    score = sum(subweights[name] * value for name, value in applied.items()) / applied_weight
    contributions = {name: round(subweights[name] * value / applied_weight, 4)
                     for name, value in applied.items()}
    coverage = applied_weight / declared_weight
    renormalization_factor = round(declared_weight / applied_weight, 4) if applied_weight else None
    return score, contributions, len(applied), coverage, renormalization_factor


def _composite_from_legs(sub_scores, weights=None):
    """sum(value*weight)/sum(weight) over whichever legs resolved -- the same renormalizing
    weighted-average formula advisor_engine.blend_research_components implements for the
    champion score (``raw = sum(score_i*weight_i)/sum(weight_i)`` over available components;
    see that function's docstring). Reimplemented here at full precision rather than called
    directly, because blend_research_components rounds its raw_score to one decimal place --
    calibrated for the champion's 0-100 scale, far too coarse for a composite built from
    z-scores that typically span roughly -3 to 3 -- and its base_score/score default to
    clamping into [0, 100], which would floor every negative composite (more than half of any
    cross-sectional z-score blend) to zero. Same formula the champion composite uses, not the
    same function call.
    """
    weights = weights or PRE_BREAKOUT_WEIGHTS
    available = [(value, weights[key]) for key, value in sub_scores.items()
                if value is not None and key in weights]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return sum(value * weight for value, weight in available) / total_weight if total_weight else None


def _factor_z(standardized, name, index):
    """One subfactor's standardized value for one row, or None if the subfactor isn't
    declared at all (e.g. after volatility_contraction is dropped per the module's own
    "droppable leg" design -- classify_stage degrades to momentum-only staging rather than
    raising)."""
    values = standardized.get(name)
    return values[index] if values is not None else None


def _score_row(row, index, standardized, config):
    sub_scores, leg_detail = {}, {}
    for leg, subfactors in PRE_BREAKOUT_SUBFACTORS.items():
        score, contributions, resolved, coverage, renorm = _leg_score(
            index, standardized, subfactors, SUBWEIGHTS_BY_LEG[leg])
        sub_scores[leg] = score
        # Standardized (sign-adjusted) per-subfactor z, published alongside contributions so
        # validation/pre_breakout_ic.py can grade each subfactor's own predictive power and
        # marginal impact on the composite (composite_attribution.py) - contributions alone
        # are each subfactor's *share of the leg's score*, not the underlying value itself.
        subfactor_z = {name: round(standardized[name][index], 4) for name, _negate in subfactors
                       if standardized.get(name) is not None and standardized[name][index] is not None}
        leg_detail[leg] = {
            "z": None if score is None else round(score, 4),
            "weight": PRE_BREAKOUT_WEIGHTS[leg],
            "applied": score is not None,
            "subfactor_contributions": contributions,
            "subfactor_z": subfactor_z,
            "subfactors_resolved": resolved,
            "subfactors_declared": len(subfactors),
            "coverage": round(coverage, 3),
            "renormalization_factor": renorm,
        }

    composite = _composite_from_legs(sub_scores)
    legs_resolved = sum(1 for score in sub_scores.values() if score is not None)
    declared_leg_weight = sum(PRE_BREAKOUT_WEIGHTS.values())
    applied_leg_weight = sum(PRE_BREAKOUT_WEIGHTS[leg] for leg, score in sub_scores.items()
                             if score is not None)
    reasons = _gate_reasons(row, legs_resolved, config)
    stage = classify_stage(_factor_z(standardized, "momentum_12_1", index),
                           _factor_z(standardized, "volatility_contraction", index))

    return {
        **row,
        "score": composite,
        "sub_scores": leg_detail,
        "classification": stage,
        "legs_resolved": legs_resolved,
        "legs_declared": len(PRE_BREAKOUT_WEIGHTS),
        "coverage": round(applied_leg_weight / declared_leg_weight, 3) if declared_leg_weight else 0.0,
        "renormalization_factor": (round(declared_leg_weight / applied_leg_weight, 4)
                                   if applied_leg_weight else None),
        "eligibility": not reasons,
        "reason_codes": reasons,
        "percentile": None,
    }


def pre_breakout_scores(rows, current_members=None, config=None):
    """Score and rank the cross-section. One row in, one scored row out - nothing is dropped.

    Mirrors swing_signals.swing_scores' shape: standardize every subfactor across the
    cross-section, blend into 3 named legs and then into one composite (both renormalized
    over whatever resolved), gate, rank, apply entry/exit hysteresis. Gated and ineligible
    rows keep their score and reason codes and stay in the returned list rather than being
    dropped, so the caller can always account for the whole universe it was given.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    current_members = current_members or {}
    rows = list(rows)
    standardized = _standardized_subfactors(rows)
    output = [_score_row(row, index, standardized, config) for index, row in enumerate(rows)]

    eligible = sorted((row for row in output if row["eligibility"] and row["score"] is not None),
                      key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = 100 * rank / max(1, len(eligible) - 1)

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

    return sorted(output, key=lambda row: (row["eligibility"],
                                           row["score"] if row["score"] is not None else float("-inf")),
                 reverse=True)


# ---------------------------------------------------------------------------
# Publish-time summaries, mirroring swing_signals.leg_coverage/legs_resolved_distribution
# ---------------------------------------------------------------------------

def leg_coverage(scored, weights=None):
    """Share of rows each leg actually resolved on - the honest header for a thin leg."""
    total = len(scored) or 1
    legs = weights or PRE_BREAKOUT_WEIGHTS
    return {leg: round(sum(1 for row in scored
                           if ((row.get("sub_scores") or {}).get(leg) or {}).get("z") is not None)
                       / total, 3)
           for leg in legs}


def legs_resolved_distribution(scored, config=None):
    """How many rows resolved 0, 1, 2 or 3 legs, and how many the floor excluded."""
    config = {**DEFAULT_CONFIG, **(config or {})}
    distribution = {}
    for row in scored:
        count = row.get("legs_resolved") or 0
        distribution[count] = distribution.get(count, 0) + 1
    return {
        "by_legs_resolved": distribution,
        "minimum_legs_resolved": config["minimum_legs_resolved"],
        "excluded_by_floor": sum(count for legs, count in distribution.items()
                                 if legs < config["minimum_legs_resolved"]),
    }
