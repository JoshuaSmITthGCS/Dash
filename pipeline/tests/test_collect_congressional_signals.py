import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import collect_congressional_signals


def _screen(results):
    return {"status": "success", "results": results}


def _row(symbol="ACME", representative="Rep A", transaction_type="Purchase",
        disclosure_date="2026-08-01", flags=None):
    return {
        "symbol": symbol, "representative": representative, "transaction_type": transaction_type,
        "disclosure_date": disclosure_date, "transaction_date": disclosure_date,
        "amount_lower": 15001, "flags": flags or [],
    }


class CollectCongressionalSignalsTests(unittest.TestCase):
    def test_a_disclosed_purchase_produces_a_positive_signal(self):
        payload = _screen([_row()])

        signals, diagnostics = collect_congressional_signals(
            ("ACME",), as_of=date(2026, 8, 9), screen_payload=payload)

        self.assertIn("ACME", signals)
        self.assertGreater(signals["ACME"]["score_points"], 0.0)
        self.assertEqual(diagnostics["tickers_matched"], 1)

    def test_a_ticker_outside_the_requested_universe_is_excluded(self):
        payload = _screen([_row(symbol="OTHER")])

        signals, _ = collect_congressional_signals(
            ("ACME",), as_of=date(2026, 8, 9), screen_payload=payload)

        self.assertEqual(signals, {})

    def test_an_empty_screen_returns_empty_and_marks_itself_unavailable(self):
        signals, diagnostics = collect_congressional_signals(
            ("ACME",), screen_payload={"status": "success", "results": []})

        self.assertEqual(signals, {})
        self.assertFalse(diagnostics["screen_available"])

    def test_a_sale_produces_no_signal(self):
        payload = _screen([_row(transaction_type="Sale")])

        signals, _ = collect_congressional_signals(
            ("ACME",), as_of=date(2026, 8, 9), screen_payload=payload)

        self.assertEqual(signals, {})


if __name__ == "__main__":
    unittest.main()
