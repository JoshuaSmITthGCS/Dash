import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import sector_attribution as sa
import stress_scenarios as ss


def daily_prices(start, days, daily_return):
    import datetime
    start_date = datetime.date.fromisoformat(start)
    rows, value = [], 1.0
    for index in range(days):
        rows.append({"date": (start_date + datetime.timedelta(days=index)).isoformat(),
                     "total_return_index": value})
        value *= 1 + daily_return
    return rows


def snapshots(count, *, strategy_weights, benchmark_weights, start="2026-08-01"):
    import datetime
    start_date = datetime.date.fromisoformat(start)
    return [
        {"as_of": (start_date + datetime.timedelta(days=index)).isoformat() + "T00:00:00",
         "strategy_sector_weights": strategy_weights, "benchmark_sector_weights": benchmark_weights}
        for index in range(count)
    ]


class AllocationEffectTests(unittest.TestCase):
    def test_none_below_the_minimum_snapshot_count(self):
        history = snapshots(sa.MINIMUM_SNAPSHOTS - 1, strategy_weights={"technology": 0.5},
                            benchmark_weights={"technology": 0.3})
        self.assertIsNone(sa.allocation_effect(history))

    def test_none_when_snapshots_do_not_span_more_than_one_day(self):
        history = [{"as_of": "2026-08-01T00:00:00", "strategy_sector_weights": {"technology": 0.5},
                   "benchmark_sector_weights": {"technology": 0.3}}] * sa.MINIMUM_SNAPSHOTS
        self.assertIsNone(sa.allocation_effect(history))

    def test_overweighting_the_best_performing_sector_is_a_positive_effect(self):
        # Technology (XLK) rallies hard; the book is heavily overweight it, underweight
        # everything else equally. Allocation effect must come out positive.
        history = snapshots(6, strategy_weights={"technology": 0.6},
                            benchmark_weights={"technology": 0.2})
        etf_prices = {
            "SPY": daily_prices("2026-08-01", 10, 0.001),
            "XLK": daily_prices("2026-08-01", 10, 0.01),
        }
        with mock.patch.object(ss, "read_etf_prices",
                               side_effect=lambda ticker, etf_dir=None: etf_prices.get(ticker)):
            result = sa.allocation_effect(history)
        self.assertIsNotNone(result)
        self.assertGreater(result["total_allocation_effect_pct"], 0)
        self.assertGreater(result["sectors"]["technology"]["allocation_effect_pct"], 0)

    def test_a_sector_with_no_priced_etf_is_reported_without_a_fabricated_effect(self):
        history = snapshots(6, strategy_weights={"real_estate": 0.3},
                            benchmark_weights={"real_estate": 0.1})
        etf_prices = {"SPY": daily_prices("2026-08-01", 10, 0.001)}  # XLRE missing on purpose
        with mock.patch.object(ss, "read_etf_prices",
                               side_effect=lambda ticker, etf_dir=None: etf_prices.get(ticker)):
            result = sa.allocation_effect(history)
        self.assertIsNotNone(result)
        self.assertIsNone(result["sectors"]["real_estate"]["allocation_effect_pct"])
        self.assertIsNone(result["sectors"]["real_estate"]["sector_return_pct"])
        # A sector with a real active weight but no priced ETF must not silently contribute 0
        # to the total as though it had been measured and found neutral.
        self.assertIsNotNone(result["sectors"]["real_estate"]["active_weight"])

    def test_none_without_a_priced_benchmark(self):
        history = snapshots(6, strategy_weights={"technology": 0.5},
                            benchmark_weights={"technology": 0.3})
        with mock.patch.object(ss, "read_etf_prices", return_value=None):
            self.assertIsNone(sa.allocation_effect(history))

    def test_rows_missing_either_weight_map_are_excluded_from_the_usable_count(self):
        history = snapshots(sa.MINIMUM_SNAPSHOTS - 1, strategy_weights={"technology": 0.5},
                            benchmark_weights={"technology": 0.3})
        history.append({"as_of": "2026-08-20T00:00:00"})  # missing both weight maps
        self.assertIsNone(sa.allocation_effect(history))


if __name__ == "__main__":
    unittest.main()
