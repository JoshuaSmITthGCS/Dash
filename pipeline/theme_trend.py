"""Whether a structural trend is actually strengthening in the market, and whether it is
already priced.

Kept rigidly apart from ``themes.score_theme_exposure``, which answers a different question.
Exposure asks "does this company build any of this?" and is forbidden by design from reading
price: a thematic screen that scores exposure off price action becomes a momentum screen
wearing a thesis, which is the documented failure mode of specialized thematic products
(Ben-David, Franzoni, Kim & Moussawi, RFS 2023). This module reads price on purpose, but it
reads it *about the theme*, never about a company's exposure, and its output is published in
its own block that nothing in the exposure or research score consumes. ``validate_data``
enforces that separation rather than trusting it.

What it measures, and why each reading is here rather than a single number:

  * **Direction** - is the group beating the market, and is that lead widening? A theme can be
    real and going nowhere; a thesis is not an entry.
  * **Breadth** - how many members are above their own 20- and 50-day averages, and how many
    are outperforming at all. This is the difference between a trend and one stock.
  * **Leadership concentration** - if the largest member is carrying the whole reading, the
    "theme" is a company. Explicitly separated so a mega-cap cannot impersonate a group move.
  * **Fundamental confirmation** - estimate revisions and volume. Price alone cannot tell a
    re-rating from a bid; revisions say whether the operating picture moved too.
  * **Crowding** - the members' median valuation percentile. A strengthening theme that is
    already expensive is precisely the setup the research above says destroys returns, so it
    is reported next to the strength rather than buried.
  * **Role rotation** - the same readings per supply-chain role, which is what makes a
    rotation legible (utilities leading, then the transformer makers) instead of arriving as
    an undifferentiated sector move.

Every reading degrades to ``None`` when too few members resolve it, and every threshold below
is a stated convention rather than a fitted parameter - nothing here is optimized against
returns, because a number tuned on the same history it is judged against would be a backtest
result presented as a measurement.
"""

from statistics import median

# A group reading needs enough members to be a group. Below this the theme reports the count
# and no verdict: three names moving together is a coincidence with a name.
MINIMUM_MEMBERS = 5

# Breadth conventions. 60% of members above their own trend is "most of it participating";
# below 35% the move belongs to a minority of the group whatever the median says.
BROAD_PARTICIPATION = 0.60
NARROW_PARTICIPATION = 0.35

# A theme whose members sit in the most expensive third of their sectors is already carrying
# the expectation. Deliberately looser than the per-company exposure guardrail (top decile),
# because that one excludes a single name while this one only labels the group.
CROWDED_EXPENSIVENESS = 67

# How much of the group's outperformance the single largest member may explain before the
# reading is called concentrated rather than broad.
CONCENTRATION_GAP = 5.0

ROLES = ("root", "enabler", "supplier", "infrastructure", "service")


def _numbers(values):
    return [value for value in values if isinstance(value, (int, float))]


def _median(values):
    numbers = _numbers(values)
    return round(median(numbers), 2) if numbers else None


def _share(values, predicate):
    """Fraction of resolved readings satisfying a predicate, or None when none resolved."""
    numbers = _numbers(values)
    if not numbers:
        return None
    return round(sum(1 for value in numbers if predicate(value)) / len(numbers), 3)


def above_moving_average(closes, window):
    """Whether the latest close sits above its own ``window``-day simple average.

    Returns ``None`` rather than a guess when the series is too short - a 50-day average of
    30 closes is a different statistic wearing the same name.
    """
    series = _numbers(closes or [])
    if len(series) < window:
        return None
    return series[-1] >= sum(series[-window:]) / window


def member_reading(row):
    """One member's contribution to its theme's trend, read from fields already computed.

    Nothing is fetched here. The technical block is the same one the research score's own
    behavior layer uses, so a theme's trend and a company's momentum can never disagree about
    what the price did.
    """
    technical = row.get("technical_detail") or {}
    closes = (row.get("history") or {}).get("closes")
    expensiveness = row.get("valuation_expensiveness_percentile")
    if expensiveness is None and row.get("sector_valuation_percentile") is not None:
        expensiveness = 100 - row["sector_valuation_percentile"]
    return {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "role": row.get("role"),
        "market_cap": row.get("market_cap"),
        "theme_exposure_score": row.get("theme_exposure_score"),
        "relative_strength": technical.get("relative_strength"),
        "relative_strength_20d": technical.get("relative_strength_20d"),
        "relative_acceleration": technical.get("relative_acceleration"),
        "volume_ratio_60d": technical.get("volume_ratio_60d"),
        "above_20d": above_moving_average(closes, 20),
        "above_50d": above_moving_average(closes, 50),
        "revision_breadth_30d": row.get("revision_breadth_30d"),
        "eps_revision_30d_pct": row.get("eps_revision_30d_pct"),
        "expensiveness_percentile": expensiveness,
    }


