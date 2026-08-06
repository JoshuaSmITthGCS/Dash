import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from costs import (cost_scenarios, estimate_cost_bps, liquidity_tier,
                   max_trade_for_adv_participation)


class LiquidityTierTests(unittest.TestCase):
    def test_matches_the_existing_scoring_modifier_thresholds(self):
        # settings.json modifiers.liquidity: illiquid < $5M, thin < $25M, else liquid.
        self.assertEqual(liquidity_tier(1_000_000), "illiquid")
        self.assertEqual(liquidity_tier(10_000_000), "thin")
        self.assertEqual(liquidity_tier(50_000_000), "liquid")

    def test_missing_volume_is_none_not_a_guess(self):
        self.assertIsNone(liquidity_tier(None))

    def test_custom_thresholds_are_honored(self):
        self.assertEqual(
            liquidity_tier(6_000_000, thin_threshold=25_000_000, illiquid_threshold=5_000_000),
            "thin",
        )


class EstimateCostBpsTests(unittest.TestCase):
    def test_stress_scenario_costs_more_than_base_costs_more_than_optimistic(self):
        kwargs = dict(median_dollar_volume_60d=10_000_000, annualized_volatility=0.3,
                     trade_dollar_value=100_000)
        optimistic = estimate_cost_bps(**kwargs, scenario="optimistic")
        base = estimate_cost_bps(**kwargs, scenario="base")
        stress = estimate_cost_bps(**kwargs, scenario="stress")

        self.assertLess(optimistic["total_bps"], base["total_bps"])
        self.assertLess(base["total_bps"], stress["total_bps"])

    def test_illiquid_names_cost_more_than_liquid_names(self):
        illiquid = estimate_cost_bps(median_dollar_volume_60d=1_000_000)
        liquid = estimate_cost_bps(median_dollar_volume_60d=100_000_000)

        self.assertGreater(illiquid["total_bps"], liquid["total_bps"])

    def test_no_trade_size_or_volatility_means_zero_impact_not_a_fabricated_number(self):
        result = estimate_cost_bps(median_dollar_volume_60d=10_000_000)

        self.assertEqual(result["impact_bps"], 0.0)
        self.assertIsNone(result["participation_rate"])

    def test_every_result_discloses_the_spread_is_a_proxy_not_measured(self):
        result = estimate_cost_bps(median_dollar_volume_60d=10_000_000)

        self.assertEqual(result["spread_source"], "liquidity_tiered_proxy_not_measured")

    def test_unsupported_scenario_raises_rather_than_silently_falling_back(self):
        with self.assertRaises(ValueError):
            estimate_cost_bps(median_dollar_volume_60d=10_000_000, scenario="fantasy")

    def test_larger_participation_costs_more(self):
        small_trade = estimate_cost_bps(
            median_dollar_volume_60d=10_000_000, annualized_volatility=0.3, trade_dollar_value=10_000,
        )
        large_trade = estimate_cost_bps(
            median_dollar_volume_60d=10_000_000, annualized_volatility=0.3, trade_dollar_value=500_000,
        )
        self.assertGreater(large_trade["impact_bps"], small_trade["impact_bps"])


class CostScenariosTests(unittest.TestCase):
    def test_returns_all_three_scenarios(self):
        result = cost_scenarios(median_dollar_volume_60d=10_000_000, annualized_volatility=0.3,
                                trade_dollar_value=50_000)

        self.assertEqual(set(result), {"optimistic", "base", "stress"})


class MaxTradeForAdvParticipationTests(unittest.TestCase):
    def test_defaults_to_the_research_contract_two_percent_cap(self):
        self.assertEqual(max_trade_for_adv_participation(10_000_000), 200_000.0)

    def test_missing_volume_is_none(self):
        self.assertIsNone(max_trade_for_adv_participation(None))


if __name__ == "__main__":
    unittest.main()
