import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from xbrl_dimensions import dimensional_facts, facts_matching, facts_on_axis, undimensioned_facts

# A standalone XBRL instance: one undimensioned total plus one context carrying the two
# axes customer-concentration disclosures actually use. This is the shape `companyfacts`
# collapses - it would report only the 4200000000 total, or nothing, and give no way to
# tell the two apart from the response alone.
PLAIN_INSTANCE = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c-total">
    <entity><identifier>0000320193</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-concentrated">
    <entity>
      <identifier>0000320193</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByTypeAxis">us-gaap:CustomerConcentrationRiskMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:ConcentrationRiskByBenchmarkAxis">us-gaap:RevenueFromContractWithCustomerMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="c-total" unitRef="usd" decimals="0">4200000000</us-gaap:Revenues>
  <us-gaap:ConcentrationRiskPercentage1 contextRef="c-concentrated" unitRef="pure" decimals="2">0.23</us-gaap:ConcentrationRiskPercentage1>
</xbrl>"""

# Inline XBRL: the shape a modern 10-K's *_htm.xml/primary document actually is. Backlog
# reported only in SatisfactionPeriodAxis bands, with no undimensioned total tag at all -
# the case where company_concept legitimately has nothing to return.
INLINE_XBRL = """<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <ix:header>
    <ix:resources>
      <xbrli:context id="c-near" xmlns:xbrli="http://www.xbrl.org/2003/instance">
        <xbrli:entity>
          <xbrli:identifier>0000320193</xbrli:identifier>
          <xbrli:segment>
            <xbrldi:explicitMember dimension="us-gaap:SatisfactionPeriodAxis">us-gaap:WithinOneYearMember</xbrldi:explicitMember>
          </xbrli:segment>
        </xbrli:entity>
        <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
      </xbrli:context>
      <xbrli:context id="c-far" xmlns:xbrli="http://www.xbrl.org/2003/instance">
        <xbrli:entity>
          <xbrli:identifier>0000320193</xbrli:identifier>
          <xbrli:segment>
            <xbrldi:explicitMember dimension="us-gaap:SatisfactionPeriodAxis">us-gaap:MoreThanOneYearMember</xbrldi:explicitMember>
          </xbrli:segment>
        </xbrli:entity>
        <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
      </xbrli:context>
      <xbrli:context id="c-geo-us" xmlns:xbrli="http://www.xbrl.org/2003/instance">
        <xbrli:entity>
          <xbrli:identifier>0000320193</xbrli:identifier>
          <xbrli:segment>
            <xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">country:US</xbrldi:explicitMember>
          </xbrli:segment>
        </xbrli:entity>
        <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
      </xbrli:context>
    </ix:resources>
  </ix:header>
  <body>
    <span><ix:nonFraction name="us-gaap:RevenueRemainingPerformanceObligation" contextRef="c-near" unitRef="usd" scale="6" decimals="-6">1200</ix:nonFraction></span>
    <span><ix:nonFraction name="us-gaap:RevenueRemainingPerformanceObligation" contextRef="c-far" unitRef="usd" scale="6" decimals="-6" sign="-">300</ix:nonFraction></span>
    <span><ix:nonFraction name="srt:RevenueRemainingPerformanceObligation" contextRef="c-far" unitRef="usd" decimals="0">99999999</ix:nonFraction></span>
    <span><ix:nonFraction name="us-gaap:Revenues" contextRef="c-geo-us" unitRef="usd" decimals="0">2500000000</ix:nonFraction></span>
  </body>
