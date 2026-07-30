import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import scorer


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
        score, parts = scorer.valuation_score({
            "is_etf": False, "sector": "Technology", "peg": 0.9, "forward_pe": 24,
            "price_to_sales": 4, "price_to_book": 2.5, "price_to_tangible_book": 2.8,
            "ev_to_ebitda": 9, "ev_to_fcf": 17, "return_on_equity": 0.22,
            "return_on_invested_capital": 0.24, "cash_conversion": 1.1,
            "free_cash_flow_yield": 0.08, "profit_margin": 0.20,
            "debt_to_equity": 0.4, "current_ratio": 2.1, "interest_coverage": 20,
            "net_debt_to_ebitda": 0.2, "altman_z": 5.5,
            "revenue_growth": 0.20, "earnings_growth": 0.20, "fcf_growth_3y": 0.18,
            "operating_margin_trend": 0.03, "net_buyback_yield": 0.04,
            "stock_comp_to_revenue": 0.008, "capex_to_depreciation": 1.2,
            "accruals_ratio": -0.05, "piotroski_f": 8.5,
            "days_sales_outstanding_trend": -0.06, "inventory_days_trend": -0.06,
        })
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


if __name__ == "__main__":
    unittest.main()
