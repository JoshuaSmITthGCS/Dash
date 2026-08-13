import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import score_calibration as sc
from data_coverage import data_coverage_components, historical_calibration_component


def rows(count, score, outcome=0.02):
    return [{"score": score, sc.TARGET_FIELD: outcome} for _ in range(count)]


def mixed(count, score, positive_share=0.6):
    positives = int(count * positive_share)
    return [{"score": score, sc.TARGET_FIELD: 0.03 if index < positives else -0.02}
            for index in range(count)]


class GateTests(unittest.TestCase):
    """The whole point of this module is that it refuses to publish without evidence."""

    def test_an_empty_history_reports_insufficient_data_not_a_number(self):
        report = sc.build_report([])
        self.assertEqual(report["status"], "insufficient_data")
        self.assertEqual(report["observations"], 0)
        self.assertFalse(report["publishable_to_confidence_detail"])

    def test_every_fixed_band_is_reported_even_when_empty(self):
        """Silently omitting an empty band would hide that it was never measured."""
        bands = sc.build_report([])["fixed_score_bands"]
        self.assertEqual(len(bands), len(sc.FIXED_BANDS))
        for bucket in bands:
            self.assertEqual(bucket["status"], "insufficient_data")
            self.assertEqual(bucket["observations"], 0)

    def test_a_bucket_one_observation_short_still_refuses(self):
        bucket = sc.summarize_bucket("test", rows(sc.MINIMUM_BUCKET_OBSERVATIONS - 1, 82.0))
        self.assertEqual(bucket["status"], "insufficient_data")
        self.assertEqual(bucket["shortfall"], 1)

    def test_a_bucket_at_the_minimum_is_measured(self):
        bucket = sc.summarize_bucket("test", mixed(sc.MINIMUM_BUCKET_OBSERVATIONS, 82.0))
        self.assertEqual(bucket["status"], "measured")
        self.assertEqual(bucket["observations"], sc.MINIMUM_BUCKET_OBSERVATIONS)

    def test_observations_missing_an_outcome_do_not_count_toward_the_minimum(self):
        incomplete = [{"score": 82.0, sc.TARGET_FIELD: None}
                      for _ in range(sc.MINIMUM_BUCKET_OBSERVATIONS)]
        self.assertEqual(sc.summarize_bucket("test", incomplete)["status"], "insufficient_data")


class MeasurementTests(unittest.TestCase):
    def test_beat_sector_rate_counts_positive_residual_returns(self):
        bucket = sc.summarize_bucket("test", mixed(100, 82.0, positive_share=0.6))
        self.assertAlmostEqual(bucket["beat_sector_rate"], 0.6)

    def test_intervals_are_reported_alongside_every_point_estimate(self):
        bucket = sc.summarize_bucket("test", mixed(100, 82.0))
        self.assertEqual(len(bucket["mean_confidence_interval_95"]), 2)
        self.assertLess(bucket["mean_confidence_interval_95"][0],
                        bucket["mean_residual_return"])
        self.assertGreater(bucket["beat_sector_confidence_interval_95"][1],
                           bucket["beat_sector_rate"])

    def test_adaptive_buckets_split_by_equal_count_not_equal_width(self):
        observations = [{"score": float(index), sc.TARGET_FIELD: 0.01}
                        for index in range(100)]
        buckets = sc.adaptive_buckets(observations, count=5)
        self.assertEqual(len(buckets), 5)
        self.assertTrue(all(bucket["observations"] == 20 for bucket in buckets))

    def test_a_score_band_containing_data_becomes_measured_while_others_do_not(self):
        report = sc.build_report(mixed(60, 82.0))
        by_bucket = {bucket["bucket"]: bucket for bucket in report["fixed_score_bands"]}
        self.assertEqual(by_bucket["80+"]["status"], "measured")
        self.assertEqual(by_bucket["70-74"]["status"], "insufficient_data")
        self.assertTrue(report["publishable_to_confidence_detail"])


