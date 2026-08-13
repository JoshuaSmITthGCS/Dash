"""Real trading-session calendar, derived from committed daily price history.

``ic_harness.py`` used to compute forward horizons with ``timedelta(days=horizon_days)``
against calendar dates and call the result "trading days" -- 63 trading days is not 63
calendar days once weekends and market holidays are accounted for (roughly 91 calendar days
per 63 sessions in a typical year), and the validation contract specifies session counts, not
calendar time.

This derives a session index from ``public/data/etf/SPY.json``'s ``price_series.fund`` leg --
8,437 real trading sessions, 1993-01-29 through the latest committed close -- the longest
daily history committed to this repository, rather than fabricating a calendar from weekday
arithmetic (which would silently count market holidays as open sessions).
"""

import os
from bisect import bisect_left, bisect_right
from datetime import date, datetime

from common import load_json

DEFAULT_SOURCE = os.path.join("etf", "SPY.json")
# ``etf/SPY.json`` is the longest history when it is committed, but it is an optional
# artifact. ``benchmark-report.json`` carries the same real SPY session dates and is
# always published, so it is the fallback rather than weekday arithmetic - a calendar
# guessed from weekdays would silently count market holidays as open sessions, which is
# the exact failure this module exists to prevent.
FALLBACK_SOURCES = ("benchmark-report.json",)


def _parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _session_dates(payload):
    """Session dates from either committed layout, or ``[]`` if neither is present."""
    series = payload.get("price_series") or {}
    rows = series.get("fund") or series.get("benchmark") or []
    if rows:
        return [row["date"] for row in rows if row.get("date")]
    history = (payload.get("histories") or {}).get("SPY") or {}
    return list(history.get("dates") or [])


def load_sessions(source=DEFAULT_SOURCE, *, loader=load_json, fallbacks=FALLBACK_SOURCES):
    """Sorted, deduplicated trading-session dates from a committed daily price series."""
    attempted = []
    for candidate in (source, *(fallbacks or ())):
        attempted.append(candidate)
        payload = loader(candidate)
        if not payload:
            continue
        sessions = sorted({_parse_date(value) for value in _session_dates(payload) if value})
        if sessions:
            return sessions
    raise FileNotFoundError(
        f"no committed daily price series among {attempted}; cannot derive a trading calendar")


class TradingCalendar:
    """Session-index arithmetic over a fixed, sorted list of trading dates."""

    def __init__(self, sessions):
        if not sessions:
            raise ValueError("a trading calendar needs at least one session")
        self.sessions = sessions

    def index_of(self, when):
        """Index of the session on or immediately after ``when``, or ``None`` if ``when``
        is after every session this calendar knows about (e.g. beyond the committed history's
        latest close).
        """
        target = _parse_date(when)
        position = bisect_left(self.sessions, target)
        return position if position < len(self.sessions) else None

    def is_session(self, when):
        """True when ``when`` is itself a trading session in this calendar."""
        target = _parse_date(when)
        position = bisect_left(self.sessions, target)
        return position < len(self.sessions) and self.sessions[position] == target

    def latest_session_on_or_before(self, when):
        """The most recent trading session at or before ``when``.

        This is the session a price tape fetched on ``when`` can actually reflect. Returns
        ``None`` before the calendar starts rather than extrapolating backwards.
        """
        position = bisect_right(self.sessions, _parse_date(when))
        return self.sessions[position - 1] if position else None

    def add_sessions(self, when, count):
        """The date ``count`` trading sessions after the session on/after ``when``.

        Returns ``None`` past the edge of the known calendar rather than extrapolating -
        a forward horizon that runs off the end of committed history is not yet observable,
        not zero.
        """
        start = self.index_of(when)
        if start is None:
            return None
        target_index = start + count
        if target_index >= len(self.sessions):
            return None
        return self.sessions[target_index]


_CACHE = {}


def default_calendar(source=DEFAULT_SOURCE):
    """Process-lifetime cache: the committed SPY history does not change within one run."""
    if source not in _CACHE:
        _CACHE[source] = TradingCalendar(load_sessions(source))
    return _CACHE[source]
