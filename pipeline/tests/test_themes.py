import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import themes
import theme_signals as ts

BASE_THEME = {
    "id": "test_theme",
    "display_name": "Test Theme",
    "signals": [
        {"name": "segment_revenue_share", "weight": 0.4, "leading": False},
        {"name": "filing_keyword_density_trend", "weight": 0.3, "leading": True},
        {"name": "hyperscaler_capex_growth", "weight": 0.3, "leading": True},
    ],
}


def build(**overrides):
    return themes.normalize_theme({**BASE_THEME, **overrides})


class ThemeConfigTests(unittest.TestCase):
    def test_signal_weights_are_normalized_to_one(self):
        theme = themes.normalize_theme({**BASE_THEME, "signals": [
            {"name": "segment_revenue_share", "weight": 3},
            {"name": "filing_keyword_density_trend", "weight": 1},
        ]})
        self.assertAlmostEqual(sum(s["weight"] for s in theme["signals"]), 1.0, places=4)
        self.assertAlmostEqual(theme["signals"][0]["weight"], 0.75, places=4)

    def test_a_price_derived_signal_is_rejected_outright(self):
        # This is the guardrail the whole layer exists for. A thematic screen that reads
        # price momentum is a momentum screen, and thematic products built that way have
        # a documented history of losing money.
        problems = themes.validate_theme({**BASE_THEME, "signals": [
            {"name": "price_momentum", "weight": 1.0},
        ]})
        self.assertTrue(any("price" in problem for problem in problems))

    def test_a_nonzero_momentum_allowance_is_rejected(self):
        problems = themes.validate_theme({
            **BASE_THEME, "guardrails": {"max_price_momentum_contribution": 0.2}})
        self.assertTrue(any("max_price_momentum_contribution" in p for p in problems))

    def test_a_theme_without_signals_is_rejected(self):
        self.assertIn("no signals declared", themes.validate_theme({"id": "x", "signals": []}))

    def test_the_shipped_theme_definition_loads_and_validates(self):
        loaded = themes.load_themes()
        self.assertTrue(loaded, "expected at least one theme in pipeline/themes/")
        theme = loaded[0]
        self.assertEqual(theme["guardrails"]["max_price_momentum_contribution"], 0.0)
        self.assertAlmostEqual(sum(s["weight"] for s in theme["signals"]), 1.0, places=4)

    def test_retired_themes_are_skipped_unless_requested(self):
        self.assertEqual(themes.load_themes("/nonexistent-directory"), [])

    def test_every_shipped_theme_declares_a_usable_definition(self):
        loaded = themes.load_themes()
        self.assertGreater(len(loaded), 1, "expected the shipped theme set, not just one file")
        for theme in loaded:
            with self.subTest(theme=theme["id"]):
                self.assertAlmostEqual(sum(s["weight"] for s in theme["signals"]), 1.0, places=4)
                self.assertEqual(theme["guardrails"]["max_price_momentum_contribution"], 0.0)
                # Unscoped themes rank on filing language alone, which is how a bank ends up
                # published as top exposure to a hardware buildout.
                self.assertTrue(theme["sectors"], "shipped themes must declare a sector scope")
                self.assertTrue(theme["seed_tickers"])
                self.assertTrue((theme.get("keywords") or {}).get("include"))

    def test_a_capex_pull_through_signal_without_a_universe_is_rejected(self):
        problems = themes.validate_theme({**BASE_THEME, "signals": [
            {"name": "filing_keyword_density_trend", "weight": 0.5},
            {"name": "spender_capex_growth", "weight": 0.5},   # nobody's capex to read
        ]})
        self.assertTrue(any("universe" in problem for problem in problems), problems)

    def test_a_theme_measured_only_on_its_spenders_is_rejected(self):
        problems = themes.validate_theme({**BASE_THEME, "signals": [
            {"name": "spender_capex_growth", "weight": 1, "universe": ["MSFT"]},
        ]})
        self.assertTrue(any("company-specific" in problem for problem in problems), problems)

    def test_a_signal_with_a_universe_is_marked_theme_level(self):
        theme = build(signals=[
            {"name": "filing_keyword_density_trend", "weight": 0.5},
            {"name": "spender_capex_growth", "weight": 0.5, "universe": ["MSFT", "GOOGL"]},
        ])
        by_name = {signal["name"]: signal for signal in theme["signals"]}
        self.assertFalse(by_name["filing_keyword_density_trend"]["theme_level"])
        self.assertTrue(by_name["spender_capex_growth"]["theme_level"])


