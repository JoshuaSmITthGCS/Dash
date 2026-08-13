import contextlib
import os
import sys
import threading
import time
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import sec_edgar
from pipeline.sec_edgar import SecEdgarClient, parse_form4, parse_owner


FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0000012345</rptOwnerCik>
      <rptOwnerName>Doe Jane</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Financial Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-01</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>25.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>500</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

ANONYMOUS_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-01</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10</value></transactionShares>
        <transactionPricePerShare><value>5</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


class Form4ParserTests(unittest.TestCase):
    def test_parse_form4_keeps_open_market_trades_only(self):
        rows = parse_form4(FORM4)
        self.assertEqual(rows, [{
            "code": "P", "side": "purchase", "shares": 100.0, "price": 25.5,
            "value": 2550.0, "acquired_disposed": "A", "date": "2026-07-01",
            "owner_name": "Doe Jane", "owner_cik": "0000012345",
            "roles": ["director", "officer"], "officer_title": "Chief Financial Officer",
        }])

    def test_owner_identity_and_roles_are_attached_to_every_transaction(self):
        # Identity is what makes the routine-versus-opportunistic split possible: the
        # classifier has to know whether this same person trades every July.
        row = parse_form4(FORM4)[0]
        self.assertEqual(row["owner_cik"], "0000012345")
        self.assertIn("director", row["roles"])
        self.assertNotIn("ten_percent_owner", row["roles"])

    def test_missing_reporting_owner_block_degrades_to_nulls(self):
        row = parse_form4(ANONYMOUS_FORM4)[0]
        self.assertEqual(row["side"], "sale")
        self.assertIsNone(row["owner_name"])
        self.assertEqual(row["roles"], [])

    def test_a_rendered_html_page_is_rejected_rather_than_read_as_an_empty_filing(self):
        # A well-formed HTML rendering parses cleanly and simply contains no
        # nonDerivativeTransaction nodes, which is indistinguishable from a filing that
        # genuinely reported nothing. Rejecting it lets the caller try another URL.
        with self.assertRaises(ValueError):
            parse_form4("<html><body><table><tr><td>Form 4</td></tr></table></body></html>")

    def test_parse_owner_reads_relationship_flags(self):
        owner = parse_owner(ET.fromstring(FORM4))
        self.assertEqual(owner["owner_name"], "Doe Jane")
        self.assertEqual(owner["officer_title"], "Chief Financial Officer")


