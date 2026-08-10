import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import scorer

# A company that answers every metric the model asks for. Used wherever a test needs full
# coverage, so adding a metric means updating one fixture rather than hunting for six.
STRONG_TECH = {
    "is_etf": False, "sector": "Technology", "peg": 0.9, "forward_pe": 24,
    "price_to_sales": 4, "ev_to_sales": 4.2, "price_to_book": 2.5,
    "ev_to_ebitda": 9, "ev_to_ebit": 11, "ev_to_fcf": 17, "return_on_equity": 0.22,
    "return_on_invested_capital": 0.24, "gross_profits_to_assets": 0.38,
    "cash_conversion": 1.1, "free_cash_flow_yield": 0.08, "profit_margin": 0.20,
    "debt_to_equity": 0.4, "current_ratio": 2.1, "interest_coverage": 20,
    "net_debt_to_ebitda": 0.2, "altman_z": 5.5, "altman_z_variant": "z_double_prime",
    "revenue_growth": 0.20, "earnings_growth": 0.20, "fcf_growth_3y": 0.18,
    "operating_margin_trend": 0.03, "earnings_surprise": 9.0,
    "net_buyback_yield": 0.04, "stock_comp_to_revenue": 0.008,
    "capex_to_depreciation": 1.2, "asset_growth": 0.05,
    "accruals_ratio": -0.05, "piotroski_f": 8.5,
    "days_sales_outstanding_trend": -0.06, "inventory_days_trend": -0.06,
}


