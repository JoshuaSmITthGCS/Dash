import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import (_screen_row, build_portfolio_coverage, carry_forward_rows,
                           compact_news, curate_candidate_news, enrich, latest_unique_news,
                           previous_rows_by_ticker, previous_top_symbols,
                           resolve_refresh_symbols, select_enrichment_priority, yahoo_extended)


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

    def test_full_universe_research_cannot_let_previous_rank_leak_in(self):
        # A3: statement enrichment must be decided from this run's fundamentals alone in
        # research mode. A populated previous_top - the exact incumbency the production
        # path favors - must produce byte-identical priority to an empty previous_top.
        preliminary = tuple(f"S{i:02d}" for i in range(30))
        previous_top_populated = tuple(f"S{i:02d}" for i in range(25, 30)) + ("OUTSIDER",)
        available = set(preliminary)

        with_history = select_enrichment_priority(
            previous_top_populated, preliminary, available, ("PORT",),
            full_universe_research=True,
        )
        without_history = select_enrichment_priority(
            (), preliminary, available, ("PORT",),
            full_universe_research=True,
        )

        self.assertEqual(with_history, without_history)
        self.assertEqual(with_history[0], ())
        self.assertEqual(with_history[1], preliminary)
        self.assertEqual(with_history[2], (*preliminary, "PORT"))

    def test_full_universe_research_lifts_the_challenger_cap(self):
        preliminary = tuple(f"S{i:02d}" for i in range(150))
        _, challengers, priority = select_enrichment_priority(
            (), preliminary, set(preliminary), full_universe_research=True,
        )
        self.assertEqual(len(challengers), 150)
        self.assertEqual(len(priority), 150)


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


class FastRefreshCarryForwardTests(unittest.TestCase):
    def test_screen_only_rows_are_found_when_not_published(self):
        payload = {
            "research": [{"ticker": "AAPL", "score": 90}],
            "screen_universe": [{"ticker": "IBM", "score": 40}],
        }

        rows = previous_rows_by_ticker(payload)

        self.assertEqual(set(rows), {"AAPL", "IBM"})
        self.assertEqual(rows["IBM"]["score"], 40)

    def test_published_row_wins_over_a_screen_only_duplicate(self):
        payload = {
            "research": [{"ticker": "AAPL", "score": 90}],
            "screen_universe": [{"ticker": "AAPL", "score": 40}],
        }

        self.assertEqual(previous_rows_by_ticker(payload)["AAPL"]["score"], 90)

    def test_unrefreshed_symbols_carry_forward_flagged_as_stale(self):
        previous_payload = {
            "research": [{"ticker": "AAPL", "score": 90}, {"ticker": "MU", "score": 55}],
            "screen_universe": [{"ticker": "IBM", "score": 40}],
        }
        research = [{"ticker": "AAPL", "score": 92}]  # only AAPL was actually polled

        carried = carry_forward_rows(research, ("AAPL", "MU", "IBM"), previous_payload)

        self.assertEqual({row["ticker"] for row in carried}, {"MU", "IBM"})
        self.assertTrue(all(row["stale_carryforward"] for row in carried))
        self.assertEqual(next(row for row in carried if row["ticker"] == "MU")["score"], 55)

    def test_a_symbol_with_no_prior_row_is_simply_not_carried(self):
        previous_payload = {"research": [{"ticker": "AAPL", "score": 90}]}

        carried = carry_forward_rows([], ("AAPL", "NEWCO"), previous_payload)

        self.assertEqual([row["ticker"] for row in carried], ["AAPL"])

    def test_a_symbol_that_was_actually_refreshed_is_not_duplicated(self):
        previous_payload = {"research": [{"ticker": "AAPL", "score": 90}]}
        research = [{"ticker": "AAPL", "score": 92}]

        carried = carry_forward_rows(research, ("AAPL",), previous_payload)

        self.assertEqual(carried, [])

    def test_top_symbols_span_published_research_and_the_screen_tail(self):
        # publish_limit-sized "research" (published leaders) plus a much longer
        # "screen_universe" tail, exactly the shape a real advisor.json has.
        payload = {
            "research": [{"ticker": f"R{i:02d}", "score": 100 - i} for i in range(40)],
            "screen_universe": [{"ticker": f"S{i:02d}", "score": 60 - i} for i in range(60)],
        }

        top100 = previous_top_symbols(payload, 100)

        self.assertEqual(len(top100), 100)
        self.assertEqual(top100[:3], ("R00", "R01", "R02"))
        self.assertEqual(top100[40:43], ("S00", "S01", "S02"))

    def test_top_symbols_does_not_silently_shrink_below_the_requested_count(self):
        # A naive implementation that only looks at "research" (40 rows) would return 40
        # tickers here instead of the 100 asked for - this is the regression to catch.
        payload = {"research": [{"ticker": f"R{i:02d}", "score": 100 - i} for i in range(40)],
                   "screen_universe": [{"ticker": f"S{i:02d}", "score": 60 - i} for i in range(60)]}

        self.assertEqual(len(previous_top_symbols(payload, 100)), 100)


