import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import options_track_record as otr  # noqa: E402
from options_common import call_price, put_price  # noqa: E402


class LegsForTests(unittest.TestCase):
    def test_options_screen_produces_one_bought_leg_no_stock_leg(self):
        row = {"option_type": "call", "strike": 100.0, "mid": 5.0}
        legs, stock_leg = otr.legs_for("options", row)
        self.assertEqual(legs, [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}])
        self.assertFalse(stock_leg)

    def test_covered_calls_produces_one_sold_leg_plus_a_stock_leg(self):
        row = {"legs": [{"action": "sell", "option_type": "call", "strike": 105.0, "mid": 3.0}]}
        legs, stock_leg = otr.legs_for("covered_calls", row)
        self.assertEqual(legs, [{"action": "sell", "option_type": "call", "strike": 105.0, "premium": 3.0}])
        self.assertTrue(stock_leg)

    def test_cash_secured_puts_produces_one_sold_leg_no_stock_leg(self):
        row = {"legs": [{"action": "sell", "option_type": "put", "strike": 95.0, "mid": 4.0}]}
        legs, stock_leg = otr.legs_for("cash_secured_puts", row)
        self.assertEqual(legs, [{"action": "sell", "option_type": "put", "strike": 95.0, "premium": 4.0}])
        self.assertFalse(stock_leg)

    def test_short_term_trades_sell_call_gets_a_stock_leg_but_sell_put_does_not(self):
        sell_call_row = {"strategy": "sell_call", "legs": [{"action": "sell", "option_type": "call", "strike": 100.0, "mid": 2.0}]}
        sell_put_row = {"strategy": "sell_put", "legs": [{"action": "sell", "option_type": "put", "strike": 90.0, "mid": 2.0}]}
        _, sell_call_stock_leg = otr.legs_for("short_term_trades", sell_call_row)
        _, sell_put_stock_leg = otr.legs_for("short_term_trades", sell_put_row)
        self.assertTrue(sell_call_stock_leg)
        self.assertFalse(sell_put_stock_leg)

    def test_an_unrecognized_sub_screen_returns_nothing_rather_than_raising(self):
        self.assertEqual(otr.legs_for("mystery", {"anything": True}), ([], False))


class CapitalRequiredForTests(unittest.TestCase):
    def test_options_screen_computes_premium_times_the_contract_multiplier(self):
        self.assertEqual(otr.capital_required_for("options", {"mid": 5.0}), 500.0)

    def test_options_screen_is_none_without_a_premium(self):
        self.assertIsNone(otr.capital_required_for("options", {"mid": None}))

    def test_every_other_sub_screen_uses_the_published_field_directly(self):
        self.assertEqual(otr.capital_required_for("covered_calls", {"capital_required": 12345.0}), 12345.0)


class PositionPnlSettlementTests(unittest.TestCase):
    """dte_now <= 0: settled on intrinsic value, no Black-Scholes involved - exact numbers."""

    def test_a_bought_call_that_settles_in_the_money_profits_by_intrinsic_less_premium(self):
        position = {"expiration": "2020-01-01",
                   "legs": [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}]}
        pnl = otr.position_pnl(position, spot_now=110.0, iv_now=0.3)
        self.assertAlmostEqual(pnl, (10.0 - 5.0) * 100)

    def test_a_bought_call_that_settles_out_of_the_money_loses_the_full_premium(self):
        position = {"expiration": "2020-01-01",
                   "legs": [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}]}
        pnl = otr.position_pnl(position, spot_now=90.0, iv_now=0.3)
        self.assertAlmostEqual(pnl, (0.0 - 5.0) * 100)

    def test_a_sold_put_that_settles_out_of_the_money_keeps_the_full_premium(self):
        position = {"expiration": "2020-01-01",
                   "legs": [{"action": "sell", "option_type": "put", "strike": 100.0, "premium": 4.0}]}
        pnl = otr.position_pnl(position, spot_now=110.0, iv_now=0.3)
        self.assertAlmostEqual(pnl, (4.0 - 0.0) * 100)

    def test_a_sold_put_that_settles_in_the_money_is_assigned_at_a_loss(self):
        position = {"expiration": "2020-01-01",
                   "legs": [{"action": "sell", "option_type": "put", "strike": 100.0, "premium": 4.0}]}
        pnl = otr.position_pnl(position, spot_now=90.0, iv_now=0.3)
        self.assertAlmostEqual(pnl, (4.0 - 10.0) * 100)

    def test_a_covered_call_combines_the_stock_leg_with_the_short_call_leg(self):
        position = {"expiration": "2020-01-01", "entry_underlying_price": 95.0, "stock_leg": True,
                   "legs": [{"action": "sell", "option_type": "call", "strike": 100.0, "premium": 3.0}]}
        pnl = otr.position_pnl(position, spot_now=110.0, iv_now=0.3)
        stock_pnl = (110.0 - 95.0) * 100
        call_pnl = (3.0 - 10.0) * 100  # short call is deep ITM at settlement, a loss on that leg alone
        self.assertAlmostEqual(pnl, stock_pnl + call_pnl)

    def test_a_covered_call_missing_its_entry_price_cannot_be_priced(self):
        position = {"expiration": "2020-01-01", "stock_leg": True,
                   "legs": [{"action": "sell", "option_type": "call", "strike": 100.0, "premium": 3.0}]}
        self.assertIsNone(otr.position_pnl(position, spot_now=110.0, iv_now=0.3))


