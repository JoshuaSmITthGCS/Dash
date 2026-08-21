import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_advisor import (_evidence_summary, _screen_row, _sentiment_summary, build_portfolio_coverage,
                           carry_forward_missing_sessions, carry_forward_rows,
                           collect_insider_signals, compact_news,
                           curate_candidate_news, enrich, enrichment_rotation,
                           latest_unique_news,
                           previous_rows_by_ticker, previous_top_symbols,
                           resolve_refresh_symbols, rotation_slice,
                           select_enrichment_priority, yahoo_extended)


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

    def test_a_retired_symbol_cannot_reseed_itself_from_the_previous_run(self):
        # portfolio_coverage seeds the next run's holdings, so before this a retired symbol
        # re-entered on every refresh and could not be removed from anywhere.
        symbols, portfolio = resolve_refresh_symbols(
            ("AAPL",), ("MU",), "DECJ, DECK", ("DECJ", "NTNX"),
        )

        self.assertNotIn("DECJ", portfolio)
        self.assertNotIn("DECJ", symbols)
        self.assertEqual(portfolio, ("MU", "NTNX", "DECK"))

    def test_ttm_and_amzm_are_retired_and_cannot_reseed_from_prior_coverage(self):
        # Round 7 Task 1: the two missing_price_tickers breaching data_quality_counters.
        # TTM (Tata Motors NYSE ADR) delisted January 2025; AMZM resolves to nothing at any
        # provider. Both were hand-entered holdings carried forward run-to-run from
        # portfolio_coverage, permanently breaching the counter.
        symbols, portfolio = resolve_refresh_symbols(
            ("AAPL",), ("MU",), "", ("TTM", "AMZM", "NTNX"),
        )
        self.assertNotIn("TTM", symbols)
        self.assertNotIn("AMZM", symbols)
        self.assertEqual(portfolio, ("MU", "NTNX"))
        # Every retired symbol must carry a stated reason - it's what record_universe
        # publishes into the universe store's churn note.
        from fetch_advisor import RETIRED_SYMBOLS
        for ticker in ("DECJ", "TTM", "AMZM"):
            self.assertTrue(RETIRED_SYMBOLS[ticker].strip())

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
            previous, preliminary, available, ("PORT",), rotation_size=0
        )

        self.assertEqual(previous, incumbents)
        self.assertEqual(tuple(f"C{i:02d}" for i in range(5)), challengers)
        self.assertEqual((*incumbents, *challengers, "PORT"), priority)

    def test_statement_starved_names_are_rotated_in_beyond_the_top_twenty_five(self):
        """Enrichment used to be a closed loop over the previous run's leaders, so a name
        outside it could never acquire the metrics that would let it out-rank an incumbent."""
        previous = tuple(f"P{i:02d}" for i in range(20))
        outsiders = tuple(f"C{i:02d}" for i in range(30))
        preliminary = (*previous, *outsiders)

        _, challengers, priority = select_enrichment_priority(
            previous, preliminary, set(preliminary), (), rotation_size=15
        )

        rotated = [symbol for symbol in priority
                   if symbol not in previous and symbol not in challengers]
        self.assertEqual(len(rotated), 15)
        # Names the previous run never enriched come first, in universe order.
        self.assertEqual(rotated, list(outsiders[5:20]))

    def test_a_never_enriched_name_outranks_one_that_was_enriched_recently(self):
        preliminary = ("ENRICHED", "NEVER")
        previous_payload = {"research": [
            {"ticker": "ENRICHED", "last_polled_at": "2026-08-09T00:00:00+00:00",
             "fundamental_detail": {"raw_score": 88.0}},
            {"ticker": "NEVER", "last_polled_at": "2026-01-01T00:00:00+00:00",
             "fundamental_detail": {}},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 2)
        self.assertEqual(rotated[0], "NEVER")

    def test_a_theme_flagged_name_outranks_a_plain_unenriched_name(self):
        # Both are statement-starved, but THEMED is already on a theme screen ranked on a
        # business-quality reading alone (themes.explain_rank) -- it should close that gap
        # before PLAIN, which nothing has surfaced yet, gets a turn.
        preliminary = ("PLAIN", "THEMED")
        previous_payload = {"research": [
            {"ticker": "PLAIN", "fundamental_detail": {}, "theme_exposure": []},
            {"ticker": "THEMED", "fundamental_detail": {},
             "theme_exposure": [{"theme_id": "ai_infrastructure"}]},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 2)
        self.assertEqual(rotated[0], "THEMED")

    def test_a_theme_flagged_name_still_outranks_an_enriched_incumbent(self):
        preliminary = ("ENRICHED", "THEMED")
        previous_payload = {"research": [
            {"ticker": "ENRICHED", "last_polled_at": "2026-08-09T00:00:00+00:00",
             "fundamental_detail": {"raw_score": 88.0}},
            {"ticker": "THEMED", "fundamental_detail": {},
             "theme_exposure": [{"theme_id": "ai_infrastructure"}]},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 2)
        self.assertEqual(rotated[0], "THEMED")

    def test_once_the_theme_backlog_clears_plain_unenriched_names_resume(self):
        # No theme-flagged name left in this preliminary set -- ordinary never-enriched-first
        # behavior must still hold, unaffected by the new tier.
        preliminary = ("PLAIN",)
        previous_payload = {"research": [
            {"ticker": "PLAIN", "fundamental_detail": {}, "theme_exposure": []},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 1)
        self.assertEqual(rotated, ("PLAIN",))

    def test_a_screen_only_row_still_counts_as_enriched_for_rotation_purposes(self):
        # TAILCO was rotated in, successfully enriched, and still didn't crack the
        # publish_limit leaderboard, so it lives in screen_universe, not research, in
        # previous_payload. Its statement coverage must still be visible here, or rotation
        # would burn a slot re-selecting it every run instead of ever treating it as done.
        preliminary = ("TAILCO", "NEVER")
        previous_payload = {"research": [], "screen_universe": [
            {"ticker": "TAILCO", "fundamental_detail": {"raw_score": 63.5}},
            {"ticker": "NEVER", "fundamental_detail": {"raw_score": None}},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 1)
        self.assertEqual(rotated, ("NEVER",))

    def test_an_already_enriched_name_is_skipped_even_after_moving_up_in_rank(self):
        # MOVER sits first in preliminary order -- ahead of both never-enriched names, i.e.
        # it "moved up" -- but it was already statement-enriched in a past run. The rotation
        # batch must not spend one of its slots re-touching it while genuinely uncovered
        # names are still waiting, no matter where MOVER now sits in the ranking.
        preliminary = ("MOVER", "NEVER_A", "NEVER_B")
        previous_payload = {"research": [
            {"ticker": "MOVER", "last_polled_at": "2026-08-20T00:00:00+00:00",
             "fundamental_detail": {"raw_score": 71.0}},
            {"ticker": "NEVER_A", "fundamental_detail": {}},
            {"ticker": "NEVER_B", "fundamental_detail": {}},
        ]}
        rotated = enrichment_rotation(preliminary, set(), previous_payload, 2)
        self.assertEqual(set(rotated), {"NEVER_A", "NEVER_B"})
        self.assertNotIn("MOVER", rotated)

    def test_select_enrichment_priority_also_skips_a_mover_already_enriched(self):
        # Same guarantee, exercised through the actual production entry point. FILLERS soak
        # up the five challenger slots so MOVER and NEVER both land in the rotation pool.
        # MOVER sits ahead of NEVER in preliminary order -- it "moved up" -- but it was
        # already statement-enriched via a past rotation; the single rotation slot here must
        # still go to NEVER, which has no statement coverage at all.
        previous = tuple(f"P{i:02d}" for i in range(20))
        fillers = tuple(f"F{i:02d}" for i in range(5))
        preliminary = (*previous, *fillers, "MOVER", "NEVER")
        previous_payload = {"research": [
            {"ticker": "MOVER", "last_polled_at": "2026-08-20T00:00:00+00:00",
             "fundamental_detail": {"raw_score": 71.0}},
            {"ticker": "NEVER", "fundamental_detail": {}},
        ]}
        _, challengers, priority = select_enrichment_priority(
            previous, preliminary, set(preliminary), (),
            previous_payload=previous_payload, rotation_size=1,
        )
        self.assertEqual(set(challengers), set(fillers))
        self.assertIn("NEVER", priority)
        self.assertNotIn("MOVER", priority)

    def test_rotation_can_be_switched_off(self):
        preliminary = tuple(f"S{i:02d}" for i in range(30))
        _, _, priority = select_enrichment_priority(
            (), preliminary, set(preliminary), (), rotation_size=0)
        self.assertEqual(len(priority), 25)

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


class FocusedRefreshTests(unittest.TestCase):
    """A re-ranking request for one named set: the theme screen's re-run button."""

    def test_a_re_ranked_name_is_enriched_before_yesterdays_leaders(self):
        # Without this the button would return the ranking it was asked to revisit: the
        # metrics carrying most of the model's weight only exist for enriched names, so a
        # focused run that spent its statement budget on incumbents would change nothing.
        previous = tuple(f"P{i:02d}" for i in range(20))
        preliminary = (*previous, *(f"C{i:02d}" for i in range(8)))

        _, _, priority = select_enrichment_priority(
            previous, preliminary, set(preliminary), (), rotation_size=0,
            focus_symbols=("C07", "C06"),
        )

        self.assertEqual(priority[:2], ("C07", "C06"))

    def test_a_focus_symbol_absent_from_this_run_is_dropped_not_queued(self):
        previous = ("P00",)
        priority = select_enrichment_priority(
            previous, previous, {"P00"}, (), rotation_size=0,
            focus_symbols=("GONE",))[2]
        self.assertNotIn("GONE", priority)

    def test_focus_symbols_are_not_treated_as_holdings(self):
        # The distinction the separate input exists for: `portfolio_symbols` means the user
        # owns it, and feeds portfolio coverage and the theme layer's "Your holding" tag.
        symbols, portfolio = resolve_refresh_symbols(("NVDA", "ETN"), ("AAPL",), "", ())
        self.assertEqual(portfolio, ("AAPL",))
        self.assertNotIn("NVDA", portfolio)
        self.assertIn("NVDA", symbols)


class PortfolioCoverageTests(unittest.TestCase):
    def test_every_configured_holding_gets_a_coverage_row(self):
        analytics = {"dates": ["2026-08-12", "2026-08-13"], "closes": [9.8, 10], "frequency": "daily"}
        research = [{"ticker": "LIVE", "name": "Live", "price": 10, "analytics_history": analytics}]
        previous = [{"ticker": "STALE", "name": "Stale", "price": 8}]

        rows = build_portfolio_coverage(
            research, ("LIVE", "STALE", "MISSING"), previous
        )

        self.assertEqual([row["ticker"] for row in rows], ["LIVE", "STALE", "MISSING"])
        self.assertEqual(rows[0]["analytics_history"], analytics)
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


class BenchmarkHistoryRegressionTests(unittest.TestCase):
    """A short fetch must never erase a session the previous run already published -
    that is exactly what stalled the live-tracking countdown: a provider hiccup dropped a
    session from the benchmark history that a prior refresh had already recorded."""

    def test_a_session_dropped_by_the_fresh_fetch_is_carried_forward(self):
        previous_dates = ["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17"]
        previous_closes = [640.0, 641.0, 642.0, 643.0, 644.0]
        fresh = {"dates": previous_dates[:-1], "closes": previous_closes[:-1], "volumes": [1, 2, 3, 4]}

        merged = carry_forward_missing_sessions(previous_dates, previous_closes, fresh)

        self.assertEqual(merged["dates"], previous_dates)
        self.assertEqual(merged["closes"], previous_closes)
        self.assertEqual(merged["volumes"][-1], 0.0)

    def test_a_fresh_fetch_that_already_covers_everything_is_returned_unchanged(self):
        previous_dates = ["2026-08-13", "2026-08-14"]
        previous_closes = [642.0, 643.0]
        fresh = {"dates": ["2026-08-13", "2026-08-14", "2026-08-17"], "closes": [642.0, 643.0, 644.0], "volumes": [3, 4, 5]}

        merged = carry_forward_missing_sessions(previous_dates, previous_closes, fresh)

        self.assertIs(merged, fresh)

    def test_no_prior_history_returns_the_fresh_fetch_unchanged(self):
        fresh = {"dates": ["2026-08-14"], "closes": [643.0], "volumes": [4]}

        self.assertIs(carry_forward_missing_sessions(None, None, fresh), fresh)
        self.assertIs(carry_forward_missing_sessions([], [], fresh), fresh)

    def test_a_symbol_history_reunions_gaps_the_batch_download_dropped(self):
        # The per-symbol path: yf.download drops individual bars out of a batch, so a symbol's
        # own tape can come back with interior holes even while the fetch "succeeds".
        previous_dates = ["2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17"]
        previous_closes = [10.0, 11.0, 12.0, 13.0]
        fresh = {"dates": ["2026-08-12", "2026-08-14", "2026-08-18"],
                 "closes": [10.0, 12.0, 14.0], "volumes": [1, 2, 3]}

        merged = carry_forward_missing_sessions(previous_dates, previous_closes, fresh)

        self.assertEqual(merged["dates"],
                         ["2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18"])
        self.assertEqual(merged["closes"], [10.0, 11.0, 12.0, 13.0, 14.0])

    def test_a_previous_date_without_a_usable_close_is_skipped(self):
        merged = carry_forward_missing_sessions(
            ["2026-08-13", "2026-08-14"], [None, 12.0],
            {"dates": ["2026-08-18"], "closes": [14.0], "volumes": [1]},
        )

        self.assertEqual(merged["dates"], ["2026-08-14", "2026-08-18"])
        self.assertEqual(merged["closes"], [12.0, 14.0])

    def test_an_overlapping_date_prefers_the_fresh_close_over_the_previous_one(self):
        previous_dates = ["2026-08-13", "2026-08-14"]
        previous_closes = [642.0, 643.0]
        fresh = {"dates": ["2026-08-14"], "closes": [999.0], "volumes": [7]}

        merged = carry_forward_missing_sessions(previous_dates, previous_closes, fresh)

        self.assertEqual(merged["dates"], previous_dates)
        self.assertEqual(merged["closes"], [642.0, 999.0])

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

    def test_the_screen_only_slice_still_carries_what_the_strategy_lenses_need(self):
        # The client-side sort lenses (rankCatalyst, rankAnalystConviction, the theme
        # "tailwind" opportunity score) need to read these fields for a name outside the
        # published leaderboard, or those lenses silently stay scoped to the top 40.
        full_row = {
            "ticker": "MU", "name": "Micron", "sector": "Technology", "price": 100.0, "score": 55,
            "stance": "hold", "components": {"fundamentals": 55, "news_sentiment": 70},
            "fundamental_categories": {}, "technical_detail": {"drawdown_60d": -12, "volume_ratio_60d": 1.4},
            "insider_activity": {"available": True, "points": 3.0},
            "analyst_count": 12, "analyst_rating": 1.8, "analyst_target_upside": 15.0,
            "theme_exposure": [{"theme_id": "ai_infrastructure", "theme_exposure_score": 70,
                                "opportunity_score": 62, "eligible": True}],
        }

        projected = _screen_row(full_row)

        self.assertEqual(projected["technical_detail"]["drawdown_60d"], -12)
        self.assertEqual(projected["technical_detail"]["volume_ratio_60d"], 1.4)
        self.assertEqual(projected["insider_activity"], {"available": True, "points": 3.0})
        self.assertEqual(projected["analyst_count"], 12)
        self.assertEqual(projected["analyst_rating"], 1.8)
        self.assertEqual(projected["analyst_target_upside"], 15.0)
        self.assertEqual(projected["theme_exposure"][0]["opportunity_score"], 62)

    def test_the_screen_only_slice_carries_the_corroboration_cross_checks(self):
        # Independent, already-published cross-checks the strategy-lens gates read
        # (rankReversal/rankValueTurnarounds/rankAnalystConviction/rankCatalyst) - none
        # of these feed any score, they only corroborate or flag a lens's primary signal.
        full_row = {
            "ticker": "MU", "name": "Micron", "sector": "Technology", "price": 100.0, "score": 55,
            "stance": "hold", "components": {}, "fundamental_categories": {},
            "technical_detail": {"return_60d": 8.0, "return_252d": 22.0},
            "earnings_surprise": -4.2, "short_percent_of_float": 0.041, "days_to_cover": 2.9,
            "sector_valuation_percentile": 63.0,
            "sentiment_detail": {
                "article_count": 3, "filing_count": 1,
                "articles": [
                    {"source_quality_tier": "aggregator_syndicated"},
                    {"source_quality_tier": "established_press"},
                ],
            },
        }

        projected = _screen_row(full_row)

        self.assertEqual(projected["technical_detail"]["return_60d"], 8.0)
        self.assertEqual(projected["technical_detail"]["return_252d"], 22.0)
        self.assertEqual(projected["earnings_surprise"], -4.2)
        self.assertEqual(projected["short_percent_of_float"], 0.041)
        self.assertEqual(projected["days_to_cover"], 2.9)
        self.assertEqual(projected["sector_valuation_percentile"], 63.0)
        self.assertEqual(projected["sentiment_summary"], {
            "article_count": 3, "filing_count": 1, "best_source_quality_tier": "established_press",
        })

    def test_sentiment_summary_is_none_without_any_sentiment_data(self):
        self.assertIsNone(_sentiment_summary(None))
        self.assertIsNone(_sentiment_summary({}))

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

    def test_a_rotation_enriched_name_that_misses_the_leaderboard_still_carries_its_statement_flag(self):
        # A name enrichment_rotation() sent to enrich() and that resolved real statement
        # metrics, but that still isn't good enough to crack the publish_limit leaderboard,
        # used to lose that fact the moment it projected into screen_universe -- the
        # lightweight shape carried fundamental_categories (populated for every row
        # regardless of enrichment) but not fundamental_detail.raw_score, the one field
        # enrichment_rotation()'s last_enriched() actually checks. Every subsequent run then
        # saw it as never-enriched and could burn a rotation slot re-selecting it forever,
        # instead of it ever counting as done.
        enriched_but_unranked = {
            "ticker": "OBSCURECO", "name": "Obscure Co", "sector": "Industrials", "price": 12.0,
            "score": 41, "stance": "hold", "components": {"fundamentals": 41},
            "fundamental_categories": {"valuation": 38}, "technical_detail": {},
            "fundamental_detail": {"raw_score": 63.5, "coverage": 0.9},
        }

        projected = _screen_row(enriched_but_unranked)

        self.assertEqual(projected["fundamental_detail"], {"raw_score": 63.5})


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


class _PassthroughCache:
    """`cache.fetch` with no persistence - the collection logic is what is under test."""

    def fetch(self, namespace, key, produce, source=None):
        return produce()


class _FakeSec:
    def __init__(self, by_symbol, available=True):
        self.available = available
        self._by_symbol = by_symbol

    def form4_transactions(self, symbol, lookback_days=1100):
        return self._by_symbol[symbol]


class InsiderCollectionDiagnosticsTests(unittest.TestCase):
    """"Every symbol scored zero insider activity" has two causes that used to be
    indistinguishable in the published payload: a genuinely quiet market, and a layer that
    downloaded thousands of filings and could not read one of them."""

    def test_unreadable_filings_are_counted_rather_than_passed_off_as_no_activity(self):
        unreadable = [{"parsed": False}, {"parsed": False}]
        sec = _FakeSec({"AAPL": ([], unreadable)})

        signals, failures, diagnostics = collect_insider_signals(
            sec, ("AAPL",), cache=_PassthroughCache())

        self.assertEqual(failures, [])
        self.assertFalse(signals["AAPL"]["available"])
        self.assertEqual(diagnostics["filings_reviewed"], 2)
        self.assertEqual(diagnostics["filings_unreadable"], 2)

    def test_a_readable_run_reports_no_unreadable_filings(self):
        transactions = [{
            "code": "P", "side": "purchase", "shares": 100.0, "price": 25.5, "value": 2550.0,
            "acquired_disposed": "A", "date": "2026-07-01", "owner_name": "Doe Jane",
            "owner_cik": "0000012345", "roles": ["officer"], "officer_title": "CFO",
            "filed": "2026-07-02",
        }]
        sec = _FakeSec({"AAPL": (transactions, [{"parsed": True}])})

        signals, _, diagnostics = collect_insider_signals(
            sec, ("AAPL",), cache=_PassthroughCache())

        self.assertTrue(signals["AAPL"]["available"])
        self.assertEqual(diagnostics["filings_unreadable"], 0)
        self.assertEqual(diagnostics["symbols_with_filings"], 1)

    def test_an_unconfigured_client_returns_empty_diagnostics_rather_than_raising(self):
        signals, failures, diagnostics = collect_insider_signals(
            _FakeSec({}, available=False), ("AAPL",), cache=_PassthroughCache())

        self.assertEqual((signals, failures), ({}, []))
        self.assertEqual(diagnostics["filings_reviewed"], 0)


class FastRefreshRotationTests(unittest.TestCase):
    """A fast refresh polls the prior leaders and the portfolio - a fixed set. Anything
    outside it was never re-fetched, so it carried the same row forward run after run and
    stopped carrying fields later runs began publishing. That is what left 756 of 837
    screen rows with no 60-day drawdown, which is the only input the reversal screen gates
    on: the screen could see 121 names out of a 926-name universe."""

    def test_the_stalest_symbols_outside_the_priority_set_are_rotated_back_in(self):
        previous_payload = {"research": [], "screen_universe": [
            {"ticker": "OLD", "score": 10, "last_polled_at": "2026-07-01T00:00:00+00:00"},
            {"ticker": "NEWER", "score": 10, "last_polled_at": "2026-08-01T00:00:00+00:00"},
            {"ticker": "MIDDLE", "score": 10, "last_polled_at": "2026-07-15T00:00:00+00:00"},
        ]}

        rotated = rotation_slice(("LEADER", "OLD", "NEWER", "MIDDLE"), {"LEADER"}, previous_payload, 2)

        self.assertEqual(rotated, ("OLD", "MIDDLE"))

    def test_a_symbol_that_has_never_been_polled_sorts_ahead_of_every_dated_row(self):
        previous_payload = {"screen_universe": [
            {"ticker": "DATED", "score": 10, "last_polled_at": "2026-07-01T00:00:00+00:00"},
        ]}

        rotated = rotation_slice(("DATED", "NEVER"), set(), previous_payload, 1)

        self.assertEqual(rotated, ("NEVER",))

    def test_symbols_already_being_polled_are_never_rotated_in_twice(self):
        previous_payload = {"screen_universe": [{"ticker": "LEADER", "score": 10}]}

        rotated = rotation_slice(("LEADER", "TAIL"), {"LEADER"}, previous_payload, 5)

        self.assertEqual(rotated, ("TAIL",))

    def test_rotation_can_be_switched_off_with_a_zero_size(self):
        self.assertEqual(rotation_slice(("A", "B"), set(), {}, 0), ())


class ScreenRowAssetTypeTests(unittest.TestCase):
    def test_a_fund_stays_identifiable_in_the_lightweight_projection(self):
        # Without this the client-side strategy screens, which all gate on per-security
        # fundamentals, treat every fund in the universe as an ordinary company.
        projected = _screen_row({"ticker": "VOO", "score": 70, "is_etf": True})

        self.assertTrue(projected["is_etf"])

    def test_an_ordinary_company_projects_as_not_a_fund(self):
        self.assertFalse(_screen_row({"ticker": "AAPL", "score": 70})["is_etf"])

    def test_the_poll_timestamp_survives_the_projection(self):
        projected = _screen_row({"ticker": "AAPL", "score": 70,
                                 "last_polled_at": "2026-08-08T00:00:00+00:00"})

        self.assertEqual(projected["last_polled_at"], "2026-08-08T00:00:00+00:00")


class EvidenceProjectionTests(unittest.TestCase):
    """The catalyst and analyst-conviction models exist to surface names that are NOT already
    top fundamentals scores, so their inputs have to reach the lightweight tail as well as the
    published leaderboard - otherwise those models can only ever see the leaderboard."""

    EVIDENCE = {
        "news_events": [{"title": "Raises FY guidance"} for _ in range(12)],
        "news_score": 88.0,
        "news_detail": {
            "available": True, "event_count": 3, "dominant_event": "Raises FY guidance",
            "dominant_event_types": ["guidance"], "dominant_age_trading_days": 1.4,
            "dominant_materiality": 1.0,
        },
        "insider_score": 72.0,
        "insider_score_long_term": 78.0,
        "insider_detail": {"available": True, "freshest_age_trading_days": 6.0},
        "expectation_score": 66.0,
        "expectation_detail": {"available": True, "inputs_resolved": 3},
    }

    def test_the_tail_carries_the_scores_and_the_dominant_event(self):
        projected = _screen_row({"ticker": "MU", "score": 55, "evidence": self.EVIDENCE})["evidence_summary"]

        self.assertEqual(projected["news_score"], 88.0)
        self.assertEqual(projected["dominant_event"], "Raises FY guidance")
        self.assertEqual(projected["dominant_event_types"], ["guidance"])
        self.assertEqual(projected["insider_freshest_age_trading_days"], 6.0)
        self.assertEqual(projected["expectation_inputs_resolved"], 3)

    def test_the_tail_does_not_carry_the_full_per_event_breakdown(self):
        # Twelve fully-detailed events for each of ~900 rows would roughly double the payload
        # to answer a question nobody asks of the 800th-ranked name.
        projected = _screen_row({"ticker": "MU", "score": 55, "evidence": self.EVIDENCE})

        self.assertNotIn("news_events", projected["evidence_summary"])

    def test_a_carried_forward_summary_is_not_re_projected_into_nothing(self):
        # A fast-refresh row arrives already in summary shape; re-projecting it would strip
        # the dominant-event fields it already holds.
        already_summarized = _evidence_summary(self.EVIDENCE)

        self.assertEqual(_evidence_summary(already_summarized), already_summarized)

    def test_a_row_with_no_evidence_projects_none_rather_than_an_empty_shell(self):
        self.assertIsNone(_screen_row({"ticker": "QUIET", "score": 40})["evidence_summary"])

    def test_the_tail_carries_the_estimate_revisions_the_analyst_model_reads(self):
        detail = {"revision_breadth_30d": 0.6, "eps_revision_30d_pct": 0.08, "inputs_resolved": 2}

        projected = _screen_row({"ticker": "MU", "score": 55, "estimate_detail": detail})

        self.assertEqual(projected["estimate_detail"]["revision_breadth_30d"], 0.6)


class PointInTimeExpectationTests(unittest.TestCase):
    def test_revision_fields_are_archived_because_yahoo_only_serves_today(self):
        from pit_store import TRACKED_FIELDS, tracked_fields

        row = {
            "ticker": "MU", "price": 100.0, "analyst_consensus_target": 130.0,
            "revision_breadth_30d": 0.75, "eps_revision_30d_pct": 0.12, "net_upgrades_90d": 4,
        }

        archived = tracked_fields(row, TRACKED_FIELDS)

        self.assertEqual(archived["analyst_consensus_target"], 130.0)
        self.assertEqual(archived["revision_breadth_30d"], 0.75)
        self.assertEqual(archived["net_upgrades_90d"], 4)
