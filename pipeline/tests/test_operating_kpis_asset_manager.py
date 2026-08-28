import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from operating_kpis_asset_manager import extract_assets_under_management, extract_net_flows


class AssetsUnderManagementTests(unittest.TestCase):
    def test_billions_with_parenthetical_aum_gloss(self):
        text = "Assets under management (AUM) of $650 billion as of quarter end."
        value, detail = extract_assets_under_management(text)
        self.assertEqual(value, 650.0)
        self.assertEqual(detail["status"], "matched")

    def test_trillions_are_converted_to_billions(self):
        # Unit-conversion correctness: 1.2 trillion must normalize to 1200.0 billion, not 1.2.
        text = "Total AUM increased to $1.2 trillion during the quarter."
        value, detail = extract_assets_under_management(text)
        self.assertEqual(value, 1200.0)
        self.assertEqual(detail["status"], "matched")

    def test_bare_aum_acronym_phrasing(self):
        text = "AUM was $410.5 billion as of quarter end, up from the prior period."
        value, detail = extract_assets_under_management(text)
        self.assertEqual(value, 410.5)
        self.assertEqual(detail["status"], "matched")

    def test_bare_aum_does_not_match_lowercase_substring(self):
        # "aum" inside "aluminum" must not be mistaken for the AUM acronym.
        text = "Aluminum input costs of $410.5 billion were reported by the industrial segment."
        value, detail = extract_assets_under_management(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_million_magnitude_is_converted_to_fractional_billions(self):
        text = "Assets under management (AUM) of $850 million in the specialty strategy."
        value, _ = extract_assets_under_management(text)
        self.assertEqual(value, 0.85)

    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $42 million, up from $38 million a year ago."
        value, detail = extract_assets_under_management(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_large_dollar_figure_does_not_false_positive(self):
        # Quarterly revenue is a large dollar figure with a magnitude word, but never appears
        # near the AUM anchor phrase, so it must not be mistaken for AUM.
        text = ("Total revenue for the quarter was $2.1 billion, up 8% year over year. "
                "Net income also grew.")
        value, detail = extract_assets_under_management(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        # Firm-wide AUM and a single segment's AUM under near-identical bare-AUM phrasing.
        text = ("Total AUM was $650 billion at quarter-end. "
                "Equity AUM was $210 billion at quarter-end.")
        value, detail = extract_assets_under_management(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [210.0, 650.0])

    def test_the_same_value_repeated_is_not_treated_as_ambiguous(self):
        text = ("Highlights: assets under management (AUM) of $650 billion. "
                "In the body: total AUM of $650 billion as of quarter end.")
        value, detail = extract_assets_under_management(text)
        self.assertEqual(value, 650.0)
        self.assertEqual(detail["status"], "matched")

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Assets under management trends remained healthy this quarter. "
                "Total revenue was $2.1 billion for the period.")
        value, detail = extract_assets_under_management(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_assets_under_management("")[1]["status"], "not_found")
        self.assertEqual(extract_assets_under_management(None)[1]["status"], "not_found")


class NetFlowsTests(unittest.TestCase):
    def test_net_inflows_are_positive(self):
        text = "Net inflows of $12.3 billion for the quarter, led by fixed income."
        value, detail = extract_net_flows(text)
        self.assertEqual(value, 12.3)
        self.assertEqual(detail["status"], "matched")

    def test_net_outflows_are_negative_despite_positive_number_in_text(self):
        # The word "outflows" makes the value negative even though "2.1" itself carries no sign.
        text = "Net outflows of $2.1 billion during the period reflected redemptions."
        value, detail = extract_net_flows(text)
        self.assertEqual(value, -2.1)
        self.assertEqual(detail["status"], "matched")

    def test_parenthesized_negative_net_flows(self):
        text = "Net flows of $(4.2) billion reflected continued client redemptions."
        value, detail = extract_net_flows(text)
        self.assertEqual(value, -4.2)
        self.assertEqual(detail["status"], "matched")

    def test_long_term_net_inflows_phrasing(self):
        text = "Long-term net inflows of $8.5 billion in the quarter."
        value, detail = extract_net_flows(text)
        self.assertEqual(value, 8.5)
        self.assertEqual(detail["status"], "matched")
        self.assertIn("long-term net inflows", detail["matched_phrase"].lower())

    def test_leading_minus_sign_is_not_double_negated_by_outflow_word(self):
        # A leading minus plus the word "outflows" is one negative number, not two negatives
        # canceling out -- same discipline as the comps module's parenthesized-percent case.
        text = "Net outflows of $-2.1 billion were reported for the period."
        value, _ = extract_net_flows(text)
        self.assertEqual(value, -2.1)

    def test_no_disclosure_returns_none(self):
        text = "Net income for the quarter was $500 million, roughly flat year over year."
        value, detail = extract_net_flows(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_unrelated_large_dollar_figure_does_not_false_positive(self):
        text = ("Total revenue for the quarter was $2.1 billion. "
                "Assets under management remained strong.")
        value, detail = extract_net_flows(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_ambiguous_multiple_distinct_values_returns_none(self):
        text = ("Net inflows of $12.3 billion for the quarter. "
                "Net outflows of $2.1 billion in the prior-year quarter.")
        value, detail = extract_net_flows(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "ambiguous_multiple_values")
        self.assertEqual(detail["candidates"], [-2.1, 12.3])

    def test_pattern_does_not_bridge_across_a_sentence_boundary(self):
        text = ("Net flows trends remained healthy this quarter. "
                "Total revenue increased to $2.1 billion for the period.")
        value, detail = extract_net_flows(text)
        self.assertIsNone(value)
        self.assertEqual(detail["status"], "not_found")

    def test_empty_and_none_text(self):
        self.assertEqual(extract_net_flows("")[1]["status"], "not_found")
        self.assertEqual(extract_net_flows(None)[1]["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
