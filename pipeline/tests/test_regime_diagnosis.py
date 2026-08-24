import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import regime_diagnosis as regime


def flip_panel(count=120, *, flip_at=60, names=60, seed=5, noise=0.03):
    """Synthetic panel whose signal genuinely reverses sign at ``flip_at``: before it the
    composite anti-predicts, after it it predicts -- the planted ground truth for the break
    scanner. Dates advance monthly so year bucketing and boundary arithmetic are exercised.
    """
    generator = random.Random(seed)
    periods = []
    for index in range(count):
        year, month = 2016 + index // 12, index % 12 + 1
        direction = -1.0 if index < flip_at else 1.0
        leg_scores, forwards = {}, {}
        for position in range(names):
            ticker = f"T{position}"
            true_score = generator.uniform(0, 100)
            leg_scores[ticker] = {"good": true_score, "bad": generator.uniform(0, 100)}
            forwards[ticker] = direction * (true_score - 50) / 50 * 0.02 + generator.gauss(0, noise)
        periods.append({"date": f"{year}-{month:02d}-01", "leg_scores": leg_scores,
                        "forward_returns": forwards})
    return {"periods": periods, "leg_weights": {"good": 0.8, "bad": 0.2}}


def steady_panel(count=120, *, names=60, seed=6, noise=0.03):
    """Same construction, no flip -- the null case the permutation test must not reject."""
    return flip_panel(count, flip_at=0, names=names, seed=seed, noise=noise)


class WelchTTests(unittest.TestCase):
    def test_a_clear_mean_difference_produces_a_large_positive_t(self):
        t = regime.welch_t([-1.0, -1.1, -0.9, -1.05], [1.0, 1.1, 0.9, 1.05])
        self.assertGreater(t, 10)

    def test_degenerate_segments_return_none(self):
        self.assertIsNone(regime.welch_t([1.0], [1.0, 2.0]))
        self.assertIsNone(regime.welch_t([1.0, 1.0], [2.0, 2.0]))  # zero variance both sides


class BestBreakTests(unittest.TestCase):
    def test_finds_a_planted_flip_within_a_few_periods(self):
        panel = flip_panel(flip_at=60)
        _dates, ics = regime.champion_ic_series(panel["periods"], panel["leg_weights"])
        index, stat = regime.best_break(ics, min_segment=24)
        self.assertTrue(abs(index - 60) <= 3, index)
        self.assertGreater(abs(stat), 5)

    def test_too_short_a_series_returns_none(self):
        self.assertEqual(regime.best_break([0.1] * 10, min_segment=24), (None, None))


class PermutationTests(unittest.TestCase):
    def test_a_real_flip_is_significant(self):
        panel = flip_panel(flip_at=60)
        _dates, ics = regime.champion_ic_series(panel["periods"], panel["leg_weights"])
        _index, stat = regime.best_break(ics, min_segment=24)
        p = regime.permutation_p_value(ics, stat, min_segment=24, permutations=200, seed=1)
        self.assertLess(p, 0.05)

    def test_a_steady_signal_is_not_declared_a_break(self):
        panel = steady_panel()
        _dates, ics = regime.champion_ic_series(panel["periods"], panel["leg_weights"])
        _index, stat = regime.best_break(ics, min_segment=24)
        p = regime.permutation_p_value(ics, stat, min_segment=24, permutations=200, seed=1)
        self.assertGreater(p, 0.05)


class BoundaryTests(unittest.TestCase):
    def test_median_yahoo_native_start_is_computed_from_cache_files(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            for name, oldest in (("AAA", "2024-06-30"), ("BBB", "2024-09-30"),
                                 ("CCC", "2025-03-31")):
                with open(os.path.join(cache_dir, f"{name}.json"), "w") as handle:
                    json.dump({"income": {"periods": ["2026-06-30", oldest]}}, handle)
            boundary, measured = regime.yahoo_native_start(cache_dir, report_lag_days=45)
        self.assertEqual(measured, 3)
        # Median oldest quarter is BBB's 2024-09-30; +45 days lag = 2024-11-14.
        self.assertEqual(boundary, "2024-11-14")

    def test_an_empty_or_missing_cache_reports_none(self):
        self.assertEqual(regime.yahoo_native_start("/nonexistent"), (None, 0))


class DiagnoseTests(unittest.TestCase):
    def test_planted_flip_far_from_boundary_reads_regime_break(self):
        panel = flip_panel(flip_at=60)  # break ~2021-01; fabricated boundary ~2024-11
        with tempfile.TemporaryDirectory() as cache_dir:
            with open(os.path.join(cache_dir, "AAA.json"), "w") as handle:
                json.dump({"income": {"periods": ["2024-09-30"]}}, handle)
            result = regime.diagnose(panel, cache_dir=cache_dir, permutations=200, seed=1)
        self.assertEqual(result["verdict"], "REGIME_BREAK")
        self.assertGreater(result["data_source_boundary"]["months_from_break"], 3)
        self.assertLess(result["break"]["mean_ic_before"], 0)
        self.assertGreater(result["break"]["mean_ic_after"], 0)

    def test_planted_flip_at_the_boundary_reads_data_artifact(self):
        panel = flip_panel(flip_at=60)  # break lands ~2021-01-01
        with tempfile.TemporaryDirectory() as cache_dir:
            with open(os.path.join(cache_dir, "AAA.json"), "w") as handle:
                json.dump({"income": {"periods": ["2020-11-30"]}}, handle)  # +45d ~ 2021-01-14
            result = regime.diagnose(panel, cache_dir=cache_dir, permutations=200, seed=1)
        self.assertEqual(result["verdict"], "DATA_ARTIFACT_SUSPECTED")
        self.assertLessEqual(result["data_source_boundary"]["months_from_break"], 3)

    def test_steady_signal_reads_no_significant_break(self):
        panel = steady_panel()
        with tempfile.TemporaryDirectory() as cache_dir:
            result = regime.diagnose(panel, cache_dir=cache_dir, permutations=200, seed=1)
        self.assertEqual(result["verdict"], "NO_SIGNIFICANT_BREAK")

    def test_yearly_table_and_per_leg_break_are_reported(self):
        panel = flip_panel(flip_at=60)
        with tempfile.TemporaryDirectory() as cache_dir:
            result = regime.diagnose(panel, cache_dir=cache_dir, permutations=100, seed=1)
        self.assertEqual(len(result["yearly"]), 10)
        legs = result["per_leg_at_break"]
        self.assertIn("good", legs)
        # The planted flip lives in the predictive leg, visible standalone too.
        self.assertLess(legs["good"]["mean_ic_before"], 0)
        self.assertGreater(legs["good"]["mean_ic_after"], 0)

    def test_too_short_a_panel_reports_an_error_rather_than_guessing(self):
        panel = flip_panel(count=20, flip_at=10)
        result = regime.diagnose(panel, cache_dir="/nonexistent", permutations=10)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
