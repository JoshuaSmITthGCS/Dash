"""Sharded point-in-time storage: lossless where it matters, small enough to keep.

A 25-company sample was 89,434 rows and 64.5 MB, projecting to 2.2 GB for the full universe
-- past GitHub's 100 MB per-file limit and a permanent weight on every clone. The reductions
here are lossless for every point-in-time and restatement question; these tests pin that.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from edgar_facts import as_of, restatements
from pit_fundamentals_store import ShardedStore, compact, dedupe, expand, shard_for


def observation(**updates):
    row = {"cik": "0000320193", "concept": "revenue", "unit": "USD",
           "period_start": "2024-10-01", "period_end": "2025-09-27", "filed": "2025-10-31",
           "value": 416_161_000_000, "accession": "a-1", "form": "10-K",
           "fiscal_year": 2025, "fiscal_period": "FY"}
    row.update(updates)
    return row


class DeduplicationTests(unittest.TestCase):
    def test_an_unchanged_repeat_of_a_filed_value_is_dropped(self):
        """A 10-K repeats prior years as comparatives; the repeat changes nothing knowable."""
        rows = [observation(filed="2025-10-31", accession="a-1"),
                observation(filed="2026-10-30", accession="a-2")]
        self.assertEqual(len(dedupe(rows)), 1)

    def test_a_changed_value_is_a_restatement_and_is_always_kept(self):
        rows = [observation(filed="2025-10-31", accession="a-1", value=100),
                observation(filed="2026-10-30", accession="a-2", value=95)]
        kept = dedupe(rows)
        self.assertEqual([row["value"] for row in kept], [100, 95])

    def test_a_value_that_reverts_is_kept_as_a_third_observation(self):
        rows = [observation(filed="2025-01-01", accession="a", value=100),
                observation(filed="2025-06-01", accession="b", value=95),
                observation(filed="2025-12-01", accession="c", value=100)]
        self.assertEqual([row["value"] for row in dedupe(rows)], [100, 95, 100])

    def test_different_series_never_deduplicate_against_each_other(self):
        rows = [observation(concept="revenue", value=1), observation(concept="assets", value=1)]
        self.assertEqual(len(dedupe(rows)), 2)

    def test_deduplication_preserves_every_restatement_answer(self):
        rows = [observation(filed="2025-10-31", accession="a-1", value=100),
                observation(filed="2026-01-15", accession="a-2", value=100),
                observation(filed="2026-10-30", accession="a-3", value=95)]
        full = restatements([expand(row) for row in rows])
        reduced = restatements([expand(row) for row in dedupe(rows)])
        self.assertEqual(len(full), len(reduced))
        self.assertEqual(full[0]["revised_value"], reduced[0]["revised_value"])

    def test_deduplication_preserves_every_as_of_answer(self):
        rows = [observation(period_end="2024-09-28", filed="2024-11-01", accession="a", value=391),
                observation(period_end="2024-09-28", filed="2025-10-31", accession="b", value=391),
                observation(period_end="2025-09-27", filed="2025-10-31", accession="c", value=416)]
        full = [expand(row) for row in rows]
        reduced = [expand(row) for row in dedupe(rows)]
        for when in ("2024-10-31", "2024-11-01", "2025-10-30", "2025-10-31", "2026-06-01"):
            a = as_of(full, when)
            b = as_of(reduced, when)
            self.assertEqual(a and a["value"], b and b["value"], when)


class RoundTripTests(unittest.TestCase):
    def test_constants_and_derivable_fields_come_back_on_read(self):
        rehydrated = expand(compact(observation()),
                            tags={("0000320193", "revenue"): "Revenues"},
                            tickers={"0000320193": "AAPL"})
        self.assertEqual(rehydrated["source"], "sec_edgar_xbrl")
        self.assertEqual(rehydrated["reliability_tier"], "regulatory_primary")
        self.assertTrue(rehydrated["point_in_time"])
        self.assertEqual(rehydrated["available_at"], "2025-10-31")
        self.assertEqual(rehydrated["observed_at"], "2025-10-31")
        self.assertEqual(rehydrated["period_type"], "annual")
        self.assertEqual(rehydrated["source_field"], "Revenues")
        self.assertEqual(rehydrated["ticker"], "AAPL")
        self.assertFalse(rehydrated["amended"])

    def test_an_amendment_is_recognised_from_its_form(self):
        self.assertTrue(expand(compact(observation(form="10-K/A")))["amended"])

    def test_the_stored_row_keeps_only_what_varies(self):
        stored = compact(observation())
        for dropped in ("source", "reliability_tier", "transformation", "point_in_time",
                        "observed_at", "available_at", "period_type", "ticker"):
            self.assertNotIn(dropped, stored)
        for kept in ("cik", "concept", "value", "period_end", "filed", "accession"):
            self.assertIn(kept, stored)


class ShardingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ShardedStore(self.directory.name)

    def test_a_company_always_lands_in_the_same_shard(self):
        self.assertEqual(shard_for("0000320193"), shard_for("0000320193"))

    def test_companies_spread_across_shards(self):
        shards = {shard_for(f"{index:010d}") for index in range(1, 400)}
        self.assertGreater(len(shards), 50)

    def test_write_then_load_round_trips(self):
        self.store.write([observation()])
        loaded = self.store.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["value"], 416_161_000_000)

    def test_rewriting_the_same_rows_is_idempotent(self):
        self.store.write([observation()])
        self.store.write([observation()])
        self.assertEqual(len(self.store.load()), 1)

    def test_a_later_restatement_merges_into_its_series_in_filing_order(self):
        self.store.write([observation(filed="2026-10-30", accession="b", value=95)])
        self.store.write([observation(filed="2025-10-31", accession="a", value=100)])
        values = [row["value"] for row in self.store.load()]
        self.assertEqual(values, [100, 95])

    def test_keys_supports_resumability_across_shards(self):
        self.store.write([observation(), observation(cik="0000000042", accession="z")])
        self.assertEqual(len(self.store.keys()), 2)

    def test_stats_report_the_largest_shard_so_a_size_limit_is_visible(self):
        self.store.write([observation()])
        stats = self.store.stats()
        self.assertEqual(stats["observations"], 1)
        self.assertGreater(stats["largest_shard_bytes"], 0)
        self.assertLessEqual(stats["largest_shard_bytes"], stats["total_bytes"])


class LiveStoreTests(unittest.TestCase):
    """Guards against the committed store, so a regression is caught before it is pushed."""

    DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pit",
                             "fundamentals")
    GITHUB_WARNING_BYTES = 50 * 1024 * 1024

    def setUp(self):
        if not os.path.isdir(self.DIRECTORY):
            self.skipTest("no point-in-time fundamentals store in this checkout")
        self.stats = ShardedStore(self.DIRECTORY).stats()

    def test_no_shard_approaches_the_file_size_limit(self):
        self.assertLess(self.stats["largest_shard_bytes"], self.GITHUB_WARNING_BYTES)

    def test_the_single_file_store_is_gone(self):
        legacy = os.path.join(os.path.dirname(self.DIRECTORY), "fundamentals.jsonl")
        self.assertFalse(os.path.exists(legacy),
                         "the unsharded store would grow past GitHub's hard limit")


if __name__ == "__main__":
    unittest.main()
