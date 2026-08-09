import unittest
from unittest.mock import Mock, patch

from congress_trades import (CongressTradesClient, CongressTradesError, StockWatcherClient,
                             normalize_date)


class NormalizeDateTests(unittest.TestCase):
    """Every date comparison downstream - the publish window, the late-filing flag, the
    price lookup - is a string compare, so a mixed format sorts and filters wrong instead
    of raising."""

    def test_us_slash_dates_become_iso(self):
        self.assertEqual(normalize_date("10/04/2021"), "2021-10-04")
        self.assertEqual(normalize_date("1/2/2021"), "2021-01-02")

    def test_iso_dates_pass_through_and_are_truncated_to_the_day(self):
        self.assertEqual(normalize_date("2026-07-15"), "2026-07-15")
        self.assertEqual(normalize_date("2026-07-15T00:00:00"), "2026-07-15")

    def test_unparseable_and_blank_values_become_none(self):
        for value in (None, "", "--", "not a date"):
            self.assertIsNone(normalize_date(value))


class StockWatcherClientTests(unittest.TestCase):
    HOUSE_ROW = {
        "disclosure_date": "10/04/2021", "transaction_date": "09/27/2021", "owner": "joint",
        "ticker": "bp", "asset_description": "BP plc", "type": "purchase",
        "amount": "$1,001 - $15,000", "representative": "Hon. Virginia Foxx",
        "district": "NC05", "ptr_link": "https://example.com/ptr",
    }
    SENATE_ROW = {
        "disclosure_date": "11/02/2021", "transaction_date": "10/04/2021", "owner": "Spouse",
        "ticker": "AAPL", "asset_description": "Apple Inc", "asset_type": "Stock",
        "type": "Purchase", "amount": "$1,001 - $15,000", "senator": "Thomas H Tuberville",
        "comment": "--", "ptr_link": "https://example.com/senate",
    }

    def test_house_rows_are_normalized_to_the_shared_shape(self):
        client = StockWatcherClient(opener=lambda url: [self.HOUSE_ROW])
        rows, seen = client.house_latest()

        self.assertEqual(seen, 1)
        self.assertEqual(rows[0]["chamber"], "house")
        self.assertEqual(rows[0]["representative"], "Hon. Virginia Foxx")
        self.assertEqual(rows[0]["symbol"], "BP")          # upper-cased from the scrape
        self.assertEqual(rows[0]["transaction_date"], "2021-09-27")
        self.assertEqual(rows[0]["disclosure_date"], "2021-10-04")
        self.assertEqual(rows[0]["link"], "https://example.com/ptr")

    def test_the_senate_dataset_names_the_member_differently_and_still_parses(self):
        client = StockWatcherClient(opener=lambda url: [self.SENATE_ROW])
        rows, _ = client.senate_latest()

        self.assertEqual(rows[0]["representative"], "Thomas H Tuberville")
        self.assertEqual(rows[0]["asset_type"], "Stock")
        self.assertIsNone(rows[0]["comment"])   # "--" is the mirrors' null, not a comment

    def test_rows_with_no_disclosure_date_are_dropped_rather_than_published_undated(self):
        client = StockWatcherClient(opener=lambda url: [
            {**self.HOUSE_ROW, "disclosure_date": "--"}, self.HOUSE_ROW])
        rows, seen = client.house_latest()

        self.assertEqual((len(rows), seen), (1, 2))

    def test_a_transport_failure_is_raised_as_a_congress_trades_error(self):
        def boom(url):
            raise OSError("connection reset")

        with self.assertRaises(CongressTradesError):
            StockWatcherClient(opener=boom).house_latest()

    def test_a_non_list_payload_is_rejected_rather_than_read_as_empty(self):
        client = StockWatcherClient(opener=lambda url: {"message": "forbidden"})
        with self.assertRaises(CongressTradesError):
            client.senate_latest()


class CongressTradesClientTests(unittest.TestCase):
    def test_requires_an_api_key(self):
        with self.assertRaises(CongressTradesError):
            CongressTradesClient(api_key="")

    @patch("congress_trades.requests.get")
    def test_senate_latest_normalizes_fields(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [{
            "symbol": "AAPL", "disclosureDate": "2026-08-01", "transactionDate": "2026-07-15",
            "firstName": "Jane", "lastName": "Doe", "office": "Jane Doe", "owner": "Spouse",
            "type": "Purchase", "amount": "$15,001 - $50,000", "link": "https://example.com/a",
        }])
        client = CongressTradesClient(api_key="key")

        rows = client.senate_latest()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["chamber"], "senate")
        self.assertEqual(row["representative"], "Jane Doe")
        self.assertEqual(row["transaction_type"], "Purchase")
        self.assertEqual(row["amount"], "$15,001 - $50,000")
        self.assertEqual(row["transaction_date"], "2026-07-15")
        self.assertEqual(row["disclosure_date"], "2026-08-01")

    @patch("congress_trades.requests.get")
    def test_house_latest_falls_back_to_first_last_name_when_office_is_missing(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [{
            "symbol": "MSFT", "firstName": "John", "lastName": "Smith",
            "district": "TX-01", "type": "Sale", "amount": "$1,001 - $15,000",
        }])
        client = CongressTradesClient(api_key="key")

        rows = client.house_latest()

        self.assertEqual(rows[0]["representative"], "John Smith")
        self.assertEqual(rows[0]["chamber"], "house")
        self.assertEqual(rows[0]["district"], "TX-01")

    @patch("congress_trades.requests.get")
    def test_http_error_does_not_expose_the_api_key(self, get):
        get.return_value = Mock(status_code=401, json=lambda: {})
        client = CongressTradesClient(api_key="super-secret-key")

        with self.assertRaisesRegex(CongressTradesError, r"HTTP 401") as raised:
            client.senate_latest()
        self.assertNotIn("super-secret-key", str(raised.exception))

    @patch("congress_trades.requests.get")
    def test_error_payload_message_is_surfaced(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"Error Message": "Invalid API KEY."})
        client = CongressTradesClient(api_key="key")

        with self.assertRaisesRegex(CongressTradesError, "Invalid API KEY"):
            client.senate_latest()

    @patch("congress_trades.requests.get")
    def test_price_history_sorts_oldest_first_and_falls_back_to_price_field(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [
            {"date": "2026-07-15", "close": 200.0},
            {"date": "2026-07-10", "price": 195.0},
        ])
        client = CongressTradesClient(api_key="key")

        points = client.price_history("AAPL", from_date="2026-07-01")

        self.assertEqual(points, [
            {"date": "2026-07-10", "close": 195.0},
            {"date": "2026-07-15", "close": 200.0},
        ])

    @patch("congress_trades.requests.get")
    def test_price_history_skips_rows_missing_a_date_or_close(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [
            {"date": "2026-07-15", "close": 200.0},
            {"date": None, "close": 100.0},
            {"date": "2026-07-16"},
        ])
        client = CongressTradesClient(api_key="key")

        points = client.price_history("AAPL")

        self.assertEqual(points, [{"date": "2026-07-15", "close": 200.0}])


if __name__ == "__main__":
    unittest.main()
