import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from p0_q2_turnover_attribution import _fundamentals_reconstruction, _relative_change, attribute_transition


class RelativeChangeTests(unittest.TestCase):
    def test_small_change_is_below_threshold(self):
        self.assertLess(_relative_change(100.0, 100.5), 0.02)

    def test_large_change_is_above_threshold(self):
        self.assertGreater(_relative_change(100.0, 110.0), 0.02)

    def test_missing_values_return_none(self):
        self.assertIsNone(_relative_change(None, 5.0))
        self.assertIsNone(_relative_change(5.0, None))

    def test_zero_to_zero_is_none_not_undefined(self):
        self.assertIsNone(_relative_change(0.0, 0.0))


class FundamentalsReconstructionTests(unittest.TestCase):
    def test_weights_present_categories_only(self):
        row = {"category_scores": {"champion": {"valuation": 80.0, "profitability": 60.0}}}
        result = _fundamentals_reconstruction(row)
        # Weighted average restricted to the two present categories (0.28 and 0.26 of the
        # full category_weights), not diluted by the four missing ones.
        expected = (0.28 * 80.0 + 0.26 * 60.0) / (0.28 + 0.26)
        self.assertAlmostEqual(result, expected, places=6)

    def test_no_categories_returns_none(self):
        self.assertIsNone(_fundamentals_reconstruction({"category_scores": {"champion": {}}}))


def _row(ticker, champion_score, metric_scores, raw_inputs, modifier_total=0.0, categories=None):
    return {
        "ticker": ticker,
        "scores": {"champion": champion_score},
        "normalized_metric_scores": {"champion": metric_scores},
        "raw_metric_inputs": raw_inputs,
        "modifiers": {"champion": {"total": modifier_total}},
        "category_scores": {"champion": categories or {}},
    }


class AttributeTransitionTests(unittest.TestCase):
    def test_classifies_band_crossing_vs_genuine_change_by_raw_magnitude(self):
        previous = [_row("AAA", 50.0, {"forward_pe": 60.0}, {"forward_pe": 20.0}),
                   _row("BBB", 50.0, {"forward_pe": 60.0}, {"forward_pe": 20.0})]
        current = [
            # Raw barely moved (0.5%) but the banded score jumped a full band -- a crossing.
            _row("AAA", 55.0, {"forward_pe": 70.0}, {"forward_pe": 20.1}),
            # Raw moved substantially (25%) -- a genuine change.
            _row("BBB", 55.0, {"forward_pe": 70.0}, {"forward_pe": 25.0}),
        ]
        result = attribute_transition(previous, current)
        self.assertEqual(result["metric_level_events"]["band_crossing_unchanged_value"], 1)
        self.assertEqual(result["metric_level_events"]["genuine_input_change"], 1)

    def test_counts_availability_flicker_separately(self):
        previous = [_row("AAA", 50.0, {}, {})]
        current = [_row("AAA", 55.0, {"forward_pe": 70.0}, {"forward_pe": 20.0})]
        result = attribute_transition(previous, current)
        self.assertEqual(result["metric_level_events"]["availability_flicker"], 1)
        self.assertEqual(result["metric_level_events"]["genuine_input_change"], 0)

    def test_only_shared_tickers_are_compared(self):
        previous = [_row("AAA", 50.0, {}, {}), _row("ONLY_PREVIOUS", 40.0, {}, {})]
        current = [_row("AAA", 50.0, {}, {}), _row("ONLY_CURRENT", 60.0, {}, {})]
        result = attribute_transition(previous, current)
        self.assertEqual(result["shared_tickers"], 1)


if __name__ == "__main__":
    unittest.main()
