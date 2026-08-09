"""Score customer-concentration risk the way ASC 280 actually discloses it.

ASC 280-10-50-42 requires naming any customer that accounts for 10% or more of
consolidated revenue. Many filers tag the percentage itself as
``us-gaap:ConcentrationRiskPercentage1``, qualified by
``ConcentrationRiskByTypeAxis = CustomerConcentrationRiskMember`` (as opposed to vendor,
credit, or geographic concentration, which share the same base concept on a different
axis member). Reading this off ``company_concept``/``companyfacts`` does not work: both
APIs return default (non-dimensional) facts only, and a percentage qualified by a
concentration-type axis has no undimensioned counterpart for them to return - see
``pipeline/xbrl_dimensions.py`` for the general mechanism this reads it through instead.

This is a risk factor, not a two-sided signal: a company earning 40% of revenue from one
buyer is exposed to that buyer's decisions in a way a diversified peer is not, regardless
of how well the relationship is going today. The modifier this feeds is accordingly
penalty-only, the same shape as ``short_interest_modifier`` in ``advisor_engine.py``: it
flags a known, uncompensated risk rather than betting on a direction.

One deliberate limitation, stated plainly rather than left to be discovered: the
dimension only carries a *magnitude*. The customer's *identity* usually is not in the tag
at all (the benchmark axis member names the revenue standard being measured against, not
the counterparty), so this cannot replace ``theme_signals.customer_overlap_share``'s
name-matching against confirmed spenders - it can only say how concentrated revenue is,
not to whom.
"""

from xbrl_dimensions import dimensional_facts, facts_matching

CONCENTRATION_CONCEPT = "ConcentrationRiskPercentage1"
CUSTOMER_TYPE_AXIS = "ConcentrationRiskByTypeAxis"
CUSTOMER_TYPE_MEMBER = "CustomerConcentrationRiskMember"

DEFAULTS = {
    "warning_share": 0.15,   # comfortably above the 10% ASC 280 disclosure floor
    "severe_share": 0.30,    # roughly a third of revenue riding on one counterparty
    "max_penalty": 3.0,
}


def customer_concentration_percentages(document_text):
    """Every disclosed customer-concentration percentage in one filing, largest first.

    Filters to ``CustomerConcentrationRiskMember`` specifically so a vendor, credit, or
    geographic concentration tagged on the same base concept is not mistaken for revenue
    concentration in a customer.
    """
    facts = dimensional_facts(document_text, CONCENTRATION_CONCEPT)
    customer_facts = facts_matching(facts, {CUSTOMER_TYPE_AXIS: CUSTOMER_TYPE_MEMBER})
    values = sorted({round(fact["value"], 4) for fact in customer_facts
                     if fact["value"] is not None}, reverse=True)
    return values


def score_concentration_risk(percentages, config=None):
    """A bounded, penalty-only modifier from disclosed customer-concentration percentages.

    Returns ``(points, detail)`` with ``points <= 0``. Scored on the single largest
    disclosed customer share - a company already at the ``severe_share`` threshold is not
    made meaningfully safer by also naming a second, smaller customer.
    """
    settings = {**DEFAULTS, **(config or {})}
    if not percentages:
        return 0.0, {"available": False, "reason": "no disclosed customer concentration",
                     "percentages": []}
    top = percentages[0]
    cap = settings["max_penalty"]
    if top >= settings["severe_share"]:
        points = -cap
    elif top >= settings["warning_share"]:
        points = -round(cap / 2, 2)
    else:
        points = 0.0
    notes = []
    if points:
        named = len(percentages)
        notes.append(f"largest named customer is {top * 100:.0f}% of revenue"
                     f"{f' ({named} customers named above 10%)' if named > 1 else ''}")
    return round(points, 2), {
        "available": True,
        "percentages": percentages,
        "largest_customer_share": top,
        "points": round(points, 2),
        "notes": notes,
        "method": "ASC 280 customer concentration, penalty-only above a warning/severe "
                  "share of consolidated revenue",
    }


def summarize(document_text, config=None):
    """Convenience wrapper returning a single publishable concentration-risk record."""
    percentages = customer_concentration_percentages(document_text)
    points, detail = score_concentration_risk(percentages, config=config)
    return {"source": "SEC EDGAR XBRL (ConcentrationRiskPercentage1)",
            "score_points": points, **detail}
