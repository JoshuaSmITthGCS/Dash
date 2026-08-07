import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cost_sensitivity as cs


class DragArithmeticTests(unittest.TestCase):
    def test_annual_drag_reproduces_the_identity_the_backtest_charges(self):
        """backtest_monthly.py charges value * turnover * bps / 10000 per rebalance."""
        self.assertAlmostEqual(cs.annual_drag_bps(0.649, 10.0), 0.649 * 10.0 * 12)

    def test_drag_is_linear_in_both_turnover_and_rate(self):
        self.assertAlmostEqual(cs.annual_drag_bps(0.5, 20.0), cs.annual_drag_bps(1.0, 10.0))
        self.assertAlmostEqual(cs.annual_drag_bps(0.65, 20.0),
                               2 * cs.annual_drag_bps(0.65, 10.0))

    def test_zero_turnover_costs_nothing(self):
        self.assertEqual(cs.annual_drag_bps(0.0, 25.0), 0.0)


class TierRateTests(unittest.TestCase):
    def test_rates_widen_as_liquidity_thins_within_every_scenario(self):
        for scenario, tiers in cs.tier_rates().items():
            with self.subTest(scenario=scenario):
                self.assertLess(tiers["liquid"], tiers["thin"])
                self.assertLess(tiers["thin"], tiers["illiquid"])

    def test_stress_prices_above_base_which_prices_above_optimistic(self):
        rates = cs.tier_rates()
        for tier in ("liquid", "thin", "illiquid"):
            with self.subTest(tier=tier):
                self.assertLess(rates["optimistic"][tier], rates["base"][tier])
                self.assertLess(rates["base"][tier], rates["stress"][tier])


class ThresholdTests(unittest.TestCase):
    BACKTEST = {
        "generated_at": "2026-08-03T00:00:00Z",
        "portfolio": {
            "rebalances": [{"turnover": 0.649, "cost": 649.0, "portfolio_value": 100_000.0}] * 12,
            "history": [{"date": "2024-01-31", "value": 100_000.0},
                        {"date": "2024-02-29", "value": 101_000.0},
                        {"date": "2024-03-28", "value": 102_000.0}],
        },
    }

    def test_breakeven_rate_is_where_extra_drag_reaches_the_threshold(self):
        report = cs.build_report(self.BACKTEST)
        check = report["threshold_check"]
        extra = cs.annual_drag_bps(0.649, check["breakeven_one_way_bps"]) - \
            cs.annual_drag_bps(0.649, cs.PUBLISHED_RATE_BPS)
        self.assertAlmostEqual(extra, cs.THRESHOLD_BPS_OF_ANNUAL_RETURN, delta=1.0)

    def test_verdict_reports_the_floor_does_not_cross_at_this_turnover(self):
        """The honest answer: spread+fees alone stays under 200bps at 64.9% turnover."""
        check = cs.build_report(self.BACKTEST)["threshold_check"]
        self.assertEqual(check["verdict"], "not_crossed_by_the_spread_and_fee_floor")
        self.assertLess(check["worst_modelled_additional_drag_bps"],
                        cs.THRESHOLD_BPS_OF_ANNUAL_RETURN)

    def test_much_higher_turnover_does_cross_the_threshold(self):
        """The verdict tracks turnover, not a hardcoded conclusion.

        At 150% monthly turnover the breakeven rate falls to ~21bps, below the model's
        25bps stress/illiquid worst case, so the same cost model now crosses.
        """
        heavy = {**self.BACKTEST, "portfolio": {
            **self.BACKTEST["portfolio"],
            "rebalances": [{"turnover": 1.5, "cost": 1500.0, "portfolio_value": 100_000.0}] * 12,
        }}
        self.assertEqual(cs.build_report(heavy)["threshold_check"]["verdict"], "crossed")

    def test_gross_return_is_net_plus_the_published_drag(self):
        published = cs.build_report(self.BACKTEST)["published_assumption"]
        self.assertAlmostEqual(
            published["implied_gross_annualized_return"],
            published["net_annualized_return"] + published["annual_drag_bps"] / 10_000,
            places=5)

    def test_every_scenario_net_return_is_below_the_implied_gross(self):
        report = cs.build_report(self.BACKTEST)
        gross = report["published_assumption"]["implied_gross_annualized_return"]
        for tiers in report["scenarios"].values():
            for block in tiers.values():
                self.assertLess(block["net_annualized_return"], gross)

    def test_the_rates_are_declared_a_floor_and_the_gap_is_declared_blocked(self):
        report = cs.build_report(self.BACKTEST)
        self.assertIn("lower bound", report["rates_are_a_floor"])
        self.assertEqual(report["unresolved"]["status"], "blocked_network_policy")
        self.assertTrue(report["unresolved"]["reproduction"])


class CommittedBacktestTests(unittest.TestCase):
    def test_committed_backtest_turnover_is_the_documented_figure(self):
        if not os.path.exists(cs.BACKTEST_PATH):
            self.skipTest("backtest artifact not present in this checkout")
        turnover = cs.build_report()["realized_turnover"]
        self.assertAlmostEqual(turnover["mean_monthly"], 0.649, places=2)
        self.assertEqual(turnover["rebalances"], 60)


if __name__ == "__main__":
    unittest.main()
