import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from theme_signals import EdgarThemeSignals, backlog_total
from xbrl_dimensions import dimensional_facts

# Filer discloses only the near/long-term split - no undimensioned total tag at all. This
# is the shape `company_concept` cannot serve, since it returns default (non-dimensional)
# facts only; `backlog_total` has to sum the bands itself.
BANDED_ONLY = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c-near">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:SatisfactionPeriodAxis">us-gaap:WithinOneYearMember</xbrldi:explicitMember>
    </segment></entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="c-far">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:SatisfactionPeriodAxis">us-gaap:MoreThanOneYearMember</xbrldi:explicitMember>
    </segment></entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <us-gaap:RevenueRemainingPerformanceObligation contextRef="c-near" unitRef="usd" decimals="0">600</us-gaap:RevenueRemainingPerformanceObligation>
  <us-gaap:RevenueRemainingPerformanceObligation contextRef="c-far" unitRef="usd" decimals="0">400</us-gaap:RevenueRemainingPerformanceObligation>
</xbrl>"""

TOTAL_ONLY = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026">
  <context id="c-total">
    <entity><identifier>1</identifier></entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <us-gaap:RevenueRemainingPerformanceObligation contextRef="c-total" unitRef="usd" decimals="0">1500</us-gaap:RevenueRemainingPerformanceObligation>
</xbrl>"""


class BacklogTotalTests(unittest.TestCase):
    def test_sums_satisfaction_period_bands_when_no_total_is_tagged(self):
        facts = dimensional_facts(BANDED_ONLY, "RevenueRemainingPerformanceObligation")
        self.assertEqual(backlog_total(facts), 1000.0)

    def test_prefers_the_undimensioned_total_when_one_exists(self):
        facts = dimensional_facts(TOTAL_ONLY, "RevenueRemainingPerformanceObligation")
        self.assertEqual(backlog_total(facts), 1500.0)

    def test_neither_shape_present_returns_none_rather_than_zero(self):
        self.assertIsNone(backlog_total([]))


class _FakeCache:
    """No disk, no expiry - just calls the producer and remembers nothing between calls."""

    def fetch(self, namespace, key, producer, source=None):
        return producer()


class _FakeSec:
    available = True

    def __init__(self, filings, documents):
        self._filings = filings
        self._documents = documents

    def ticker_map(self):
        return {"ACME": "0000000001"}

    def _get(self, url, as_json=False):
        return {"filings": {"recent": self._filings}}

    def filing_document(self, cik, accession, document):
        return self._documents[(accession, document)]


def _recent_filings(accessions_documents):
    forms = ["10-K"] * len(accessions_documents)
    return {
        "form": forms,
        "accessionNumber": [a for a, _ in accessions_documents],
        "primaryDocument": [d for _, d in accessions_documents],
        "filingDate": ["2026-02-01"] * len(accessions_documents),
    }


class BacklogValuesTests(unittest.TestCase):
    def test_two_annual_filings_produce_a_newest_first_series(self):
        docs = {("acc-2026", "doc.htm"): TOTAL_ONLY.replace("1500", "1800"),
                ("acc-2025", "doc.htm"): TOTAL_ONLY}
        sec = _FakeSec(_recent_filings([("acc-2026", "doc.htm"), ("acc-2025", "doc.htm")]), docs)
        provider = EdgarThemeSignals(sec, cache=_FakeCache())

        values = provider.backlog_values("ACME")

        self.assertEqual(values, [1800.0, 1500.0])

    def test_a_filing_with_no_matching_fact_is_skipped_not_treated_as_zero(self):
        docs = {("acc-2026", "doc.htm"): "<xbrl></xbrl>",
                ("acc-2025", "doc.htm"): TOTAL_ONLY}
        sec = _FakeSec(_recent_filings([("acc-2026", "doc.htm"), ("acc-2025", "doc.htm")]), docs)
        provider = EdgarThemeSignals(sec, cache=_FakeCache())

        self.assertEqual(provider.backlog_values("ACME"), [1500.0])

    def test_call_computes_backlog_growth_when_the_theme_declares_it(self):
        docs = {("acc-2026", "doc.htm"): TOTAL_ONLY.replace("1500", "1800"),
                ("acc-2025", "doc.htm"): TOTAL_ONLY}
        sec = _FakeSec(_recent_filings([("acc-2026", "doc.htm"), ("acc-2025", "doc.htm")]), docs)
        provider = EdgarThemeSignals(sec, cache=_FakeCache())
        theme = {"id": "t1", "signals": [{"name": "backlog_growth"}]}

        result = provider("ACME", theme)

        self.assertAlmostEqual(result["backlog_growth"], 0.2, places=4)

    def test_call_omits_backlog_growth_when_the_theme_does_not_declare_it(self):
        sec = _FakeSec(_recent_filings([]), {})
        provider = EdgarThemeSignals(sec, cache=_FakeCache())
        theme = {"id": "t2", "signals": [{"name": "hyperscaler_capex_growth", "universe": []}]}

        result = provider("ACME", theme)

        self.assertNotIn("backlog_growth", result)


if __name__ == "__main__":
    unittest.main()
