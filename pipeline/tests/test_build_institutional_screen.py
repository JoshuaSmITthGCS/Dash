import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import build_institutional_screen as screen

MANAGERS = [
    {"ticker": "BLK", "name": "BlackRock", "style": "passive"},
    {"ticker": "TROW", "name": "T. Rowe Price", "style": "active"},
    {"ticker": "BX", "name": "Blackstone", "style": "alternative"},
    {"ticker": "APAM", "name": "Artisan Partners", "style": "active"},
]

INFO_TABLE_TEMPLATE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ACME CORP</nameOfIssuer>
    <cusip>000000001</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


class ActiveManagersTests(unittest.TestCase):
    def test_only_style_active_managers_are_selected_by_default(self):
        selected = screen.active_managers({"managers": MANAGERS})
        self.assertEqual({m["ticker"] for m in selected}, {"TROW", "APAM"})

    def test_passive_and_alternative_managers_are_excluded(self):
        selected = screen.active_managers({"managers": MANAGERS})
        tickers = {m["ticker"] for m in selected}
        self.assertNotIn("BLK", tickers)
        self.assertNotIn("BX", tickers)


class _FakeSec:
    available = True

    def __init__(self, filings_by_ticker, documents_by_accession, index_by_accession=None):
        self._filings = filings_by_ticker
        self._documents = documents_by_accession
        self._index = index_by_accession or {}

    def recent_forms(self, ticker, forms, limit=2):
        return self._filings.get(ticker, [])[:limit]

    def filing_document(self, cik, accession, document):
        return self._documents[(accession, document)] if (accession, document) in self._documents \
            else self._documents[accession]

    def filing_index(self, cik, accession):
        return self._index.get(accession, [])


class ManagerQuartersTests(unittest.TestCase):
    def test_two_distinct_periods_are_read_newest_first(self):
        filings = {"TROW": [
            {"cik": "1", "form": "13F-HR", "accession": "cur", "document": "d.xml",
             "filed": "2026-05-14", "period": "2026-03-31"},
            {"cik": "1", "form": "13F-HR", "accession": "pri", "document": "d.xml",
             "filed": "2026-02-14", "period": "2025-12-31"},
        ]}
        documents = {"cur": INFO_TABLE_TEMPLATE.format(shares=2000),
                     "pri": INFO_TABLE_TEMPLATE.format(shares=1000)}
        sec = _FakeSec(filings, documents)

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(len(quarters), 2)
        self.assertEqual(quarters[0]["period"], "2026-03-31")
        self.assertEqual(quarters[0]["holdings"][0]["shares"], 2000.0)
        self.assertFalse(quarters[0]["is_amendment"])

    def test_an_amendment_supersedes_the_original_for_the_same_period(self):
        # The original 13F-HR for Q1 and its later 13F-HR/A both cover period 2026-03-31 -
        # the amendment must win, not be counted as a third quarter.
        filings = {"TROW": [
            {"cik": "1", "form": "13F-HR/A", "accession": "amend", "document": "d.xml",
             "filed": "2026-06-01", "period": "2026-03-31"},
            {"cik": "1", "form": "13F-HR", "accession": "orig", "document": "d.xml",
             "filed": "2026-05-14", "period": "2026-03-31"},
            {"cik": "1", "form": "13F-HR", "accession": "pri", "document": "d.xml",
             "filed": "2026-02-14", "period": "2025-12-31"},
        ]}
        documents = {"amend": INFO_TABLE_TEMPLATE.format(shares=2500),
                     "orig": INFO_TABLE_TEMPLATE.format(shares=2000),
                     "pri": INFO_TABLE_TEMPLATE.format(shares=1000)}
        sec = _FakeSec(filings, documents)

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(len(quarters), 2)
        self.assertEqual(quarters[0]["period"], "2026-03-31")
        self.assertEqual(quarters[0]["holdings"][0]["shares"], 2500.0)
        self.assertTrue(quarters[0]["is_amendment"])

    def test_an_unreadable_filing_is_flagged_not_silently_dropped(self):
        filings = {"TROW": [{"cik": "1", "form": "13F-HR", "accession": "bad", "document": "d.xml",
                             "filed": "2026-05-01", "period": "2026-03-31"}]}
        sec = _FakeSec(filings, {})  # accession missing -> KeyError inside filing_document

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(quarters, [{"period": "2026-03-31", "filed": "2026-05-01",
                                     "holdings": [], "unreadable": True, "is_amendment": False}])

    def test_a_cover_page_primary_document_falls_back_to_the_info_table_exhibit(self):
        # The real-world shape this whole fallback exists for: primaryDocument is an
        # empty cover page, and the actual holdings live in a separate exhibit the
        # submissions API never names - only the filing's own directory listing does.
        filings = {"TROW": [{"cik": "1", "form": "13F-HR", "accession": "acc-1",
                             "document": "primary_doc.xml", "filed": "2026-05-14",
                             "period": "2026-03-31"}]}
        documents = {
            ("acc-1", "primary_doc.xml"): "<edgarSubmission><coverPage/></edgarSubmission>",
            ("acc-1", "InfoTable.xml"): INFO_TABLE_TEMPLATE.format(shares=2000),
        }
        sec = _FakeSec(filings, documents, index_by_accession={
            "acc-1": ["primary_doc.xml", "InfoTable.xml"],
        })

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(quarters[0]["holdings"][0]["shares"], 2000.0)
        self.assertFalse(quarters[0]["unreadable"])

    def test_no_matching_exhibit_in_the_index_yields_empty_holdings_not_unreadable(self):
        filings = {"TROW": [{"cik": "1", "form": "13F-HR", "accession": "acc-1",
                             "document": "primary_doc.xml", "filed": "2026-05-14",
                             "period": "2026-03-31"}]}
        documents = {("acc-1", "primary_doc.xml"): "<edgarSubmission><coverPage/></edgarSubmission>"}
        sec = _FakeSec(filings, documents, index_by_accession={
            "acc-1": ["primary_doc.xml", "exhibit99.xml"],
        })

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(quarters[0]["holdings"], [])
        self.assertFalse(quarters[0]["unreadable"])


