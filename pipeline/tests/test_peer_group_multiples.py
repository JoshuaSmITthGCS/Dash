import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from peer_groups import peer_group_multiple_medians


def rows(values, sector="Technology"):
    """{"ticker", "sector", "ev_to_ebitda"} rows, one per value; None values are missing data."""
    return [{"ticker": f"T{index}", "sector": sector, "ev_to_ebitda": value}
            for index, value in enumerate(values)]


class PeerGroupMultipleMedianTests(unittest.TestCase):
    def test_median_is_published_once_the_group_clears_the_minimum(self):
        result = peer_group_multiple_medians(rows([10, 12, 14, 16, 18]), minimum=5)
        for ticker in ("T0", "T1", "T2", "T3", "T4"):
            self.assertEqual(result[ticker]["peer_group_median_multiple"], 14)
            self.assertEqual(result[ticker]["peer_group_multiple_sample_count"], 5)
            self.assertEqual(result[ticker]["peer_group_multiple_key"], "ev_to_ebitda")

    def test_median_is_null_below_the_minimum_but_the_ticker_still_appears(self):
        result = peer_group_multiple_medians(rows([10, 12, 14]), minimum=5)
        self.assertIn("T0", result)
        self.assertIsNone(result["T0"]["peer_group_median_multiple"])
        self.assertEqual(result["T0"]["peer_group_multiple_sample_count"], 3)

    def test_missing_values_are_excluded_from_the_median_but_ticker_still_appears(self):
        data = rows([10, 12, 14, 16, None])
        result = peer_group_multiple_medians(data, minimum=4)
        self.assertEqual(result["T4"]["peer_group_multiple_sample_count"], 4)
        self.assertIsNotNone(result["T4"]["peer_group_median_multiple"])

    def test_groups_are_kept_separate_by_sector(self):
        tech = rows([10, 12, 14, 16, 18], sector="Technology")
        healthcare = [{"ticker": f"H{index}", "sector": "Healthcare", "ev_to_ebitda": value}
                     for index, value in enumerate([2, 4, 6, 8, 10])]
        result = peer_group_multiple_medians(tech + healthcare, minimum=5)
        self.assertEqual(result["T0"]["peer_group_median_multiple"], 14)
        self.assertEqual(result["H0"]["peer_group_median_multiple"], 6)

    def test_a_custom_multiple_key_is_respected(self):
        data = [{"ticker": "T0", "sector": "Technology", "ev_to_sales": 3.0},
               {"ticker": "T1", "sector": "Technology", "ev_to_sales": 5.0}]
        result = peer_group_multiple_medians(data, multiple_key="ev_to_sales", minimum=2)
        self.assertEqual(result["T0"]["peer_group_median_multiple"], 4.0)
        self.assertEqual(result["T0"]["peer_group_multiple_key"], "ev_to_sales")


if __name__ == "__main__":
    unittest.main()
