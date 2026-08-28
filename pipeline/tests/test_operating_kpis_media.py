import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_media import extract_daily_active_users, extract_monthly_active_users


class MonthlyActiveUsersTests(unittest.TestCase):
    def test_mau_in_millions_anchor_first_with_of(self):
        value, detail = extract_monthly_active_users("MAU of 450 million for the quarter.")
        self.assertEqual(value, 450.0)
        self.assertEqual(detail["status"], "matched")

    def test_mau_in_billions_number_first_unit_conversion(self):
        text = "The Company reported 3.07 billion monthly active users (MAUs) as of quarter end."
        value, detail = extract_monthly_active_users(text)
        self.assertEqual(value, 3070.0)
        self.assertEqual(detail["status"], "matched")
        self.assertIn("monthly active users", detail["matched_phrase"].lower())

    def test_mau_increased_to_phrasing(self):
        text = "Monthly active users increased to 82 million during the quarter."
        value, _ = extract_monthly_active_users(text)
        self.assertEqual(value, 82.0)

    def test_map_terminology_is_a_mau_synonym(self):
        text = "Family Monthly Active People (MAP) of 3.82 billion for December 2025."
        value, detail = extract_monthly_active_users(text)
        self.assertEqual(value, 3820.0)
        self.assertEqual(detail["status"], "matched")

    def test_map_does_not_leak_into_dau_extraction(self):
        text = "Family Monthly Active People (MAP) of 3.82 billion for December 2025."
        value, detail = extract_daily_active_users(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")


class DailyActiveUsersTests(unittest.TestCase):
    def test_dau_in_millions_anchor_first_with_of(self):
        text = "DAU of 197 million for the quarter, consistent with prior guidance."
        value, detail = extract_daily_active_users(text)
        self.assertEqual(value, 197.0)
        self.assertEqual(detail["status"], "matched")

    def test_dau_full_phrase_in_billions(self):
        text = "Average daily active users of 3.35 billion for December 2025."
        value, _ = extract_daily_active_users(text)
        self.assertEqual(value, 3350.0)

    def test_dau_increased_percent_to_phrasing(self):
        text = "Daily active users (DAUs) increased 5% to 210 million in the quarter."
        value, detail = extract_daily_active_users(text)
        self.assertEqual(value, 210.0)
        self.assertEqual(detail["status"], "matched")

    def test_dap_terminology_is_a_dau_synonym(self):
        text = "Family Daily Active People (DAP) of 3.35 billion for December 2025."
        value, detail = extract_daily_active_users(text)
        self.assertEqual(value, 3350.0)
        self.assertEqual(detail["status"], "matched")

    def test_dap_does_not_leak_into_mau_extraction(self):
        text = "Family Daily Active People (DAP) of 3.35 billion for December 2025."
        value, detail = extract_monthly_active_users(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")


class BothMetricsFromOneMetaStyleDocumentTests(unittest.TestCase):
    def test_dap_and_map_extracted_independently_from_the_same_text(self):
        text = ("Family Daily Active People (DAP) of 3.35 billion and Family Monthly Active "
                "People (MAP) of 3.82 billion on average for December 2025.")
        dau_value, dau_detail = extract_daily_active_users(text)
        mau_value, mau_detail = extract_monthly_active_users(text)
        self.assertEqual(dau_value, 3350.0)
        self.assertEqual(mau_value, 3820.0)
        self.assertEqual(dau_detail["status"], "matched")
        self.assertEqual(mau_detail["status"], "matched")


class NotFoundTests(unittest.TestCase):
    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $42 million, up from $38 million a year ago."
        mau_value, mau_detail = extract_monthly_active_users(text)
        dau_value, dau_detail = extract_daily_active_users(text)
        self.assertIsNone(mau_value)
        self.assertIsNone(dau_value)
        self.assertEqual(mau_detail["status"], "not_found")
        self.assertEqual(dau_detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_monthly_active_users("")[1]["status"], "not_found")
        self.assertEqual(extract_monthly_active_users(None)[1]["status"], "not_found")
        self.assertEqual(extract_daily_active_users("")[1]["status"], "not_found")
        self.assertEqual(extract_daily_active_users(None)[1]["status"], "not_found")


class AmbiguousTests(unittest.TestCase):
    def test_ambiguous_multiple_distinct_mau_values_returns_none(self):
        text = ("Monthly active users increased to 82 million for the quarter. "
                "For the prior-year quarter, monthly active users were 76 million.")
        value, detail = extract_monthly_active_users(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [76.0, 82.0])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: MAU of 450 million. "
                "In the body: monthly active users increased to 450 million during the quarter.")
        value, detail = extract_monthly_active_users(text)
        self.assertEqual(value, 450.0)
        self.assertEqual(detail["status"], "matched")


class FalsePositiveGuardTests(unittest.TestCase):
    def test_unrelated_revenue_figure_does_not_false_positive_as_a_user_count(self):
        # Contains both a "million"-scaled figure and the anchor phrase, but the anchor is never
        # connected to a number by a recognized connective -- must not fabricate a pairing.
        text = "Revenue was $410 million for the quarter. The Company does not disclose monthly active users for this segment."
        value, detail = extract_monthly_active_users(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_revenue_in_millions_is_ignored_while_the_real_mau_figure_is_still_found(self):
        text = ("Total revenue increased 12% to $410 million for the quarter. "
                "Monthly active users increased to 82 million during the same period.")
        value, detail = extract_monthly_active_users(text)
        self.assertEqual(value, 82.0)
        self.assertEqual(detail["status"], "matched")


class SentenceBoundaryTests(unittest.TestCase):
    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Monthly active users trends remained healthy this quarter. "
                "Total revenue reached $3.07 billion for the same period.")
        value, detail = extract_monthly_active_users(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
