"""Three horizon-stratified swing books: 3-day, 2-week, 8-week.

The screen this replaces ran one composite across a 2-to-40-session window and produced one
ranked book. That is a design error, and it is the one this module exists to fix. A signal
that pays over 40 sessions and a signal that pays over 3 are not the same signal at different
strengths. They have different decay curves, different break-evens and different habitats, so
they get different books with their own legs, their own weights, their own liquidity floors
and their own cost budgets.

Three rules govern what may enter a tier.

1. **A leg enters a tier only if its documented payoff lands inside that tier's window.**
   Fraction-of-payoff captured, from the decay curves in research/HORIZON-STRATIFIED-REDESIGN.md
   section 2:

   | leg                 | 2-5 sessions | 6-15 sessions | 16-90 sessions |
   |---------------------|--------------|---------------|----------------|
   | announcement return | 100%         | 30%           | 100%           |
   | high volume premium | 20%          | 55%           | 100% (spent)   |
   | short-term reversal | 55-65%       | 95-100%       | then adverse   |
   | PEAD (SUE)          | 10-12%       | 25-30%        | 95%            |
   | 52-week high        | 5%           | 16%           | 95%            |
   | analyst revision    | 6-8%         | 12-15%        | 55%            |

   That table is why the fast book carries no 52-week leg and the slow book carries no volume
   leg. Neither has paid yet, or both have already paid, at the other's horizon.

   The slow column is quoted at a 65-session hold rather than the 40 this screen originally
   capped at. Capping at 40 forfeited roughly 35-40% of the PEAD payoff, most of it the
   25-30% Bernard & Thomas measure landing in the three days around the *next* announcement,
   which a 40-session hold sells before reaching.

2. **The fast book is event-triggered, not a cross-sectional rank.** TIER_F requires the
   announcement-return leg to resolve, so a name enters only when it has actually just
   reported. A 3-day book that ranks 820 names every day and replaces itself 84 times a year
   pays roughly 4200bps of annual cost at a 50bp round trip against published fast-horizon
   effects that are nowhere near that. Gating on the event is what makes the tier's turnover
   a function of how many names reported rather than of the calendar.

3. **Every row publishes what it costs against what the tier can expect to earn.** The three
   tiers differ far more in cost than in signal, so a ranked list without a cost column is a
   list of names sorted by something that may not survive being traded. `net_edge_bps` is that
   arithmetic per row, and it is a sort key on the page.

The expected-alpha figures the cost columns are measured against are **assumptions, not
measurements**, and they are published as such in every payload. See ALPHA_NOTE.
"""

import math

from swing_signals import (DEFAULT_CONFIG, SWING_EVIDENCE, SWING_SUBFACTORS, book_rows,
                           swing_scores)

# Sessions per month, for converting the monthly alpha assumption to a per-holding-period one.
SESSIONS_PER_MONTH = 21

# The one number every cost column is measured against, and the weakest link in the chain.
#
# Chen & Velikov (JFQA 2023) measure, across 204 anomalies and net of effective spreads,
# post-publication decay and the post-2000 trading era, an average anomaly netting 4bps/month,
# the strongest netting 10bps, and methods for *combining* anomalies netting around 20bps.
# Those are long-short figures. Working forward instead: a good multi-signal composite at
# 60bps/month long-short in sample, less the 58% McLean-Pontiff post-publication haircut, less
# the roughly 65% of a long-short spread a long-only book cannot reach, leaves 8.8bps/month
# gross. That is the number below.
#
# It is a convention built on two further conventions (the haircut choice and the long-only
# reachable fraction) and it is not measured on this universe. It is published rather than
# hidden because a cost column has to be measured against something, and an assumption stated
# in the payload is auditable in a way that one buried in a ratio is not.
ASSUMED_GROSS_ALPHA_BPS_PER_MONTH = 8.8

ALPHA_NOTE = (
    "Expected alpha is an assumption, not a measurement. 8.8bps/month gross is derived from a "
    "60bps/month long-short composite less the 58% McLean-Pontiff post-publication haircut "
    "less the ~65% of a long-short spread a long-only book cannot reach, and is consistent "
    "with Chen & Velikov (JFQA 2023) measuring anomaly combinations netting ~20bps/month "
    "long-short. Nothing in this pipeline has measured it. Every net_edge_bps and cost_ratio "
    "on this page inherits that assumption, so read them as a cost ranking with an alpha scale "
    "attached rather than as a forecast of what a name will earn.")

