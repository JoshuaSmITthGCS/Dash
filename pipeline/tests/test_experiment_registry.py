import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import experiment_registry as er
from validation.ic_harness import CONFIG, research_trial_count


class EntryValidationTests(unittest.TestCase):
    BASE = dict(id="x", hypothesis="h", category="diagnostic", result="supported",
                decision="promote", reason="r")

    def test_a_valid_entry_round_trips_its_fields(self):
        item = er.entry(**self.BASE, number_of_variants_tested=3)
        self.assertEqual(item["id"], "x")
        self.assertEqual(item["number_of_variants_tested"], 3)
        self.assertEqual(item["configuration"], {})
        self.assertEqual(item["artifacts"], [])

    def test_an_unknown_category_result_or_decision_is_rejected(self):
        for field, value in (("category", "vibes"), ("result", "great"),
                             ("decision", "ship_it")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    er.entry(**{**self.BASE, field: value})

    def test_a_negative_variant_count_is_rejected(self):
        with self.assertRaises(ValueError):
            er.entry(**self.BASE, number_of_variants_tested=-1)


class RegistryTests(unittest.TestCase):
    def test_every_recorded_experiment_is_well_formed(self):
        for item in er.RECORDED:
            with self.subTest(experiment=item["id"]):
                self.assertIn(item["category"], er.CATEGORIES)
                self.assertIn(item["result"], er.RESULTS)
                self.assertIn(item["decision"], er.DECISIONS)
                self.assertTrue(item["hypothesis"])
                self.assertTrue(item["reason"])

    def test_duplicate_ids_are_rejected(self):
        duplicated = [*er.RECORDED, er.RECORDED[0]]
        with self.assertRaises(ValueError):
            er.build_report(duplicated)

    def test_failed_and_blocked_experiments_are_recorded_not_omitted(self):
        """An absent experiment and a failed one are different facts."""
        results = {item["result"] for item in er.RECORDED}
        self.assertIn("rejected", results)
        self.assertIn("blocked", results)

    def test_nothing_has_been_promoted_to_champion(self):
        """Governance: every change so far is a fix or a shadow, not a promotion."""
        self.assertEqual(er.build_report()["summary"]["promoted_to_champion"], [])

    def test_summary_counts_match_the_entries(self):
        report = er.build_report()
        summary = report["summary"]
        self.assertEqual(summary["experiments"], len(er.RECORDED))
        self.assertEqual(sum(len(ids) for ids in summary["by_result"].values()),
                         len(er.RECORDED))
        self.assertEqual(summary["total_variants_tested"],
                         sum(item["number_of_variants_tested"] for item in er.RECORDED))


class DeflationTrialCountTests(unittest.TestCase):
    """Understating the trial count is the standard way a deflated Sharpe is re-inflated."""

    def test_the_harness_deflates_against_the_whole_research_programme(self):
        self.assertEqual(research_trial_count(), er.total_variants_tested())

    def test_the_registry_count_exceeds_the_configured_shadow_strategy_count(self):
        self.assertGreater(er.total_variants_tested(), CONFIG["shadow_strategy_trials"])

    def test_the_count_is_a_floor_never_a_reduction(self):
        self.assertGreaterEqual(research_trial_count(), CONFIG["shadow_strategy_trials"])

    def test_total_is_the_sum_of_the_entries(self):
        entries = [er.entry(id=f"e{index}", hypothesis="h", category="diagnostic",
                            result="supported", decision="promote", reason="r",
                            number_of_variants_tested=index)
                   for index in range(5)]
        self.assertEqual(er.total_variants_tested(entries), 10)


if __name__ == "__main__":
    unittest.main()
