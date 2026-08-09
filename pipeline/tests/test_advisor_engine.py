import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import (MODIFIERS, RANKING_WEIGHTS, apply_challenger_modifiers,
                            build_research, concentration_risk_modifier,
                            geographic_concentration_modifier, insider_modifier,
                            institutional_ownership_modifier, macro_regime_modifier,
                            sentiment_score, shrink_research_components, technical_factors,
                            technical_score_from_parts)
from scorer import SETTINGS


class AdvisorEngineTests(unittest.TestCase):
    def test_ranking_is_fundamentals_dominant(self):
        self.assertAlmostEqual(sum(RANKING_WEIGHTS.values()), 1.0, places=6)
        self.assertGreaterEqual(RANKING_WEIGHTS["fundamentals"], 0.7)
        self.assertGreater(RANKING_WEIGHTS["fundamentals"],
                           RANKING_WEIGHTS["market_behavior"] + RANKING_WEIGHTS["news_sentiment"])

    def test_news_sentiment_is_a_tilt_not_a_core_component(self):
        # Headline sentiment alpha decays within days, so it must not carry the weight of a
        # component that is measured over quarters.
        self.assertLessEqual(RANKING_WEIGHTS["news_sentiment"], 0.05)

    def test_peg_pe_and_price_to_sales_change_the_rank_score(self):
        base = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "price_to_book": 3, "return_on_equity": 0.18, "free_cash_flow_yield": 0.06,
            "profit_margin": 0.15, "debt_to_equity": 0.6, "current_ratio": 1.5,
            "revenue_growth": 0.10, "earnings_growth": 0.10,
        }
        attractive = {**base, "peg": 0.9, "forward_pe": 20, "price_to_sales": 4}
        expensive = {**base, "peg": 3.2, "forward_pe": 55, "price_to_sales": 26}
        closes = [100 + index * 0.1 for index in range(100)]
        good = build_research("TEST", attractive, closes, closes, [])
        bad = build_research("TEST", expensive, closes, closes, [])
        self.assertGreater(good["components"]["fundamentals"], bad["components"]["fundamentals"])
        self.assertGreater(good["score"], bad["score"])

    def test_technical_score_has_risk_and_relative_strength(self):
        closes = [100 + index * 0.4 for index in range(300)]
        benchmark = [100 + index * 0.1 for index in range(300)]
        volumes = [1_000_000.0] * 300
        score, detail = technical_factors(closes, benchmark, volumes)
        self.assertGreater(score, 50)
        self.assertGreater(detail["relative_strength_20d"], 0)
        self.assertEqual(detail["coverage"], 1.0)

    def test_max_drawdown_and_volume_confirmation_are_scored(self):
        rising = [100 + index for index in range(300)]
        broken = [100 + index for index in range(150)] + [250 - index * 1.2 for index in range(150)]
        volumes = [1_000_000.0] * 300
        healthy_score, healthy = technical_factors(rising, rising, volumes)
        broken_score, damaged = technical_factors(broken, rising, volumes)
        self.assertGreater(healthy_score, broken_score)
        self.assertLess(damaged["max_drawdown_252d"], -30)
        self.assertGreaterEqual(healthy["volume_ratio_60d"], 1.0)

    def test_fundamentals_drive_research_score_and_explanations(self):
        snap = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 0.9, "forward_pe": 22, "price_to_sales": 4, "price_to_book": 2.5,
            "return_on_equity": 0.22, "free_cash_flow_yield": 0.08, "profit_margin": 0.21,
            "debt_to_equity": 0.4, "current_ratio": 2.0, "revenue_growth": 0.15,
            "earnings_growth": 0.18, "return_on_invested_capital": 0.21, "cash_conversion": 1.05,
            "interest_coverage": 18, "net_debt_to_ebitda": 0.4, "altman_z": 6.0,
            "ev_to_ebitda": 11, "ev_to_ebit": 13, "ev_to_sales": 4.2, "ev_to_fcf": 20,
            "fcf_growth_3y": 0.14, "gross_profits_to_assets": 0.35,
            "operating_margin_trend": 0.02, "earnings_surprise": 6.0,
            "net_buyback_yield": 0.03, "stock_comp_to_revenue": 0.02,
            "capex_to_depreciation": 1.1, "asset_growth": 0.06,
            "accruals_ratio": -0.02, "piotroski_f": 8.0, "altman_z_variant": "z_double_prime",
            "days_sales_outstanding_trend": -0.02, "inventory_days_trend": 0.01,
        }
        closes = [100 + index * 0.3 for index in range(100)]
        row = build_research("TEST", snap, closes, closes, [], extended=snap)
        self.assertGreater(row["components"]["fundamentals"], 75)
        self.assertIn(row["stance"], ("ATTRACTIVE", "PROMISING"))
        self.assertTrue(any("valuation" in item.lower() for item in row["strengths"]))
        self.assertGreater(row["confidence"], 0.8)
        self.assertEqual(row["recommendation"]["action"], "HOLD")

    def test_two_factors_are_required_before_any_trim(self):
        weak = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 4.0, "forward_pe": 70, "price_to_sales": 30, "price_to_book": 18,
            "return_on_equity": 0.01, "free_cash_flow_yield": -0.02, "profit_margin": -0.05,
            "debt_to_equity": 3.5, "current_ratio": 0.6, "revenue_growth": -0.15,
            "earnings_growth": -0.4, "interest_coverage": 1.1, "accruals_ratio": 0.18,
            "piotroski_f": 2.0, "cash_conversion": 0.2, "return_on_invested_capital": 0.01,
        }
        # Fundamentals broken and the chart broken: two independent factors, so guidance acts.
        falling = [200 - index * 0.6 for index in range(300)]
        rising = [100 + index * 0.3 for index in range(300)]
        acted = build_research("TEST", weak, falling, rising, [], extended=weak)
        self.assertIn(acted["recommendation"]["action"], ("TRIM", "SELL"))
        self.assertGreaterEqual(acted["recommendation"]["agreement_count"], 2)
        self.assertGreater(acted["recommendation"]["suggested_trim_pct"], 0)

        # Same broken fundamentals, healthy chart: one factor only, so it is a watch item.
        watched = build_research("TEST", weak, rising, rising, [], extended=weak)
        self.assertEqual(watched["recommendation"]["action"], "WATCH")
        self.assertEqual(watched["recommendation"]["suggested_trim_pct"], 0)

    def test_modifiers_are_bounded_and_explained(self):
        snap = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
                "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18}
        crowded = {"short_percent_of_float": 0.22, "days_to_cover": 9.0,
                   "average_dollar_volume": 2_000_000}
        closes = [100 + index * 0.2 for index in range(300)]
        plain = build_research("TEST", snap, closes, closes, [])
        pressured = build_research("TEST", snap, closes, closes, [], extended=crowded)
        self.assertLess(pressured["score"], plain["score"])
        self.assertGreaterEqual(pressured["modifiers"]["total"], -15)
        self.assertTrue(pressured["modifiers"]["notes"])
        self.assertEqual(plain["base_score"], pressured["base_score"])

    def test_missing_evidence_lowers_confidence(self):
        sparse = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False, "forward_pe": 20}
        row = build_research("TEST", sparse, [100 + i for i in range(100)], None, [])
        self.assertLess(row["confidence"], 0.5)

    def test_macro_is_sector_sensitive_and_capped(self):
        regime = {
            "coverage": 1.0,
            "factors": {
                "rates": {"score": 20},
                "inflation": {"score": 50},
                "labor": {"score": 55},
                "yield_curve": {"score": 90},
            },
        }
        tech_points, tech_note = macro_regime_modifier({"sector": "Technology"}, regime)
        bank_points, bank_note = macro_regime_modifier({"sector": "Financial Services"}, regime)

        self.assertLess(tech_points, bank_points)
        self.assertGreaterEqual(tech_points, -3)
        self.assertLessEqual(bank_points, 3)
        self.assertIn("Technology", tech_note)
        self.assertIn("Financial Services", bank_note)