class ThemeScopeTests(unittest.TestCase):
    def test_a_theme_without_a_declared_scope_admits_everything(self):
        theme = build()
        self.assertTrue(themes.in_theme_scope(theme, {"sector": "Financial Services"}))

    def test_scope_matching_ignores_case_and_surrounding_space(self):
        theme = build(sectors=["Technology"])
        self.assertTrue(themes.in_theme_scope(theme, {"sector": " technology "}))
        self.assertFalse(themes.in_theme_scope(theme, {"sector": "Financial Services"}))
        self.assertFalse(themes.in_theme_scope(theme, {}))

    def test_an_out_of_scope_company_is_never_even_measured(self):
        # The point is not only that the bank is absent from the published rows: an
        # out-of-scope name must not cost a filing fetch to reject.
        theme = build(sectors=["Technology"])
        asked = []

        def provider(ticker, _theme):
            asked.append(ticker)
            return {"segment_revenue_share": 0.5, "filing_keyword_density_trend": 0.4}

        rows = [{"ticker": "CHIP", "sector": "Technology", "components": {"fundamentals": 70}},
                {"ticker": "BANK", "sector": "Financial Services",
                 "components": {"fundamentals": 90}}]
        screen = themes.build_theme_screen([theme], rows, provider)
        self.assertEqual(asked, ["CHIP"])
        self.assertEqual([row["ticker"] for row in screen["themes"][0]["rows"]], ["CHIP"])


class ExposureScoringTests(unittest.TestCase):
    def test_stronger_evidence_scores_higher(self):
        theme = build()
        strong = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.5, "filing_keyword_density_trend": 0.4,
            "hyperscaler_capex_growth": 0.3})
        weak = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.02, "filing_keyword_density_trend": -0.3,
            "hyperscaler_capex_growth": -0.1})
        self.assertGreater(strong["theme_exposure_score"], weak["theme_exposure_score"])

    def test_min_signals_required_blocks_a_single_source_reading(self):
        # ASC 280 segment granularity is management-determined, so one segment number is
        # never allowed to carry a theme on its own.
        theme = build()
        result = themes.score_theme_exposure(theme, {"segment_revenue_share": 0.9})
        self.assertIsNone(result["theme_exposure_score"])
        self.assertFalse(result["eligible"])

    def test_a_euphoric_valuation_is_excluded_not_promoted(self):
        theme = build()
        result = themes.score_theme_exposure(
            theme, {"segment_revenue_share": 0.6, "filing_keyword_density_trend": 0.5},
            valuation_percentile=96)
        self.assertIsNotNone(result["theme_exposure_score"])
        self.assertFalse(result["eligible"])
        self.assertTrue(any("valuation" in reason for reason in result["excluded_by"]))

    def test_lagging_evidence_alone_fails_the_confirmation_guardrail(self):
        theme = build()
        result = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.6,
            "filing_keyword_density_trend": -0.4,   # the company talks about it less
            "hyperscaler_capex_growth": -0.4,       # and the spenders are pulling back
        })
        self.assertFalse(result["eligible"])
        self.assertTrue(any("leading signal" in reason for reason in result["excluded_by"]))

    def test_a_theme_wide_reading_cannot_confirm_one_companys_exposure(self):
        # The failure this closes: the spenders' capex reading is identical for every
        # candidate, so accepting it as confirmation confirmed every company at once - which
        # is how names whose only company-specific evidence was flat filing language were
        # published as fully-cleared exposure.
        theme = build(signals=[
            {"name": "filing_keyword_density_trend", "weight": 0.5},
            {"name": "spender_capex_growth", "weight": 0.5, "universe": ["MSFT", "GOOGL"]},
        ])
        theme_wide_only = themes.score_theme_exposure(theme, {
            "filing_keyword_density_trend": -0.2,   # this company says less about it
            "spender_capex_growth": 0.8,            # but the spenders are spending
        })
        self.assertFalse(theme_wide_only["eligible"])
        self.assertEqual(theme_wide_only["leading_signals_fired"], [])
        self.assertEqual(theme_wide_only["theme_level_signals_fired"], ["spender_capex_growth"])
        self.assertEqual(theme_wide_only["company_signals_answered"], 1)

        with_company_evidence = themes.score_theme_exposure(theme, {
            "filing_keyword_density_trend": 0.6, "spender_capex_growth": 0.8})
        self.assertTrue(with_company_evidence["eligible"])
        self.assertEqual(with_company_evidence["leading_signals_fired"],
                         ["filing_keyword_density_trend"])

    def test_the_general_and_ai_specific_capex_signals_score_identically(self):
        reading = 0.3
        self.assertEqual(themes.normalize_signal("spender_capex_growth", reading),
                         themes.normalize_signal("hyperscaler_capex_growth", reading))

    def test_price_signals_are_ignored_even_if_supplied(self):
        # Defence in depth: validation rejects them at config load, and scoring ignores
        # them if one reaches this far by any other route.
        theme = build()
        without = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.2})
        with_price = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.2,
            "price_momentum": 99, "return_12m": 250})
        self.assertEqual(without["theme_exposure_score"], with_price["theme_exposure_score"])

    def test_confidence_tracks_how_much_signal_weight_answered(self):
        theme = build()
        partial = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.2})
        full = themes.score_theme_exposure(theme, {
            "segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.2,
            "hyperscaler_capex_growth": 0.2})
        self.assertLess(partial["confidence"], full["confidence"])
        self.assertEqual(full["confidence"], 1.0)


