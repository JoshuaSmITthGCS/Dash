"""Reconciling filed share counts with the price series' split basis.

Anything that divides by market value -- earnings yield, book yield, free-cash-flow yield --
needs a share count and a price on the *same* split basis. They are not, and the mismatch is
silent, large, and in the direction that makes a stock look cheap.

Two facts about the inputs:

* **Filed share counts are as-reported.** A 10-Q filed 2020-07-31 reported Apple's diluted
  share count as 4,354,788,000. That was correct on the day it was filed.
* **The price series is on today's basis.** The cache stores Yahoo's ``Close``, to which
  splits have been applied retroactively -- Apple's August 2016 close reads $27.09 in the
  cache against roughly $108 as it actually traded. (An earlier note in this engagement
  called ``raw_closes`` the traded price. It is not: it is split-adjusted and merely
  dividend-unadjusted. That distinction is the reason this module exists.)

Multiplying one by the other gives Apple a $459bn market cap in July 2020 against the
$1.84tn it actually carried, and an earnings yield four times too high.

No external split feed is needed, because the store already contains the answer. ASC 260
requires share counts and per-share figures to be restated for splits in every period
presented, so **the same period filed twice across a split appears twice, and the ratio is
the split**::

    period 2020-03-29..2020-06-27  filed 2020-07-31   4,354,788,000
    period 2020-03-29..2020-06-27  filed 2021-07-28  17,419,154,000   ratio 4.0000

Comparing one period against itself is what makes this exact. Comparing *consecutive* periods
would fold buybacks into the ratio -- Apple's reads 3.79 rather than 4.00 across the same
split -- and no tolerance loose enough to accept that is tight enough to reject a secondary
offering.

Each such pair dates a basis change: it was not reflected in the earlier filing and was
reflected in the later one, so the first filing that shows it bounds the date from above.
Every period is then carried onto today's basis by the splits filed after its own newest
vintage.

Two deliberate refusals:

* **A step is only a split if it looks like one.** The ratio must land within half a percent
  of a simple fraction, up to 20:1 either way, or of a thousandfold units restatement. A
  company that genuinely issued a third more shares is not rescaled.
* **An unexplained step publishes nothing.** Where a period's value changes across vintages
  by more than a fifth and matches no split, that period yields no share count at all. A
  missing value costs one company a few rebalances; a wrong one is a fabricated twentyfold
  valuation error, and the brief's standing instruction is that absence is absence.

What this cannot see: a split more recent than every filing that would restate it. Such a
split is real in the price series and invisible in the filings for one quarter.
``unadjusted_tail_days`` reports how long that blind spot currently is per company rather
than leaving a reader to assume there is none.
"""

from datetime import date
from math import log10

# Below this, a change in a period's reported share count across vintages is a rounding
# change or an immaterial correction, and nothing is rescaled. The smallest split in common
# use is 5:4, so the threshold sits under it with room to spare.
MINIMUM_BASIS_STEP = 1.2

# How close a step must sit to a canonical ratio to be called a split. Comparing a period
# against itself leaves only reporting precision -- Amazon's 20:1 shows up as 19.9961 -- so
# this can be tight, and tight is what keeps a financing event from being mistaken for one.
BASIS_TOLERANCE = 0.005

# Ratios boards actually declare. Deliberately a list rather than every fraction with small
# terms: allowing any p/q up to 20:1 admits 19/5, which sits within a quarter of a percent of
# the 3.79 that Apple's *consecutive* quarters show across its 4:1 split, and within a
# percent of a 2.6x stock-funded acquisition. A dense candidate set matches everything and
# therefore recognises nothing. 20:1 covers Amazon and Alphabet; the inverses cover the
# reverse splits a company uses to stay above an exchange's minimum bid price.
_SPLIT_RATIOS = (1.25, 4 / 3, 1.5, 5 / 3, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0,
                 10.0, 12.0, 15.0, 20.0)