class RebuiltTechnicalTests(unittest.TestCase):
    """The invented trend/risk constants are gone; these lock in what replaced them."""

    def test_momentum_skips_the_most_recent_month(self):
        # A year of steady gains that reverses hard in the final month. Raw 12-month return
        # is dragged down by the reversal; 12-1 momentum, which is what the literature
        # documents, still sees the underlying trend.
        rising = [100 * (1.001 ** index) for index in range(300)]
        reversed_last_month = rising[:-21] + [rising[-21] * (1 - 0.004 * step)
                                              for step in range(1, 22)]
        _, detail = technical_factors(reversed_last_month, rising, [1e6] * 300)
        self.assertGreater(detail["momentum_12_1_pct"], 0)
        self.assertLess(detail["return_20d"], 0)

    def test_risk_is_a_real_ratio_not_an_invented_penalty(self):
        trend = [100 * (1.0008 ** index) for index in range(300)]
        # Both series drift upward at the same rate; only the size of the wobble differs.
        steady = [value * (1.002 if index % 3 else 0.998) for index, value in enumerate(trend)]
        choppy = [value * (1.06 if index % 3 else 0.94) for index, value in enumerate(trend)]
        _, calm = technical_factors(steady, trend, [1e6] * 300)
        _, wild = technical_factors(choppy, trend, [1e6] * 300)
        self.assertIsNotNone(calm["sortino_ratio"])
        self.assertIsNotNone(calm["sharpe_ratio"])
        self.assertGreater(calm["risk_adjusted"], wild["risk_adjusted"])

    def test_stock_and_etf_models_compute_the_same_sharpe(self):
        # The point of the shared risk_metrics module: a Sharpe of 1.2 has to mean the same
        # thing on the stock screen and the ETF screen.
        import fetch_etfs
        from risk_metrics import daily_returns as shared_daily_returns
        closes = [100 * (1.0009 ** index) for index in range(300)]
        _, detail = technical_factors(closes, closes, [1e6] * 300)
        etf_sharpe = fetch_etfs.sharpe_ratio(shared_daily_returns(closes)[-252:])
        self.assertEqual(detail["sharpe_ratio"], etf_sharpe)

    def test_short_history_lowers_coverage_instead_of_faking_a_score(self):
        short = [100 + index * 0.2 for index in range(60)]
        long = [100 + index * 0.2 for index in range(400)]
        _, sparse = technical_factors(short, long, [1e6] * 60)
        _, full = technical_factors(long, long, [1e6] * 400)
        self.assertLess(sparse["coverage"], full["coverage"])
        self.assertIsNone(sparse.get("momentum_12_1_pct"))

    def test_low_beta_is_rewarded_rather_than_volatility_punished(self):
        closes = [100 + index * 0.2 for index in range(300)]
        _, defensive = technical_factors(closes, closes, [1e6] * 300, extended={"beta": 0.8})
        _, aggressive = technical_factors(closes, closes, [1e6] * 300, extended={"beta": 2.4})
        self.assertGreater(defensive["low_beta"], aggressive["low_beta"])

    def test_technical_extended_is_computed_and_weighted_far_below_fundamentals(self):
        closes = [100 * (1.001 ** index) for index in range(300)]
        volumes = [1e6 + index * 1000 for index in range(300)]

        score, detail = technical_factors(closes, closes, volumes)

        self.assertIn("technical_extended", detail)
        self.assertIn("technical_extended_detail", detail)
        self.assertIsNotNone(score)
        # technical_extended's weight (0.06) against the rest of market_behavior (0.94), and
        # market_behavior itself is 18% of the total composite -- roughly 1% of the total
        # score, nowhere near fundamentals' 78%. Confirm it stays a minority weight within
        # its own component rather than dominating market_behavior.
        from advisor_engine import TECHNICAL_WEIGHTS
        self.assertLess(TECHNICAL_WEIGHTS["technical_extended"], TECHNICAL_WEIGHTS["momentum_12_1"])
        self.assertLess(TECHNICAL_WEIGHTS["technical_extended"] / sum(TECHNICAL_WEIGHTS.values()), 0.10)

    def test_neutral_treatment_drops_relative_strength_and_redistributes_weight(self):
        parts = {name: 50.0 for name in (
            "momentum_12_1", "risk_adjusted", "drawdown_resilience",
            "volume_confirmation", "low_beta",
        )}
        parts["relative_strength"] = 100.0
        legacy, _ = technical_score_from_parts(parts, "legacy_momentum")
        neutral, detail = technical_score_from_parts(parts, "neutral")
        self.assertGreater(legacy, neutral)
        self.assertNotIn("relative_strength", detail["weights"])
        self.assertEqual(neutral, 50.0)

    def test_reversal_inverts_relative_strength_at_reduced_weight(self):
        parts = {name: 50.0 for name in (
            "momentum_12_1", "risk_adjusted", "drawdown_resilience",
            "volume_confirmation", "low_beta",
        )}
        parts["relative_strength"] = 90.0
        reversal, detail = technical_score_from_parts(parts, "reversal", reversal_weight=0.08)
        self.assertLess(reversal, 50.0)
        self.assertEqual(detail["parts"]["relative_strength"], 10.0)


class SignalCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.config = SETTINGS["challengers"]["signal_corrections"]

    def test_single_shrinkage_moves_sparse_extremes_toward_neutral(self):
        result = shrink_research_components(
            {"fundamentals": 100.0, "market_behavior": 100.0, "news_sentiment": 100.0},
            {"fundamentals": 0.1, "market_behavior": 0.1, "news_sentiment": 0.0},
            self.config,
        )
        self.assertGreater(result["base_score"], self.config["shrinkage_target"])
        self.assertLess(result["base_score"], result["raw_score"])

    def test_low_short_interest_receives_positive_fraction_of_cap(self):
        score, detail = apply_challenger_modifiers(
            50.0,
            {"sector": "Technology"},
            {"short_percent_of_float": 0.01},
            self.config,
            short_interest_rank={"percentile": 0.05, "normalization_scope": "sector"},
        )
        expected = (self.config["modifier_cap"]
                    * self.config["modifier_fractions"]["short_interest_reward"])
        self.assertEqual(detail["applied"]["short_interest"], expected)
        self.assertEqual(score, 50.0 + expected)

    def test_combined_challenger_modifier_is_capped_at_twenty(self):
        snapshot = {
            "sector": "Technology", "short_percent_of_float": 0.3,
            "days_to_cover": 20.0, "average_dollar_volume": 100_000,
            "analyst_target_upside": -50.0, "analyst_rating": 5.0, "analyst_count": 10,
        }
        _, detail = apply_challenger_modifiers(
            50.0, snapshot, snapshot, self.config, sector_percentile=0,
            short_interest_rank={"percentile": 1.0},
        )
        self.assertGreaterEqual(detail["total"], -self.config["modifier_cap"])
        self.assertEqual(detail["cap"], 20.0)