class OpportunityRankingTests(unittest.TestCase):
    def test_cheap_exposure_outranks_expensive_exposure(self):
        cheap = themes.opportunity_score(80, 75, valuation_percentile=20)
        expensive = themes.opportunity_score(80, 75, valuation_percentile=95)
        self.assertGreater(cheap, expensive)

    def test_quality_matters_at_equal_exposure(self):
        self.assertGreater(themes.opportunity_score(80, 85, 50),
                           themes.opportunity_score(80, 40, 50))

    def test_missing_inputs_return_nothing_rather_than_a_guess(self):
        self.assertIsNone(themes.opportunity_score(None, 70, 50))
        self.assertIsNone(themes.opportunity_score(80, None, 50))


class ScreenAssemblyTests(unittest.TestCase):
    def test_screen_ranks_eligible_names_above_excluded_ones(self):
        theme = build()
        rows = [
            {"ticker": "CHEAP", "name": "Cheap Co", "components": {"fundamentals": 78},
             "sector_valuation_percentile": 85},   # cheapness 85 -> expensiveness 15
            {"ticker": "HYPED", "name": "Hyped Co", "components": {"fundamentals": 78},
             "sector_valuation_percentile": 2},    # expensiveness 98 -> excluded
        ]
        signals = {"segment_revenue_share": 0.5, "filing_keyword_density_trend": 0.4,
                   "hyperscaler_capex_growth": 0.3}
        screen = themes.build_theme_screen([theme], rows, lambda ticker, t: signals)
        published = screen["themes"][0]["rows"]
        self.assertEqual(published[0]["ticker"], "CHEAP")
        self.assertFalse(published[1]["eligible"])
        self.assertEqual(screen["themes"][0]["eligible_count"], 1)

    def test_a_failing_signal_provider_does_not_sink_the_screen(self):
        theme = build()
        rows = [{"ticker": "AAA", "components": {"fundamentals": 70}},
                {"ticker": "BBB", "components": {"fundamentals": 70}}]

        def provider(ticker, _theme):
            if ticker == "AAA":
                raise RuntimeError("EDGAR timeout")
            return {"segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.3}

        screen = themes.build_theme_screen([theme], rows, provider)
        self.assertEqual([row["ticker"] for row in screen["themes"][0]["rows"]], ["BBB"])

    def test_by_ticker_index_is_emitted_for_cross_referencing(self):
        theme = build()
        rows = [{"ticker": "AAA", "components": {"fundamentals": 70}}]
        screen = themes.build_theme_screen(
            [theme], rows,
            lambda t, th: {"segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.3})
        self.assertIn("AAA", screen["by_ticker"])
        entry = screen["by_ticker"]["AAA"][0]
        self.assertEqual(entry["theme_id"], "test_theme")
        # Confidence travels with the index so a cross-theme reader can tell two
        # well-evidenced exposures from two thin ones.
        self.assertEqual(entry["confidence"], 0.7)

    def test_empty_screen_still_satisfies_the_published_contract(self):
        screen = themes.empty_screen("no SEC credentials")
        self.assertEqual(screen["themes"], [])
        self.assertIn("unavailable_reason", screen)

    def test_each_candidate_group_is_published_on_its_own_quota(self):
        # The regression this locks: one global cap let leaders take every published slot,
        # so the sector-connected group - the only one that surfaces a name before the
        # leaderboard does - shipped three rows out of dozens scored.
        theme = build()
        rows = [{"ticker": f"LEAD{index}", "candidate_source": "published_leader",
                 "components": {"fundamentals": 90}} for index in range(5)]
        rows += [{"ticker": f"PEER{index}", "candidate_source": "sector_peer",
                  "components": {"fundamentals": 40}} for index in range(5)]
        screen = themes.build_theme_screen(
            [theme], rows,
            lambda ticker, _theme: {"segment_revenue_share": 0.5,
                                    "filing_keyword_density_trend": 0.4},
            limit_per_group=2)
        published = screen["themes"][0]["rows"]
        sources = [row["candidate_source"] for row in published]
        self.assertEqual(sources.count("published_leader"), 2)
        self.assertEqual(sources.count("sector_peer"), 2)
        # Pre-truncation sizes stay published so the UI can say how much it is hiding.
        self.assertEqual(screen["themes"][0]["group_counts"], {"leaders": 5, "connected": 5})
        self.assertEqual(screen["themes"][0]["count"], 10)

    def test_a_holding_is_grouped_with_the_leaders_not_the_connected_names(self):
        theme = build()
        rows = [{"ticker": "HELD", "candidate_source": "portfolio",
                 "components": {"fundamentals": 60}},
                {"ticker": "PEER", "candidate_source": "sector_peer",
                 "components": {"fundamentals": 60}}]
        screen = themes.build_theme_screen(
            [theme], rows,
            lambda ticker, _theme: {"segment_revenue_share": 0.5,
                                    "filing_keyword_density_trend": 0.4})
        self.assertEqual(screen["themes"][0]["group_counts"], {"leaders": 1, "connected": 1})

    def test_one_company_is_indexed_under_every_theme_it_is_exposed_to(self):
        # What the cross-theme view on the screen is assembled from.
        first, second = build(), build(id="second_theme", display_name="Second")
        rows = [{"ticker": "AAA", "components": {"fundamentals": 70}}]
        screen = themes.build_theme_screen(
            [first, second], rows,
            lambda ticker, _theme: {"segment_revenue_share": 0.4,
                                    "filing_keyword_density_trend": 0.3})
        self.assertEqual([entry["theme_id"] for entry in screen["by_ticker"]["AAA"]],
                         ["test_theme", "second_theme"])


class CandidateExpansionTests(unittest.TestCase):
    def _research(self):
        # NVDA is the theme's seed ticker. AMD shares NVDA's sector (both classify into
        # the same "sector:technology" peer group via peer_groups.peer_group, since
        # neither is a bank/insurer/REIT/utility/commodity producer), so it should be
        # pulled in as a sector_peer candidate even though it never makes the published
        # leaderboard. UNRELATED sits in a different sector and must never be pulled in.
        return [
            {"ticker": "NVDA", "sector": "Technology", "score": 90},
            {"ticker": "AMD", "sector": "Technology", "score": 60},
            {"ticker": "MSFT", "sector": "Technology", "score": 55},
            {"ticker": "UNRELATED", "sector": "Utilities", "score": 80},
        ]

    def test_seed_tickers_sector_peers_are_added_as_candidates(self):
        theme = build(seed_tickers=["NVDA"])
        research = self._research()
        ranked = [research[0]]  # only NVDA is a published leader
        candidates = themes.expand_theme_candidates(
            [theme], research, ranked, portfolio_symbols=[])
        tickers = {row["ticker"] for row in candidates}
        self.assertIn("AMD", tickers)
        self.assertIn("MSFT", tickers)
        self.assertNotIn("UNRELATED", tickers)

    def test_every_candidate_is_tagged_with_its_source(self):
        theme = build(seed_tickers=["NVDA"])
        research = self._research()
        ranked = [research[0]]
        candidates = themes.expand_theme_candidates(
            [theme], research, ranked, portfolio_symbols=["MSFT"])
        by_ticker = {row["ticker"]: row for row in candidates}
        self.assertEqual(by_ticker["NVDA"]["candidate_source"], "published_leader")
        self.assertEqual(by_ticker["MSFT"]["candidate_source"], "portfolio")
        self.assertEqual(by_ticker["AMD"]["candidate_source"], "sector_peer")

    def test_a_ticker_already_published_or_held_is_not_duplicated_as_a_peer(self):
        theme = build(seed_tickers=["NVDA"])
        research = self._research()
        ranked = [research[0]]
        candidates = themes.expand_theme_candidates(
            [theme], research, ranked, portfolio_symbols=["AMD"])
        amd_rows = [row for row in candidates if row["ticker"] == "AMD"]
        self.assertEqual(len(amd_rows), 1)
        self.assertEqual(amd_rows[0]["candidate_source"], "portfolio")

    def test_expansion_is_capped_per_theme(self):
        theme = build(seed_tickers=["NVDA"])
        research = [{"ticker": "NVDA", "sector": "Technology", "score": 100}] + [
            {"ticker": f"PEER{i}", "sector": "Technology", "score": 100 - i}
            for i in range(30)
        ]
        candidates = themes.expand_theme_candidates(
            [theme], research, ranked=[research[0]], portfolio_symbols=[],
            limit_per_theme=5)
        peers = [row for row in candidates if row["candidate_source"] == "sector_peer"]
        self.assertEqual(len(peers), 5)
        # Highest-scoring peers win the capped slots.
        self.assertEqual({row["ticker"] for row in peers}, {f"PEER{i}" for i in range(5)})

    def test_peer_expansion_respects_the_themes_declared_scope(self):
        # A peer group is coarse - business-profile groups span whole sectors - so scope is
        # what stops a theme from adopting neighbours its supply chain cannot contain.
        theme = build(seed_tickers=["NVDA"], sectors=["Technology"])
        research = self._research() + [
            {"ticker": "BANK", "sector": "Technology", "score": 70},
        ]
        candidates = themes.expand_theme_candidates(
            [build(seed_tickers=["NVDA"], sectors=["Healthcare"])], research,
            ranked=[research[0]], portfolio_symbols=[])
        self.assertEqual({row["ticker"] for row in candidates
                          if row["candidate_source"] == "sector_peer"}, set())
        in_scope = themes.expand_theme_candidates(
            [theme], research, ranked=[research[0]], portfolio_symbols=[])
        self.assertIn("AMD", {row["ticker"] for row in in_scope})

    def test_a_theme_whose_seed_tickers_were_never_scored_this_run_expands_nothing(self):
        theme = build(seed_tickers=["NOTSCORED"])
        research = self._research()
        candidates = themes.expand_theme_candidates(
            [theme], research, ranked=[], portfolio_symbols=[])
        self.assertEqual(candidates, [])


class SignalMeasurementTests(unittest.TestCase):
    def test_keyword_density_counts_hits_per_thousand_words(self):
        text = " ".join(["filler"] * 990 + ["HBM"] * 10)
        self.assertAlmostEqual(ts.keyword_density(text, ["hbm"]), 10.0, places=1)

    def test_excluded_buzzwords_are_netted_out(self):
        text = "AI-powered marketing " * 50
        plain = ts.keyword_density(text, ["ai"])
        guarded = ts.keyword_density(text, ["ai"], ["ai-powered marketing"])
        self.assertGreater(plain, guarded)
        self.assertEqual(guarded, 0.0)

    def test_html_markup_does_not_inflate_the_word_count(self):
        self.assertGreater(ts.keyword_density("<p><b>HBM</b> memory</p>", ["hbm"]), 0)

    def test_density_trend_is_a_relative_change(self):
        self.assertAlmostEqual(ts.density_trend(1.5, 1.0), 0.5)
        self.assertIsNone(ts.density_trend(1.5, 0))
        self.assertIsNone(ts.density_trend(None, 1.0))

    def test_segment_share_is_capped_at_full_revenue(self):
        self.assertAlmostEqual(ts.segment_share(400, 1000), 0.4)
        self.assertEqual(ts.segment_share(1500, 1000), 1.0)
        self.assertIsNone(ts.segment_share(400, 0))

    def test_customer_overlap_matches_named_major_customers(self):
        share = ts.customer_overlap_share({"Microsoft Corporation": 0.18, "Acme Ltd": 0.11},
                                          ["MSFT", "MICROSOFT"])
        self.assertAlmostEqual(share, 0.18)
        self.assertIsNone(ts.customer_overlap_share({}, ["MSFT"]))

    def test_growth_rate_reads_a_newest_first_series(self):
        self.assertAlmostEqual(ts.growth_rate([120, 100]), 0.2)
        self.assertIsNone(ts.growth_rate([120]))


class SignalNormalizationTests(unittest.TestCase):
    def test_each_signal_family_maps_onto_zero_to_one_hundred(self):
        for name, value in (("segment_revenue_share", 0.5),
                            ("filing_keyword_density_trend", 0.3),
                            ("customer_concentration_to_spenders", 0.4),
                            ("hyperscaler_capex_growth", 0.25)):
            with self.subTest(signal=name):
                score = themes.normalize_signal(name, value)
                self.assertTrue(0 <= score <= 100)

    def test_a_declining_signal_scores_below_neutral(self):
        self.assertLess(themes.normalize_signal("filing_keyword_density_trend", -0.3), 50)
        self.assertGreater(themes.normalize_signal("filing_keyword_density_trend", 0.3), 50)

    def test_unparseable_readings_are_unanswered_not_zero(self):
        self.assertIsNone(themes.normalize_signal("segment_revenue_share", None))
        self.assertIsNone(themes.normalize_signal("segment_revenue_share", "n/a"))


if __name__ == "__main__":
    unittest.main()
