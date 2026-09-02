import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import reverse_dcf as rd

ASSUMPTIONS = {
    "risk_free_rate": 0.04,
    "equity_risk_premium": 0.045,
    "default_cost_of_debt": 0.055,
    "implausible_growth_ceiling": 0.15,
}


class CostOfEquityTests(unittest.TestCase):
    def test_capm_with_a_declared_beta(self):
        self.assertAlmostEqual(rd.estimate_cost_of_equity(1.2, 0.04, 0.045), 0.04 + 1.2 * 0.045, places=6)

    def test_missing_beta_falls_back_to_market_average(self):
        self.assertAlmostEqual(rd.estimate_cost_of_equity(None, 0.04, 0.045), 0.04 + 0.045, places=6)

    def test_missing_macro_assumptions_return_none(self):
        self.assertIsNone(rd.estimate_cost_of_equity(1.0, None, 0.045))


class WaccTests(unittest.TestCase):
    def test_blends_equity_and_after_tax_debt_by_market_value_weight(self):
        # equity 4000, debt 1000: weights 0.8/0.2
        wacc = rd.estimate_wacc(market_cap=4000, total_debt=1000, cost_of_equity=0.10,
                                cost_of_debt=0.05, tax_rate=0.21)
        expected = 0.8 * 0.10 + 0.2 * (0.05 * 0.79)
        self.assertAlmostEqual(wacc, expected, places=6)

    def test_debt_free_company_is_pure_cost_of_equity(self):
        self.assertAlmostEqual(rd.estimate_wacc(market_cap=4000, total_debt=0, cost_of_equity=0.09,
                                                cost_of_debt=0.05, tax_rate=0.21), 0.09, places=6)

    def test_nonpositive_market_cap_is_undefined(self):
        self.assertIsNone(rd.estimate_wacc(market_cap=0, total_debt=100, cost_of_equity=0.09,
                                           cost_of_debt=0.05, tax_rate=0.21))


class MarketImpliedGrowthTests(unittest.TestCase):
    def test_solves_the_perpetuity_for_growth(self):
        # g = (EV*WACC - FCF) / (EV + FCF) with EV=4200, FCF=200, WACC=0.09.
        growth = rd.market_implied_growth(enterprise_value=4200, free_cash_flow=200, wacc=0.09)
        self.assertAlmostEqual(growth, (4200 * 0.09 - 200) / (4200 + 200), places=4)

    def test_a_richer_valuation_implies_higher_growth_at_equal_fcf_and_wacc(self):
        cheap = rd.market_implied_growth(enterprise_value=2000, free_cash_flow=200, wacc=0.09)
        rich = rd.market_implied_growth(enterprise_value=6000, free_cash_flow=200, wacc=0.09)
        self.assertLess(cheap, rich)

    def test_nonpositive_fcf_or_ev_is_undefined(self):
        self.assertIsNone(rd.market_implied_growth(enterprise_value=4200, free_cash_flow=-10, wacc=0.09))
        self.assertIsNone(rd.market_implied_growth(enterprise_value=-100, free_cash_flow=200, wacc=0.09))

    def test_growth_solve_stays_below_wacc_even_at_extreme_inputs(self):
        # Algebraically g < WACC whenever EV and FCF are both positive (see the function's
        # docstring) -- a tiny FCF against a huge EV pushes g toward WACC but never past it.
        # The published figure is rounded to 4 decimals, so at a sufficiently extreme ratio
        # that rounding can land exactly on WACC; it must never round past it.
        growth = rd.market_implied_growth(enterprise_value=1_000_000, free_cash_flow=1, wacc=0.09)
        self.assertLessEqual(growth, 0.09)


