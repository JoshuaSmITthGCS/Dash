import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rescore import backfill_row_observations


class BackfillRowObservationsTests(unittest.TestCase):
    def test_backfills_statement_derived_and_quote_metrics_from_flat_fields(self):
        row = {
            "ticker": "TEST", "data_fetched_at": "2026-08-03T00:00:00+00:00",
            "altman_z": 10.13, "accruals_ratio": -0.04, "asset_growth": 0.01,
            "statement_periods": ["2025-12-31", "2024-12-31"],
            "debt_to_equity": 0.02, "return_on_equity": 0.133, "profit_margin": 0.1892,
            "price_to_sales": 3.45, "free_cash_flow_yield": 0.0319,
            "observations": {"forward_pe": [{"value": 15.8}]},
        }
        backfill_row_observations(row)
        for metric_id in ("altman_z", "accruals_ratio", "asset_growth", "debt_to_equity",
                          "return_on_equity", "profit_margin", "price_to_sales", "free_cash_flow_yield"):
            with self.subTest(metric_id=metric_id):
                self.assertIn(metric_id, row["observations"])
        # Pre-existing observations (from a real fetch) are kept, not overwritten.
        self.assertEqual(row["observations"]["forward_pe"], [{"value": 15.8}])

    def test_does_not_invent_an_observation_for_a_metric_the_row_never_had(self):
        row = {"ticker": "TEST", "data_fetched_at": "2026-08-03T00:00:00+00:00"}
        backfill_row_observations(row)
        self.assertEqual(row["observations"], {})

    def test_does_not_duplicate_an_observation_already_present(self):
        existing = [{"value": 0.5, "source": "yahoo"}]
        row = {"ticker": "TEST", "return_on_equity": 0.5, "observations": {"return_on_equity": existing}}
        backfill_row_observations(row)
        self.assertEqual(row["observations"]["return_on_equity"], existing)


if __name__ == "__main__":
    unittest.main()
