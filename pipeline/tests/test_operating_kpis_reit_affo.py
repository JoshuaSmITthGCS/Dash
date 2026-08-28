import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_reit_affo import extract_affo_per_share


class AffoPerShareTests(unittest.TestCase):
    def test_affo_per_share_simple(self):
        text = "AFFO per share of $1.23 for the quarter, up from $1.15 a year ago."
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 1.23)
        self.assertEqual(detail["status"], "matched")
        self.assertEqual(detail["synonym"], "affo")

    def test_adjusted_funds_from_operations_per_diluted_share(self):
        text = ("Adjusted funds from operations (AFFO) per diluted share of $0.98, "
                "compared to $0.91 in the prior-year period.")
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 0.98)
        self.assertEqual(detail["status"], "matched")
        self.assertEqual(detail["synonym"], "affo")

    def test_core_ffo_per_share(self):
        text = "Core FFO per share was $2.34 for the third quarter."
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 2.34)
        self.assertEqual(detail["status"], "matched")
        self.assertEqual(detail["synonym"], "core_ffo")

    def test_ffo_as_adjusted_per_share(self):
        text = "FFO as adjusted per share increased to $1.50 in the quarter."
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 1.50)
        self.assertEqual(detail["status"], "matched")
        self.assertEqual(detail["synonym"], "ffo_as_adjusted")

    def test_ffo_comma_as_adjusted_per_share(self):
        text = "FFO, as adjusted, per share was $1.05 for the period."
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 1.05)
        self.assertEqual(detail["synonym"], "ffo_as_adjusted")

    def test_plain_unqualified_ffo_per_share_does_not_match(self):
        # Critical negative test: plain "FFO per share" (no AFFO/adjusted/core/as-adjusted
        # qualifier) is the structural figure fundamentals_extended.py already computes, and
        # must NOT be picked up by this extractor.
        text = "FFO per share was $1.05, compared to $0.99 in the prior-year quarter."
        value, detail = extract_affo_per_share(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_no_per_share_metric_at_all_returns_not_found(self):
        text = "Net income for the quarter was $42 million, up from $38 million a year ago."
        value, detail = extract_affo_per_share(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("AFFO per share was $1.23 for the quarter. "
                "For the full year, AFFO per share is expected to be $4.85.")
        value, detail = extract_affo_per_share(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [1.23, 4.85])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: AFFO per share of $1.23. "
                "In the body: AFFO per share was $1.23 for the quarter.")
        value, detail = extract_affo_per_share(text)
        self.assertEqual(value, 1.23)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("AFFO per share trends remained healthy. "
                "Total revenue was $1.23 billion for the quarter.")
        value, detail = extract_affo_per_share(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_dollar_and_share_do_not_false_positive(self):
        # Contains both "per share" and a dollar amount, but never one of the AFFO/Core-FFO/
        # FFO-as-adjusted anchors.
        text = "Diluted earnings per share were $0.55 for the quarter."
        value, detail = extract_affo_per_share(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_affo_per_share("")[1]["status"], "not_found")
        self.assertEqual(extract_affo_per_share(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
