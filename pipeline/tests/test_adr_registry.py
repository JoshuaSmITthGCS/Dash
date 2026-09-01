"""adr_registry.py: the ADR/ordinary-share reconciliation gate (round-12 valuation audit).

Every entry currently ships unverified (see pipeline/config/adr_listings.json) -- these tests
assert the *policy* (fail closed on an unverified ratio, pass through an unknown ticker,
convert correctly once verified), not any specific ticker's real-world ratio.
"""
import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import adr_registry


class AdrRegistryTests(unittest.TestCase):
    def setUp(self):
        self._original = adr_registry._REGISTRY

    def tearDown(self):
        adr_registry._REGISTRY = self._original

    def test_unregistered_ticker_is_not_an_adr(self):
        adr_registry._REGISTRY = {}
        self.assertFalse(adr_registry.is_unreconciled_adr("AAPL"))
        self.assertIsNone(adr_registry.verified_ads_ratio("AAPL"))
        self.assertEqual(adr_registry.ads_equivalent_shares("AAPL", 1000.0), 1000.0)

    def test_known_adr_with_no_verified_ratio_is_unreconciled(self):
        adr_registry._REGISTRY = {"TSM": {"is_adr": True, "adr_ratio": None, "verified": False}}
        self.assertTrue(adr_registry.is_unreconciled_adr("TSM"))
        self.assertIsNone(adr_registry.verified_ads_ratio("TSM"))
        # Must never fall back to treating the ordinary-share count as ADS-equivalent.
        self.assertIsNone(adr_registry.ads_equivalent_shares("TSM", 5000.0))

    def test_verified_ratio_converts_ordinary_shares(self):
        adr_registry._REGISTRY = {"FAKE": {"is_adr": True, "adr_ratio": 5, "verified": True}}
        self.assertFalse(adr_registry.is_unreconciled_adr("FAKE"))
        self.assertEqual(adr_registry.verified_ads_ratio("FAKE"), 5)
        self.assertEqual(adr_registry.ads_equivalent_shares("FAKE", 5000.0), 1000.0)

    def test_lookup_is_case_insensitive(self):
        adr_registry._REGISTRY = {"TSM": {"is_adr": True, "adr_ratio": None, "verified": False}}
        self.assertTrue(adr_registry.is_unreconciled_adr("tsm"))

    def test_config_file_ships_with_every_entry_unverified(self):
        """A ratio must never enter production with false confidence; see the config file's
        own _verification_note for why. This guards against someone flipping verified=true
        without also filling in a citable source.
        """
        adr_registry._REGISTRY = None  # force a real load from pipeline/config/adr_listings.json
        registry = adr_registry._registry()
        self.assertTrue(registry, "expected at least the confirmed-foreign-issuer tickers")
        for ticker, entry in registry.items():
            with self.subTest(ticker=ticker):
                if entry.get("verified"):
                    self.assertIsNotNone(entry.get("source"),
                                         "a verified ratio must cite a source")
                else:
                    self.assertIsNone(entry.get("adr_ratio"),
                                      "an unverified entry must not carry a ratio someone "
                                      "could accidentally trust")


if __name__ == "__main__":
    unittest.main()
