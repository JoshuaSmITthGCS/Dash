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
from bisect import bisect_left
from datetime import date, datetime

from common import load_json

DEFAULT_SOURCE = os.path.join("etf", "SPY.json")


def _parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def load_sessions(source=DEFAULT_SOURCE, *, loader=load_json):
    """Sorted, deduplicated trading-session dates from a committed daily price series."""
    payload = loader(source)
    if not payload:
        raise FileNotFoundError(f"{source} is not committed; cannot derive a trading calendar")
    series = payload.get("price_series") or {}
    rows = series.get("fund") or series.get("benchmark") or []
    sessions = sorted({_parse_date(row["date"]) for row in rows if row.get("date")})
    if not sessions:
        raise ValueError(f"{source} has no usable price_series dates")
    return sessions


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
