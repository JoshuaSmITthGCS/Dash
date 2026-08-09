"""Phase 2.4: a suspicious provider value must not quietly enter the scoring model.

The values in these tests are the ones that shipped. THG published an incremental margin of
89.9% and NEM 128.2%; both are arithmetically impossible as a steady state, both came from a
near-zero revenue denominator, and neither was flagged anywhere in the payload.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from plausibility import (cross_source_violations, field_violations,
                          implied_share_count_violations, screen)


def rules(violations):
    return {item["rule"] for item in violations}


class ArithmeticImpossibilityTests(unittest.TestCase):
    def test_a_margin_above_one_hundred_percent_is_rejected(self):
        self.assertIn("margin_above_100_percent", rules(field_violations({"profit_margin": 1.4})))

    def test_an_ordinary_margin_passes(self):
        self.assertEqual(field_violations({"profit_margin": 0.21}), [])

    def test_a_large_but_real_loss_passes(self):
        """A pre-profit company can lose several times revenue; that is a business, not a bug."""
        self.assertEqual(field_violations({"profit_margin": -3.0}), [])

    def test_roic_above_two_hundred_percent_is_rejected(self):
        self.assertIn("roic_above_200_percent",
                      rules(field_violations({"return_on_invested_capital": 3.5})))

    def test_accruals_cannot_exceed_the_asset_base(self):
        self.assertIn("accruals_exceed_total_assets",
                      rules(field_violations({"accruals_ratio": -1.8})))

    def test_the_f_score_is_nine_binary_tests(self):
        self.assertIn("piotroski_outside_0_9", rules(field_violations({"piotroski_f": 11})))
        self.assertEqual(field_violations({"piotroski_f": 8.5}), [])

    def test_a_negative_forward_pe_is_a_provider_artefact_not_a_cheap_stock(self):
        self.assertIn("negative_forward_pe", rules(field_violations({"forward_pe": -6.0})))


class UnitErrorTests(unittest.TestCase):
    """The failure that looks most like data: wrong by orders of magnitude, ordinary as a float."""

    def test_a_market_cap_in_thousands_is_caught(self):
        self.assertIn("market_cap_implausibly_small",
                      rules(field_violations({"market_cap": 8_400.0})))

    def test_a_real_market_cap_passes(self):
        self.assertEqual(field_violations({"market_cap": 8_400_000_000.0}), [])

    def test_a_split_adjusted_price_against_an_unadjusted_share_count(self):
        violations = implied_share_count_violations(
            {"price": 50.0, "shares_outstanding": 400_000_000, "market_cap": 4_000_000_000})
        self.assertEqual(rules(violations), {"market_cap_inconsistent_with_price_times_shares"})

    def test_a_consistent_share_count_passes(self):
        self.assertEqual(implied_share_count_violations(
            {"price": 50.0, "shares_outstanding": 80_000_000, "market_cap": 4_000_000_000}), [])


class IncrementalMarginTests(unittest.TestCase):
    """The two published values that motivated this module."""

    def test_thg_eighty_nine_point_nine_percent_is_accepted_as_a_ratio(self):
        """89.9% is below 1.0, so only the denominator rule can catch it."""
        self.assertEqual(field_violations({"incremental_margin": 0.899}), [])

    def test_nem_one_hundred_twenty_eight_percent_is_rejected_outright(self):
        self.assertIn("incremental_margin_outside_unit_interval",
                      rules(field_violations({"incremental_margin": 1.282})))

    def test_a_near_flat_revenue_denominator_invalidates_the_ratio(self):
        violations = field_violations({
            "incremental_margin": 0.899, "revenue": 6_050_000_000, "prior_revenue": 6_000_000_000})
        self.assertIn("incremental_margin_denominator_too_small", rules(violations))

    def test_a_real_revenue_change_leaves_the_ratio_alone(self):
        violations = field_violations({
            "incremental_margin": 0.42, "revenue": 7_200_000_000, "prior_revenue": 6_000_000_000})
        self.assertEqual(violations, [])


class CrossSourceTests(unittest.TestCase):
    def test_market_caps_disagreeing_by_more_than_twenty_percent(self):
        violations = cross_source_violations(
            {"alpha_vantage": 10_000_000_000, "yahoo": 13_000_000_000},
            field="market_cap", tolerance=0.20)
        self.assertEqual(rules(violations), {"market_cap_provider_disagreement"})

    def test_market_caps_inside_tolerance_agree(self):
        self.assertEqual(cross_source_violations(
            {"alpha_vantage": 10_000_000_000, "yahoo": 10_500_000_000},
            field="market_cap", tolerance=0.20), [])

    def test_prices_disagreeing_by_more_than_five_percent(self):
        violations = cross_source_violations({"alpha_vantage": 100.0, "yahoo": 112.0},
                                             field="price", tolerance=0.05)
        self.assertEqual(rules(violations), {"price_provider_disagreement"})

    def test_a_single_source_cannot_disagree_with_itself(self):
        self.assertEqual(cross_source_violations({"yahoo": 100.0}, field="price", tolerance=0.05), [])


class ScreenTests(unittest.TestCase):
    def test_a_rejected_field_is_removed_not_corrected(self):
        """This module can tell that a number is wrong, never what the right number was."""
        screened, violations = screen({"ticker": "TEST", "profit_margin": 1.4,
                                       "return_on_equity": 0.2})
        self.assertIsNone(screened["profit_margin"])
        self.assertEqual(screened["return_on_equity"], 0.2)
        self.assertEqual(len(violations), 1)

    def test_every_drop_is_recorded_with_the_rule_and_the_value(self):
        screened, _ = screen({"ticker": "TEST", "incremental_margin": 1.282})
        recorded = screened["data_quality_violations"]
        self.assertEqual(recorded[0]["field"], "incremental_margin")
        self.assertEqual(recorded[0]["value"], 1.282)
        self.assertIn("rule", recorded[0])
        self.assertIn("detail", recorded[0])

    def test_a_clean_snapshot_is_untouched_and_carries_no_violation_key(self):
        original = {"ticker": "TEST", "profit_margin": 0.2, "market_cap": 5e9, "forward_pe": 18.0}
        screened, violations = screen(original)
        self.assertEqual(violations, [])
        self.assertNotIn("data_quality_violations", screened)
        self.assertEqual({key: screened[key] for key in original}, original)

    def test_non_numeric_and_missing_values_are_not_violations(self):
        screened, violations = screen({"ticker": "TEST", "profit_margin": None,
                                       "market_cap": "n/a", "piotroski_f": True})
        self.assertEqual(violations, [])
        self.assertNotIn("data_quality_violations", screened)


class LivePayloadTests(unittest.TestCase):
    """Run the rules over the committed production payload."""

    def test_the_published_universe_is_screened_without_mass_rejection(self):
        import json
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "public", "data", "advisor.json")
        if not os.path.exists(path):
            self.skipTest("public/data/advisor.json is not present in this checkout")
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload.get("research", [])
        flagged = {row["ticker"]: field_violations(row) for row in rows}
        flagged = {ticker: items for ticker, items in flagged.items() if items}
        # NEM's 128.2% must be caught, and the rules must not reject a large share of a
        # universe that is mostly fine -- a screen that fires everywhere is not a screen.
        self.assertIn("NEM", flagged)
        self.assertLess(len(flagged), len(rows) * 0.5)


if __name__ == "__main__":
    unittest.main()
