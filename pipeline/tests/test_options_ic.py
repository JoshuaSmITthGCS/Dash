import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation"))

import options_pit_store as ops  # noqa: E402
import options_ic as oic  # noqa: E402


class RealizedReturnTests(unittest.TestCase):
    def test_buy_call_matches_the_hand_computed_backtest_universe_formula(self):
        row = {"strategy": "buy_call", "strike": 100.0, "premium": 2.0, "entry_price": 95.0}
        # cost = 2*100 + 0.65 = 200.65; intrinsic = max(0, 110-100) = 10
        # pnl = 10*100 - 200.65 = 799.35; return = 799.35 / 200.65
        self.assertAlmostEqual(oic.realized_return(row, settle_price=110.0), 799.35 / 200.65, places=6)

    def test_buy_call_out_of_the_money_loses_the_full_premium(self):
        row = {"strategy": "buy_call", "strike": 100.0, "premium": 2.0, "entry_price": 95.0}
        self.assertAlmostEqual(oic.realized_return(row, settle_price=90.0), -1.0, places=6)

    def test_buy_put_matches_the_hand_computed_backtest_universe_formula(self):
        row = {"strategy": "buy_put", "strike": 100.0, "premium": 2.0, "entry_price": 105.0}
        self.assertAlmostEqual(oic.realized_return(row, settle_price=90.0), 799.35 / 200.65, places=6)

    def test_sell_call_matches_the_hand_computed_backtest_universe_formula(self):
        row = {"strategy": "sell_call", "strike": 100.0, "premium": 2.0, "entry_price": 95.0}
        self.assertAlmostEqual(oic.realized_return(row, settle_price=110.0), 6.9935 / 95, places=6)

    def test_sell_put_matches_the_hand_computed_backtest_universe_formula(self):
        row = {"strategy": "sell_put", "strike": 100.0, "premium": 2.0, "entry_price": 95.0}
        self.assertAlmostEqual(oic.realized_return(row, settle_price=90.0), 0.019935 - 0.1, places=6)

    def test_an_unknown_strategy_grades_nothing(self):
        row = {"strategy": "collar", "strike": 100.0, "premium": 2.0, "entry_price": 95.0}
        self.assertIsNone(oic.realized_return(row, settle_price=100.0))