class ScorerTests(unittest.TestCase):
    def test_band_score_prefers_lower_valuation(self):
        bands = {"excellent": 1, "good": 2, "fair": 3, "rich": 4}
        self.assertEqual(scorer.band_score(0.8, bands), 100.0)
        self.assertEqual(scorer.band_score(5, bands), 10.0)

    def test_valuation_score_reweights_missing_metrics(self):
        score, parts = scorer.valuation_score({"is_etf": False, "peg": 1.0,
                                               "forward_pe": None, "price_to_sales": None})
        self.assertEqual(parts["peg"], 100.0)
        # A single answered metric earns the category full marks but almost no coverage,
        # so the confidence multiplier keeps the published score well short of that.
        self.assertEqual(parts["categories"]["valuation"], 100.0)
        self.assertLess(parts["coverage"], 0.1)
        self.assertLess(score, 70)

    def test_coverage_is_weighted_by_metric_importance(self):
        headline = {"is_etf": False, "sector": "Technology", "peg": 1.0, "forward_pe": 20,
                    "return_on_invested_capital": 0.2, "cash_conversion": 1.0}
        trivia = {"is_etf": False, "sector": "Technology", "inventory_days_trend": 0.0,
                  "days_sales_outstanding_trend": 0.0, "capex_to_depreciation": 1.2,
                  "price_to_tangible_book": 2.0}
        _, headline_parts = scorer.valuation_score(headline)
        _, trivia_parts = scorer.valuation_score(trivia)
        self.assertGreater(headline_parts["coverage"], trivia_parts["coverage"])

    def test_negative_net_debt_reads_as_a_strength(self):
        self.assertEqual(scorer.lower_is_better_score(-1.5, scorer.SETTINGS["fundamentals"]["net_debt_to_ebitda"]), 100.0)
        self.assertEqual(scorer.lower_is_better_score(6.0, scorer.SETTINGS["fundamentals"]["net_debt_to_ebitda"]), 10.0)

    def test_capex_is_scored_as_a_range_not_a_direction(self):
        bands = scorer.SETTINGS["fundamentals"]["capex_to_depreciation"]
        self.assertEqual(scorer.range_score(1.2, bands), 100.0)
        self.assertEqual(scorer.range_score(0.2, bands), 25.0)  # under-investing
        self.assertEqual(scorer.range_score(4.0, bands), 25.0)  # empire-building

    def test_sector_context_changes_forward_pe_score(self):
        tech_score, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 30})
        bank_score, _ = scorer.valuation_score({"is_etf": False, "sector": "Financial Services", "forward_pe": 30})
        self.assertGreater(tech_score, bank_score)

    def test_strong_fundamentals_score_across_all_categories(self):
        score, parts = scorer.valuation_score(STRONG_TECH)
        self.assertGreaterEqual(score, 95)
        self.assertEqual(parts["coverage"], 1.0)
        self.assertEqual(set(parts["categories"]),
                         {"valuation", "profitability", "financial_health", "growth",
                          "capital_allocation", "accounting_quality"})

    def test_accounting_red_flags_pull_the_score_down(self):
        base = {
            "is_etf": False, "sector": "Technology", "peg": 0.9, "forward_pe": 24,
            "price_to_sales": 4, "return_on_equity": 0.22, "return_on_invested_capital": 0.2,
            "profit_margin": 0.20, "revenue_growth": 0.20, "earnings_growth": 0.20,
        }
        clean = {**base, "accruals_ratio": -0.03, "cash_conversion": 1.05, "piotroski_f": 8,
                 "days_sales_outstanding_trend": -0.02}
        suspect = {**base, "accruals_ratio": 0.22, "cash_conversion": 0.3, "piotroski_f": 3,
                   "days_sales_outstanding_trend": 0.35}
        clean_score, _ = scorer.valuation_score(clean)
        suspect_score, _ = scorer.valuation_score(suspect)
        self.assertGreater(clean_score, suspect_score + 10)

    def test_leverage_shows_up_through_roic_and_interest_coverage(self):
        base = {"is_etf": False, "sector": "Industrials", "peg": 1.2, "forward_pe": 14,
                "return_on_equity": 0.25, "profit_margin": 0.10, "revenue_growth": 0.06}
        durable = {**base, "return_on_invested_capital": 0.18, "interest_coverage": 15,
                   "net_debt_to_ebitda": 0.8}
        levered = {**base, "return_on_invested_capital": 0.04, "interest_coverage": 1.6,
                   "net_debt_to_ebitda": 5.2}
        self.assertGreater(scorer.valuation_score(durable)[0], scorer.valuation_score(levered)[0])

    def test_suspiciously_low_pe_is_not_automatic_maximum(self):
        suspicious, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 5})
        healthy, _ = scorer.valuation_score({"is_etf": False, "sector": "Technology", "forward_pe": 20})
        self.assertGreater(healthy, suspicious)

    def test_bank_liquidity_is_displayed_but_not_scored_with_industrial_cutoffs(self):
        """Suppression follows the business profile, not the sector string.

        current_ratio is meaningless for a deposit-funded balance sheet and the registry
        suppresses it. debt_to_equity is not suppressed: financial leverage is a canonical
        bank and insurer input, and forcing it to null was the defect, not the feature.
        """
        _, parts = scorer.valuation_score({"is_etf": False, "sector": "Financial Services",
                                           "industry": "Banks - Regional",
                                           "price_to_tangible_book": 1.2, "debt_to_equity": 2.5,
                                           "current_ratio": 0.6})
        self.assertIsNone(parts["current_ratio"])
        self.assertIsNotNone(parts["debt_to_equity"])
        self.assertEqual(parts["applicability_profile"], "bank")
        self.assertIn("current_ratio", parts["suppressed_metrics"])

    def test_a_generic_financial_is_not_given_bank_exemptions(self):
        """"Financial Services" covers exchanges and asset managers too; only a profile the
        registry recognises earns a profile's suppressions."""
        _, parts = scorer.valuation_score({"is_etf": False, "sector": "Financial Services",
                                           "industry": "Capital Markets",
                                           "price_to_book": 1.2, "debt_to_equity": 0.4,
                                           "current_ratio": 1.8})
        self.assertEqual(parts["applicability_profile"], "general")
        self.assertIsNotNone(parts["current_ratio"])

    def test_label_thresholds(self):
        self.assertEqual(scorer.label_for(90), "HIGH CONVICTION")
        self.assertEqual(scorer.label_for(0), "LOW")


