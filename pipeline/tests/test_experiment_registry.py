import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from experiment_registry import (DECISIONS, REGISTRY, backfill_multiple_testing_log,
                                 build_report)


class RegistrySchemaTests(unittest.TestCase):
    def test_every_entry_has_the_full_brief_schema(self):
        required = {"id", "hypothesis", "category", "configuration", "train_period",
                   "validation_period", "test_period", "metrics",
                   "number_of_variants_tested", "result", "decision", "reason"}
        for entry in REGISTRY:
            self.assertEqual(required, required & set(entry), f"{entry['id']} missing fields")

    def test_every_decision_is_one_of_the_four_brief_categories(self):
        for entry in REGISTRY:
            self.assertIn(entry["decision"], DECISIONS)

    def test_ids_are_unique(self):
        ids = [entry["id"] for entry in REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))

    def test_backfills_the_five_prior_work_orders(self):
        ids = {entry["id"] for entry in REGISTRY}
        for expected in ("WO-1", "WO-2", "WO-3", "WO-4", "WO-5"):
            self.assertIn(expected, ids)

    def test_failed_and_blocked_experiments_are_not_hidden(self):
        # The brief is explicit: failed/blocked experiments must appear, not be omitted.
        decisions = {entry["decision"] for entry in REGISTRY}
        self.assertIn("ABANDON", decisions)
        self.assertIn("INCONCLUSIVE", decisions)


class BuildReportTests(unittest.TestCase):
    def test_report_totals_match_the_registry(self):
        report = build_report()
        self.assertEqual(report["total_experiments"], len(REGISTRY))
        self.assertEqual(sum(report["by_decision"].values()), len(REGISTRY))

    def test_report_is_json_serializable(self):
        report = build_report()
        json.dumps(report)


class MultipleTestingBackfillTests(unittest.TestCase):
    def test_backfill_writes_one_entry_per_experiment_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "multiple_testing_log.json")
            first_pass = backfill_multiple_testing_log(REGISTRY, path)
            second_pass = backfill_multiple_testing_log(REGISTRY, path)

            self.assertEqual(first_pass, len(REGISTRY))
            self.assertEqual(second_pass, 0)
            with open(path) as handle:
                logged = json.load(handle)
            self.assertEqual(len(logged), len(REGISTRY))
            self.assertEqual({row["test_id"] for row in logged},
                             {entry["id"] for entry in REGISTRY})


if __name__ == "__main__":
    unittest.main()
