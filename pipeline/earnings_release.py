"""Point-in-time earnings *release* datetimes, sourced independently of the 10-Q filing date.

The swing screen anchors its post-earnings-drift window on when the market learned the
number. Until now that anchor was the 10-Q/10-K filing date, which is the wrong date: a
periodic report lands days after the press release that carried the earnings. At a
2-to-10-session holding period a multi-day misdating is a large fraction of the window, and
it always errs the same way, reporting a window as younger than it is.

The independent source is Form 8-K Item 2.02, "Results of Operations and Financial
Condition", which is the filing a US issuer makes when it releases quarterly results. It is a
different filing from the 10-Q, arrives on the release day rather than weeks later, and
carries two usable timestamps:

  ``report_date``          the 8-K item date, which is the date of the release event
  ``acceptance_datetime``  when EDGAR accepted the filing, in US Eastern time

This module reads a local append-only store of those records and answers one question: for
this company and this fiscal period, when was the result released? It never falls back to a
filing date. A period with no resolvable release stays unresolved, and the caller drops the
row from the drift leg rather than scoring it on an anchor known to be wrong.

The store is built by pipeline/collect_earnings_releases.py, which crawls the EDGAR
submissions API. Nothing in this module fetches.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
PIT_DIR = os.path.join(HERE, "data", "pit")
RELEASES_PATH = os.path.join(PIT_DIR, "earnings_releases.jsonl")

ANNOUNCEMENT_ANCHOR = "earnings_release_datetime_8k_item_202"
ANNOUNCEMENT_ANCHOR_NOTE = (
    "Drift windows are anchored on the earnings release datetime taken from Form 8-K Item "
    "2.02, which is filed on the day results are released and is independent of the 10-Q or "
    "10-K filing date. A period with no resolvable release datetime is marked unresolved for "
    "the drift leg and is never anchored on a filing date instead.")

# How far after a fiscal period end an earnings release may legitimately sit. US issuers file
# the 8-K within days to weeks of period end; a Form 8-K Item 2.02 further out than this is
# reporting a different period, most often a delayed prior quarter or an annual result being
# restated. The band starts at 0 rather than 1 because a 52/53-week filer can date the release
# event on the period end itself.
RELEASE_MIN_LAG_DAYS = 0
RELEASE_MAX_LAG_DAYS = 120

# EDGAR acceptance timestamps are US Eastern with no offset in the payload. Earnings releases
# cluster before the open and after the close, so the offset matters for ordering a release
# against a trading session. Stored records carry an explicit offset; this is the fallback
# applied only to legacy rows written without one.
EASTERN_STANDARD_OFFSET = timezone(timedelta(hours=-5))


def _as_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_release_datetime(value):
    """An ISO release timestamp as an aware datetime, or None.

    Accepts a bare date (the 8-K item date with no time component), a naive datetime (an
    EDGAR acceptance stamp), and a fully offset-qualified timestamp. A naive value is read as
    US Eastern, which is what EDGAR publishes, never as UTC: reading a 16:05 Eastern
    after-close release as 16:05 UTC would move it to the morning of the same session and
    invert its position against that day's close.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=EASTERN_STANDARD_OFFSET)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        day = _as_date(text)
        if day is None:
            return None
        parsed = datetime(day.year, day.month, day.day)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=EASTERN_STANDARD_OFFSET)


def release_date(value):
    """The calendar date of a release timestamp, in its own local offset, or None."""
    parsed = parse_release_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _load_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


@lru_cache(maxsize=4)
def _releases_by_cik(path=RELEASES_PATH):
    """{cik: [record, ...]} ordered oldest release first.

    One record per (cik, accession). Where a company files more than one Item 2.02 8-K for a
    period - a preliminary release followed by a correction - the earliest wins, because the
    market repriced on the first one.
    """
    by_cik = {}
    seen = set()
    for row in _load_rows(path):
        cik = str(row.get("cik") or "").zfill(10)
        stamp = parse_release_datetime(row.get("release_datetime"))
        if not cik or cik == "0" * 10 or stamp is None:
            continue
        key = (cik, row.get("accession"))
        if key in seen and row.get("accession"):
            continue
        seen.add(key)
        by_cik.setdefault(cik, []).append({
            "cik": cik,
            "release_datetime": stamp.isoformat(),
            "release_date": stamp.date().isoformat(),
            "period_end": row.get("period_end"),
            "accession": row.get("accession"),
            "form": row.get("form"),
            "items": row.get("items"),
            # Carried through from the collector, which records whether the anchor came from
            # an EDGAR acceptance timestamp or only from the 8-K item date. Dropping it here
            # made every published row report no precision at all, which hides the difference
            # between a minute-accurate anchor and a date-only one.
            "precision": row.get("precision"),
            "source": row.get("source") or ANNOUNCEMENT_ANCHOR,
        })
    for records in by_cik.values():
        records.sort(key=lambda record: record["release_datetime"])
    return by_cik


def reset_cache():
    """Drop the parsed store. Tests that write a fixture store call this between cases."""
    _releases_by_cik.cache_clear()


def release_for_period(cik, period_end, as_of=None, *, path=RELEASES_PATH,
                       max_lag_days=RELEASE_MAX_LAG_DAYS, min_lag_days=RELEASE_MIN_LAG_DAYS):
    """The earliest Item 2.02 release that reports ``period_end``, or None.

    Two ways a record matches. It carries an explicit ``period_end`` equal to the one asked
    for, which is the reliable path and is what the collector writes whenever the 8-K states a
    period. Or its release date sits inside the lag band after ``period_end``, which is the
    fallback for the 8-Ks that name no period.

    ``as_of`` enforces point-in-time discipline: a release that had not happened yet on the
    scoring date is invisible, so a rerun of an old date cannot see a future announcement.
    """
    period = _as_date(period_end)
    if not period:
        return None
    records = _releases_by_cik(path).get(str(cik).zfill(10)) or []
    exact, windowed = [], []
    for record in records:
        if as_of and record["release_date"] > str(as_of)[:10]:
            continue
        if record.get("period_end") and _as_date(record["period_end"]) == period:
            exact.append(record)
            continue
        if record.get("period_end"):
            # It names a different period. Never let it date this one.
            continue
        released = _as_date(record["release_date"])
        lag = (released - period).days if released else None
        if lag is not None and min_lag_days <= lag <= max_lag_days:
            windowed.append(record)
    for candidates in (exact, windowed):
        if candidates:
            return candidates[0]
    return None


def coverage(ciks_and_periods, as_of=None, *, path=RELEASES_PATH):
    """Share of (cik, period_end) pairs that resolve to a release datetime.

    The diagnostic the re-anchoring owes its readers: moving the anchor off the filing date
    buys a correct window at the price of every period whose 8-K is not in the store, and that
    price has to be quoted rather than absorbed.
    """
    pairs = list(ciks_and_periods)
    resolved = sum(1 for cik, period_end in pairs
                   if release_for_period(cik, period_end, as_of, path=path))
    return {
        "periods_requested": len(pairs),
        "periods_resolved": resolved,
        "resolved_share": round(resolved / len(pairs), 4) if pairs else None,
        "source": ANNOUNCEMENT_ANCHOR,
        "store": os.path.relpath(path, os.path.dirname(HERE)),
    }
