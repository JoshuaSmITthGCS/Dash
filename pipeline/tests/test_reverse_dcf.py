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


if __name__ == "__main__":
    unittest.main()
