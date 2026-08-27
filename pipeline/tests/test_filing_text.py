import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import filing_text as ft


class HtmlToTextTests(unittest.TestCase):
    def test_strips_tags_and_scripts(self):
        html = """
        <html><head><style>.x{color:red}</style></head>
        <body>
          <script>var x = 1;</script>
          <h1>Acme Corp Reports Third Quarter Results</h1>
          <p>Comparable store sales increased 3.2% for the quarter.</p>
        </body></html>
        """
        text = ft.html_to_text(html)
        self.assertNotIn("color:red", text)
        self.assertNotIn("var x", text)
        self.assertIn("Acme Corp Reports Third Quarter Results", text)
        self.assertIn("Comparable store sales increased 3.2% for the quarter.", text)

    def test_never_raises_on_malformed_markup(self):
        self.assertEqual(ft.html_to_text("<p>unterminated"), "unterminated")
        self.assertEqual(ft.html_to_text(""), "")
        self.assertEqual(ft.html_to_text(None), "")

    def test_normalizes_whitespace_without_merging_across_newlines(self):
        html = "<p>Line one.</p>\n<p>Line   two.</p>"
        text = ft.html_to_text(html)
        self.assertIn("Line one.", text)
        self.assertIn("Line two.", text)


class ExhibitPickerTests(unittest.TestCase):
    def test_prefers_the_canonical_991_name(self):
        names = ["0001234567-26-000012-index.htm", "acme-8k.htm", "ex991.htm", "ex99-2.htm"]
        self.assertEqual(ft.pick_exhibit_document(names), "ex991.htm")

    def test_matches_the_common_filer_agent_naming_convention(self):
        names = ["tm2412345d1_8k.htm", "tm2412345d1_ex99-1.htm"]
        self.assertEqual(ft.pick_exhibit_document(names), "tm2412345d1_ex99-1.htm")

    def test_falls_back_to_a_bare_ex99_when_no_sub_number_is_present(self):
        names = ["form8k.htm", "ex99.htm"]
        self.assertEqual(ft.pick_exhibit_document(names), "ex99.htm")

    def test_returns_none_rather_than_guess_the_cover_document(self):
        names = ["0001234567-26-000012-index.htm", "acme-8k.htm", "ex101.htm"]
        self.assertIsNone(ft.pick_exhibit_document(names))

    def test_empty_listing(self):
        self.assertIsNone(ft.pick_exhibit_document([]))
        self.assertIsNone(ft.pick_exhibit_document(None))


class _FakeClient:
    def __init__(self, index_by_accession, documents):
        self.index_by_accession = index_by_accession
        self.documents = documents
        self.filing_index_calls = 0
        self.filing_document_calls = 0

    def filing_index(self, cik, accession):
        self.filing_index_calls += 1
        return self.index_by_accession[accession]

    def filing_document(self, cik, accession, document):
        self.filing_document_calls += 1
        return self.documents[(accession, document)]


class EarningsReleaseTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._original_cache_dir = ft.CACHE_DIR
        ft.CACHE_DIR = self.tmp

    def tearDown(self):
        ft.CACHE_DIR = self._original_cache_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fetches_and_caches_the_exhibit_text(self):
        client = _FakeClient(
            index_by_accession={"0001234567-26-000012": ["8k.htm", "ex991.htm"]},
            documents={("0001234567-26-000012", "ex991.htm"):
                      "<p>Comparable store sales increased 3.2%.</p>"})
        text = ft.earnings_release_text(client, "1234567", "0001234567-26-000012")
        self.assertIn("Comparable store sales increased 3.2%.", text)
        self.assertEqual(client.filing_document_calls, 1)

        # Second call reads the cache, not the network.
        text_again = ft.earnings_release_text(client, "1234567", "0001234567-26-000012")
        self.assertEqual(text_again, text)
        self.assertEqual(client.filing_document_calls, 1)

    def test_returns_none_when_no_exhibit_is_found(self):
        client = _FakeClient(index_by_accession={"acc1": ["8k.htm", "ex101.htm"]}, documents={})
        self.assertIsNone(ft.earnings_release_text(client, "1234567", "acc1"))

    def test_returns_none_rather_than_raise_on_a_fetch_failure(self):
        class _RaisingClient:
            def filing_index(self, cik, accession):
                raise TimeoutError("boom")

        self.assertIsNone(ft.earnings_release_text(_RaisingClient(), "1234567", "acc1"))


if __name__ == "__main__":
    unittest.main()
