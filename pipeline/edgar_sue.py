"""Standardized unexpected earnings (SUE) from the local SEC EDGAR point-in-time store.

The swing screen's highest-weighted leg is post-earnings-announcement drift, and until now
it resolved on 0% of the universe. The cause was not missing data: it was that the leg read
``earnings_surprise`` from the advisor snapshot, which comes from yfinance's ``earnings_dates``
scrape (fundamentals_extended.earnings_surprise_rows, whose own docstring records that this
"let this signal sit at zero coverage unnoticed"). That field is 0/839 populated. Meanwhile
pipeline/data/pit/fundamentals holds as-filed quarterly XBRL facts with real filing dates for
essentially the whole universe. This module builds the leg from that store instead.

Two deliberate departures from the field it replaces:

**The construct.** ``derive_earnings_surprise`` averages the last four quarters of *percent*
surprise, newest weighted heaviest, and cites Novy-Marx fundamental momentum. That is a
different signal at a different horizon. Bernard & Thomas drift is driven by the standardized
surprise of the *most recent* announcement, and percent surprise is unscaled - a one-cent beat
on a two-cent estimate reads +50%. Implemented here is the seasonal random walk with drift the
PEAD literature actually uses (Foster 1977; Foster, Olsen & Shevlin 1984; Bernard & Thomas
1989, 1990):

    d_t  = x_t - x_{t-4}                       seasonal difference
    SUE  = (d_t - mean(d_{t-1..t-k})) / sd(d_{t-1..t-k})

so the surprise is measured against the firm's own drift and scaled by the firm's own history
of forecast errors, which is what makes SUE comparable across the cross-section.

**The series.** ``net_income``, not EPS. As-filed EPS is not split-adjusted, so a split makes
x_t and x_{t-4} incomparable and injects one spurious enormous seasonal difference into both
the surprise and the scale that divides it. Net income is immune to splits, and carries ~46%
more rows in this store than eps_diluted. The standard-deviation normalization makes the level
of the series irrelevant, so nothing is given up by the choice. ``eps_diluted`` remains
available as a fallback basis and is labelled as such on every row that uses it, because the
split exposure is real on that path.

**Announcement dating.** For one (concept, period_start, period_end) the *earliest* filing
wins here, which is the opposite of edgar_enrichment's latest-filing-wins rule. That rule is
right for valuation - a restatement should become visible on its own filing date. It is wrong
for a surprise: the market reacted to the number as originally announced, on the day it was
originally announced. Comparatives republished in later filings are excluded by requiring the
originating filing to land within ANNOUNCEMENT_MAX_LAG_DAYS of the period end.

**The drift anchor** (amended 2026-08-12, spec amendment SA-2026-08-12-02). Drift windows are
anchored on the earnings *release* datetime from Form 8-K Item 2.02, read from the
point-in-time store earnings_release.py maintains. They are no longer anchored on the 10-Q or
10-K filing date. A periodic report lands days after the press release that carried the
number, so a filing-date anchor reports every window as younger than it is, and at a
2-to-10-session holding period a multi-day error is a large fraction of the window.

A period whose release datetime does not resolve is marked unresolved for the drift leg. The
filing date stays on the row as ``filed``, for provenance, and is never substituted for the
anchor. Trading a stale drift window because the anchor was quietly wrong is a worse outcome
than not trading the leg at all, and the coverage this costs is reported as its own
diagnostic rather than absorbed.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date
from functools import lru_cache

from earnings_release import (ANNOUNCEMENT_ANCHOR_NOTE as RELEASE_ANCHOR_NOTE,
                              RELEASES_PATH, release_for_period)
from pit_fundamentals_store import ShardedStore, shard_for

HERE = os.path.dirname(os.path.abspath(__file__))
PIT_DIR = os.path.join(HERE, "data", "pit")
FUNDAMENTALS_DIR = os.path.join(PIT_DIR, "fundamentals")
ENTITY_MAP = os.path.join(PIT_DIR, "entity_map.json")

# Period-length windows, in days, for classifying an XBRL duration fact. Fiscal calendars
# drift (52/53-week filers especially), so these are bands rather than exact lengths.
QUARTER_DAYS = (80, 100)
HALF_DAYS = (170, 195)
NINE_MONTH_DAYS = (260, 285)
YEAR_DAYS = (330, 400)
SEASON_DAYS = (330, 400)  # how far back the year-ago quarter is allowed to sit

# A filing this far past its own period end is an original report; anything later is a
# comparative republished inside a subsequent filing and must not date an announcement.
ANNOUNCEMENT_MAX_LAG_DAYS = 120

# Seasonal differences used to estimate the drift and the scale. Bernard & Thomas use a
# rolling window of this order; below the minimum the standard deviation is an opinion about
# three numbers and the row is dropped rather than scored on it.
SUE_TARGET_HISTORY = 8
SUE_MIN_HISTORY = 4

PRIMARY_BASIS = "net_income"
FALLBACK_BASIS = "eps_diluted"

ANNOUNCEMENT_ANCHOR = "earnings_release_datetime_8k_item_202"
ANNOUNCEMENT_ANCHOR_NOTE = RELEASE_ANCHOR_NOTE

# The anchor the leg used before spec amendment SA-2026-08-12-02, kept as a label so a row
# written under the old rule stays identifiable and so the migration diagnostic can name it.
SUPERSEDED_ANNOUNCEMENT_ANCHOR = "sec_filing_date"

# Status a row carries when its fiscal period has no resolvable release datetime. The PEAD
# leg drops these rows. It does not fall back to the filing date.
RELEASE_UNRESOLVED_STATUS = "RELEASE_DATE_UNRESOLVED"


def _days_between(start, end):
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
    except ValueError:
        return None


def _within(days, band):
    return days is not None and band[0] <= days <= band[1]


@lru_cache(maxsize=1)
def _ticker_to_cik():
    try:
        with open(ENTITY_MAP, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
            for row in payload.get("rows", [])
            if row.get("ticker") and row.get("cik_str") is not None}


# Keyed by (shard, concept), and the store is 100 shards over two concepts, so 128 is one
# bad day away from thrashing: a miss re-parses a whole shard, and a run that has to fall
# back to eps_diluted for most of the universe would need 200 live keys. Sized above that.
@lru_cache(maxsize=256)
def _shard_periods(shard, concept):
    """{cik: {(period_start, period_end): (filed, value, form)}}, earliest filing per period.

    Earliest rather than latest: see the module docstring. A restatement of a quarter does
    not move the date the market learned the number.
    """
    by_cik = {}
    for row in ShardedStore(FUNDAMENTALS_DIR).load_compact(shard):
        if row.get("concept") != concept:
            continue
        start, end, filed = row.get("period_start"), row.get("period_end"), row.get("filed")
        value = row.get("value")
        if not (start and end and filed) or value is None:
            continue
        periods = by_cik.setdefault(row.get("cik"), {})
        key = (start, end)
        prior = periods.get(key)
        if prior is None or filed < prior[0]:
            periods[key] = (filed, float(value), row.get("form"))
    return by_cik


def quarterly_series(cik, concept, as_of):
    """Discrete fiscal quarters visible on ``as_of``, oldest first.

    Returns ``[{period_end, filed, value, derived}]``. Quarters tagged directly as ~90-day
    durations are used as filed; the ones filers do not tag discretely - Q4 above all, which
    is reported only inside the fiscal year - are recovered by differencing the year-to-date
    chain that shares a fiscal-year start, the same construction edgar_enrichment's TTM path
    uses. A derived quarter is dated by the later of its two components, since both had to be
    public before the quarter was knowable.
    """
    periods = _shard_periods(shard_for(cik), concept).get(cik, {})
    visible = {key: value for key, value in periods.items() if value[0] <= as_of}

    quarters = {}   # period_end -> (filed, value, derived)
    chains = {}     # fiscal-year start -> {band name: (period_end, filed, value)}
    for (start, end), (filed, value, _form) in visible.items():
        length = _days_between(start, end)
        if _within(length, QUARTER_DAYS):
            prior = quarters.get(end)
            if prior is None or filed < prior[0]:
                quarters[end] = (filed, value, False)
            continue
        for name, band in (("h1", HALF_DAYS), ("m9", NINE_MONTH_DAYS), ("fy", YEAR_DAYS)):
            if _within(length, band):
                chain = chains.setdefault(start, {})
                prior = chain.get(name)
                if prior is None or filed < prior[1]:
                    chain[name] = (end, filed, value)

    # Difference the year-to-date chain for the quarters nobody tags discretely.
    for start, chain in chains.items():
        q1 = next(((end, filed, value) for (s, end), (filed, value, _f) in visible.items()
                   if s == start and _within(_days_between(s, end), QUARTER_DAYS)), None)
        steps = (("h1", q1), ("m9", chain.get("h1")), ("fy", chain.get("m9")))
        for name, previous in steps:
            current = chain.get(name)
            if current is None or previous is None:
                continue
            end, filed, value = current
            if end in quarters:
                continue
            quarters[end] = (max(filed, previous[1]), value - previous[2], True)

    return [{"period_end": end, "filed": filed, "value": value, "derived": derived}
            for end, (filed, value, derived) in sorted(quarters.items())]


def seasonal_differences(series):
    """[(period_end, filed, difference)] where a quarter ~one year earlier exists.

    Matched on period end rather than on position, so a gap in the series drops the pairs it
    breaks instead of silently comparing a quarter to the wrong season.

    Public because pre_breakout_signals/earnings_acceleration.py reuses this exact
    period-matched differencing to build the second derivative (earnings/revenue
    acceleration) on top of the same d_t = x_t - x_{t-4} series SUE is built from.
    """
    differences = []
    for index, quarter in enumerate(series):
        prior = next((candidate for candidate in reversed(series[:index])
                      if _within(_days_between(candidate["period_end"], quarter["period_end"]),
                                 SEASON_DAYS)), None)
        if prior is None:
            continue
        differences.append((quarter["period_end"], quarter["filed"],
                            quarter["value"] - prior["value"]))
    return differences


def _sue_from_series(series, basis):
    """SUE under the seasonal random walk **with drift**, and the pieces it was built from.

    The expectation model is not a bare year-over-year difference. Foster (The Accounting
    Review 1977) and Foster, Olsen & Shevlin (The Accounting Review 1984) specify

        E[x_t] = x_{t-4} + delta        delta estimated from the firm's own history
        SUE    = (x_t - E[x_t]) / sd(d_{t-1..t-k}),   d_i = x_i - x_{i-4}

    so the surprise is what the firm did beyond its own trend, and it is scaled by the
    standard deviation of that firm's history of seasonal differences. ``drift`` on the
    returned dict is delta, published so the with-drift form is verifiable from the output
    rather than asserted in a comment.

    Dropping delta would make a firm growing earnings steadily register a positive surprise
    every single quarter, which is a growth signal wearing a surprise's name. That failure
    mode is pinned by a test in pipeline/tests/test_edgar_sue.py.
    """
    differences = seasonal_differences(series)
    if len(differences) < SUE_MIN_HISTORY + 1:
        return None
    period_end, filed, latest = differences[-1]
    history = [difference for _pe, _f, difference in differences[-(SUE_TARGET_HISTORY + 1):-1]]
    if len(history) < SUE_MIN_HISTORY:
        return None
    drift = sum(history) / len(history)
    variance = sum((value - drift) ** 2 for value in history) / (len(history) - 1)
    scale = math.sqrt(variance)
    if not scale or not math.isfinite(scale):
        # A firm whose seasonal differences never move has no scale to standardize against;
        # dividing by ~0 would manufacture the largest surprise in the cross-section.
        return None
    value = (latest - drift) / scale
    if not math.isfinite(value):
        return None
    return {"sue": value, "basis": basis, "period_end": period_end, "filed": filed,
            "expectation_model": "seasonal_random_walk_with_drift",
            "drift": drift, "seasonal_difference": latest, "scale": scale,
            "history_quarters": len(history), "derived_quarters": sum(1 for q in series if q["derived"]),
            "announcement_anchor": ANNOUNCEMENT_ANCHOR}


def attach_release_anchor(result, as_of, *, cik, releases_path=RELEASES_PATH):
    """Stamp a SUE row with its earnings release datetime, or mark it unresolved.

    Spec amendment SA-2026-08-12-02. The release datetime comes from Form 8-K Item 2.02 by
    way of earnings_release.py, which is a different filing from the 10-Q that produced the
    number. When no release resolves, ``release_datetime`` stays None, ``anchor_status``
    says so, and the PEAD leg drops the row. The filing date remains on the row as provenance
    and is never promoted into the anchor.
    """
    release = release_for_period(cik, result.get("period_end"), as_of,
                                 path=releases_path)
    if not release:
        return {**result, "release_datetime": None, "release_date": None,
                "release_source": None, "release_precision": None,
                "anchor_status": RELEASE_UNRESOLVED_STATUS,
                "announcement_anchor": ANNOUNCEMENT_ANCHOR,
                "superseded_anchor": SUPERSEDED_ANNOUNCEMENT_ANCHOR}
    return {**result,
            "release_datetime": release["release_datetime"],
            "release_date": release["release_date"],
            "release_source": release.get("source"),
            "release_precision": release.get("precision"),
            "release_accession": release.get("accession"),
            "anchor_status": "RELEASE_DATE_RESOLVED",
            "announcement_anchor": ANNOUNCEMENT_ANCHOR,
            "superseded_anchor": SUPERSEDED_ANNOUNCEMENT_ANCHOR}


def sue_for(symbol, as_of, *, cik=None, releases_path=RELEASES_PATH):
    """Standardized unexpected earnings for one ticker as of a date, or None.

    Tries net income first and diluted EPS only if net income cannot produce a full history,
    so the split-exposed basis is a fallback rather than a silent equal partner. ``basis`` on
    the returned dict always says which one answered.

    Every returned row carries its release anchor, resolved or not. A row is still returned
    when the release datetime is missing, because the surprise itself is real and the caller
    needs to be able to count how many rows the anchor requirement costs.
    """
    cik = cik or _ticker_to_cik().get(str(symbol).upper())
    if not cik:
        return None
    for basis in (PRIMARY_BASIS, FALLBACK_BASIS):
        series = quarterly_series(cik, basis, as_of)
        result = _sue_from_series(series, basis) if series else None
        if result:
            return attach_release_anchor(result, as_of, cik=cik, releases_path=releases_path)
    return None


def announcement_age_trading_days(anchor, sessions):
    """Sessions elapsed since ``anchor``, counted on the name's own trading calendar.

    ``anchor`` is the earnings release datetime, so a release accepted after the close on a
    session does not count that session as drift: the comparison is on the calendar date of
    the release and sessions strictly after it. ``sessions`` is the cached date series for
    the ticker, so real trading days are counted rather than calendar days scaled by a
    factor, which keeps the window honest across holidays and across the gap between the last
    cached session and the run date.

    Returns None when the anchor is missing. The caller must treat that as unresolved rather
    than as a zero-age window.
    """
    if not anchor or not sessions:
        return None
    anchor_date = str(anchor)[:10]
    return sum(1 for session in sessions if session and str(session)[:10] > anchor_date)
