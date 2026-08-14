import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cost_sensitivity import build_report, reprice_rebalance


def _backtest(rebalances, estimated_transaction_cost=0.0, final_value=100000.0, cagr=0.0):
    return {
        "portfolio": {
            "rebalances": rebalances,
            "metrics": {"estimated_transaction_cost": estimated_transaction_cost,
                       "final_value": final_value, "cagr": cagr},
        },
    }


class RepriceRebalanceTests(unittest.TestCase):
    def test_zero_turnover_costs_nothing_at_any_rate(self):
        cost, turnover = reprice_rebalance({"turnover": 0.0, "cost": 0.0}, bps=25.0)
        self.assertEqual(cost, 0.0)

    def test_reprices_a_known_flat_10bps_trade_at_a_different_rate(self):
        # value_before = 100 / (1.0 * 10/10000) = 100,000. At 25bps: 100000*1.0*25/10000=250.
        cost, turnover = reprice_rebalance({"turnover": 1.0, "cost": 100.0}, bps=25.0)
        self.assertAlmostEqual(cost, 250.0, places=2)

    def test_reproduces_the_realized_cost_at_the_realized_rate(self):
        cost, _ = reprice_rebalance({"turnover": 0.852004, "cost": 89.67}, bps=10.0)
        self.assertAlmostEqual(cost, 89.67, places=2)


class BuildReportTests(unittest.TestCase):
    def test_gross_scenario_is_always_zero_cost(self):
        backtest = _backtest([{"signal_date": "2026-01", "turnover": 1.0, "cost": 100.0}],
                             estimated_transaction_cost=100.0)
        report = build_report(backtest)
        self.assertEqual(report["scenarios"]["gross"]["total_cost"], 0.0)

    def test_stress_costs_more_than_optimistic(self):
        backtest = _backtest([{"signal_date": "2026-01", "turnover": 1.0, "cost": 100.0}],
                             estimated_transaction_cost=100.0)
        report = build_report(backtest)
        self.assertGreater(report["scenarios"]["stress"]["cost_bps"],
                           report["scenarios"]["optimistic"]["cost_bps"])
        self.assertGreater(report["scenarios"]["stress"]["total_cost"],
                           report["scenarios"]["optimistic"]["total_cost"])

    def test_turnover_summary_reflects_the_committed_rebalance_log(self):
        backtest = _backtest([
            {"signal_date": "2026-01", "turnover": 1.0, "cost": 100.0},
            {"signal_date": "2026-02", "turnover": 0.5, "cost": 50.0},
        ], estimated_transaction_cost=150.0)
        report = build_report(backtest)
        self.assertEqual(report["turnover"]["rebalances"], 2)
        self.assertAlmostEqual(report["turnover"]["mean_turnover"], 0.75, places=4)

    def test_per_name_liquidity_legs_are_unmeasured_never_fabricated(self):
        report = build_report(_backtest([]))
        blocked = report["per_name_liquidity_legs"]
        self.assertEqual(blocked["status"], "not_measured_inputs_available")
        self.assertIn("adv_participation_pct", blocked["measures"])

    def test_never_presents_gross_as_net(self):
        report = build_report(_backtest([]))
        self.assertTrue(report["never_present_gross_as_net"])
        self.assertIn("gross", report["scenarios"])
        self.assertIn("realized_flat_10bps", report)

    def test_loads_and_reports_against_the_real_committed_backtest(self):
        # No mocking - this is the actual verification command from the brief.
        report = build_report()
        self.assertEqual(report["turnover"]["rebalances"], 60)
        self.assertGreater(report["scenarios"]["base"]["total_cost"], 0)


if __name__ == "__main__":
    unittest.main()
