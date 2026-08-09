import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import collect_filing_risk_signals, collect_institutional_ownership_signals

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


INFO_TABLE_TEMPLATE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ACME CORP</nameOfIssuer>
    <cusip>000000001</cusip>
    <value>{value}</value>
    <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


class _FakeSecFor13F:
    available = True

    def __init__(self, filings_by_manager, documents_by_accession):
        self._filings = filings_by_manager
        self._documents = documents_by_accession

    def recent_forms(self, ticker, forms, limit=2):
        return self._filings.get(ticker, [])

    def filing_document(self, cik, accession, document):
        return self._documents[accession]


class _FakeOpenFigi:
    def __init__(self, mapping):
        self._mapping = mapping

    def map_cusips(self, cusips):
        return {cusip: ticker for cusip, ticker in self._mapping.items() if cusip in cusips}


class CollectInstitutionalOwnershipSignalsTests(unittest.TestCase):
    def _managers_filings(self, current_shares_by_manager, prior_shares_by_manager):
        filings_by_manager, documents = {}, {}
        for manager, shares in current_shares_by_manager.items():
            filings_by_manager[manager] = [
                {"cik": "1", "accession": f"{manager}-cur", "document": "cur.xml", "filed": "2026-05-01"},
                {"cik": "1", "accession": f"{manager}-pri", "document": "pri.xml", "filed": "2026-02-01"},
            ]
            documents[f"{manager}-cur"] = INFO_TABLE_TEMPLATE.format(value=1000, shares=shares)
            documents[f"{manager}-pri"] = INFO_TABLE_TEMPLATE.format(
                value=1000, shares=prior_shares_by_manager.get(manager, 0))
        return filings_by_manager, documents

    def test_multiple_managers_adding_produces_a_positive_signal_for_the_mapped_ticker(self):
        filings, documents = self._managers_filings(
            {"MGR_A": 2000, "MGR_B": 2000, "MGR_C": 100}, {"MGR_A": 1000, "MGR_B": 1000, "MGR_C": 100})
        sec = _FakeSecFor13F(filings, documents)
        managers = [{"ticker": t, "name": t} for t in filings]
        openfigi = _FakeOpenFigi({"000000001": "ACME"})

        signals, diagnostics = collect_institutional_ownership_signals(
            sec, ("ACME",), cache=_PassthroughCache(), managers=managers, openfigi=openfigi)

        self.assertIn("ACME", signals)
        self.assertGreater(signals["ACME"]["score_points"], 0.0)
        self.assertEqual(diagnostics["managers_reviewed"], 3)
        self.assertEqual(diagnostics["cusips_mapped"], 1)

    def test_a_ticker_resolved_outside_the_scored_universe_is_not_published(self):
        filings, documents = self._managers_filings({"MGR_A": 2000, "MGR_B": 2000}, {"MGR_A": 1000, "MGR_B": 1000})
        sec = _FakeSecFor13F(filings, documents)
        managers = [{"ticker": t, "name": t} for t in filings]
        openfigi = _FakeOpenFigi({"000000001": "ACME"})

        signals, _ = collect_institutional_ownership_signals(
            sec, ("SOMETHING_ELSE",), cache=_PassthroughCache(), managers=managers, openfigi=openfigi)

        self.assertEqual(signals, {})

    def test_no_curated_managers_configured_returns_empty_rather_than_raising(self):
        sec = _FakeSecFor13F({}, {})

        signals, diagnostics = collect_institutional_ownership_signals(
            sec, ("ACME",), cache=_PassthroughCache(), managers=[], openfigi=_FakeOpenFigi({}))

        self.assertEqual(signals, {})
        self.assertEqual(diagnostics["managers_reviewed"], 0)

    def test_an_unavailable_client_returns_empty_rather_than_raising(self):
        sec = _FakeSecFor13F({}, {})
        sec.available = False
        managers = [{"ticker": "MGR_A", "name": "Manager A"}]

        signals, diagnostics = collect_institutional_ownership_signals(
            sec, ("ACME",), cache=_PassthroughCache(), managers=managers, openfigi=_FakeOpenFigi({}))

        self.assertEqual(signals, {})


if __name__ == "__main__":
    unittest.main()
