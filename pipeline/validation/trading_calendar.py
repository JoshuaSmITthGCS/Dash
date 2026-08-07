"""A real NYSE trading-session calendar, read from committed price history.

``docs/RESEARCH-CONTRACT.md`` specifies the primary forecast target as a **63-trading-day**
forward return. The IC harness measured calendar days instead (91 days for "3M"), which is a
different horizon: 63 sessions is about 91 calendar days *on average*, but the mapping drifts
with holidays and long weekends, and the error is not symmetric across the year. A label that
is sometimes 60 sessions and sometimes 66 is not the label the contract preregisters.

Rather than approximating sessions as ``weekdays minus a guessed holiday count``, this reads
the actual session dates out of ``public/data/etf/SPY.json`` -- 8,437 observed NYSE sessions
from 1993 to the present, already committed for the ETF comparison feature. Every date in that
series is a day the exchange actually traded, which is exactly the definition needed, and it
costs no new dependency and no network call.

If the series is unavailable the calendar reports itself unavailable rather than silently
falling back to calendar days: a horizon that quietly changes meaning is the defect this
module exists to fix.
"""

import json
import os
from bisect import bisect_left, bisect_right
from functools import lru_cache

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(PIPELINE_DIR)
DEFAULT_SESSION_SOURCE = os.path.join(REPO_DIR, "public", "data", "etf", "SPY.json")

# Enough history that a 252-session horizon is measurable from any plausible snapshot date.
MINIMUM_USABLE_SESSIONS = 300


class TradingCalendarUnavailable(RuntimeError):
    """Raised instead of degrading to calendar days when no session series can be loaded."""


def _extract_dates(payload):
    series = (payload.get("price_series") or {}).get("fund") or []
    dates = sorted({str(row.get("date"))[:10] for row in series if row.get("date")})
    return [date for date in dates if len(date) == 10]


@lru_cache(maxsize=4)
def sessions(source=DEFAULT_SESSION_SOURCE):
    """Sorted ISO dates on which the exchange traded."""
    if not os.path.exists(source):
        raise TradingCalendarUnavailable(f"no session source at {source}")
    with open(source) as handle:
        dates = _extract_dates(json.load(handle))
    if len(dates) < MINIMUM_USABLE_SESSIONS:
        raise TradingCalendarUnavailable(
            f"{source} has {len(dates)} sessions, need at least {MINIMUM_USABLE_SESSIONS}")
    return tuple(dates)


def is_available(source=DEFAULT_SESSION_SOURCE):
    try:
        sessions(source)
    except TradingCalendarUnavailable:
        return False
    return True


def _index_on_or_after(dates, date):
    return bisect_left(dates, date[:10])


def advance(date, session_count, source=DEFAULT_SESSION_SOURCE):
    """The date ``session_count`` trading sessions after ``date``.

    ``date`` need not itself be a session -- a snapshot recorded on a Saturday advances from
    the next session. Returns None when the calendar does not extend far enough, which is the
    correct answer for a forward window that has not finished yet.
    """
    dates = sessions(source)
    start = _index_on_or_after(dates, date)
    target = start + session_count
    return dates[target] if 0 <= target < len(dates) else None


def sessions_between(start, end, source=DEFAULT_SESSION_SOURCE):
    """Number of trading sessions in ``(start, end]``."""
    dates = sessions(source)
    return bisect_right(dates, end[:10]) - bisect_right(dates, start[:10])


def calendar_days_for_sessions(session_count, source=DEFAULT_SESSION_SOURCE):
    """Median calendar-day span of ``session_count`` sessions -- diagnostic only.

    Published so the size of the correction is visible: this is what the harness *was*
    approximating when it used a fixed calendar-day horizon.
    """
    from datetime import date as date_type

    dates = sessions(source)
    if session_count <= 0 or len(dates) <= session_count:
        return None
    spans = []
    for index in range(len(dates) - session_count):
        start = date_type.fromisoformat(dates[index])
        end = date_type.fromisoformat(dates[index + session_count])
        spans.append((end - start).days)
    spans.sort()
    return spans[len(spans) // 2]
