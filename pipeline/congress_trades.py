"""Financial Modeling Prep client for Congressional (STOCK Act) trade disclosures.

SEC EDGAR does not carry this data - Form 3/4/5 there cover corporate insiders
(officers, directors, 10%+ owners; see insider_signal.py), not members of Congress.
Senators and representatives disclose under the STOCK Act to the Senate eFD and
House Clerk systems instead, which have no official free API - FMP normalizes both
chambers into one schema. The access key is read only from the environment
(FMP_API_KEY, or the ignored .env.local file) and is never included in cache keys,
logs, or published JSON.
"""

import os

import requests

from alpha_vantage import load_local_env

BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT = 30


class CongressTradesError(RuntimeError):
    pass


class CongressTradesClient:
    def __init__(self, api_key=None):
        load_local_env()
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise CongressTradesError("FMP_API_KEY is not configured")

    def _get(self, path, **params):
        response = requests.get(
            f"{BASE_URL}/{path}",
            params={**{key: value for key, value in params.items() if value is not None},
                    "apikey": self.api_key},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise CongressTradesError(f"FMP {path} request failed with HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, list):
            message = payload.get("Error Message") if isinstance(payload, dict) else None
            raise CongressTradesError(message or f"FMP {path} returned an invalid response")
        return payload

    def senate_latest(self, page=0, limit=100):
        return [self._normalize(row, "senate") for row in self._get("senate-latest", page=page, limit=limit)]

    def house_latest(self, page=0, limit=100):
        return [self._normalize(row, "house") for row in self._get("house-latest", page=page, limit=limit)]

    def price_history(self, symbol, from_date=None, to_date=None):
        """Daily closes for a symbol since from_date, oldest first. Used to measure how
        a stock actually performed after a disclosed purchase - one call per distinct
        symbol, not per trade. Field name isn't independently confirmed against a live
        key from this environment (network access to financialmodelingprep.com is
        blocked here), so this reads whichever of close/price is present defensively,
        the same pattern as marketstack.py."""
        rows = self._get("historical-price-eod/light", symbol=symbol, **{"from": from_date, "to": to_date})
        points = []
        for row in rows:
            date = row.get("date")
            close = row.get("close")
            close = close if close is not None else row.get("price")
            if date and close is not None:
                try:
                    points.append({"date": str(date)[:10], "close": float(close)})
                except (TypeError, ValueError):
                    continue
        points.sort(key=lambda point: point["date"])
        return points

    @staticmethod
    def _normalize(row, chamber):
        """One shape for both chambers - FMP names a few fields differently between
        senate-latest and house-latest, so callers never need to branch on chamber."""
        name = row.get("office") or " ".join(
            part for part in (row.get("firstName"), row.get("lastName")) if part)
        return {
            "chamber": chamber,
            "representative": name,
            "district": row.get("district"),
            "symbol": row.get("symbol"),
            "asset_type": row.get("assetType"),
            "asset_description": row.get("assetDescription"),
            "owner": row.get("owner"),
            "transaction_type": row.get("type"),
            "amount": row.get("amount"),
            "transaction_date": row.get("transactionDate"),
            "disclosure_date": row.get("disclosureDate"),
            "comment": row.get("comment"),
            "link": row.get("link"),
        }
