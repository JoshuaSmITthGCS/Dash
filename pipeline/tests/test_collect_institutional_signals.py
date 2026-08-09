import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import collect_institutional_signals


def _screen(results, generated_at="2026-05-20T00:00:00+00:00"):
    return {"status": "success", "generated_at": generated_at, "results": results}


class CollectInstitutionalSignalsTests(unittest.TestCase):
    def test_a_fresh_filing_scores_close_to_the_undecayed_magnitude(self):
        payload = _screen([{"ticker": "ACME", "undecayed_magnitude": 2.0, "as_of": "2026-05-14",
                            "notes": ["2 curated institutional manager(s) added a position"]}])

        signals, diagnostics = collect_institutional_signals(
            ("ACME",), as_of=date(2026, 5, 15), screen_payload=payload)

        self.assertIn("ACME", signals)
        self.assertGreater(signals["ACME"]["score_points"], 1.9)
        self.assertEqual(diagnostics["tickers_matched"], 1)

    def test_a_stale_filing_scores_less_than_a_fresh_one(self):
        payload = _screen([{"ticker": "ACME", "undecayed_magnitude": 2.0, "as_of": "2026-01-01",
                            "notes": []}])

        signals, _ = collect_institutional_signals(
            ("ACME",), as_of=date(2026, 5, 15), screen_payload=payload)

        # 134 days old, still under the default 135d max_age but heavily decayed.
        self.assertLess(signals["ACME"]["score_points"], 0.3)

    def test_a_ticker_outside_the_requested_universe_is_excluded(self):
        payload = _screen([{"ticker": "OTHER", "undecayed_magnitude": 2.0, "as_of": "2026-05-14"}])

        signals, _ = collect_institutional_signals(
            ("ACME",), as_of=date(2026, 5, 15), screen_payload=payload)

        self.assertEqual(signals, {})

    def test_a_skipped_screen_returns_empty_and_marks_itself_unavailable(self):
        signals, diagnostics = collect_institutional_signals(
            ("ACME",), screen_payload={"status": "skipped", "results": []})

        self.assertEqual(signals, {})
        self.assertFalse(diagnostics["screen_available"])

    def test_a_missing_as_of_or_magnitude_is_skipped_rather_than_guessed(self):
        payload = _screen([
            {"ticker": "A", "undecayed_magnitude": 2.0, "as_of": None},
            {"ticker": "B", "undecayed_magnitude": None, "as_of": "2026-05-14"},
        ])

        signals, _ = collect_institutional_signals(
            ("A", "B"), as_of=date(2026, 5, 15), screen_payload=payload)

        self.assertEqual(signals, {})


if __name__ == "__main__":
    unittest.main()
