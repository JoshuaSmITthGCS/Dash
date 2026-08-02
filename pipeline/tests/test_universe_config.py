"""Guards on the configured universes.

These catch the failure modes that only show up in production: a peer group too thin to
rank, a fund pointing at an index proxy nobody downloads, a duplicate ticker, or a screen
payload that quietly grows until the browser is downloading megabytes of unread fields.
"""

import collections
import json
import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import fetch_advisor
from common import load_json
from fetch_etfs import MIN_PEER_GROUP_SIZE, peer_group_for

UNIVERSE = load_json("universe.json", from_config=True) or {}
ETFS = UNIVERSE.get("etfs", {})
ADVISOR = load_json("advisor_universe.json", from_config=True) or {}
SYMBOLS = ADVISOR.get("symbols", [])


class EtfUniverseTests(unittest.TestCase):
    def test_every_peer_group_can_actually_be_ranked(self):
        # A group below the threshold falls back to cross-asset-class pooling, which is the
        # exact comparison the peer-group ranking exists to prevent. Config should not put
        # a fund in that position.
        counts = collections.Counter(peer_group_for(meta) for meta in ETFS.values())
        thin = {group: count for group, count in counts.items()
                if count < MIN_PEER_GROUP_SIZE}
        self.assertEqual(thin, {}, f"peer groups too small to rank within: {thin}")

    def test_the_batch_has_enough_funds_for_percentiles_to_mean_something(self):
        self.assertGreaterEqual(len(ETFS), 40)

    def test_index_proxies_point_at_funds_in_the_universe(self):
        # An off-universe proxy would need its own price download purely to serve one
        # tracking-difference number.
        missing = {ticker: meta["index_proxy"] for ticker, meta in ETFS.items()
                   if meta.get("index_proxy") and meta["index_proxy"] not in ETFS}
        self.assertEqual(missing, {}, f"proxies outside the universe: {missing}")

    def test_a_fund_is_never_its_own_index_proxy(self):
        self_referential = [ticker for ticker, meta in ETFS.items()
                            if meta.get("index_proxy") == ticker]
        self.assertEqual(self_referential, [])

    def test_most_funds_have_a_tracking_difference_reference(self):
        covered = sum(1 for meta in ETFS.values() if meta.get("index_proxy"))
        self.assertGreater(covered / len(ETFS), 0.6,
                           "under 60% of funds can compute tracking difference")

    def test_every_fund_declares_the_fields_scoring_needs(self):
        for ticker, meta in ETFS.items():
            with self.subTest(ticker=ticker):
                self.assertTrue(meta.get("name"))
                self.assertTrue(meta.get("category"))
                self.assertTrue(meta.get("issuer"))
                self.assertIsInstance(meta.get("expense_ratio"), (int, float))
                # Expense ratios are percentages, not decimals: 0.03 means three basis
                # points. A value above 3 is almost certainly a unit mix-up.
                self.assertLess(meta["expense_ratio"], 3.0)
                self.assertGreaterEqual(meta["expense_ratio"], 0.0)

    def test_the_scored_benchmarks_are_present(self):
        self.assertIn("SPY", ETFS)
        self.assertIn("DIA", ETFS)


class StockUniverseTests(unittest.TestCase):
    def test_symbols_are_unique_and_well_formed(self):
        self.assertEqual(len(SYMBOLS), len(set(SYMBOLS)), "duplicate tickers in the universe")
        import re
        malformed = [s for s in SYMBOLS if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", s)]
        self.assertEqual(malformed, [])

    def test_breadth_is_wide_enough_for_cross_sectional_ranking(self):
        # Information ratio scales with the square root of breadth, and decile analysis
        # needs enough names per bucket to be more than noise.
        self.assertGreaterEqual(len(SYMBOLS), 300)

    def test_the_statement_shortlist_stays_well_under_the_universe(self):
        # Statement enrichment costs several requests per company, so it must grow
        # sub-linearly with the universe or the run stops fitting in its window.
        self.assertLess(ADVISOR["extended_limit"], len(SYMBOLS) / 2)
        self.assertGreaterEqual(ADVISOR["extended_limit"], ADVISOR["publish_limit"])

    def test_configured_holdings_are_inside_the_scored_universe(self):
        symbols = set(SYMBOLS)
        missing = [s for s in ADVISOR.get("portfolio_symbols", []) if s not in symbols]
        self.assertEqual(missing, [], f"holdings that would never be scored: {missing}")


class ScreenPayloadTests(unittest.TestCase):
    def test_the_screen_slice_carries_only_fields_the_screens_read(self):
        # The unpublished remainder of a ~900-name universe is most of what the browser
        # downloads, so it must not quietly accumulate unread fields.
        fields = set(fetch_advisor.SCREEN_TECHNICAL_FIELDS)
        screens = os.path.join(os.path.dirname(PIPELINE_DIR), "src", "lib", "researchScreens.js")
        with open(screens) as handle:
            source = handle.read()
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, source,
                              f"'{field}' is published to every screen row but never read")

    def test_the_slice_is_materially_smaller_than_the_full_block(self):
        full = {f"field_{index}": index for index in range(24)}
        full.update({key: 1.0 for key in fetch_advisor.SCREEN_TECHNICAL_FIELDS})
        slimmed = {key: full.get(key) for key in fetch_advisor.SCREEN_TECHNICAL_FIELDS
                   if full.get(key) is not None}
        self.assertLess(len(json.dumps(slimmed)), len(json.dumps(full)) / 1.8)


if __name__ == "__main__":
    unittest.main()
