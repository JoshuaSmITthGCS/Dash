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

    def __init__(self, filings_by_ticker, documents_by_accession):
        self._filings = filings_by_ticker
        self._documents = documents_by_accession

    def recent_forms(self, ticker, forms, limit=2):
        return self._filings.get(ticker, [])

    def filing_document(self, cik, accession, document):
        return self._documents[accession]


class ManagerQuartersTests(unittest.TestCase):
    def test_two_quarters_are_read_newest_first(self):
        filings = {"TROW": [
            {"cik": "1", "accession": "cur", "document": "d.xml", "filed": "2026-05-01"},
            {"cik": "1", "accession": "pri", "document": "d.xml", "filed": "2026-02-01"},
        ]}
        documents = {"cur": INFO_TABLE_TEMPLATE.format(shares=2000),
                     "pri": INFO_TABLE_TEMPLATE.format(shares=1000)}
        sec = _FakeSec(filings, documents)

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(len(quarters), 2)
        self.assertEqual(quarters[0]["filed"], "2026-05-01")
        self.assertEqual(quarters[0]["holdings"][0]["shares"], 2000.0)

    def test_an_unreadable_filing_is_flagged_not_silently_dropped(self):
        filings = {"TROW": [{"cik": "1", "accession": "bad", "document": "d.xml", "filed": "2026-05-01"}]}
        sec = _FakeSec(filings, {})  # accession missing -> KeyError inside filing_document

        quarters = screen.manager_quarters(sec, {"ticker": "TROW"})

        self.assertEqual(quarters, [{"filed": "2026-05-01", "holdings": [], "unreadable": True}])


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

    def test_a_flagged_ticker_reports_manager_breadth_not_a_score(self):
        current = {"CUSIP1": {"TROW": 200, "APAM": 200}}
        prior = {"CUSIP1": {"TROW": 100, "APAM": 100}}
        results = screen.build_results(current, prior, {"CUSIP1": "ACME"}, universe=("ACME",))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "ACME")
        self.assertNotIn("score", results[0])
        self.assertNotIn("score_points", results[0])
        self.assertIn(results[0]["flag"], {"ACCUMULATION", "CLUSTER_ACCUMULATION"})


class AppendNewPositionsTests(unittest.TestCase):
    def test_positions_are_keyed_by_manager_cusip_and_filed_date_not_period_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(screen, "INSTITUTIONAL_DIR", tmp):
                first = screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 100, "filed": "2026-05-01"},
                ])
                second = screen.append_new_positions([
                    {"manager": "TROW", "cusip": "C1", "shares": 100, "filed": "2026-05-01"},
                    {"manager": "TROW", "cusip": "C1", "shares": 150, "filed": "2026-08-01"},
                ])
                rows = screen._read_all()

        self.assertEqual(first, 1)
        self.assertEqual(second, 1)  # only the new filing date is new
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["filed"] for row in rows}, {"2026-05-01", "2026-08-01"})


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
