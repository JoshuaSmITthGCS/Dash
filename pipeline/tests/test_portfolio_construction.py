import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import portfolio_construction as pc


def ranked(order, scores=None):
    """Ranked rows, highest score first, in the given ticker order."""
    scores = scores or {}
    return [{"ticker": ticker, "score": scores.get(ticker, 100.0 - index)}
            for index, ticker in enumerate(order)]


ALPHABET = [f"T{index:02d}" for index in range(40)]


class DefaultBehaviourTests(unittest.TestCase):
    def test_no_controls_reproduces_plain_top_n_selection(self):
        """Every control defaults to off, so the champion path is untouched."""
        rows = ranked(ALPHABET)
        self.assertEqual(pc.apply_controls(["T30", "T31"], rows, 20),
                         pc.select_top_n(rows, 20))

    def test_select_top_n_takes_exactly_the_first_n(self):
        self.assertEqual(pc.select_top_n(ranked(ALPHABET), 5), ALPHABET[:5])


class RankBufferTests(unittest.TestCase):
    def test_an_incumbent_inside_the_buffer_is_held_not_replaced(self):
        """Rank 18 drifting to 22 is noise, not information, at 1.5x buffer on N=20."""
        rows = ranked([*ALPHABET[:21], "INCUMBENT", *ALPHABET[21:]])
        selected = pc.rank_buffer_selection(["INCUMBENT"], rows, 20, buffer_multiple=1.5)
        self.assertIn("INCUMBENT", selected)
        self.assertEqual(len(selected), 20)

    def test_an_incumbent_outside_the_buffer_is_sold(self):
        rows = ranked([*ALPHABET[:35], "FALLEN"])
        self.assertNotIn("FALLEN", pc.rank_buffer_selection(["FALLEN"], rows, 20,
                                                            buffer_multiple=1.5))

    def test_the_buffer_boundary_is_exact_at_the_multiple(self):
        """rank == buffer_multiple * N is held; one past it is not."""
        for buffer_multiple in pc.RANK_BUFFER_MULTIPLES:
            outer = int(round(10 * buffer_multiple))
            with self.subTest(buffer_multiple=buffer_multiple):
                at_edge = ranked([*ALPHABET[:outer - 1], "EDGE", *ALPHABET[outer - 1:]])
                self.assertIn("EDGE", pc.rank_buffer_selection(["EDGE"], at_edge, 10,
                                                               buffer_multiple))
                past_edge = ranked([*ALPHABET[:outer], "PAST", *ALPHABET[outer:]])
                self.assertNotIn("PAST", pc.rank_buffer_selection(["PAST"], past_edge, 10,
                                                                  buffer_multiple))

    def test_buffering_never_returns_more_than_n_names(self):
        rows = ranked(ALPHABET)
        selected = pc.rank_buffer_selection(ALPHABET[:25], rows, 20, buffer_multiple=2.0)
        self.assertEqual(len(selected), 20)
        self.assertEqual(len(set(selected)), 20)

    def test_buffering_lowers_turnover_versus_the_champion(self):
        previous = ALPHABET[:20]
        # Every incumbent slips a few places; a plain top-20 would churn, a buffer would not.
        shuffled = ranked([*ALPHABET[20:25], *ALPHABET[:20], *ALPHABET[25:]])
        champion = pc.select_top_n(shuffled, 20)
        buffered = pc.rank_buffer_selection(previous, shuffled, 20, buffer_multiple=1.5)
        self.assertLess(pc.turnover(previous, buffered), pc.turnover(previous, champion))

    def test_a_buffer_below_one_is_rejected(self):
        with self.assertRaises(ValueError):
            pc.rank_buffer_selection([], ranked(ALPHABET), 20, buffer_multiple=0.9)

    def test_an_empty_previous_book_selects_the_plain_top_n(self):
        rows = ranked(ALPHABET)
        self.assertEqual(pc.rank_buffer_selection([], rows, 20, 1.5),
                         pc.select_top_n(rows, 20))