class PositionPnlMarkTests(unittest.TestCase):
    """dte_now > 0: Black-Scholes marks, checked against options_common directly rather than
    hand-computed - this is a plumbing test (right inputs reach the pricer), not a re-proof
    of Black-Scholes itself."""

    def test_a_bought_call_marks_via_black_scholes_while_time_remains(self):
        position = {"expiration": "2099-01-01",
                   "legs": [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}]}
        pnl = otr.position_pnl(position, spot_now=105.0, iv_now=0.3, as_of=__import__("datetime").date(2098, 12, 1))
        expected_mark = call_price(105.0, 100.0, 0.3, 31)
        self.assertAlmostEqual(pnl, (expected_mark - 5.0) * 100, places=2)

    def test_a_sold_put_marks_via_black_scholes_while_time_remains(self):
        position = {"expiration": "2099-01-01",
                   "legs": [{"action": "sell", "option_type": "put", "strike": 100.0, "premium": 4.0}]}
        as_of = __import__("datetime").date(2098, 12, 1)
        pnl = otr.position_pnl(position, spot_now=95.0, iv_now=0.3, as_of=as_of)
        expected_mark = put_price(95.0, 100.0, 0.3, 31)
        self.assertAlmostEqual(pnl, (4.0 - expected_mark) * 100, places=2)

    def test_a_mark_with_no_volatility_reading_cannot_be_priced(self):
        position = {"expiration": "2099-01-01",
                   "legs": [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}]}
        self.assertIsNone(otr.position_pnl(position, spot_now=105.0, iv_now=None))


class TrackRecordForTests(unittest.TestCase):
    def test_no_position_returns_an_all_none_record(self):
        self.assertEqual(otr.track_record_for(None, 100.0, 0.3),
                         {"date_predicted": None, "pnl_dollars": None, "pnl_pct_of_capital": None})

    def test_a_priceable_position_reports_dollars_and_percent_of_capital(self):
        position = {"date_predicted": "2026-09-01", "expiration": "2020-01-01",
                   "capital_required": 500.0,
                   "legs": [{"action": "buy", "option_type": "call", "strike": 100.0, "premium": 5.0}]}
        record = otr.track_record_for(position, spot_now=110.0, iv_now=0.3)
        self.assertEqual(record["date_predicted"], "2026-09-01")
        self.assertEqual(record["pnl_dollars"], 500.0)
        self.assertEqual(record["pnl_pct_of_capital"], 100.0)


TOP_ROW = {"ticker": "A", "rank": 3, "price": 100.0, "expiration": "2099-01-01",
          "option_type": "call", "strike": 105.0, "mid": 5.0}
OUTSIDE_TOP_ROW = {"ticker": "B", "rank": 11, "price": 50.0, "expiration": "2099-01-01",
                  "option_type": "call", "strike": 55.0, "mid": 2.0}


class UpdateFirstSeenTests(unittest.TestCase):
    def test_a_qualifying_position_is_recorded_with_todays_date_and_its_full_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = otr.update_first_seen({"options": [TOP_ROW]}, recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertEqual(store["options"]["A"], {
                "date_predicted": "2026-09-15", "entry_underlying_price": 100.0,
                "expiration": "2099-01-01", "capital_required": 500.0,
                "legs": [{"action": "buy", "option_type": "call", "strike": 105.0, "premium": 5.0}],
                "stock_leg": False,
            })
            self.assertEqual(otr.load_first_seen(tmp), store)

    def test_a_position_ranking_outside_top_n_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = otr.update_first_seen({"options": [OUTSIDE_TOP_ROW]}, recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertEqual(store["options"], {})

    def test_a_position_still_top_n_on_a_later_run_keeps_its_original_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            otr.update_first_seen({"options": [TOP_ROW]}, recorded_at_date="2026-09-15", store_dir=tmp)
            moved = {**TOP_ROW, "rank": 1, "price": 130.0, "mid": 20.0}
            store = otr.update_first_seen({"options": [moved]}, recorded_at_date="2026-09-20", store_dir=tmp)
            self.assertEqual(store["options"]["A"]["date_predicted"], "2026-09-15")
            self.assertEqual(store["options"]["A"]["entry_underlying_price"], 100.0)

    def test_a_position_that_falls_out_of_the_top_n_is_evicted(self):
        with tempfile.TemporaryDirectory() as tmp:
            otr.update_first_seen({"options": [TOP_ROW]}, recorded_at_date="2026-09-15", store_dir=tmp)
            store = otr.update_first_seen({"options": []}, recorded_at_date="2026-09-20", store_dir=tmp)
            self.assertEqual(store["options"], {})

    def test_sub_screens_are_tracked_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            covered_call_row = {"ticker": "C", "rank": 1, "price": 80.0, "expiration": "2099-01-01",
                                "capital_required": 8000.0,
                                "legs": [{"action": "sell", "option_type": "call", "strike": 85.0, "mid": 2.0}]}
            store = otr.update_first_seen(
                {"options": [TOP_ROW], "covered_calls": [covered_call_row]},
                recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertIn("A", store["options"])
            self.assertNotIn("A", store["covered_calls"])
            self.assertIn("C", store["covered_calls"])

    def test_a_row_missing_a_strike_or_premium_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = {**TOP_ROW, "mid": None}
            store = otr.update_first_seen({"options": [broken]}, recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertEqual(store["options"], {})


if __name__ == "__main__":
    unittest.main()