class FlagForTests(unittest.TestCase):
    def test_strong_accumulation_is_flagged_as_cluster(self):
        self.assertEqual(screen.flag_for(2.0), "CLUSTER_ACCUMULATION")

    def test_mild_accumulation_is_flagged_without_cluster(self):
        self.assertEqual(screen.flag_for(0.5), "ACCUMULATION")

    def test_strong_distribution_is_flagged_as_cluster(self):
        self.assertEqual(screen.flag_for(-2.0), "CLUSTER_DISTRIBUTION")

    def test_zero_is_unflagged(self):
        self.assertIsNone(screen.flag_for(0.0))


class BuildResultsTests(unittest.TestCase):
    def test_a_ticker_outside_the_universe_is_excluded(self):
        current = {"CUSIP1": {"TROW": 200, "APAM": 200}}
        prior = {"CUSIP1": {"TROW": 100, "APAM": 100}}
        results = screen.build_results(current, prior, {"CUSIP1": "ACME"}, universe=("OTHER",))
        self.assertEqual(results, [])

    def test_a_flagged_ticker_reports_manager_breadth_and_as_of_not_a_score(self):
        current = {"CUSIP1": {"TROW": 200, "APAM": 200}}
        prior = {"CUSIP1": {"TROW": 100, "APAM": 100}}
        results = screen.build_results(current, prior, {"CUSIP1": "ACME"}, universe=("ACME",),
                                       as_of_by_cusip={"CUSIP1": "2026-05-14"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "ACME")
        self.assertEqual(results[0]["as_of"], "2026-05-14")
        self.assertNotIn("score", results[0])
        self.assertNotIn("score_points", results[0])
        self.assertIn(results[0]["flag"], {"ACCUMULATION", "CLUSTER_ACCUMULATION"})


class AppendNewPositionsTests(unittest.TestCase):
    def test_a_new_period_is_recorded_as_a_fresh_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(screen, "INSTITUTIONAL_DIR", tmp):
                first = screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 100, "filed": "2026-05-14",
                     "period": "2026-03-31"},
                ])
                second = screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 100, "filed": "2026-05-14",
                     "period": "2026-03-31"},  # identical repeat - a re-run, not new info
                    {"manager": "TROW", "cusip": "C1", "shares": 150, "filed": "2026-08-14",
                     "period": "2026-06-30"},  # a genuinely new quarter
                ])
                rows = screen._read_all()

        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["period"] for row in rows}, {"2026-03-31", "2026-06-30"})

    def test_an_amendment_changing_the_share_count_is_logged_as_a_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(screen, "INSTITUTIONAL_DIR", tmp):
                screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 2000, "filed": "2026-05-14",
                     "period": "2026-03-31", "is_amendment": False},
                ])
                screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 2500, "filed": "2026-06-01",
                     "period": "2026-03-31", "is_amendment": True},  # same period, revised
                ])
                positions = screen._read_all()
                revisions = screen._read_jsonl(screen._revisions_path())

        # Both the original and the revised value stay in history - nothing is overwritten.
        self.assertEqual(sorted(row["shares"] for row in positions), [2000, 2500])
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["previous_shares"], 2000)
        self.assertEqual(revisions[0]["current_shares"], 2500)


class RunSkipsGracefullyTests(unittest.TestCase):
    def test_an_unconfigured_client_skips_rather_than_raises(self):
        with mock.patch.object(screen, "SecEdgarClient") as fake_client_cls, \
                mock.patch.object(screen, "save_json") as fake_save_json:
            fake_client_cls.return_value.available = False
            payload = screen.run()

        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["results"], [])
        fake_save_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