class RebalancedWeightTests(unittest.TestCase):
    """The weight table now follows the published evidence, so assert the shape of it."""

    def test_enterprise_multiples_outweigh_peg(self):
        # EV/EBITDA is the best-validated single value multiple in the literature; PEG's
        # support as a return predictor is thin. The weights must reflect that ordering.
        weights = scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"]
        self.assertGreater(weights["ev_to_ebitda"], weights["peg"] * 2)
        self.assertGreaterEqual(weights["ev_to_ebitda"], 0.26)

    def test_piotroski_outweighs_the_decayed_accruals_signal(self):
        weights = scorer.SETTINGS["fundamentals"]["metric_weights"]["accounting_quality"]
        self.assertGreater(weights["piotroski_f"], weights["accruals_ratio"])

    def test_every_bucket_and_category_sums_to_one(self):
        cfg = scorer.SETTINGS["fundamentals"]
        self.assertAlmostEqual(sum(cfg["category_weights"].values()), 1.0, places=6)
        for bucket, weights in cfg["metric_weights"].items():
            with self.subTest(bucket=bucket):
                self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)


class NewMetricScoringTests(unittest.TestCase):
    def test_gross_profitability_lifts_the_profitability_bucket(self):
        base = {"is_etf": False, "sector": "Technology", "return_on_invested_capital": 0.10,
                "profit_margin": 0.08}
        profitable = {**base, "gross_profits_to_assets": 0.40}
        unprofitable = {**base, "gross_profits_to_assets": 0.03}
        self.assertGreater(scorer.valuation_score(profitable)[1]["categories"]["profitability"],
                           scorer.valuation_score(unprofitable)[1]["categories"]["profitability"])

    def test_sales_multiple_prefers_enterprise_value_over_price(self):
        # Two identical-looking companies on price-to-sales; the levered one is more
        # expensive on EV/Sales and must score worse for it.
        cfg = scorer.SETTINGS["fundamentals"]
        unlevered, basis = scorer.sales_multiple_score(
            {"sector": "Technology", "price_to_sales": 4, "ev_to_sales": 4.1}, cfg)
        levered, _ = scorer.sales_multiple_score(
            {"sector": "Technology", "price_to_sales": 4, "ev_to_sales": 20.0}, cfg)
        self.assertEqual(basis, "ev_to_sales")
        self.assertGreater(unlevered, levered)

    def test_sales_multiple_falls_back_to_price_to_sales(self):
        cfg = scorer.SETTINGS["fundamentals"]
        score, basis = scorer.sales_multiple_score(
            {"sector": "Technology", "price_to_sales": 4}, cfg)
        self.assertEqual(basis, "price_to_sales")
        self.assertIsNotNone(score)

    def test_altman_z_is_scored_against_its_own_variant_bands(self):
        cfg = scorer.SETTINGS["fundamentals"]
        # 2.7 is "safe" under Z'' but only "fair" under the original manufacturing model.
        self.assertEqual(scorer.altman_score(2.7, "z_double_prime", cfg), 100.0)
        self.assertLess(scorer.altman_score(2.7, "z", cfg), 100.0)
        self.assertIsNone(scorer.altman_score(2.7, None, cfg))

    def test_tangible_book_is_only_scored_where_it_means_something(self):
        software = scorer.valuation_score({"is_etf": False, "sector": "Technology",
                                           "price_to_tangible_book": 40.0})[1]
        bank = scorer.valuation_score({"is_etf": False, "sector": "Financial Services",
                                       "price_to_tangible_book": 1.1})[1]
        self.assertIsNone(software["price_to_tangible_book"])
        self.assertIsNotNone(bank["price_to_tangible_book"])

    def test_asset_growth_penalizes_both_empire_building_and_shrinkage(self):
        bands = scorer.SETTINGS["fundamentals"]["asset_growth"]
        self.assertEqual(scorer.range_score(0.05, bands), 100.0)
        self.assertEqual(scorer.range_score(0.60, bands), 25.0)   # aggressive expansion
        self.assertEqual(scorer.range_score(-0.30, bands), 25.0)  # shrinking balance sheet

    def test_earnings_surprise_rewards_beating_expectations(self):
        base = {"is_etf": False, "sector": "Technology", "revenue_growth": 0.10,
                "earnings_growth": 0.10}
        beating = {**base, "earnings_surprise": 12.0}
        missing = {**base, "earnings_surprise": -8.0}
        self.assertGreater(scorer.valuation_score(beating)[1]["categories"]["growth"],
                           scorer.valuation_score(missing)[1]["categories"]["growth"])

    def test_bank_metrics_that_do_not_apply_leave_the_coverage_denominator(self):
        # A bank should not be marked down for lacking EV/EBITDA or an Altman Z; those
        # metrics do not apply to it, so they leave the denominator entirely. The same
        # answered metrics on a company where they *do* apply must score lower coverage.
        answered = {"is_etf": False, "forward_pe": 11, "return_on_equity": 0.14,
                    "interest_coverage": 8, "piotroski_f": 7.0}
        _, bank = scorer.valuation_score({**answered, "sector": "Financial Services",
                                          "price_to_tangible_book": 1.2})
        _, software = scorer.valuation_score({**answered, "sector": "Technology"})
        self.assertIsNone(bank["ev_to_ebitda"])
        self.assertIsNone(bank["altman_z"])
        self.assertGreater(bank["coverage"], software["coverage"])


class CrossSectionalNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "winsor_lower_percentile": 0.01,
            "winsor_upper_percentile": 0.99,
            "sector_minimum_count": 8,
        }

    def test_uses_sector_scope_at_eight_observations_and_universe_below_it(self):
        snapshots = [
            {"ticker": f"T{index}", "sector": "Technology", "forward_pe": 10 + index}
            for index in range(8)
        ] + [
            {"ticker": f"H{index}", "sector": "Healthcare", "forward_pe": 30 + index}
            for index in range(7)
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config)
        _, technology = normalizer.score("forward_pe", 14, "Technology")
        _, healthcare = normalizer.score("forward_pe", 33, "Healthcare")
        self.assertEqual(technology["normalization_scope"], "sector")
        self.assertEqual(healthcare["normalization_scope"], "universe")

    def test_lower_is_better_direction_is_flipped(self):
        snapshots = [
            {"ticker": str(index), "sector": "Technology", "forward_pe": value}
            for index, value in enumerate(range(10, 20))
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config)
        cheap, _ = normalizer.score("forward_pe", 11, "Technology")
        expensive, _ = normalizer.score("forward_pe", 18, "Technology")
        self.assertGreater(cheap, expensive)

    def test_range_metrics_rank_distance_from_ideal(self):
        snapshots = [
            {"ticker": str(index), "sector": "Industrials", "asset_growth": value}
            for index, value in enumerate((-0.4, -0.2, -0.1, 0.0, 0.04, 0.08, 0.2, 0.4))
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config)
        ideal, _ = normalizer.score("asset_growth", 0.04, "Industrials")
        extreme, _ = normalizer.score("asset_growth", 0.4, "Industrials")
        self.assertGreater(ideal, extreme)

    def test_nonpositive_valuation_is_not_applicable(self):
        snapshots = [
            {"ticker": str(index), "sector": "Technology", "forward_pe": value}
            for index, value in enumerate((-12, 10, 12, 14, 16, 18, 20, 22, 24))
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config)
        score, detail = normalizer.score("forward_pe", -12, "Technology")
        distribution = normalizer.published_distributions()["metrics"]["forward_pe"]
        self.assertIsNone(score)
        self.assertEqual(detail["status"], "not_applicable_nonpositive")
        self.assertNotIn(-12, distribution["universe_values"])

    def test_winsorized_distribution_is_published_exactly(self):
        snapshots = [
            {"ticker": str(index), "sector": "Technology", "return_on_equity": value}
            for index, value in enumerate((0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 20.0))
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config)
        published = normalizer.published_distributions()
        values = published["metrics"]["return_on_equity"]["universe_values"]
        self.assertEqual(len(values), len(snapshots))
        self.assertLess(values[-1], 20.0)

    def test_sector_percentile_ranks_identify_low_short_interest(self):
        snapshots = [
            {"ticker": f"T{index}", "sector": "Technology", "short_percent_of_float": value}
            for index, value in enumerate((0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08))
        ]
        ranks = scorer.sector_percentile_ranks(snapshots, "short_percent_of_float", 8)
        self.assertEqual(ranks["T0"]["percentile"], 0.0)
        self.assertEqual(ranks["T0"]["normalization_scope"], "sector")

    def test_valuation_metric_publishes_own_history_percentile_without_blending_it(self):
        history = {
            "ABC": {
                "forward_pe": [
                    {"observed_at": f"2025-{month:02d}-01", "value": value}
                    for month, value in enumerate(range(10, 22), start=1)
                ]
            }
        }
        snapshots = [
            {"ticker": f"T{index}", "sector": "Technology", "forward_pe": 10 + index}
            for index in range(12)
        ]
        normalizer = scorer.CrossSectionalNormalizer(snapshots, self.config, history)
        score, detail = normalizer.score("forward_pe", 15, "Technology", "ABC")
        score_without_history, _ = scorer.CrossSectionalNormalizer(
            snapshots, self.config
        ).score("forward_pe", 15, "Technology", "ABC")
        self.assertEqual(score, score_without_history)
        self.assertEqual(detail["own_history_status"], "scored")
        self.assertIsNotNone(detail["own_history_percentile"])


