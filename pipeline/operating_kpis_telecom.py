"""Telecom carrier operating KPIs extracted from earnings-release exhibit text, not XBRL.

Sibling module to ``pipeline/operating_kpis.py`` (same house rules, same text source: the plain
text ``pipeline/filing_text.py`` fetches from a carrier's 8-K Exhibit 99.x earnings release, not
structured XBRL or Item codes -- see that module's docstring for why this pipeline reads prose
here at all, and ``docs/LIMITATIONS.md`` for what "unvalidated against live filings" means for
this module's output today). Kept in its own file, rather than added to ``operating_kpis.py``,
so a sibling sector's extraction work lands without touching a file this one is also touching.

Two metrics, both read from the same earnings-release text a carrier discloses together in its
"key operating metrics" or "selected operating data" section:

  * ``extract_postpaid_churn_rate`` -- postpaid phone churn, a small signed percentage (churn is
    always reported as a positive rate in practice, but the sign-handling is kept anyway, for the
    same reason the comps module keeps it: defensive parsing costs nothing and a filer that ever
    phrased a *change in* churn with a decrease verb should not silently mis-sign).
  * ``extract_postpaid_phone_arpu`` -- postpaid phone ARPU, a dollar figure, not a percentage.
    This is the one genuinely new pattern shape versus the comps module: a dollar amount
    (``$46.12``) rather than a signed percent, so it gets its own anchor/connective/value regex
    rather than reusing ``_PERCENT``.

The house rule this module is held to exactly as strictly as ``operating_kpis.py``: **a pattern
that does not match cleanly returns None, never a best guess.** The same two text-specific
reasons apply here, doubly for ARPU:

  * A release routinely states more than one figure for the same metric under near-identical
    phrasing -- current-quarter ARPU alongside the prior-year comparison quarter's ARPU, or
    postpaid phone churn alongside blended/total postpaid churn -- which this function cannot
    structurally tell apart without parsing document layout, which it does not do. Multiple
    distinct candidate values is therefore ambiguous and returns ``None``, not the first, largest,
    or smallest match.
  * Sign (churn) and magnitude (ARPU) are each resolved once from the matched text; nothing here
    compounds a verb's directionality with punctuation the way a naive parser could.

Scope: postpaid phone churn rate and postpaid phone ARPU for carriers that report them under
these specific phrasing conventions. Prepaid churn/ARPU, broadband/cable subscriber metrics
(relevant for the cable-heavy names in this universe -- CHTR, CMCSA, LBRDK), wireless net adds,
and the rest of a full telecom-KPI research brief are not attempted -- each is its own researched
phrasing pattern and its own validation pass against real filings, not something to guess at in
bulk. A cable/broadband-only filer's release is expected to return ``"not_found"`` for both
metrics here, which is a correct result, not a bug.
"""

from __future__ import annotations

import re

# A signed percentage, in either "-0.85%" or "(0.85)%" notation, never a mismatched paren. Kept
# identical to operating_kpis._PERCENT -- churn rates are commonly reported to two decimal places
# ("0.80%"), which this already handles.
_PERCENT = r"(?:\(-?\d{1,2}(?:\.\d{1,2})?\)|-?\d{1,2}(?:\.\d{1,2})?)%"

# A dollar amount, e.g. "$46.12". Telecom ARPU is reported in whole-to-low-hundreds of dollars
# (never four digits in practice for a per-subscriber monthly figure), so the digit count is
# capped defensively the same way _PERCENT caps percentage digits -- a cap that also helps keep
# the pattern from wandering into an unrelated larger dollar figure (e.g. a revenue total in
# millions) that happens to appear nearby.
_DOLLARS = r"\$\d{1,4}(?:\.\d{1,2})?"

_NEGATIVE_VERBS = ("decreased", "declined", "fell", "down", "negative", "lower")

# Anchor phrase, a short connective run (never crossing a sentence boundary), an optional
# direction verb or "of"/"was"/"were", then the percentage. The connective window is short and
# non-greedy on purpose -- see operating_kpis.py's comment on the same tradeoff: a long window
# would as happily bridge two unrelated sentences that each mention churn and a percentage.
_POSTPAID_CHURN_PATTERN = re.compile(
    r"((?:branded[\s-])?postpaid(?:[\s-](?:phone|wireless))?[\s-]churn(?:[\s-]rate)?)"
    r"[^.\n%]{0,40}?"
    r"(increased|decreased|improved|worsened|was|were|of)"
    r"[^.\n%]{0,20}?"
    r"(" + _PERCENT + r")",
    re.IGNORECASE,
)

# Same shape as the churn pattern, but anchored on ARPU phrasing and looking for a dollar amount
# instead of a percent. "average revenue per postpaid phone customer" is the spelled-out form a
# few carriers use instead of the "ARPU" abbreviation; both anchor to the same value pattern.
_POSTPAID_ARPU_PATTERN = re.compile(
    r"(postpaid(?:[\s-]phone)?[\s-]ARPU|average revenue per postpaid(?:[\s-]phone)? customer)"
    r"[^.\n$]{0,40}?"
    r"(increased to|decreased to|of|was|were|to)"
    r"[^.\n$]{0,20}?"
    r"(" + _DOLLARS + r")",
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
                  or any(word in (verb or "").lower() for word in _NEGATIVE_VERBS))
    return -magnitude if is_negative else magnitude


def _dollar_amount(raw_dollars):
    cleaned = raw_dollars.strip().lstrip("$")
    try:
        return abs(float(cleaned))
    except ValueError:
        return None


def extract_postpaid_churn_rate(text):
    """Postpaid phone churn rate from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a decimal fraction (0.008 for "churn of 0.80%"),
    rounded to 4 places, or ``None`` with a ``detail["status"]`` reason -- ``"not_found"`` (no
    matching phrase at all), ``"ambiguous_multiple_values"`` (more than one distinct candidate
    number), or ``"unparseable_percent"``.
    """
    matches = list(_POSTPAID_CHURN_PATTERN.finditer(text or ""))
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


def extract_postpaid_phone_arpu(text):
    """Postpaid phone ARPU (average revenue per user), in dollars, from earnings-release text.

    Returns ``(value, detail)``. ``value`` is a dollar figure (46.12 for "ARPU of $46.12"), or
    ``None`` with a ``detail["status"]`` reason -- ``"not_found"``, ``"ambiguous_multiple_values"``
    (more than one distinct dollar figure found -- e.g. current quarter alongside a prior-year
    comparison under near-identical phrasing), or ``"unparseable_dollar_amount"``.
    """
    matches = list(_POSTPAID_ARPU_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_dollar_amount(match.group(3)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_dollar_amount", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _dollar_amount(match.group(3))
    return round(value, 2), {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
