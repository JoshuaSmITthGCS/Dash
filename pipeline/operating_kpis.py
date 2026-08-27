"""Sector operating KPIs extracted from earnings-release exhibit text, not XBRL.

Every metric here (same-store/comparable sales today; see the module docstring's scope note
below for what is deliberately not attempted yet) is a pattern match against known, common
earnings-release phrasing, run against the plain text ``pipeline/filing_text.py`` fetches from
an 8-K's Exhibit 99.x. This is the one place in the pipeline that reads a filing's actual prose
rather than its structured facts or Item codes -- see that module's docstring for why, and
docs/LIMITATIONS.md for what "unvalidated against live filings" means for this module's output
today.

The house rule this module is held to exactly as strictly as everywhere else in the pipeline:
**a pattern that does not match cleanly returns None, never a best guess.** Two further,
text-specific versions of that same rule:

  * A release commonly states more than one comparable-sales figure in one document -- the
    quarter's number alongside year-to-date, or a U.S. figure alongside a global one -- under
    near-identical phrasing this function cannot structurally tell apart without parsing the
    surrounding document layout, which it does not do. Multiple distinct candidate values is
    therefore treated as ambiguous and returns ``None``, not the first (or largest, or
    smallest) match found.
  * Sign matters and is resolved once, from whichever of the verb, a leading minus sign, or
    parenthesized-negative notation is present -- never compounded (a parenthesized "(2.3)%"
    next to the word "decreased" is one negative number, not a double negative).

Scope: same-store/comparable sales (retail, restaurants) is the only KPI implemented. ARPU,
churn, MAU/DAU, ARR/NRR, rate base, capacity factor, AFFO and the rest of a full sector-KPI
research brief are not -- each would need its own researched phrasing patterns and its own
validation pass against real filings, which is exactly the work this module's introduction
makes tractable to add incrementally, not something to guess at in bulk.
"""

from __future__ import annotations

import re

# A signed percentage, in either "-2.3%" or "(2.3)%" notation, never a mismatched paren.
_PERCENT = r"(?:\(-?\d{1,2}(?:\.\d{1,2})?\)|-?\d{1,2}(?:\.\d{1,2})?)%"

_NEGATIVE_VERBS = ("decreased", "declined", "fell", "down", "negative")

# Anchor phrase, a short connective run (never crossing a sentence boundary), a direction verb
# or "of", then the percentage itself. The connective window is short and non-greedy on purpose
# -- a long window would as happily bridge two unrelated sentences that each mention "sales"
# and a percentage.
_COMPARABLE_SALES_PATTERN = re.compile(
    r"(comparable(?:[\s-]\w+){0,3}[\s-]sales|same[\s-]store[\s-]sales|"
    r"same[\s-]restaurant[\s-]sales|comparable[\s-]restaurant[\s-]sales)"
    r"[^.\n%]{0,60}?"
    r"(increased|decreased|grew|declined|rose|fell|were up|were down|of)"
    r"[^.\n%]{0,20}?"
    r"(" + _PERCENT + r")",
    re.IGNORECASE,
)


def _signed_percent(raw_percent, verb):
    cleaned = raw_percent.strip()
    is_parenthesized = cleaned.startswith("(")
    cleaned = cleaned.strip("()%")
    try:
        magnitude = abs(float(cleaned))
    except ValueError:
        return None
    is_negative = (is_parenthesized or cleaned.startswith("-")
                  or any(word in verb.lower() for word in _NEGATIVE_VERBS))
    return -magnitude if is_negative else magnitude


def extract_comparable_sales_growth(text):
    """Same-store / comparable sales growth from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a decimal fraction (0.032 for "increased 3.2%"),
    rounded to 4 places, or ``None`` with a ``detail["status"]`` reason -- ``"not_found"`` (no
    matching phrase at all), ``"ambiguous_multiple_values"`` (more than one distinct candidate
    number), or ``"unparseable_percent"``.
    """
    matches = list(_COMPARABLE_SALES_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_signed_percent(match.group(3), match.group(2)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_percent", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _signed_percent(match.group(3), match.group(2))
    return round(value / 100, 4), {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
