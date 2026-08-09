import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from geographic_exposure import geographic_revenue_shares, score_geographic_concentration

CONCENTRATED = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c-total">
    <entity><identifier>1</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-us">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">country:US</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-cn">
    <entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">country:CN</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="c-total" unitRef="usd" decimals="0">1000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-us" unitRef="usd" decimals="0">400</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-cn" unitRef="usd" decimals="0">600</us-gaap:Revenues>
</xbrl>"""

# Total tagged, no geographic band at all - the ordinary case, must abstain rather than
# treat "no bands" as "no foreign risk".
TOTAL_ONLY = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026">
  <context id="c-total"><entity><identifier>1</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
  <us-gaap:Revenues contextRef="c-total" unitRef="usd" decimals="0">1000</us-gaap:Revenues>
</xbrl>"""


class GeographicRevenueSharesTests(unittest.TestCase):
    def test_shares_are_computed_against_the_undimensioned_total(self):
        shares = geographic_revenue_shares(CONCENTRATED)
        self.assertEqual(shares, {"us": 0.4, "cn": 0.6})

    def test_a_total_with_no_geographic_band_abstains_rather_than_guesses(self):
        self.assertEqual(geographic_revenue_shares(TOTAL_ONLY), {})

    def test_no_data_at_all_abstains(self):
        self.assertEqual(geographic_revenue_shares("<xbrl></xbrl>"), {})


class ScoreGeographicConcentrationTests(unittest.TestCase):
    def test_no_shares_scores_zero_and_is_marked_unavailable(self):
        points, detail = score_geographic_concentration({})
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_diversified_domestic_only_revenue_scores_zero(self):
        points, detail = score_geographic_concentration({"us": 1.0})
        self.assertEqual(points, 0.0)
        self.assertTrue(detail["available"])

    def test_severe_single_country_concentration_earns_the_full_penalty(self):
        points, detail = score_geographic_concentration(
            {"us": 0.4, "cn": 0.6}, config={"severe_share": 0.5, "max_penalty": 2.0})
        self.assertEqual(points, -2.0)
        self.assertEqual(detail["largest_foreign_geography"], "cn")

    def test_broad_international_diversification_with_no_single_country_over_threshold_scores_zero(self):
        # 70% non-domestic in total, but split across three countries with none dominant -
        # this is the case the module explicitly does not penalize.
        points, detail = score_geographic_concentration(
            {"us": 0.3, "cn": 0.25, "de": 0.25, "jp": 0.2},
            config={"warning_share": 0.3, "severe_share": 0.5})
        self.assertEqual(points, 0.0)

    def test_points_are_never_positive(self):
        for shares in ({}, {"us": 1.0}, {"us": 0.1, "cn": 0.9}):
            points, _ = score_geographic_concentration(shares)
            self.assertLessEqual(points, 0.0)


if __name__ == "__main__":
    unittest.main()
