import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rank_emerging_growth import emerging_growth_score, volatility_contracting


def emerging_row(ticker, **overrides):
    row = {
        "ticker": ticker,
        "is_etf": False,
        "technical_detail": {"return_5d": 1, "relative_strength_20d": 3},
        "fundamental_detail": {"revenue_growth": 0.15, "operating_margin_trend": 0.02},
    }
    row.update(overrides)
    return row


class EmergingGrowthGateTests(unittest.TestCase):
    def test_qualifies_a_name_with_real_growth_and_early_strength(self):
        result = emerging_growth_score(emerging_row("EARLY"))
        self.assertIsNotNone(result)

    def test_excludes_anything_the_breakout_screen_would_already_catch(self):
        already_broken = emerging_row(
            "BROKE", technical_detail={"return_5d": 8, "relative_strength_20d": 6},
        )
        self.assertIsNone(emerging_growth_score(already_broken))

    def test_excludes_names_without_a_real_meaningful_revenue_growth_rate(self):
        no_growth = emerging_row("FLAT", fundamental_detail={"revenue_growth": 0.01})
        negative_growth = emerging_row("SHRINK", fundamental_detail={"revenue_growth": -0.05})
        self.assertIsNone(emerging_growth_score(no_growth))
        self.assertIsNone(emerging_growth_score(negative_growth))

    def test_excludes_names_without_positive_early_relative_strength(self):
        weak = emerging_row("WEAK", technical_detail={"return_5d": 1, "relative_strength_20d": -2})
        self.assertIsNone(emerging_growth_score(weak))

    def test_excludes_an_etf_that_would_otherwise_clear_every_gate(self):
        etf = emerging_row("FUND_LIKE", is_etf=True)
        self.assertIsNone(emerging_growth_score(etf))

    def test_does_not_require_estimate_revision_data_to_qualify(self):
        result = emerging_growth_score(emerging_row("NOREV"))
        self.assertIsNotNone(result)
        _, detail = result
        self.assertIsNone(detail["revision_breadth"])

    def test_ranks_stronger_growth_and_strength_higher(self):
        stronger = emerging_row(
            "STRONG",
            fundamental_detail={"revenue_growth": 0.30, "operating_margin_trend": 0.05},
            technical_detail={"return_5d": 1, "relative_strength_20d": 8},
        )
        milder = emerging_row(
            "MILD",
            fundamental_detail={"revenue_growth": 0.08, "operating_margin_trend": 0.0},
            technical_detail={"return_5d": 1, "relative_strength_20d": 1},
        )
        strong_score, _ = emerging_growth_score(stronger)
        mild_score, _ = emerging_growth_score(milder)
        self.assertGreater(strong_score, mild_score)

    def test_missing_margin_trend_defaults_to_a_neutral_fifty_not_a_disqualification(self):
        row = emerging_row("NOMARGIN", fundamental_detail={"revenue_growth": 0.15, "operating_margin_trend": None})
        result = emerging_growth_score(row)
        self.assertIsNotNone(result)


class VolatilityContractingTests(unittest.TestCase):
    def test_none_without_enough_price_history(self):
        self.assertIsNone(volatility_contracting([100.0] * 30))
        self.assertIsNone(volatility_contracting(None))

    def test_true_when_recent_volatility_is_meaningfully_lower(self):
        # 60+1 daily closes: choppy for the first 50 sessions, dead flat for the last 11.
        import random
        random_gen = random.Random(7)
        choppy = [100.0]
        for _ in range(49):
            choppy.append(choppy[-1] * (1 + random_gen.uniform(-0.05, 0.05)))
        flat = [choppy[-1] * (1 + 0.0005 * index) for index in range(1, 12)]
        closes = choppy + flat
        self.assertTrue(volatility_contracting(closes))

    def test_false_when_recent_volatility_is_not_contracting(self):
        import random
        random_gen = random.Random(3)
        flat = [100.0 * (1 + 0.0005 * index) for index in range(50)]
        choppy = [flat[-1]]
        for _ in range(11):
            choppy.append(choppy[-1] * (1 + random_gen.uniform(-0.08, 0.08)))
        closes = flat + choppy
        self.assertFalse(volatility_contracting(closes))


if __name__ == "__main__":
    unittest.main()
