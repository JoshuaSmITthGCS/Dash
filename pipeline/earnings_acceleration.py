"""Earnings/revenue growth acceleration (the second derivative) off the EDGAR PIT store.

docs/PRE-BREAKOUT-SCREEN-RESEARCH.md cites He & Narayanamoorthy, "Earnings Acceleration and
Stock Returns" (JAE 2020): acceleration is the *change in earnings growth* -- the second
derivative of earnings, not the first. Nothing in this codebase computed that before this
module; edgar_sue.py computes the first derivative already (the seasonal difference
d_t = x_t - x_{t-4} that its SUE construct standardizes), so acceleration here is built by
differencing that same series one step further: accel_t = d_t - d_{t-1}.

Reuses edgar_sue.quarterly_series/seasonal_differences rather than re-deriving PIT-correct
quarterly facts or the year-over-year matching logic. Both already resolve strictly on data
filed on or before ``as_of`` and match seasonal pairs by period-end proximity rather than by
list position, so a gap in the filing history drops the pair it breaks instead of silently
comparing the wrong seasons -- that guarantee is inherited unchanged here.

One additional guard this module adds on top of ``seasonal_differences``: the two seasonal
differences used for the second derivative (d_t and d_{t-1}) must themselves be consecutive
fiscal quarters, not merely the last two entries in the list. A firm missing one quarter's
year-ago match (dropped by ``seasonal_differences``) could otherwise have its two surviving
differences silently compared across a skipped quarter, understating or fabricating an
acceleration reading. See ``_consecutive`` below.

Dated by the later ``filed`` date of the two seasonal differences it combines -- the same
"later of its two components" convention ``quarterly_series`` already uses for a derived Q4
value -- so a caller filtering on ``as_of`` never sees an acceleration figure before both of
its inputs were actually knowable.
"""

from __future__ import annotations

import math
from datetime import date

import edgar_sue

# A "next" seasonal difference must sit within one ordinary quarter of the prior one to be
# treated as consecutive. Reuses edgar_sue's own quarter-length band rather than declaring a
# second, possibly-drifting one.
CONSECUTIVE_DAYS = edgar_sue.QUARTER_DAYS


def _days_between(start, end):
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
    except ValueError:
        return None


def _consecutive(prior_period_end, latest_period_end):
    days = _days_between(prior_period_end, latest_period_end)
    return days is not None and CONSECUTIVE_DAYS[0] <= days <= CONSECUTIVE_DAYS[1]


def acceleration_from_series(series, concept):
    """The second derivative from an already-fetched ``quarterly_series`` result, or None.

    ``acceleration`` is standardized by the firm's own trailing history of seasonal
    differences -- the same standard deviation ``edgar_sue._sue_from_series`` scales SUE by
    -- rather than published as a raw dollar figure. Net income and revenue are absolute
    dollar levels, so an unscaled second derivative would rank almost entirely on company
    size (a mega-cap's $800M swing dwarfing a small-cap's $50M one) rather than on
    acceleration intensity, defeating the point of standardizing it cross-sectionally
    afterward. Scaling by each firm's own history keeps the construction consistent with how
    every other seasonal-difference-based figure in this codebase (SUE) is already made
    comparable across the cross-section. ``raw_acceleration`` and ``scale`` are published
    alongside so the standardized figure is verifiable from the output rather than asserted.

    Split from ``acceleration_for`` so a caller that already has the series (the swing
    screen's own PEAD leg fetches ``quarterly_series`` once and reuses it) never pays for a
    second store read, and so this is directly unit-testable on a hand-built series.
    """
    differences = edgar_sue.seasonal_differences(series)
    if len(differences) < 2:
        return None
    (prior_end, prior_filed, prior_diff), (latest_end, latest_filed, latest_diff) = differences[-2:]
    if not _consecutive(prior_end, latest_end):
        return None
    raw_accel = latest_diff - prior_diff
    if not math.isfinite(raw_accel):
        return None
    # The scale is estimated from history strictly before the two seasonal differences the
    # acceleration itself is built from, so the figure being standardized never contributes
    # to its own scale.
    history = [difference for _pe, _f, difference in
              differences[:-2][-edgar_sue.SUE_TARGET_HISTORY:]]
    scale = None
    if len(history) >= edgar_sue.SUE_MIN_HISTORY:
        mean_diff = sum(history) / len(history)
        variance = sum((value - mean_diff) ** 2 for value in history) / (len(history) - 1)
        scale = math.sqrt(variance) if variance and math.isfinite(variance) else None
    if not scale or not math.isfinite(scale):
        return None
    standardized = raw_accel / scale
    if not math.isfinite(standardized):
        return None
    derived_quarters = sum(1 for quarter in series if quarter.get("derived"))
    return {
        "acceleration": standardized,
        "raw_acceleration": raw_accel,
        "scale": scale,
        "concept": concept,
        "period_end": latest_end,
        "filed": max(prior_filed, latest_filed),
        "seasonal_difference_latest": latest_diff,
        "seasonal_difference_prior": prior_diff,
        "derived_quarters": derived_quarters,
    }


def acceleration_for(symbol, as_of, *, cik=None, concept="net_income"):
    """Earnings (``concept="net_income"``) or revenue (``concept="revenue"``) acceleration
    for one ticker as of a date, or None.

    ``as_of``-correctness is inherited entirely from ``quarterly_series``: every quarter it
    returns was already filed on or before ``as_of``, so nothing here needs its own PIT
    filter -- the guarantee just has to not be broken by taking the wrong two entries, which
    is what ``_consecutive`` checks.
    """
    cik = cik or edgar_sue._ticker_to_cik().get(str(symbol).upper())
    if not cik:
        return None
    series = edgar_sue.quarterly_series(cik, concept, as_of)
    if not series:
        return None
    return acceleration_from_series(series, concept)
