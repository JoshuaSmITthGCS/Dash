import unittest
from unittest.mock import Mock, patch

from congress_trades import CongressTradesClient, CongressTradesError


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