# Book value the per-position cost estimate is computed at. Round-trip cost is dominated by
# spread at small size and by impact at large size, so a cost column without a book size
# attached is meaningless: the same name costs ~3bps to round trip in a $1M book and ~14bps in
# a $50M one. $1M is the scale this system is actually run at.
DEFAULT_BOOK_DOLLARS = 1_000_000


TIER_SPECS = {
    "F": {
        "id": "swing-tier-F",
        "label": "3-day swing",
        "horizon_label": "2-5 sessions",
        "target_hold_sessions": 3,
        "session_band": (2, 5),
        "trigger": "earnings announcement in the last 5 sessions",
        # Only the legs with documented payoff inside 5 sessions. No 52-week leg (5% captured),
        # no PEAD leg (10-12%), no revision leg (6-8%) - none of them has paid yet.
        "weights": {
            "announcement_return": .50,
            "high_volume_premium": .30,
            "short_term_reversal": .20,
        },
        # Rule 2: the event gate. Without a resolved announcement return this is not a fast
        # book, it is a daily-rebalanced volume-and-reversal rank, which is the construction
        # the cost arithmetic rules out.
        "required_legs": ("announcement_return",),
        "config": {
            "announcement_window_max_age": 5,
            # The fast book cannot afford the small-cap end of the cost curve: a 66bp round
            # trip against a 3-session hold is unpayable at any plausible alpha. Same floor the
            # reversal leg already uses.
            "minimum_median_dollar_volume_60d": 25_000_000,
            "minimum_legs_resolved": 2,
            "entry_percentile": 95,
            "exit_percentile": 80,
        },
        "book_size_names": 25,
        "note": ("Event-triggered rather than a standing cross-sectional rank. A name enters "
                 "only in the days after it reports, so turnover follows the earnings calendar "
                 "rather than the trading calendar. This is the tier where cost most often "
                 "exceeds expected alpha: sort on net edge before reading the composite."),
    },
    "M": {
        "id": "swing-tier-M",
        "label": "2-week swing",
        "horizon_label": "6-15 sessions",
        "target_hold_sessions": 10,
        "session_band": (6, 15),
        "trigger": "cross-sectional rank, announcement window still open",
        # No 52-week leg. It captures 16% of its payoff over 15 sessions, below the 20% floor
        # rule 1 sets, so carrying it here would be paying turnover for a signal that has not
        # yet delivered. Its 15% went to the three legs that had, in proportion.
        "weights": {
            "high_volume_premium": .40,
            "announcement_return": .30,
            "pead_drift": .30,
        },
        "required_legs": (),
        "config": {
            "announcement_window_max_age": 15,
            "minimum_median_dollar_volume_60d": 10_000_000,
            "minimum_legs_resolved": 2,
            "entry_percentile": 92,
            "exit_percentile": 75,
        },
        "book_size_names": 50,
        "note": ("The high-volume premium's own window. It captures roughly 55% of its "
                 "documented payoff here against 20% in the fast book and nothing left in the "
                 "slow one, which is the whole reason this tier exists."),
    },
    "S": {
        "id": "swing-tier-S",
        "label": "13-week swing",
        "horizon_label": "16-90 sessions",
        # 65, not 40, and not an arbitrary "longer". A quarter is roughly 63 trading sessions,
        # and Bernard & Thomas measure 25-30% of the entire post-earnings drift landing in the
        # three-day window around the *next* announcement. A 40-session hold sells the position
        # before the single densest part of the payoff arrives. 65 sessions is the shortest
        # hold that clears that cluster, which captures it without paying for holding time that
        # buys nothing: every session past the next announcement is cost without drift.
        "target_hold_sessions": 65,
        "session_band": (16, 90),
        "trigger": "cross-sectional rank",
        "weights": {
            "pead_drift": .30,
            "announcement_return": .25,
            "high_52w_proximity": .25,
            "analyst_revision": .20,
        },
        "required_legs": (),
        "config": {
            "announcement_window_max_age": 60,
            "entry_percentile": 90,
            "exit_percentile": 75,
        },
        "book_size_names": 82,
        "note": ("The only tier whose cost budget is comfortable: under 4 round trips a year "
                 "against 84 in the fast book. The hold runs past the next earnings "
                 "announcement deliberately, because 25-30% of the post-earnings drift lands in "
                 "the three days around it and a 40-session hold sells before it arrives. The "
                 "volume leg is absent because its 20-session window has closed before this "
                 "book's hold is a third done."),
    },
}