# Filers mis-tag a share count's scale often enough to matter: CenterPoint's 2010-08-04 10-Q
# reported 402 diluted shares where it meant 401,993,000, and corrected it a year later.
# These are *not* basis changes and must never propagate -- treating one as a split multiplies
# a decade of earlier periods by a million. They are per-period tagging errors, and they are
# repaired per period, against the magnitude the company reports everywhere else.
_UNIT_DECADES = (3, 6)

# How far, in log10, a value may sit from an exact thousandfold offset and still be called a
# scale error. Wide on purpose. A company's own share count drifts over fifteen years -- Alaska
# Air's ran from 36m to 123m across a 2:1 split, putting its 2010 figures half a decade below
# its own median -- so a tight window misses real mis-tags. Nothing legitimate lands in the
# gap: a units error is three decades out, and the largest split in use is 20:1, or 1.3.
_UNIT_MATCH_TOLERANCE = 1.0

# Two periods revealing the same split rarely name the same filing date, since each period is
# restated in whichever filing next presents it. Events this close together with a matching
# factor are one corporate action, not several.
_EVENT_MERGE_DAYS = 400

_PERIOD_TYPES = ("quarter", "nine_months", "annual")


CANONICAL_RATIOS = tuple(sorted(value for value in _SPLIT_RATIOS
                                if value >= MINIMUM_BASIS_STEP))


def canonical_split_ratio(ratio):
    """The split ``ratio`` represents, or None if it resembles no split in particular."""
    if not ratio or ratio <= 0:
        return None
    inverted = ratio < 1
    value = 1 / ratio if inverted else ratio
    if value < MINIMUM_BASIS_STEP:
        return None
    for candidate in CANONICAL_RATIOS:
        if abs(value / candidate - 1) <= BASIS_TOLERANCE:
            return 1 / candidate if inverted else candidate
    return None


def _days_between(earlier, later):
    try:
        return (date.fromisoformat(str(later)[:10]) - date.fromisoformat(str(earlier)[:10])).days
    except (TypeError, ValueError):
        return 0


def _usable(row, concept):
    return (row.get("concept") == concept and row.get("value")
            and row.get("period_end") and row.get("period_type") in _PERIOD_TYPES)


