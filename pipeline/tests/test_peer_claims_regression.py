"""Regression: the specific false peer claim this audit began with must not recur.

The published dataset stated, for The Hanover Insurance Group:

    "Cheaper than approximately 85% of Property & casualty insurers, based on 14 valid peers."

THG traded at 2.18x book and 2.48x tangible book. SIGI, in the same peer group at 1.66x book
and 1.60x tangible book, was published as *more expensive* -- the two had the identical
valuation composite of 95.7 and were separated purely by an alphabetical tie-break. See
research/audit/CURRENT_MODEL_AUDIT.md section 2.

These tests run the real peer machinery over the real published universe, so they fail if any
future change reintroduces either the sub-sample claim or the continuous percentile.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from peer_groups import MINIMUM_VALID_PEERS, canonical_percentiles

ADVISOR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                       "public", "data", "advisor.json")


def published_rows():
    if not os.path.exists(ADVISOR):
        return []
    with open(ADVISOR, encoding="utf-8") as handle:
        payload = json.load(handle)
    rows, seen = [], set()
    for row in (*payload.get("research", []), *payload.get("screen_universe", [])):
        ticker = row.get("ticker")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append({"ticker": ticker, "sector": row.get("sector"),
                     "industry": row.get("industry"),
                     "categories": row.get("fundamental_categories") or {}})
    return rows


class PublishedUniversePeerClaimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = published_rows()
        cls.result = canonical_percentiles(cls.rows) if cls.rows else {}

    def setUp(self):
        if not self.rows:
            self.skipTest("public/data/advisor.json is not present in this checkout")

    def test_thg_publishes_no_percentile_claim(self):
        """The literal regression: THG's payload must contain no percentile."""
        metadata = self.result.get("THG")
        self.assertIsNotNone(metadata, "THG missing from the published universe")
        self.assertNotIn("value", metadata)
        self.assertNotIn("display_value", metadata)

    def test_thg_peer_group_is_below_the_minimum_and_therefore_silent(self):
        metadata = self.result["THG"]
        self.assertLess(metadata["peer_count_with_valid_data"], MINIMUM_VALID_PEERS)
        self.assertIsNone(metadata["peer_context"])
        self.assertIsNone(metadata["tier"])
        self.assertEqual(metadata["invalid_reason"], "insufficient_valid_peers")

    def test_thg_earns_no_valuation_modifier_points(self):
        """A suppressed peer claim must not still move the score.

        The old payload granted THG +2.08 points from the same ranking that produced the
        false sentence.
        """
        from advisor_engine import sector_percentile_modifier
        points, note = sector_percentile_modifier(self.result["THG"]["ordinal"])
        self.assertEqual(points, 0.0)
        self.assertIsNone(note)

    def test_no_row_anywhere_publishes_a_continuous_percentile(self):
        offenders = [ticker for ticker, metadata in self.result.items()
                     if metadata.get("value") is not None or metadata.get("display_value") is not None]
        self.assertEqual(offenders, [])

    def test_every_published_tier_is_backed_by_a_sufficient_sample(self):
        offenders = [(ticker, metadata["peer_count_with_valid_data"])
                     for ticker, metadata in self.result.items()
                     if metadata["peer_context"] is not None
                     and metadata["peer_count_with_valid_data"] < MINIMUM_VALID_PEERS]
        self.assertEqual(offenders, [])

    def test_the_universe_still_gets_useful_peer_context(self):
        """Suppression must not be so aggressive that nothing is ever comparable."""
        with_context = sum(1 for metadata in self.result.values() if metadata["peer_context"])
        self.assertGreater(with_context, len(self.result) * 0.5,
                           "the n>=30 gate silenced more than half the universe")

    def test_tied_valuation_scores_never_land_in_different_tiers(self):
        by_group = {}
        for ticker, metadata in self.result.items():
            if metadata["peer_context"] is None:
                continue
            by_group.setdefault(metadata["peer_group_id"], []).append(
                (metadata["underlying_value"], metadata["tier"], ticker))
        for group_id, entries in by_group.items():
            tiers_by_value = {}
            for value, tier, ticker in entries:
                tiers_by_value.setdefault(value, set()).add(tier)
            split = {value: tiers for value, tiers in tiers_by_value.items() if len(tiers) > 1}
            self.assertEqual(split, {}, f"{group_id}: tied scores split across tiers: {split}")


if __name__ == "__main__":
    unittest.main()
