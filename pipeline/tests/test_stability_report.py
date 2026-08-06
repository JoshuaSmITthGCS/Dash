import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from stability_report import (compute_stability_report, decompose_score_delta,
                              load_refresh_rows, rank_turnover)


def _row(ticker, refresh_id, score, confidence, metrics, published=True):
    return {
        "ticker": ticker, "refresh_id": refresh_id, "published_research": published,
        "scores": {"champion": score}, "confidence": {"champion": confidence},
        "normalized_metric_scores": {"champion": metrics},
    }


class RankTurnoverTests(unittest.TestCase):
    def test_identical_lists_have_zero_turnover(self):
        self.assertEqual(rank_turnover(["A", "B", "C"], ["A", "B", "C"]), 0.0)

    def test_complete_replacement_has_full_turnover(self):
        self.assertEqual(rank_turnover(["A", "B"], ["C", "D"]), 1.0)

    def test_partial_replacement_is_fractional(self):
        self.assertEqual(rank_turnover(["A", "B", "C", "D"], ["A", "B", "X", "Y"]), 0.5)

    def test_empty_previous_list_is_none_not_a_divide_by_zero(self):
        self.assertIsNone(rank_turnover([], ["A"]))


class ScoreDeltaDecompositionTests(unittest.TestCase):
    def test_a_metric_flipping_from_missing_to_present_is_availability_driven(self):
        previous = _row("AAPL", "r1", 60.0, 0.5, {"roic": None, "peg": 80.0})
        current = _row("AAPL", "r2", 68.0, 0.6, {"roic": 90.0, "peg": 80.0})

        delta = decompose_score_delta(previous, current, "champion")

        self.assertEqual(delta["metrics_with_availability_change"], ["roic"])
        self.assertEqual(delta["metrics_with_value_change"], [])
        self.assertEqual(delta["score_delta"], 8.0)

    def test_a_metric_changing_value_without_flipping_is_a_value_change(self):
        previous = _row("AAPL", "r1", 60.0, 0.5, {"peg": 70.0})
        current = _row("AAPL", "r2", 65.0, 0.5, {"peg": 80.0})

        delta = decompose_score_delta(previous, current, "champion")

        self.assertEqual(delta["metrics_with_value_change"], ["peg"])
        self.assertEqual(delta["metrics_with_availability_change"], [])

    def test_confidence_delta_is_tracked_alongside_score_delta(self):
        previous = _row("AAPL", "r1", 60.0, 0.40, {})
        current = _row("AAPL", "r2", 60.0, 0.70, {})

        delta = decompose_score_delta(previous, current, "champion")

        self.assertAlmostEqual(delta["confidence_delta"], 0.30)


class LoadRefreshRowsTests(unittest.TestCase):
    def test_non_standard_refresh_ids_are_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-01-01.jsonl")
            with open(path, "w") as handle:
                handle.write(json.dumps(_row("AAPL", "advisor-2026-01-01T00:00:00+00:00", 60, 0.5, {})) + "\n")
                handle.write(json.dumps(_row("AAPL", "some-old-test-fixture", 60, 0.5, {})) + "\n")

            by_refresh = load_refresh_rows(tmp)

            self.assertEqual(set(by_refresh), {"advisor-2026-01-01T00:00:00+00:00"})

    def test_require_prefix_none_includes_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-01-01.jsonl")
            with open(path, "w") as handle:
                handle.write(json.dumps(_row("AAPL", "some-old-test-fixture", 60, 0.5, {})) + "\n")

            by_refresh = load_refresh_rows(tmp, require_prefix=None)

            self.assertEqual(set(by_refresh), {"some-old-test-fixture"})


class ComputeStabilityReportTests(unittest.TestCase):
    def test_fewer_than_two_refreshes_reports_insufficient_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-01-01.jsonl")
            with open(path, "w") as handle:
                handle.write(json.dumps(_row("AAPL", "advisor-2026-01-01T00:00:00+00:00", 60, 0.5, {})) + "\n")

            report = compute_stability_report(pit_dir=tmp)

            self.assertEqual(report["status"], "insufficient_history")

    def test_a_universe_wide_availability_flip_is_visible_in_the_report(self):
        # Mirrors the real 2026-08-06 incident: every shared ticker's fundamentals metrics
        # flip from present to missing in one transition, and the report must surface it as
        # an availability-driven spike, not just a generic score change.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-01-01.jsonl")
            rows = []
            for i in range(50):
                ticker = f"T{i:02d}"
                rows.append(_row(ticker, "advisor-2026-01-01T00:00:00+00:00", 70.0 - i * 0.1, 0.8,
                                 {"roic": 90.0}))
                rows.append(_row(ticker, "advisor-2026-01-01T01:00:00+00:00", 55.0 - i * 0.1, 0.4,
                                 {"roic": None}))
            with open(path, "w") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            report = compute_stability_report(pit_dir=tmp, top_ns=(40,))

            transition = report["transitions"][0]
            self.assertEqual(transition["tickers_with_availability_driven_change_pct"], 1.0)
            self.assertGreater(transition["mean_abs_score_delta"], 10)


if __name__ == "__main__":
    unittest.main()
