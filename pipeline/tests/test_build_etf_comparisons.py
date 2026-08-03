import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

import cache as cache_module
from build_etf_comparisons import _fetch_rows


class FakeTicker:
    def __init__(self, frame, error=None):
        self._frame = frame
        self._error = error
        self.calls = 0

    def history(self, **kwargs):
        self.calls += 1
        if self._error:
            raise self._error
        return self._frame


class FakeYf:
    def __init__(self, tickers):
        self._tickers = tickers

    def Ticker(self, symbol):  # noqa: N802 - matches yfinance's API
        return self._tickers[symbol]


def _frame(dates, closes):
    return pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates))


class FetchRowsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="etf-cache-test-")
        self.cache = cache_module.DiskCache(root=self.directory, ttls={"default": 3600})
        cache_module.reset_limiters()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        cache_module.reset_limiters()

    def test_a_successful_fetch_is_only_requested_from_yahoo_once(self):
        ticker = FakeTicker(_frame(["2026-01-02", "2026-01-05"], [100.0, 101.0]))
        yf = FakeYf({"VTI": ticker})

        first = _fetch_rows("VTI", yf, "max", self.cache)
        second = _fetch_rows("VTI", yf, "max", self.cache)

        self.assertEqual(ticker.calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(first[0]["adjusted_close"], 100.0)

    @patch("cache.time.sleep")
    def test_a_rate_limit_error_falls_back_to_the_last_cached_history(self, _sleep):
        good = FakeTicker(_frame(["2026-01-02"], [50.0]))
        cached = _fetch_rows("SPY", FakeYf({"SPY": good}), "max", self.cache)
        self.assertEqual(len(cached), 1)

        class YFRateLimitError(Exception):
            pass

        broken = FakeTicker(None, error=YFRateLimitError("rate limited"))
        # Force a miss so the producer actually runs and hits the fake error.
        self.cache.ttls["default"] = 0
        result = _fetch_rows("SPY", FakeYf({"SPY": broken}), "max", self.cache)

        self.assertEqual(result, cached)

    @patch("cache.time.sleep")
    def test_a_hard_failure_with_no_cached_copy_propagates(self, _sleep):
        class YFRateLimitError(Exception):
            pass

        broken = FakeTicker(None, error=YFRateLimitError("rate limited"))
        with self.assertRaises(YFRateLimitError):
            _fetch_rows("NEWFUND", FakeYf({"NEWFUND": broken}), "max", self.cache)


if __name__ == "__main__":
    unittest.main()
