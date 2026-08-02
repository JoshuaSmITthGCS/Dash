import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import fundamentals_extended as fx


def statement(**rows):
    """Build a statement series; every value list runs newest period first."""
    return {"periods": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"], "rows": dict(rows)}


INCOME = statement(**{
    "Total Revenue": [1000.0, 900.0, 820.0, 750.0],
    "Cost Of Revenue": [400.0, 380.0, 360.0, 340.0],
    "Gross Profit": [600.0, 520.0, 460.0, 410.0],
    "Operating Income": [250.0, 200.0, 170.0, 150.0],
    "EBIT": [250.0, 200.0, 170.0, 150.0],
    "EBITDA": [320.0, 265.0, 230.0, 205.0],
    "Net Income": [180.0, 140.0, 120.0, 100.0],
    "Pretax Income": [230.0, 180.0, 155.0, 130.0],
    "Tax Provision": [50.0, 40.0, 35.0, 30.0],
    "Interest Expense": [20.0, 22.0, 24.0, 25.0],
})

BALANCE = statement(**{
    "Total Assets": [2000.0, 1800.0, 1700.0, 1600.0],
    "Total Liabilities Net Minority Interest": [900.0, 880.0, 900.0, 920.0],
    "Current Assets": [700.0, 600.0, 560.0, 520.0],
    "Current Liabilities": [350.0, 340.0, 330.0, 320.0],
    "Total Debt": [500.0, 520.0, 560.0, 600.0],
    "Long Term Debt": [400.0, 430.0, 470.0, 510.0],
    "Cash And Cash Equivalents": [300.0, 250.0, 220.0, 200.0],
    "Stockholders Equity": [1100.0, 920.0, 800.0, 680.0],
    "Retained Earnings": [700.0, 560.0, 450.0, 360.0],
    "Working Capital": [350.0, 260.0, 230.0, 200.0],
    "Goodwill": [200.0, 200.0, 200.0, 200.0],
    "Other Intangible Assets": [100.0, 110.0, 120.0, 130.0],
    "Accounts Receivable": [150.0, 140.0, 130.0, 120.0],
    "Inventory": [80.0, 78.0, 76.0, 74.0],
    "Ordinary Shares Number": [95.0, 100.0, 102.0, 104.0],
})

CASHFLOW = statement(**{
    "Operating Cash Flow": [260.0, 210.0, 185.0, 160.0],
    "Free Cash Flow": [200.0, 160.0, 140.0, 120.0],
    "Capital Expenditure": [-60.0, -50.0, -45.0, -40.0],
    "Depreciation And Amortization": [55.0, 50.0, 48.0, 45.0],
    "Stock Based Compensation": [30.0, 28.0, 25.0, 22.0],
    "Repurchase Of Capital Stock": [-90.0, -60.0, -40.0, -20.0],
})


class LineLookupTests(unittest.TestCase):
    def test_aliases_and_case_insensitive_fallback(self):
        self.assertEqual(fx.at(fx.line(INCOME, "revenue")), 1000.0)
        self.assertEqual(fx.at(fx.line(INCOME, "operating_income"), 1), 200.0)
        odd = {"periods": ["2025"], "rows": {"total revenue": [42.0]}}
        self.assertEqual(fx.at(fx.line(odd, "revenue")), 42.0)

    def test_missing_concepts_return_empty_not_zero(self):
        self.assertEqual(fx.line(INCOME, "not_a_concept"), [])
        self.assertIsNone(fx.at(fx.line(INCOME, "not_a_concept")))


class ProfitabilityTests(unittest.TestCase):
    def test_roic_uses_nopat_over_invested_capital(self):
        # tax rate 50/230 = 21.7%; NOPAT = 250 * 0.783 = 195.7
        # invested capital averages (500+1100-300)=1300 and (520+920-250)=1190 -> 1245
        self.assertAlmostEqual(fx.derive_roic(INCOME, BALANCE), 0.1572, places=3)

    def test_roic_is_immune_to_the_leverage_that_flatters_roe(self):
        levered = dict(BALANCE)
        levered["rows"] = {**BALANCE["rows"], "Stockholders Equity": [300.0, 250.0, 200.0, 150.0],
                           "Total Debt": [1300.0, 1190.0, 1160.0, 1130.0]}
        # Equity shrank and debt grew by the same amount: ROE would soar, ROIC should barely move.
        self.assertAlmostEqual(fx.derive_roic(INCOME, levered), fx.derive_roic(INCOME, BALANCE), places=1)

    def test_cash_conversion_and_fcf_growth(self):
        self.assertAlmostEqual(fx.derive_cash_conversion(INCOME, CASHFLOW), 200 / 180, places=3)
        self.assertAlmostEqual(fx.derive_fcf_growth(CASHFLOW), (200 / 120) ** (1 / 3) - 1, places=4)

    def test_cash_conversion_undefined_when_earnings_are_negative(self):
        loss = {"periods": ["2025"], "rows": {"Net Income": [-50.0]}}
        self.assertIsNone(fx.derive_cash_conversion(loss, CASHFLOW))

    def test_margin_level_trend_and_incremental_margin(self):
        margins = fx.derive_margins(INCOME)
        self.assertAlmostEqual(margins["operating_margin"], 0.25, places=4)
        self.assertAlmostEqual(margins["operating_margin_trend"], 0.25 - 200 / 900, places=4)
        # $100 of new revenue carried $50 of new operating profit.
        self.assertAlmostEqual(margins["incremental_margin"], 0.5, places=4)


class HealthTests(unittest.TestCase):
    def test_interest_coverage(self):
        self.assertAlmostEqual(fx.derive_interest_coverage(INCOME), 12.5, places=2)

    def test_debt_free_company_reads_as_fully_covered(self):
        no_debt = {"periods": ["2025"], "rows": {"EBIT": [100.0], "Interest Expense": [0.0]}}
        self.assertEqual(fx.derive_interest_coverage(no_debt), 99.0)

    def test_net_debt_to_ebitda_can_go_negative_for_net_cash(self):
        cash_rich = dict(BALANCE)
        cash_rich["rows"] = {**BALANCE["rows"], "Cash And Cash Equivalents": [900.0, 800.0, 700.0, 600.0]}
        self.assertLess(fx.derive_net_debt_to_ebitda(INCOME, cash_rich), 0)

    def test_altman_z_is_skipped_for_banks(self):
        self.assertIsNotNone(fx.derive_altman_z(INCOME, BALANCE, 4000, "Technology")[0])
        self.assertEqual(fx.derive_altman_z(INCOME, BALANCE, 4000, "Financial Services"),
                         (None, None))

    def test_altman_variant_follows_the_sector(self):
        # The original 1968 model was fitted on manufacturers; applying it to an asset-light
        # company reports a misleadingly low score, so non-manufacturers get Altman's own
        # Z'' revision instead. The variant travels with the number.
        _, industrial = fx.derive_altman_z(INCOME, BALANCE, 4000, "Industrials")
        _, software = fx.derive_altman_z(INCOME, BALANCE, 4000, "Technology")
        self.assertEqual(industrial, "z")
        self.assertEqual(software, "z_double_prime")
        self.assertIsNone(fx.altman_variant_for("Financial Services"))

    def test_z_double_prime_drops_the_asset_turnover_term(self):
        # Same balance sheet, two models: the scores must differ, because Z'' removes the
        # revenue/assets term that penalizes asset-light filers and reweights the rest.
        manufacturing, _ = fx.derive_altman_z(INCOME, BALANCE, 4000, "Industrials")
        non_manufacturing, _ = fx.derive_altman_z(INCOME, BALANCE, 4000, "Technology")
        self.assertNotAlmostEqual(manufacturing, non_manufacturing, places=2)

    def test_gross_profits_to_assets_uses_average_assets(self):
        value = fx.derive_gross_profits_to_assets(INCOME, BALANCE)
        gross = fx.at(fx.line(INCOME, "gross_profit"))
        assets = fx.average(fx.at(fx.line(BALANCE, "total_assets")),
                            fx.at(fx.line(BALANCE, "total_assets"), 1))
        self.assertAlmostEqual(value, gross / assets, places=4)

    def test_gross_profits_falls_back_to_revenue_minus_cost(self):
        without_gross = {"periods": ["2025"], "rows": {"Total Revenue": [1000.0],
                                                       "Cost Of Revenue": [400.0]}}
        balance = {"periods": ["2025"], "rows": {"Total Assets": [2000.0]}}
        self.assertAlmostEqual(fx.derive_gross_profits_to_assets(without_gross, balance), 0.3)

    def test_asset_growth_is_year_over_year(self):
        balance = {"periods": ["2025", "2024"], "rows": {"Total Assets": [1200.0, 1000.0]}}
        self.assertAlmostEqual(fx.derive_asset_growth(balance), 0.2)
        self.assertIsNone(fx.derive_asset_growth({"periods": ["2025"], "rows": {"Total Assets": [1200.0]}}))

    def test_earnings_surprise_weights_recent_quarters_heaviest(self):
        recent_beat = fx.derive_earnings_surprise([
            {"date": "2026-06-30", "surprise_pct": 10.0},
            {"date": "2026-03-31", "surprise_pct": -2.0},
        ])
        recent_miss = fx.derive_earnings_surprise([
            {"date": "2026-06-30", "surprise_pct": -2.0},
            {"date": "2026-03-31", "surprise_pct": 10.0},
        ])
        self.assertGreater(recent_beat, recent_miss)

    def test_earnings_surprise_is_none_without_reported_quarters(self):
        self.assertIsNone(fx.derive_earnings_surprise([]))
        self.assertIsNone(fx.derive_earnings_surprise([{"date": "2026-06-30", "surprise_pct": None}]))

    def test_piotroski_rewards_improving_fundamentals(self):
        score, tests = fx.derive_piotroski(INCOME, BALANCE, CASHFLOW)
        self.assertGreaterEqual(score, 8)
        self.assertTrue(tests["cash_exceeds_income"])
        self.assertTrue(tests["no_dilution"])

    def test_piotroski_needs_enough_answerable_tests(self):
        thin = {"periods": ["2025"], "rows": {"Net Income": [10.0]}}
        score, _ = fx.derive_piotroski(thin, thin, thin)
        self.assertIsNone(score)


class AccountingQualityTests(unittest.TestCase):
    def test_accruals_ratio_is_negative_when_cash_leads_earnings(self):
        ratio = fx.derive_accruals_ratio(INCOME, BALANCE, CASHFLOW)
        self.assertLess(ratio, 0)  # 180 net income against 260 of operating cash

    def test_accruals_ratio_flags_earnings_running_ahead_of_cash(self):
        aggressive = {"periods": ["2025", "2024"], "rows": {"Operating Cash Flow": [40.0, 30.0]}}
        ratio = fx.derive_accruals_ratio(INCOME, BALANCE, aggressive)
        self.assertGreater(ratio, 0.05)

    def test_receivable_and_inventory_days_track_their_own_trend(self):
        trends = fx.derive_working_capital_trends(INCOME, BALANCE)
        self.assertAlmostEqual(trends["days_sales_outstanding"], 150 / 1000 * 365, places=1)
        # Receivables grew slower than revenue, so days outstanding fell.
        self.assertLess(trends["days_sales_outstanding_trend"], 0)
        self.assertIsNotNone(trends["inventory_days_trend"])


class CapitalAllocationTests(unittest.TestCase):
    def test_buybacks_show_up_as_a_positive_net_yield(self):
        allocation = fx.derive_capital_allocation(INCOME, BALANCE, CASHFLOW, market_cap=4000)
        self.assertAlmostEqual(allocation["share_count_change"], -0.05, places=4)
        self.assertAlmostEqual(allocation["net_buyback_yield"], 0.05, places=4)

    def test_dilution_shows_up_as_a_negative_net_yield(self):
        diluting = dict(BALANCE)
        diluting["rows"] = {**BALANCE["rows"], "Ordinary Shares Number": [110.0, 100.0, 95.0, 90.0]}
        allocation = fx.derive_capital_allocation(INCOME, diluting, CASHFLOW, market_cap=4000)
        self.assertAlmostEqual(allocation["net_buyback_yield"], -0.10, places=4)

    def test_stock_comp_and_reinvestment_intensity(self):
        allocation = fx.derive_capital_allocation(INCOME, BALANCE, CASHFLOW, market_cap=4000)
        self.assertAlmostEqual(allocation["stock_comp_to_revenue"], 0.03, places=4)
        self.assertAlmostEqual(allocation["capex_to_depreciation"], 60 / 55, places=2)


class ValuationTests(unittest.TestCase):
    def test_enterprise_multiples_fall_back_to_the_balance_sheet(self):
        multiples = fx.derive_enterprise_multiples(INCOME, BALANCE, CASHFLOW, {}, market_cap=4000)
        self.assertEqual(multiples["enterprise_value"], 4000 + 500 - 300)
        self.assertAlmostEqual(multiples["ev_to_ebitda"], 4200 / 320, places=1)
        self.assertAlmostEqual(multiples["ev_to_fcf"], 4200 / 200, places=2)

    def test_tangible_book_strips_goodwill_and_intangibles(self):
        multiples = fx.derive_enterprise_multiples(INCOME, BALANCE, CASHFLOW, {}, market_cap=4000)
        self.assertAlmostEqual(multiples["price_to_tangible_book"], 4000 / (1100 - 200 - 100), places=2)

    def test_loss_making_ebitda_leaves_the_multiple_undefined(self):
        loss = {"periods": ["2025"], "rows": {"EBITDA": [-50.0]}}
        multiples = fx.derive_enterprise_multiples(loss, BALANCE, CASHFLOW, {}, market_cap=4000)
        self.assertIsNone(multiples["ev_to_ebitda"])


class MarketStructureTests(unittest.TestCase):
    def test_short_liquidity_and_52_week_context(self):
        info = {"shortPercentOfFloat": 0.18, "shortRatio": 7.5, "heldPercentInstitutions": 0.71,
                "beta": 1.4, "averageVolume": 2_000_000, "fiftyTwoWeekHigh": 200,
                "fiftyTwoWeekLow": 100, "targetMeanPrice": 180, "numberOfAnalystOpinions": 22,
                "recommendationMean": 1.9}
        structure = fx.derive_market_structure(info, price=150)
        self.assertEqual(structure["average_dollar_volume"], 300_000_000)
        self.assertAlmostEqual(structure["pct_from_52w_high"], -25.0, places=1)
        self.assertAlmostEqual(structure["pct_above_52w_low"], 50.0, places=1)
        self.assertEqual(structure["analyst_consensus_target"], 180)
        self.assertAlmostEqual(structure["analyst_target_upside"], 20.0, places=1)

    def test_missing_quote_fields_stay_missing(self):
        structure = fx.derive_market_structure({}, price=None)
        self.assertIsNone(structure["beta"])
        self.assertIsNone(structure["average_dollar_volume"])


class AssemblyTests(unittest.TestCase):
    def test_derive_extended_reports_its_own_coverage(self):
        metrics = fx.derive_extended(
            annual={"income": INCOME, "balance": BALANCE, "cashflow": CASHFLOW},
            info={"beta": 1.1}, market_cap=4000, price=40, sector="Technology")
        self.assertGreater(metrics["extended_coverage"], 0.9)
        self.assertIsNotNone(metrics["return_on_invested_capital"])
        self.assertIsNotNone(metrics["piotroski_f"])
        self.assertIsNotNone(metrics["ev_to_ebitda"])

    def test_empty_statements_produce_no_metrics_rather_than_zeros(self):
        empty = {"periods": [], "rows": {}}
        metrics = fx.derive_extended(annual={"income": empty, "balance": empty, "cashflow": empty},
                                     info={}, market_cap=None, price=None)
        self.assertEqual(metrics["extended_coverage"], 0.0)
        self.assertIsNone(metrics["return_on_invested_capital"])
        self.assertIsNone(metrics["accruals_ratio"])


if __name__ == "__main__":
    unittest.main()
