import unittest
from datetime import date
from unittest import mock

import build_inside_information_screen as screen


def congress_row(**overrides):
    base = {"symbol": "AAPL", "representative": "Jane Doe", "transaction_type": "Purchase",
            "asset_type": "Stock", "transaction_date": "2026-06-01",
            "disclosure_date": "2026-06-20", "amount_lower": 15001.0, "flags": []}
    base.update(overrides)
    return base


def institutional_row(**overrides):
    base = {"ticker": "AAPL", "flag": None, "undecayed_magnitude": 0.0, "as_of": "2026-05-14",
            "managers_added": 0, "managers_dropped": 0}
    base.update(overrides)
    return base


class CongressFlagsByTickerTests(unittest.TestCase):
    def test_collects_only_notable_flags_across_a_tickers_rows(self):
        rows = [
            congress_row(symbol="AAPL", flags=["LATE_FILING"]),
            congress_row(symbol="AAPL", flags=["CLUSTER_TRADE", "CONCENTRATED_SIZE"]),
            congress_row(symbol="MSFT", flags=["EXTRAORDINARY_BUY"]),
        ]
        by_ticker = screen.congress_flags_by_ticker(rows)
        self.assertEqual(by_ticker["AAPL"], {"CLUSTER_TRADE"})
        self.assertEqual(by_ticker["MSFT"], {"EXTRAORDINARY_BUY"})

    def test_a_ticker_with_no_notable_flags_is_absent(self):
        rows = [congress_row(symbol="AAPL", flags=["LATE_FILING", "SAME_SECTOR_REPEAT"])]
        self.assertEqual(screen.congress_flags_by_ticker(rows), {})


class FilterNotableTests(unittest.TestCase):
    def test_cluster_institutional_flag_is_notable(self):
        ranked = [{"ticker": "AAPL", "institutional_flag": "CLUSTER_ACCUMULATION"}]
        result = screen.filter_notable(ranked, {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["congress_flags"], [])

    def test_plain_accumulation_flag_is_not_notable(self):
        # ACCUMULATION (one manager) is weaker than CLUSTER_ACCUMULATION (several) - only
        # the cluster tier clears the bar build_inside_information_screen applies.
        ranked = [{"ticker": "AAPL", "institutional_flag": "ACCUMULATION"}]
        self.assertEqual(screen.filter_notable(ranked, {}), [])

    def test_a_notable_congress_flag_alone_is_enough(self):
        ranked = [{"ticker": "AAPL", "institutional_flag": None}]
        result = screen.filter_notable(ranked, {"AAPL": {"CLUSTER_TRADE"}})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["congress_flags"], ["CLUSTER_TRADE"])

    def test_neither_side_notable_drops_the_row(self):
        ranked = [{"ticker": "AAPL", "institutional_flag": "DISTRIBUTION"}]
        self.assertEqual(screen.filter_notable(ranked, {}), [])


class RunTests(unittest.TestCase):
    def test_no_source_data_skips_rather_than_raises(self):
        with mock.patch.object(screen, "load_json", return_value={}), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            payload = screen.run()

        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["results"], [])
        fake_save_json.assert_called_once()

    def test_a_successful_run_publishes_only_notable_rows(self):
        congress_payload = {"generated_at": "2026-08-15T00:00:00Z", "status": "success",
                            "results": [congress_row(symbol="AAPL", flags=["CLUSTER_TRADE"]),
                                       congress_row(symbol="TSLA", flags=["LATE_FILING"])]}
        institutional_payload = {"generated_at": "2026-08-01T00:00:00Z", "status": "success",
                                 "results": [institutional_row(ticker="TSLA",
                                                               flag="DISTRIBUTION")]}

        def fake_load_json(name):
            if name == "screens/congress-trades.json":
                return congress_payload
            if name == "screens/institutional-13f.json":
                return institutional_payload
            return {}

        with mock.patch.object(screen, "load_json", side_effect=fake_load_json), \
                mock.patch.object(screen, "shortlist_symbols", return_value=["AAPL", "TSLA"]), \
                mock.patch.object(screen, "save_json") as fake_save_json:
            payload = screen.run()

        self.assertEqual(payload["status"], "success")
        tickers = {row["ticker"] for row in payload["results"]}
        self.assertIn("AAPL", tickers)  # notable via CLUSTER_TRADE
        self.assertNotIn("TSLA", tickers)  # DISTRIBUTION alone is not notable
        self.assertEqual(set(payload["by_ticker"]), tickers)
        fake_save_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
