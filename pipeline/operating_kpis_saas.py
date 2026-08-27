"""SaaS operating KPIs extracted from earnings-release exhibit text, not XBRL.

Sibling module to ``pipeline/operating_kpis.py`` (same-store/comparable sales for retail and
restaurants) -- see that module's docstring for the full rationale on why this pipeline reads
prose here at all (it deliberately does not, everywhere else) and for what "unvalidated against
live filings" means for this module's output today. This module covers the SaaS-industry
equivalent: **Annual Recurring Revenue (ARR)** and **Net Revenue Retention (NRR)**, both read
from the same Item 2.02 earnings-release exhibit text ``pipeline/filing_text.py`` fetches.

The house rule is identical: **a pattern that does not match cleanly returns None, never a best
guess**, and multiple *distinct* candidate values found in one document is treated as ambiguous
rather than resolved by picking one -- a release commonly states both the quarter's ARR and a
year-ago comparison figure, or both a headline NRR and a "gross retention" figure under
near-identical phrasing.

Two metrics, two different value shapes, so they get two different parsing strategies:

  * ``annual_recurring_revenue`` is a dollar amount paired with a magnitude word ("million" /
    "billion"), not a percentage -- so this module adds a currency-and-scale parser (there is
    no equivalent in the comps reference) and normalizes every match to millions as a float,
    e.g. "$1.25 billion" and "$1,250 million" both become ``1250.0``. Company size varies by two
    to three orders of magnitude across this universe (a $50M-ARR name and a $10B-ARR name can
    both appear), so the scale word is load-bearing and is captured, not assumed.

  * ``net_revenue_retention_rate`` is a plain percentage, always stated as a positive number in
    the 100%-centered range SaaS companies use (net revenue retention is a ratio of ending to
    starting cohort revenue, not a signed growth rate) -- roughly 50%-200% covers every real
    published figure, whether the company is expanding accounts faster than it loses them
    (>100%) or not (<100%, a real and meaningfully bad number that must NOT be treated as a
    parse failure or filtered out). Because it is never written with a leading minus sign or
    parenthesized-negative notation in this context, this module does *not* reuse the comps
    module's ``_signed_percent``/parenthesized-negative machinery -- carrying that complexity
    over would do nothing but risk silently accepting a malformed match. A plain
    ``\\d{2,3}(?:\\.\\d{1,2})?%`` percent, converted straight to a decimal ratio (125% -> 1.25,
    not 0.25 -- these companies report the ratio itself, not a delta over 100%), is what real
    filings use and what this module matches.

Scope: ARR and NRR are the only two KPIs implemented here. Other SaaS-adjacent metrics (RPO,
billings, CAC payback, magic number, rule-of-40 components) are not attempted -- same reasoning
as the comps module's own scope note: each would need its own researched phrasing patterns and
its own validation pass against real filings.
"""

from __future__ import annotations

import re

# Currency amount: optional leading "$", digits with optional thousands separators and an
# optional decimal component. Deliberately does not allow a trailing "%" or a preceding word
# like "up" that would make it read as a growth figure rather than a level.
_DOLLAR_AMOUNT = r"\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
_SCALE_WORD = r"(million|billion)"

_SCALE_TO_MILLIONS = {"million": 1.0, "billion": 1000.0}

# Anchor phrase (ARR, or its common synonyms/parenthetical), a short connective run that never
# crosses a sentence boundary, then a dollar amount followed by its magnitude word. The
# connective window is short and non-greedy for the same reason as the comps pattern: a long
# window would as happily bridge two unrelated sentences that each mention revenue and a
# dollar figure.
_ARR_PATTERN = re.compile(
    r"(annual recurring revenue(?:\s*\(arr\))?|arr)"
    r"[^.\n$]{0,60}?"
    r"(" + _DOLLAR_AMOUNT + r")"
    r"\s*" + _SCALE_WORD,
    re.IGNORECASE,
)

# Anchor phrase covering the common industry synonyms for the same metric (net revenue
# retention, net dollar retention / NDR, dollar-based net retention), a short connective run,
# then a plain percentage. Two to three digits before the decimal covers the realistic range
# (well below 100% for a struggling cohort, well above it for strong net expansion) without
# also matching a one-digit percentage that is almost certainly some other metric entirely.
_NRR_PATTERN = re.compile(
    r"(net (?:revenue|dollar)[\s-]based? retention(?:\s*rate)?|"
    r"net (?:revenue|dollar) retention(?:\s*rate)?(?:\s*\(ndr\))?|"
    r"dollar-based net retention(?:\s*rate)?|ndr)"
    r"[^.\n%]{0,40}?"
    r"(\d{2,3}(?:\.\d{1,2})?)%",
    re.IGNORECASE,
)


def _dollar_millions(raw_amount, scale_word):
    cleaned = raw_amount.strip().lstrip("$").strip().replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    multiplier = _SCALE_TO_MILLIONS.get(scale_word.lower())
    if multiplier is None:
        return None
    return amount * multiplier


def extract_annual_recurring_revenue(text):
    """Annual Recurring Revenue from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a float in millions of dollars (1250.0 for "$1.25
    billion" or "$1.25 billion ARR"), or ``None`` with a ``detail["status"]`` reason --
    ``"not_found"`` (no matching phrase at all), ``"ambiguous_multiple_values"`` (more than one
    distinct candidate figure -- e.g. current-quarter ARR alongside a year-ago comparison), or
    ``"unparseable_amount"``.
    """
    matches = list(_ARR_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_dollar_millions(match.group(2), match.group(3)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_amount", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _dollar_millions(match.group(2), match.group(3))
    return round(value, 4), {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }


def extract_net_revenue_retention_rate(text):
    """Net Revenue Retention (or Net Dollar Retention) rate from one earnings-release
    exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a decimal ratio (1.25 for "125%", 0.98 for "98%"
    -- the ratio itself, not a delta over 100%; a value below 1.0 is a real, valid, negative-
    for-the-company figure and is returned exactly like any other match, never treated as an
    error), or ``None`` with a ``detail["status"]`` reason -- ``"not_found"`` or
    ``"ambiguous_multiple_values"`` (more than one distinct candidate percentage, e.g. a
    headline net revenue retention figure alongside a separately stated gross retention figure
    under similar phrasing).
    """
    matches = list(_NRR_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {round(float(match.group(2)) / 100, 4) for match in matches}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = round(float(match.group(2)) / 100, 4)
    return value, {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
