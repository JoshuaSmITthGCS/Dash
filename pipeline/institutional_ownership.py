"""Classify institutional 13F accumulation/distribution: pure logic, fully testable
without the network.

Two consumers, deliberately different treatments of the same underlying computation.
``build_institutional_screen.py`` runs monthly, fetches the curated managers' filings
directly, and publishes the result as a factual, disclaimed screen - descriptive flags,
not points - the same way ``build_congress_screen.py`` handles STOCK Act disclosures.
``advisor_engine.py`` (via ``fetch_advisor.py``) reads *that already-published screen*,
not the network, and folds a lag-decayed version of the same magnitude into the research
score as a bounded modifier - see ``decay`` below and ``institutional_ownership_modifier``
in ``advisor_engine.py``.

The residual bias from restricting reads to publicly traded managers is not eliminated by
scoring it, only mitigated: this module and the screen both default to ``style: active``
managers only (excluding the largest passive indexers, whose position changes track index
membership and fund flows more than conviction, and excluding private-equity/alternative
managers, whose public 13F stakes are typically residual take-private holdings) - see
``pipeline/config/institutional_managers.json``. That mitigates, but does not remove, the
sampling bias; it is still not a random subset of institutional flow.

The structural problem 13F has that Form 4 does not: a Form 4 is filed by the *company*
being traded, so ``SecEdgarClient.recent_form4_filings(ticker)`` finds it directly. A 13F
is filed by the *investment manager*, and says nothing about which ticker to look under -
there is no per-company "who holds this" endpoint on EDGAR. Answering "did institutions
accumulate AAPL" therefore requires either (a) SEC's bulk quarterly Form 13F data sets,
covering every filer, or (b) a curated list of specific managers' own filings, which is
this module's approach - the same "curated beats a generic parser that quietly guesses
wrong" tradeoff ``theme_signals`` already makes for segment and customer-overlap maps.

The curated list (``pipeline/config/institutional_managers.json``) intentionally holds
only publicly traded asset managers, resolved through the same ``ticker_map()`` every
other CIK lookup in this codebase goes through - never a hand-typed CIK number, which
would fail silently wrong (attributing one manager's holdings to another) rather than
failing loudly. The honest cost of that choice: large influential 13F filers that are
privately held (Renaissance Technologies, Citadel Advisors, Bridgewater, ...) are not
reachable this way and are simply absent, not guessed at.

A 13F information table reports each manager's *shares held as of quarter-end*, not
trades, so "accumulation" here means the *breadth* of curated managers whose position in
one CUSIP grew quarter over quarter, mirroring how Form 4 scoring counts distinct
insiders rather than dollar totals - one manager's fund flows are noise, several managers
independently adding is a corroborated signal.
"""

from collections import defaultdict

# Position types that represent a fund's real economic stake. PUT/CALL rows in the same
# information table are option positions, not equity ownership, and mixing them into a
# share count would overstate or invert the position they're meant to hedge.
_EQUITY_PUT_CALL = {None, ""}

DEFAULTS = {
    "max_points": 3.0,
    "max_penalty": 2.0,
    "min_managers": 2,   # one curated manager moving is not corroboration
    "half_life_days": 45,   # matches the STOCK Act / 13F filing deadline, not a guess
    "max_age_days": 135,    # one quarter (90d) plus one filing deadline (45d): by then a
                            # fresher filing should exist, and this one is presumptively stale
}


def decay(days_since_filed, half_life=DEFAULTS["half_life_days"], max_age=DEFAULTS["max_age_days"]):
    """Exponential decay of a 13F position's scoring weight by filing lag.

    A 13F reports a position as of quarter-end but is not required to be filed until 45
    days later, so "current" is always already stale by construction - the only question
    is by how much. Fresh (just filed) scores near full weight; a filing sitting at the
    edge of ``max_age`` - roughly the point a fresher one should have landed - scores
    near zero rather than being read as still-current information.
    """
    if days_since_filed is None or days_since_filed < 0:
        return 0.0
    if days_since_filed > max_age:
        return 0.0
    return round(0.5 ** (days_since_filed / half_life), 4)


def parse_13f_info_table(xml_text, manager_id):
    """Every straight-equity holding in one manager's 13F information table.

    Namespace-agnostic on purpose - EDGAR's own 13F XML schema has changed prefixes
    across years, and the field names (``nameOfIssuer``, ``cusip``, ``sshPrnamt``) are
    what stays stable.
    """
    import xml.etree.ElementTree as ET

    def local(tag):
        return tag.rsplit("}", 1)[-1].lower()

    def text_of(node, name):
        found = next((child for child in node.iter() if local(child.tag) == name.lower()), None)
        return found.text.strip() if found is not None and found.text else None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    holdings = []
    for node in root.iter():
        if local(node.tag) != "infotable":
            continue
        put_call = text_of(node, "putCall")
        if put_call not in _EQUITY_PUT_CALL:
            continue
        cusip = text_of(node, "cusip")
        shares = text_of(node, "sshPrnamt")
        if not cusip or not shares:
            continue
        try:
            shares = float(shares)
        except ValueError:
            continue
        holdings.append({
            "manager_id": manager_id,
            "cusip": cusip.strip().upper(),
            "issuer": text_of(node, "nameOfIssuer"),
            "shares": shares,
            "value": float(text_of(node, "value") or 0) or None,
        })
    return holdings


