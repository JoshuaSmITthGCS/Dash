import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import growth_track_record as gtr  # noqa: E402


def breakout_row(ticker, price=100.0, **overrides):
    row = {"ticker": ticker, "is_etf": False, "price": price,
           "technical_detail": {"return_5d": 4.0, "return_20d": 6.0, "volume_ratio_60d": 1.5}}
    row.update(overrides)
    return row


def emerging_row(ticker, price=100.0, **overrides):
    row = {"ticker": ticker, "is_etf": False, "price": price,
           "technical_detail": {"return_5d": 1.0, "relative_strength_20d": 3.0},
           "fundamental_detail": {"revenue_growth": 0.15, "operating_margin_trend": 0.02}}
    row.update(overrides)
    return row


class LoadOnEmptyStoreTests(unittest.TestCase):
    def test_returns_empty_maps_for_both_sub_screens(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gtr.load(tmp), {"breakout": {}, "emerging": {}})


class UpdateTests(unittest.TestCase):
    def test_a_qualifying_ticker_is_recorded_with_todays_date_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = gtr.update([breakout_row("UP", price=50.0)], recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertEqual(store["breakout"]["UP"],
                             {"date_predicted": "2026-09-15", "price_at_prediction": 50.0})
            self.assertEqual(gtr.load(tmp), store)

    def test_a_ticker_still_in_the_top_n_on_a_later_run_keeps_its_original_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            gtr.update([breakout_row("UP")], recorded_at_date="2026-09-15", store_dir=tmp)
            store = gtr.update([breakout_row("UP", price=120.0)], recorded_at_date="2026-09-20", store_dir=tmp)
            # Price moved (the ticker is still ranked, just at a new price); the entry date and
            # the price recorded AT ENTRY must not move with it.
            self.assertEqual(store["breakout"]["UP"],
                             {"date_predicted": "2026-09-15", "price_at_prediction": 100.0})

    def test_a_ticker_that_falls_out_of_the_top_n_is_evicted(self):
        with tempfile.TemporaryDirectory() as tmp:
            gtr.update([breakout_row("GONE")], recorded_at_date="2026-09-15", store_dir=tmp)
            # A row that no longer clears the breakout gates at all - "GONE" simply is not in
            # this run's candidate list any more, exactly like falling out of the ranking.
            store = gtr.update([breakout_row("STILL_IN")], recorded_at_date="2026-09-20", store_dir=tmp)
            self.assertNotIn("GONE", store["breakout"])
            self.assertIn("STILL_IN", store["breakout"])

    def test_re_entering_later_starts_a_fresh_clock_rather_than_resuming_the_old_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            gtr.update([breakout_row("CYCLE", price=50.0)], recorded_at_date="2026-09-01", store_dir=tmp)
            gtr.update([], recorded_at_date="2026-09-05", store_dir=tmp)  # falls out
            store = gtr.update([breakout_row("CYCLE", price=80.0)], recorded_at_date="2026-09-10", store_dir=tmp)
            self.assertEqual(store["breakout"]["CYCLE"],
                             {"date_predicted": "2026-09-10", "price_at_prediction": 80.0})

    def test_the_two_sub_screens_are_tracked_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = gtr.update([breakout_row("B_ONLY"), emerging_row("E_ONLY")],
                               recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertIn("B_ONLY", store["breakout"])
            self.assertNotIn("B_ONLY", store["emerging"])
            self.assertIn("E_ONLY", store["emerging"])
            self.assertNotIn("E_ONLY", store["breakout"])

    def test_top_n_is_respected_when_deciding_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [breakout_row(f"T{i}", technical_detail={"return_5d": 4.0 + i, "return_20d": 6.0,
                                                            "volume_ratio_60d": 1.0})
                    for i in range(15)]
            store = gtr.update(rows, recorded_at_date="2026-09-15", store_dir=tmp, top_n=10)
            self.assertEqual(len(store["breakout"]), 10)
            # T14 has the highest week_return and therefore the top rank; T0 the lowest.
            self.assertIn("T14", store["breakout"])
            self.assertNotIn("T0", store["breakout"])

    def test_a_ticker_with_no_price_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = gtr.update([breakout_row("NOPRICE", price=None)], recorded_at_date="2026-09-15", store_dir=tmp)
            self.assertEqual(store["breakout"], {})


if __name__ == "__main__":
    unittest.main()
