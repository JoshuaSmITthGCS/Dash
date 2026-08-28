import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import filing_extraction as fe

# Synthetic HTML modeled on the known structure of a real 8-K Exhibit 99.1 earnings release:
# a "financial highlights" table plus MD&A-style prose paragraphs. Not fetched from a live
# filing -- this session's network policy blocks sec.gov (see the module docstring).
RETAIL_EXHIBIT_HTML = """
<html><body>
<table>
  <tr><td>Net sales</td><td>$1,245.3 million</td></tr>
  <tr><td>Comparable store sales increase</td><td>3.2%</td></tr>
  <tr><td>Gross margin</td><td>41.6%</td></tr>
</table>
<p>Comparable store sales increased 3.2% for the fiscal quarter, driven by traffic growth
across all regions.</p>
</body></html>
"""

BANK_EXHIBIT_HTML = """
<html><body>
<table>
  <tr><th>Metric</th><th>Q2 2026</th><th>Q1 2026</th></tr>
  <tr><td>Net interest margin</td><td>3.15%</td><td>3.09%</td></tr>
  <tr><td>Efficiency ratio</td><td>54.2%</td><td>55.0%</td></tr>
</table>
</body></html>
"""

TELECOM_EXHIBIT_HTML = """
<html><body>
<p>Postpaid phone ARPU of $46.50, up 2.1% year over year.</p>
<p>Postpaid phone churn was 0.85% for the quarter, an improvement of 5 basis points.</p>
</body></html>
"""

NO_MATCH_HTML = "<html><body><p>This press release contains forward-looking statements.</p></body></html>"


class HtmlToLinesTests(unittest.TestCase):
    def test_table_rows_stay_on_one_line(self):
        lines = fe.html_to_lines(RETAIL_EXHIBIT_HTML)
        self.assertIn("Comparable store sales increase | 3.2%", lines)

    def test_paragraphs_are_captured_as_their_own_lines(self):
        lines = fe.html_to_lines(RETAIL_EXHIBIT_HTML)
        self.assertTrue(any("Comparable store sales increased 3.2%" in line for line in lines))

    def test_empty_html_returns_no_lines(self):
        self.assertEqual(fe.html_to_lines(""), [])


class ExtractKpisTests(unittest.TestCase):
    def test_extracts_same_store_sales_from_a_table_row(self):
        lines = fe.html_to_lines(RETAIL_EXHIBIT_HTML)
        result = fe.extract_kpis(lines, ["same_store_sales_growth"])
        self.assertAlmostEqual(result["same_store_sales_growth"]["value"], 0.032, places=4)
        self.assertIn("3.2%", result["same_store_sales_growth"]["evidence_line"])

    def test_extracts_bank_metrics_from_a_multi_column_table(self):
        lines = fe.html_to_lines(BANK_EXHIBIT_HTML)
        result = fe.extract_kpis(lines, ["net_interest_margin", "efficiency_ratio"])
        self.assertAlmostEqual(result["net_interest_margin"]["value"], 0.0315, places=4)
        self.assertAlmostEqual(result["efficiency_ratio"]["value"], 0.542, places=4)

    def test_extracts_telecom_metrics_from_prose(self):
        lines = fe.html_to_lines(TELECOM_EXHIBIT_HTML)
        result = fe.extract_kpis(lines, ["average_revenue_per_user", "postpaid_churn"])
        self.assertAlmostEqual(result["average_revenue_per_user"]["value"], 46.50, places=2)
        self.assertAlmostEqual(result["postpaid_churn"]["value"], 0.0085, places=4)

    def test_a_metric_with_no_matching_line_is_simply_absent(self):
        lines = fe.html_to_lines(NO_MATCH_HTML)
        result = fe.extract_kpis(lines, ["net_interest_margin"])
        self.assertNotIn("net_interest_margin", result)

    def test_unknown_metric_id_is_ignored_not_an_error(self):
        lines = fe.html_to_lines(RETAIL_EXHIBIT_HTML)
        result = fe.extract_kpis(lines, ["not_a_real_metric"])
        self.assertEqual(result, {})


