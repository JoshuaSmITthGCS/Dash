import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_factors import build_factor_payload, parse_monthly_csv


FIVE = """Description\n,Mkt-RF,SMB,HML,RMW,CMA,RF\n202401,1.00,2.00,3.00,4.00,5.00,0.40\n202402,-1.00,1.00,2.00,3.00,4.00,0.30\n Annual Factors: January-December\n2024,1,2,3,4,5,6\n"""
MOMENTUM = """Description\n,Mom\n202401,6.00\n202402,7.00\n Annual Factors:\n2024,8.00\n"""


class FactorFetchTests(unittest.TestCase):
    def test_parses_only_monthly_percent_returns_as_decimals(self):
        parsed = parse_monthly_csv(FIVE, ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
        self.assertEqual(list(parsed), ["2024-01", "2024-02"])
        self.assertEqual(parsed["2024-01"]["Mkt-RF"], 0.01)

    def test_merges_five_factors_with_momentum(self):
        payload = build_factor_payload(FIVE, MOMENTUM, generated_at="2026-08-05T00:00:00+00:00")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["observations"][0]["momentum"], 0.06)
        self.assertEqual(payload["observations"][1]["risk_free"], 0.003)


if __name__ == "__main__":
    unittest.main()