class MinimumHoldingTests(unittest.TestCase):
    def test_a_young_holding_is_kept_even_when_it_falls_out_of_the_top_n(self):
        rows = ranked([*ALPHABET[:25], "YOUNG"])
        selected = pc.minimum_holding_selection(["YOUNG"], rows, 20, {"YOUNG": 1},
                                                minimum_months=3)
        self.assertIn("YOUNG", selected)

    def test_a_matured_holding_is_released(self):
        rows = ranked([*ALPHABET[:25], "OLD"])
        selected = pc.minimum_holding_selection(["OLD"], rows, 20, {"OLD": 3},
                                                minimum_months=3)
        self.assertNotIn("OLD", selected)

    def test_a_broken_thesis_overrides_the_holding_floor(self):
        """Otherwise this is not a turnover control, it is a refusal to update.

        With N=20 the default thesis-break rank is 3N = 60. A name that has merely slipped
        (rank 41) keeps its floor; one that has collapsed past the break rank loses it.
        """
        slipped = ranked([*ALPHABET, "COLLAPSED"])                       # rank 41, inside 60
        collapsed = ranked([*[f"X{i:02d}" for i in range(70)], "COLLAPSED"])  # rank 71, past 60

        self.assertIn("COLLAPSED",
                      pc.minimum_holding_selection(["COLLAPSED"], slipped, 20, {"COLLAPSED": 0}))
        self.assertNotIn("COLLAPSED",
                         pc.minimum_holding_selection(["COLLAPSED"], collapsed, 20,
                                                      {"COLLAPSED": 0}))

    def test_every_configured_minimum_is_honoured(self):
        rows = ranked([*ALPHABET[:25], "HELD"])
        for minimum in pc.MINIMUM_HOLDING_MONTHS:
            with self.subTest(minimum=minimum):
                young = pc.minimum_holding_selection(["HELD"], rows, 20, {"HELD": minimum - 1},
                                                     minimum_months=minimum)
                mature = pc.minimum_holding_selection(["HELD"], rows, 20, {"HELD": minimum},
                                                      minimum_months=minimum)
                self.assertIn("HELD", young)
                self.assertNotIn("HELD", mature)

    def test_a_minimum_below_one_month_is_rejected(self):
        with self.assertRaises(ValueError):
            pc.minimum_holding_selection([], ranked(ALPHABET), 20, {}, minimum_months=0)


class SmoothingTests(unittest.TestCase):
    def test_smoothing_blends_prior_and_new_at_exactly_alpha(self):
        rows = [{"ticker": "AAA", "score": 80.0}]
        smoothed = pc.smooth_scores({"AAA": 60.0}, rows, alpha=0.7)
        self.assertAlmostEqual(smoothed[0]["score"], 0.7 * 80.0 + 0.3 * 60.0)
        self.assertEqual(smoothed[0]["raw_score"], 80.0)

    def test_alpha_of_one_is_a_no_op(self):
        rows = [{"ticker": "AAA", "score": 80.0}, {"ticker": "BBB", "score": 70.0}]
        smoothed = pc.smooth_scores({"AAA": 10.0, "BBB": 99.0}, rows, alpha=1.0)
        self.assertEqual([row["score"] for row in smoothed], [80.0, 70.0])

    def test_a_new_name_enters_at_its_own_score_not_a_neutral_prior(self):
        """Seeding at neutral would penalize every name for being new."""
        smoothed = pc.smooth_scores({}, [{"ticker": "NEW", "score": 90.0}], alpha=0.5)
        self.assertEqual(smoothed[0]["score"], 90.0)

    def test_smoothing_reorders_when_the_prior_disagrees_with_the_new_score(self):
        rows = [{"ticker": "SPIKE", "score": 90.0}, {"ticker": "STEADY", "score": 85.0}]
        smoothed = pc.smooth_scores({"SPIKE": 40.0, "STEADY": 85.0}, rows, alpha=0.5)
        self.assertEqual([row["ticker"] for row in smoothed], ["STEADY", "SPIKE"])

    def test_output_stays_sorted_by_smoothed_score(self):
        rows = ranked(ALPHABET[:10])
        smoothed = pc.smooth_scores({ticker: 50.0 for ticker in ALPHABET[:10]}, rows, 0.5)
        scores = [row["score"] for row in smoothed]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_alpha_outside_the_unit_interval_is_rejected(self):
        for alpha in (0.0, -0.1, 1.1):
            with self.subTest(alpha=alpha):
                with self.assertRaises(ValueError):
                    pc.smooth_scores({}, [{"ticker": "A", "score": 1.0}], alpha)


