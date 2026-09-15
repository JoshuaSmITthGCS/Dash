import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fast_growth_rank import rank_breakout_in_progress, rank_emerging_growth, trailing_week_return


def breakout_row(ticker, **overrides):
    row = {
        "ticker": ticker, "is_etf": False, "price": 100.0,
        "technical_detail": {"return_5d": 4.0, "return_20d": 6.0, "volume_ratio_60d": 1.5},
    }
    row.update(overrides)
    return row


def emerging_row(ticker, **overrides):
    row = {
        "ticker": ticker, "is_etf": False, "price": 100.0,
        "technical_detail": {"return_5d": 1.0, "relative_strength_20d": 3.0},
        "fundamental_detail": {"revenue_growth": 0.15, "operating_margin_trend": 0.02},
    }
    row.update(overrides)
    return row


class BreakoutInProgressTests(unittest.TestCase):
    def test_qualifies_a_name_up_and_accelerating(self):
        ranked = rank_breakout_in_progress([breakout_row("UP")])
        self.assertEqual([row["ticker"] for row in ranked], ["UP"])

    def test_excludes_a_week_return_at_or_below_the_two_percent_floor(self):
        ranked = rank_breakout_in_progress([breakout_row("FLAT", technical_detail={"return_5d": 2.0, "return_20d": 6.0})])
        self.assertEqual(ranked, [])

    def test_excludes_a_negative_month_return(self):
        ranked = rank_breakout_in_progress([breakout_row("DOWN", technical_detail={"return_5d": 4.0, "return_20d": -1.0})])
        self.assertEqual(ranked, [])

    def test_excludes_a_decelerating_move(self):
        # Nearly all the month's return already happened outside this week: the pace before
        # this week was faster than this week's own pace, so acceleration is negative.
        ranked = rank_breakout_in_progress(
            [breakout_row("DECEL", technical_detail={"return_5d": 3.0, "return_20d": 20.0})])
        self.assertEqual(ranked, [])

    def test_excludes_an_etf(self):
        ranked = rank_breakout_in_progress([breakout_row("FUND", is_etf=True)])
        self.assertEqual(ranked, [])

    def test_missing_volume_ratio_defaults_to_neutral_rather_than_excluding(self):
        row = breakout_row("NOVOL", technical_detail={"return_5d": 4.0, "return_20d": 6.0, "volume_ratio_60d": None})
        ranked = rank_breakout_in_progress([row])
        self.assertEqual(len(ranked), 1)

    def test_ranks_a_bigger_burst_and_acceleration_higher(self):
        big = breakout_row("BIG", technical_detail={"return_5d": 10.0, "return_20d": 12.0, "volume_ratio_60d": 3.0})
        small = breakout_row("SMALL", technical_detail={"return_5d": 3.0, "return_20d": 5.0, "volume_ratio_60d": 1.1})
        ranked = rank_breakout_in_progress([small, big])
        self.assertEqual([row["ticker"] for row in ranked], ["BIG", "SMALL"])

    def test_falls_back_to_trailing_week_return_from_price_history(self):
        row = breakout_row("NOFEED", technical_detail={"return_5d": None, "return_20d": 6.0, "volume_ratio_60d": 1.0},
                           history={"closes": [90.0, 100.0]})
        self.assertEqual(trailing_week_return(row), (100.0 / 90.0 - 1) * 100)
        ranked = rank_breakout_in_progress([row])
        self.assertEqual(len(ranked), 1)

    def test_respects_the_limit(self):
        rows = [breakout_row(f"T{i}", technical_detail={"return_5d": 4.0 + i, "return_20d": 6.0, "volume_ratio_60d": 1.0})
                for i in range(15)]
        ranked = rank_breakout_in_progress(rows, limit=10)
        self.assertEqual(len(ranked), 10)

    def test_published_screen_block_carries_the_inputs_and_score(self):
        ranked = rank_breakout_in_progress([breakout_row("UP")])
        screen = ranked[0]["screen"]
        self.assertEqual(screen["weekReturn"], 4.0)
        self.assertEqual(screen["monthReturn"], 6.0)
        self.assertIn("rankScore", screen)


class EmergingGrowthTests(unittest.TestCase):
    def test_qualifies_a_name_with_real_growth_and_early_strength(self):
        ranked = rank_emerging_growth([emerging_row("EARLY")])
        self.assertEqual([row["ticker"] for row in ranked], ["EARLY"])
        self.assertEqual(ranked[0]["research_status"], "prospective_unvalidated")

    def test_excludes_anything_the_breakout_screen_would_already_catch(self):
        row = emerging_row("BROKE", technical_detail={"return_5d": 8.0, "relative_strength_20d": 6.0})
        self.assertEqual(rank_emerging_growth([row]), [])

    def test_excludes_names_without_meaningful_revenue_growth(self):
        no_growth = emerging_row("FLAT", fundamental_detail={"revenue_growth": 0.01})
        negative = emerging_row("SHRINK", fundamental_detail={"revenue_growth": -0.05})
        self.assertEqual(rank_emerging_growth([no_growth, negative]), [])

    def test_excludes_names_without_positive_early_relative_strength(self):
        row = emerging_row("WEAK", technical_detail={"return_5d": 1.0, "relative_strength_20d": -2.0})
        self.assertEqual(rank_emerging_growth([row]), [])

    def test_excludes_an_etf(self):
        self.assertEqual(rank_emerging_growth([emerging_row("FUND", is_etf=True)]), [])

    def test_does_not_require_estimate_revision_data_to_qualify(self):
        ranked = rank_emerging_growth([emerging_row("NOREV")])
        self.assertEqual(len(ranked), 1)
        self.assertIsNone(ranked[0]["screen"]["revisionBreadth"])

    def test_missing_margin_trend_defaults_to_neutral_not_a_disqualification(self):
        row = emerging_row("NOMARGIN", fundamental_detail={"revenue_growth": 0.15, "operating_margin_trend": None})
        self.assertEqual(len(rank_emerging_growth([row])), 1)

    def test_ranks_stronger_growth_and_strength_higher(self):
        strong = emerging_row("STRONG", fundamental_detail={"revenue_growth": 0.30, "operating_margin_trend": 0.05},
                              technical_detail={"return_5d": 1.0, "relative_strength_20d": 8.0})
        mild = emerging_row("MILD", fundamental_detail={"revenue_growth": 0.08, "operating_margin_trend": 0.0},
                            technical_detail={"return_5d": 1.0, "relative_strength_20d": 1.0})
        ranked = rank_emerging_growth([mild, strong])
        self.assertEqual([row["ticker"] for row in ranked], ["STRONG", "MILD"])

    def test_respects_the_limit(self):
        rows = [emerging_row(f"T{i}", fundamental_detail={"revenue_growth": 0.10 + i / 100,
                                                          "operating_margin_trend": 0.0})
                for i in range(15)]
        ranked = rank_emerging_growth(rows, limit=10)
        self.assertEqual(len(ranked), 10)


if __name__ == "__main__":
    unittest.main()
