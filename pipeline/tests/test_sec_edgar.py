import contextlib
import os
import sys
import threading
import time
import unittest
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
