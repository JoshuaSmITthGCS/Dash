"""Small SEC EDGAR Form 4 client.

The SEC is the source of record and free to use. Set SEC_USER_AGENT to a real
application/contact string (for example ``ValueSignal research admin@example.com``).
Without it, the pipeline reports the source as unavailable rather than spoofing a client.
"""

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

SEC_ROOT = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(node, path):
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def parse_owner(root):
    """Who filed, and in what capacity.

    Identity matters because the routine-versus-opportunistic classification in
    ``insider_signal`` is per-insider: it needs to know whether *this person* trades every
    March. Role matters because Cohen, Malloy & Pomorski (2012) find the informative
    subset skews toward non-executive insiders, so the two are kept separate rather than
    collapsed into a single "insider bought" count.
    """
    node = root.find(".//reportingOwner")
    if node is None:
        return {"owner_name": None, "owner_cik": None, "roles": [], "officer_title": None}
    relationship = node.find("./reportingOwnerRelationship")
    roles = []
    if relationship is not None:
        for tag, label in (("isDirector", "director"), ("isOfficer", "officer"),
                           ("isTenPercentOwner", "ten_percent_owner"), ("isOther", "other")):
            value = _text(relationship, f"./{tag}")
            if value and value.strip().lower() in {"1", "true"}:
                roles.append(label)
    return {
        "owner_name": _text(node, "./reportingOwnerId/rptOwnerName"),
        "owner_cik": _text(node, "./reportingOwnerId/rptOwnerCik"),
        "roles": roles,
        "officer_title": _text(node, "./reportingOwnerRelationship/officerTitle"),
    }


def parse_form4(xml_text):
    """Return open-market purchases/sales from one ownership XML document.

    Transaction codes P and S are used instead of acquisition/disposition alone so grants,
    tax withholding, gifts, and option exercises are not mislabeled as insider conviction.
    Each transaction carries its filer's identity and role so downstream scoring can tell a
    calendar-clockwork sale from a genuine opportunistic purchase.
    """
    root = ET.fromstring(xml_text)
    owner = parse_owner(root)
    transactions = []
    for node in root.findall(".//nonDerivativeTransaction"):
        code = _text(node, "./transactionCoding/transactionCode")
        if code not in {"P", "S"}:
            continue
        shares = _number(_text(node, "./transactionAmounts/transactionShares/value"))
        price = _number(_text(node, "./transactionAmounts/transactionPricePerShare/value"))
        acquired = _text(node, "./transactionAmounts/transactionAcquiredDisposedCode/value")
        transaction_date = _text(node, "./transactionDate/value")
        transactions.append({
            "code": code,
            "side": "purchase" if code == "P" else "sale",
            "shares": shares,
            "price": price,
            "value": None if shares is None or price is None else round(shares * price, 2),
            "acquired_disposed": acquired,
            "date": transaction_date,
            **owner,
        })
    return transactions


