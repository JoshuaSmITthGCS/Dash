import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_saas import (
    extract_annual_recurring_revenue,
    extract_net_revenue_retention_rate,
)


class AnnualRecurringRevenueTests(unittest.TestCase):
    def test_arr_in_millions(self):
        text = "ARR grew 28% to $500 million, up from the prior-year quarter."
        value, detail = extract_annual_recurring_revenue(text)
        self.assertEqual(value, 500.0)
        self.assertEqual(detail["status"], "matched")

    def test_arr_in_billions_is_normalized_to_millions(self):
        text = "Annual recurring revenue (ARR) of $1.25 billion as of the end of the quarter."
        value, detail = extract_annual_recurring_revenue(text)
        self.assertEqual(value, 1250.0)
        self.assertEqual(detail["status"], "matched")

    def test_arr_with_thousands_separator(self):
        text = "Total ARR was $1,250 million, representing 30% growth year over year."
        value, _ = extract_annual_recurring_revenue(text)
        self.assertEqual(value, 1250.0)

    def test_arr_decimal_millions(self):
        text = "The Company ended the quarter with ARR of $340.5 million."
        value, _ = extract_annual_recurring_revenue(text)
        self.assertEqual(value, 340.5)

    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $42 million, up from $38 million a year ago."
        value, detail = extract_annual_recurring_revenue(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_dollar_figure_does_not_false_positive(self):
        # Contains a dollar amount and a scale word, but never the ARR anchor.
        text = "Total revenue was $340.5 million for the quarter, up 22% year over year."
        value, detail = extract_annual_recurring_revenue(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Annual recurring revenue (ARR) was $500 million for the quarter. "
                "For the year-ago quarter, ARR was $390 million.")
        value, detail = extract_annual_recurring_revenue(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [390.0, 500.0])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: ARR of $500 million. "
                "In the body: annual recurring revenue (ARR) of $500 million as of quarter end.")
        value, detail = extract_annual_recurring_revenue(text)
        self.assertEqual(value, 500.0)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Annual recurring revenue continued to grow steadily this quarter. "
                "Total billings were $500 million for the period.")
        value, detail = extract_annual_recurring_revenue(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_annual_recurring_revenue("")[1]["status"], "not_found")
        self.assertEqual(extract_annual_recurring_revenue(None)[1]["status"], "not_found")


class NetRevenueRetentionTests(unittest.TestCase):
    def test_nrr_above_100_percent(self):
        text = "We ended the quarter with a net revenue retention rate of 125%."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertEqual(value, 1.25)
        self.assertEqual(detail["status"], "matched")

    def test_nrr_below_100_percent_is_a_valid_match_not_an_error(self):
        text = "Net revenue retention of 95% reflected continued softness among smaller customers."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertEqual(value, 0.95)
        self.assertEqual(detail["status"], "matched")

    def test_ndr_phrasing(self):
        text = "Net dollar retention (NDR) of 118% for the trailing twelve months."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertEqual(value, 1.18)
        self.assertEqual(detail["status"], "matched")

    def test_dollar_based_net_retention_phrasing(self):
        text = "Dollar-based net retention rate was 112% as of quarter end."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertEqual(value, 1.12)
        self.assertEqual(detail["status"], "matched")

    def test_no_disclosure_returns_none(self):
        text = "Operating margin improved to 22% for the quarter, up from 18% a year ago."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_percent_does_not_false_positive(self):
        # Contains a percentage in the retention-plausible 50-200 range, but never the anchor.
        text = "Gross margin was 78% for the quarter, compared to 75% in the prior year."
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Net revenue retention rate was 125% for enterprise customers. "
                "Net revenue retention rate was 110% for the overall customer base.")
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [1.10, 1.25])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: net revenue retention rate of 125%. "
                "In the body: net revenue retention rate of 125% for the quarter.")
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertEqual(value, 1.25)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Net revenue retention trends remained healthy this quarter. "
                "Operating margin was 22% for the period.")
        value, detail = extract_net_revenue_retention_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_net_revenue_retention_rate("")[1]["status"], "not_found")
        self.assertEqual(extract_net_revenue_retention_rate(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
