import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis import extract_comparable_sales_growth


class ComparableSalesTests(unittest.TestCase):
    def test_simple_increase(self):
        text = "Comparable store sales increased 3.2% for the quarter, driven by higher traffic."
        value, detail = extract_comparable_sales_growth(text)
        self.assertEqual(value, 0.032)
        self.assertEqual(detail["status"], "matched")

    def test_decrease_by_verb(self):
        text = "Same-store sales decreased 1.3% compared to the prior-year quarter."
        value, detail = extract_comparable_sales_growth(text)
        self.assertEqual(value, -0.013)

    def test_decrease_by_parentheses_not_double_negated_by_the_verb(self):
        # "were down" + "(2.1)%" is one negative number, not two.
        text = "Comparable sales were down (2.1)% for the period."
        value, _ = extract_comparable_sales_growth(text)
        self.assertEqual(value, -0.021)

    def test_grew_and_rose_are_positive(self):
        self.assertEqual(extract_comparable_sales_growth(
            "Comparable sales grew 4.5% year over year.")[0], 0.045)
        self.assertEqual(extract_comparable_sales_growth(
            "Same store sales rose 6% in the quarter.")[0], 0.06)

    def test_restaurant_phrasing(self):
        text = "Comparable restaurant sales increased 5.0% during the thirteen weeks ended March 30."
        value, detail = extract_comparable_sales_growth(text)
        self.assertEqual(value, 0.05)
        self.assertIn("comparable restaurant sales", detail["matched_phrase"].lower())

    def test_of_phrasing_without_a_direction_verb(self):
        text = "The Company reported comparable sales of 4.5% for the third quarter."
        value, _ = extract_comparable_sales_growth(text)
        self.assertEqual(value, 0.045)

    def test_leading_minus_sign(self):
        text = "Same-store sales of -2.5% reflected continued softness in the category."
        value, _ = extract_comparable_sales_growth(text)
        self.assertEqual(value, -0.025)

    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $42 million, up from $38 million a year ago."
        value, detail = extract_comparable_sales_growth(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_sales_and_percent_do_not_false_positive(self):
        # Contains both "sales" and a percentage, but never the comparable/same-store anchor.
        text = "E-commerce sales grew to 15% of total revenue this quarter."
        value, detail = extract_comparable_sales_growth(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Comparable store sales increased 3.2% for the quarter. "
                "For the fiscal year to date, comparable store sales increased 4.1%.")
        value, detail = extract_comparable_sales_growth(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [3.2, 4.1])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        # A headline bullet and the body both stating the identical figure is one fact
        # mentioned twice, not two candidate facts.
        text = ("Highlights: comparable sales increased 3.2%. "
                "In the body: comparable store sales increased 3.2% for the quarter.")
        value, detail = extract_comparable_sales_growth(text)
        self.assertEqual(value, 0.032)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Comparable store sales trends remained healthy. "
                "Total revenue increased 3.2% for the quarter.")
        value, detail = extract_comparable_sales_growth(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_comparable_sales_growth("")[1]["status"], "not_found")
        self.assertEqual(extract_comparable_sales_growth(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