class _FakeSecClient:
    """Mirrors the three SecEdgarClient methods find/extract need -- no network."""

    def __init__(self, filings, index_by_accession, documents_by_key):
        self._filings = filings
        self._index_by_accession = index_by_accession
        self._documents_by_key = documents_by_key

    def recent_forms(self, ticker, forms, limit=4):
        return self._filings[:limit]

    def filing_index(self, cik, accession):
        return self._index_by_accession.get(accession, [])

    def filing_document(self, cik, accession, document):
        return self._documents_by_key[(accession, document)]


class FindExhibitDocumentsTests(unittest.TestCase):
    def test_matches_exhibit_99_style_filenames_and_skips_the_rest(self):
        client = _FakeSecClient(
            filings=[{"cik": 123, "accession": "0001-26-000001", "form": "8-K", "filed": "2026-08-01"}],
            index_by_accession={"0001-26-000001": ["a-8k.htm", "a-ex991.htm", "a-ex311.htm"]},
            documents_by_key={},
        )
        enriched = fe.find_exhibit_documents(client, "FAKE")
        self.assertEqual(enriched[0]["documents"], ["a-ex991.htm"])

    def test_a_filing_with_no_exhibit_99_has_an_empty_documents_list(self):
        client = _FakeSecClient(
            filings=[{"cik": 123, "accession": "0001-26-000002", "form": "8-K", "filed": "2026-08-01"}],
            index_by_accession={"0001-26-000002": ["a-8k.htm", "a-ex311.htm"]},
            documents_by_key={},
        )
        enriched = fe.find_exhibit_documents(client, "FAKE")
        self.assertEqual(enriched[0]["documents"], [])

    def test_an_unreadable_index_does_not_sink_the_batch(self):
        class _RaisingClient(_FakeSecClient):
            def filing_index(self, cik, accession):
                raise RuntimeError("EDGAR unavailable")

        client = _RaisingClient(
            filings=[{"cik": 123, "accession": "0001-26-000003", "form": "8-K", "filed": "2026-08-01"}],
            index_by_accession={}, documents_by_key={},
        )
        enriched = fe.find_exhibit_documents(client, "FAKE")
        self.assertEqual(enriched[0]["documents"], [])


class ExtractOperatingKpisForTickerTests(unittest.TestCase):
    def test_end_to_end_against_a_fake_client(self):
        client = _FakeSecClient(
            filings=[{"cik": 123, "accession": "0001-26-000004", "form": "8-K", "filed": "2026-08-06"}],
            index_by_accession={"0001-26-000004": ["a-8k.htm", "a-ex991.htm"]},
            documents_by_key={("0001-26-000004", "a-ex991.htm"): BANK_EXHIBIT_HTML},
        )
        results, attempted = fe.extract_operating_kpis_for_ticker(
            client, "FAKE", ["net_interest_margin", "efficiency_ratio"])
        self.assertEqual(attempted, 1)
        self.assertAlmostEqual(results["net_interest_margin"]["value"], 0.0315, places=4)
        self.assertEqual(results["net_interest_margin"]["filed"], "2026-08-06")

    def test_stops_once_every_requested_metric_is_found(self):
        # Two exhibits available; the first already satisfies both metrics, so the second's
        # filing_document must never be called (a stray key would raise KeyError if it were).
        client = _FakeSecClient(
            filings=[
                {"cik": 123, "accession": "0001-26-000005", "form": "8-K", "filed": "2026-08-06"},
                {"cik": 123, "accession": "0001-26-000006", "form": "8-K", "filed": "2026-05-05"},
            ],
            index_by_accession={
                "0001-26-000005": ["a-ex991.htm"],
                "0001-26-000006": ["b-ex991.htm"],
            },
            documents_by_key={("0001-26-000005", "a-ex991.htm"): BANK_EXHIBIT_HTML},
        )
        results, attempted = fe.extract_operating_kpis_for_ticker(
            client, "FAKE", ["net_interest_margin", "efficiency_ratio"])
        self.assertEqual(attempted, 1)
        self.assertEqual(set(results), {"net_interest_margin", "efficiency_ratio"})

    def test_an_unreadable_exhibit_does_not_sink_the_batch(self):
        class _RaisingClient(_FakeSecClient):
            def filing_document(self, cik, accession, document):
                raise RuntimeError("EDGAR unavailable")

        client = _RaisingClient(
            filings=[{"cik": 123, "accession": "0001-26-000007", "form": "8-K", "filed": "2026-08-06"}],
            index_by_accession={"0001-26-000007": ["a-ex991.htm"]}, documents_by_key={},
        )
        results, attempted = fe.extract_operating_kpis_for_ticker(client, "FAKE", ["net_interest_margin"])
        self.assertEqual(results, {})
        self.assertEqual(attempted, 1)