TIER_ORDER = ("F", "M", "S")

# The announcement-return leg has no entry in SWING_EVIDENCE, which is keyed to the original
# five. Published in the same shape so the page renders it without special casing.
ANNOUNCEMENT_EVIDENCE = {
    "label": "Announcement return (EAR)",
    "horizon": "0 to +1 sessions, drift over the following quarter",
    "direction": "continuation of the announcement reaction",
    "citation": "Brandt, Kishore, Santa-Clara & Venkatachalam, "
                "'Earnings Announcements are Full of Surprises'",
    "effect": "A strategy sorted on the announcement-window return earns 7.55%/yr abnormal, "
              "roughly 1.3 points above the same strategy sorted on SUE, and unlike SUE it "
              "does not reverse after three quarters",
    "caveat": "Carried here for coverage as much as for effect size. It needs no analyst "
              "estimate and no XBRL line item, only daily bars and the 8-K Item 2.02 "
              "timestamp, so it resolves on names that fail every analyst-dependent leg. That "
              "is the part of the answer to a resolution floor that screens for size because "
              "two of the original five legs needed analyst data. It does not make small caps "
              "cheaper to trade, only scoreable.",
    "sign_convention": "a positive announcement reaction scores positive",
}


def tier_spec(tier):
    if tier not in TIER_SPECS:
        raise ValueError(f"unknown swing tier: {tier!r}. Tiers are {list(TIER_ORDER)}.")
    return TIER_SPECS[tier]


def tier_config(tier, config=None):
    """DEFAULT_CONFIG, then the tier's overrides, then the caller's."""
    return {**DEFAULT_CONFIG, **tier_spec(tier)["config"], **(config or {})}


def tier_subfactors(tier):
    """SWING_SUBFACTORS restricted to the tier's legs, plus the ones this module adds.

    The volume leg reads the abnormal-turnover construction rather than the raw ratio, for the
    reason in swing_signals.abnormal_turnover: a raw ratio ranks the quiet-baseline names to
    the top and imports a liquidity tilt nobody declared.
    """
    subfactors = dict(SWING_SUBFACTORS)
    subfactors["announcement_return"] = (("announcement_return", False),)
    subfactors["high_volume_premium"] = (("abnormal_turnover_1d", False),
                                         ("abnormal_turnover_5d", False))
    weights = tier_spec(tier)["weights"]
    return {leg: definition for leg, definition in subfactors.items() if leg in weights}


def round_trips_per_year(tier):
    """252 / holding period. A ceiling: it assumes the book replaces itself completely."""
    return 252 / tier_spec(tier)["target_hold_sessions"]


def expected_alpha_bps(tier, alpha_bps_per_month=ASSUMED_GROSS_ALPHA_BPS_PER_MONTH):
    """Assumed gross alpha over one holding period, in bps. See ALPHA_NOTE."""
    hold = tier_spec(tier)["target_hold_sessions"]
    return alpha_bps_per_month * hold / SESSIONS_PER_MONTH


def position_dollars(tier, book_dollars=DEFAULT_BOOK_DOLLARS):
    return book_dollars / tier_spec(tier)["book_size_names"]


UPSIDE_NOTE = (
    "Predicted upside adds three things and each is a different kind of number. First, how far "
    "this name has actually travelled over a window this long in the price history held, taken "
    "as the median of overlapping windows - that is the term that sets the scale, it is "
    "measured rather than assumed, and it includes whatever the market did over that period, so "
    "it is not alpha. Second, this row's share of the tier's assumed alpha, which is the "
    "model's opinion and is a convention rather than a measurement (see ALPHA_NOTE). Third, "
    "minus this row's own round-trip cost. "
    "Read the size of the number as coming almost entirely from the first term: the model's "
    "edge is a fraction of a percent against a typical move of several percent, so a large "
    "upside means this name usually moves a lot in this much time, not that the model is "
    "confident. Roughly 400 sessions of history is one particular market period and a rising "
    "one, so these medians are optimistic as a long-run base rate. Past travel is not a "
    "forecast, the windows overlap heavily, and this model has no out-of-sample record.")


