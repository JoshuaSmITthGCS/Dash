import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from theme_signals import EdgarThemeSignals, backlog_total, keyword_density, normalized_body
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

    def recent_forms(self, ticker, forms, limit=2):
        cik = self.ticker_map().get(ticker.upper())
        filings = []
        for index, form in enumerate(self._filings.get("form", [])):
            if form not in forms:
                continue
            filings.append({
                "cik": cik,
                "accession": self._filings["accessionNumber"][index],
                "document": self._filings["primaryDocument"][index],
                "filed": self._filings.get("filingDate", [""])[index],
            })
            if len(filings) >= limit:
                break
        return filings

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


class MultiThemeReuseTests(unittest.TestCase):
    """One company's filings are read and normalized once, however many themes ask."""

    def _provider(self, counter):
        docs = {("acc-2026", "doc.htm"): "<p>GPU and data center capacity</p>",
                ("acc-2025", "doc.htm"): "<p>data center</p>"}

        class CountingSec(_FakeSec):
            def ticker_map(self):
                return {"ACME": "0000000001", "OTHER": "0000000002"}

            def filing_document(self, cik, accession, document):
                counter.append((accession, document))
                return super().filing_document(cik, accession, document)

        sec = CountingSec(_recent_filings([("acc-2026", "doc.htm"), ("acc-2025", "doc.htm")]),
                          docs)
        return EdgarThemeSignals(sec, cache=_FakeCache())

    def _theme(self, theme_id, include):
        return {"id": theme_id, "signals": [{"name": "filing_keyword_density_trend"}],
                "keywords": {"include": include}}

    def test_a_second_theme_rereads_nothing_for_the_same_company(self):
        reads = []
        provider = self._provider(reads)

        provider("ACME", self._theme("first", ["GPU"]))
        after_first = len(reads)
        provider("ACME", self._theme("second", ["data center"]))

        self.assertEqual(after_first, 2, "expected both 10-Ks read once for the first theme")
        self.assertEqual(len(reads), after_first, "second theme should reuse the same bodies")

    def test_each_theme_still_measures_its_own_vocabulary(self):
        provider = self._provider([])

        gpu = provider("ACME", self._theme("first", ["GPU"]))
        centers = provider("ACME", self._theme("second", ["data center"]))

        # "GPU" appears only in the newer filing, so its density rose from nothing; "data
        # center" appears in both. Sharing the normalized text must not share the counts.
        self.assertIsNone(gpu.get("filing_keyword_density_trend"))
        self.assertIsNotNone(centers.get("filing_keyword_density_trend"))

    def test_moving_to_the_next_company_drops_the_previous_ones_text(self):
        reads = []
        provider = self._provider(reads)

        provider("ACME", self._theme("first", ["GPU"]))
        provider("OTHER", self._theme("first", ["GPU"]))
        provider("ACME", self._theme("first", ["GPU"]))

        # Bounded to one company at a time on purpose: holding every candidate's normalized
        # 10-K would cost gigabytes to save work the caller's loop ordering already avoids.
        self.assertEqual(len(reads), 6)

    def test_backlog_is_read_once_per_company_across_themes(self):
        reads = []
        docs = {("acc-2026", "doc.htm"): TOTAL_ONLY.replace("1500", "1800"),
                ("acc-2025", "doc.htm"): TOTAL_ONLY}

        class CountingSec(_FakeSec):
            def filing_document(self, cik, accession, document):
                reads.append((accession, document))
                return super().filing_document(cik, accession, document)

        provider = EdgarThemeSignals(
            CountingSec(_recent_filings([("acc-2026", "doc.htm"), ("acc-2025", "doc.htm")]), docs),
            cache=_FakeCache())
        theme = {"id": "t1", "signals": [{"name": "backlog_growth"}]}

        first = provider("ACME", {**theme, "id": "one"})
        second = provider("ACME", {**theme, "id": "two"})

        self.assertEqual(first["backlog_growth"], second["backlog_growth"])
        self.assertEqual(len(reads), 2)


class KeywordDensityCompositionTests(unittest.TestCase):
    def test_splitting_normalization_from_counting_leaves_the_measurement_unchanged(self):
        from theme_signals import density_from_body
        text = "<p>HBM and <b>HBM</b> in the data center</p>"
        lowered, words = normalized_body(text)
        self.assertEqual(keyword_density(text, ["HBM"]), density_from_body(lowered, words, ["HBM"]))

    def test_an_empty_document_is_unanswered_rather_than_zero(self):
        self.assertIsNone(keyword_density("", ["HBM"]))


class SpenderCapexAliasTests(unittest.TestCase):
    def test_the_general_signal_name_is_computed_like_the_ai_specific_one(self):
        class CapexSec(_FakeSec):
            def company_concept(self, ticker, concept):
                return {"units": {"USD": [
                    {"form": "10-K", "end": "2026-01-31", "val": 200.0},
                    {"form": "10-K", "end": "2025-01-31", "val": 100.0},
                ]}}

        sec = CapexSec(_recent_filings([]), {})
        provider = EdgarThemeSignals(sec, cache=_FakeCache())

        general = provider("ACME", {"id": "general", "signals": [
            {"name": "spender_capex_growth", "universe": ["MSFT"]}]})
        ai = provider("ACME", {"id": "ai", "signals": [
            {"name": "hyperscaler_capex_growth", "universe": ["MSFT"]}]})

        self.assertAlmostEqual(general["spender_capex_growth"], 1.0)
        self.assertAlmostEqual(ai["hyperscaler_capex_growth"], 1.0)


if __name__ == "__main__":
    unittest.main()
