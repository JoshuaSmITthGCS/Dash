import unittest

from pipeline.sec_edgar import parse_form4


FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
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


class Form4ParserTests(unittest.TestCase):
    def test_parse_form4_keeps_open_market_trades_only(self):
        rows = parse_form4(FORM4)
        self.assertEqual(rows, [{
            "code": "P", "side": "purchase", "shares": 100.0, "price": 25.5,
            "value": 2550.0, "acquired_disposed": "A", "date": "2026-07-01",
        }])
