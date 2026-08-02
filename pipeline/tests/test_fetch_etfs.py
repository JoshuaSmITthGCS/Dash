import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_etfs import build_etf_row, rank_etf_rows


class BuildEtfRowTests(unittest.TestCase):
    def test_growth_score_weights_20d_return_most_heavily(self):
        row = build_etf_row(
            "QQQ", {"name": "Nasdaq 100", "category": "growth", "expense_ratio": 0.20},
            {"price": 520, "dividend_yield": 0.006},
            {"return_5d": 4.0, "return_20d": 10.0, "return_60d": 2.0},
        )

        self.assertEqual(row["ticker"], "QQQ")
        self.assertEqual(row["category"], "growth")
        self.assertEqual(row["growth_score"], round(10.0 * 0.55 + 4.0 * 0.25 + 2.0 * 0.20, 2))

    def test_missing_return_windows_default_to_zero(self):
        row = build_etf_row(
            "BND", {"name": "Total Bond Market"}, {},
            {"return_20d": -1.0},
        )

        self.assertEqual(row["growth_score"], round(-1.0 * 0.55, 2))


class RankEtfRowsTests(unittest.TestCase):
    def test_ranks_by_growth_score_descending(self):
        rows = [
            {"ticker": "BND", "growth_score": -1.2},
            {"ticker": "SMH", "growth_score": 11.3},
            {"ticker": "VTI", "growth_score": 2.4},
        ]

        ranked = rank_etf_rows(rows)

        self.assertEqual([row["ticker"] for row in ranked], ["SMH", "VTI", "BND"])
        self.assertEqual([row["growth_rank"] for row in ranked], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
