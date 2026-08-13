"""Small SEC EDGAR Form 4 client.

The SEC is the source of record and free to use. Set SEC_USER_AGENT to a real
application/contact string (for example ``ValueSignal research admin@example.com``).
Without it, the pipeline reports the source as unavailable rather than spoofing a client.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

SEC_ROOT = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"

# EDGAR reports an ownership form's ``primaryDocument`` as its human-readable rendering -
# ``xslF345X03/wf-form4_1234.xml`` - which serves HTML, not XML. The raw ownership XML sits
# at the same path with the XSL rendering directory stripped off.
XSL_RENDER_DIRECTORY = re.compile(r"^xsl[^/]*/", re.IGNORECASE)

# EDGAR conformed names are upper-case, punctuation-noisy, and word-ordered differently
# from how a manager is colloquially known ("PRICE T ROWE ASSOCIATES INC /MD/" for what the
# config calls "T. Rowe Price"). Comparing them as raw strings fails on every one of those
# differences, so both sides are reduced to a bag of alphanumeric tokens first.
_NAME_NOISE = re.compile(r"[^A-Z0-9 ]+")


def _name_tokens(value):
    return _NAME_NOISE.sub(" ", (value or "").upper()).split()


def entity_name_matches(conformed_name, expected_name):
    """Whether an EDGAR conformed name plausibly belongs to the expected manager family.

    Token-subset, not equality: an adviser subsidiary's conformed name is the family name
    plus extra words ("ARTISAN PARTNERS **LIMITED PARTNERSHIP**"), and EDGAR reorders and
    re-punctuates freely. Requires at least two tokens to match on, because a single common
    token ("FRANKLIN", "ARTISAN") would happily accept an unrelated filer - and attributing
    one manager's holdings to another is the specific failure this guard exists to prevent.
    """
    wanted = _name_tokens(expected_name)
    if not wanted:
        return False
    have = set(_name_tokens(conformed_name))
    if len(wanted) < 2:
        return wanted[0] in have
    return all(token in have for token in wanted)


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


def form4_document_urls(cik, accession, document):
    """Candidate URLs for one Form 4's ownership XML, most likely first.

    Fetching ``primaryDocument`` verbatim returns the XSL-rendered HTML for the great
    majority of ownership filings, so ``parse_form4`` raises and the filing is skipped. That
    failure is invisible from the outside: the run still reviews thousands of filings, still
    reports the source healthy, and still scores every symbol as having no insider activity
    at all - which is exactly what the published dataset showed. Try the de-rendered path
    first, then the document as filed, then the conventional ``primary_doc.xml``.
    """
    base = f"{SEC_ROOT}/Archives/edgar/data/{cik}/{accession}"
    names = [XSL_RENDER_DIRECTORY.sub("", document or ""), document, "primary_doc.xml"]
    urls = []
    for name in names:
        url = f"{base}/{name}" if name else None
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_form4(xml_text):
    """Return open-market purchases/sales from one ownership XML document.

    Transaction codes P and S are used instead of acquisition/disposition alone so grants,
    tax withholding, gifts, and option exercises are not mislabeled as insider conviction.
    Each transaction carries its filer's identity and role so downstream scoring can tell a
    calendar-clockwork sale from a genuine opportunistic purchase.
    """
    root = ET.fromstring(xml_text)
    # An XSL-rendered filing is sometimes well-formed enough to parse, in which case it
    # yields zero transactions and looks exactly like a filing with nothing in it. Reject
    # anything that is not an ownership document outright so the caller can fall back to
    # another URL instead of recording a phantom empty filing.
    if root.tag.rsplit("}", 1)[-1] != "ownershipDocument":
        raise ValueError(f"not a Form 4 ownership document (root <{root.tag}>)")
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
        # One submissions payload per CIK per process. Filer resolution reads a candidate's
        # payload to check both its conformed name and whether it files the form at all, and
        # the caller then reads the same payload again for the filings themselves.
        self._submissions = {}

    @property
    def available(self):
        return bool(self.user_agent)

    def limiter(self):
        if self._limiter is None:
            from cache import limiter_for  # local import keeps sec_edgar standalone-usable
            self._limiter = limiter_for("sec_edgar")
        return self._limiter

    # SEC answers a rate-limit breach with 403 or 429 rather than a queue, and a client that
    # retries immediately earns a longer block. Back off exponentially and give up rather
    # than hammer: a partial backfill is recoverable, a blocked User-Agent is not.
    RETRY_STATUSES = (403, 429, 500, 502, 503, 504)
    MAX_ATTEMPTS = 5

    def _get(self, url, as_json=False, *, raw=False):
        if not self.available:
            raise RuntimeError("SEC_USER_AGENT is required by SEC fair-access policy")
        last_error = None
        for attempt in range(self.MAX_ATTEMPTS):
            # Blocks until this caller owns the next slot, across every thread in the process.
            self.limiter().acquire()
            request = urllib.request.Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "identity",
                "Host": urllib.parse.urlparse(url).netloc,
            })
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = response.read()
                break
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code not in self.RETRY_STATUSES or attempt + 1 == self.MAX_ATTEMPTS:
                    raise
                delay = 2 ** attempt
                # Local import for the same reason as limiter() above - sec_edgar stays
                # usable standalone. It was previously a bare LOG reference with no import
                # at all, so the one path that exists to survive a rate-limit breach raised
                # NameError on its first 403/429 instead of backing off, and the backoff
                # below never ran once.
                from common import LOG
                LOG.warn(f"SEC {error.code} on {url}; backing off {delay}s "
                         f"(attempt {attempt + 1}/{self.MAX_ATTEMPTS})")
                time.sleep(delay)
            except urllib.error.URLError as error:
                last_error = error
                if attempt + 1 == self.MAX_ATTEMPTS:
                    raise
                time.sleep(2 ** attempt)
        else:  # pragma: no cover - the loop always breaks or raises
            raise last_error
        if self.request_delay:
            time.sleep(self.request_delay)
        if raw:
            return payload
        return json.loads(payload) if as_json else payload.decode("utf-8", errors="replace")

    def ticker_map_rows(self):
        """The raw company_tickers.json rows, for edgar_entities.EntityResolver."""
        payload = self._get(f"{SEC_ROOT}/files/company_tickers.json", as_json=True)
        return list(payload.values())

    def bulk_company_facts(self):
        """The whole-universe companyfacts archive: one download instead of ~900 requests."""
        return self._get(f"{SEC_ROOT}/Archives/edgar/daily-index/xbrl/companyfacts.zip",
                         raw=True)

    def ticker_map(self):
        if self._tickers is None:
            payload = self._get(f"{SEC_ROOT}/files/company_tickers.json", as_json=True)
            self._tickers = {
                row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                for row in payload.values()
            }
        return self._tickers

    def submissions(self, cik):
        """One CIK's submissions payload, fetched at most once per process."""
        cik = str(cik).zfill(10)
        if cik not in self._submissions:
            self._submissions[cik] = self._get(f"{SEC_DATA}/submissions/CIK{cik}.json", as_json=True)
        return self._submissions[cik]

    def entity_name(self, cik):
        """EDGAR's conformed name for a CIK - what a resolved filer must be checked against
        before its holdings are attributed to a configured manager."""
        return (self.submissions(cik) or {}).get("name")

    def company_search(self, name, form_type=None, limit=40):
        """Entities whose EDGAR conformed name *begins with* ``name``, as ``(cik, name)``.

        The reason this exists: ``company_tickers.json`` maps a ticker to the CIK of the
        *listed operating company*, and for an asset manager that is almost never the entity
        that files the 13F. T. Rowe Price Group files the 10-K; its adviser subsidiaries file
        the 13F-HRs, under their own CIKs, and no EDGAR endpoint links a parent to them. This
        company-name search is the only free way to reach them without hand-typing a CIK -
        which the curated config deliberately refuses to do, because a mistyped CIK reads a
        *different* manager's holdings under the configured name and fails silently wrong.

        ``company=`` is a prefix match on the conformed name, not a substring one, so an
        entity filed under a reordered name ("PRICE T ROWE ASSOCIATES") is not reachable from
        the colloquial spelling and needs its own alias in the config. Callers must still
        verify each hit with ``entity_name_matches`` - a prefix search returns neighbours.
        """
        params = {"action": "getcompany", "company": name, "owner": "include",
                  "count": str(limit), "output": "atom"}
        if form_type:
            params["type"] = form_type
        try:
            payload = self._get(f"{SEC_ROOT}/cgi-bin/browse-edgar?{urllib.parse.urlencode(params)}")
        except OSError:
            return []
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return []

        def local(tag):
            return tag.rsplit("}", 1)[-1].lower()

        found, seen = [], set()
        # Two response shapes: several matches come back as a list of <company-info> blocks,
        # while a single exact match returns that company's filing list with one
        # <company-info> header. Walking every <company-info> in the tree handles both.
        for node in root.iter():
            if local(node.tag) != "company-info":
                continue
            fields = {local(child.tag): (child.text or "").strip() for child in node}
            cik = fields.get("cik")
            if not cik or cik in seen:
                continue
            seen.add(cik)
            found.append((str(cik).zfill(10), fields.get("conformed-name")))
        return found

    def recent_form4_filings(self, ticker, lookback_days=180, max_filings=12):
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return []
        payload = self.submissions(cik)
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

    def filings_for_cik(self, cik, forms, limit=2):
        """Most recent filings of the given form type(s) for an already-known CIK.

        Kept separate from ``recent_forms`` because some callers - institutional 13F
        managers, chiefly - are identified by CIK directly rather than by a covered
        ticker, so there is nothing for ``ticker_map`` to resolve.

        Carries ``form`` (so a caller can tell a 13F-HR from its own 13F-HR/A amendment)
        and ``period`` (EDGAR's ``reportDate`` - the quarter or period the filing actually
        covers, as opposed to ``filed``, when it became public). The two diverge exactly
        when an amendment matters: an amendment's ``filed`` date is recent, but its
        ``period`` is the same quarter the original filing already covered, and a caller
        that groups by ``filed`` alone will mistake the amendment for a new quarter.
        """
        payload = self.submissions(cik)
        recent = payload.get("filings", {}).get("recent", {})
        filings = []
        for index, form in enumerate(recent.get("form", [])):
            if form not in forms:
                continue
            filings.append({
                "cik": cik,
                "form": form,
                "accession": recent["accessionNumber"][index],
                "document": recent["primaryDocument"][index],
                "filed": recent.get("filingDate", [""])[index],
                "period": recent.get("reportDate", [""])[index],
            })
            if len(filings) >= limit:
                break
        return filings

    def recent_forms(self, ticker, forms, limit=2):
        """Most recent filings of the given form type(s) for a covered ticker."""
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return []
        return self.filings_for_cik(cik, forms, limit=limit)

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
            parsed = None
            source_url = None
            for url in form4_document_urls(cik, accession, filing["document"]):
                try:
                    parsed = parse_form4(self._get(url))
                except (ET.ParseError, OSError, ValueError):
                    continue
                source_url = url
                break
            # Recorded per filing rather than swallowed: a run where every filing is
            # unreadable must be able to report itself as degraded instead of as a market
            # in which no insider traded.
            filing["parsed"] = parsed is not None
            if parsed is None:
                continue
            for transaction in parsed:
                transactions.append({**transaction, "filing_url": source_url, "filed": filing["filed"]})
        return transactions, filings

    def form4_summary(self, ticker, lookback_days=180, max_filings=12):
        transactions, filings = self.form4_transactions(ticker, lookback_days, max_filings)
        purchases = [row for row in transactions if row["side"] == "purchase"]
        sales = [row for row in transactions if row["side"] == "sale"]
        return {
            "source": "SEC EDGAR Form 4",
            "lookback_days": lookback_days,
            "filings_reviewed": len(filings),
            "filings_unreadable": sum(1 for filing in filings if not filing.get("parsed")),
            "records_reviewed": len(transactions),
            "recent_acquisitions": len(purchases),
            "recent_disposals": len(sales),
            "purchase_value": round(sum(row["value"] or 0 for row in purchases), 2),
            "sale_value": round(sum(row["value"] or 0 for row in sales), 2),
            "latest_transaction_date": max((row["date"] for row in transactions if row["date"]), default=None),
            "transactions": transactions[:20],
        }

    # ---------------- XBRL and full-text search (used by the theme-exposure layer) ----------------

    def company_facts_by_cik(self, cik):
        """Every XBRL fact this filer has ever reported, keyed by CIK.

        The CIK-keyed entry point, used by the point-in-time backfill. Distinct name from
        ``company_facts`` below on purpose: a second ``company_facts`` defined later in this
        class silently shadowed an earlier one, so a CIK went into a ticker lookup, missed,
        and returned an empty dict that read as a successful fetch -- 25 companies reported
        "ok" with zero facts. ``test_sec_edgar_contract`` now fails the build on any
        duplicate method name in this class.
        """
        return self._get(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",
                         as_json=True)

    def company_facts(self, ticker):
        """Every XBRL fact the filer has ever tagged, by ticker. Large; cache aggressively."""
        cik = self.ticker_map().get(ticker.upper())
        if not cik:
            return {}
        return self.company_facts_by_cik(cik)

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

    def filing_index(self, cik, accession):
        """Every document filed under one accession, from EDGAR's own directory listing.

        A filing's ``primaryDocument`` is often the cover page or a rendered summary, not
        every exhibit - a 13F-HR's actual holdings, for instance, are commonly a separate
        ``InfoTable.xml`` exhibit the submissions API never names directly. This is the
        same problem ``form4_document_urls`` solved for Form 4 by trying several candidate
        paths; unlike Form 4's fixed rendering-directory pattern, an exhibit name has no
        fixed convention, so the caller needs the real listing to search it.
        """
        accession = str(accession).replace("-", "")
        payload = self._get(f"{SEC_ROOT}/Archives/edgar/data/{int(cik)}/{accession}/index.json",
                            as_json=True)
        return [item["name"] for item in (payload.get("directory") or {}).get("item", [])
                if item.get("name")]
