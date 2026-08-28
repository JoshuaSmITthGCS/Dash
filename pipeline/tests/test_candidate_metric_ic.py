import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import validation.candidate_metric_ic as cmi


def obs(ticker, date, **values):
    return {"ticker": ticker, "observed_at": date, "values": values}


class SeriesByTickerTests(unittest.TestCase):
    def test_collects_and_sorts_one_field_per_ticker(self):
        rows = [obs("AAA", "2025-03-01", price=10.0), obs("AAA", "2025-01-01", price=8.0),
                obs("BBB", "2025-01-01", price=20.0)]
        series = cmi._series_by_ticker(rows, "price")
        self.assertEqual(series["AAA"], [("2025-01-01", 8.0), ("2025-03-01", 10.0)])
        self.assertEqual(series["BBB"], [("2025-01-01", 20.0)])

    def test_non_numeric_and_missing_values_are_skipped(self):
        rows = [obs("AAA", "2025-01-01", inventory_correction_flag="lean"),
                obs("AAA", "2025-01-02", price=None)]
        self.assertEqual(cmi._series_by_ticker(rows, "inventory_correction_flag"), {})
        self.assertEqual(cmi._series_by_ticker(rows, "price"), {})


class ValueAsOfTests(unittest.TestCase):
    def test_returns_the_latest_value_at_or_before_the_cutoff(self):
        series = [("2025-01-01", 1.0), ("2025-02-01", 2.0), ("2025-03-01", 3.0)]
        self.assertEqual(cmi._value_as_of(series, "2025-02-15"), ("2025-02-01", 2.0))

    def test_none_before_the_first_observation(self):
        series = [("2025-02-01", 2.0)]
        self.assertIsNone(cmi._value_as_of(series, "2025-01-01"))


class CandidateMetricRankIcTests(unittest.TestCase):
    def test_no_history_reports_accumulating_with_a_clear_note(self):
        result = cmi.candidate_metric_rank_ic("return_on_tangible_common_equity", rows=[])
        self.assertEqual(result["summary"]["status"], "accumulating")
        self.assertEqual(result["periods"], [])
        self.assertIn("No pit_store history", result["note"])

    def test_a_clean_positive_relationship_reads_as_a_positive_rank_ic(self):
        # Higher ROTCE this period -> higher forward return, across 12 names, one period.
        rows = []
        for i in range(12):
            rows.append(obs(f"T{i}", "2025-01-01", return_on_tangible_common_equity=i * 0.01,
                            price=100.0))
            rows.append(obs(f"T{i}", "2025-04-01", price=100.0 + i * 2.0))
        result = cmi.candidate_metric_rank_ic(
            "return_on_tangible_common_equity", horizon_days=90, minimum_names=10, rows=rows)
        self.assertEqual(len(result["periods"]), 1)
        self.assertAlmostEqual(result["periods"][0]["rank_ic"], 1.0, places=4)

    def test_periods_below_minimum_names_are_skipped(self):
        rows = []
        for i in range(3):  # below minimum_names=10
            rows.append(obs(f"T{i}", "2025-01-01", return_on_tangible_common_equity=i * 0.01,
                            price=100.0))
            rows.append(obs(f"T{i}", "2025-04-01", price=105.0))
        result = cmi.candidate_metric_rank_ic(
            "return_on_tangible_common_equity", horizon_days=90, minimum_names=10, rows=rows)
        self.assertEqual(result["periods"], [])

    def test_a_ticker_missing_the_forward_price_is_excluded_not_zero_filled(self):
        rows = [obs(f"T{i}", "2025-01-01", return_on_tangible_common_equity=i * 0.01, price=100.0)
                for i in range(12)]
        # No 2025-04-01 price rows at all -> nothing has a forward return.
        result = cmi.candidate_metric_rank_ic(
            "return_on_tangible_common_equity", horizon_days=90, minimum_names=10, rows=rows)
        self.assertEqual(result["periods"], [])

    def test_a_stale_reading_is_not_reused_as_a_new_period(self):
        # T0 is observed on both dates; T1..T11 only on the first -- the second date's cross
        # section has just one name actually observed there, so it must not form a period.
        rows = []
        for i in range(12):
            rows.append(obs(f"T{i}", "2025-01-01", return_on_tangible_common_equity=i * 0.01,
                            price=100.0))
            rows.append(obs(f"T{i}", "2025-04-01", price=100.0 + i * 2.0))
        rows.append(obs("T0", "2025-02-01", return_on_tangible_common_equity=0.5, price=110.0))
        result = cmi.candidate_metric_rank_ic(
            "return_on_tangible_common_equity", horizon_days=90, minimum_names=10, rows=rows)
        self.assertEqual(len(result["periods"]), 1)
        self.assertEqual(result["periods"][0]["period_start"], "2025-01-01")


if __name__ == "__main__":
    unittest.main()