class ScreenRowProjectionTests(unittest.TestCase):
    def test_a_full_research_row_projects_to_the_lightweight_shape(self):
        full_row = {
            "ticker": "AAPL", "name": "Apple", "sector": "Tech", "price": 200.0, "score": 88,
            "stance": "buy", "components": {"fundamentals": 90}, "fundamental_categories": {"valuation": 80},
            "technical_detail": {"momentum_12_1": 0.2, "unrelated_field": "drop me"},
            "confidence": 0.9, "history": {"dates": []}, "hypothetical": {},
        }

        projected = _screen_row(full_row)

        self.assertEqual(projected["ticker"], "AAPL")
        self.assertEqual(projected["technical_detail"], {"momentum_12_1": 0.2})
        self.assertNotIn("confidence", projected)
        self.assertNotIn("history", projected)
        self.assertFalse(projected["stale_carryforward"])

    def test_an_already_lightweight_carried_forward_row_projects_without_error(self):
        # What a carried-forward row looks like when it was never published to begin with -
        # i.e. it came from a prior screen_universe entry, not a prior research entry.
        lightweight_row = {
            "ticker": "IBM", "name": "IBM", "sector": "Tech", "price": 150.0, "score": 40,
            "stance": "hold", "components": {}, "fundamental_categories": {},
            "technical_detail": {"return_5d": 0.01}, "stale_carryforward": True,
        }

        projected = _screen_row(lightweight_row)

        self.assertEqual(projected["ticker"], "IBM")
        self.assertTrue(projected["stale_carryforward"])


def _statement_frame(rows):
    """Two-period yfinance-shaped statement DataFrame (columns=periods, index=line items)."""
    return pd.DataFrame(rows, index=["2025-12-31", "2024-12-31"]).T


class _FakeTickerObj:
    """A ticker whose statement frames resolve fine but whose ``.info`` call fails -- the
    2026-08-06 production failure mode this test guards against."""

    def __init__(self, info_error=None):
        self._info_error = info_error
        self.income_stmt = _statement_frame({
            "Total Revenue": [1000.0, 900.0], "EBIT": [200.0, 170.0],
            "Net Income": [150.0, 120.0], "Pretax Income": [190.0, 160.0],
            "Tax Provision": [40.0, 40.0], "Gross Profit": [600.0, 540.0],
        })
        self.balance_sheet = _statement_frame({
            "Total Assets": [2000.0, 1800.0], "Total Debt": [300.0, 300.0],
            "Stockholders Equity": [1200.0, 1100.0],
            "Cash And Cash Equivalents": [400.0, 350.0],
        })
        self.cashflow = _statement_frame({
            "Free Cash Flow": [180.0, 150.0], "Operating Cash Flow": [220.0, 190.0],
            "Capital Expenditure": [-40.0, -40.0],
        })
        self.quarterly_income_stmt = pd.DataFrame()
        self.quarterly_balance_sheet = pd.DataFrame()
        self.quarterly_cashflow = pd.DataFrame()
        self.options = ()

    @property
    def info(self):
        if self._info_error is not None:
            raise self._info_error
        return {"marketCap": 5_000_000_000}


class YahooExtendedFailureIsolationTests(unittest.TestCase):
    """Regression coverage for the 2026-08-06 statement_enriched_count=0 incident: a broken
    ``.info`` call used to discard successfully-fetched statement frames wholesale."""

    def test_info_failure_does_not_discard_successfully_fetched_statement_frames(self):
        ticker_obj = _FakeTickerObj(info_error=RuntimeError("crumb negotiation failed"))
        snapshot = {"market_cap": 5_000_000_000, "price": 50.0, "sector": "Technology"}
        history = {"closes": [50.0] * 25, "volumes": [1_000_000] * 25}
        diagnostics = {"attempted": 0, "info_fetch_failed": 0, "statement_fetch_failed": 0,
                       "derivation_failed": 0, "no_statement_data": 0}

        extended = yahoo_extended("FAKE", ticker_obj, snapshot, history, diagnostics)

        self.assertIsNotNone(extended.get("return_on_invested_capital"))
        self.assertIsNotNone(extended.get("gross_profits_to_assets"))
        self.assertGreater(extended.get("extended_coverage", 0), 0)
        self.assertEqual(diagnostics["info_fetch_failed"], 1)

    def test_healthy_ticker_enriches_with_no_diagnostic_failures(self):
        ticker_obj = _FakeTickerObj()
        snapshot = {"market_cap": 5_000_000_000, "price": 50.0, "sector": "Technology"}
        history = {"closes": [50.0] * 25, "volumes": [1_000_000] * 25}
        diagnostics = {"attempted": 0, "info_fetch_failed": 0, "statement_fetch_failed": 0,
                       "derivation_failed": 0, "no_statement_data": 0}

        extended = yahoo_extended("FAKE", ticker_obj, snapshot, history, diagnostics)

        self.assertGreater(extended.get("extended_coverage", 0), 0)
        self.assertEqual(sum(diagnostics.values()), 0)

    def test_enrich_counts_only_companies_with_positive_extended_coverage(self):
        # A company whose ticker_obj is None (e.g. yfinance unavailable) must not count as
        # enriched just because yahoo_extended returns a dict-shaped {} without raising.
        healthy_context = {
            "symbol": "GOOD", "ticker_obj": _FakeTickerObj(),
            "snapshot": {"market_cap": 5_000_000_000, "price": 50.0, "sector": "Technology"},
            "history": {"closes": [50.0] * 25, "volumes": [1_000_000] * 25},
        }
        starved_context = {
            "symbol": "BAD", "ticker_obj": None,
            "snapshot": {"market_cap": 1_000_000_000, "price": 10.0, "sector": "Technology"},
            "history": {"closes": [10.0] * 25, "volumes": [1_000_000] * 25},
        }

        enriched_count, diagnostics = enrich(
            [healthy_context, starved_context], limit=2, delay=0,
        )

        self.assertEqual(enriched_count, 1)
        self.assertEqual(diagnostics["attempted"], 2)
        self.assertIn("extended", healthy_context)
        self.assertNotIn("extended", starved_context)


if __name__ == "__main__":
    unittest.main()
