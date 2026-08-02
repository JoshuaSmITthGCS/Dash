import os
import random
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import evaluate_signal
import pit_store


class ForwardReturnTests(unittest.TestCase):
    def test_it_uses_the_first_observation_past_the_horizon(self):
        series = {"2026-01-01": 100.0, "2026-01-15": 105.0, "2026-02-01": 110.0}
        # A 21-day horizon skips the 14-day observation and lands on the February one.
        self.assertAlmostEqual(
            evaluate_signal.forward_return(series, "2026-01-01", 21), 0.10, places=6)

    def test_it_returns_nothing_when_the_horizon_is_not_covered(self):
        series = {"2026-01-01": 100.0, "2026-01-08": 101.0}
        self.assertIsNone(evaluate_signal.forward_return(series, "2026-01-01", 60))

    def test_an_unknown_start_date_yields_nothing(self):
        self.assertIsNone(evaluate_signal.forward_return({"2026-01-01": 100.0},
                                                         "2025-06-01", 21))

    def test_unparseable_dates_are_ignored_rather_than_raising(self):
        series = {"2026-01-01": 100.0, "not-a-date": 200.0, "2026-03-01": 120.0}
        self.assertAlmostEqual(
            evaluate_signal.forward_return(series, "2026-01-01", 21), 0.20, places=6)


class ObservationDateTests(unittest.TestCase):
    def test_dates_below_the_minimum_breadth_are_excluded(self):
        rows = [{"observation_date": "2026-01-01", "ticker": f"T{i}"} for i in range(5)]
        rows += [{"observation_date": "2026-02-01", "ticker": f"T{i}"} for i in range(25)]
        dates = evaluate_signal.observation_dates(rows, minimum_names=20)
        self.assertEqual(dates, ["2026-02-01"])


class BuildPeriodsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="pit-eval-")
        self._original = pit_store.PIT_DIR
        pit_store.PIT_DIR = self.directory

    def tearDown(self):
        pit_store.PIT_DIR = self._original
        shutil.rmtree(self.directory, ignore_errors=True)

    def _populate(self, weeks=14, names=30, seed=19):
        generator = random.Random(seed)
        start = date(2026, 1, 5)
        quality = {f"T{index}": generator.uniform(0.02, 0.30) for index in range(names)}
        price = {ticker: 100.0 for ticker in quality}
        for week in range(weeks):
            stamp = (start + timedelta(days=7 * week)).isoformat() + "T12:00:00+00:00"
            pit_store.append_snapshot([
                {"ticker": ticker, "price": round(price[ticker], 2), "sector": "Technology",
                 "return_on_invested_capital": round(roic, 4), "forward_pe": 22,
                 "profit_margin": 0.15, "revenue_growth": 0.08}
                for ticker, roic in quality.items()
            ], observed_at=stamp, source="test")
            for ticker, roic in quality.items():
                # Higher-quality names drift up; everything carries noise.
                price[ticker] *= 1 + (roic - 0.16) * 0.05 + generator.gauss(0, 0.01)

    def test_an_empty_store_says_so_instead_of_inventing_a_verdict(self):
        periods, problem = evaluate_signal.build_periods(21, 20)
        self.assertEqual(periods, [])
        self.assertIn("empty", problem)

    def test_it_reports_when_no_period_has_enough_forward_coverage(self):
        self._populate(weeks=2)
        periods, problem = evaluate_signal.build_periods(horizon_days=365, minimum_names=20)
        self.assertEqual(periods, [])
        self.assertIsNotNone(problem)

    def test_it_builds_scored_periods_paired_with_realized_returns(self):
        self._populate()
        periods, problem = evaluate_signal.build_periods(horizon_days=21, minimum_names=20)
        self.assertIsNone(problem)
        self.assertGreater(len(periods), 5)
        first = periods[0]
        self.assertEqual(set(first["scores"]), set(first["forward_returns"]))

    def test_a_planted_relationship_is_recovered(self):
        # End-to-end sanity: quality genuinely drives the forward move here, so the harness
        # must find a positive information coefficient. If it cannot detect a signal that is
        # real by construction, it cannot be trusted to reject one that is not.
        import evaluation
        self._populate()
        periods, _ = evaluate_signal.build_periods(horizon_days=21, minimum_names=20)
        report = evaluation.evaluate_candidate(periods, trials=12)
        self.assertGreater(report["ic"]["mean_ic"], 0.05)
        self.assertTrue(report["ic"]["meaningful"])

    def test_scores_are_reconstructed_only_from_prior_observations(self):
        self._populate(weeks=4)
        rows = pit_store._read(pit_store.OBSERVATIONS)
        # A date before the store begins can produce no score at all.
        self.assertIsNone(evaluate_signal.score_as_of("T0", "2025-01-01", rows))
        self.assertIsNotNone(evaluate_signal.score_as_of("T0", "2026-01-05", rows))


if __name__ == "__main__":
    unittest.main()
