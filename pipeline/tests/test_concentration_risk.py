import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from concentration_risk import customer_concentration_percentages, score_concentration_risk

# One customer at 35% (severe), qualified by both the type and benchmark axes real filings
# use; a second, unrelated concentration fact (credit risk, not customer) on the same base
# concept, which must NOT be picked up.
FILING = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c-customer">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByTypeAxis">us-gaap:CustomerConcentrationRiskMember</xbrldi:explicitMember>
      <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByBenchmarkAxis">us-gaap:RevenueFromContractWithCustomerMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-credit">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByTypeAxis">us-gaap:CreditConcentrationRiskMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:ConcentrationRiskPercentage1 contextRef="c-customer" unitRef="pure" decimals="2">0.35</us-gaap:ConcentrationRiskPercentage1>
  <us-gaap:ConcentrationRiskPercentage1 contextRef="c-credit" unitRef="pure" decimals="2">0.90</us-gaap:ConcentrationRiskPercentage1>
</xbrl>"""


class CustomerConcentrationPercentagesTests(unittest.TestCase):
    def test_only_the_customer_typed_fact_is_returned(self):
        self.assertEqual(customer_concentration_percentages(FILING), [0.35])

    def test_no_matching_facts_is_an_empty_list_not_an_error(self):
        self.assertEqual(customer_concentration_percentages("<xbrl></xbrl>"), [])


class ScoreConcentrationRiskTests(unittest.TestCase):
    def test_no_disclosure_scores_zero_and_is_marked_unavailable(self):
        points, detail = score_concentration_risk([])
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_below_warning_share_scores_zero(self):
        points, _ = score_concentration_risk([0.10])
        self.assertEqual(points, 0.0)

    def test_warning_share_earns_half_the_max_penalty(self):
        points, detail = score_concentration_risk([0.20], config={"max_penalty": 3.0})
        self.assertEqual(points, -1.5)
        self.assertIn("20%", detail["notes"][0])

    def test_severe_share_earns_the_full_penalty(self):
        points, _ = score_concentration_risk([0.35], config={"max_penalty": 3.0})
        self.assertEqual(points, -3.0)

    def test_a_second_smaller_named_customer_does_not_deepen_the_penalty(self):
        one_customer, _ = score_concentration_risk([0.35])
        two_customers, _ = score_concentration_risk([0.35, 0.12])
        self.assertEqual(one_customer, two_customers)

    def test_points_are_never_positive(self):
        for percentages in ([], [0.05], [0.10], [0.50], [0.99]):
            points, _ = score_concentration_risk(percentages)
            self.assertLessEqual(points, 0.0)


if __name__ == "__main__":
    unittest.main()