class DeriveMarketImpliedGrowthTests(unittest.TestCase):
    def test_end_to_end_reading_with_declared_assumptions(self):
        result = rd.derive_market_implied_growth(
            beta=1.1, market_cap=4000, total_debt=500, enterprise_value=4200,
            free_cash_flow=200, tax_rate=0.21, assumptions=ASSUMPTIONS)
        self.assertIsNotNone(result)
        self.assertIn("market_implied_growth", result)
        self.assertIn("wacc_assumed", result)
        self.assertFalse(result["exceeds_plausible_ceiling"])

    def test_flags_an_implausibly_high_implied_growth_rate(self):
        # High beta (0.04 + 3*0.045 = 17.5% cost of equity) and a tiny FCF against a huge EV
        # push the solved growth close to that WACC, comfortably past the 15% ceiling.
        result = rd.derive_market_implied_growth(
            beta=3.0, market_cap=1_000_000, total_debt=0, enterprise_value=1_000_000,
            free_cash_flow=1, tax_rate=0.21, assumptions=ASSUMPTIONS)
        self.assertIsNotNone(result)
        self.assertTrue(result["exceeds_plausible_ceiling"])

    def test_missing_free_cash_flow_returns_none_rather_than_a_guess(self):
        self.assertIsNone(rd.derive_market_implied_growth(
            beta=1.0, market_cap=4000, total_debt=500, enterprise_value=4200,
            free_cash_flow=None, tax_rate=0.21, assumptions=ASSUMPTIONS))


class DeriveValueCreationTests(unittest.TestCase):
    def test_roic_above_wacc_is_a_positive_spread(self):
        # beta 1.0 (fallback) -> cost of equity 0.04 + 0.045 = 0.085; debt-free -> wacc = 0.085.
        result = rd.derive_value_creation(
            roic=0.15, beta=None, market_cap=4000, total_debt=0, assumptions=ASSUMPTIONS)
        self.assertAlmostEqual(result["wacc_assumed"], 0.085, places=6)
        self.assertAlmostEqual(result["value_creation_spread"], 0.15 - 0.085, places=6)

    def test_roic_below_wacc_is_a_negative_spread(self):
        result = rd.derive_value_creation(
            roic=0.03, beta=1.5, market_cap=4000, total_debt=0, assumptions=ASSUMPTIONS)
        self.assertLess(result["value_creation_spread"], 0)

    def test_resolves_without_enterprise_value_or_free_cash_flow(self):
        # Unlike derive_market_implied_growth, the spread needs no EV/FCF -- it must still
        # resolve for a company with no free cash flow at all (e.g. a pre-profit grower).
        result = rd.derive_value_creation(
            roic=0.10, beta=1.2, market_cap=4000, total_debt=500, assumptions=ASSUMPTIONS)
        self.assertIsNotNone(result["wacc_assumed"])
        self.assertIsNotNone(result["value_creation_spread"])

    def test_missing_roic_still_reports_wacc(self):
        result = rd.derive_value_creation(
            roic=None, beta=1.0, market_cap=4000, total_debt=0, assumptions=ASSUMPTIONS)
        self.assertIsNotNone(result["wacc_assumed"])
        self.assertIsNone(result["value_creation_spread"])

    def test_nonpositive_market_cap_leaves_both_fields_none(self):
        result = rd.derive_value_creation(
            roic=0.15, beta=1.0, market_cap=0, total_debt=0, assumptions=ASSUMPTIONS)
        self.assertIsNone(result["wacc_assumed"])
        self.assertIsNone(result["value_creation_spread"])


class GrowthExpectationsGapTests(unittest.TestCase):
    def test_priced_in_growth_above_trailing_delivery_is_a_positive_gap(self):
        gap = rd.growth_expectations_gap(market_implied_growth=0.08, realized_growth=0.03)
        self.assertAlmostEqual(gap, 0.05, places=6)

    def test_priced_in_growth_below_trailing_delivery_is_a_negative_gap(self):
        gap = rd.growth_expectations_gap(market_implied_growth=0.02, realized_growth=0.06)
        self.assertAlmostEqual(gap, -0.04, places=6)

    def test_missing_either_side_is_undefined(self):
        self.assertIsNone(rd.growth_expectations_gap(market_implied_growth=None, realized_growth=0.03))
        self.assertIsNone(rd.growth_expectations_gap(market_implied_growth=0.03, realized_growth=None))


if __name__ == "__main__":
    unittest.main()
