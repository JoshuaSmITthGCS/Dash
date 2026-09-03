import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from technical_indicators import (bollinger_percent_b, moving_average_slope,
                                  on_balance_volume_slope, relative_strength_index,
                                  support_resistance_levels, technical_extended_score)


def rising_closes(n=100, start=100, step=0.5):
    return [start + index * step for index in range(n)]


def flat_closes(n=100, value=100):
    return [value] * n


def zigzag(anchors):
    """Linearly interpolate a price path through ``(index, price)`` anchors.

    A convenient way to build a synthetic series with known swing highs/lows at known
    prices, for testing pivot detection without depending on real market data.
    """
    closes = []
    for (start_index, start_price), (end_index, end_price) in zip(anchors, anchors[1:]):
        span = end_index - start_index
        for step in range(span):
            closes.append(start_price + (end_price - start_price) * step / span)
    closes.append(anchors[-1][1])
    return closes


class MovingAverageSlopeTests(unittest.TestCase):
    def test_a_steadily_rising_series_has_a_positive_slope(self):
        self.assertGreater(moving_average_slope(rising_closes(80)), 0)

    def test_a_flat_series_has_zero_slope(self):
        self.assertEqual(moving_average_slope(flat_closes(80)), 0.0)

    def test_insufficient_history_returns_none_not_a_guess(self):
        self.assertIsNone(moving_average_slope(rising_closes(30)))


class RsiTests(unittest.TestCase):
    def test_stays_within_zero_to_a_hundred(self):
        value = relative_strength_index(rising_closes(30))
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 100)

    def test_a_purely_rising_series_is_at_the_ceiling(self):
        self.assertEqual(relative_strength_index(rising_closes(30)), 100.0)

    def test_a_purely_falling_series_is_at_the_floor(self):
        falling = list(reversed(rising_closes(30)))
        self.assertEqual(relative_strength_index(falling), 0.0)

    def test_insufficient_history_returns_none(self):
        self.assertIsNone(relative_strength_index(rising_closes(5)))


class BollingerPercentBTests(unittest.TestCase):
    def test_a_flat_series_has_no_band_width(self):
        self.assertIsNone(bollinger_percent_b(flat_closes(30)))

    def test_price_at_the_top_of_a_rising_band_is_near_one(self):
        closes = rising_closes(40, step=2.0)
        value = bollinger_percent_b(closes)
        self.assertGreater(value, 0.5)

    def test_insufficient_history_returns_none(self):
        self.assertIsNone(bollinger_percent_b(rising_closes(5)))


class OnBalanceVolumeSlopeTests(unittest.TestCase):
    def test_rising_price_with_rising_volume_is_positive(self):
        closes = rising_closes(40)
        volumes = [1_000_000 + index * 10_000 for index in range(40)]
        self.assertGreater(on_balance_volume_slope(closes, volumes), 0)

    def test_mismatched_lengths_return_none(self):
        self.assertIsNone(on_balance_volume_slope(rising_closes(40), [1, 2, 3]))

    def test_no_volume_returns_none(self):
        self.assertIsNone(on_balance_volume_slope(rising_closes(40), None))

    def test_insufficient_history_returns_none(self):
        self.assertIsNone(on_balance_volume_slope(rising_closes(5), [1] * 5))


class TechnicalExtendedScoreTests(unittest.TestCase):
    def test_returns_a_bounded_score_and_full_coverage_with_enough_history(self):
        closes = rising_closes(80)
        volumes = [1_000_000] * 80

        score, detail = technical_extended_score(closes, volumes)

        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertEqual(detail["coverage"], 1.0)

    def test_reweights_around_missing_indicators_instead_of_scoring_neutral(self):
        # Not enough history for moving_average_slope (needs 60) but enough for the
        # 20-session indicators.
        closes = rising_closes(25)
        volumes = [1_000_000] * 25

        score, detail = technical_extended_score(closes, volumes)

        self.assertIsNone(detail["raw"]["moving_average_slope"])
        self.assertLess(detail["coverage"], 1.0)
        self.assertIsNotNone(score)

    def test_no_history_at_all_returns_none_not_a_fabricated_midpoint(self):
        score, detail = technical_extended_score([], [])

        self.assertIsNone(score)
        self.assertEqual(detail["coverage"], 0.0)


class SupportResistanceLevelsTests(unittest.TestCase):
    def test_insufficient_history_returns_none(self):
        self.assertIsNone(support_resistance_levels(rising_closes(15)))

    def test_a_pure_uptrend_has_no_levels_because_nothing_has_reversed(self):
        # Nothing in a strictly monotonic series is a local extreme with room on both sides,
        # so there is nothing to call a support or a resistance level yet.
        self.assertIsNone(support_resistance_levels(rising_closes(80)))

    def test_finds_a_repeated_resistance_and_support(self):
        anchors = [(0, 100), (10, 110), (20, 95), (30, 110), (40, 95), (50, 105)]
        closes = zigzag(anchors)

        result = support_resistance_levels(closes, pivot_window=3)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["nearest_resistance"], 110, delta=1)
        self.assertGreaterEqual(result["resistance_touch_count"], 2)
        self.assertGreater(result["resistance_distance_pct"], 0)
        self.assertAlmostEqual(result["nearest_support"], 95, delta=1)
        self.assertGreaterEqual(result["support_touch_count"], 2)
        self.assertGreater(result["support_distance_pct"], 0)

    def test_a_stock_making_new_lows_has_no_support_below_only_resistance_above(self):
        anchors = [(0, 100), (10, 60), (20, 100), (30, 60), (40, 40)]
        closes = zigzag(anchors)

        result = support_resistance_levels(closes, pivot_window=3)

        self.assertIsNotNone(result)
        self.assertIsNone(result["nearest_support"])
        self.assertIsNone(result["support_distance_pct"])
        self.assertIsNotNone(result["nearest_resistance"])

    def test_no_history_at_all_returns_none(self):
        self.assertIsNone(support_resistance_levels([]))


if __name__ == "__main__":
    unittest.main()
