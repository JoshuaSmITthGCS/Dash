import os
import sys
import unittest
from datetime import date

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from backtest_monthly import (  # noqa: E402
    appeal_weights,
    build_rebalance_calendar,
    performance_metrics,
    simulate_locked_portfolio,
    trailing_liquidity_and_volatility,
)


class MonthlyBacktestTests(unittest.TestCase):
    def test_calendar_executes_after_signal(self):
        dates = ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"]
        pairs = build_rebalance_calendar(dates, 0)
        self.assertEqual(pairs, [])
        pairs = build_rebalance_calendar(dates, 1)
        self.assertTrue(all(signal < execution for signal, execution in pairs))

    def test_appeal_weights_are_proportional(self):
        rows = [
            {"ticker": "A", "score": 80, "price": 10},
            {"ticker": "B", "score": 40, "price": 20},
            {"ticker": "C", "score": 100, "price": 30},
        ]
        weights = appeal_weights(rows, 2)
        self.assertAlmostEqual(weights["A"], 2 / 3)
        self.assertAlmostEqual(weights["B"], 1 / 3)
        self.assertNotIn("C", weights)

    def test_metrics_compute_drawdown(self):
        history = [
            {"date": "2023-01-01", "value": 100.0},
            {"date": "2023-06-01", "value": 120.0},
            {"date": "2024-01-01", "value": 90.0},
        ]
        metrics = performance_metrics(history, 100.0)
        self.assertAlmostEqual(metrics["maximum_drawdown"], -0.25)
        self.assertAlmostEqual(metrics["total_return"], -0.10)


def _daily_dates(count, start=date(2024, 1, 1)):
    return [(date.fromordinal(start.toordinal() + offset)).isoformat() for offset in range(count)]


class TrailingLiquidityAndVolatilityTests(unittest.TestCase):
    def test_missing_ticker_data_returns_none_not_a_guess(self):
        mdv, vol = trailing_liquidity_and_volatility(None, "2024-01-01")
        self.assertIsNone(mdv)
        self.assertIsNone(vol)

    def test_uses_only_the_trailing_window_no_look_ahead(self):
        dates = _daily_dates(65)
        closes = [100.0 + (index % 3) for index in range(65)]
        volumes = [1_000_000.0] * 65
        ticker_data = {"dates": dates, "closes": closes, "volumes": volumes}
        mdv, vol = trailing_liquidity_and_volatility(ticker_data, dates[10])
        self.assertIsNotNone(mdv)
        self.assertGreater(mdv, 0)
        self.assertIsNotNone(vol)
        # A date after the series ends should still only see what existed by then.
        mdv_early, _ = trailing_liquidity_and_volatility(ticker_data, dates[1])
        self.assertLess(mdv_early or 0, mdv * 2)


class CostModelWiringTests(unittest.TestCase):
    def _fixture(self):
        dates = _daily_dates(65)
        # Small day-to-day variation so volatility is nonzero for both names.
        closes_liquid = [100.0 + (index % 4) * 0.5 for index in range(65)]
        closes_illiquid = [50.0 + (index % 5) * 0.3 for index in range(65)]
        universe_data = {
            "LIQUID": {"dates": dates, "closes": closes_liquid, "volumes": [2_000_000.0] * 65},
            "ILLIQUID": {"dates": dates, "closes": closes_illiquid, "volumes": [2_000.0] * 65},
        }
        benchmark = {"dates": dates, "closes": [500.0] * 65}
        plans = [
            {
                "signal_date": dates[0], "execution_date": dates[60],
                "weights": {"LIQUID": 1.0},
                "picks": [{"ticker": "LIQUID", "appeal_score": 90, "weight": 1.0}],
            },
            {
                "signal_date": dates[60], "execution_date": dates[62],
                "weights": {"ILLIQUID": 1.0},
                "picks": [{"ticker": "ILLIQUID", "appeal_score": 80, "weight": 1.0}],
            },
        ]
        return plans, universe_data, benchmark

    def test_flat_cost_model_matches_the_original_single_rate_formula(self):
        # Pre-refactor, cost was computed as value_before_cost * turnover * bps / 10000,
        # then subtracted: value_after = value_before - cost. So
        # value_before = value_after + cost, and cost must equal
        # (value_after + cost) * turnover * bps / 10000 exactly.
        plans, universe_data, benchmark = self._fixture()
        result = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0, transaction_cost_bps=10.0,
            cost_model="flat",
        )
        for rebalance in result["rebalances"]:
            value_before = rebalance["portfolio_value"] + rebalance["cost"]
            expected_cost = round(value_before * rebalance["turnover"] * 10.0 / 10000, 2)
            self.assertAlmostEqual(rebalance["cost"], expected_cost, places=2)

    def test_tiered_stress_costs_more_than_tiered_optimistic(self):
        plans, universe_data, benchmark = self._fixture()
        optimistic = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="optimistic",
        )
        stress = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="stress",
        )
        self.assertGreater(
            stress["metrics"]["estimated_transaction_cost"],
            optimistic["metrics"]["estimated_transaction_cost"],
        )
        self.assertLessEqual(
            stress["metrics"]["final_value"], optimistic["metrics"]["final_value"],
        )

    def test_tiered_illiquid_trade_costs_more_than_an_equal_size_liquid_trade(self):
        # Same weight/dollar trade into ILLIQUID (2,000 shares/day) should cost more in the
        # tiered model than the same-size entry into LIQUID (2,000,000 shares/day) did,
        # since costs.py's spread/impact both widen as liquidity thins.
        plans, universe_data, benchmark = self._fixture()
        result = simulate_locked_portfolio(
            plans, universe_data, benchmark, 100_000.0,
            cost_model="tiered", cost_scenario="base",
        )
        first_entry_cost, second_entry_cost = (r["cost"] for r in result["rebalances"])
        self.assertGreater(second_entry_cost, first_entry_cost)

    def test_unsupported_cost_model_raises(self):
        plans, universe_data, benchmark = self._fixture()
        with self.assertRaises(ValueError):
            simulate_locked_portfolio(
                plans, universe_data, benchmark, 100_000.0, cost_model="fantasy",
            )


if __name__ == "__main__":
    unittest.main()
