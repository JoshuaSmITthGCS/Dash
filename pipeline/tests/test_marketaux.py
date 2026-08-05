import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from marketaux import (MarketauxClient, MarketauxError, advisor_articles,
                       advisor_articles_for_symbols)


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
        self.assertEqual(rows[0]["content_type"], "commentary")
        self.assertIn("source_quality_tier", rows[0])

    def test_sec_item_is_labelled_as_a_source_filing(self):
        payload = {"data": [{
            "title": "Issuer files Form 8-K",
            "url": "https://www.sec.gov/Archives/edgar/data/example",
            "source": "SEC EDGAR",
            "entities": [{"symbol": "TEST", "sentiment_score": 0.1, "match_score": 90}],
        }]}

        rows = advisor_articles(payload, "TEST")

        self.assertEqual(rows[0]["content_type"], "filing")
        self.assertEqual(rows[0]["source_quality_tier"], "regulatory_primary")

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

    def test_advisor_articles_for_symbols_keeps_strong_primary_candidates(self):
        payload = {"data": [
            {
                "title": "Adobe launches a new product",
                "entities": [{"symbol": "ADBE", "sentiment_score": 0.3, "match_score": 52}],
            },
            {
                "title": "ServiceNow expands",
                "entities": [{"symbol": "NOW", "sentiment_score": 0.2, "match_score": 45}],
            },
            {
                "title": "Unrelated company",
                "entities": [{"symbol": "OTHER", "sentiment_score": 0.4, "match_score": 70}],
            },
        ]}

        rows = advisor_articles_for_symbols(payload, ("ADBE", "NOW"))

        self.assertEqual([row["ticker"] for row in rows], ["ADBE", "NOW"])

    @patch("marketaux.requests.get")
    def test_http_error_does_not_expose_token(self, get):
        get.return_value = Mock(status_code=401)
        client = MarketauxClient(api_key="private-token", cache_hours=0)

        with self.assertRaisesRegex(MarketauxError, r"HTTP 401") as raised:
            client.news(symbols="AAPL")

        self.assertNotIn("private-token", str(raised.exception))