def _flag_share(readings, key):
    """Share of members whose boolean reading is true, ignoring those that could not resolve."""
    resolved = [reading[key] for reading in readings if reading[key] is not None]
    if not resolved:
        return None
    return round(sum(1 for value in resolved if value) / len(resolved), 3)


def leadership(readings):
    """Whether the group's strength survives removing its largest member.

    The check the user of a theme screen actually needs: one mega-cap can carry a
    capitalization-weighted impression of a trend while the companies that would have to
    supply it go nowhere. Comparing the largest member against the median of everyone else
    turns "the theme is working" into a claim about the group or a claim about one company.
    """
    sized = [reading for reading in readings if isinstance(reading.get("market_cap"), (int, float))]
    if len(sized) < 2:
        return {"largest": None, "median_excluding_largest": None, "led_by_one_name": None}
    largest = max(sized, key=lambda reading: reading["market_cap"])
    rest = _median([reading["relative_strength"] for reading in readings
                    if reading is not largest])
    lead = largest.get("relative_strength")
    concentrated = None
    if isinstance(lead, (int, float)) and rest is not None:
        concentrated = lead - rest > CONCENTRATION_GAP and rest <= 0
    return {
        "largest": largest.get("ticker"),
        "largest_relative_strength": lead,
        "median_excluding_largest": rest,
        "led_by_one_name": concentrated,
    }


def role_rotation(readings):
    """Median strength per supply-chain role, strongest first.

    This is what makes a rotation visible before it shows up as a sector move: money arriving
    in the utilities and money arriving in the transformer makers are the same theme at two
    different stages, and only the role split distinguishes them.
    """
    buckets = {}
    for reading in readings:
        role = reading.get("role")
        if role:
            buckets.setdefault(role, []).append(reading)
    rows = [{
        "role": role,
        "members": len(items),
        "relative_strength_median": _median([item["relative_strength"] for item in items]),
        "above_50d_share": _flag_share(items, "above_50d"),
    } for role, items in buckets.items()]
    rows.sort(key=lambda row: (row["relative_strength_median"] is not None,
                               row["relative_strength_median"] or 0), reverse=True)
    return rows


def chain_confirmation(rotation):
    """Whether the supply chain confirms the headline, or only the obvious names moved.

    A defense thesis carried entirely by one prime is a company story; the same thesis with
    the subsystem and sensor suppliers moving too is a chain. Reported as an explicit boolean
    rather than folded into a score, because it is the single most useful thing to check
    before treating a theme as tradeable, and averaging it away would hide it.
    """
    by_role = {row["role"]: row for row in rotation}
    downstream = [by_role[role]["relative_strength_median"] for role in
                  ("supplier", "infrastructure", "enabler")
                  if role in by_role and by_role[role]["relative_strength_median"] is not None]
    root = (by_role.get("root") or {}).get("relative_strength_median")
    if root is None or not downstream:
        return {"root_relative_strength": root,
                "supply_chain_relative_strength": _median(downstream) if downstream else None,
                "confirms": None}
    supply = _median(downstream)
    return {"root_relative_strength": root, "supply_chain_relative_strength": supply,
            # Confirmation is about the chain participating, not about it winning: suppliers
            # holding their own while the root leads is a healthy chain.
            "confirms": supply > 0}


def _direction_label(strength, acceleration):
    if strength is None:
        return "unmeasured"
    if strength > 0 and (acceleration is None or acceleration >= 0):
        return "strengthening"
    if strength < 0 and (acceleration is None or acceleration <= 0):
        return "weakening"
    return "mixed"


def _breadth_label(participation):
    if participation is None:
        return "unmeasured"
    if participation >= BROAD_PARTICIPATION:
        return "broad"
    if participation <= NARROW_PARTICIPATION:
        return "narrow"
    return "mixed"


