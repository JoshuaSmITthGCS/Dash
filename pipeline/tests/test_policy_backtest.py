import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from policy_backtest import POLICIES, compare_policies


class PolicyBacktestTests(unittest.TestCase):
    def test_compares_all_policies_with_same_entry_snapshots(self):
        dates = [date(2026, 1, 1) + timedelta(weeks=index) for index in range(4)]
        prices = [100, 95, 79, 82]
        rankings = [[{
            "ticker": "AAA", "price": price,
            "technical_detail": {"annualized_volatility": 20},
            "recommendation": {"agreement_count": 0},
            "recommendation_v2": {"company": {"action": {"label": "hold_existing_position"}, "deterioration_groups": []}},
        }] for price in prices]
        result = compare_policies(rankings, dates, top_n=1, initial_capital=10000)
        self.assertEqual(set(result["policies"]), set(POLICIES))
        self.assertGreater(result["policies"]["fixed_20_stop"]["metrics"]["exit_count"], 0)
        self.assertEqual(result["policies"]["no_stops"]["metrics"]["exit_count"], 0)
        self.assertIn("maximum_drawdown", result["policies"]["combined_policy"]["metrics"])


if __name__ == "__main__":
    unittest.main()
