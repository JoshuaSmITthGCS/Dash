import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation import trading_calendar
from validation.trading_calendar import TradingCalendarUnavailable


def _source(dates):
    """Write a minimal SPY.json-shaped payload and return its path."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"price_series": {"fund": [{"date": date} for date in dates]}}, handle)
    handle.close()
    return handle.name


class SessionSeriesTests(unittest.TestCase):
    def test_committed_series_supplies_a_long_real_session_history(self):
        sessions = trading_calendar.sessions()
        self.assertGreater(len(sessions), 8000)
        self.assertEqual(sessions, tuple(sorted(sessions)))
        self.assertEqual(len(set(sessions)), len(sessions))

    def test_weekends_are_absent_from_the_series(self):
        from datetime import date
        sessions = trading_calendar.sessions()
        weekend = [day for day in sessions[-500:]
                   if date.fromisoformat(day).weekday() >= 5]
        self.assertEqual(weekend, [])

    def test_a_missing_source_reports_unavailable_rather_than_degrading(self):
        """Silently falling back to calendar days is the defect this module removes."""
        with self.assertRaises(TradingCalendarUnavailable):
            trading_calendar.sessions("/nonexistent/spy.json")
        self.assertFalse(trading_calendar.is_available("/nonexistent/spy.json"))

    def test_a_too_short_series_is_rejected(self):
        path = _source([f"2024-01-{day:02d}" for day in range(1, 29)])
        try:
            with self.assertRaises(TradingCalendarUnavailable):
                trading_calendar.sessions(path)
        finally:
            os.unlink(path)


class AdvanceTests(unittest.TestCase):
    def test_advance_counts_sessions_not_days(self):
        self.assertEqual(trading_calendar.advance("2024-01-02", 1), "2024-01-03")
        # 2024-01-06/07 is a weekend, so five sessions from the 2nd lands on the 9th.
        self.assertEqual(trading_calendar.advance("2024-01-02", 5), "2024-01-09")

    def test_advance_from_a_non_session_starts_at_the_next_session(self):
        # 2024-01-06 is a Saturday; the next session is Monday the 8th.
        self.assertEqual(trading_calendar.advance("2024-01-06", 0), "2024-01-08")

    def test_advance_past_the_end_of_the_calendar_returns_none(self):
        last = trading_calendar.sessions()[-1]
        self.assertIsNone(trading_calendar.advance(last, 1))

    def test_zero_sessions_is_the_next_session_on_or_after_the_date(self):
        self.assertEqual(trading_calendar.advance("2024-01-02", 0), "2024-01-02")


class SpanTests(unittest.TestCase):
    def test_sessions_between_is_exclusive_of_start_and_inclusive_of_end(self):
        self.assertEqual(trading_calendar.sessions_between("2024-01-02", "2024-01-02"), 0)
        self.assertEqual(trading_calendar.sessions_between("2024-01-02", "2024-01-03"), 1)

    def test_advance_and_sessions_between_are_inverses(self):
        for start in ("2015-02-17", "2019-11-01", "2022-07-05", "2024-03-15"):
            for count in (21, 63, 126, 252):
                with self.subTest(start=start, count=count):
                    end = trading_calendar.advance(start, count)
                    self.assertEqual(trading_calendar.sessions_between(start, end), count)

    def test_median_calendar_span_matches_the_old_calendar_day_horizons(self):
        """Why the bug was invisible: the medians are exactly the old constants."""
        self.assertEqual(trading_calendar.calendar_days_for_sessions(21), 30)
        self.assertEqual(trading_calendar.calendar_days_for_sessions(63), 91)
        self.assertEqual(trading_calendar.calendar_days_for_sessions(126), 182)
        self.assertEqual(trading_calendar.calendar_days_for_sessions(252), 365)

    def test_a_fixed_calendar_day_horizon_spans_a_varying_number_of_sessions(self):
        """And why it mattered: the same 91 days is not always 63 sessions."""
        from datetime import date, timedelta
        spans = set()
        for start in ("2022-01-03", "2022-06-01", "2023-03-01", "2023-11-01", "2024-09-03"):
            end = (date.fromisoformat(start) + timedelta(days=91)).isoformat()
            spans.add(trading_calendar.sessions_between(start, end))
        self.assertGreater(len(spans), 1, "expected calendar-day horizons to drift in sessions")


if __name__ == "__main__":
    unittest.main()