class ResolvedRowsTests(unittest.TestCase):
    def test_a_position_past_expiration_with_an_observed_settle_price_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = {"ticker": "AAPL", "strategy": "buy_call", "score": 70.0, "price": 95.0,
                        "expiration": "2026-01-10", "days_to_expiration": 9,
                        "legs": [{"strike": 100.0, "mid": 2.0}]}
            ops.append_snapshot([candidate], recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)

            with patch.object(oic.pit_store, "history",
                              return_value=[{"observed_at": "2026-01-11T00:00:00+00:00", "value": 110.0}]):
                resolved = oic._resolved_rows(as_of=datetime(2026, 2, 1, tzinfo=timezone.utc), store_dir=tmp)
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["settle_price"], 110.0)

    def test_a_position_not_yet_expired_does_not_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = {"ticker": "AAPL", "strategy": "buy_call", "score": 70.0, "price": 95.0,
                        "expiration": "2026-06-01", "days_to_expiration": 9,
                        "legs": [{"strike": 100.0, "mid": 2.0}]}
            ops.append_snapshot([candidate], recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
            resolved = oic._resolved_rows(as_of=datetime(2026, 2, 1, tzinfo=timezone.utc), store_dir=tmp)
            self.assertEqual(resolved, [])

    def test_a_ticker_never_observed_by_pit_store_never_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = {"ticker": "ZZZZ", "strategy": "buy_call", "score": 70.0, "price": 95.0,
                        "expiration": "2026-01-10", "days_to_expiration": 9,
                        "legs": [{"strike": 100.0, "mid": 2.0}]}
            ops.append_snapshot([candidate], recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
            with patch.object(oic.pit_store, "history", return_value=[]):
                resolved = oic._resolved_rows(as_of=datetime(2026, 2, 1, tzinfo=timezone.utc), store_dir=tmp)
            self.assertEqual(resolved, [])


class BuildReportTests(unittest.TestCase):
    def test_no_recorded_positions_reports_accumulating(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = oic.build_report(store_dir=tmp)
            metric = report["metrics"][oic.GRADED_METRIC]
            self.assertEqual(metric["status"], "accumulating")
            self.assertIsNone(metric["mean_rank_ic"])
            self.assertEqual(report["positions_recorded"], 0)
            self.assertEqual(report["positions_resolved"], 0)

    def test_five_resolved_positions_in_one_week_form_one_period_below_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [{"ticker": t, "strategy": "sell_put", "score": score, "price": 95.0,
                          "expiration": "2026-01-10", "days_to_expiration": 9,
                          "legs": [{"strike": 100.0, "mid": 2.0}]}
                         for t, score in zip("ABCDE", (10, 20, 30, 40, 50))]
            ops.append_snapshot(candidates, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)

            settle_prices = {"A": 80.0, "B": 90.0, "C": 100.0, "D": 105.0, "E": 110.0}
            with patch.object(oic.pit_store, "history",
                              side_effect=lambda ticker, field: [
                                  {"observed_at": "2026-01-11T00:00:00+00:00", "value": settle_prices[ticker]}]):
                report = oic.build_report(as_of=datetime(2026, 2, 1, tzinfo=timezone.utc), store_dir=tmp)

            self.assertEqual(report["positions_recorded"], 5)
            self.assertEqual(report["positions_resolved"], 5)
            metric = report["metrics"][oic.GRADED_METRIC]
            self.assertEqual(metric["eligible_periods"], 1)
            self.assertEqual(metric["status"], "accumulating")
            self.assertIsNone(metric["mean_rank_ic"])

    def test_positions_expiring_in_different_weeks_of_the_same_month_form_separate_periods(self):
        # The whole point of grading by week rather than month: two batches three weeks apart,
        # still well within a single calendar month, must not be collapsed into one period -
        # that collapse is exactly what made the old monthly cadence too slow to "hone in" on
        # a screen whose picks actually resolve every 1-14 days.
        with tempfile.TemporaryDirectory() as tmp:
            def batch(expiration):
                return [{"ticker": t, "strategy": "sell_put", "score": score, "price": 95.0,
                        "expiration": expiration, "days_to_expiration": 9,
                        "legs": [{"strike": 100.0, "mid": 2.0}]}
                       for t, score in zip("ABCDE", (10, 20, 30, 40, 50))]
            ops.append_snapshot(batch("2026-01-05"), recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), store_dir=tmp)
            ops.append_snapshot(batch("2026-01-26"), recorded_at=datetime(2026, 1, 20, tzinfo=timezone.utc), store_dir=tmp)

            settle_prices = {"A": 80.0, "B": 90.0, "C": 100.0, "D": 105.0, "E": 110.0}
            with patch.object(oic.pit_store, "history",
                              side_effect=lambda ticker, field: [
                                  {"observed_at": "2026-02-01T00:00:00+00:00", "value": settle_prices[ticker]}]):
                report = oic.build_report(as_of=datetime(2026, 2, 15, tzinfo=timezone.utc), store_dir=tmp)

            self.assertEqual(report["positions_resolved"], 10)
            self.assertEqual(report["metrics"][oic.GRADED_METRIC]["eligible_periods"], 2)

    def test_periods_per_year_is_weekly_not_monthly(self):
        self.assertEqual(oic.PERIODS_PER_YEAR, 52)

    def test_attribution_by_mechanism_covers_all_three_mechanisms_with_their_own_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = oic.build_report(store_dir=tmp)
            attribution = report["attribution_by_mechanism"]
            self.assertEqual(set(attribution), {"buy", "sell_call", "sell_put"})
            self.assertEqual(set(attribution["buy"]["metrics"]), set(oic.BUY_WEIGHTS))
            self.assertEqual(set(attribution["sell_call"]["metrics"]), set(oic.SELL_CALL_WEIGHTS))
            self.assertEqual(set(attribution["sell_put"]["metrics"]), set(oic.SELL_PUT_WEIGHTS))


class MechanismPeriodsTests(unittest.TestCase):
    def test_a_buy_call_and_a_buy_put_pool_into_one_buy_mechanism_period(self):
        rows = [
            {"ticker": "A", "strategy": "buy_call", "expiration": "2026-01-05",
             "factors": {"iv_value": 0.5}, "realized_return": 0.1},
            {"ticker": "B", "strategy": "buy_put", "expiration": "2026-01-05",
             "factors": {"iv_value": -0.3}, "realized_return": -0.05},
        ]
        periods = oic._mechanism_periods(rows, oic.MECHANISM_STRATEGIES["buy"])
        self.assertEqual(len(periods), 1)
        self.assertEqual(set(periods[0]["leg_scores"]), {"A", "B"})

    def test_a_sell_put_row_is_excluded_from_the_buy_mechanism(self):
        rows = [{"ticker": "A", "strategy": "sell_put", "expiration": "2026-01-05",
                "factors": {"expected_value_pct": 0.5}, "realized_return": 0.1}]
        self.assertEqual(oic._mechanism_periods(rows, oic.MECHANISM_STRATEGIES["buy"]), [])

    def test_a_row_with_no_recorded_factors_contributes_nothing(self):
        rows = [{"ticker": "A", "strategy": "buy_call", "expiration": "2026-01-05",
                "factors": {}, "realized_return": 0.1}]
        self.assertEqual(oic._mechanism_periods(rows, oic.MECHANISM_STRATEGIES["buy"]), [])


if __name__ == "__main__":
    unittest.main()
