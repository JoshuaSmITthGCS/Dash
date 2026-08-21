"""The Alpha Vantage client is cache-first and paces itself through the shared, per-provider
rate limiter every other provider uses -- not a second, hardcoded interval of its own."""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cache  # noqa: F401 -- ensures sys.modules["cache"] exists to patch, since
               # alpha_vantage.query() imports it locally rather than at module load time
from alpha_vantage import AlphaVantageClient, AlphaVantageError


class _CountingLimiter:
    def __init__(self):
        self.acquired = 0

    def acquire(self):
        self.acquired += 1
        return 0.0


def _ok_response(payload):
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value=payload)
    return response


class AlphaVantageClientTests(unittest.TestCase):
    def setUp(self):
        self.client = AlphaVantageClient(api_key="test-key")

    def tearDown(self):
        import alpha_vantage
        cache_dir = alpha_vantage.CACHE_DIR
        if os.path.isdir(cache_dir):
            for name in os.listdir(cache_dir):
                os.remove(os.path.join(cache_dir, name))

    @patch("alpha_vantage.requests.get")
    def test_query_paces_through_the_shared_alpha_vantage_limiter(self, get):
        # This client used to pace itself with a hardcoded 1.1s min_interval that ignored
        # the real 5-requests/minute free-tier limit entirely (cache.py's DEFAULT_RATE_LIMITS
        # declares 5/min but was never consulted here). It must now go through the same
        # limiter_for() token bucket every other provider uses.
        get.return_value = _ok_response({"Symbol": "AAPL"})
        limiter = _CountingLimiter()
        requested_providers = []
        with patch.object(sys.modules["cache"], "limiter_for",
                           lambda provider: requested_providers.append(provider) or limiter):
            self.client.query("OVERVIEW", symbol="AAPL")

        self.assertEqual(limiter.acquired, 1)
        self.assertEqual(requested_providers, ["alpha_vantage"])

    @patch("alpha_vantage.requests.get")
    def test_a_cache_hit_does_not_consume_a_rate_limit_slot(self, get):
        get.return_value = _ok_response({"Symbol": "AAPL"})
        limiter = _CountingLimiter()
        with patch.object(sys.modules["cache"], "limiter_for", lambda provider: limiter):
            self.client.query("OVERVIEW", symbol="AAPL")
            self.client.query("OVERVIEW", symbol="AAPL")

        self.assertEqual(limiter.acquired, 1)
        self.assertEqual(get.call_count, 1)

    @patch("alpha_vantage.requests.get")
    def test_a_rate_limit_note_raises_rather_than_caching_a_throttled_response(self, get):
        get.return_value = _ok_response({"Note": "Thank you for using Alpha Vantage! Our "
                                                    "standard API rate limit is 25 requests "
                                                    "per day."})
        with patch.object(sys.modules["cache"], "limiter_for", lambda provider: _CountingLimiter()):
            with self.assertRaisesRegex(AlphaVantageError, "rate limit"):
                self.client.query("OVERVIEW", symbol="AAPL")

        import alpha_vantage
        cache_path = os.path.join(alpha_vantage.CACHE_DIR,
                                  self.client._cache_key({"function": "OVERVIEW", "symbol": "AAPL"}))
        self.assertFalse(os.path.exists(cache_path))

    @patch("alpha_vantage.requests.get")
    def test_the_api_key_never_appears_in_a_raised_error(self, get):
        get.return_value = _ok_response({"Error Message": "invalid api call"})
        with patch.object(sys.modules["cache"], "limiter_for", lambda provider: _CountingLimiter()):
            with self.assertRaises(AlphaVantageError) as raised:
                self.client.query("OVERVIEW", symbol="AAPL")
        self.assertNotIn("test-key", str(raised.exception))