if __name__ == "__main__":
    unittest.main()


class RegistryDrivenApplicabilityTests(unittest.TestCase):
    """The live scorer and the v2 layer read one applicability authority.

    Previously scorer.py decided suppression from a hardcoded financial-sector tuple while
    pipeline/config/applicability_matrix.json governed only the shadow path, so the correct
    insurer rules existed and controlled nothing a user saw. See
    research/audit/CURRENT_MODEL_AUDIT.md section 5.
    """

    def insurer(self, **updates):
        base = {"is_etf": False, "sector": "Financial Services",
                "industry": "Insurance - Property & Casualty",
                "price_to_book": 2.18, "price_to_tangible_book": 2.48, "forward_pe": 11.76,
                "peg": 0.34, "debt_to_equity": 0.23, "return_on_equity": 0.22,
                "profit_margin": 0.11, "days_sales_outstanding_trend": -0.03,
                "revenue_growth": 0.05, "interest_coverage": 12.0}
        base.update(updates)
        return base

    def test_an_insurer_scores_price_to_book_and_financial_leverage(self):
        """The two canonical insurer inputs were forced to null for every financial."""
        _, parts = scorer.valuation_score(self.insurer())
        self.assertEqual(parts["applicability_profile"], "property_casualty_insurer")
        self.assertIsNotNone(parts["price_to_book"])
        self.assertIsNotNone(parts["debt_to_equity"])

    def test_an_insurer_does_not_score_receivable_days_or_peg(self):
        """THG published days_sales_outstanding 215.2 with its trend scored 80/100, and PEG
        carried 31% of an insurer's effective valuation weight while the registry declared
        PEG not comparable for insurers."""
        _, parts = scorer.valuation_score(self.insurer())
        self.assertIsNone(parts["days_sales_outstanding_trend"])
        self.assertIsNone(parts["peg"])
        for metric in ("ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "sales_multiple",
                       "gross_profits_to_assets", "inventory_days_trend", "current_ratio"):
            self.assertIn(metric, parts["suppressed_metrics"])

    def test_an_insurer_without_price_to_book_publishes_no_valuation_score(self):
        """125 of 125 financial rows published a Value score with price-to-book nulled."""
        _, parts = scorer.valuation_score(self.insurer(price_to_book=None))
        self.assertIsNone(parts["categories"]["valuation"])
        self.assertEqual(parts["categories_withheld"]["valuation"], ["price_to_book"])

    def test_an_insurer_without_financial_leverage_publishes_no_health_score(self):
        _, parts = scorer.valuation_score(self.insurer(debt_to_equity=None))
        self.assertIsNone(parts["categories"]["financial_health"])
        self.assertEqual(parts["categories_withheld"]["financial_health"], ["debt_to_equity"])

    def test_suppressed_metrics_leave_the_coverage_denominator_but_missing_ones_do_not(self):
        suppressed = scorer.valuation_score(self.insurer())[1]
        missing = scorer.valuation_score(self.insurer(return_on_equity=None,
                                                      profit_margin=None))[1]
        self.assertGreater(suppressed["coverage"], missing["coverage"])

    def test_a_semiconductor_is_not_penalised_for_outsourced_fabrication(self):
        """Cirrus Logic's 0.28x capex/depreciation scored 25/100 as "starving the business"."""
        fabless = {"is_etf": False, "sector": "Technology", "industry": "Semiconductors",
                   "capex_to_depreciation": 0.28, "forward_pe": 14.0, "price_to_book": 2.9,
                   "return_on_equity": 0.21}
        _, parts = scorer.valuation_score(fabless)
        self.assertEqual(parts["applicability_profile"], "semiconductor")
        self.assertIsNone(parts["capex_to_depreciation"])
        self.assertIn("capex_to_depreciation", parts["suppressed_metrics"])

    def test_a_producers_commodity_driven_margin_trend_is_not_scored_as_quality(self):
        """NEM's 17% trailing margin expansion and 128.2% incremental margin are the gold
        price, not structural improvement."""
        miner = {"is_etf": False, "sector": "Basic Materials", "industry": "Gold",
                 "operating_margin_trend": 0.17, "fcf_growth_3y": 0.9,
                 "gross_profits_to_assets": 0.2, "forward_pe": 10.7, "price_to_book": 3.4,
                 "return_on_equity": 0.26}
        _, parts = scorer.valuation_score(miner)
        self.assertEqual(parts["applicability_profile"], "commodity_producer")
        for metric in ("operating_margin_trend", "fcf_growth_3y", "gross_profits_to_assets"):
            self.assertIsNone(parts[metric])
            self.assertIn(metric, parts["suppressed_metrics"])


