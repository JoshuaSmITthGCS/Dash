import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import run_backtest_suite as suite


class DefaultCandidatesTests(unittest.TestCase):
    def test_reads_the_explicit_weight_map_not_a_guessed_attribute_name(self):
        # Regression: an earlier draft guessed the attribute name from the strategy id
        # (f"{strategy_id.upper()}_WEIGHTS") -- for "reweighted_composite_a" that guesses
        # "REWEIGHTED_COMPOSITE_A_WEIGHTS", which does not exist (the real constant is
        # shadow_portfolios.REWEIGHTED_A_WEIGHTS), so the guess silently returned nothing.
        candidates = suite.default_candidates()
        names = [name for name, _ in candidates]
        self.assertIn("reweighted_composite_a", names)
        weights = dict(candidates)["reweighted_composite_a"]
        self.assertGreater(sum(weights.values()), 0)

    def test_a_candidate_not_currently_registered_is_excluded(self):
        import shadow_portfolios
        with patch.object(shadow_portfolios, "RESEARCH_CANDIDATE_WEIGHTS",
                          {**shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS,
                           "not_registered": {"valuation": 1.0}}):
            names = [name for name, _ in suite.default_candidates()]
        self.assertNotIn("not_registered", names)


if __name__ == "__main__":
    unittest.main()