def verdict(direction, breadth, crowding, leadership_reading):
    """A label and the plain-language reason for it, from the readings above.

    Rule-based and deliberately unfitted. The ordering matters more than the wording: crowding
    is checked before strength is celebrated, so the one combination this screen exists to
    warn about - a real trend everybody has already paid for - can never be reported as a
    clean green light.
    """
    label, reasons = "mixed", []
    strengthening = direction["label"] == "strengthening"
    weakening = direction["label"] == "weakening"
    crowded = bool(crowding.get("already_priced"))
    # "Not broad" rather than "narrow": a median-based direction and a participation share are
    # two views of the same distribution, so a group can only be both strengthening and
    # outright narrow in the degenerate case. The distinction worth publishing is between an
    # advance most of the group shares and one carried by a minority of it - or by one name.
    narrow = breadth["label"] != "broad" or leadership_reading.get("led_by_one_name") is True

    if direction["label"] == "unmeasured":
        return {"label": "unmeasured", "summary": "Too little price history resolved to say."}
    if weakening:
        label = "cooling"
        reasons.append("the group is lagging the market and not recovering")
    elif strengthening and crowded:
        label = "strong but already priced"
        reasons.append("the group is outperforming, and its members already trade in the most "
                       "expensive third of their sectors - the setup thematic products have "
                       "historically bought at the wrong time")
    elif strengthening and narrow:
        label = "narrow leadership"
        reasons.append(
            f"the strength is concentrated in {leadership_reading.get('largest')}, with the "
            "rest of the group flat or lagging"
            if leadership_reading.get("led_by_one_name") else
            "the group is outperforming, but the advance is not shared by most of its members")
    elif strengthening:
        label = "broadening"
        reasons.append("the group is outperforming, most of its members are participating, "
                       "and it is not yet priced as an expensive third of the market")
    else:
        reasons.append("the group is neither clearly leading nor clearly lagging")

    if crowded and label not in ("strong but already priced",):
        reasons.append("members already trade expensively relative to their sectors")
    return {"label": label, "summary": ("; ".join(reasons) + ".").capitalize()}


def evaluate_theme(rows, *, minimum_members=MINIMUM_MEMBERS):
    """Turn a theme's scored members into a trend evaluation.

    ``rows`` are the theme's scored candidates carrying their research fields (technical
    block, revisions, valuation, market cap, and the role assigned by the theme config).
    Returns a block with ``contributes_to_exposure`` stamped false, which ``validate_data``
    checks, so the separation between "is this company exposed" and "is this trend moving" is
    a published fact rather than a convention someone has to remember.
    """
    readings = [member_reading(row) for row in rows or []]
    measured = [reading for reading in readings
                if reading["relative_strength"] is not None]
    if len(measured) < minimum_members:
        return {
            "contributes_to_exposure": False,
            "members_measured": len(measured),
            "minimum_members": minimum_members,
            "verdict": {"label": "unmeasured",
                        "summary": f"Only {len(measured)} members resolved price behavior; "
                                   f"{minimum_members} are needed before a group reading means "
                                   "anything."},
        }

    strength = _median([reading["relative_strength"] for reading in measured])
    acceleration = _median([reading["relative_acceleration"] for reading in measured])
    participation = _share([reading["relative_strength"] for reading in measured],
                           lambda value: value > 0)
    direction = {"relative_strength_median": strength,
                 "relative_strength_20d_median":
                     _median([reading["relative_strength_20d"] for reading in measured]),
                 "acceleration_median": acceleration,
                 "label": _direction_label(strength, acceleration)}
    breadth = {"above_20d_share": _flag_share(measured, "above_20d"),
               "above_50d_share": _flag_share(measured, "above_50d"),
               "outperforming_share": participation,
               "label": _breadth_label(participation)}
    expensiveness = _median([reading["expensiveness_percentile"] for reading in measured])
    crowding = {"expensiveness_percentile_median": expensiveness,
                "already_priced": None if expensiveness is None
                else expensiveness >= CROWDED_EXPENSIVENESS}
    confirmation = {
        "revision_breadth_median":
            _median([reading["revision_breadth_30d"] for reading in measured]),
        "positive_revision_share":
            _share([reading["eps_revision_30d_pct"] for reading in measured],
                   lambda value: value > 0),
        "volume_ratio_median": _median([reading["volume_ratio_60d"] for reading in measured]),
    }
    rotation = role_rotation(measured)
    leadership_reading = leadership(measured)
    return {
        "contributes_to_exposure": False,
        "members_measured": len(measured),
        "minimum_members": minimum_members,
        "direction": direction,
        "breadth": breadth,
        "leadership": leadership_reading,
        "fundamental_confirmation": confirmation,
        "crowding": crowding,
        "roles": rotation,
        "chain_confirmation": chain_confirmation(rotation),
        "verdict": verdict(direction, breadth, crowding, leadership_reading),
    }


def biggest_players(rows, limit=8):
    """The theme's largest members by market capitalization, with why they are in it.

    "Who are the biggest names here" is the first question anyone asks of a theme, and the
    exposure leaderboard cannot answer it: that one ranks by evidence and cheapness, so the
    companies most identified with a trend are frequently not at the top of it.
    """
    sized = [row for row in rows or []
             if isinstance(row.get("market_cap"), (int, float))]
    sized.sort(key=lambda row: row["market_cap"], reverse=True)
    return [{
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "role": row.get("role"),
        "market_cap": row.get("market_cap"),
        "theme_exposure_score": row.get("theme_exposure_score"),
        "eligible": row.get("eligible"),
        "relative_strength": (row.get("technical_detail") or {}).get("relative_strength"),
    } for row in sized[:limit]]