</html>"""


class DimensionalFactsFromPlainInstanceTests(unittest.TestCase):
    def test_the_undimensioned_total_and_the_dimensioned_percentage_are_both_returned(self):
        revenue = dimensional_facts(PLAIN_INSTANCE, "Revenues")
        concentration = dimensional_facts(PLAIN_INSTANCE, "ConcentrationRiskPercentage1")
        self.assertEqual([f["value"] for f in revenue], [4200000000.0])
        self.assertEqual(revenue[0]["dimensions"], {})
        self.assertEqual([f["value"] for f in concentration], [0.23])

    def test_the_percentage_carries_both_axes_it_was_reported_against(self):
        concentration = dimensional_facts(PLAIN_INSTANCE, "ConcentrationRiskPercentage1")
        self.assertEqual(concentration[0]["dimensions"], {
            "concentrationriskbytypeaxis": "customerconcentrationriskmember",
            "concentrationriskbybenchmarkaxis": "revenuefromcontractwithcustomermember",
        })

    def test_facts_matching_filters_by_axis_member_regardless_of_case_or_prefix(self):
        concentration = dimensional_facts(PLAIN_INSTANCE, "ConcentrationRiskPercentage1")
        matched = facts_matching(concentration, {
            "ConcentrationRiskByTypeAxis": "us-gaap:CustomerConcentrationRiskMember"})
        self.assertEqual(len(matched), 1)
        unmatched = facts_matching(concentration, {"ConcentrationRiskByTypeAxis": "SomeOtherMember"})
        self.assertEqual(unmatched, [])

    def test_undimensioned_facts_excludes_the_segmented_context(self):
        concentration = dimensional_facts(PLAIN_INSTANCE, "ConcentrationRiskPercentage1")
        self.assertEqual(undimensioned_facts(concentration), [])


class DimensionalFactsFromInlineXbrlTests(unittest.TestCase):
    """The case the SEC's companyconcept API cannot serve at all: a concept with no
    undimensioned total, only SatisfactionPeriodAxis bands that must be summed."""

    def test_no_undimensioned_backlog_total_exists(self):
        facts = dimensional_facts(INLINE_XBRL, "RevenueRemainingPerformanceObligation")
        self.assertEqual(undimensioned_facts(facts), [])

    def test_the_taxonomy_prefix_disambiguates_a_same_named_concept_in_another_taxonomy(self):
        facts = dimensional_facts(INLINE_XBRL, "RevenueRemainingPerformanceObligation", taxonomy="us-gaap")
        # Only the two us-gaap: facts, not the srt: one worth 99999999.
        self.assertEqual(sorted(f["value"] for f in facts), [-300000000.0, 1200000000.0])

    def test_scale_and_sign_attributes_are_applied(self):
        facts = dimensional_facts(INLINE_XBRL, "RevenueRemainingPerformanceObligation")
        near = facts_matching(facts, {"SatisfactionPeriodAxis": "WithinOneYearMember"})
        far = facts_matching(facts, {"SatisfactionPeriodAxis": "MoreThanOneYearMember"})
        self.assertEqual(near[0]["value"], 1200000000.0)
        self.assertEqual(far[0]["value"], -300000000.0)

    def test_facts_on_axis_groups_bands_by_member_for_summing(self):
        facts = dimensional_facts(INLINE_XBRL, "RevenueRemainingPerformanceObligation")
        by_member = facts_on_axis(facts, "SatisfactionPeriodAxis")
        self.assertEqual(set(by_member), {"withinoneyearmember", "morethanoneyearmember"})

    def test_geographic_revenue_is_recovered_from_an_inline_document(self):
        facts = dimensional_facts(INLINE_XBRL, "Revenues")
        us_revenue = facts_matching(facts, {"StatementGeographicalAxis": "country:US"})
        self.assertEqual(us_revenue[0]["value"], 2500000000.0)


class DimensionalFactsOnMalformedDocumentTests(unittest.TestCase):
    def test_a_document_that_does_not_parse_as_xml_degrades_to_an_empty_list(self):
        self.assertEqual(dimensional_facts("<html><body>not closed", "Revenues"), [])

    def test_a_missing_concept_degrades_to_an_empty_list(self):
        self.assertEqual(dimensional_facts(PLAIN_INSTANCE, "NoSuchConcept"), [])


if __name__ == "__main__":
    unittest.main()
