import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import build_filings_screen as screen


class TempStore:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = screen.FILINGS_DIR
        screen.FILINGS_DIR = os.path.join(self.tmp, "filings")
        return self

    def __exit__(self, *exc):
        screen.FILINGS_DIR = self._orig


def filing(form, filed, cik="1", accession="acc-1", items=""):
    return {"cik": cik, "form": form, "accession": accession, "document": "doc.htm",
            "filed": filed, "period": "", "items": items}


class ShortlistSymbolsTests(unittest.TestCase):
    def test_combines_research_and_portfolio_coverage_tickers(self):
        payload = {
            "research": [{"ticker": "aapl"}, {"ticker": "MSFT"}],
            "portfolio_coverage": [{"ticker": "msft"}, {"ticker": "TSLA"}],
        }
        with mock.patch.object(screen, "load_json", return_value=payload):
            self.assertEqual(screen.shortlist_symbols(), ["AAPL", "MSFT", "TSLA"])

    def test_no_advisor_data_returns_empty_list(self):
        with mock.patch.object(screen, "load_json", return_value=None):
            self.assertEqual(screen.shortlist_symbols(), [])


class AppendNewFilingsTests(unittest.TestCase):
    def test_dedupes_on_symbol_cik_form_accession(self):
        with TempStore():
            first = screen.append_new_filings("AAPL", [filing("10-K", "2026-02-01")])
            second = screen.append_new_filings("AAPL", [filing("10-K", "2026-02-01")])
            different = screen.append_new_filings("AAPL", [filing("10-Q", "2026-05-01", accession="acc-2")])

            self.assertEqual(first, 1)
            self.assertEqual(second, 0)
            self.assertEqual(different, 1)
            self.assertEqual(len(screen._read_all()), 2)


class BuildResultTests(unittest.TestCase):
    def test_scores_all_three_signals_for_one_symbol(self):
        as_of = datetime(2026, 8, 17, tzinfo=timezone.utc).date()
        result = screen.build_result(
            "AAPL",
            filings_10k=[filing("10-K", "2026-02-01")],
            filings_10q=[filing("NT 10-Q", "2026-08-12")],
            filings_proxy=[filing("DEFC14A", "2026-08-01")],
            filings_8k=[filing("8-K", "2026-08-10", items="4.02")],
            as_of=as_of,
        )
        self.assertEqual(result["ticker"], "AAPL")
        self.assertLess(result["filing_integrity"]["score_points"], 0)
        self.assertLess(result["proxy_activity"]["score_points"], 0)
        self.assertLess(result["eightk_activity"]["score_points"], 0)


class RunSkipsGracefullyTests(unittest.TestCase):
    def test_no_sec_user_agent_skips_rather_than_raises(self):
        with mock.patch.object(screen, "SecEdgarClient") as fake_client_cls, \
                mock.patch.object(screen, "shortlist_symbols", return_value=["AAPL"]), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            fake_client_cls.return_value.available = False
            payload = screen.run()

        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["results"], [])
        fake_save_json.assert_called_once()

    def test_no_shortlisted_symbols_skips_rather_than_raises(self):
        with mock.patch.object(screen, "SecEdgarClient") as fake_client_cls, \
                mock.patch.object(screen, "shortlist_symbols", return_value=[]), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            fake_client_cls.return_value.available = True
            payload = screen.run()

        self.assertEqual(payload["status"], "skipped")
        fake_save_json.assert_called_once()

    def test_a_run_where_every_symbol_fails_is_degraded_not_successful(self):
        sec = mock.Mock()
        sec.available = True
        sec.recent_forms.side_effect = RuntimeError("boom")
        with mock.patch.object(screen, "SecEdgarClient", return_value=sec), \
                mock.patch.object(screen, "shortlist_symbols", return_value=["AAPL"]), \
                mock.patch.object(screen, "append_new_filings", return_value=0), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            payload = screen.run()

        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["failures"])
        fake_save_json.assert_called_once()

    def test_a_successful_run_publishes_per_symbol_results(self):
        sec = mock.Mock()
        sec.available = True
        sec.recent_forms.return_value = []
        with mock.patch.object(screen, "SecEdgarClient", return_value=sec), \
                mock.patch.object(screen, "shortlist_symbols", return_value=["AAPL"]), \
                mock.patch.object(screen, "append_new_filings", return_value=0), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            payload = screen.run()

        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["ticker"], "AAPL")
        fake_save_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