def repair_units(rows, *, concept="shares_diluted"):
    """Rows with scale mis-tags brought onto the magnitude the filer uses everywhere else.

    Returns ``(repaired, corrections)``. A value is only moved by an exact power of a
    thousand, and only when it sits that far from the company's own median magnitude, so a
    company that genuinely grew or shrank its share count is untouched. This runs before
    anything else, because a factor-of-a-million outlier otherwise looks exactly like a
    corporate action to the split detector -- and unlike a split, it must not propagate.
    """
    usable = [row for row in rows if _usable(row, concept)]
    if len(usable) < 3:
        return list(rows), []
    magnitudes = sorted(log10(abs(float(row["value"]))) for row in usable)
    median = magnitudes[len(magnitudes) // 2]

    repaired, corrections = [], []
    for row in rows:
        if not _usable(row, concept):
            repaired.append(row)
            continue
        offset = log10(abs(float(row["value"]))) - median
        decade = next((sign * decades
                       for decades in _UNIT_DECADES for sign in (1, -1)
                       if abs(offset - sign * decades) <= _UNIT_MATCH_TOLERANCE), None)
        if decade is None:
            repaired.append(row)
            continue
        repaired.append({**row, "value": float(row["value"]) / (10 ** decade)})
        corrections.append({"period_end": row["period_end"], "filed": str(row["filed"]),
                            "as_filed": float(row["value"]), "decades": decade})
    return repaired, corrections


def basis_events(observations, *, concept="shares_diluted"):
    """Every basis change a company's own restatements reveal.

    A change is dated by ``known_from``: the earliest filing whose value already reflects it.
    ``factor`` is the split; ``None`` marks a step this cannot explain, which disqualifies
    everything filed before it rather than guessing.
    """
    periods = {}
    for row in observations:
        if _usable(row, concept):
            periods.setdefault((row.get("period_start"), row["period_end"]), []).append(row)

    raw = []
    for vintages in periods.values():
        vintages.sort(key=lambda row: str(row["filed"]))
        for earlier, later in zip(vintages, vintages[1:]):
            step = float(later["value"]) / float(earlier["value"])
            if 1 / MINIMUM_BASIS_STEP <= step <= MINIMUM_BASIS_STEP:
                continue
            raw.append({"factor": canonical_split_ratio(step),
                        "step": round(step, 4),
                        "known_from": str(later["filed"]),
                        "after": str(earlier["filed"]),
                        "period_end": later["period_end"]})

    # One corporate action shows up once per period that straddles it. Collapse them so the
    # cumulative factor multiplies each split once.
    merged = []
    for event in sorted(raw, key=lambda entry: entry["known_from"]):
        match = next((entry for entry in merged
                      if entry["factor"] == event["factor"]
                      and _days_between(entry["known_from"], event["known_from"])
                      <= _EVENT_MERGE_DAYS), None)
        if match is None:
            merged.append({**event, "periods": [event["period_end"]]})
        else:
            match["periods"].append(event["period_end"])
            match["after"] = max(match["after"], event["after"])
    return merged


def current_basis_shares(observations, *, concept="shares_diluted"):
    """Share counts on the price series' split basis, one per period.

    Returns ``(rows, events)``. Each row carries ``shares`` on today's basis, or ``None``
    where an unexplained basis change sits between it and the present. ``events`` is the
    reconstruction's working, so it can be checked against a company's real history.
    """
    observations, unit_fixes = repair_units(observations, concept=concept)
    events = basis_events(observations, concept=concept)
    newest = {}
    for row in observations:
        if not _usable(row, concept):
            continue
        # Keyed by the whole period, not its end date: a filer reports a quarter and a
        # six-month cumulative ending on the same day, and collapsing them mixes a quarterly
        # weighted average with a half-year one.
        key = (row.get("period_start"), row["period_end"])
        filed, available = str(row["filed"]), str(row.get("available_at") or row["filed"])
        current = newest.get(key)
        if current is None or filed > current["filed"]:
            # The value and its units come from the newest vintage; the date the period
            # became knowable comes from the oldest, and must survive the replacement.
            earliest = min(available, current["available_at"]) if current else available
            newest[key] = {"period_end": row["period_end"], "period_type": row.get("period_type"),
                           "filed": filed, "value": float(row["value"]),
                           "available_at": earliest}
        elif available < current["available_at"]:
            current["available_at"] = available

    rows = []
    for entry in sorted(newest.values(), key=lambda item: item["period_end"]):
        factor, uncertain = 1.0, False
        for event in events:
            if event["known_from"] <= entry["filed"]:
                continue  # already reflected in the vintage this reads
            if event["factor"] is None:
                uncertain = True
            else:
                factor *= event["factor"]
        rows.append({
            "period_end": entry["period_end"],
            "period_type": entry["period_type"],
            "available_at": entry["available_at"],
            "as_reported": entry["value"],
            "shares": None if uncertain else entry["value"] * factor,
            "basis_factor": factor,
            "basis_uncertain": uncertain,
        })
    return rows, events + [{**fix, "recognised": "units_mis_tag"} for fix in unit_fixes]


def shares_as_of(rows, when, *, period_type="quarter"):
    """The newest share count disclosed on or before ``when``, on the price series' basis.

    ``None`` when nothing had been filed yet, or when the basis at that date could not be
    established. Both are absences, and neither is a zero.
    """
    cutoff = str(when)[:10]
    best = None
    for row in rows:
        if row["available_at"] > cutoff:
            continue
        if period_type and row["period_type"] != period_type:
            continue
        if best is None or row["period_end"] > best["period_end"]:
            best = row
    if best is None:
        return None
    return best["shares"]


def unadjusted_tail_days(rows, when):
    """Days between the newest filing readable at ``when`` and ``when`` itself.

    A split inside that window is in the price series and in no filing yet, so a market cap
    computed there is wrong by exactly the split. Reported rather than corrected, because
    nothing in this data can correct it.
    """
    cutoff = str(when)[:10]
    readable = [row["available_at"] for row in rows if row["available_at"] <= cutoff]
    return _days_between(max(readable), cutoff) if readable else None
