"""Score geographic revenue concentration on the same principle as customer concentration.

Companies routinely tag revenue by geography via ``us-gaap:Revenues`` (or one of the
ASC 606 contract-revenue variants) dimensioned on ``StatementGeographicalAxis``, with
member values drawn from the ``country`` XBRL scheme (``country:US``, ``country:CN``, ...)
or, less consistently, a company-specific regional extension member. Like customer
concentration, this is invisible to ``company_concept``/``companyfacts`` whenever a filer
tags only the geographic split and no undimensioned consolidated total in the same
context - which is common, since the consolidated total is usually tagged separately
anyway, but there is no guarantee of that, and no way to tell from the aggregator's
response whether a missing value means "not tagged" or "tagged, but dimensioned."

The risk claim here is deliberately narrow and mirrors ``concentration_risk.py``: heavy
revenue *concentration in a single non-domestic geography* is a diversifiable,
uncompensated risk (a single country's regulatory, currency, or demand shock moves an
outsized share of revenue), not a bet on whether international revenue in general is good
or bad. A globally diversified company with no single foreign country above the threshold
scores no penalty here even if the bulk of its revenue is non-domestic - the modifier
penalizes concentration, not exposure.
"""

from xbrl_dimensions import dimensional_facts, facts_on_axis, undimensioned_facts

REVENUE_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax")
GEOGRAPHIC_AXIS = "StatementGeographicalAxis"
# Local names (post `country:` prefix strip, lowercased) treated as the filer's home
# market. Extend deliberately, not permissively - an unrecognized member is treated as
# "cannot classify" and abstained on, per the module's own governing principle below.
DOMESTIC_MEMBERS = {"us", "unitedstates", "unitedstatesofamerica"}

DEFAULTS = {
    "warning_share": 0.30,
    "severe_share": 0.50,
    "max_penalty": 2.0,
}


def geographic_revenue_shares(document_text):
    """Each disclosed geography's share of total revenue, or ``{}`` if it can't be told.

    Requires *both* an undimensioned total and at least one geographic band in the same
    filing's tagging of the same concept - matching only one of the two is exactly the
    "looks untagged but isn't, or looks total but is one segment" trap this module exists
    to avoid, so it abstains rather than guess which shape it is looking at.
    """
    for concept in REVENUE_CONCEPTS:
        facts = dimensional_facts(document_text, concept)
        total_facts = undimensioned_facts(facts)
        by_geography = facts_on_axis(facts, GEOGRAPHIC_AXIS)
        if not total_facts or not by_geography:
            continue
        total = total_facts[0]["value"]
        if not total:
            continue
        return {member: round(values[0]["value"] / total, 4)
                for member, values in by_geography.items()}
    return {}


def score_geographic_concentration(shares, config=None):
    """A bounded, penalty-only modifier from one filing's geographic revenue split.

    Returns ``(points, detail)`` with ``points <= 0``, scored on the largest single
    non-domestic geography's share of total revenue.
    """
    settings = {**DEFAULTS, **(config or {})}
    if not shares:
        return 0.0, {"available": False, "reason": "no geographic revenue split resolved",
                     "shares": {}}
    foreign = {member: share for member, share in shares.items()
               if member not in DOMESTIC_MEMBERS}
    if not foreign:
        return 0.0, {"available": True, "shares": shares, "points": 0.0, "notes": [],
                     "reason": "no material non-domestic geography disclosed"}
    member, share = max(foreign.items(), key=lambda pair: pair[1])
    cap = settings["max_penalty"]
    if share >= settings["severe_share"]:
        points = -cap
    elif share >= settings["warning_share"]:
        points = -round(cap / 2, 2)
    else:
        points = 0.0
    notes = []
    if points:
        notes.append(f"{share * 100:.0f}% of revenue concentrated in a single non-domestic "
                     f"geography ({member.upper()})")
    return round(points, 2), {
        "available": True,
        "shares": shares,
        "largest_foreign_share": share,
        "largest_foreign_geography": member,
        "points": round(points, 2),
        "notes": notes,
        "method": "Single-geography revenue concentration, penalty-only above a "
                  "warning/severe share of consolidated revenue",
    }


def summarize(document_text, config=None):
    """Convenience wrapper returning a single publishable geographic-exposure record."""
    shares = geographic_revenue_shares(document_text)
    points, detail = score_geographic_concentration(shares, config=config)
    return {"source": "SEC EDGAR XBRL (Revenues x StatementGeographicalAxis)",
            "score_points": points, **detail}
