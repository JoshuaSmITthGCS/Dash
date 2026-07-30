import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from marketaux import MarketauxClient, MarketauxError, advisor_articles


class MarketauxTests(unittest.TestCase):
    def test_advisor_articles_maps_entity_sentiment(self):
        payload = {"data": [{
            "title": "Chip demand rises",
            "url": "https://example.com/story",
            "source": "example.com",
            "published_at": "2026-07-30T12:00:00Z",
            "description": "Demand improved.",
            "entities": [
                {"symbol": "AMD", "sentiment_score": 0.4, "match_score": 18.2},
                {"symbol": "NVDA", "sentiment_score": 0.2, "match_score": 12.1},
            ],
        }]}

        rows = advisor_articles(payload, "AMD")

        self.assertEqual(rows, [])

    def test_advisor_articles_maps_strong_primary_entity_sentiment(self):
        payload = {"data": [{
            "title": "AMD launches a new chip",
            "url": "https://example.com/amd",
            "entities": [
                {"symbol": "AMD", "sentiment_score": 0.4, "match_score": 48.2},
                {"symbol": "NVDA", "sentiment_score": 0.2, "match_score": 12.1},
            ],
        }]}

        rows = advisor_articles(payload, "AMD")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AMD")
        self.assertEqual(rows[0]["overall_sentiment_score"], 0.4)

    def test_advisor_articles_rejects_secondary_entity(self):
        payload = {"data": [{
            "title": "Infosys launches on Microsoft Azure",
            "entities": [
                {"symbol": "INFY", "sentiment_score": 0.4, "match_score": 60.0},
                {"symbol": "MSFT", "sentiment_score": 0.2, "match_score": 35.0},
            ],
        }]}

        self.assertEqual(advisor_articles(payload, "MSFT"), [])

    def test_advisor_articles_ignores_articles_without_requested_symbol(self):
        self.assertEqual(advisor_articles({"data": [{"entities": [{"symbol": "MSFT"}]}]}, "AAPL"), [])

    @patch("marketaux.requests.get")
    def test_http_error_does_not_expose_token(self, get):
        get.return_value = Mock(status_code=401)
        client = MarketauxClient(api_key="private-token", cache_hours=0)

        with self.assertRaisesRegex(MarketauxError, r"HTTP 401") as raised:
            client.news(symbols="AAPL")

        self.assertNotIn("private-token", str(raised.exception))
