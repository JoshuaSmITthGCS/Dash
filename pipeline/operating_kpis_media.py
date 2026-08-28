"""Media/internet platform user-count KPIs extracted from earnings-release exhibit text, not XBRL.

Sibling to ``pipeline/operating_kpis.py`` (same-store/comparable sales for retail and
restaurants): same source (the plain text ``pipeline/filing_text.py`` fetches from an Item 2.02
8-K's Exhibit 99.x), same house rule -- **a pattern that does not match cleanly returns None,
never a best guess** -- and the same reason for existing at all: monthly and daily active user
counts genuinely do not exist anywhere in structured SEC XBRL for most filers. They live only in
the earnings release's prose, phrased however each company's investor-relations team phrases it.

Two metrics, extracted independently from the same document by two separate functions:

  * ``extract_monthly_active_users`` -- "MAU" and its full-word form "monthly active users", plus
    Meta's own terminology "monthly active people" / "MAP" (Meta's 10-Qs and earnings releases use
    "Family Monthly Active People (MAP)" rather than "MAU" for its cross-app family metric; this
    module treats it as the same concept, not a different one).
  * ``extract_daily_active_users`` -- "DAU" / "daily active users", plus Meta's "daily active
    people" / "DAP".

Unlike the percent-only comparable-sales pattern, a user count needs a **magnitude word**
alongside the number ("3.07 billion", "450 million") normalized to one canonical unit --
millions, as a float -- before two mentions can even be compared for the ambiguity check below.
``_scaled_count`` is that normalization, shared by both metrics.

Real earnings-release phrasing puts the number on either side of the anchor phrase:

  * anchor first: "MAU of 450 million", "monthly active users increased to 82 million",
    "daily active users (DAUs) increased 5% to 210 million", "Family Daily Active People (DAP) of
    3.35 billion"
  * number first: "3.07 billion monthly active users (MAUs)"

Both orderings are matched, by two separate compiled patterns per metric, run against the same
text and merged before the ambiguity check -- not one another's alternation branch, because the
two orderings share no fixed anchor-then-number (or number-then-anchor) skeleton to alternate
within a single pattern without either becoming unreadable or losing the sentence-boundary guard
each half needs independently.

Two of the same text-specific rules ``operating_kpis.py`` documents apply here unchanged:

  * A release commonly states the current period's figure alongside a year-ago comparison under
    near-identical phrasing ("increased to 82 million ... compared to 76 million a year ago") that
    this module does not attempt to structurally disambiguate. More than one distinct candidate
    value in one document is therefore ``"ambiguous_multiple_values"``, not the first match found.
  * The connective window between an anchor and its number never crosses a sentence boundary (it
    excludes ``.`` and newlines), so a company that merely mentions "monthly active users" in one
    sentence and an unrelated dollar figure in the next does not get a fabricated pairing.

Scope: MAU and DAU only. See ``operating_kpis.py``'s own scope note for the rest of a full
sector-KPI research brief (ARPU, churn, ARR/NRR, rate base, capacity factor, AFFO, ...) that
remains unimplemented; this module does not touch subscriber counts (Netflix, Disney+, HBO Max)
which are a related but distinct metric this module does not attempt to extract.
"""

from __future__ import annotations

import re

# A plain count, optionally comma-grouped, optionally with a decimal -- "82", "3.07", "3,500".
_NUMBER = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)"

# "million" / "billion", case-insensitive regardless of the anchor abbreviation's own case.
_MAGNITUDE = r"((?i:million|billion))"

# "of", "reached", "was", "were", or a direction verb ("increased", "grew", "rose", "climbed")
# optionally carrying its own percent-change clause before the "to" that introduces the number --
# "increased 5% to 210 million" is one connective, not a direction verb plus a stray percentage.
_CONNECTIVE = (
    r"(?:(?i:of|reached|was|were)"
    r"|(?i:increased|grew|rose|climbed)(?:\s+\d{1,3}(?:\.\d+)?%)?\s+(?i:to))"
)

# Filler words allowed between a number+magnitude and the anchor phrase that follows it directly
# ("3.07 billion monthly active users", or "3.07 billion global monthly active users"). "and" is
# excluded from the filler vocabulary on purpose: without it, this window would as happily bridge
# past a conjunction into a second, unrelated clause's anchor -- pairing one metric's number with
# a different metric's anchor two words later ("3.35 billion and Family Monthly Active People").
_LEADING_FILLER = r"(?:(?!and\b)\w+\s+){0,2}"


