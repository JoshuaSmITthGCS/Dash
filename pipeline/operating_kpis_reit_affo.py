"""REIT AFFO-per-share extracted from earnings-release exhibit text, not XBRL.

Companion to ``pipeline/operating_kpis.py`` (same-store/comparable sales) -- same technique,
same pattern-match-or-``None`` discipline, same source (the plain text ``pipeline/filing_text.py``
fetches from an 8-K's Item 2.02 Exhibit 99.x), and the same reason for doing it this way at all:
see that module's docstring and ``pipeline/edgar_filing_signals.py``'s for why free-text parsing
is otherwise avoided in this pipeline.

This module is deliberately narrower than "compute AFFO." Adjusted Funds From Operations is not
a standardized GAAP or even NAREIT-defined figure the way FFO is -- the original sector-KPI
research brief flags this explicitly: every equity REIT defines its own recurring-capex and
straight-line-rent adjustments, so no two filers' AFFO reconciliations are directly comparable
line-for-line, and there is no structured tag to recompute it from. What nearly every equity
REIT's earnings release *does* do, despite that, is state a headline adjusted per-share figure in
prose -- "AFFO per share", "Core FFO per share", "FFO as adjusted per share" are three
conventions filers use interchangeably for the same purpose (their own "better than raw FFO"
per-share number). This module extracts *that stated figure*, verbatim, under whichever of the
three names the filer happened to headline. It does not recompute AFFO from its components, and
it does not attempt to reconcile one filer's AFFO to another's -- the number this returns is only
ever as comparable across filers as AFFO itself is, which per the research brief is "not very."

Contrast with ``pipeline/fundamentals_extended.py``'s ``derive_reit_ffo``: that function computes
a *simplified* FFO (net income plus D&A) structurally from ordinary tagged XBRL statement lines,
no free-text parsing needed, because plain FFO's inputs are ordinary GAAP figures. AFFO has no
such structural shortcut -- its adjustments are filer-specific and not tagged -- so the only way
to get a filer's own AFFO figure at all is to read what the filer's release says it is. The two
metrics are intentionally kept separate: this module never touches ``fundamentals_extended.py``,
and a caller wanting the structural, comparable, XBRL-based number should use that module instead
of this one.

The house rule, unchanged from ``operating_kpis.py``: **a pattern that does not match cleanly
returns None, never a best guess.** In particular:

  * Plain, unqualified "FFO per share" (without "AFFO", "adjusted", "core", or "as adjusted"
    nearby) is deliberately NOT matched here -- that is the simpler, structural FFO figure
    ``derive_reit_ffo`` already computes, and conflating the two would misrepresent which of two
    different numbers was reported.
  * A release commonly states more than one adjusted per-share figure in one document -- a
    quarterly figure alongside full-year guidance, or a diluted figure alongside a non-diluted
    one -- under near-identical phrasing this function cannot structurally tell apart without
    parsing document layout, which it does not do. Multiple distinct candidate dollar amounts is
    therefore treated as ambiguous and returns ``None``, not the first (or largest) match found.
  * The match window between the anchor phrase and the dollar amount never crosses a sentence
    boundary (or another dollar sign), for the same false-positive-avoidance reason
    ``operating_kpis.py``'s comparable-sales window does not.

Coverage note: this module returns "not_found" for any REIT that headlines FFO without one of
the AFFO/Core-FFO/FFO-as-adjusted qualifiers, or that does not state a per-share adjusted figure
in prose at all (a genuine and expected outcome for some filers, not a bug). Which convention
predominates among real REIT earnings releases -- and therefore what this module's real-world
match rate looks like -- is unvalidated: see ``pipeline/collect_operating_kpis_reit_affo.py``'s
module docstring and ``docs/LIMITATIONS.md`` for what "unvalidated against live filings" means
here, same as for ``operating_kpis.py``.
"""

from __future__ import annotations

import re

# A dollar-and-cents per-share figure, e.g. "$1.23" or "$0.98". Up to 3 whole-dollar digits is
# generous headroom above any real REIT AFFO/share figure, deliberately not tightened further.
_DOLLAR = r"\$\d{1,3}(?:\.\d{2})?"

# Three accepted synonyms for the same headline concept -- REITs are inconsistent about which
# one they lead with, so all three are treated as "this filer's adjusted, non-GAAP per-share
# number." Plain "FFO" (no qualifier) is intentionally absent from this list.
_AFFO_SYNONYM = r"\bAFFO\b|adjusted\s+funds\s+from\s+operations(?:\s*\(AFFO\))?"
_CORE_FFO_SYNONYM = r"core\s+FFO"
_FFO_AS_ADJUSTED_SYNONYM = r"FFO,?\s*as\s+adjusted"

_ANCHOR = "(" + _AFFO_SYNONYM + "|" + _CORE_FFO_SYNONYM + "|" + _FFO_AS_ADJUSTED_SYNONYM + ")"

# Anchor synonym, a short connective run to "per (diluted) share" (never crossing a sentence
# boundary or another dollar sign), then another short connective run to the dollar figure
# itself. The connective windows are short and non-greedy on purpose, mirroring
# operating_kpis.py's comparable-sales pattern -- a long window would as happily bridge two
# unrelated sentences that each happen to mention a per-share figure.
_AFFO_PER_SHARE_PATTERN = re.compile(
    _ANCHOR
    + r"[^.\n$]{0,40}?per\s+(?:diluted\s+)?share"
    + r"[^.\n$]{0,20}?"
    + "(" + _DOLLAR + ")",
    re.IGNORECASE,
)


def _classify_synonym(matched_anchor):
    lowered = matched_anchor.lower()
    if lowered.startswith("core"):
        return "core_ffo"
    if "as adjusted" in lowered:
        return "ffo_as_adjusted"
    return "affo"


def _parse_dollar(raw):
    cleaned = raw.strip().lstrip("$")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def extract_affo_per_share(text):
    """AFFO (or Core FFO, or FFO-as-adjusted) per share from one earnings-release exhibit's
    plain text.

    Returns ``(value, detail)``. ``value`` is a dollars-and-cents float (1.23 for "$1.23"), or
    ``None`` with a ``detail["status"]`` reason -- ``"not_found"`` (no matching phrase at all),
    ``"ambiguous_multiple_values"`` (more than one distinct candidate dollar amount), or
    ``"unparseable_amount"``. On a match, ``detail["synonym"]`` records which of the three
    accepted conventions the filer used -- ``"affo"``, ``"core_ffo"``, or ``"ffo_as_adjusted"``
    -- so a downstream consumer can tell which convention a given filer follows without
    re-parsing the text.
    """
    matches = list(_AFFO_PER_SHARE_PATTERN.finditer(text or ""))
    if not matches:
        return None, {"status": "not_found"}
    values = {_parse_dollar(match.group(2)) for match in matches}
    if None in values:
        return None, {"status": "unparseable_amount", "matched_text": matches[0].group(0).strip()}
    if len(values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": sorted(values)}
    match = matches[0]
    value = _parse_dollar(match.group(2))
    return value, {
        "status": "matched",
        "synonym": _classify_synonym(match.group(1)),
        "matched_phrase": match.group(1).strip(),
        "matched_text": match.group(0).strip(),
    }
