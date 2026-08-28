"""Semiconductor / aerospace-defense book-to-bill ratio, extracted from earnings-release exhibit
text, not XBRL.

Same extraction discipline as ``pipeline/operating_kpis.py`` (same-store/comparable sales),
applied to a second sector KPI: the ratio of new orders booked to product billed/shipped in a
period, a leading indicator that gets stated in prose, not in structured facts. This is the
second module in the pipeline that reads a filing's actual prose rather than its structured facts
or Item codes -- see ``pipeline/filing_text.py``'s module docstring for why that is otherwise
avoided, and docs/LIMITATIONS.md for what "unvalidated against live filings" means for this
module's output today.

**Which names actually say this**: book-to-bill is a semiconductor-capital-equipment convention
first -- SEMI (the industry association) publishes an aggregate book-to-bill series, and the
equipment makers (Applied Materials, KLA, Lam Research, Entegris, Onto Innovation, Teradyne,
Veeco) cite either that industry figure or their own company ratio in earnings releases about as
routinely as retailers cite comps. Fabless and IDM chipmakers (Nvidia, AMD, Qualcomm, Broadcom,
Texas Instruments, and the rest of the digital/analog chip list) do not follow this convention --
their releases talk about revenue, gross margin, and design wins, essentially never a book-to-bill
ratio, so ``not_found`` is the expected and correct result for nearly all of them. Aerospace and
defense primes (Lockheed Martin, RTX, Northrop Grumman, General Dynamics, Boeing, L3Harris) are a
third pattern again: some report a book-to-bill or backlog-coverage figure for one segment (e.g. a
missiles-and-fire-control or space segment) rather than a company-wide ratio, and several just
state backlog in dollars with no ratio at all. A "not_found" or a segment-scoped match on those
names is not a bug in this module -- it is what the filings actually say.

The house rule this module is held to exactly as strictly as everywhere else in the pipeline:
**a pattern that does not match cleanly returns None, never a best guess.** Two further,
text-specific versions of that same rule, carried over from the comparable-sales module:

  * More than one distinct book-to-bill figure in one document -- a segment's ratio next to a
    different segment's, or the current quarter's next to a trailing-twelve-month figure -- is
    ambiguous and returns ``None``, not the first (or largest, or smallest) match found.
  * The ratio is a bare decimal, not a percentage and not signed. Real-world filings decorate the
    same number three ways: a plain decimal ("1.15"), a trailing "x" ("0.92x"), or an explicit
    ":1" ("1.05:1"). All three are unit decoration around the same ratio value and are stripped,
    not computed against.

Scope: book-to-bill ratio (semiconductor equipment, aerospace/defense) is the only KPI
implemented in this module. See ``pipeline/operating_kpis.py`` for the retail/restaurant
comparable-sales module this one mirrors.
"""

from __future__ import annotations

import re

# A bare ratio, 1-2 digits optionally followed by up to 2 decimal digits -- "1", "1.1", "0.92",
# "10.25". Never signed: book-to-bill is not reported as a negative number.
_RATIO = r"\d{1,2}(?:\.\d{1,2})?"

# Anchor phrase ("book-to-bill" or "book-to-bill ratio", hyphen or space between the words),
# a connective run up to a required linking word ("of", "was", "is", "were", "stood at", "came
# in at"), then the ratio itself, with an optional trailing "x" or ":1" unit decoration.
#
# The connective window before the linking word excludes only sentence boundaries (matching
# ``operating_kpis.py``'s convention) -- real filings routinely insert a few words ("for the
# quarter", "for the segment") between the anchor and the verb. The shorter window between the
# linking word and the number additionally excludes "$": without that exclusion, a phrase like
# "book-to-bill remained strong; revenue of $1.15 billion was reported" would let the regex slide
# past the dollar sign and misread an unrelated dollar figure's numeral as the ratio. Requiring
# the number to follow the linking word with no dollar sign in between blocks that false
# positive, since a real book-to-bill figure is never dollar-denominated.
_BOOK_TO_BILL_PATTERN = re.compile(
    r"(book[\s-]to[\s-]bill(?:\s+ratio)?)"
    r"[^.\n]{0,60}?"
    r"(of|was|is|were|stood at|came in at)"
    r"[^.\n$]{0,20}?"
    r"(" + _RATIO + r")"
    r"(?:x\b|:1\b)?",
    re.IGNORECASE,
)


def _ratio_value(raw):
    cleaned = raw.strip()
    try:
        return round(float(cleaned), 4)
    except ValueError:
        return None


def extract_book_to_bill_ratio(text):
    """Book-to-bill ratio from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a bare decimal ratio (1.15 for "book-to-bill ratio
    of 1.15", 0.92 for "book-to-bill of 0.92x", 1.05 for "book-to-bill ratio ... was 1.05:1"), or
    ``None`` with a ``detail["status"]`` reason -- ``"not_found"`` (no matching phrase at all --
    the expected result for most names outside semiconductor capital equipment),
    ``"ambiguous_multiple_values"`` (more than one distinct candidate ratio), or
    ``"unparseable_ratio"``.
    """
    matches = list(_BOOK_TO_BILL_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_ratio_value(match.group(3)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_ratio", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _ratio_value(match.group(3))
    return value, {
        "status": "matched",
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