def aggregate_by_cusip(holdings):
    """Every manager's position in each CUSIP, keyed by CUSIP."""
    by_cusip = defaultdict(dict)
    for holding in holdings:
        by_cusip[holding["cusip"]][holding["manager_id"]] = holding["shares"]
    return dict(by_cusip)


def holdings_change(current, prior):
    """Quarter-over-quarter breadth of curated managers adding vs. cutting one CUSIP.

    ``current``/``prior`` are ``{manager_id: shares}`` dicts for a single CUSIP, as
    produced by ``aggregate_by_cusip``. A manager absent from ``prior`` and present in
    ``current`` is a new position (counted as "added"); the reverse is an exit (counted
    as "dropped").
    """
    managers = set(current) | set(prior)
    added, dropped, unchanged = [], [], []
    for manager_id in managers:
        before = prior.get(manager_id, 0.0)
        after = current.get(manager_id, 0.0)
        if after > before * 1.05 or (before == 0 and after > 0):
            added.append(manager_id)
        elif after < before * 0.95 or (before > 0 and after == 0):
            dropped.append(manager_id)
        else:
            unchanged.append(manager_id)
    total_before = sum(prior.values())
    total_after = sum(current.values())
    return {
        "managers_added": sorted(added),
        "managers_dropped": sorted(dropped),
        "managers_unchanged": sorted(unchanged),
        "share_change_pct": round(total_after / total_before - 1, 4) if total_before else None,
        "total_shares_current": total_after,
        "total_shares_prior": total_before,
    }


def score_institutional_ownership(change, *, days_since_filed=None, config=None):
    """A bounded modifier from one CUSIP's quarter-over-quarter curated-manager breadth.

    Returns ``(points, detail)``. Positive when a plurality of curated managers with a
    position added to it this quarter; negative when a plurality cut. Requires
    ``min_managers`` net movers on the winning side before scoring anything, since one
    manager's flows are not corroboration.

    ``days_since_filed`` - age of the *current* quarter's filing, not the prior one being
    compared against - scales the result by ``decay``. Passing ``None`` skips the decay
    (full weight), which matters for the screen's own factual publish, where the flag
    should describe what happened regardless of how stale it now is; the score modifier
    always passes a real value.
    """
    settings = {**DEFAULTS, **(config or {})}
    if not change:
        return 0.0, {"available": False, "reason": "no curated manager held a position "
                                                     "in either quarter"}
    added, dropped = len(change["managers_added"]), len(change["managers_dropped"])
    net = added - dropped
    if abs(net) < settings["min_managers"]:
        return 0.0, {"available": True, "managers_added": added, "managers_dropped": dropped,
                     "points": 0.0, "notes": [],
                     "reason": "fewer than min_managers net movers; not corroborated"}
    freshness = (1.0 if days_since_filed is None else
                decay(days_since_filed, settings["half_life_days"], settings["max_age_days"]))
    if net > 0:
        cap = settings["max_points"]
        points = min(cap, cap * net / (added + dropped or 1) * 2) * freshness
        note = f"{added} curated institutional manager(s) added a position, {dropped} cut"
    else:
        cap = settings["max_penalty"]
        points = -min(cap, cap * -net / (added + dropped or 1) * 2) * freshness
        note = f"{dropped} curated institutional manager(s) cut their position, {added} added"
    if days_since_filed is not None:
        note += f", {days_since_filed}d since filed"
    if freshness <= 0:
        return 0.0, {"available": True, "managers_added": added, "managers_dropped": dropped,
                     "points": 0.0, "notes": [],
                     "reason": f"filing is {days_since_filed}d old, past max_age_days "
                              f"({settings['max_age_days']}d); presumptively stale"}
    return round(points, 2), {
        "available": True,
        "managers_added": added,
        "managers_dropped": dropped,
        "share_change_pct": change.get("share_change_pct"),
        "days_since_filed": days_since_filed,
        "freshness": freshness,
        "points": round(points, 2),
        "notes": [note],
        "method": "Breadth of curated public asset managers' quarter-over-quarter 13F "
                  "position change, decayed by filing lag; requires a net-mover plurality "
                  "to score",
    }
