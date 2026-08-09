"""Clients for Congressional (STOCK Act) trade disclosures.

SEC EDGAR does not carry this data - Form 3/4/5 there cover corporate insiders
(officers, directors, 10%+ owners; see insider_signal.py), not members of Congress.
Senators and representatives disclose under the STOCK Act to the Senate eFD and
House Clerk systems instead, which have no official free API.

Three clients, deliberately, because none alone is dependable:

  * ``CongressTradesClient`` reads Financial Modeling Prep, which normalizes both chambers
    into one schema. The access key is read only from the environment (FMP_API_KEY, or the
    ignored .env.local file) and is never included in cache keys, logs, or published JSON.
    FMP answers these endpoints with HTTP 402 unless the key's plan covers them, which is a
    billing boundary no amount of retrying gets past.
  * ``SenateEfdClient`` reads the Senate's own Electronic Financial Disclosure system - the
    authoritative source for one chamber, keyless, and the only free per-trade feed that
    cannot be withdrawn by a third party. It covers *electronically filed* periodic
    transaction reports; a senator who files on paper discloses a scanned PDF with no
    machine-readable transactions, which this counts and skips rather than guesses at.
  * ``StockWatcherClient`` reads the house/senate stock-watcher datasets. **Those buckets
    now answer every request with HTTP 403 AccessDenied** - the mirror was withdrawn, which
    is what left this screen publishing nothing at all. The client is kept because it is
    the only reachable source of *House* disclosures this pipeline has, and its endpoints
    are overridable (``CONGRESS_HOUSE_DATASET_URL`` / ``CONGRESS_SENATE_DATASET_URL``) so a
    replacement mirror is a configuration change rather than a code change.

``build_congress_screen`` attempts every configured source independently and merges what
comes back, deduped on the disclosure identity, so one source being unavailable costs
coverage rather than the whole screen. Each source's outcome is reported separately - see
``source_errors`` and ``source_counts`` in the published payload.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser

import requests

from alpha_vantage import load_local_env

BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT = 30

# Overridable because the defaults are dead: both buckets answer AccessDenied since the
# stock-watcher project stopped publishing. Pointing these at a live mirror needs no code.
HOUSE_DATASET = os.getenv("CONGRESS_HOUSE_DATASET_URL") or (
    "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json")
SENATE_DATASET = os.getenv("CONGRESS_SENATE_DATASET_URL") or (
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json")
# These files are the full history, not a recent window - tens of MB - so the read is
# streamed to a parsed list once per run and then filtered locally by the publish window.
DATASET_TIMEOUT = 120

EFD_ROOT = "https://efdsearch.senate.gov"
EFD_HOME = f"{EFD_ROOT}/search/home/"
EFD_SEARCH = f"{EFD_ROOT}/search/report/data/"
# eFD's own report-type code for a periodic transaction report - the STOCK Act filing that
# carries individual trades. Annual and candidate reports carry holdings, not transactions.
EFD_PTR_REPORT_TYPE = "11"
EFD_PAGE_SIZE = 100
# One request per report page, so this is the difference between a courteous read and a
# hammering one. eFD publishes no documented rate limit; this is deliberately slow.
EFD_REQUEST_DELAY = 0.5
EFD_MAX_REPORTS = 400
EFD_USER_AGENT = "ValueSignal research (STOCK Act disclosure reader)"


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


class _TableParser(HTMLParser):
    """Every HTML table on a page as a list of ``{header: cell}`` rows.

    Cells are keyed by their column's header text rather than by position: eFD's periodic
    transaction report varies its columns (an owner column appears for a joint account, a
    comment column only when there is one), and a positional read silently shifts ticker
    into asset-type the first time that happens. A header the page does not have simply
    yields no value, which the caller reads as a missing field.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._headers, self._row, self._cell = [], [], None
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._headers, self.tables = [], self.tables + [[]]
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell = True, []

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._row.append(" ".join("".join(self._cell).split()))
        elif tag == "tr":
            if not self.tables:
                self.tables.append([])
            if not self._headers:
                self._headers = [cell.lower() for cell in self._row]
            elif self._row:
                self.tables[-1].append(dict(zip(self._headers, self._row)))
            self._row = []


