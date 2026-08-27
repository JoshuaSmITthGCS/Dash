import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_telecom import extract_postpaid_churn_rate, extract_postpaid_phone_arpu


class PostpaidChurnRateTests(unittest.TestCase):
    def test_simple_churn_of_phrasing(self):
        text = "Postpaid phone churn of 0.80% for the quarter, consistent with prior periods."
        value, detail = extract_postpaid_churn_rate(text)
        self.assertEqual(value, 0.008)
        self.assertEqual(detail["status"], "matched")

    def test_churn_rate_was_phrasing(self):
        text = "Postpaid phone churn rate was 0.85%, up slightly from last quarter."
        value, detail = extract_postpaid_churn_rate(text)
        self.assertEqual(value, 0.0085)
        self.assertEqual(detail["status"], "matched")

    def test_churn_of_without_phone_qualifier(self):
        text = "Postpaid churn of 1.0% reflected continued competitive pressure."
        value, _ = extract_postpaid_churn_rate(text)
        self.assertEqual(value, 0.01)

    def test_branded_postpaid_phone_churn_rate_phrasing(self):
        text = "Branded postpaid phone churn rate of 0.79% was the best in company history."
        value, detail = extract_postpaid_churn_rate(text)
        self.assertEqual(value, 0.0079)
        self.assertIn("branded postpaid phone churn rate", detail["matched_phrase"].lower())

    def test_decrease_verb_is_negative(self):
        text = "Postpaid phone churn decreased 0.05% year over year to a company low."
        value, _ = extract_postpaid_churn_rate(text)
        self.assertEqual(value, -0.0005)

    def test_parenthesized_negative_not_double_negated_by_verb(self):
        text = "Postpaid phone churn improved (0.10)% versus the prior-year quarter."
        value, _ = extract_postpaid_churn_rate(text)
        self.assertEqual(value, -0.001)

    def test_no_disclosure_returns_none(self):
        text = "Total revenue for the quarter was $30.1 billion, up 3% year over year."
        value, detail = extract_postpaid_churn_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_churn_word_and_percent_do_not_false_positive(self):
        # Contains "churn" and a percentage, but never the postpaid churn anchor.
        text = "Subscriber churn across the industry averaged 1.5% this quarter."
        value, detail = extract_postpaid_churn_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Postpaid phone churn was 0.80% for the quarter. "
                "For the full year, postpaid phone churn was 0.95%.")
        value, detail = extract_postpaid_churn_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [0.8, 0.95])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: postpaid phone churn of 0.80%. "
                "In the body: postpaid phone churn rate was 0.80% for the quarter.")
        value, detail = extract_postpaid_churn_rate(text)
        self.assertEqual(value, 0.008)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Postpaid phone churn trends remained healthy. "
                "Total net additions increased 0.80% for the quarter.")
        value, detail = extract_postpaid_churn_rate(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_postpaid_churn_rate("")[1]["status"], "not_found")
        self.assertEqual(extract_postpaid_churn_rate(None)[1]["status"], "not_found")


class PostpaidPhoneArpuTests(unittest.TestCase):
    def test_simple_of_phrasing(self):
        text = "Postpaid phone ARPU of $46.12, up from the prior-year quarter."
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertEqual(value, 46.12)
        self.assertEqual(detail["status"], "matched")

    def test_increased_to_phrasing(self):
        text = "Postpaid ARPU increased to $46.50 driven by higher-value plan mix."
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertEqual(value, 46.50)
        self.assertEqual(detail["status"], "matched")

    def test_decreased_to_phrasing(self):
        text = "Postpaid phone ARPU decreased to $44.75 due to promotional activity."
        value, _ = extract_postpaid_phone_arpu(text)
        self.assertEqual(value, 44.75)

    def test_spelled_out_average_revenue_per_customer_phrasing(self):
        text = "Average revenue per postpaid phone customer of $45.98 for the quarter."
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertEqual(value, 45.98)
        self.assertIn("average revenue per postpaid phone customer", detail["matched_phrase"].lower())

    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $4.2 billion, up from $3.8 billion a year ago."
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_dollar_figure_does_not_false_positive(self):
        # Contains a dollar figure, but never the postpaid ARPU anchor.
        text = "Capital expenditures were $4.5 billion for the quarter, in line with guidance."
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Postpaid phone ARPU of $46.12 for the quarter. "
                "In the prior-year quarter, postpaid phone ARPU was $44.80.")
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [44.80, 46.12])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: postpaid phone ARPU of $46.12. "
                "In the body: postpaid phone ARPU was $46.12 for the quarter.")
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertEqual(value, 46.12)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Postpaid phone ARPU trends remained healthy. "
                "Total service revenue was $46.12 billion for the quarter.")
        value, detail = extract_postpaid_phone_arpu(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_postpaid_phone_arpu("")[1]["status"], "not_found")
        self.assertEqual(extract_postpaid_phone_arpu(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
