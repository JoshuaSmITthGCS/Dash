"""Point-in-time derivation: filed facts into ratios, visible only when they were filed.

Every test here is about the same property from a different angle -- a value computed for a
date must use only what had been filed by that date, and a missing input must produce an
absent ratio rather than a defaulted one.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pit_derive import derive, growth, trailing_twelve_months


def flow(concept, start, end, value, filed, period_type="quarter"):
    return {"concept": concept, "period_start": start, "period_end": end, "value": value,
            "filed": filed, "available_at": filed, "period_type": period_type,
            "unit": "USD", "accession": f"{concept}-{end}-{filed}"}


def instant(concept, end, value, filed):
    return {"concept": concept, "period_start": None, "period_end": end, "value": value,
            "filed": filed, "available_at": filed, "period_type": "instant",
            "unit": "USD", "accession": f"{concept}-{end}"}


def four_quarters(concept="revenue", base=100, filed_lag=("2024-05-01", "2024-08-01",
                                                          "2024-11-01", "2025-02-01")):
    spans = [("2023-10-01", "2023-12-31"), ("2024-01-01", "2024-03-31"),
             ("2024-04-01", "2024-06-30"), ("2024-07-01", "2024-09-30")]
    return [flow(concept, start, end, base + index, filed_lag[index])
            for index, (start, end) in enumerate(spans)]


class TrailingTwelveMonthTests(unittest.TestCase):
    def test_four_quarters_sum_to_a_trailing_year(self):
        value, detail = trailing_twelve_months(four_quarters(), "2025-03-01")
        self.assertEqual(value, 100 + 101 + 102 + 103)
        self.assertEqual(detail["method"], "four_quarters")

    def test_a_quarter_filed_after_the_as_of_date_is_not_used(self):
        rows = four_quarters()
        value, detail = trailing_twelve_months(rows, "2024-12-01")
        self.assertNotEqual(detail["method"], "four_quarters")
        self.assertIsNone(value)

    def test_adjacent_quarters_sharing_a_boundary_date_are_not_treated_as_overlapping(self):
        """SEC period conventions are inconsistent: Apple's Q3 FY2024 ends 2024-06-29 and the
        next quarter starts on that same date. A `>=` overlap test left a hole in the year and
        fell back to a stale annual for a third of every year."""
        rows = [flow("revenue", "2023-09-30", "2023-12-30", 10, "2024-02-01"),
                flow("revenue", "2023-12-30", "2024-03-30", 20, "2024-05-01"),
                flow("revenue", "2024-03-30", "2024-06-29", 30, "2024-08-01"),
                flow("revenue", "2024-06-29", "2024-09-28", 40, "2024-11-01")]
        value, detail = trailing_twelve_months(rows, "2025-01-01")
        self.assertEqual(detail["method"], "four_quarters")
        self.assertEqual(value, 100)

    def test_a_missing_fourth_quarter_is_synthesised_from_annual_minus_nine_months(self):
        """Most annual filers never tag Q4 separately."""
        rows = [flow("revenue", "2023-10-01", "2023-12-31", 100, "2024-02-01"),
                flow("revenue", "2024-01-01", "2024-03-31", 101, "2024-05-01"),
                flow("revenue", "2024-04-01", "2024-06-30", 102, "2024-08-01"),
                flow("revenue", "2023-10-01", "2024-06-30", 303, "2024-08-01", "nine_months"),
                flow("revenue", "2023-10-01", "2024-09-30", 406, "2024-11-01", "annual")]
        value, detail = trailing_twelve_months(rows, "2025-01-01")
        self.assertEqual(detail["method"], "four_quarters")
        self.assertEqual(value, 406)
        self.assertEqual(detail["synthesised_quarters"], ["2024-09-30"])

    def test_a_synthesised_quarter_is_invisible_until_both_its_inputs_were_filed(self):
        rows = [flow("revenue", "2023-10-01", "2024-06-30", 303, "2024-08-01", "nine_months"),
                flow("revenue", "2023-10-01", "2024-09-30", 406, "2024-11-01", "annual")]
        value, detail = trailing_twelve_months(rows, "2024-10-01")
        self.assertNotEqual(detail["method"], "four_quarters")

    def test_the_annual_fallback_says_it_may_be_stale(self):
        rows = [flow("revenue", "2023-10-01", "2024-09-30", 406, "2024-11-01", "annual")]
        value, detail = trailing_twelve_months(rows, "2025-08-01")
        self.assertEqual(detail["method"], "latest_annual")
        self.assertIn("stale", detail["caveat"])

    def test_a_restated_quarter_supersedes_only_after_its_own_filing(self):
        rows = [*four_quarters(),
                flow("revenue", "2024-07-01", "2024-09-30", 999, "2025-06-01")]
        before, _ = trailing_twelve_months(rows, "2025-03-01")
        after, _ = trailing_twelve_months(rows, "2025-07-01")
        self.assertEqual(before, 406)
        self.assertEqual(after, 100 + 101 + 102 + 999)

    def test_nothing_filed_yet_produces_no_value(self):
        value, detail = trailing_twelve_months(four_quarters(), "2020-01-01")
        self.assertIsNone(value)
        self.assertEqual(detail["method"], "unavailable")


class DerivedRatioTests(unittest.TestCase):
    def observations(self):
        return [*four_quarters("revenue", base=1000),
                *four_quarters("net_income", base=100),
                instant("equity", "2024-09-30", 2000, "2024-11-01"),
                instant("assets", "2024-09-30", 5000, "2024-11-01")]

    def test_ratios_are_computed_from_filed_inputs(self):
        result = derive(self.observations(), "2025-03-01")
        metrics = result["metrics"]
        self.assertAlmostEqual(metrics["profit_margin"], 406 / 4006, places=6)
        self.assertAlmostEqual(metrics["return_on_equity"], 406 / 2000, places=6)
        self.assertAlmostEqual(metrics["return_on_assets"], 406 / 5000, places=6)

    def test_a_ratio_with_a_missing_input_is_absent_and_named(self):
        result = derive(four_quarters("revenue"), "2025-03-01")
        self.assertIsNone(result["metrics"]["return_on_equity"])
        self.assertIn("return_on_equity", result["inputs_missing"])

    def test_a_zero_denominator_yields_absence_rather_than_infinity(self):
        rows = [*four_quarters("net_income", base=100), instant("equity", "2024-09-30", 0, "2024-11-01")]
        self.assertIsNone(derive(rows, "2025-03-01")["metrics"]["return_on_equity"])

    def test_negative_equity_does_not_produce_a_flattering_return(self):
        """A negative book value makes ROE meaningless, not excellent."""
        rows = [*four_quarters("net_income", base=100),
                instant("equity", "2024-09-30", -500, "2024-11-01")]
        self.assertIsNone(derive(rows, "2025-03-01")["metrics"]["return_on_equity"])

    def test_balance_sheet_items_are_read_as_of_not_summed(self):
        rows = [instant("assets", "2024-06-30", 4000, "2024-08-01"),
                instant("assets", "2024-09-30", 5000, "2024-11-01")]
        self.assertEqual(derive(rows, "2024-09-01")["metrics"]["assets"], 4000)
        self.assertEqual(derive(rows, "2024-12-01")["metrics"]["assets"], 5000)

    def test_free_cash_flow_subtracts_capex_regardless_of_its_sign(self):
        rows = [*four_quarters("operating_cash_flow", base=100),
                *four_quarters("capital_expenditure", base=-10)]
        metrics = derive(rows, "2025-03-01")["metrics"]
        self.assertEqual(metrics["free_cash_flow_ttm"], 406 - abs(-34))

    def test_coverage_reports_how_much_actually_resolved(self):
        full = derive(self.observations(), "2025-03-01")
        thin = derive(four_quarters("revenue"), "2025-03-01")
        self.assertGreater(full["coverage"], thin["coverage"])


class GrowthTests(unittest.TestCase):
    def test_both_legs_are_evaluated_point_in_time(self):
        rows = [*four_quarters("revenue", base=1000),
                flow("revenue", "2022-10-01", "2022-12-31", 900, "2023-02-01"),
                flow("revenue", "2023-01-01", "2023-03-31", 900, "2023-05-01"),
                flow("revenue", "2023-04-01", "2023-06-30", 900, "2023-08-01"),
                flow("revenue", "2023-07-01", "2023-09-30", 900, "2023-11-01")]
        value, detail = growth(rows, "2025-03-01")
        self.assertEqual(detail["method"], "ttm_over_ttm")
        self.assertAlmostEqual(value, (4006 - 3600) / 3600, places=6)

    def test_growth_is_absent_when_the_prior_year_was_not_filed_yet(self):
        value, detail = growth(four_quarters("revenue"), "2025-03-01")
        self.assertIsNone(value)
        self.assertEqual(detail["method"], "unavailable")


class LiveStoreTests(unittest.TestCase):
    """Apple's real filings, as committed. Values verified against the published 10-K."""

    CIK = "0000320193"

    def setUp(self):
        from pit_fundamentals_store import ShardedStore, shard_for
        directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pit",
                                 "fundamentals")
        if not os.path.isdir(directory):
            self.skipTest("no point-in-time fundamentals store in this checkout")
        store = ShardedStore(directory)
        self.rows = [row for row in store.load(shard=shard_for(self.CIK))
                     if row["cik"] == self.CIK]
        if not self.rows:
            self.skipTest("Apple is not in this store")

    def test_the_annual_report_becomes_visible_on_the_day_it_was_filed(self):
        before = derive(self.rows, "2024-10-31")["metrics"]["revenue_ttm"]
        after = derive(self.rows, "2024-11-01")["metrics"]["revenue_ttm"]
        self.assertNotEqual(before, after)
        # Apple's FY2024 revenue, as filed on 2024-11-01.
        self.assertAlmostEqual(after / 1e9, 391.0, places=0)

    def test_trailing_twelve_months_keeps_up_with_quarterly_filings(self):
        result = derive(self.rows, "2025-06-01")
        self.assertEqual(result["flow_detail"]["revenue"]["method"], "four_quarters")
        self.assertEqual(result["as_reported_through"], "2025-03-29")

    def test_margins_are_in_a_plausible_range_for_the_company(self):
        metrics = derive(self.rows, "2025-06-01")["metrics"]
        self.assertTrue(0.15 < metrics["profit_margin"] < 0.35)
        self.assertTrue(0.20 < metrics["operating_margin"] < 0.45)