class ConfidenceWiringTests(unittest.TestCase):
    def test_calibration_stays_null_without_a_qualified_report(self):
        detail = data_coverage_components({"score": 82.0, "data_coverage": 0.9})
        self.assertIsNone(detail["components"]["historical_calibration"])
        self.assertTrue(any("insufficient prospective calibration" in item
                            for item in detail["limitations"]))

    def test_an_unqualified_calibration_report_changes_nothing(self):
        detail = data_coverage_components({"score": 82.0, "data_coverage": 0.9},
                                       calibration=sc.build_report([]))
        self.assertIsNone(detail["components"]["historical_calibration"])

    def test_a_qualified_report_populates_the_matching_band(self):
        calibration = sc.build_report(mixed(60, 82.0, positive_share=0.65))
        detail = data_coverage_components({"score": 82.0, "data_coverage": 0.9},
                                       calibration=calibration)
        self.assertAlmostEqual(detail["components"]["historical_calibration"], 0.65, places=2)
        self.assertFalse(any("insufficient prospective calibration" in item
                             for item in detail["limitations"]))

    def test_a_score_outside_every_measured_band_stays_null(self):
        calibration = sc.build_report(mixed(60, 82.0))
        self.assertIsNone(historical_calibration_component({"score": 71.0}, calibration))

    def test_a_row_without_a_score_stays_null(self):
        calibration = sc.build_report(mixed(60, 82.0))
        self.assertIsNone(historical_calibration_component({"score": None}, calibration))

    def test_coverage_states_it_is_not_a_probability_of_rising(self):
        """The single most important label in the product."""
        detail = data_coverage_components({"score": 82.0, "data_coverage": 0.9})
        self.assertIn("not a probability that the stock rises", detail["interpretation"])

    def test_coverage_never_calls_itself_a_reliability_measure(self):
        """It is a completeness ratio. Naming it confidence is the defect this fixes."""
        detail = data_coverage_components({"score": 82.0, "data_coverage": 0.9})
        self.assertIn("not a reliability score", detail["interpretation"])
        self.assertIn("data_coverage", detail)
        self.assertNotIn("confidence", detail)


class LiveHarnessTests(unittest.TestCase):
    def test_the_current_harness_supplies_no_closed_observations(self):
        """Records the true state: 0 of 24 periods, so nothing is calibrated."""
        report = sc.build_report(sc.observations_from_harness())
        self.assertEqual(report["status"], "insufficient_data")
        self.assertFalse(report["publishable_to_confidence_detail"])
        self.assertIn("EDGAR", report["what_would_populate_this"])

    def test_calibration_reads_the_harness_primary_path_not_the_raw_diagnostic(self):
        """Guards a silent mismatch: with no data, reading the wrong path also returns [].

        The harness keeps a calendar-day, raw-return diagnostic beside the preregistered
        sector-residual/session path. Calibrating against the diagnostic would attach outcome
        statistics to a label the contract does not preregister -- and because both return
        nothing while the store is empty, the mistake is invisible until real data arrives.
        This pins the field and the horizon unit instead.
        """
        import inspect

        source = inspect.getsource(sc.observations_from_harness)
        self.assertIn("_forward_periods_sessions", source)
        self.assertNotIn("_forward_periods(", source)
        self.assertEqual(sc.TARGET_FIELD, "sector_residual_return")

    def test_target_field_matches_the_harness_contract(self):
        """A rename in the harness must break this loudly, not silently zero the buckets."""
        from validation.ic_harness import sector_residual_returns

        residualized = sector_residual_returns([
            {"ticker": t, "score": 60.0, "forward_return": r, "sector": "Tech"}
            for t, r in (("A", 0.10), ("B", 0.20), ("C", 0.30))
        ])
        self.assertIn(sc.TARGET_FIELD, residualized[0])



class GateConsistencyTests(unittest.TestCase):
    """The gate and its consumer must never disagree about what is measured."""

    def test_publishability_is_gated_on_the_bands_confidence_actually_reads(self):
        # 60 observations all at one score: the 80+ band measures fine, but every equal-count
        # quintile holds only 12 and starves. Gating on the quintiles would flag the report
        # unpublishable while confidence.py could still read a measured band out of it.
        report = sc.build_report(mixed(60, 82.0))
        measured_fixed = [b for b in report["fixed_score_bands"] if b["status"] == "measured"]
        measured_adaptive = [b for b in report["adaptive_buckets"] if b["status"] == "measured"]

        self.assertTrue(measured_fixed)
        self.assertFalse(measured_adaptive)
        self.assertTrue(report["publishable_to_confidence_detail"])

    def test_a_publishable_report_always_has_a_readable_band(self):
        for observations in (mixed(60, 82.0), mixed(40, 71.0), mixed(35, 50.0)):
            report = sc.build_report(observations)
            with self.subTest(n=len(observations)):
                if report["publishable_to_confidence_detail"]:
                    score = observations[0]["score"]
                    self.assertIsNotNone(
                        historical_calibration_component({"score": score}, report))


if __name__ == "__main__":
    unittest.main()
