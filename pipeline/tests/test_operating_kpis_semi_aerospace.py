import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_semi_aerospace import extract_book_to_bill_ratio


class BookToBillTests(unittest.TestCase):
    def test_plain_decimal(self):
        text = "The Company's book-to-bill ratio of 1.15 for the quarter reflected strong order intake."
        value, detail = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 1.15)
        self.assertEqual(detail["status"], "matched")
        self.assertIn("book-to-bill ratio", detail["matched_phrase"].lower())

    def test_trailing_x_notation(self):
        text = "Semiconductor equipment book-to-bill of 0.92x signals softer near-term demand."
        value, detail = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 0.92)
        self.assertEqual(detail["status"], "matched")

    def test_colon_one_notation(self):
        text = "The Company's book-to-bill ratio for the quarter was 1.05:1, up from the prior period."
        value, detail = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 1.05)
        self.assertEqual(detail["status"], "matched")

    def test_approximately_phrasing(self):
        text = "Industry-wide, the book-to-bill ratio was approximately 1.1 for the period."
        value, _ = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 1.1)

    def test_no_disclosure_returns_none(self):
        # Typical fabless-chipmaker release: revenue and margin, never a book-to-bill ratio.
        text = ("Revenue for the quarter was $9.4 billion, up 12% year over year, with gross "
               "margin of 74.5%.")
        value, detail = extract_book_to_bill_ratio(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("The semiconductor systems segment's book-to-bill ratio was 1.15 for the "
               "quarter. For the trailing twelve months, the Company's book-to-bill ratio "
               "was 1.32.")
        value, detail = extract_book_to_bill_ratio(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [1.15, 1.32])

    def test_unrelated_decimal_nearby_does_not_false_positive(self):
        # A dollar figure precedes the real book-to-bill mention -- extraction must pick the
        # ratio, not misread the unrelated revenue figure.
        text = ("Total bookings of $1.42 billion resulted in a book-to-bill ratio of 1.15 for "
               "the quarter.")
        value, detail = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 1.15)
        self.assertEqual(detail["status"], "matched")

    def test_dollar_figure_immediately_after_linking_word_is_not_misread(self):
        # "of $1.15 billion" directly follows the anchor's linking word "of" -- must not be
        # misread as a book-to-bill ratio of 1.15, since it is a dollar amount, not a ratio.
        text = "The book-to-bill ratio of $1.15 billion in bookings was strong across the segment."
        value, detail = extract_book_to_bill_ratio(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Book-to-bill trends remained healthy across the segment. Total orders "
               "increased 1.15 times versus last year.")
        value, detail = extract_book_to_bill_ratio(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: book-to-bill ratio of 1.15. In the body: the Company's "
               "book-to-bill ratio was 1.15 for the quarter.")
        value, detail = extract_book_to_bill_ratio(text)
        self.assertEqual(value, 1.15)
        self.assertEqual(detail["status"], "matched")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_book_to_bill_ratio("")[1]["status"], "not_found")
        self.assertEqual(extract_book_to_bill_ratio(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
