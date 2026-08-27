import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import collect_operating_kpis as cok
import filing_text as ft


class _FakeClient:
    """Returns a fixed, realistic earnings-release exhibit for every accession asked."""

    def __init__(self, comparable_sales_text="Comparable store sales increased 3.4% for the quarter."):
        self.comparable_sales_text = comparable_sales_text
        self.filing_index_calls = []
        self.filing_document_calls = []

    def filing_index(self, cik, accession):
        self.filing_index_calls.append((cik, accession))
        return ["8k.htm", "ex991.htm"]

    def filing_document(self, cik, accession, document):
        self.filing_document_calls.append((cik, accession, document))
        return f"<html><body><p>{self.comparable_sales_text}</p></body></html>"


class CollectAgainstRealReleaseHistoryTests(unittest.TestCase):
    """Uses the real, committed earnings_releases.jsonl and entity_map.json (both already in
    the repo, no network) to exercise CIK resolution, release lookup, and file writing exactly
    as production would -- only the exhibit fetch itself is faked, since SEC EDGAR is not
    reachable from this test environment.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmp, "operating_kpis.jsonl")
        self.cache_dir = os.path.join(self.tmp, "filing_text_cache")
        self._original_cache_dir = ft.CACHE_DIR
        ft.CACHE_DIR = self.cache_dir

    def tearDown(self):
        ft.CACHE_DIR = self._original_cache_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolves_real_ciks_and_writes_a_matched_record(self):
        client = _FakeClient()
        summary = cok.collect(client, {"WMT": "retail", "MCD": "restaurant"}, path=self.store_path)
        self.assertEqual(summary["symbols_configured"], 2)
        self.assertGreaterEqual(summary["matched"], 1)
        with open(self.store_path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        self.assertTrue(any(row["ticker"] == "WMT" and row["comparable_sales_growth"] == 0.034
                            for row in rows))
        # Real CIKs, not placeholders.
        wmt_row = next(row for row in rows if row["ticker"] == "WMT")
        self.assertEqual(wmt_row["cik"], "0000104169")

    def test_an_unresolvable_ticker_is_recorded_as_failed_not_raised(self):
        client = _FakeClient()
        summary = cok.collect(client, {"NOTATICKER123": "retail"}, path=self.store_path)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["failed"][0]["error"], "no_cik")

    def test_rerunning_skips_accessions_already_on_disk(self):
        client = _FakeClient()
        cok.collect(client, {"WMT": "retail"}, path=self.store_path)
        first_document_calls = len(client.filing_document_calls)
        cok.collect(client, {"WMT": "retail"}, path=self.store_path)
        self.assertEqual(len(client.filing_document_calls), first_document_calls)

    def test_a_release_with_no_matching_phrase_is_recorded_with_its_status(self):
        client = _FakeClient(comparable_sales_text="Net income for the quarter was $1.2 billion.")
        summary = cok.collect(client, {"WMT": "retail"}, path=self.store_path)
        self.assertEqual(summary["matched"], 0)
        with open(self.store_path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        self.assertEqual(rows[0]["status"], "not_found")
        self.assertIsNone(rows[0]["comparable_sales_growth"])


class ReportTests(unittest.TestCase):
    def test_report_on_an_empty_store(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as handle:
            path = handle.name
        os.unlink(path)  # report() must tolerate a store that doesn't exist yet
        result = cok.report(path)
        self.assertEqual(result["symbols_with_any_attempt"], 0)
        self.assertIsNone(result["match_rate_of_attempted"])
        self.assertGreater(result["symbols_configured"], 0)  # from the real config file


if __name__ == "__main__":
    unittest.main()
