"""Cached Marketaux news client and provider-shape adapters.

The API token is read only from the environment (or the ignored .env.local file)
and is never included in cache keys, logs, or published JSON.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import requests

from alpha_vantage import load_local_env
from common import HERE

BASE_URL = "https://api.marketaux.com/v1/news/all"
CACHE_DIR = os.path.join(HERE, "cache", "marketaux")
MIN_PRIMARY_MATCH_SCORE = 25.0


class MarketauxError(RuntimeError):
    pass


class MarketauxClient:
    def __init__(self, api_key=None, cache_hours=4):
        load_local_env()
        self.api_key = api_key or os.getenv("MARKETAUX_API_TOKEN")
        if not self.api_key:
            raise MarketauxError("MARKETAUX_API_TOKEN is not configured")
        self.cache_seconds = cache_hours * 3600
        os.makedirs(CACHE_DIR, exist_ok=True)

    @staticmethod
    def _cache_key(params):
        public = {key: value for key, value in params.items() if key != "api_token"}
        digest = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()[:16]
        return f"news-{digest}.json"

    def news(self, *, cache_hours=None, **params):
        request_params = {key: value for key, value in params.items() if value is not None}
        cache_path = os.path.join(CACHE_DIR, self._cache_key(request_params))
        max_age = self.cache_seconds if cache_hours is None else cache_hours * 3600
        if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < max_age:
            with open(cache_path, encoding="utf-8") as handle:
                return json.load(handle)

        response = requests.get(
            BASE_URL,
            params={**request_params, "api_token": self.api_key},
            headers={"User-Agent": "ValueSignal/1.0 personal-research-dashboard"},
            timeout=30,
        )
        if response.status_code != 200:
            raise MarketauxError(f"Marketaux news request failed with HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload.get("data"), list):
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            raise MarketauxError(message or "Marketaux returned an invalid news response")

        payload["_cached_at"] = datetime.now(timezone.utc).isoformat()
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return payload


def advisor_articles_for_symbols(payload, symbols):
    """Convert articles whose strong primary entity is in the requested symbol set."""
    allowed = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    result = []
    for article in payload.get("data", []):
        entities = []
        for entity in article.get("entities", []):
            try:
                match_score = float(entity.get("match_score"))
            except (TypeError, ValueError):
                continue
            ticker = str(entity.get("symbol") or "").strip().upper()
            if ticker:
                entities.append((match_score, ticker, entity))
        if not entities:
            continue
        match_score, primary_ticker, primary_entity = max(entities, key=lambda item: item[0])
        if primary_ticker not in allowed or match_score < MIN_PRIMARY_MATCH_SCORE:
            continue
        matching = [primary_entity]
        scores = [
            float(entity["sentiment_score"]) for entity in matching
            if entity.get("sentiment_score") is not None
        ]
        if not matching:
            continue
        average = sum(scores) / len(scores) if scores else None
        result.append({
            "title": article.get("title"),
            "url": article.get("url"),
            "source": article.get("source"),
            "published_at": article.get("published_at"),
            "summary": article.get("description") or article.get("snippet"),
            "overall_sentiment_score": round(average, 3) if average is not None else None,
            "ticker": primary_ticker,
            "ticker_sentiment": [
                {
                    "ticker": primary_ticker,
                    "ticker_sentiment_score": entity.get("sentiment_score"),
                    "relevance_score": entity.get("match_score"),
                }
                for entity in matching
            ],
        })
    return result


def advisor_articles(payload, symbol):
    """Convert articles only when the requested symbol is the strong primary entity."""
    return advisor_articles_for_symbols(payload, (symbol,))
