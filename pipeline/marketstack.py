"""Thin Marketstack (apilayer) client for premarket/intraday price data.

The access key is read only from the environment (MARKETSTACK_API_KEY, or the
ignored .env.local file) and is never included in cache keys, logs, or published
JSON. One request always carries every requested symbol comma-joined - Marketstack
bills per request regardless of how many symbols or rows it returns (up to the
`limit` cap), so batching the whole top-100 list into a single call is what keeps a
daily collection run affordable on a 100-calls/month plan.
"""

import os

import requests

from alpha_vantage import load_local_env

BASE_URL = "https://api.marketstack.com/v2"
MAX_SYMBOLS_PER_REQUEST = 100
REQUEST_TIMEOUT = 30


class MarketstackError(RuntimeError):
    pass


class MarketstackPlanRestricted(MarketstackError):
    """Raised on HTTP 403 function_access_restricted: the endpoint isn't on this plan.

    Marketstack's free tier commonly includes end-of-day data but not intraday/real-time
    endpoints. Callers should catch this specifically and fall back rather than treating
    it the same as a transient failure.
    """


class MarketstackClient:
    def __init__(self, api_key=None):
        load_local_env()
        self.api_key = api_key or os.getenv("MARKETSTACK_API_KEY")
        if not self.api_key:
            raise MarketstackError("MARKETSTACK_API_KEY is not configured")

    def _get(self, path, **params):
        response = requests.get(
            f"{BASE_URL}/{path}",
            params={**{key: value for key, value in params.items() if value is not None},
                    "access_key": self.api_key},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            payload = response.json() if response.content else {}
            code = (payload.get("error") or {}).get("code")
            if code == "function_access_restricted":
                raise MarketstackPlanRestricted(
                    f"{path} is not available on this Marketstack plan")
        if response.status_code != 200:
            raise MarketstackError(f"Marketstack {path} request failed with HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload.get("data"), list):
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            raise MarketstackError(message or f"Marketstack {path} returned an invalid response")
        return payload["data"]

    def eod_latest(self, symbols):
        """The most recent published end-of-day bar for each symbol, one request total."""
        return self._batched(symbols, lambda batch: self._get(
            "eod/latest", symbols=",".join(batch), limit=len(batch)))

    def intraday(self, symbols, interval="1min"):
        """Live/delayed intraday bars, one request total. Raises MarketstackPlanRestricted
        on a free plan without intraday access - callers should fall back to eod_latest."""
        return self._batched(symbols, lambda batch: self._get(
            "intraday", symbols=",".join(batch), interval=interval, limit=len(batch)))

    def _batched(self, symbols, fetch):
        """Marketstack caps a single response at 1000 rows; chunk only if the symbol
        list itself exceeds what one request's `limit` can return, one row per symbol."""
        cleaned = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
        rows = []
        for start in range(0, len(cleaned), MAX_SYMBOLS_PER_REQUEST):
            rows.extend(fetch(cleaned[start:start + MAX_SYMBOLS_PER_REQUEST]))
        return rows
