import unittest

from pipeline.sec_edgar import parse_form4, parse_owner
import xml.etree.ElementTree as ET


FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0000012345</rptOwnerCik>
      <rptOwnerName>Doe Jane</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Financial Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-01</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>25.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>500</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

ANONYMOUS_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-01</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10</value></transactionShares>
        <transactionPricePerShare><value>5</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


class Form4ParserTests(unittest.TestCase):
    def test_parse_form4_keeps_open_market_trades_only(self):
        rows = parse_form4(FORM4)
        self.assertEqual(rows, [{
            "code": "P", "side": "purchase", "shares": 100.0, "price": 25.5,
            "value": 2550.0, "acquired_disposed": "A", "date": "2026-07-01",
            "owner_name": "Doe Jane", "owner_cik": "0000012345",
            "roles": ["director", "officer"], "officer_title": "Chief Financial Officer",
        }])

    def test_owner_identity_and_roles_are_attached_to_every_transaction(self):
        # Identity is what makes the routine-versus-opportunistic split possible: the
        # classifier has to know whether this same person trades every July.
        row = parse_form4(FORM4)[0]
        self.assertEqual(row["owner_cik"], "0000012345")
        self.assertIn("director", row["roles"])
        self.assertNotIn("ten_percent_owner", row["roles"])

    def test_missing_reporting_owner_block_degrades_to_nulls(self):
        row = parse_form4(ANONYMOUS_FORM4)[0]
        self.assertEqual(row["side"], "sale")
        self.assertIsNone(row["owner_name"])
        self.assertEqual(row["roles"], [])

    def test_parse_owner_reads_relationship_flags(self):
        owner = parse_owner(ET.fromstring(FORM4))
        self.assertEqual(owner["owner_name"], "Doe Jane")
        self.assertEqual(owner["officer_title"], "Chief Financial Officer")


if __name__ == "__main__":
    unittest.main()