class SentimentWindowTests(unittest.TestCase):
    def _article(self, ticker, score, published_at):
        return {"published_at": published_at, "ticker": ticker,
                "ticker_sentiment": [{"ticker": ticker, "ticker_sentiment_score": score}]}

    def test_articles_outside_the_window_are_excluded(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        fresh = self._article("TEST", 0.5, "20260801T120000")
        stale = self._article("TEST", -0.9, "20260101T120000")
        score, detail = sentiment_score([fresh, stale], "TEST", window_days=7, now=now)
        self.assertEqual(detail["article_count"], 1)
        self.assertGreater(score, 50)

    def test_no_coverage_is_reported_unavailable_not_neutral(self):
        # A component with no evidence must not silently read as "neutral" - that fabricates
        # a data point. blend_research_components renormalizes over the components that
        # remain, rather than anchoring the blend on a manufactured 50.0.
        score, detail = sentiment_score([], "TEST")
        self.assertIsNone(score)
        self.assertEqual(detail["coverage"], 0.0)
        self.assertFalse(detail["news_available"])

    def test_nine_syndicated_copies_count_as_one_article(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        copies = [
            {
                "title": "Test Corp beats quarterly expectations",
                "url": f"https://publisher-{index}.example/story",
                "source": f"Publisher {index}",
                "published_at": "2026-08-02T10:00:00Z",
                "ticker": "TEST",
                "ticker_sentiment": [{
                    "ticker": "TEST",
                    "ticker_sentiment_score": 0.4,
                    "relevance_score": 82,
                }],
            }
            for index in range(9)
        ]

        score, detail = sentiment_score(copies, "TEST", now=now)

        self.assertGreater(score, 50)
        self.assertEqual(detail["raw_article_count"], 9)
        self.assertEqual(detail["article_count"], 1)
        self.assertEqual(detail["syndicated_copies_removed"], 8)
        self.assertEqual(detail["coverage"], 1 / detail["full_coverage_article_count"])

    def test_low_confidence_entity_match_is_discarded(self):
        article = self._article("TEST", -0.9, "20260801T120000")
        article["ticker_sentiment"][0]["relevance_score"] = 10

        score, detail = sentiment_score([article], "TEST",
                                        now=datetime(2026, 8, 2, tzinfo=timezone.utc))

        self.assertIsNone(score)
        self.assertFalse(detail["news_available"])
        self.assertEqual(detail["discarded_low_confidence"], 1)

    def test_unavailable_news_is_excluded_from_the_blend_not_treated_as_neutral(self):
        # A row with zero cleared news coverage must renormalize fundamentals/market_behavior
        # to fill the full weight, not silently blend in a manufactured 50.0 news score.
        snap = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
                "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18}
        closes = [100 + index * 0.2 for index in range(300)]
        row = build_research("TEST", snap, closes, closes, [])
        self.assertIsNone(row["components"]["news_sentiment"])
        self.assertFalse(row["news_available"])
        self.assertFalse(row["sentiment_detail"]["news_available"])
        expected_raw = round(
            (row["components"]["fundamentals"] * RANKING_WEIGHTS["fundamentals"]
             + row["components"]["market_behavior"] * RANKING_WEIGHTS["market_behavior"])
            / (RANKING_WEIGHTS["fundamentals"] + RANKING_WEIGHTS["market_behavior"]),
            1,
        )
        self.assertEqual(row["raw_score"], expected_raw)

    def test_filing_and_commentary_are_labelled_in_weight_detail(self):
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        filing = self._article("TEST", 0.3, "20260802T100000")
        filing.update({"title": "Test Corp files Form 8-K", "source": "SEC EDGAR",
                       "url": "https://www.sec.gov/Archives/example"})
        commentary = self._article("TEST", 0.2, "20260802T100000")
        commentary.update({"title": "Analysts discuss Test Corp", "source": "Example Finance",
                           "url": "https://example.com/analysis"})

        _, detail = sentiment_score([filing, commentary], "TEST", now=now)

        self.assertEqual(detail["filing_count"], 1)
        self.assertEqual(detail["commentary_count"], 1)
        self.assertEqual({row["content_type"] for row in detail["articles"]},
                         {"filing", "commentary"})


class InsiderModifierTests(unittest.TestCase):
    def test_opportunistic_cluster_buying_lifts_the_score(self):
        today = date.today()
        transactions = [
            {"side": "purchase", "value": 400_000, "date": (today - timedelta(days=5)).isoformat(),
             "owner_cik": f"000{index}", "owner_name": f"Insider {index}", "roles": ["director"]}
            for index in range(3)
        ]
        points, note = insider_modifier({"transactions": transactions})
        self.assertGreater(points, 0)
        self.assertIn("insider", note.lower())

    def test_routine_calendar_trades_contribute_nothing(self):
        # Same insider selling every March for three years: diversification, not a signal.
        transactions = [
            {"side": "sale", "value": 500_000, "date": f"{year}-03-15",
             "owner_cik": "0001", "owner_name": "Regular Seller", "roles": ["officer"]}
            for year in (date.today().year - 2, date.today().year - 1, date.today().year)
        ]
        points, _ = insider_modifier({"transactions": transactions})
        self.assertEqual(points, 0.0)

    def test_absent_insider_data_is_neutral(self):
        self.assertEqual(insider_modifier(None), (0.0, None))
        self.assertEqual(insider_modifier({"transactions": []}), (0.0, None))

    def test_modifier_respects_the_configured_cap(self):
        today = date.today()
        transactions = [
            {"side": "purchase", "value": 50_000_000, "date": today.isoformat(),
             "owner_cik": f"00{index}", "owner_name": f"Buyer {index}", "roles": ["director"]}
            for index in range(8)
        ]
        points, _ = insider_modifier({"transactions": transactions})
        self.assertLessEqual(points, MODIFIERS.get("insider_activity", {}).get("max_points", 5.0))


class ConcentrationRiskModifierTests(unittest.TestCase):
    def test_a_severe_disclosed_customer_share_penalizes_the_score(self):
        points, note = concentration_risk_modifier({"percentages": [0.35]})
        self.assertLess(points, 0.0)
        self.assertIn("customer", note.lower())

    def test_a_precomputed_summary_is_read_directly(self):
        points, note = concentration_risk_modifier(
            {"score_points": -2.0, "notes": ["largest named customer is 35% of revenue"]})
        self.assertEqual(points, -2.0)
        self.assertIn("35%", note)

    def test_absent_data_is_neutral(self):
        self.assertEqual(concentration_risk_modifier(None), (0.0, None))
        self.assertEqual(concentration_risk_modifier({"percentages": []}), (0.0, None))

    def test_points_never_exceed_the_configured_penalty(self):
        points, _ = concentration_risk_modifier({"percentages": [0.99]})
        self.assertGreaterEqual(
            points, -MODIFIERS.get("customer_concentration_risk", {}).get("max_penalty", 3.0))


class GeographicConcentrationModifierTests(unittest.TestCase):
    def test_a_severe_single_country_share_penalizes_the_score(self):
        points, note = geographic_concentration_modifier({"shares": {"us": 0.4, "cn": 0.6}})
        self.assertLess(points, 0.0)
        self.assertIn("geograph", note.lower())

    def test_diversified_international_revenue_with_no_single_country_dominant_is_neutral(self):
        points, note = geographic_concentration_modifier(
            {"shares": {"us": 0.4, "cn": 0.2, "de": 0.2, "jp": 0.2}})
        self.assertEqual(points, 0.0)

    def test_absent_data_is_neutral(self):
        self.assertEqual(geographic_concentration_modifier(None), (0.0, None))
        self.assertEqual(geographic_concentration_modifier({"shares": {}}), (0.0, None))


class BuildResearchDoesNotYetUseConcentrationOrGeographicRiskTests(unittest.TestCase):
    """Champion ``row["score"]`` must be identical regardless of concentration/geographic
    data - both are shadow-mode only (challenger score_variants) until their XBRL tagging
    coverage across the scored universe has actually been measured on a live run. A
    penalty-only modifier that only fires on tagged filers would otherwise systematically
    favor whichever companies happen not to have tagged the concept."""

    def setUp(self):
        self.snapshot = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "price_to_book": 3, "return_on_equity": 0.18, "free_cash_flow_yield": 0.06,
            "profit_margin": 0.15, "debt_to_equity": 0.6, "current_ratio": 1.5,
            "revenue_growth": 0.10, "earnings_growth": 0.10, "peg": 1.2, "forward_pe": 22,
            "price_to_sales": 5,
        }
        self.closes = [100 + index * 0.1 for index in range(100)]

    def test_build_research_has_no_parameter_for_either_signal(self):
        row = build_research("TEST", self.snapshot, self.closes, self.closes, [])
        with self.assertRaises(TypeError):
            build_research("TEST", self.snapshot, self.closes, self.closes, [],
                           concentration_risk={"percentages": [0.40]})
        self.assertIn("score", row)


class ChallengerOnlyShadowModeTests(unittest.TestCase):
    """The two concentration modifiers DO move the challenger score - that is the whole
    point of shadow mode: measurable, but not yet risking the live champion score."""

    def setUp(self):
        self.config = SETTINGS["challengers"]["signal_corrections"]

    def test_severe_customer_concentration_lowers_the_challenger_score_only(self):
        baseline, _ = apply_challenger_modifiers(70.0, {}, {}, self.config)
        concentrated, _ = apply_challenger_modifiers(
            70.0, {}, {}, self.config, concentration_risk={"percentages": [0.40]})
        self.assertLess(concentrated, baseline)

    def test_severe_geographic_concentration_lowers_the_challenger_score_only(self):
        baseline, _ = apply_challenger_modifiers(70.0, {}, {}, self.config)
        concentrated, _ = apply_challenger_modifiers(
            70.0, {}, {}, self.config,
            geographic_exposure={"shares": {"us": 0.3, "cn": 0.7}})
        self.assertLess(concentrated, baseline)


class InstitutionalOwnershipModifierTests(unittest.TestCase):
    def test_a_precomputed_positive_summary_lifts_the_score(self):
        points, note = institutional_ownership_modifier(
            {"score_points": 1.5, "notes": ["3 curated institutional manager(s) added a position"]})
        self.assertEqual(points, 1.5)
        self.assertIn("added", note)

    def test_a_precomputed_negative_summary_penalizes_the_score(self):
        points, _ = institutional_ownership_modifier({"score_points": -1.0, "notes": []})
        self.assertEqual(points, -1.0)

    def test_absent_data_is_neutral(self):
        self.assertEqual(institutional_ownership_modifier(None), (0.0, None))
        self.assertEqual(institutional_ownership_modifier({}), (0.0, None))

    def test_points_respect_the_configured_caps(self):
        points, _ = institutional_ownership_modifier({"score_points": 999.0, "notes": []})
        self.assertLessEqual(points, MODIFIERS.get("institutional_13f", {}).get("max_points", 3.0))


class BuildResearchWiresInstitutionalOwnershipIntoTheChampionScoreTests(unittest.TestCase):
    """Unlike concentration_risk/geographic_exposure, institutional_ownership IS back in
    the champion path (with lag decay baked into its input upstream) - this is the
    end-to-end proof it actually moves row["score"], not just a display field."""

    def setUp(self):
        self.snapshot = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "price_to_book": 3, "return_on_equity": 0.18, "free_cash_flow_yield": 0.06,
            "profit_margin": 0.15, "debt_to_equity": 0.6, "current_ratio": 1.5,
            "revenue_growth": 0.10, "earnings_growth": 0.10, "peg": 1.2, "forward_pe": 22,
            "price_to_sales": 5,
        }
        self.closes = [100 + index * 0.1 for index in range(100)]

    def test_corroborated_accumulation_raises_the_champion_score(self):
        baseline = build_research("TEST", self.snapshot, self.closes, self.closes, [])["score"]
        accumulating = build_research(
            "TEST", self.snapshot, self.closes, self.closes, [],
            institutional_ownership={"score_points": 2.0, "notes": []},
        )["score"]
        self.assertGreater(accumulating, baseline)

    def test_a_stale_filing_moves_the_score_less_than_a_fresh_one(self):
        # The decay itself lives in institutional_ownership.score_institutional_ownership,
        # applied before this reaches build_research - this just confirms a smaller
        # score_points input (as a decayed one would be) produces a smaller effect.
        fresh = build_research(
            "TEST", self.snapshot, self.closes, self.closes, [],
            institutional_ownership={"score_points": 2.0, "notes": []},
        )["score"]
        stale = build_research(
            "TEST", self.snapshot, self.closes, self.closes, [],
            institutional_ownership={"score_points": 0.2, "notes": []},
        )["score"]
        self.assertGreater(fresh, stale)


if __name__ == "__main__":
    unittest.main()
