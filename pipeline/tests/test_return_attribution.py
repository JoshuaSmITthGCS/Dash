import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import return_attribution as ra


class DecomposeReturnTests(unittest.TestCase):
    def test_pure_re_rating_with_flat_fundamentals(self):
        # Price doubles entirely because the multiple doubles (P/E 10 -> 20); the implied
        # fundamental (EPS) must come back unchanged.
        result = ra.decompose_return(price_then=100, price_now=200, multiple_then=10, multiple_now=20)
        self.assertAlmostEqual(result["total_return"], 1.0, places=4)
        self.assertAlmostEqual(result["multiple_change"], 1.0, places=4)
        self.assertAlmostEqual(result["delivery_growth"], 0.0, places=4)
        self.assertTrue(result["mostly_re_rating"])

    def test_pure_delivery_with_a_flat_multiple(self):
        # Price doubles while the multiple is unchanged -- entirely earnings growth.
        result = ra.decompose_return(price_then=100, price_now=200, multiple_then=10, multiple_now=10)
        self.assertAlmostEqual(result["multiple_change"], 0.0, places=4)
        self.assertAlmostEqual(result["delivery_growth"], 1.0, places=4)
        self.assertFalse(result["mostly_re_rating"])

    def test_a_falling_multiple_can_still_mean_growth_did_the_work(self):
        # Multiple compresses (20 -> 15, -25%) but price still rose 20%: growth more than
        # offset the de-rating.
        result = ra.decompose_return(price_then=100, price_now=120, multiple_then=20, multiple_now=15)
        self.assertAlmostEqual(result["multiple_change"], -0.25, places=4)
        self.assertGreater(result["delivery_growth"], 0)
        self.assertFalse(result["mostly_re_rating"])

    def test_reconstructs_the_observed_price_return_exactly(self):
        result = ra.decompose_return(price_then=80, price_now=134, multiple_then=12, multiple_now=17)
        reconstructed = (1 + result["multiple_change"]) * (1 + result["delivery_growth"])
        self.assertAlmostEqual(reconstructed, 134 / 80 - 1 + 1, places=3)

    def test_nonpositive_inputs_are_undefined(self):
        self.assertIsNone(ra.decompose_return(price_then=0, price_now=100, multiple_then=10, multiple_now=10))
        self.assertIsNone(ra.decompose_return(price_then=100, price_now=100, multiple_then=-5, multiple_now=10))

    def test_missing_inputs_return_none_rather_than_a_guess(self):
        self.assertIsNone(ra.decompose_return(price_then=None, price_now=100, multiple_then=10, multiple_now=10))

    def test_a_near_total_multiple_collapse_is_undefined_not_a_wild_number(self):
        # multiple_now/multiple_then - 1 == -1 makes the delivery-growth denominator zero.
        result = ra.decompose_return(price_then=100, price_now=50, multiple_then=10, multiple_now=0.0001)
        # Whatever comes back (None, or a finite number) must not be a divide-by-zero blowup.
        if result is not None:
            self.assertLess(abs(result["delivery_growth"]), 1e6)

    def test_flat_return_is_never_flagged_as_re_rating(self):
        result = ra.decompose_return(price_then=100, price_now=100.2, multiple_then=10, multiple_now=10.1)
        self.assertFalse(result["mostly_re_rating"])


class _FakePitStore:
    def __init__(self, states_by_date):
        self._states_by_date = states_by_date

    def as_of(self, ticker, when):
        if when is None:
            when = "9999-12-31"
        candidates = [date for date in self._states_by_date if date <= when]
        if not candidates:
            return None
        latest = max(candidates)
        return {"ticker": ticker, "as_of": latest, "values": self._states_by_date[latest],
               "observed_at": {field: latest for field in self._states_by_date[latest]}}


class AttributeReturnFromHistoryTests(unittest.TestCase):
    def test_end_to_end_against_a_fake_pit_store(self):
        store = _FakePitStore({
            "2025-01-15": {"price": 100.0, "forward_pe": 10.0},
            "2026-01-15": {"price": 150.0, "forward_pe": 12.0},
        })
        result = ra.attribute_return_from_history(
            "FAKE", multiple_field="forward_pe", months_back=12, pit_store=store)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["multiple_change"], 0.2, places=4)
        self.assertEqual(result["multiple_field"], "forward_pe")

    def test_no_history_returns_none(self):
        store = _FakePitStore({})
        result = ra.attribute_return_from_history(
            "FAKE", multiple_field="forward_pe", months_back=12, pit_store=store)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
