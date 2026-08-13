import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import collect_filing_risk_signals

CONCENTRATED_10K = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c-cust">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByTypeAxis">us-gaap:CustomerConcentrationRiskMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-total"><entity><identifier>1</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
  <context id="c-cn"><entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">country:CN</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
  <us-gaap:ConcentrationRiskPercentage1 contextRef="c-cust" unitRef="pure" decimals="2">0.40</us-gaap:ConcentrationRiskPercentage1>
  <us-gaap:Revenues contextRef="c-total" unitRef="usd" decimals="0">1000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-cn" unitRef="usd" decimals="0">600</us-gaap:Revenues>
</xbrl>"""

# No dimensional tags at all - a filing that was successfully fetched and parsed but
# simply never disclosed either concept. Distinct from an unreadable filing.
UNTAGGED_10K = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026">
  <context id="c-total"><entity><identifier>1</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
  <us-gaap:Revenues contextRef="c-total" unitRef="usd" decimals="0">1000</us-gaap:Revenues>
</xbrl>"""


class _PassthroughCache:
    def fetch(self, namespace, key, produce, source=None):
        return produce()


class _FakeSecForFilingRisk:
    available = True

    def __init__(self, filings_by_symbol, documents_by_url):
        self._filings = filings_by_symbol
        self._documents = documents_by_url

    def recent_forms(self, ticker, forms, limit=2):
        return self._filings.get(ticker, [])

    def filing_document(self, cik, accession, document):
        return self._documents[(accession, document)]


class CollectFilingRiskSignalsTests(unittest.TestCase):
    def test_concentration_and_geography_are_both_extracted_from_one_fetch(self):
        filings = {"ACME": [{"cik": "1", "accession": "acc-1", "document": "doc.htm",
                             "filed": "2026-02-01", "url": "1/acc-1/doc.htm"}]}
        sec = _FakeSecForFilingRisk(filings, {("acc-1", "doc.htm"): CONCENTRATED_10K})

        concentration, geography, diagnostics = collect_filing_risk_signals(
            sec, ("ACME",), cache=_PassthroughCache())

        self.assertEqual(concentration["ACME"]["score_points"], -3.0)
        self.assertLess(geography["ACME"]["score_points"], 0.0)
        self.assertEqual(diagnostics["filings_reviewed"], 1)
        self.assertEqual(diagnostics["filings_unreadable"], 0)
        self.assertEqual(diagnostics["concentration_tagged"], 1)
        self.assertEqual(diagnostics["geographic_tagged"], 1)

    def test_an_untagged_filing_counts_as_reviewed_but_not_coverage(self):
        # This is the coverage-measurement gate itself: a reviewed-but-untagged filing
        # must not silently inflate the tag-coverage rate the way it would if "reviewed"
        # and "tagged" were conflated.
        filings = {"ACME": [{"cik": "1", "accession": "acc-1", "document": "doc.htm",
                             "filed": "2026-02-01", "url": "1/acc-1/doc.htm"}]}
        sec = _FakeSecForFilingRisk(filings, {("acc-1", "doc.htm"): UNTAGGED_10K})

        concentration, geography, diagnostics = collect_filing_risk_signals(
            sec, ("ACME",), cache=_PassthroughCache())

        self.assertEqual(diagnostics["filings_reviewed"], 1)
        self.assertEqual(diagnostics["concentration_tagged"], 0)
        self.assertEqual(diagnostics["geographic_tagged"], 0)
        self.assertFalse(concentration["ACME"]["available"])

    def test_a_symbol_with_no_10k_on_file_is_simply_absent_not_zero(self):
        sec = _FakeSecForFilingRisk({"ACME": []}, {})

        concentration, geography, diagnostics = collect_filing_risk_signals(
            sec, ("ACME",), cache=_PassthroughCache())

        self.assertNotIn("ACME", concentration)
        self.assertNotIn("ACME", geography)

    def test_an_unavailable_client_returns_empty_diagnostics_rather_than_raising(self):
        sec = _FakeSecForFilingRisk({}, {})
        sec.available = False

        concentration, geography, diagnostics = collect_filing_risk_signals(
            sec, ("ACME",), cache=_PassthroughCache())

        self.assertEqual((concentration, geography), ({}, {}))
        self.assertEqual(diagnostics["filings_reviewed"], 0)


if __name__ == "__main__":
    unittest.main()
