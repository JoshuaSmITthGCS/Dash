import unittest
from unittest.mock import Mock, patch

from marketstack import MarketstackClient, MarketstackError, MarketstackPlanRestricted


class MarketstackClientTests(unittest.TestCase):
    def test_requires_an_api_key(self):
        with self.assertRaises(MarketstackError):
            MarketstackClient(api_key="")

    @patch("marketstack.requests.get")
    def test_eod_latest_batches_every_symbol_into_one_request(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"data": [
            {"symbol": "AAPL", "close": 200.1}, {"symbol": "MSFT", "close": 410.2},
        ]})
        client = MarketstackClient(api_key="key")

        rows = client.eod_latest(["aapl", "msft"])

        self.assertEqual(len(rows), 2)
        self.assertEqual(get.call_count, 1)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["symbols"], "AAPL,MSFT")

    @patch("marketstack.requests.get")
    def test_intraday_raises_plan_restricted_on_403_function_access_restricted(self, get):
        get.return_value = Mock(status_code=403, content=b"x", json=lambda: {
            "error": {"code": "function_access_restricted", "message": "not on this plan"}})
        client = MarketstackClient(api_key="key")

        with self.assertRaises(MarketstackPlanRestricted):
            client.intraday(["AAPL"])

    @patch("marketstack.requests.get")
    def test_other_403_is_a_generic_error_not_plan_restricted(self, get):
        get.return_value = Mock(status_code=403, content=b"x", json=lambda: {
            "error": {"code": "unauthorized", "message": "bad key"}})
        client = MarketstackClient(api_key="key")

        with self.assertRaises(MarketstackError):
            client.eod_latest(["AAPL"])

    @patch("marketstack.requests.get")
    def test_http_error_does_not_expose_the_access_key(self, get):
        get.return_value = Mock(status_code=500, content=b"")
        client = MarketstackClient(api_key="super-secret-key")

        with self.assertRaisesRegex(MarketstackError, r"HTTP 500") as raised:
            client.eod_latest(["AAPL"])
        self.assertNotIn("super-secret-key", str(raised.exception))

    def test_batching_chunks_beyond_the_per_request_symbol_cap(self):
        calls = []

        def fake_get(path, **params):
            calls.append(params["symbols"].split(","))
            return [{"symbol": symbol} for symbol in params["symbols"].split(",")]

        client = MarketstackClient(api_key="key")
        client._get = fake_get  # noqa: SLF001 - exercising the batching helper directly
        symbols = [f"T{i}" for i in range(150)]

        rows = client.eod_latest(symbols)

        self.assertEqual(len(rows), 150)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0]), 100)
        self.assertEqual(len(calls[1]), 50)


if __name__ == "__main__":
    unittest.main()