def _period_patterns(period_word, abbr_prefix):
    """Build the (anchor-first, number-first) compiled patterns for one metric.

    ``period_word`` is "monthly" or "daily"; ``abbr_prefix`` is "MA" or "DA" -- the two-letter
    stem shared by both of a company's abbreviations for that period ("MAU"/"MAP", "DAU"/"DAP").
    The full-word phrase ("monthly active users") is matched case-insensitively; the abbreviation
    itself is matched case-sensitively (word-bounded) since a lowercase "mau"/"dau" substring is
    far more likely to be an unrelated word fragment than this metric.
    """
    abbr = rf"\b(?:{abbr_prefix}Us?|{abbr_prefix}Ps?)\b"
    full_phrase = rf"(?i:{period_word} active (?:users|people))"
    anchor = rf"(?:{full_phrase}|{abbr})"
    trailing_abbr_paren = rf"(?:\s*\({abbr}\))?"

    anchor_first = re.compile(
        r"(" + anchor + r")" + trailing_abbr_paren
        + r"[^.\n]{0,40}?" + _CONNECTIVE + r"\s+" + _NUMBER + r"\s*" + _MAGNITUDE
    )
    number_first = re.compile(
        _NUMBER + r"\s*" + _MAGNITUDE + r"\s+" + _LEADING_FILLER
        + r"(" + anchor + r")" + trailing_abbr_paren
    )
    return anchor_first, number_first


_MAU_ANCHOR_FIRST, _MAU_NUMBER_FIRST = _period_patterns("monthly", "MA")
_DAU_ANCHOR_FIRST, _DAU_NUMBER_FIRST = _period_patterns("daily", "DA")


def _scaled_count(number_text, magnitude_word):
    """A regex-captured number and magnitude word, normalized to millions as a float.

    Returns ``None`` (never a guess) when the number can't be parsed or the magnitude word isn't
    one this module recognizes -- the latter should be unreachable given ``_MAGNITUDE`` only ever
    captures "million"/"billion", but this stays defensive rather than assuming its own regex.
    """
    cleaned = (number_text or "").replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    magnitude = (magnitude_word or "").strip().lower()
    if magnitude == "billion":
        return value * 1000.0
    if magnitude == "million":
        return value
    return None


def _extract_user_count(text, anchor_first_pattern, number_first_pattern):
    """Shared extraction body for both metrics: run both orderings, merge, apply the same
    not-found / ambiguous / matched decision ``operating_kpis.extract_comparable_sales_growth``
    uses.
    """
    source = text or ""
    candidates = []
    for match in anchor_first_pattern.finditer(source):
        anchor_text, number_text, magnitude_word = match.group(1), match.group(2), match.group(3)
        candidates.append((match, anchor_text, number_text, magnitude_word))
    for match in number_first_pattern.finditer(source):
        number_text, magnitude_word, anchor_text = match.group(1), match.group(2), match.group(3)
        candidates.append((match, anchor_text, number_text, magnitude_word))

    if not candidates:
        return None, {"status": "not_found"}

    scaled = [_scaled_count(number_text, magnitude_word) for _, _, number_text, magnitude_word in candidates]
    if None in scaled:
        first_unparseable = next(
            (match for (match, *_), value in zip(candidates, scaled) if value is None)
        )
        return None, {"status": "unparseable_number", "matched_text": first_unparseable.group(0).strip()}

    distinct_values = sorted(set(scaled))
    if len(distinct_values) > 1:
        return None, {"status": "ambiguous_multiple_values", "candidates": distinct_values}

    match, anchor_text, _, _ = candidates[0]
    value = scaled[0]
    return round(value, 4), {
        "status": "matched",
        "matched_phrase": anchor_text.strip(),
        "matched_text": match.group(0).strip(),
    }


def extract_monthly_active_users(text):
    """Monthly active users (MAU), including Meta's "monthly active people" / "MAP" terminology,
    from one earnings-release exhibit's plain text.

    Returns ``(value, detail)``. ``value`` is a float in millions (3070.0 for "3.07 billion",
    450.0 for "450 million"), rounded to 4 places, or ``None`` with a ``detail["status"]`` reason
    -- ``"not_found"``, ``"ambiguous_multiple_values"`` (more than one distinct candidate count),
    or ``"unparseable_number"``.
    """
    return _extract_user_count(text, _MAU_ANCHOR_FIRST, _MAU_NUMBER_FIRST)


def extract_daily_active_users(text):
    """Daily active users (DAU), including Meta's "daily active people" / "DAP" terminology, from
    one earnings-release exhibit's plain text.

    Same return shape as ``extract_monthly_active_users``: ``(value, detail)``, ``value`` a float
    in millions or ``None`` with a ``detail["status"]`` reason.
    """
    return _extract_user_count(text, _DAU_ANCHOR_FIRST, _DAU_NUMBER_FIRST)