class CategoryCoverageTests(unittest.TestCase):
    """A category score alone cannot say how much of its evidence base it came from;
    category_coverage publishes the answered share and counts alongside it."""

    def test_full_coverage_reports_every_applicable_metric_used(self):
        _, detail = scorer.valuation_score(STRONG_TECH)
        for category, entry in detail["category_coverage"].items():
            self.assertEqual(entry["metrics_used"], entry["metrics_applicable"], category)
            self.assertEqual(entry["answered_weight_share"], 1.0, category)

    def test_missing_metric_lowers_only_its_own_categorys_share(self):
        snap = {**STRONG_TECH, "ev_to_ebitda": None}
        _, detail = scorer.valuation_score(snap)
        full = scorer.valuation_score(STRONG_TECH)[1]["category_coverage"]
        thinner = detail["category_coverage"]
        self.assertLess(thinner["valuation"]["answered_weight_share"],
                        full["valuation"]["answered_weight_share"])
        self.assertEqual(thinner["valuation"]["metrics_used"],
                         full["valuation"]["metrics_used"] - 1)
        self.assertEqual(thinner["profitability"], full["profitability"])

    def test_suppressed_metrics_leave_the_denominator(self):
        # A suppressed metric is not missing evidence: it must not depress the answered share.
        insurer = {**STRONG_TECH, "sector": "Financial Services",
                   "industry": "Insurance - Property & Casualty"}
        _, detail = scorer.valuation_score(insurer)
        for category, entry in detail["category_coverage"].items():
            self.assertLessEqual(entry["metrics_applicable"],
                                 len(scorer.SETTINGS["fundamentals"]["metric_weights"][category]))
