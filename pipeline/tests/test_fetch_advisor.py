import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import (build_portfolio_coverage, compact_news, curate_candidate_news,
                           latest_unique_news, resolve_refresh_symbols,
                           select_enrichment_priority)


class RefreshSymbolTests(unittest.TestCase):
    def test_dynamic_portfolio_symbols_are_fetched_and_covered(self):
        symbols, portfolio = resolve_refresh_symbols(
            ("AAPL", "MSFT"), ("MU", "AMAT"), "ntnx, VOO, NEW.X"
        )

        self.assertEqual(portfolio, ("MU", "AMAT", "NTNX", "VOO", "NEW.X"))
        self.assertEqual(
            symbols,
            ("AAPL", "MSFT", "MU", "AMAT", "NTNX", "VOO", "NEW.X"),
        )

    def test_dynamic_symbols_are_validated_and_deduplicated(self):
        symbols, portfolio = resolve_refresh_symbols(
            ("AAPL",), ("MU",), " mu, bad symbol, , $SPY, VOO "
        )

        self.assertEqual(portfolio, ("MU", "VOO"))
        self.assertEqual(symbols, ("AAPL", "MU", "VOO"))

    def test_discovered_holdings_persist_into_scheduled_refreshes(self):
        symbols, portfolio = resolve_refresh_symbols(
            ("AAPL",),
            ("MU",),
            "",
            ("NTNX", "VOO"),
        )

        self.assertEqual(portfolio, ("MU", "NTNX", "VOO"))
        self.assertEqual(symbols, ("AAPL", "MU", "NTNX", "VOO"))


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


class PortfolioCoverageTests(unittest.TestCase):
    def test_every_configured_holding_gets_a_coverage_row(self):
        research = [{"ticker": "LIVE", "name": "Live", "price": 10}]
        previous = [{"ticker": "STALE", "name": "Stale", "price": 8}]

        rows = build_portfolio_coverage(
            research, ("LIVE", "STALE", "MISSING"), previous
        )

        self.assertEqual([row["ticker"] for row in rows], ["LIVE", "STALE", "MISSING"])
        self.assertEqual(rows[1]["coverage_status"], "stale_provider_unavailable")
        self.assertEqual(rows[2]["coverage_status"], "provider_unavailable")
        self.assertIsNone(rows[2]["price"])


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

    def test_reserves_space_for_broader_research_candidates(self):
        leaders = [
            {"url": f"https://example.com/top-{index}", "ticker": "TOP", "published_at": f"20260730T12{index:02d}00"}
            for index in range(10)
        ]
        discovery = [
            {"url": f"https://example.com/next-{index}", "ticker": "NEXT", "published_at": f"20260729T12{index:02d}00"}
            for index in range(5)
        ]
        context = {
            "TOP": {"published_research": True, "research_rank": 1},
            "NEXT": {"published_research": False, "research_rank": 41},
        }

        rows = curate_candidate_news(leaders + discovery, context, limit=10, discovery_slots=3)

        self.assertEqual(sum(not row["published_research"] for row in rows), 3)
        self.assertEqual(len(rows), 10)


if __name__ == "__main__":
    unittest.main()
