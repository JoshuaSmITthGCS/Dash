"""Clients for Congressional (STOCK Act) trade disclosures.

SEC EDGAR does not carry this data - Form 3/4/5 there cover corporate insiders
(officers, directors, 10%+ owners; see insider_signal.py), not members of Congress.
Senators and representatives disclose under the STOCK Act to the Senate eFD and
House Clerk systems instead, which have no official free API.

Two clients, deliberately, because neither alone is dependable:

  * ``CongressTradesClient`` reads Financial Modeling Prep, which normalizes both chambers
    into one schema. The access key is read only from the environment (FMP_API_KEY, or the
    ignored .env.local file) and is never included in cache keys, logs, or published JSON.
    FMP answers these endpoints with HTTP 402 unless the key's plan covers them, which is a
    billing boundary no amount of retrying gets past.
  * ``StockWatcherClient`` reads the public house/senate stock-watcher datasets, which are
    scraped mirrors of the same Clerk and eFD filings, served as plain JSON with no key.
    Being a community mirror, it can lag or change shape without notice.

``build_congress_screen`` attempts every configured source independently and merges what
comes back, deduped on the disclosure identity, so one source being unavailable costs
coverage rather than the whole screen. Each source's outcome is reported separately - see
``source_errors`` and ``source_counts`` in the published payload.
"""

import json
import os
import urllib.request

import requests

from alpha_vantage import load_local_env

BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT = 30

HOUSE_DATASET = ("https://house-stock-watcher-data.s3-us-west-2.amazonaws.com"
                 "/data/all_transactions.json")
SENATE_DATASET = ("https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com"
                  "/aggregate/all_transactions.json")
# These files are the full history, not a recent window - tens of MB - so the read is
# streamed to a parsed list once per run and then filtered locally by the publish window.
DATASET_TIMEOUT = 120


class CongressTradesError(RuntimeError):
    pass


def _first(row, *names):
    """First present, non-blank value among several candidate field names.

    The two mirrors do not agree with each other or with FMP on what a column is called
    (``representative`` vs ``senator``, ``ticker`` vs ``symbol``, ``type`` vs
    ``transaction_type``), and a scraped dataset can rename one without warning. Reading
    defensively across the plausible spellings is the same approach ``price_history`` and
    ``marketstack`` already take, and it degrades to a missing field rather than to a row
    silently dropped on the floor.
    """
    for name in names:
        value = row.get(name)
        if value not in (None, "", "--", "N/A"):
            return value
    return None


def normalize_date(value):
    """An ISO ``YYYY-MM-DD`` date from the several formats these sources publish.

    The mirrors use US ``MM/DD/YYYY`` in some columns and ISO in others, sometimes within
    the same file. Everything downstream - the publish window, the late-filing flag, the
    price-history lookup - compares dates as strings, so a mixed format does not raise, it
    silently sorts and filters wrong.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    parts = text.split("/")
    if len(parts) == 3:
        month, day, year = (part.strip() for part in parts)
        if len(year) == 2:
            year = f"20{year}"
        if month.isdigit() and day.isdigit() and year.isdigit():
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


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
            "transaction_date": normalize_date(row.get("transactionDate")),
            "disclosure_date": normalize_date(row.get("disclosureDate")),
            "comment": row.get("comment"),
            "link": row.get("link"),
        }


class StockWatcherClient:
    """The public house/senate stock-watcher datasets - the same Clerk and eFD filings,
    scraped and republished as keyless JSON.

    No credential, so this is the source that keeps the screen populated when the FMP plan
    does not cover the Congressional endpoints. The cost of that is provenance: it is a
    community mirror, so it can lag the official systems, and its column names are not a
    contract. Every field is therefore read through ``_first`` across the spellings both
    datasets have used, and ``fetch`` reports how many rows it read against how many it could
    normalize, so a silent schema change shows up as a coverage number rather than as an
    empty screen that claims Congress did not trade.
    """

    def __init__(self, house_url=HOUSE_DATASET, senate_url=SENATE_DATASET, opener=None):
        self.house_url = house_url
        self.senate_url = senate_url
        self._opener = opener or self._read_json

    @staticmethod
    def _read_json(url):
        request = urllib.request.Request(url, headers={
            "User-Agent": "ValueSignal research (congressional disclosure mirror)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(request, timeout=DATASET_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _fetch(self, url, chamber):
        try:
            payload = self._opener(url)
        except Exception as exc:  # noqa: BLE001
            raise CongressTradesError(
                f"{chamber} disclosure dataset request failed ({type(exc).__name__}: {exc})") from exc
        if not isinstance(payload, list):
            raise CongressTradesError(f"{chamber} disclosure dataset returned an invalid response")
        rows = [self._normalize(row, chamber) for row in payload if isinstance(row, dict)]
        # A row with neither a traded symbol nor a disclosure date cannot be flagged, dated or
        # deduped, so it is dropped here rather than downstream where it would look like data.
        usable = [row for row in rows if row["disclosure_date"] and
                  (row["symbol"] or row["asset_description"])]
        return usable, len(payload)

    def house_latest(self):
        return self._fetch(self.house_url, "house")

    def senate_latest(self):
        return self._fetch(self.senate_url, "senate")

    @staticmethod
    def _normalize(row, chamber):
        """Both mirrors reduced to the same shape ``CongressTradesClient`` produces, so the
        classification layer never learns which source a disclosure came from."""
        symbol = _first(row, "ticker", "symbol")
        return {
            "chamber": chamber,
            "representative": _first(row, "representative", "senator", "office", "member_name"),
            "district": _first(row, "district", "state"),
            # The mirrors use "--" as their null ticker, which _first already filters; what
            # survives can still carry whitespace or lower case from the scrape.
            "symbol": str(symbol).strip().upper() if symbol else None,
            "asset_type": _first(row, "asset_type", "type_of_asset", "assetType"),
            "asset_description": _first(row, "asset_description", "assetDescription", "asset"),
            "owner": _first(row, "owner"),
            "transaction_type": _first(row, "type", "transaction_type"),
            "amount": _first(row, "amount"),
            "transaction_date": normalize_date(_first(row, "transaction_date", "transactionDate")),
            "disclosure_date": normalize_date(_first(row, "disclosure_date", "disclosureDate")),
            "comment": _first(row, "comment"),
            "link": _first(row, "ptr_link", "link"),
        }