class SecEdgarClient:
    def __init__(self, user_agent=None, request_delay=None, limiter=None):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "").strip()
        # Pacing is delegated to a process-wide token bucket rather than a per-instance
        # sleep. A sleep only paces the thread it runs on, so N concurrent callers each
        # sleeping 0.12s issue roughly N * 8 requests per second between them - which is how
        # a "compliant" client quietly ends up eight times over the SEC's ceiling. The
        # shared limiter is the only thing that can enforce a global rate.
        self.request_delay = request_delay
        self._limiter = limiter
        self._tickers = None

    @property
    def available(self):
        return bool(self.user_agent)

    def limiter(self):
        if self._limiter is None:
            from cache import limiter_for  # local import keeps sec_edgar standalone-usable
            self._limiter = limiter_for("sec_edgar")
        return self._limiter

    def _get(self, url, as_json=False):
        if not self.available:
            raise RuntimeError("SEC_USER_AGENT is required by SEC fair-access policy")
        # Blocks until this caller owns the next slot, across every thread in the process.
        self.limiter().acquire()
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
            "Host": urllib.parse.urlparse(url).netloc,
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
        if self.request_delay:
            time.sleep(self.request_delay)
        return json.loads(payload) if as_json else payload.decode("utf-8", errors="replace")

    def ticker_map(self):
        if self._tickers is None:
            payload = self._get(f"{SEC_ROOT}/files/company_tickers.json", as_json=True)
            self._tickers = {
                row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                for row in payload.values()
            }
        return self._tickers

    def recent_form4_filings(self, ticker, lookback_days=180, max_filings=12):
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return []
        payload = self._get(f"{SEC_DATA}/submissions/CIK{cik}.json", as_json=True)
        recent = payload.get("filings", {}).get("recent", {})
        cutoff = date.today() - timedelta(days=lookback_days)
        filings = []
        for index, form in enumerate(recent.get("form", [])):
            if form not in {"4", "4/A"}:
                continue
            filed = recent.get("filingDate", [""])[index]
            try:
                if datetime.strptime(filed, "%Y-%m-%d").date() < cutoff:
                    continue
            except ValueError:
                continue
            filings.append({
                "cik": cik,
                "accession": recent["accessionNumber"][index],
                "document": recent["primaryDocument"][index],
                "filed": filed,
            })
            if len(filings) >= max_filings:
                break
        return filings

    def form4_transactions(self, ticker, lookback_days=1100, max_filings=80):
        """Every open-market Form 4 transaction in the window, newest filing first.

        The default lookback is deliberately close to three years. Classifying a trade as
        routine requires seeing whether the same insider traded in the same calendar month
        in prior years, and that judgement is impossible on a six-month window.
        """
        transactions = []
        filings = self.recent_form4_filings(ticker, lookback_days, max_filings)
        for filing in filings:
            accession = filing["accession"].replace("-", "")
            cik = str(int(filing["cik"]))
            url = f"{SEC_ROOT}/Archives/edgar/data/{cik}/{accession}/{filing['document']}"
            try:
                parsed = parse_form4(self._get(url))
            except (ET.ParseError, OSError, ValueError):
                continue
            for transaction in parsed:
                transactions.append({**transaction, "filing_url": url, "filed": filing["filed"]})
        return transactions, filings

    def form4_summary(self, ticker, lookback_days=180, max_filings=12):
        transactions, filings = self.form4_transactions(ticker, lookback_days, max_filings)
        purchases = [row for row in transactions if row["side"] == "purchase"]
        sales = [row for row in transactions if row["side"] == "sale"]
        return {
            "source": "SEC EDGAR Form 4",
            "lookback_days": lookback_days,
            "filings_reviewed": len(filings),
            "records_reviewed": len(transactions),
            "recent_acquisitions": len(purchases),
            "recent_disposals": len(sales),
            "purchase_value": round(sum(row["value"] or 0 for row in purchases), 2),
            "sale_value": round(sum(row["value"] or 0 for row in sales), 2),
            "latest_transaction_date": max((row["date"] for row in transactions if row["date"]), default=None),
            "transactions": transactions[:20],
        }

    # ---------------- XBRL and full-text search (used by the theme-exposure layer) ----------------

    def company_facts(self, ticker):
        """Every XBRL fact the filer has ever tagged. Large; cache aggressively."""
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return {}
        return self._get(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json", as_json=True)

    def company_concept(self, ticker, concept, taxonomy="us-gaap"):
        """One XBRL concept's full reported history for one filer."""
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return {}
        return self._get(
            f"{SEC_DATA}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json",
            as_json=True,
        )

    def frames(self, concept, period, taxonomy="us-gaap", unit="USD"):
        """One concept across every filer for one period - the cross-sectional view.

        EDGAR snaps each filer's nearest reporting date into the requested calendar period,
        so a frame mixes fiscal calendars by design. Fine for ranking, wrong for precision.
        """
        return self._get(
            f"{SEC_DATA}/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json",
            as_json=True,
        )

    def full_text_search(self, query, *, forms="10-K", date_range=None, limit=10):
        """EDGAR full-text search. Returns the raw hit payload; callers extract what they need."""
        params = {"q": f'"{query}"', "forms": forms, "hits": str(limit)}
        if date_range:
            params["dateRange"] = "custom"
            params["startdt"], params["enddt"] = date_range
        encoded = urllib.parse.urlencode(params)
        return self._get(f"https://efts.sec.gov/LATEST/search-index?{encoded}", as_json=True)

    def filing_document(self, cik, accession, document):
        """Raw text of one filed document, for keyword-density work."""
        accession = str(accession).replace("-", "")
        return self._get(
            f"{SEC_ROOT}/Archives/edgar/data/{int(cik)}/{accession}/{document}")