if __name__ == "__main__":
    unittest.main()


def test_components_expose_the_levels_the_ratios_were_built_from():
    """A consumer forming enterprise value or tangible book should not re-derive the TTM.

    ``metrics`` publishes ratios; ``components`` publishes the flows and instants underneath
    them, on the same point-in-time basis, so a caller can build EV/EBITDA or book value net
    of goodwill without a second pass over the store.
    """
    rows = [
        flow("revenue", "2023-01-01", "2023-03-31", 100.0, "2023-04-20"),
        flow("revenue", "2023-04-01", "2023-06-30", 110.0, "2023-07-20"),
        flow("revenue", "2023-07-01", "2023-09-30", 120.0, "2023-10-20"),
        flow("revenue", "2023-10-01", "2023-12-31", 130.0, "2024-01-20"),
        instant("cash", "2023-12-31", 45.0, "2024-01-20"),
        instant("goodwill", "2023-12-31", 12.0, "2024-01-20"),
    ]
    result = derive(rows, "2024-02-01")
    assert result["components"]["revenue"] == 460.0
    assert result["components"]["cash"] == 45.0
    assert result["components"]["goodwill"] == 12.0
    # A component nothing was filed for stays absent rather than becoming zero.
    assert result["components"]["inventory"] is None


def test_components_respect_the_as_of_date_like_everything_else():
    rows = [instant("cash", "2023-12-31", 45.0, "2024-01-20")]
    assert derive(rows, "2024-01-19")["components"]["cash"] is None
    assert derive(rows, "2024-01-20")["components"]["cash"] == 45.0