class FairAccessTests(unittest.TestCase):
    """SEC fair access allows 10 requests/second. Exceeding it gets the client blocked."""

    def test_requests_are_paced_by_a_shared_limiter_across_threads(self):
        # The bug this guards: pacing used to be a per-instance sleep, which only slows the
        # thread it runs on. Four concurrent workers each sleeping 0.12s issued ~33 requests
        # a second between them. A process-wide token bucket is the only thing that can hold
        # a global rate, so this measures the rate under concurrency rather than in one thread.
        from cache import RateLimiter

        limiter = RateLimiter(per_minute=540)   # 9 requests/second
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=limiter)
        sent = []

        def fake_urlopen(request, timeout=None):
            sent.append(time.monotonic())
            return contextlib.nullcontext(_FakeResponse(b"{}"))

        with mock.patch.object(sec_edgar.urllib.request, "urlopen", fake_urlopen):
            def worker():
                for _ in range(4):
                    client._get("https://data.sec.gov/x.json", as_json=True)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            start = time.monotonic()
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            elapsed = time.monotonic() - start

        self.assertEqual(len(sent), 16)
        observed_rate = len(sent) / max(elapsed, 1e-9)
        self.assertLessEqual(observed_rate, 10.0,
                             f"issued {observed_rate:.1f} requests/second, over the SEC ceiling")

    def test_a_rate_limited_response_is_retried_rather_than_raising(self):
        # The bug this guards: the 403/429 handler logged through a bare `LOG` name that was
        # never imported into this module, so the one code path that exists to survive a
        # rate-limit breach raised NameError on its first use and the backoff below it never
        # ran. Callers wrapping the fetch saw an opaque NameError and fell back to stale
        # cached copies instead of retrying.
        responses = [urllib.error.HTTPError("https://data.sec.gov/x.json", 429, "Too Many "
                                            "Requests", {}, None)]

        def fake_urlopen(request, timeout=None):
            if responses:
                raise responses.pop()
            return contextlib.nullcontext(_FakeResponse(b'{"ok": true}'))

        client = SecEdgarClient(user_agent="Test Harness test@example.com",
                                limiter=_NoopLimiter())
        with mock.patch.object(sec_edgar.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(sec_edgar.time, "sleep", lambda _seconds: None):
            payload = client._get("https://data.sec.gov/x.json", as_json=True)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(responses, [])

    def test_a_client_without_an_identity_refuses_to_call(self):
        # The environment is cleared explicitly: other modules call load_local_env() at
        # import time, so on a machine with a real .env.local this would otherwise pick up
        # a live identity and make an actual network request.
        with mock.patch.dict(os.environ, {"SEC_USER_AGENT": ""}):
            client = SecEdgarClient(user_agent="")
            self.assertFalse(client.available)
            with self.assertRaises(RuntimeError):
                client._get("https://data.sec.gov/x.json")

    def test_the_required_headers_are_sent(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com",
                                limiter=_NoopLimiter())
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return contextlib.nullcontext(_FakeResponse(b"{}"))

        with mock.patch.object(sec_edgar.urllib.request, "urlopen", fake_urlopen):
            client._get("https://data.sec.gov/submissions/CIK0000320193.json", as_json=True)

        # urllib title-cases header names on the way in.
        self.assertEqual(captured["headers"]["User-agent"], "Test Harness test@example.com")
        self.assertEqual(captured["headers"]["Host"], "data.sec.gov")


class Form4DocumentUrlTests(unittest.TestCase):
    """The bug these lock: EDGAR's ``primaryDocument`` for an ownership form is its
    XSL-rendered HTML. Requesting it verbatim and parsing the result as XML fails on almost
    every filing, and the failure was swallowed - so the layer reported itself healthy while
    scoring every symbol in the universe as having no insider activity whatsoever."""

    def test_the_xsl_rendering_directory_is_stripped_before_the_document_is_fetched(self):
        urls = sec_edgar.form4_document_urls("320193", "000032019326000058",
                                             "xslF345X03/wf-form4_175.xml")
        self.assertEqual(
            urls[0],
            "https://www.sec.gov/Archives/edgar/data/320193/000032019326000058/wf-form4_175.xml",
        )

    def test_the_document_as_filed_and_primary_doc_remain_as_fallbacks(self):
        urls = sec_edgar.form4_document_urls("320193", "000032019326000058",
                                             "xslF345X03/wf-form4_175.xml")
        self.assertTrue(urls[1].endswith("/xslF345X03/wf-form4_175.xml"))
        self.assertTrue(urls[-1].endswith("/primary_doc.xml"))

    def test_an_unprefixed_document_is_not_duplicated(self):
        urls = sec_edgar.form4_document_urls("320193", "000032019326000058", "form4.xml")
        self.assertEqual(len(urls), 2)
        self.assertTrue(urls[0].endswith("/form4.xml"))

    def test_transactions_are_parsed_from_the_de_rendered_url(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        requested = []

        def fake_get(url, as_json=False):
            requested.append(url)
            if url.endswith("/xslF345X03/doc4.xml"):
                return "<html><body>rendered, not parseable as ownership XML</body></html>"
            return FORM4

        filings = [{"cik": "0000320193", "accession": "0000320193-26-000058",
                    "document": "xslF345X03/doc4.xml", "filed": "2026-07-02"}]
        with mock.patch.object(client, "recent_form4_filings", return_value=filings), \
                mock.patch.object(client, "_get", fake_get):
            transactions, reviewed = client.form4_transactions("AAPL")

        self.assertEqual([row["code"] for row in transactions], ["P"])
        self.assertTrue(reviewed[0]["parsed"])
        self.assertTrue(requested[0].endswith("/doc4.xml"))

    def test_a_filing_no_candidate_url_can_parse_is_reported_not_silently_dropped(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        filings = [{"cik": "0000320193", "accession": "0000320193-26-000058",
                    "document": "xslF345X03/doc4.xml", "filed": "2026-07-02"}]
        with mock.patch.object(client, "recent_form4_filings", return_value=filings), \
                mock.patch.object(client, "_get", lambda url, as_json=False: "<html></html>"):
            transactions, reviewed = client.form4_transactions("AAPL")

        self.assertEqual(transactions, [])
        self.assertFalse(reviewed[0]["parsed"])


class FilingsForCikTests(unittest.TestCase):
    """``form`` and ``period`` (EDGAR's reportDate) matter specifically for 13F: an
    amendment's ``filed`` date is recent, but its ``period`` is the same quarter the
    original already covered - a caller has to be able to tell the two apart."""

    def _client_with_payload(self, recent):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        client._get = lambda url, as_json=False: {"filings": {"recent": recent}}
        return client

    def test_form_and_period_are_carried_alongside_filed(self):
        recent = {
            "form": ["13F-HR", "13F-HR/A", "4"],
            "accessionNumber": ["acc-1", "acc-2", "acc-3"],
            "primaryDocument": ["doc1.xml", "doc2.xml", "doc3.xml"],
            "filingDate": ["2026-05-14", "2026-06-01", "2026-01-01"],
            "reportDate": ["2026-03-31", "2026-03-31", "2026-01-01"],
        }
        client = self._client_with_payload(recent)

        filings = client.filings_for_cik("0000000001", ("13F-HR", "13F-HR/A"), limit=5)

        self.assertEqual([f["form"] for f in filings], ["13F-HR", "13F-HR/A"])
        self.assertEqual([f["period"] for f in filings], ["2026-03-31", "2026-03-31"])
        self.assertEqual(filings[1]["filed"], "2026-06-01")

    def test_recent_forms_resolves_the_ticker_before_delegating(self):
        recent = {
            "form": ["13F-HR"], "accessionNumber": ["acc-1"], "primaryDocument": ["doc1.xml"],
            "filingDate": ["2026-05-14"], "reportDate": ["2026-03-31"],
        }
        client = self._client_with_payload(recent)
        client._tickers = {"TROW": "0000001113169"}

        filings = client.recent_forms("trow", ("13F-HR",), limit=2)

        self.assertEqual(filings[0]["cik"], "0000001113169")

    def test_an_unknown_ticker_returns_no_filings(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        client._tickers = {}
        self.assertEqual(client.recent_forms("NOPE", ("13F-HR",)), [])


class FilingIndexTests(unittest.TestCase):
    def test_every_document_name_in_the_accession_is_returned(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        client._get = lambda url, as_json=False: {"directory": {"item": [
            {"name": "primary_doc.xml", "type": "13F-HR", "size": "1200"},
            {"name": "InfoTable.xml", "type": "13F-HR EX-INFO TABLE", "size": "84000"},
        ]}}

        names = client.filing_index("0000001113169", "0001113169-26-000042")

        self.assertEqual(names, ["primary_doc.xml", "InfoTable.xml"])

    def test_a_missing_directory_listing_degrades_to_an_empty_list(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        client._get = lambda url, as_json=False: {}
        self.assertEqual(client.filing_index("1", "acc-1"), [])


MULTI_MATCH_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><content type="text/xml"><company-info>
    <cik>0000080255</cik><conformed-name>PRICE T ROWE ASSOCIATES INC /MD/</conformed-name>
  </company-info></content></entry>
  <entry><content type="text/xml"><company-info>
    <cik>0001113169</cik><conformed-name>T. Rowe Price Group, Inc.</conformed-name>
  </company-info></content></entry>
</feed>"""

SINGLE_MATCH_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <company-info>
    <cik>0001067983</cik><conformed-name>BERKSHIRE HATHAWAY INC</conformed-name>
  </company-info>
  <entry><title>13F-HR</title></entry>
</feed>"""


class EntityNameMatchTests(unittest.TestCase):
    """The guard that lets the curated config keep asserting a manager by *name* rather than
    by a hand-typed CIK - it has to survive EDGAR's word order and punctuation while still
    refusing an unrelated filer."""

    def test_reordered_and_repunctuated_conformed_name_still_matches(self):
        self.assertTrue(sec_edgar.entity_name_matches(
            "PRICE T ROWE ASSOCIATES INC /MD/", "T. Rowe Price"))

    def test_adviser_subsidiary_with_extra_words_matches_the_family_name(self):
        self.assertTrue(sec_edgar.entity_name_matches(
            "ARTISAN PARTNERS LIMITED PARTNERSHIP", "Artisan Partners"))

    def test_an_unrelated_filer_is_rejected(self):
        self.assertFalse(sec_edgar.entity_name_matches(
            "ARTISAN CONSUMER GOODS INC", "Artisan Partners"))

    def test_a_single_shared_token_is_not_enough_for_a_multi_token_name(self):
        self.assertFalse(sec_edgar.entity_name_matches(
            "FRANKLIN ELECTRIC CO INC", "Franklin Resources"))

    def test_an_empty_expected_name_never_matches(self):
        self.assertFalse(sec_edgar.entity_name_matches("BERKSHIRE HATHAWAY INC", ""))


class CompanySearchTests(unittest.TestCase):
    def _client_returning(self, body):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        return client, mock.patch.object(
            sec_edgar.urllib.request, "urlopen",
            lambda request, timeout=None: contextlib.nullcontext(_FakeResponse(body.encode())))

    def test_a_multi_company_feed_returns_every_candidate(self):
        client, patched = self._client_returning(MULTI_MATCH_ATOM)
        with patched:
            found = client.company_search("T. Rowe Price", form_type="13F-HR")
        self.assertEqual(found, [("0000080255", "PRICE T ROWE ASSOCIATES INC /MD/"),
                                 ("0001113169", "T. Rowe Price Group, Inc.")])

    def test_a_single_match_feed_returns_the_company_header(self):
        # A search that matches exactly one company returns that company's *filing list*
        # instead of a company list, with the CIK only in the header - a shape that reads as
        # "no results" if the parser only walks <entry> elements.
        client, patched = self._client_returning(SINGLE_MATCH_ATOM)
        with patched:
            found = client.company_search("Berkshire Hathaway", form_type="13F-HR")
        self.assertEqual(found, [("0001067983", "BERKSHIRE HATHAWAY INC")])

    def test_an_unparseable_response_degrades_to_no_candidates(self):
        client, patched = self._client_returning("<html>rate limited</html>")
        with patched:
            self.assertEqual(client.company_search("Anything"), [])


class SubmissionsCacheTests(unittest.TestCase):
    def test_one_cik_is_fetched_once_per_process(self):
        client = SecEdgarClient(user_agent="Test Harness test@example.com", limiter=_NoopLimiter())
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            return contextlib.nullcontext(_FakeResponse(b'{"name": "BERKSHIRE HATHAWAY INC"}'))

        with mock.patch.object(sec_edgar.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(client.entity_name("0001067983"), "BERKSHIRE HATHAWAY INC")
            client.submissions("1067983")   # same CIK, unpadded
        self.assertEqual(len(calls), 1)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload


class _NoopLimiter:
    def acquire(self):
        return 0.0


if __name__ == "__main__":
    unittest.main()