class CollectOperatingKpiSignalsTests(unittest.TestCase):
    def test_routes_each_ticker_to_its_profiles_metric_set(self):
        client = _FakeSecClient(
            filings=[{"cik": 123, "accession": "0001-26-000008", "form": "8-K", "filed": "2026-08-06"}],
            index_by_accession={"0001-26-000008": ["a-ex991.htm"]},
            documents_by_key={("0001-26-000008", "a-ex991.htm"): BANK_EXHIBIT_HTML},
        )
        results, diagnostics = fe.collect_operating_kpi_signals(
            client, ["BANKCO"],
            metrics_by_profile={"bank": ["net_interest_margin"], "general": ["average_revenue_per_user"]},
            profile_for_ticker=lambda ticker: "bank")
        self.assertIn("BANKCO", results)
        self.assertTrue(results["BANKCO"]["net_interest_margin"]["unaudited"])
        self.assertEqual(diagnostics["resolved_tickers"], 1)

    def test_unavailable_client_returns_nothing(self):
        class _Unavailable:
            available = False

        results, diagnostics = fe.collect_operating_kpi_signals(
            _Unavailable(), ["ANY"], metrics_by_profile={"general": ["net_interest_margin"]},
            profile_for_ticker=lambda ticker: "general")
        self.assertEqual(results, {})
        self.assertEqual(diagnostics["attempted"], 0)

    def test_falls_back_to_general_metrics_for_an_unlisted_profile(self):
        client = _FakeSecClient(
            filings=[{"cik": 123, "accession": "0001-26-000009", "form": "8-K", "filed": "2026-08-06"}],
            index_by_accession={"0001-26-000009": ["a-ex991.htm"]},
            documents_by_key={("0001-26-000009", "a-ex991.htm"): RETAIL_EXHIBIT_HTML},
        )
        results, _ = fe.collect_operating_kpi_signals(
            client, ["RETAILCO"],
            metrics_by_profile={"general": ["same_store_sales_growth"]},
            profile_for_ticker=lambda ticker: "reit")  # a profile absent from metrics_by_profile
        self.assertIn("RETAILCO", results)

    def test_a_tickers_edgar_failure_does_not_sink_the_batch(self):
        class _RaisingClient(_FakeSecClient):
            def recent_forms(self, ticker, forms, limit=4):
                raise RuntimeError("EDGAR unavailable")

        client = _RaisingClient(filings=[], index_by_accession={}, documents_by_key={})
        results, diagnostics = fe.collect_operating_kpi_signals(
            client, ["BROKEN"], metrics_by_profile={"general": ["net_interest_margin"]},
            profile_for_ticker=lambda ticker: "general")
        self.assertEqual(results, {})
        self.assertEqual(diagnostics["resolved_tickers"], 0)


class SummarizeExtractionCoverageTests(unittest.TestCase):
    def test_computes_per_metric_resolution_rate(self):
        results_by_ticker = {
            "AAA": {"net_interest_margin": {"value": 0.03}},
            "BBB": {"net_interest_margin": {"value": 0.031}, "efficiency_ratio": {"value": 0.55}},
            "CCC": {},
        }
        coverage = fe.summarize_extraction_coverage(
            results_by_ticker, ["net_interest_margin", "efficiency_ratio"])
        self.assertAlmostEqual(coverage["net_interest_margin"], 2 / 3, places=4)
        self.assertAlmostEqual(coverage["efficiency_ratio"], 1 / 3, places=4)

    def test_empty_batch_does_not_divide_by_zero(self):
        coverage = fe.summarize_extraction_coverage({}, ["net_interest_margin"])
        self.assertEqual(coverage["net_interest_margin"], 0.0)


if __name__ == "__main__":
    unittest.main()
