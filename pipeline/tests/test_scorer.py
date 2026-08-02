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

    def test_bank_leverage_is_displayed_but_not_scored_with_industrial_cutoffs(self):
        _, parts = scorer.valuation_score({"is_etf": False, "sector": "Financial Services",
                                           "price_to_book": 1.2, "debt_to_equity": 2.5,
                                           "current_ratio": 0.6})
        self.assertIsNone(parts["debt_to_equity"])
        self.assertIsNone(parts["current_ratio"])

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


if __name__ == "__main__":
    unittest.main()
