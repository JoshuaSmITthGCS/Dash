"""Small, cache-first Alpha Vantage client. The API key never enters logs or output files."""

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import requests

from common import HERE, LOG

BASE_URL = "https://www.alphavantage.co/query"
CACHE_DIR = os.path.join(HERE, "cache", "alpha_vantage")


class AlphaVantageError(RuntimeError):
    pass


def load_local_env():
    """Load the repository's ignored .env.local without adding a dependency."""
    path = os.path.abspath(os.path.join(HERE, "..", ".env.local"))
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class AlphaVantageClient:
    def __init__(self, api_key=None, cache_hours=20, min_interval=1.1):
        load_local_env()
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise AlphaVantageError("ALPHA_VANTAGE_API_KEY is not configured")
        self.cache_seconds = cache_hours * 3600
        self.min_interval = min_interval
        self._last_request_at = 0.0
        os.makedirs(CACHE_DIR, exist_ok=True)

    @staticmethod
    def _cache_key(params):
        public = {k: v for k, v in params.items() if k != "apikey"}
        digest = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()[:16]
        return f"{public.get('function', 'query').lower()}-{digest}.json"

    def query(self, function, *, cache_hours=None, **params):
        request_params = {"function": function, **params}
        cache_path = os.path.join(CACHE_DIR, self._cache_key(request_params))
        max_age = self.cache_seconds if cache_hours is None else cache_hours * 3600
        if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < max_age:
            with open(cache_path, encoding="utf-8") as handle:
                return json.load(handle)

        remaining = self.min_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)
        response = requests.get(
            BASE_URL,
            params={**request_params, "apikey": self.api_key},
            headers={"User-Agent": "ValueSignal/1.0 personal-research-dashboard"},
            timeout=30,
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        for key in ("Error Message", "Note", "Information"):
            if payload.get(key):
                raise AlphaVantageError(f"{function}: {payload[key]}")
        if not payload:
            raise AlphaVantageError(f"{function}: empty response")
        payload["_cached_at"] = datetime.now(timezone.utc).isoformat()
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return payload
