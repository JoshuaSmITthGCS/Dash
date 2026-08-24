"""Guards on the sector-connected peer re-rank.

The whole point of this screen is "names you are not already looking at", so the exclusion
rules are the contract: a published leader or a holding appearing here would make the label
false, and a fund appearing here would be a category error.
"""

import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import build_theme_peers as peers
from themes import build_theme_screen


def _row(ticker, **over):
    row = {"ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology",
           "industry": "Semiconductors", "score": 70, "components": {"fundamentals": 70},
           "sector_valuation_percentile": 50}
    row.update(over)
    return row


THEME = {
    "id": "t1", "display_name": "Theme One", "seed_tickers": ["SEED"],
    # Declared lowercase: in_theme_scope lowercases the row's sector before
    # comparing, so a capitalised entry here matches nothing.
    "sectors": ["technology"], "guardrails": {}, "signals": [],
}


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self):
        self.advisor = {
            "research": [_row("SEED"), _row("LEADER")],
            "screen_universe": [_row("PEER1"), _row("PEER2"), _row("FUND", is_etf=True)],
            "portfolio_coverage": [_row("HELD")],
        }

    def test_published_leaders_and_holdings_are_excluded(self):
        # They already carry a top research score or are already owned, so "connected, not
        # yet re-rated" is the wrong label for them and the refresh already publishes them.
        covered = peers.already_covered(self.advisor)

        self.assertEqual(covered, {"SEED", "LEADER", "HELD"})

    def test_only_unpublished_peers_become_candidates(self):
        self.advisor["screen_universe"].append(_row("HELD"))

        candidates, _ = peers.peer_candidates([THEME], self.advisor)

        self.assertEqual(set(candidates), {"PEER1", "PEER2"})

    def test_funds_are_never_candidates(self):
        # A fund has no place in a supply chain and no 10-K to read: it would resolve no
        # signal, and its role and industry would be a category error, not a missing value.
        candidates, _ = peers.peer_candidates([THEME], self.advisor)

        self.assertNotIn("FUND", candidates)

    def test_the_screen_tail_is_searched_not_just_published_rows(self):
        # Scoring only `research` would reproduce the exact blind spot this job removes:
        # the unrecognised names live in screen_universe.
        candidates, _ = peers.peer_candidates([THEME], self.advisor)

        self.assertTrue({"PEER1", "PEER2"} <= set(candidates))

    def test_candidates_are_tagged_so_they_file_under_the_connected_group(self):
        candidates, _ = peers.peer_candidates([THEME], self.advisor)

        self.assertEqual({row["candidate_source"] for row in candidates.values()},
                         {"sector_peer"})

    def test_a_theme_whose_seeds_never_scored_is_skipped_not_crashed(self):
        theme = {**THEME, "seed_tickers": ["NOTINUNIVERSE"]}

        candidates, counts = peers.peer_candidates([theme], self.advisor)

        self.assertEqual(candidates, {})
        self.assertEqual(counts["t1"], 0)

    def test_the_candidate_cap_keeps_the_strongest_peers(self):
        # A truncated first run should still evaluate the peers most worth reading, not an
        # alphabetical slice.
        self.advisor["screen_universe"] = [_row("LOW", score=10), _row("HIGH", score=99)]

        candidates, _ = peers.peer_candidates([THEME], self.advisor, limit=1)

        self.assertEqual(set(candidates), {"HIGH"})


class PublishedShapeTests(unittest.TestCase):
    def test_every_published_row_is_connected_and_capped_per_theme(self):
        # build_theme_screen splits leaders from connected by candidate_source and caps each
        # group separately; passing only peers must leave the leaders group empty.
        theme = {**THEME, "signals": [{"name": "s", "weight": 1.0, "leading": True}],
                 "scoring": {"min_signals_required": 1}}
        rows = [{**_row(f"P{i}"), "candidate_source": "sector_peer"} for i in range(25)]

        screen = build_theme_screen([theme], rows, lambda t, th: {"s": 0.9},
                                    limit_per_group=10)

        published = screen["themes"][0]
        self.assertLessEqual(len(published["rows"]), 10)
        self.assertEqual(published["group_counts"]["leaders"], 0)
        self.assertEqual({row["candidate_source"] for row in published["rows"]},
                         {"sector_peer"})

    def test_an_empty_universe_still_returns_a_well_formed_screen(self):
        screen = peers.build({"research": []})

        self.assertIn("unavailable_reason", screen)
        self.assertEqual(screen["themes"], [])


if __name__ == "__main__":
    unittest.main()