def alpha_scale(scored, config, tier, alpha_bps_per_month=ASSUMED_GROSS_ALPHA_BPS_PER_MONTH):
    """Basis points of assumed alpha per unit of composite score.

    Calibrated so the *book's* mean row carries exactly the tier's assumed alpha, which keeps
    the per-row numbers anchored to the one figure this report is willing to defend rather than
    inventing a second assumption to sit beside it. Rows above the book mean get more and rows
    below get less, linearly, which is the standard alpha_i = a * z_i approximation.

    Returns None when the book has no positive mean score to calibrate against, and the caller
    falls back to the flat tier figure rather than dividing by something near zero.
    """
    book = book_rows(scored, config)
    scores = [row["score"] for row in book
              if isinstance(row.get("score"), (int, float)) and math.isfinite(row["score"])]
    mean = sum(scores) / len(scores) if scores else 0
    if mean <= 0:
        return None
    return expected_alpha_bps(tier, alpha_bps_per_month) / mean


def row_economics(row, tier, book_dollars=DEFAULT_BOOK_DOLLARS, scenario="base",
                  alpha_bps_per_month=ASSUMED_GROSS_ALPHA_BPS_PER_MONTH, alpha_bps=None):
    """What one round trip in this name costs, against what the tier implies it earns.

    The round trip is two one-way costs at the tier's own position size, from the same
    half-spread-plus-impact model the rest of the pipeline uses. The spread term inside it is a
    liquidity-tiered proxy rather than a measured effective spread, and that limitation is
    carried on the row as `spread_source` rather than left in a docstring.

    ``alpha_bps`` is this row's share of the tier's assumed alpha, from alpha_scale. Passed in
    rather than computed here because the calibration needs the whole book. Omitted, every row
    falls back to the flat tier figure, which is the right degradation for a caller holding one
    row and no cross-section, and `alpha_basis` says which of the two happened.

    `predicted_upside_pct` is the sort key that matters, and `net_edge_bps` is the same quantity
    in basis points. Negative means the round trip costs more than the tier implies this name
    earns over its whole holding period, which is a name to skip regardless of where it ranks.
    """
    from costs import estimate_cost_bps

    one_way = estimate_cost_bps(
        median_dollar_volume_60d=row.get("median_dollar_volume_60d"),
        annualized_volatility=(row.get("factors") or {}).get("realized_volatility_60d"),
        trade_dollar_value=position_dollars(tier, book_dollars),
        scenario=scenario)
    round_trip = round(one_way["total_bps"] * 2, 2)
    scaled = alpha_bps is not None and math.isfinite(alpha_bps)
    alpha = alpha_bps if scaled else expected_alpha_bps(tier, alpha_bps_per_month)
    net = alpha - round_trip

    # What this name has actually done over a window of this length. This is the term that
    # sets the scale of the published number, and it is the only measured one of the three.
    hold = tier_spec(tier)["target_hold_sessions"]
    travel = ((row.get("factors") or {}).get("forward_returns") or {}).get(str(hold))
    typical = travel.get("p50") if travel else None
    upside = (typical + net / 100) if typical is not None else net / 100

    return {
        "round_trip_bps": round_trip,
        "one_way_bps": one_way["total_bps"],
        "spread_source": one_way.get("spread_source"),
        "liquidity_tier": one_way.get("liquidity_tier"),
        "expected_alpha_bps": round(alpha, 2),
        "alpha_basis": "scaled_by_composite_score" if scaled else "tier_flat",
        "net_edge_bps": round(net, 2),
        # The measured half, published separately so the reader can see how much of the upside
        # is the name's own habit and how much is the model. It is almost all the first.
        "typical_move_pct": typical,
        "usual_low_pct": travel.get("p25") if travel else None,
        "usual_high_pct": travel.get("p75") if travel else None,
        "share_positive": travel.get("share_positive") if travel else None,
        "history_windows": travel.get("windows") if travel else None,
        "upside_basis": "historical_travel_plus_model_edge" if typical is not None
                        else "model_edge_only_no_price_history",
        "predicted_upside_pct": round(upside, 3),
        "cost_ratio": round(round_trip / alpha, 3) if alpha else None,
        "clears_cost": net > 0,
        "position_dollars": round(position_dollars(tier, book_dollars), 2),
        "book_dollars": book_dollars,
    }


