import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from enrichment_bias import (DEFAULT_SOURCE, build_report, eligible_universe,
                             is_statement_enriched, rank_concentration, score_gap,
                             unenriched_category_gap)


def row(ticker, score, enriched, sector="Technology", stale=False, valuation=60.0):
    categories = {"valuation": valuation, "profitability": 60.0, "growth": 60.0}
    if enriched:
        categories.update({"capital_allocation": 70.0, "accounting_quality": 70.0})
    payload = {"ticker": ticker, "score": score, "sector": sector,
               "fundamental_categories": categories}
    if stale:
        payload["stale_carryforward"] = True
    return payload


class EnrichmentMarkerTests(unittest.TestCase):
    def test_statement_only_categories_mark_an_enriched_row(self):
        self.assertTrue(is_statement_enriched(row("AAA", 80, enriched=True)))
        self.assertFalse(is_statement_enriched(row("BBB", 50, enriched=False)))

    def test_a_row_with_no_categories_is_not_enriched(self):
        self.assertFalse(is_statement_enriched({"ticker": "CCC"}))


class SourceGuardTests(unittest.TestCase):
    """A fast refresh cannot answer this question and must not be allowed to look like it can."""

    def test_a_carry_forward_dominated_payload_is_rejected(self):
        payload = {"universe_mode": "fast", "screen_universe": [
            *(row(f"S{i:02d}", 40, enriched=False, stale=True) for i in range(20)),
            row("LIVE", 80, enriched=True),
        ]}
        universe, rejection = eligible_universe(payload)

        self.assertIsNone(universe)
        self.assertEqual(rejection["status"], "source_rejected_fast_refresh")
        self.assertIn("stale carry-forwards", rejection["reason"])

    def test_a_full_refresh_payload_is_accepted(self):
        payload = {"universe_mode": "full", "screen_universe": [
            row(f"S{i:02d}", 40 + i, enriched=i < 5) for i in range(20)
        ]}
        universe, rejection = eligible_universe(payload)

        self.assertIsNone(rejection)
        self.assertEqual(len(universe), 20)

    def test_rejection_short_circuits_the_report_instead_of_publishing_numbers(self):
        payload = {"universe_mode": "fast", "screen_universe": [
            row(f"S{i:02d}", 40, enriched=False, stale=True) for i in range(10)
        ]}
        report = build_report(payload, source_label="synthetic")

        self.assertEqual(report["observed_footprint"]["status"], "source_rejected_fast_refresh")
        self.assertNotIn("score_gap", report["observed_footprint"])

    def test_duplicate_tickers_across_sections_are_counted_once(self):
        payload = {"universe_mode": "full",
                   "research": [row("AAA", 80, enriched=True)],
                   "screen_universe": [row("AAA", 80, enriched=True),
                                       row("BBB", 50, enriched=False)]}
        universe, _ = eligible_universe(payload)

        self.assertEqual([item["ticker"] for item in universe], ["AAA", "BBB"])


class FootprintTests(unittest.TestCase):
    def test_rank_bands_report_the_enriched_share(self):
        rows = [*(row(f"E{i:02d}", 90 - i, enriched=True) for i in range(10)),
                *(row(f"U{i:02d}", 50 - i, enriched=False) for i in range(30))]
        concentration = rank_concentration(rows, cutoffs=(10, 20))

        self.assertEqual(concentration["by_rank_band"]["top_10"]["share"], 1.0)
        self.assertEqual(concentration["by_rank_band"]["top_20"]["share"], 0.5)
        self.assertEqual(concentration["universe_enrichment_rate"], 0.25)

    def test_score_gap_reports_both_groups_and_their_difference(self):
        rows = [row("AAA", 80, enriched=True), row("BBB", 60, enriched=True),
                row("CCC", 40, enriched=False)]
        gap = score_gap(rows)

        self.assertEqual(gap["statement_enriched"]["count"], 2)
        self.assertEqual(gap["not_enriched"]["count"], 1)
        self.assertEqual(gap["mean_gap"], 30.0)

    def test_non_statement_gap_excludes_the_statement_only_categories(self):
        """The circularity check must not measure the very categories enrichment creates."""
        rows = [row("AAA", 80, enriched=True, valuation=80.0),
                row("BBB", 40, enriched=False, valuation=50.0)]
        gaps = unenriched_category_gap(rows)

        self.assertNotIn("capital_allocation", gaps)
        self.assertNotIn("accounting_quality", gaps)
        self.assertEqual(gaps["valuation"]["gap"], 30.0)


class CommittedSourceTests(unittest.TestCase):
    def test_the_committed_full_refresh_source_still_reproduces_the_finding(self):
        if not os.path.exists(DEFAULT_SOURCE):
            self.skipTest("full-refresh snapshot not present in this checkout")
        with open(DEFAULT_SOURCE) as handle:
            payload = json.load(handle)
        report = build_report(payload, source_label="committed")
        footprint = report["observed_footprint"]

        self.assertEqual(payload["universe_mode"], "full")
        # The structural finding: statement-only evidence gates the entire top of the book.
        self.assertEqual(footprint["rank_concentration"]["by_rank_band"]["top_100"]["share"], 1.0)
        self.assertLess(footprint["rank_concentration"]["universe_enrichment_rate"], 0.5)

    def test_the_blocked_comparison_is_declared_not_silently_omitted(self):
        report = build_report({"universe_mode": "full",
                               "screen_universe": [row("AAA", 80, enriched=True)]},
                              source_label="synthetic")
        blocked = report["unconstrained_comparison"]

        self.assertEqual(blocked["status"], "blocked_network_policy")
        self.assertTrue(blocked["reproduction"])


if __name__ == "__main__":
    unittest.main()
