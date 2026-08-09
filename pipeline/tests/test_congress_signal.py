import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from congress_signal import buys_for_ticker, score_congressional_buying

TODAY = date(2026, 8, 9)


def _row(symbol="ACME", representative="Rep A", transaction_type="Purchase",
        disclosure_date="2026-08-01", amount="$15,001 - $50,000", flags=None):
    return {
        "symbol": symbol, "representative": representative, "transaction_type": transaction_type,
        "disclosure_date": disclosure_date, "transaction_date": disclosure_date,
        "amount_lower": 15001, "amount": amount, "flags": flags or [],
    }


class BuysForTickerTests(unittest.TestCase):
    def test_only_purchases_of_the_requested_ticker_match(self):
        rows = [_row(symbol="ACME"), _row(symbol="OTHER"),
                _row(symbol="ACME", transaction_type="Sale")]
        self.assertEqual(len(buys_for_ticker(rows, "ACME")), 1)


class ScoreCongressionalBuyingTests(unittest.TestCase):
    def test_no_purchases_scores_zero_and_is_unavailable(self):
        points, detail = score_congressional_buying([], "ACME", as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_a_single_ordinary_purchase_is_a_mild_positive(self):
        rows = [_row()]
        points, detail = score_congressional_buying(rows, "ACME", as_of=TODAY)
        self.assertGreater(points, 0.0)
        self.assertEqual(detail["extraordinary_members"], 0)

    def test_multiple_members_buying_scores_higher_than_one(self):
        one = score_congressional_buying([_row(representative="Rep A")], "ACME", as_of=TODAY)[0]
        many = score_congressional_buying(
            [_row(representative="Rep A"), _row(representative="Rep B"),
             _row(representative="Rep C")], "ACME", as_of=TODAY)[0]
        self.assertGreater(many, one)

    def test_an_extraordinary_buy_scores_higher_than_an_ordinary_one(self):
        ordinary = score_congressional_buying([_row()], "ACME", as_of=TODAY)[0]
        extraordinary = score_congressional_buying(
            [_row(flags=["NOVEL_TICKER", "EXTRAORDINARY_BUY"])], "ACME", as_of=TODAY)[0]
        self.assertGreater(extraordinary, ordinary)

    def test_a_stale_purchase_scores_zero(self):
        rows = [_row(disclosure_date="2026-01-01")]
        points, detail = score_congressional_buying(rows, "ACME", as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertIn("stale", detail["reason"])

    def test_a_sale_never_contributes_even_if_flagged(self):
        rows = [_row(transaction_type="Sale", flags=["EXTRAORDINARY_BUY"])]
        points, detail = score_congressional_buying(rows, "ACME", as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_a_trade_below_min_trade_value_does_not_count(self):
        rows = [{**_row(), "amount_lower": 5000}]
        points, _ = score_congressional_buying(
            rows, "ACME", as_of=TODAY, config={"min_trade_value": 15000.0})
        self.assertEqual(points, 0.0)

    def test_points_are_never_negative(self):
        for rows in ([], [_row()], [_row(disclosure_date="2020-01-01")]):
            points, _ = score_congressional_buying(rows, "ACME", as_of=TODAY)
            self.assertGreaterEqual(points, 0.0)


if __name__ == "__main__":
    unittest.main()
