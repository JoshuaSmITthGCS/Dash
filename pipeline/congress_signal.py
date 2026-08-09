"""Score Congressional stock purchases as a bounded, reward-only research modifier.

Explicit, deliberate exception to this codebase's stated "No political inputs" rule
(``advisor_engine.py``'s module docstring) - see that file for why the exception exists
and what it is scoped to. This module only ever rewards; it never penalizes a sale or
absence of buying, since a member not buying a stock carries none of the "how would they
know about this" information content a purchase might.

Two tiers, mirroring ``insider_signal.py``'s own breadth/freshness/cluster-bonus shape
rather than inventing a new one:

  * **Any disclosed purchase** is a mild positive - breadth (distinct representatives
    buying) times freshness (``insider_signal.decay``, reused as-is: the same
    one-to-three-month information-decay argument applies here). This is the "just any
    positive sign" floor.
  * **Extraordinary purchases** - flagged ``EXTRAORDINARY_BUY`` by
    ``build_congress_screen.classify``: a member's first-ever disclosed trade in a
    company small enough that owning it is not the obvious index-adjacent choice - earn
    an additional bonus that scales with how many such purchases show up, the same
    "breadth is what turns one person's position into a signal" logic the cluster bonus
    already uses for insiders. A single extraordinary buy is notable; several
    independent members making unusual small-cap picks in the same name within weeks of
    each other is a different, stronger claim.

There is a real evidentiary basis for scoring Congressional trading at all - Ziobrowski
et al. ("Abnormal Returns from the Common Stock Investments of the U.S. Senate", Journal
of Financial and Quantitative Analysis, 2004, and the 2011 House companion study) find
significant abnormal returns to disclosed Congressional purchases in samples predating
the STOCK Act's 2012 disclosure/trading-restriction regime. Whether that edge survives
in the post-STOCK-Act, mandatory-45-day-disclosure world this module actually reads is
untested by this codebase and should be treated skeptically rather than assumed.
"""

from datetime import date, datetime

from build_congress_screen import is_buy
from insider_signal import decay

DEFAULTS = {
    "max_points": 2.0,          # any-purchase floor
    "extraordinary_bonus": 2.0,  # additional cap for the EXTRAORDINARY_BUY tier
    "min_trade_value": 15000.0,  # FMP's own lowest disclosed range floor
}


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def buys_for_ticker(rows, ticker):
    """This ticker's disclosed purchases, from an already-classified congress screen."""
    return [row for row in rows
            if str(row.get("symbol") or "").upper() == ticker.upper()
            and is_buy(row.get("transaction_type"))]


def score_congressional_buying(rows, ticker, *, as_of=None, config=None):
    """A bounded, reward-only modifier from one ticker's disclosed Congressional buys.

    Returns ``(points, detail)`` with ``points >= 0``. ``rows`` is the already-classified
    congress screen's ``results`` list (each row carries ``flags`` from
    ``build_congress_screen.classify``), not raw trades - this module does not reclassify.
    """
    settings = {**DEFAULTS, **(config or {})}
    as_of_date = as_of or date.today()
    buys = buys_for_ticker(rows, ticker)
    material = [row for row in buys
               if (row.get("amount_lower") or 0) >= settings["min_trade_value"]]
    if not material:
        return 0.0, {"available": False, "reason": "no disclosed purchase above min_trade_value"}

    by_rep, extraordinary_reps, most_recent = {}, set(), None
    for row in material:
        rep = row.get("representative")
        when = _parse_date(row.get("disclosure_date") or row.get("transaction_date"))
        if not rep or when is None:
            continue
        by_rep.setdefault(rep, when)
        by_rep[rep] = max(by_rep[rep], when)
        if "EXTRAORDINARY_BUY" in (row.get("flags") or []):
            extraordinary_reps.add(rep)
        if most_recent is None or when > most_recent:
            most_recent = when

    if not by_rep:
        return 0.0, {"available": False, "reason": "no dated, attributable purchase"}

    days_since = (as_of_date - most_recent).days if most_recent else None
    freshness = decay(days_since)
    if freshness <= 0:
        return 0.0, {"available": True, "reason": "most recent purchase is stale",
                     "points": 0.0, "notes": []}

    breadth = min(1.0, 0.5 + 0.25 * (len(by_rep) - 1))
    base_points = settings["max_points"] * breadth * freshness

    extraordinary_points = 0.0
    if extraordinary_reps:
        extraordinary_breadth = min(1.0, 0.5 + 0.25 * (len(extraordinary_reps) - 1))
        extraordinary_points = settings["extraordinary_bonus"] * extraordinary_breadth * freshness

    total = round(base_points + extraordinary_points, 2)
    notes = [f"{len(by_rep)} member(s) disclosed a purchase, most recently {days_since} day(s) ago"]
    if extraordinary_reps:
        notes.append(f"{len(extraordinary_reps)} of those were a first-ever trade in a "
                     f"sub-$2B company (EXTRAORDINARY_BUY)")
    return total, {
        "available": True,
        "members_buying": len(by_rep),
        "extraordinary_members": len(extraordinary_reps),
        "days_since_latest": days_since,
        "points": total,
        "notes": notes,
        "method": "Breadth x freshness of disclosed purchases, with a breadth-scaled "
                  "bonus for first-ever trades in sub-$2B companies; reward-only",
    }
