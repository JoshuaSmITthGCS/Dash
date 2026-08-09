import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from institutional_ownership import (aggregate_by_cusip, decay, holdings_change,
                                     parse_13f_info_table, score_institutional_ownership)

INFO_TABLE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ACME CORP</nameOfIssuer>
    <cusip>000000001</cusip>
    <value>50000</value>
    <shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>ACME CORP</nameOfIssuer>
    <cusip>000000001</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>500</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>PUT</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>WIDGET INC</nameOfIssuer>
    <cusip>000000002</cusip>
    <value>2000</value>
    <shrsOrPrnAmt><sshPrnamt>200</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


class Parse13FInfoTableTests(unittest.TestCase):
    def test_straight_equity_holdings_are_returned(self):
        holdings = parse_13f_info_table(INFO_TABLE, "manager-a")
        self.assertEqual([h["cusip"] for h in holdings], ["000000001", "000000002"])

    def test_option_positions_are_excluded(self):
        holdings = parse_13f_info_table(INFO_TABLE, "manager-a")
        self.assertTrue(all(h["shares"] != 500 for h in holdings))

    def test_a_document_that_does_not_parse_degrades_to_an_empty_list(self):
        self.assertEqual(parse_13f_info_table("<not closed", "manager-a"), [])


class AggregateByCusipTests(unittest.TestCase):
    def test_holdings_are_grouped_by_cusip_and_manager(self):
        holdings = [
            {"manager_id": "a", "cusip": "X", "shares": 100},
            {"manager_id": "b", "cusip": "X", "shares": 200},
            {"manager_id": "a", "cusip": "Y", "shares": 50},
        ]
        by_cusip = aggregate_by_cusip(holdings)
        self.assertEqual(by_cusip["X"], {"a": 100, "b": 200})
        self.assertEqual(by_cusip["Y"], {"a": 50})


class HoldingsChangeTests(unittest.TestCase):
    def test_a_manager_growing_a_position_more_than_five_percent_counts_as_added(self):
        change = holdings_change({"a": 110}, {"a": 100})
        self.assertEqual(change["managers_added"], ["a"])

    def test_a_new_position_counts_as_added(self):
        change = holdings_change({"a": 100}, {})
        self.assertEqual(change["managers_added"], ["a"])

    def test_an_exited_position_counts_as_dropped(self):
        change = holdings_change({}, {"a": 100})
        self.assertEqual(change["managers_dropped"], ["a"])

    def test_a_small_move_counts_as_unchanged(self):
        change = holdings_change({"a": 101}, {"a": 100})
        self.assertEqual(change["managers_unchanged"], ["a"])

    def test_share_change_pct_is_the_aggregate_across_all_managers(self):
        change = holdings_change({"a": 150, "b": 50}, {"a": 100, "b": 100})
        self.assertAlmostEqual(change["share_change_pct"], 0.0, places=4)


class ScoreInstitutionalOwnershipTests(unittest.TestCase):
    def test_no_data_scores_zero_and_is_marked_unavailable(self):
        points, detail = score_institutional_ownership(None)
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_a_single_manager_adding_is_not_corroborated_and_scores_zero(self):
        change = holdings_change({"a": 200}, {"a": 100})
        points, detail = score_institutional_ownership(change, config={"min_managers": 2})
        self.assertEqual(points, 0.0)
        self.assertIn("not corroborated", detail["reason"])

    def test_multiple_managers_adding_scores_positive(self):
        change = holdings_change({"a": 200, "b": 200, "c": 100}, {"a": 100, "b": 100, "c": 100})
        points, detail = score_institutional_ownership(change, config={"min_managers": 2})
        self.assertGreater(points, 0.0)
        self.assertEqual(detail["managers_added"], 2)

    def test_multiple_managers_cutting_scores_negative(self):
        change = holdings_change({"a": 0, "b": 0, "c": 100}, {"a": 100, "b": 100, "c": 100})
        points, detail = score_institutional_ownership(change, config={"min_managers": 2})
        self.assertLess(points, 0.0)

    def test_points_never_exceed_configured_caps(self):
        change = holdings_change({"a": 999, "b": 999}, {"a": 1, "b": 1})
        points, _ = score_institutional_ownership(
            change, config={"min_managers": 2, "max_points": 3.0, "max_penalty": 2.0})
        self.assertLessEqual(points, 3.0)
        self.assertGreaterEqual(points, -2.0)


class DecayTests(unittest.TestCase):
    def test_a_fresh_filing_scores_near_full_weight(self):
        self.assertGreater(decay(0), 0.95)

    def test_decay_is_monotonically_decreasing_with_age(self):
        self.assertGreater(decay(10), decay(45))
        self.assertGreater(decay(45), decay(90))

    def test_a_filing_past_max_age_scores_zero(self):
        self.assertEqual(decay(136, max_age=135), 0.0)

    def test_a_missing_or_negative_age_scores_zero_rather_than_guessing(self):
        self.assertEqual(decay(None), 0.0)
        self.assertEqual(decay(-1), 0.0)


class ScoreInstitutionalOwnershipDecayTests(unittest.TestCase):
    def test_a_stale_filing_scores_less_than_a_fresh_one(self):
        change = holdings_change({"a": 200, "b": 200}, {"a": 100, "b": 100})
        fresh, _ = score_institutional_ownership(change, days_since_filed=1, config={"min_managers": 2})
        stale, _ = score_institutional_ownership(change, days_since_filed=90, config={"min_managers": 2})
        self.assertGreater(fresh, stale)
        self.assertGreater(stale, 0.0)

    def test_a_filing_past_max_age_scores_zero_and_says_why(self):
        change = holdings_change({"a": 200, "b": 200}, {"a": 100, "b": 100})
        points, detail = score_institutional_ownership(
            change, days_since_filed=200, config={"min_managers": 2, "max_age_days": 135})
        self.assertEqual(points, 0.0)
        self.assertIn("stale", detail["reason"])

    def test_no_days_since_filed_means_full_weight_not_zero(self):
        change = holdings_change({"a": 200, "b": 200}, {"a": 100, "b": 100})
        undecayed, _ = score_institutional_ownership(change, config={"min_managers": 2})
        fresh, _ = score_institutional_ownership(change, days_since_filed=0, config={"min_managers": 2})
        self.assertAlmostEqual(undecayed, fresh, places=1)


if __name__ == "__main__":
    unittest.main()
