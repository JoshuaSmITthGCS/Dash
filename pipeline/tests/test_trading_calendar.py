import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation.trading_calendar import TradingCalendar, load_sessions


def _synthetic_sessions(start, end, holidays):
    """Every weekday between start and end, minus a handful of holidays -- a realistic
    stand-in for "63 trading sessions" spanning more than 63 calendar days.
    """
    sessions = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


class TradingCalendarTests(unittest.TestCase):
    def setUp(self):
        self.holidays = {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
                         date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
                         date(2026, 7, 3), date(2026, 9, 7), date(2026, 10, 12),
                         date(2026, 11, 11), date(2026, 11, 26), date(2026, 12, 25)}
        self.sessions = _synthetic_sessions(date(2026, 1, 1), date(2026, 12, 31), self.holidays)
        self.calendar = TradingCalendar(self.sessions)

    def test_63_sessions_do_not_equal_91_calendar_days(self):
        start = date(2026, 1, 5)
        session_target = self.calendar.add_sessions(start, 63)
        calendar_day_target = start + timedelta(days=91)
        # A naive "add 91 calendar days" stand-in for "63 trading days" is exactly the bug
        # this module fixes: weekends and holidays inside the window push the real session
        # target later than that fixed-day approximation.
        self.assertNotEqual(session_target, calendar_day_target)
        self.assertGreater(session_target, calendar_day_target)

    def test_a_holiday_is_never_returned_as_a_session_target(self):
        # Choose a start where the naive +N-weekday count would land on Presidents' Day.
        target = self.calendar.add_sessions(date(2026, 2, 2), 10)
        self.assertNotIn(target, self.holidays)

    def test_index_of_a_weekend_start_rolls_forward_to_the_next_session(self):
        saturday = date(2026, 1, 3)
        index = self.calendar.index_of(saturday)
        self.assertEqual(self.calendar.sessions[index], date(2026, 1, 5))

    def test_horizon_running_off_the_end_of_history_returns_none_not_an_extrapolation(self):
        result = self.calendar.add_sessions(date(2026, 12, 30), 10)
        self.assertIsNone(result)

    def test_empty_calendar_is_rejected(self):
        with self.assertRaises(ValueError):
            TradingCalendar([])


class LoadSessionsFromCommittedDataTests(unittest.TestCase):
    def test_loads_the_committed_spy_history(self):
        sessions = load_sessions()
        self.assertGreater(len(sessions), 8000)
        self.assertEqual(sessions, sorted(sessions))
        self.assertEqual(len(sessions), len(set(sessions)))

    def test_missing_source_raises_rather_than_returning_an_empty_calendar(self):
        with self.assertRaises(FileNotFoundError):
            load_sessions("etf/DOES_NOT_EXIST.json", loader=lambda name: None)


if __name__ == "__main__":
    unittest.main()