def _cell(row, *names, avoid=()):
    """A table cell by any of several header spellings: exact match first, then substring.

    eFD labels the same column "Ticker" in one report and "Ticker Symbol" in another, and
    "Transaction Type" is sometimes just "Type". Matching loosely across the spellings keeps
    a label change costing one field rather than the whole feed - but loosely enough that
    "type" also matches "asset type", which is a *different* column reading "Stock" where
    "Purchase" belongs. Exact-first settles that whenever both columns are present, and
    ``avoid`` settles it when only the wrong one is.
    """
    def usable(value):
        return value not in (None, "", "--", "N/A")

    for name in names:
        value = row.get(name)
        if usable(value):
            return value
    for name in names:
        for header, value in row.items():
            if name in header and not any(word in header for word in avoid) and usable(value):
                return value
    return None


class SenateEfdClient:
    """The Senate's own eFD search, which is authoritative rather than a mirror.

    Three steps, in this order, because eFD enforces them: fetch the search home page for a
    CSRF token and a session cookie, POST acceptance of the prohibition agreement (eFD
    refuses every search until that is on the session), then POST the report search itself,
    which answers JSON. Each hit links to a report page whose transaction table is fetched
    separately - one request per report, paced by ``request_delay``.

    Not verified against the live service from this repository (no network access to
    efdsearch.senate.gov exists where this was written), so every step is defensive and
    every failure surfaces as a ``CongressTradesError`` naming the step that failed, rather
    than as an empty result that reads like a quiet Congress. ``fetch`` reports how many
    reports it saw against how many it could read, so a shape change shows up as a coverage
    number in the published payload.
    """

    def __init__(self, session=None, request_delay=EFD_REQUEST_DELAY, max_reports=EFD_MAX_REPORTS):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": EFD_USER_AGENT})
        self.request_delay = request_delay
        self.max_reports = max_reports
        self._token = None

    @staticmethod
    def _csrf_token(html):
        match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html or "")
        return match.group(1) if match else None

    def _accept_agreement(self):
        """eFD's session gate. Every search before this returns the agreement page, not data."""
        if self._token:
            return self._token
        try:
            home = self.session.get(EFD_HOME, timeout=REQUEST_TIMEOUT)
            home.raise_for_status()
        except requests.RequestException as exc:
            raise CongressTradesError(
                f"senate eFD home page unreachable ({type(exc).__name__}: {exc})") from exc
        token = self._csrf_token(home.text)
        if not token:
            raise CongressTradesError("senate eFD home page carried no CSRF token - the "
                                      "search form's shape has changed")
        try:
            accepted = self.session.post(
                EFD_HOME,
                data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token},
                headers={"Referer": EFD_HOME}, timeout=REQUEST_TIMEOUT)
            accepted.raise_for_status()
        except requests.RequestException as exc:
            raise CongressTradesError(
                f"senate eFD agreement was refused ({type(exc).__name__}: {exc})") from exc
        # The token is rotated with the session the agreement established.
        self._token = self._csrf_token(accepted.text) or token
        return self._token

    def reports(self, since):
        """Periodic transaction reports filed on or after ``since``, newest first.

        ``since`` bounds the read at the source rather than locally: the publish window is
        months, eFD's history is years, and one page request per hundred reports is the
        difference between a courteous read and pulling the whole archive every week.
        """
        token = self._accept_agreement()
        found, start = [], 0
        while start < self.max_reports:
            payload = {
                "start": str(start), "length": str(EFD_PAGE_SIZE),
                "report_types": f"[{EFD_PTR_REPORT_TYPE}]", "filer_types": "[]",
                "submitted_start_date": f"{since.strftime('%m/%d/%Y')} 00:00:00",
                "submitted_end_date": "", "candidate_state": "", "senator_state": "",
                "office_id": "", "first_name": "", "last_name": "",
                "csrfmiddlewaretoken": token,
            }
            try:
                response = self.session.post(
                    EFD_SEARCH, data=payload,
                    headers={"Referer": EFD_HOME, "X-CSRFToken": token,
                             "X-Requested-With": "XMLHttpRequest"},
                    timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                rows = (response.json() or {}).get("data")
            except requests.RequestException as exc:
                raise CongressTradesError(
                    f"senate eFD report search failed ({type(exc).__name__}: {exc})") from exc
            except ValueError as exc:
                raise CongressTradesError(
                    "senate eFD report search returned a non-JSON response") from exc
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                parsed = self._parse_report_row(row)
                if parsed:
                    found.append(parsed)
            if len(rows) < EFD_PAGE_SIZE:
                break
            start += EFD_PAGE_SIZE
            if self.request_delay:
                time.sleep(self.request_delay)
        return found

    @staticmethod
    def _parse_report_row(row):
        """One search hit as ``{name, url, filed}``, or None if it carries no report link.

        eFD returns each hit as a positional list of HTML fragments - first name, last name,
        office, a linked report title, and the date received. The link is the only part whose
        position is load-bearing, so it is found by pattern anywhere in the row instead.
        """
        if not isinstance(row, list):
            return None
        cells = [str(cell) for cell in row]
        link = None
        for cell in cells:
            match = re.search(r'href="(/search/view/[^"]+)"', cell)
            if match:
                link = f"{EFD_ROOT}{match.group(1)}"
                break
        if not link:
            return None
        stripped = [re.sub(r"<[^>]+>", " ", cell).strip() for cell in cells]
        filed = next((normalize_date(cell) for cell in reversed(stripped)
                      if normalize_date(cell)), None)
        # The office column, when present, is the fuller identification (it carries the
        # state); the two name columns are the fallback.
        name = " ".join(part for part in stripped[:2] if part) or None
        return {"name": name, "url": link, "filed": filed,
                "office": stripped[2] if len(stripped) > 2 else None}

    def transactions(self, report):
        """One report's disclosed trades, in this module's common shape.

        A paper filing is a scanned image with no transaction table; it is skipped rather
        than reported as a senator who disclosed nothing, which is a different claim.
        """
        if "/paper/" in report["url"]:
            return []
        try:
            response = self.session.get(report["url"], timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CongressTradesError(
                f"senate eFD report page unreadable ({type(exc).__name__}: {exc})") from exc
        parser = _TableParser()
        parser.feed(response.text)
        trades = []
        for table in parser.tables:
            for row in table:
                symbol = _cell(row, "ticker")
                description = _cell(row, "asset name", "asset")
                if not symbol and not description:
                    continue
                trades.append({
                    "chamber": "senate",
                    "representative": report.get("name"),
                    "district": report.get("office"),
                    "symbol": str(symbol).strip().upper() if symbol else None,
                    "asset_type": _cell(row, "asset type"),
                    "asset_description": description,
                    "owner": _cell(row, "owner"),
                    "transaction_type": _cell(row, "transaction type", "type", avoid=("asset",)),
                    "amount": _cell(row, "amount"),
                    "transaction_date": normalize_date(_cell(row, "transaction date", "date")),
                    "disclosure_date": report.get("filed"),
                    "comment": _cell(row, "comment"),
                    "link": report["url"],
                })
        return trades

    def fetch(self, since_days=120):
        """``(rows, reports_seen)`` for reports filed in the last ``since_days``.

        Matches ``StockWatcherClient.fetch``'s contract so ``collect`` treats every source
        the same way: rows that could be normalized, against how many the source offered.
        A report whose page fails to read costs that report, not the run.
        """
        reports = self.reports(date.today() - timedelta(days=since_days))
        rows = []
        for index, report in enumerate(reports):
            try:
                rows.extend(self.transactions(report))
            except CongressTradesError:
                continue
            if self.request_delay and index + 1 < len(reports):
                time.sleep(self.request_delay)
        usable = [row for row in rows if row["disclosure_date"] and
                  (row["symbol"] or row["asset_description"])]
        return usable, len(reports)


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
        except urllib.error.HTTPError as exc:
            # 403/404 from these buckets is not a blip to retry past - it is the mirror
            # having been withdrawn, which is exactly what happened, and which a bare
            # "request failed" reported as if a retry next week might fix it.
            if exc.code in (401, 403, 404):
                raise CongressTradesError(
                    f"{chamber} disclosure dataset is no longer public (HTTP {exc.code} at "
                    f"{url}) - set CONGRESS_{chamber.upper()}_DATASET_URL to a live mirror") from exc
            raise CongressTradesError(
                f"{chamber} disclosure dataset request failed (HTTP {exc.code})") from exc
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
