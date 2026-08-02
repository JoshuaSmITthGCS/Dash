import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fetch_etfs import (beta_vs_benchmark, build_etf_row, daily_returns, percentile_scores,
                        period_return, score_etf_universe, sharpe_ratio, sortino_ratio)


def rising_closes(days, daily_gain=0.001, start=100.0):
    closes = [start]
    for _ in range(days - 1):
        closes.append(closes[-1] * (1 + daily_gain))
    return [round(value, 4) for value in closes]


class PeriodReturnTests(unittest.TestCase):
    def test_computes_percent_change_over_the_window(self):
        closes = [100, 101, 102, 103, 104, 105]
        self.assertEqual(period_return(closes, 5), 5.0)

    def test_none_when_history_is_too_short(self):
        self.assertIsNone(period_return([100, 101], 5))


class RiskMetricTests(unittest.TestCase):
    def test_sharpe_is_positive_for_steady_gains(self):
        rets = daily_returns(rising_closes(60, daily_gain=0.002))
        self.assertGreater(sharpe_ratio(rets), 0)

    def test_sharpe_is_none_with_too_little_history(self):
        self.assertIsNone(sharpe_ratio([0.01, -0.01]))

    def test_sortino_ignores_upside_volatility(self):
        # Both series swing by the same amount; one swings up, the other down. Sortino
        # only penalizes the downside swing, so the up-swinging series should score higher.
        upside_vol = [0.02, 0.05, -0.001, 0.025] * 10
        downside_vol = [0.02, -0.05, -0.001, 0.025] * 10
        self.assertGreater(sortino_ratio(upside_vol), sortino_ratio(downside_vol))

    def test_beta_of_a_series_against_itself_is_one(self):
        rets = daily_returns(rising_closes(60, daily_gain=0.0015))
        self.assertEqual(beta_vs_benchmark(rets, rets), 1.0)

    def test_beta_is_none_with_too_little_overlap(self):
        self.assertIsNone(beta_vs_benchmark([0.01, 0.02], [0.01, 0.02]))


class PercentileScoresTests(unittest.TestCase):
    def test_ranks_ascending_when_higher_is_better(self):
        scores = percentile_scores([10, 30, 20], higher_is_better=True)
        self.assertEqual(scores, [0.0, 100.0, 50.0])

    def test_inverts_ranking_when_lower_is_better(self):
        scores = percentile_scores([10, 30, 20], higher_is_better=False)
        self.assertEqual(scores, [100.0, 0.0, 50.0])

    def test_missing_values_stay_neutral(self):
        scores = percentile_scores([10, None, 30], higher_is_better=True)
        self.assertEqual(scores, [0.0, 50.0, 100.0])

    def test_fewer_than_two_data_points_returns_all_neutral(self):
        self.assertEqual(percentile_scores([42, None, None]), [50.0, 50.0, 50.0])


class BuildEtfRowTests(unittest.TestCase):
    def test_computes_windowed_returns_and_cost_liquidity_fields(self):
        closes = rising_closes(260, daily_gain=0.001)
        volumes = [1_000_000.0] * len(closes)
        row = build_etf_row(
            "QQQ", {"name": "Nasdaq 100", "category": "growth", "issuer": "Invesco", "expense_ratio": 0.20},
            {"price": closes[-1], "aum": 3e11, "bid": 519.9, "ask": 520.1},
            closes, volumes, daily_returns(closes),
        )

        self.assertEqual(row["ticker"], "QQQ")
        self.assertEqual(row["issuer"], "Invesco")
        self.assertIsNotNone(row["returns"]["1y"])
        self.assertIsNone(row["returns"]["3y"])  # only 260 sessions of history
        self.assertAlmostEqual(row["bid_ask_spread_pct"], 0.2 / 520.0 * 100, places=2)
        self.assertEqual(row["beta"], 1.0)  # benchmark passed in was its own daily returns


class ScoreEtfUniverseTests(unittest.TestCase):
    def _row(self, ticker, issuer, expense_ratio, daily_gain, aum=1e10):
        closes = rising_closes(260, daily_gain=daily_gain)
        volumes = [2_000_000.0] * len(closes)
        benchmark_rets = daily_returns(rising_closes(260, daily_gain=0.0004))
        return build_etf_row(
            ticker, {"name": ticker, "category": "sector", "issuer": issuer, "expense_ratio": expense_ratio},
            {"price": closes[-1], "aum": aum, "bid": 99.9, "ask": 100.1}, closes, volumes, benchmark_rets,
        )

    def test_best_performer_ranks_first_and_worst_last(self):
        leader = self._row("LEAD", "Vanguard", 0.03, daily_gain=0.0025)
        sp500 = self._row("SPY", "State Street", 0.09, daily_gain=0.0006)
        dow = self._row("DIA", "State Street", 0.16, daily_gain=0.0005)
        laggard = self._row("LAG", "ARK", 0.75, daily_gain=-0.0008)

        scored = score_etf_universe([sp500, dow, leader, laggard])
        order = [row["ticker"] for row in scored]

        self.assertEqual(order[0], "LEAD")
        self.assertEqual(order[-1], "LAG")
        self.assertEqual([row["overall_rank"] for row in scored], [1, 2, 3, 4])

    def test_vs_benchmarks_diff_against_the_sp500_and_dow_rows_in_the_same_batch(self):
        leader = self._row("LEAD", "Vanguard", 0.03, daily_gain=0.0025)
        sp500 = self._row("SPY", "State Street", 0.09, daily_gain=0.0006)
        dow = self._row("DIA", "State Street", 0.16, daily_gain=0.0005)

        scored = score_etf_universe([sp500, dow, leader])
        leader_row = next(row for row in scored if row["ticker"] == "LEAD")

        expected_vs_sp500 = round(leader_row["returns"]["1y"] - sp500["returns"]["1y"], 2)
        expected_vs_dow = round(leader_row["returns"]["1y"] - dow["returns"]["1y"], 2)
        self.assertEqual(leader_row["vs_benchmarks"]["sp500_1y"], expected_vs_sp500)
        self.assertEqual(leader_row["vs_benchmarks"]["dow_1y"], expected_vs_dow)
        self.assertGreater(leader_row["vs_benchmarks"]["sp500_1y"], 0)

    def test_cheaper_fund_scores_higher_on_cost_all_else_equal(self):
        cheap = self._row("CHEAP", "Vanguard", 0.03, daily_gain=0.0006)
        pricey = self._row("PRICEY", "Vanguard", 0.75, daily_gain=0.0006)

        scored = score_etf_universe([cheap, pricey])
        cheap_row = next(row for row in scored if row["ticker"] == "CHEAP")
        pricey_row = next(row for row in scored if row["ticker"] == "PRICEY")

        self.assertGreater(cheap_row["scores"]["cost"], pricey_row["scores"]["cost"])


if __name__ == "__main__":
    unittest.main()
