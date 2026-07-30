import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import compact_news, latest_unique_news, select_enrichment_priority


class EnrichmentPriorityTests(unittest.TestCase):
    def test_previous_twenty_and_next_five_are_first(self):
        previous = tuple(f"P{i:02d}" for i in range(20))
        preliminary = (*previous, *(f"C{i:02d}" for i in range(8)))
        available = set(preliminary)

        incumbents, challengers, priority = select_enrichment_priority(
            previous, preliminary, available, ("PORT",)
        )

        self.assertEqual(previous, incumbents)
        self.assertEqual(tuple(f"C{i:02d}" for i in range(5)), challengers)
        self.assertEqual((*incumbents, *challengers, "PORT"), priority)

    def test_first_run_uses_preliminary_top_twenty_and_following_five(self):
        preliminary = tuple(f"S{i:02d}" for i in range(30))

        incumbents, challengers, _ = select_enrichment_priority(
            (), preliminary, set(preliminary)
        )

        self.assertEqual(preliminary[:20], incumbents)
        self.assertEqual(preliminary[20:25], challengers)


class NewsMatchingTests(unittest.TestCase):
    def test_uses_primary_article_ticker_instead_of_requested_ticker(self):
        cases = [
            ("Icon earnings", "MSFT", "ICLR"),
            ("Avery Dennison tops estimates", "AAPL", "AVY"),
            ("Cisco holdings increase", "GOOGL", "CSCO"),
            ("BlackRock holdings decrease", "META", "BLK"),
            ("Roper Technologies holdings decrease", "GOOGL", "ROP"),
            ("Infosys launches on Azure", "MSFT", "INFY"),
        ]
        for title, requested, primary in cases:
            with self.subTest(title=title):
                payload = {"feed": [{
                    "title": title,
                    "url": f"https://example.com/{primary.lower()}",
                    "ticker_sentiment": [
                        {"ticker": requested, "relevance_score": "0.612"},
                        {"ticker": primary, "relevance_score": "1.000"},
                    ],
                }]}

                rows = compact_news(payload, requested)

                self.assertEqual(rows[0]["ticker"], primary)
                self.assertEqual(rows[0]["ticker_sentiment"][0]["ticker"], primary)

    def test_drops_broad_article_without_a_strong_primary_company(self):
        payload = {"feed": [{
            "title": "A warning to investors",
            "url": "https://example.com/markets",
            "ticker_sentiment": [
                {"ticker": "AAPL", "relevance_score": "0.609"},
                {"ticker": "AMZN", "relevance_score": "0.589"},
            ],
        }]}

        self.assertEqual(compact_news(payload, "AAPL"), [])

    def test_deduplicates_same_article_returned_for_multiple_queries(self):
        article = {"url": "https://example.com/story", "ticker": "JPM", "published_at": "20260730T120000"}

        self.assertEqual(latest_unique_news([article, dict(article)]), [article])


if __name__ == "__main__":
    unittest.main()
