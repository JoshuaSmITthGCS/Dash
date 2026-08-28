"""Asset-manager / broker-dealer operating KPIs extracted from earnings-release exhibit text,
not XBRL.

Same house rule, same house risk, same house scope boundary as ``pipeline/operating_kpis.py``
(the comps/same-store-sales sibling of this module, whose docstring this one deliberately
mirrors): assets under management and net flows are prose disclosures for an asset manager or
broker-dealer, not structured SEC facts, so the only place to get them is the earnings release
itself -- Exhibit 99.x of an Item 2.02 8-K, the plain text ``pipeline/filing_text.py`` fetches.
This is pattern matching against known, common phrasing, nothing more; see that module's
docstring for why the pipeline otherwise avoids free text entirely, and docs/LIMITATIONS.md for
what "unvalidated against live filings" means for this module's output today. As with the comps
module, the environment this was written in has no network access to SEC EDGAR, so nothing here
has been checked against a single real exhibit -- see
``pipeline/collect_operating_kpis_asset_manager.py``'s docstring before treating this store as
anything but a coverage experiment.

**A pattern that does not match cleanly returns ``None``, never a best guess.** Two
text-specific versions of that rule, both inherited unchanged from the comps module:

  * A release commonly states more than one AUM or net-flows figure in one document -- quarter-
    end AUM alongside a year-ago comparison, or total-firm AUM alongside a single segment's,
    under near-identical phrasing this function cannot structurally tell apart without parsing
    document layout, which it does not do. Multiple distinct candidate values is therefore
    ambiguous and returns ``None``, not the first (or largest, or smallest) match found.
  * Sign (for net flows) is resolved once, from whichever of the inflow/outflow word, a leading
    minus sign, or parenthesized-negative notation is present -- never compounded.

A third, metric-specific piece of care this module adds on top of the comps pattern: unlike a
percentage, a dollar figure is written at wildly different orders of magnitude across filers and
even within one release (a segment's flows in millions next to firm-wide AUM in trillions), so
every match here carries an explicit magnitude word ("million"/"billion"/"trillion") and is
normalized to billions before comparison -- see ``_dollars_in_billions`` below, the one shared
helper both extraction functions call so the million/billion/trillion conversion is defined
exactly once.

Scope: assets under management and net flows are the only two KPIs implemented here. Fee rate,
AUA (assets under administration, distinct from AUM), and segment-level breakouts are not --
each would need its own researched phrasing and its own validation pass against real filings,
same incremental-addition rationale ``pipeline/operating_kpis.py`` states for its own scope.

Coverage caveat specific to this sector: not every ticker this is run against is a pure asset
manager. A broker-dealer (e.g. Goldman Sachs, Morgan Stanley, Jefferies) may not headline "AUM"
in the same release-level phrasing an asset manager does, and a trading-venue operator (e.g.
MarketAxess) is not an asset manager at all and should not disclose AUM in this phrasing. Both
extraction functions are expected, and correct, to return ``"not_found"`` for those -- that is
not a bug in the pattern, it is the pattern correctly declining to invent a fact that was never
disclosed in the searched-for shape.
"""

from __future__ import annotations

import re

# A dollar figure with an explicit magnitude word -- "$650 billion", "$1.2 trillion", "$410.5
# billion" -- or the parenthesized-negative form used for net flows, "$(4.2) billion". The
# magnitude word is mandatory: a bare "$650" is not, on its own, distinguishable from a
# per-share or unrelated figure at this module's remove from document layout, so it is not
# matched at all (falls through to "not_found" rather than guessing units).
_MAGNITUDE_WORDS = {"million": 1e-3, "billion": 1.0, "trillion": 1e3}
_MAGNITUDE_ALTERNATION = "|".join(_MAGNITUDE_WORDS)

_DOLLAR_AMOUNT = (
    r"\$\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?"
    r"\s*(?:" + _MAGNITUDE_ALTERNATION + r")"
)

_NEGATIVE_WORDS = ("outflow", "outflows", "negative")