def _required_legs_resolved(row, spec):
    legs = row.get("leg_scores") or {}
    return all(legs.get(leg) is not None for leg in spec["required_legs"])


def score_tier(rows, tier, current_members=None, config=None,
               book_dollars=DEFAULT_BOOK_DOLLARS,
               alpha_bps_per_month=ASSUMED_GROSS_ALPHA_BPS_PER_MONTH):
    """Score the cross-section under one tier's leg set, weights, gates and cost budget.

    Everything ranked is the same universe. What differs is which legs are eligible, what they
    weigh, how liquid a name has to be to qualify, and what one round trip costs against the
    holding period. Rows failing a tier's `required_legs` are marked ineligible with a reason
    code rather than dropped, so the fast book's event gate is visible on the page as a count
    rather than as an unexplained shortening of the list.
    """
    spec = tier_spec(tier)
    resolved = tier_config(tier, config)
    scored = swing_scores(rows, current_members=current_members, config=resolved,
                          weights=spec["weights"], subfactors=tier_subfactors(tier))
    for row in scored:
        row["tier"] = tier
        row["tier_id"] = spec["id"]
        if spec["required_legs"] and not _required_legs_resolved(row, spec):
            row["eligibility"] = False
            row["current_membership"] = False
            if "TIER_TRIGGER_UNRESOLVED" not in row["reason_codes"]:
                row["reason_codes"] = [*row["reason_codes"], "TIER_TRIGGER_UNRESOLVED"]
    # Ranking, the sector cap and membership were all settled before the trigger gate ran, so
    # every one of them was computed against a cross-section the surviving rows are no longer
    # part of. Redo the three in order.
    if spec["required_legs"]:
        _regate(scored, resolved)

    # Economics last, and deliberately so. The per-row alpha is calibrated against the book's
    # mean score, and on an event-gated tier the book is not settled until the trigger gate and
    # the re-cap above have run. Calibrating before them would anchor every predicted upside in
    # the fast book to a cross-section several times larger than the one it ends up in.
    scale = alpha_scale(scored, resolved, tier, alpha_bps_per_month)
    for row in scored:
        row["economics"] = row_economics(
            row, tier, book_dollars, alpha_bps_per_month=alpha_bps_per_month,
            alpha_bps=(scale * row["score"]) if scale is not None else None)
    return scored


