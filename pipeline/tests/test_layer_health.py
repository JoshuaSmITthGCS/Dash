import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from layer_health import (ConstantLayerError, assert_layers_vary, constant_layers,
                          layer_variance, renormalize)


class RenormalizeTest(unittest.TestCase):
    def test_missing_input_redistributes_rather_than_imputing_a_neutral(self):
        """The whole point: a dropped input's weight goes to the inputs that answered.

        Imputing 50 here would drag the score toward neutral and assert a measurement
        nobody made. Redistributing leaves the score reflecting only real evidence.
        """
        score, record = renormalize({"a": (90.0, 0.7), "b": (None, 0.3)})
        self.assertEqual(score, 90.0)
        self.assertEqual(record["inputs_dropped"], ["b"])
        self.assertEqual(record["weights_effective"], {"a": 1.0})
        self.assertAlmostEqual(record["covered_weight_fraction"], 0.7)
        self.assertAlmostEqual(record["redistributed_weight"], 0.3)

    def test_weighted_mean_over_resolved_inputs(self):
        score, record = renormalize({"a": (100.0, 0.5), "b": (0.0, 0.5), "c": (None, 1.0)})
        self.assertEqual(score, 50.0)
        self.assertEqual(record["inputs_resolved"], ["a", "b"])
        self.assertAlmostEqual(record["covered_weight_fraction"], 0.5)

    def test_nothing_resolved_publishes_nothing(self):
        score, record = renormalize({"a": (None, 0.6), "b": (None, 0.4)})
        self.assertIsNone(score)
        self.assertEqual(record["covered_weight_fraction"], 0.0)
        self.assertEqual(record["weights_effective"], {})

    def test_record_names_the_declared_weights_so_a_thin_score_is_distinguishable(self):
        """A 95 computed from 29% of the intended weight must not look like a full 95."""
        _, thin = renormalize({"a": (95.0, 0.29), "b": (None, 0.71)})
        _, full = renormalize({"a": (95.0, 0.29), "b": (95.0, 0.71)})
        self.assertNotEqual(thin["covered_weight_fraction"], full["covered_weight_fraction"])
        self.assertAlmostEqual(thin["covered_weight_fraction"], 0.29)
        self.assertAlmostEqual(full["covered_weight_fraction"], 1.0)


class LayerVarianceTest(unittest.TestCase):
    def test_identical_values_have_zero_variance(self):
        self.assertEqual(layer_variance([50.0] * 40), 0.0)

    def test_fewer_than_two_values_is_unmeasurable(self):
        self.assertIsNone(layer_variance([50.0]))
        self.assertIsNone(layer_variance([]))

    def test_booleans_are_not_treated_as_numbers(self):
        self.assertIsNone(layer_variance([True, False]))


class ConstantLayerGuardTest(unittest.TestCase):
    def rows(self, value, count=40):
        return [{"layer": {"effective_score": value}} for _ in range(count)]

    def extractors(self):
        return {"timeliness": lambda row: (row.get("layer") or {}).get("effective_score")}

    def test_the_exact_defect_this_guard_exists_for(self):
        """timeliness.effective_score was 50.0 on 40 of 40 published rows for a year."""
        with self.assertRaises(ConstantLayerError) as caught:
            assert_layers_vary(self.rows(50.0), self.extractors())
        self.assertIn("timeliness", str(caught.exception))
        self.assertIn("40 rows", str(caught.exception))

    def test_a_varying_layer_passes(self):
        rows = [{"layer": {"effective_score": float(index)}} for index in range(40)]
        assert_layers_vary(rows, self.extractors())

    def test_an_absent_layer_is_not_a_constant_layer(self):
        """Publishing None everywhere is the correct response to absent evidence."""
        assert_layers_vary(self.rows(None), self.extractors())

    def test_a_sparse_layer_is_not_flagged(self):
        """Three companies sharing a score is not evidence of a degenerate layer."""
        assert_layers_vary(self.rows(50.0, count=3), self.extractors())

    def test_constant_layers_reports_without_raising(self):
        offenders = constant_layers(self.rows(50.0), self.extractors())
        self.assertEqual([(name, count) for name, count, _ in offenders], [("timeliness", 40)])


if __name__ == "__main__":
    unittest.main()