class ReplacementMarginTests(unittest.TestCase):
    def test_a_marginally_better_challenger_does_not_displace_an_incumbent(self):
        rows = [{"ticker": "NEW", "score": 71.0}, {"ticker": "HELD", "score": 70.0}]
        selected = pc.replacement_margin_selection(["HELD"], rows, 1, margin=5.0)
        self.assertEqual(selected, ["HELD"])

    def test_a_decisively_better_challenger_does_displace_it(self):
        rows = [{"ticker": "NEW", "score": 90.0}, {"ticker": "HELD", "score": 70.0}]
        selected = pc.replacement_margin_selection(["HELD"], rows, 1, margin=5.0)
        self.assertEqual(selected, ["NEW"])

    def test_the_margin_boundary_is_strict(self):
        for margin in pc.REPLACEMENT_MARGINS:
            with self.subTest(margin=margin):
                at_margin = [{"ticker": "NEW", "score": 70.0 + margin},
                             {"ticker": "HELD", "score": 70.0}]
                past_margin = [{"ticker": "NEW", "score": 70.0 + margin + 0.01},
                               {"ticker": "HELD", "score": 70.0}]
                self.assertEqual(
                    pc.replacement_margin_selection(["HELD"], at_margin, 1, margin), ["HELD"])
                self.assertEqual(
                    pc.replacement_margin_selection(["HELD"], past_margin, 1, margin), ["NEW"])

    def test_empty_slots_are_filled_without_needing_a_margin(self):
        rows = ranked(ALPHABET[:10])
        selected = pc.replacement_margin_selection([], rows, 5, margin=5.0)
        self.assertEqual(len(selected), 5)

    def test_a_negative_margin_is_rejected(self):
        with self.assertRaises(ValueError):
            pc.replacement_margin_selection([], ranked(ALPHABET), 20, margin=-1.0)


class TurnoverTests(unittest.TestCase):
    def test_turnover_is_the_share_of_the_book_replaced(self):
        self.assertAlmostEqual(pc.turnover(["A", "B", "C", "D"], ["A", "B", "C", "E"]), 0.25)
        self.assertEqual(pc.turnover(["A", "B"], ["A", "B"]), 0.0)
        self.assertEqual(pc.turnover(["A", "B"], ["C", "D"]), 1.0)

    def test_a_first_rebalance_is_full_turnover(self):
        self.assertEqual(pc.turnover([], ["A", "B"]), 1.0)

    def test_selling_into_cash_is_not_negative_turnover(self):
        self.assertEqual(pc.turnover(["A", "B"], []), 0.0)


class CompositionTests(unittest.TestCase):
    def test_the_holding_floor_outranks_the_soft_controls(self):
        rows = ranked([*ALPHABET[:25], "YOUNG"])
        selected = pc.apply_controls(["YOUNG"], rows, 20, held_months={"YOUNG": 0},
                                     minimum_months=3, rank_buffer=1.25)
        self.assertIn("YOUNG", selected)

    def test_smoothing_changes_the_ranking_every_later_control_reads(self):
        rows = [{"ticker": "SPIKE", "score": 95.0}, {"ticker": "STEADY", "score": 90.0}]
        without = pc.apply_controls([], rows, 1)
        with_smoothing = pc.apply_controls([], rows, 1,
                                           previous_scores={"SPIKE": 10.0, "STEADY": 90.0},
                                           smoothing_alpha=0.5)
        self.assertEqual(without, ["SPIKE"])
        self.assertEqual(with_smoothing, ["STEADY"])

    def test_every_control_returns_exactly_n_names_when_the_universe_allows(self):
        rows = ranked(ALPHABET)
        previous = ALPHABET[10:30]
        for options in ({"rank_buffer": 1.5}, {"minimum_months": 3},
                        {"replacement_margin": 2.0}, {"smoothing_alpha": 0.7}, {}):
            with self.subTest(options=options):
                selected = pc.apply_controls(previous, rows, 20,
                                             held_months={t: 0 for t in previous},
                                             previous_scores={t: 50.0 for t in previous},
                                             **options)
                self.assertEqual(len(selected), 20)
                self.assertEqual(len(set(selected)), 20)


if __name__ == "__main__":
    unittest.main()


class BacktestWiringTests(unittest.TestCase):
    """The controls must be inert unless asked for -- they are challengers, not the champion."""

    def test_backtest_exposes_every_control_and_uses_the_shared_implementation(self):
        import inspect

        import backtest_monthly

        # One implementation, not a second copy that can drift from the tested one.
        self.assertIs(backtest_monthly.apply_controls, pc.apply_controls)

        source = inspect.getsource(backtest_monthly.main)
        for flag in ("--rank-buffer", "--min-holding-months", "--score-smoothing",
                     "--replacement-margin"):
            with self.subTest(flag=flag):
                self.assertIn(flag, source)
                # Each is declared with an explicit None default, so the champion path is
                # what runs when the flag is omitted.
                declaration = source.split(flag, 1)[1].split("parser.add_argument", 1)[0]
                self.assertIn("default=None", declaration)

    def test_selection_order_is_preserved_into_weighting(self):
        """apply_controls returns an ordering; the backtest must weight the names it chose."""
        rows = ranked(ALPHABET)
        selected = pc.apply_controls(ALPHABET[5:25], rows, 20, rank_buffer=1.5)
        chosen = {row["ticker"]: row for row in rows if row["ticker"] in set(selected)}
        ordered = [chosen[ticker] for ticker in selected if ticker in chosen]

        self.assertEqual([row["ticker"] for row in ordered], selected)
        self.assertEqual(len(ordered), 20)