def _regate(scored, config):
    """Re-rank, re-cap and re-mark membership after the trigger gate has removed rows.

    Order matters and it is the same order swing_scores uses: percentiles first because the
    cap reads them, the cap second because membership reads it, membership last. Skipping the
    cap step would leave the fast book carrying trims decided against a book several times
    larger, which removes the wrong names - the cap trims the lowest-scoring member of the
    crowded sector, and which name that is changes when the field changes.
    """
    from swing_signals import apply_sector_concentration_cap

    for row in scored:
        if not row["eligibility"]:
            row["percentile"] = None
    eligible = sorted((row for row in scored if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = 100 * rank / max(1, len(eligible) - 1)

    # apply_sector_concentration_cap accumulates onto the rows, so the previous pass's marks
    # have to come off before it runs again or the two passes' trims would compound.
    for row in scored:
        if row.get("sector_capped"):
            row["sector_capped"] = False
            row["sector_trim"] = None
            row["reason_codes"] = [code for code in row.get("reason_codes") or []
                                   if code != "SECTOR_CONCENTRATION_CAP"]
    apply_sector_concentration_cap(scored, config)

    entry = config["entry_percentile"]
    for row in scored:
        percentile = row.get("percentile")
        row["current_membership"] = bool(
            percentile is not None and row["eligibility"] and not row.get("sector_capped")
            and percentile >= entry)


def tier_summary(scored, tier, book_dollars=DEFAULT_BOOK_DOLLARS):
    """Per-tier economics of the book that would actually be held."""
    spec = tier_spec(tier)
    config = tier_config(tier)
    book = book_rows(scored, config)
    economics = [row["economics"] for row in book if row.get("economics")]
    costs = sorted(item["round_trip_bps"] for item in economics)
    median = costs[len(costs) // 2] if costs else None
    alpha = expected_alpha_bps(tier)
    trips = round_trips_per_year(tier)
    return {
        "tier": tier,
        "id": spec["id"],
        "label": spec["label"],
        "horizon_label": spec["horizon_label"],
        "target_hold_sessions": spec["target_hold_sessions"],
        "session_band": list(spec["session_band"]),
        "trigger": spec["trigger"],
        "note": spec["note"],
        "weights": spec["weights"],
        "required_legs": list(spec["required_legs"]),
        "entry_percentile": config["entry_percentile"],
        "exit_percentile": config["exit_percentile"],
        "minimum_median_dollar_volume_60d": config["minimum_median_dollar_volume_60d"],
        "minimum_legs_resolved": config["minimum_legs_resolved"],
        "book_size_names": spec["book_size_names"],
        "book_count": len(book),
        "book_dollars": book_dollars,
        "position_dollars": round(position_dollars(tier, book_dollars), 2),
        "round_trips_per_year": round(trips, 1),
        "median_round_trip_bps": median,
        "expected_alpha_bps_per_period": round(alpha, 2),
        "annual_cost_drag_bps": round(median * trips, 1) if median is not None else None,
        "break_even_alpha_bps_per_month": round(median * trips / 12, 2) if median is not None else None,
        "book_clearing_cost": sum(1 for item in economics if item["clears_cost"]),
        "median_net_edge_bps": (sorted(item["net_edge_bps"] for item in economics)[len(economics) // 2]
                                if economics else None),
        "eligible_count": sum(1 for row in scored if row["eligibility"]),
        "trigger_unresolved_count": sum(1 for row in scored
                                        if "TIER_TRIGGER_UNRESOLVED" in (row.get("reason_codes") or [])),
    }


def tier_evidence(tier):
    """The published evidence block for each of the tier's legs, plus its decay capture."""
    evidence = {**SWING_EVIDENCE, "announcement_return": ANNOUNCEMENT_EVIDENCE}
    return {leg: evidence[leg] for leg in tier_spec(tier)["weights"] if leg in evidence}


# Fraction of each leg's documented payoff that lands inside each tier's window. Sourced in
# research/HORIZON-STRATIFIED-REDESIGN.md section 2, which states per-cell provenance and
# marks which cells are interpolated from published endpoints rather than read off a published
# path. Published with the screen so a reader can see why a leg is absent from a tier.
# The S column is quoted at the 65-session hold. It was materially lower at 40, and the
# difference is the whole argument for the longer hold: PEAD goes from 62% to 95% because the
# next-announcement cluster lands around session 63, and the 52-week and revision legs are
# monthly accruals that simply have more months to accrue over.
DECAY_CAPTURE = {
    "announcement_return": {"F": 1.00, "M": 0.30, "S": 1.00},
    "high_volume_premium": {"F": 0.20, "M": 0.55, "S": 1.00},
    "short_term_reversal": {"F": 0.60, "M": 0.97, "S": None},
    "pead_drift": {"F": 0.11, "M": 0.27, "S": 0.95},
    "high_52w_proximity": {"F": 0.05, "M": 0.16, "S": 0.95},
    "analyst_revision": {"F": 0.07, "M": 0.13, "S": 0.55},
}

DECAY_CAPTURE_NOTE = (
    "Fraction of each leg's documented payoff landing inside each tier's holding window, from "
    "the cited decay curves. Several cells are interpolated from published endpoints rather "
    "than read off a published daily path, and none is measured on this universe. A null in "
    "the slow column means the leg's payoff is spent or reverses by that horizon. This table "
    "is why a leg is absent from a tier: below roughly 20% capture a leg is being paid for at "
    "a horizon where it has not yet delivered.")
