"""Point-in-time backfill: filing dates, amendments, tag heterogeneity, entity keying.

The property under test throughout is that a value becomes readable on the date its filing
was *accepted*, not the date its fiscal period ended. Everything else in Phases 4-10 rests on
that, and a fixed reporting lag -- what pipeline/backtest_historical.py approximates with
today -- gets it wrong by weeks in both directions.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from edgar_entities import EntityResolutionError, EntityResolver, normalize_ticker
from edgar_facts import (as_of, company_observations, observations_for_concept, restatements)

# A filer that reports Q2 on 2025-08-05, then restates it in a 10-K/A on 2026-02-20.
COMPANYFACTS = {
    "cik": 944695,
    "entityName": "HANOVER INSURANCE GROUP, INC.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {"USD": [
                    {"start": "2025-04-01", "end": "2025-06-30", "val": 1_600_000_000,
                     "accn": "0000944695-25-000042", "fy": 2025, "fp": "Q2", "form": "10-Q",
                     "filed": "2025-08-05"},
                    {"start": "2025-07-01", "end": "2025-09-30", "val": 1_650_000_000,
                     "accn": "0000944695-25-000061", "fy": 2025, "fp": "Q3", "form": "10-Q",
                     "filed": "2025-11-04"},
                    # The same Q2 period, restated in a later amendment.
                    {"start": "2025-04-01", "end": "2025-06-30", "val": 1_575_000_000,
                     "accn": "0000944695-26-000009", "fy": 2025, "fp": "Q2", "form": "10-K/A",
                     "filed": "2026-02-20"},
                    # An 8-K fact: excluded, because its period is irregular.
                    {"start": "2025-04-01", "end": "2025-06-30", "val": 1_610_000_000,
                     "accn": "0000944695-25-000050", "fy": 2025, "fp": "Q2", "form": "8-K",
                     "filed": "2025-07-28"},
                ]},
            },
            "Assets": {
                "units": {"USD": [
                    {"end": "2025-06-30", "val": 15_000_000_000,
                     "accn": "0000944695-25-000042", "fy": 2025, "fp": "Q2", "form": "10-Q",
                     "filed": "2025-08-05"},
                ]},
            },
        },
    },
}

# A filer that tags revenue under the post-ASC-606 concept instead of the legacy aggregate.
ASC606_FACTS = {
    "facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {
        "units": {"USD": [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 500_000_000,
             "accn": "x-1", "form": "10-Q", "filed": "2025-05-01"},
        ]},
    }}},
}


class FilingDateTests(unittest.TestCase):
    def observations(self):
        rows, _ = observations_for_concept(COMPANYFACTS, "revenue", cik=944695, ticker="THG")
        return rows

    def test_a_value_is_stamped_with_its_filing_date_not_its_period_end(self):
        q2 = next(row for row in self.observations()
                  if row["period_end"] == "2025-06-30" and row["form"] == "10-Q")
        self.assertEqual(q2["period_end"], "2025-06-30")
        self.assertEqual(q2["available_at"], "2025-08-05")

    def test_a_quarter_is_invisible_between_its_period_end_and_its_filing(self):
        """The exact window a fixed reporting lag gets wrong."""
        rows = self.observations()
        self.assertIsNone(as_of(rows, "2025-07-01"))
        self.assertIsNone(as_of(rows, "2025-08-04"))
        self.assertIsNotNone(as_of(rows, "2025-08-05"))

    def test_the_value_readable_on_a_date_is_the_latest_one_filed_by_then(self):
        rows = self.observations()
        self.assertEqual(as_of(rows, "2025-09-01")["value"], 1_600_000_000)
        self.assertEqual(as_of(rows, "2025-12-01")["value"], 1_650_000_000)

    def test_non_periodic_forms_are_excluded(self):
        """An 8-K revenue fact filed 2025-07-28 must not make Q2 readable a week early."""
        rows = self.observations()
        self.assertNotIn("8-K", {row["form"] for row in rows})
        self.assertIsNone(as_of(rows, "2025-07-29"))


class AmendmentTests(unittest.TestCase):
    def observations(self):
        rows, _ = observations_for_concept(COMPANYFACTS, "revenue", cik=944695, ticker="THG")
        return rows

    def test_the_original_survives_the_amendment(self):
        """A restated-fundamentals provider overwrites this; the point is that we do not."""
        q2 = [row for row in self.observations() if row["period_end"] == "2025-06-30"]
        self.assertEqual({row["value"] for row in q2}, {1_600_000_000, 1_575_000_000})

    def test_an_amendment_supersedes_only_from_its_own_filing_date(self):
        rows = self.observations()
        before = as_of(rows, "2026-01-01", period_type="quarter")
        after = as_of(rows, "2026-03-01", period_type="quarter")
        self.assertEqual(before["value"], 1_650_000_000)      # Q3, latest period then
        self.assertEqual(after["period_end"], "2025-09-30")   # Q3 is still the latest period
        q2_after = [row for row in rows if row["period_end"] == "2025-06-30"
                    and row["available_at"] <= "2026-03-01"]
        self.assertEqual(max(q2_after, key=lambda row: row["filed"])["value"], 1_575_000_000)

    def test_restatements_are_reported_with_both_sides(self):
        found = restatements(self.observations())
        self.assertEqual(len(found), 1)
        entry = found[0]
        self.assertEqual(entry["original_value"], 1_600_000_000)
        self.assertEqual(entry["revised_value"], 1_575_000_000)
        self.assertEqual(entry["original_filed"], "2025-08-05")
        self.assertEqual(entry["revised_filed"], "2026-02-20")
        self.assertAlmostEqual(entry["change_fraction"], -0.015625, places=6)


class TagHeterogeneityTests(unittest.TestCase):
    def test_the_tag_that_satisfied_a_concept_is_recorded(self):
        rows, tag = observations_for_concept(COMPANYFACTS, "revenue")
        self.assertEqual(tag, "Revenues")
        self.assertEqual({row["source_field"] for row in rows}, {"Revenues"})

    def test_a_post_asc606_filer_resolves_through_its_own_tag(self):
        rows, tag = observations_for_concept(ASC606_FACTS, "revenue")
        self.assertEqual(tag, "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(len(rows), 1)

    def test_a_concept_no_tag_satisfies_is_reported_missing_not_guessed(self):
        rows, meta = company_observations(ASC606_FACTS, concepts=("revenue", "inventory"))
        self.assertEqual(meta["missing_concepts"], ["inventory"])
        self.assertEqual(set(meta["resolved_tags"]), {"revenue"})


class ProvenanceTests(unittest.TestCase):
    REQUIRED = ("source", "source_field", "accession", "period_end", "available_at", "filed",
                "unit", "transformation", "split_adjusted", "reliability_tier",
                "requested_at", "observed_at", "point_in_time", "cik")

    def test_every_observation_carries_full_provenance(self):
        rows, _ = observations_for_concept(COMPANYFACTS, "revenue", cik=944695, ticker="THG")
        for row in rows:
            for field in self.REQUIRED:
                self.assertIn(field, row)
            self.assertTrue(row["point_in_time"])
            self.assertEqual(row["reliability_tier"], "regulatory_primary")

    def test_the_cik_is_zero_padded_so_it_never_collides_on_string_compare(self):
        rows, _ = observations_for_concept(COMPANYFACTS, "revenue", cik=944695)
        self.assertEqual(rows[0]["cik"], "0000944695")

    def test_balance_sheet_facts_are_marked_instant(self):
        rows, _ = observations_for_concept(COMPANYFACTS, "assets")
        self.assertEqual(rows[0]["period_type"], "instant")
        self.assertIsNone(rows[0]["period_start"])


class EntityResolverTests(unittest.TestCase):
    ROWS = [
        {"cik_str": 944695, "ticker": "THG", "title": "HANOVER INSURANCE GROUP, INC."},
        {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
        {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
        {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
    ]

    def resolver(self, rows=None):
        return EntityResolver(rows if rows is not None else self.ROWS,
                              fetched_at="2026-08-09T00:00:00+00:00")

    def test_a_ticker_resolves_to_a_zero_padded_cik(self):
        self.assertEqual(self.resolver().resolve("THG"), "0000944695")

    def test_an_unmapped_ticker_raises_rather_than_guessing(self):
        with self.assertRaises(EntityResolutionError) as caught:
            self.resolver().resolve("NOTREAL")
        self.assertIn("company_tickers", str(caught.exception))

    def test_two_ciks_claiming_one_ticker_is_ambiguous_and_fatal(self):
        rows = [*self.ROWS, {"cik_str": 111111, "ticker": "THG", "title": "THG PLC"}]
        with self.assertRaises(EntityResolutionError) as caught:
            self.resolver(rows).resolve("THG")
        self.assertIn("ambiguous", str(caught.exception))

    def test_share_classes_sharing_a_cik_are_reported_but_not_an_error(self):
        audit = self.resolver().audit(["GOOG", "GOOGL", "AAPL"])
        self.assertEqual(audit["resolved"], 3)
        self.assertEqual(audit["shared_cik"], {"0001652044": ["GOOG", "GOOGL"]})

    def test_class_suffixes_normalize_between_dot_and_hyphen(self):
        self.assertEqual(normalize_ticker("BRK.B"), "BRK-B")
        self.assertEqual(self.resolver().resolve("BRK.B"), "0001067983")

    def test_an_audit_separates_unresolved_from_ambiguous(self):
        rows = [*self.ROWS, {"cik_str": 111111, "ticker": "THG", "title": "THG PLC"}]
        audit = self.resolver(rows).audit(["AAPL", "THG", "NOTREAL"])
        self.assertEqual(audit["ambiguous_tickers"], ["THG"])
        self.assertEqual(sorted(audit["unresolved_reasons"]), ["NOTREAL", "THG"])

    def test_the_map_records_when_it_was_fetched(self):
        """A resolution is only true as of the map it came from; SEC reassigns tickers."""
        self.assertEqual(self.resolver().provenance()["entity_map_fetched_at"],
                         "2026-08-09T00:00:00+00:00")


class BackfillJobTests(unittest.TestCase):
    def test_the_observation_key_treats_an_amendment_as_a_new_record(self):
        from build_pit_fundamentals import observation_key
        rows, _ = observations_for_concept(COMPANYFACTS, "revenue", cik=944695)
        q2 = [row for row in rows if row["period_end"] == "2025-06-30"]
        self.assertEqual(len({observation_key(row) for row in q2}), 2)

    def test_the_job_refuses_to_run_without_a_declared_user_agent(self):
        from build_pit_fundamentals import run

        class Unavailable:
            available = False

        self.assertEqual(run(["AAPL"], client=Unavailable()), 1)


if __name__ == "__main__":
    unittest.main()


class JobArtifactTests(unittest.TestCase):
    """The files a run commits, produced end to end against a stub client.

    Every run commits its report -- audit-only included -- because an audit whose only
    record is a log that scrolls away cannot be read afterwards.
    """

    def setUp(self):
        import tempfile
        import build_pit_fundamentals as job
        self.job = job
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = self.directory.name
        for name, filename in (("FUNDAMENTALS", "fundamentals.jsonl"),
                               ("MANIFEST", "fundamentals_manifest.json"),
                               ("ENTITY_AUDIT", "entity_audit.json"),
                               ("RESTATEMENTS", "fundamental_restatements.jsonl")):
            original = getattr(job, name)
            setattr(job, name, os.path.join(root, filename))
            self.addCleanup(setattr, job, name, original)

    def resolver(self):
        return EntityResolver(EntityResolverTests.ROWS, fetched_at="2026-08-09T00:00:00+00:00")

    def client(self):
        class Stub:
            available = True

            def company_facts_by_cik(self, cik):
                return COMPANYFACTS
        return Stub()

    def read(self, path):
        import json
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_audit_only_commits_a_readable_resolution_report(self):
        code = self.job.run(["THG", "AAPL", "NOTREAL"], audit_only=True,
                            client=self.client(), resolver=self.resolver())
        self.assertEqual(code, 0)
        audit = self.read(self.job.ENTITY_AUDIT)
        self.assertEqual(audit["mode"], "audit_only")
        self.assertEqual(audit["resolved"], 2)
        self.assertEqual(audit["resolved_map"]["THG"], "0000944695")
        self.assertIn("NOTREAL", audit["unresolved_reasons"])
        # Nothing was fetched, so no observation store exists yet.
        self.assertFalse(os.path.exists(self.job.FUNDAMENTALS))

    def test_a_backfill_writes_observations_a_manifest_and_the_audit(self):
        code = self.job.run(["THG"], client=self.client(), resolver=self.resolver())
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.job.FUNDAMENTALS))
        manifest = self.read(self.job.MANIFEST)
        self.assertEqual(manifest["companies_ok"], 1)
        self.assertGreater(manifest["observations_written"], 0)
        self.assertEqual(manifest["companies"][0]["ticker"], "THG")
        self.assertIn("revenue", manifest["companies"][0]["resolved_tags"])
        # The entity audit is written on a backfill too: resolution is part of provenance.
        self.assertEqual(self.read(self.job.ENTITY_AUDIT)["mode"], "backfill")

    def test_the_restatement_in_the_fixture_is_recorded(self):
        self.job.run(["THG"], client=self.client(), resolver=self.resolver())
        with open(self.job.RESTATEMENTS, encoding="utf-8") as handle:
            rows = [line for line in handle if line.strip()]
        self.assertEqual(len(rows), 1)

    def test_rerunning_adds_nothing_and_is_therefore_resumable(self):
        self.job.run(["THG"], client=self.client(), resolver=self.resolver())
        first = self.read(self.job.MANIFEST)["observations_written"]
        self.job.run(["THG"], client=self.client(), resolver=self.resolver())
        second = self.read(self.job.MANIFEST)
        self.assertGreater(first, 0)
        self.assertEqual(second["observations_written"], 0)
        self.assertEqual(second["observations_total"], first)

    def test_a_company_that_fails_to_fetch_is_recorded_not_fatal(self):
        class Failing:
            available = True

            def company_facts_by_cik(self, cik):
                raise TimeoutError("SEC did not respond")

        code = self.job.run(["THG", "AAPL"], client=Failing(), resolver=self.resolver())
        self.assertEqual(code, 0)
        manifest = self.read(self.job.MANIFEST)
        self.assertEqual(manifest["companies_failed"], 2)
        self.assertEqual(manifest["companies"][0]["status"], "fetch_failed")
        self.assertIn("TimeoutError", manifest["companies"][0]["reason"])


class UnresolvedClassificationTests(unittest.TestCase):
    """A single bucket of unresolved tickers hides the one that matters.

    Against the first real run: 49 unresolved split into 3 funds (correct -- funds file no
    operating-company financials), 45 configured tickers absent from published data (a stale
    universe: acquisitions closed, tickers reassigned), and 1 company being scored live with
    no CIK behind it. Only the last needs a person.
    """

    PUBLISHED = [
        {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "ETF", "is_etf": True},
        {"ticker": "AEP", "name": "American Electric Power Company", "sector": "Utilities",
         "is_etf": False, "score": 36.2},
    ]

    def classify(self, unresolved):
        from build_pit_fundamentals import classify_unresolved
        return classify_unresolved(unresolved, self.PUBLISHED)

    def test_a_fund_without_a_cik_is_expected_not_a_gap(self):
        self.assertEqual(self.classify({"VOO": "not in map"})["fund"], ["VOO"])

    def test_a_ticker_absent_from_published_data_is_a_stale_universe_entry(self):
        buckets = self.classify({"WBA": "not in map"})
        self.assertEqual(buckets["absent_from_data"], ["WBA"])
        self.assertEqual(buckets["scored_but_unresolved"], [])

    def test_a_company_scored_live_with_no_cik_is_surfaced_for_review(self):
        buckets = self.classify({"AEP": "not in map"})
        self.assertEqual(len(buckets["scored_but_unresolved"]), 1)
        entry = buckets["scored_but_unresolved"][0]
        self.assertEqual(entry["ticker"], "AEP")
        self.assertEqual(entry["published_name"], "American Electric Power Company")

    def test_the_three_cases_are_separated_rather_than_pooled(self):
        buckets = self.classify({"VOO": "x", "WBA": "x", "AEP": "x"})
        self.assertEqual([len(buckets[key]) for key in
                          ("fund", "absent_from_data", "scored_but_unresolved")], [1, 1, 1])


class EmptyPayloadTests(unittest.TestCase):
    """An empty payload is not a successful fetch.

    The first live sample run reported 25 of 25 companies "ok" with zero observations,
    because a fetched payload and a usable one were the same status. They are now distinct.
    """

    def setUp(self):
        JobArtifactTests.setUp(self)

    def resolver(self):
        return EntityResolver(EntityResolverTests.ROWS, fetched_at="2026-08-09T00:00:00+00:00")

    def test_a_payload_with_no_usable_facts_is_not_reported_ok(self):
        class Empty:
            available = True

            def company_facts_by_cik(self, cik):
                return {"cik": cik, "entityName": "Test Co", "facts": {}}

        import json
        code = self.job.run(["AAPL"], client=Empty(), resolver=self.resolver())
        self.assertEqual(code, 0)
        with open(self.job.MANIFEST, encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["companies_ok"], 0)
        self.assertEqual(manifest["companies"][0]["status"], "no_usable_facts")
        self.assertEqual(manifest["companies"][0]["fact_taxonomies"], [])
