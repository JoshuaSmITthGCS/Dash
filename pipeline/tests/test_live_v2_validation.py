import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from live_v2_validation import _peer_classification


def _row(ticker, valuation, sector="Technology"):
    return {"ticker": ticker, "sector": sector,
            "fundamental_detail": {"categories": {"valuation": valuation}}}


class PeerClassificationTests(unittest.TestCase):
    """live_v2_validation used to hardcode total_peer_count=0/valid_peer_count=0/
    percentile_status=INSUFFICIENT_VALID_PEERS for every ticker unconditionally, never
    calling peer_groups.canonical_percentiles at all -- an integration gap, not the
    n>=30 gate working as designed. This pins the real computation."""

    def test_a_sector_with_thirty_or_more_peers_resolves_a_real_tier(self):
        previous_payload = {"research": [_row(f"P{i:02d}", float(i)) for i in range(35)],
                            "screen_universe": []}

        result = _peer_classification("NEWQ", {"valuation": 90.0}, previous_payload)

        self.assertEqual(result["total_peer_count"], 36)  # 35 prior + NEWQ itself
        self.assertEqual(result["valid_peer_count"], 36)
        self.assertNotEqual(result["percentile_status"], "INSUFFICIENT_VALID_PEERS")
        self.assertIn(result["percentile_status"], {"CHEAPEST_THIRD", "MIDDLE_THIRD", "MOST_EXPENSIVE_THIRD"})

    def test_a_sector_with_fewer_than_thirty_peers_reports_its_real_count_not_a_stub_zero(self):
        previous_payload = {"research": [_row(f"P{i:02d}", float(i), sector="Insurance") for i in range(9)],
                            "screen_universe": []}

        result = _peer_classification("NEWQ", {"valuation": 90.0}, previous_payload)

        # Real counts (10, including NEWQ itself), not the old hardcoded 0/0 stub.
        self.assertEqual(result["total_peer_count"], 10)
        self.assertEqual(result["valid_peer_count"], 10)
        self.assertEqual(result["percentile_status"], "INSUFFICIENT_VALID_PEERS")

    def test_the_tickers_own_live_categories_are_used_not_a_stale_prior_row(self):
        # A ticker already present in previous_payload with a stale score must be ranked
        # on this run's freshly computed categories, not the value carried in the file.
        previous_payload = {"research": [_row(f"P{i:02d}", float(i)) for i in range(35)]}
        previous_payload["research"][0] = _row("P00", -999.0)  # stale, would sort last

        result = _peer_classification("P00", {"valuation": 34.5}, previous_payload)  # this run's real score

        self.assertEqual(result["total_peer_count"], 35)  # still 35 unique tickers


if __name__ == "__main__":
    unittest.main()
