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


def parse_form4(xml_text):
    """Return open-market purchases/sales from one ownership XML document.

    Transaction codes P and S are used instead of acquisition/disposition alone so grants,
    tax withholding, gifts, and option exercises are not mislabeled as insider conviction.
    """
    root = ET.fromstring(xml_text)
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
        })
    return transactions


class SecEdgarClient:
    def __init__(self, user_agent=None, request_delay=0.12):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "").strip()
        self.request_delay = request_delay
        self._tickers = None

    @property
    def available(self):
        return bool(self.user_agent)

    def _get(self, url, as_json=False):
        if not self.available:
            raise RuntimeError("SEC_USER_AGENT is required by SEC fair-access policy")
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
            "Host": urllib.parse.urlparse(url).netloc,
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
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

    def form4_summary(self, ticker, lookback_days=180, max_filings=12):
        transactions = []
        filings = self.recent_form4_filings(ticker, lookback_days, max_filings)
        for filing in filings:
            accession = filing["accession"].replace("-", "")
            cik = str(int(filing["cik"]))
            url = f"{SEC_ROOT}/Archives/edgar/data/{cik}/{accession}/{filing['document']}"
            for transaction in parse_form4(self._get(url)):
                transactions.append({**transaction, "filing_url": url, "filed": filing["filed"]})
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