def _dollars_in_billions(raw_amount, sign_context=""):
    """Parse one ``_DOLLAR_AMOUNT`` match into a float in billions, or ``None`` if unparseable.

    ``sign_context`` is additional text (e.g. the matched direction phrase) checked for
    inflow/outflow-style sign words on top of the amount's own leading minus or parentheses --
    used by ``extract_net_flows``. ``extract_assets_under_management`` calls this with no sign
    context since AUM is never itself a signed figure.
    """
    cleaned = raw_amount.strip()
    is_parenthesized = "(" in cleaned
    cleaned = cleaned.replace("(", "").replace(")", "")
    magnitude_match = re.search(_MAGNITUDE_ALTERNATION, cleaned, re.IGNORECASE)
    if not magnitude_match:
        return None
    magnitude_word = magnitude_match.group(0).lower()
    numeric_part = cleaned[: magnitude_match.start()].strip()
    numeric_part = numeric_part.replace("$", "").replace(",", "").strip()
    try:
        magnitude = abs(float(numeric_part))
    except ValueError:
        return None
    is_negative = (
        is_parenthesized
        or numeric_part.startswith("-")
        or any(word in sign_context.lower() for word in _NEGATIVE_WORDS)
    )
    value = magnitude * _MAGNITUDE_WORDS[magnitude_word]
    return round(-value if is_negative else value, 4)


# Anchor phrase, a short non-greedy connective run that never crosses a sentence boundary
# (bounded on "." and newline the same way the comps pattern is), then the dollar amount.
# "assets under management" (any case, with an optional "(AUM)" gloss) and "total AUM" are
# matched case-insensitively -- unambiguous multi-word phrases. A bare "AUM" is also matched
# ("AUM was $410.5 billion as of quarter end" is common release-summary phrasing), but only as
# an exact-case, letter-bounded token: matching it case-insensitively would as happily fire on
# "aum" inside an unrelated word (e.g. "aluminum"), which the exact-case, word-bounded form does
# not.
_AUM_PATTERN = re.compile(
    r"((?i:assets under management(?:\s*\(\s*\"?AUM\"?\s*\))?|total\s+AUM)|(?<![A-Za-z])AUM(?![A-Za-z]))"
    r"[^.\n$]{0,60}?"
    r"((?i:" + _DOLLAR_AMOUNT + r"))",
)

# "net inflows/outflows of $X billion", "net flows of $(X) billion", "long-term net inflows of
# $X billion". The direction phrase is captured so sign can be resolved from it exactly like
# the comps module resolves sign from "increased"/"decreased".
_NET_FLOWS_PATTERN = re.compile(
    r"((?:long-term\s+)?net\s+(?:flows|inflows|outflows))"
    r"[^.\n$]{0,40}?"
    r"(" + _DOLLAR_AMOUNT + r")",
    re.IGNORECASE,
)


def extract_assets_under_management(text):
    """Assets under management from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a float in billions of dollars (650.0 for "$650
    billion", 1200.0 for "$1.2 trillion"), or ``None`` with a ``detail["status"]`` reason --
    ``"not_found"`` (no matching phrase at all), ``"ambiguous_multiple_values"`` (more than one
    distinct candidate figure), or ``"unparseable_amount"``.
    """
    matches = list(_AUM_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_dollars_in_billions(match.group(2)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_amount", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _dollars_in_billions(match.group(2))
    return value, {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }


def extract_net_flows(text):
    """Net flows (inflows positive, outflows negative) from one earnings-release exhibit's
    plain text.

    Returns ``(value, detail)``. ``value`` is a signed float in billions of dollars (12.0 for
    "net inflows of $12 billion", -3.5 for "net outflows of $3.5 billion", -4.2 for "net flows
    of $(4.2) billion"), or ``None`` with a ``detail["status"]`` reason -- ``"not_found"``,
    ``"ambiguous_multiple_values"``, or ``"unparseable_amount"``.
    """
    matches = list(_NET_FLOWS_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_dollars_in_billions(match.group(2), sign_context=match.group(1)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_amount", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _dollars_in_billions(match.group(2), sign_context=match.group(1))
    return value, {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
