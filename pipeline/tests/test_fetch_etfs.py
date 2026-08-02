import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import etf_disclosure
from fetch_etfs import (beta_vs_benchmark, build_etf_row, daily_returns, group_indices,
                        peer_group_for, percentile_scores, period_return, score_etf_universe,
                        sharpe_ratio, sortino_ratio, structural_quality)


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

    def test_equal_values_share_a_percentile(self):
        # Four identical expense ratios must not be spread across 0/33/67/100 by input
        # order - that is a decisive-looking ranking of nothing.
        self.assertEqual(percentile_scores([5, 5, 5, 5]), [50.0, 50.0, 50.0, 50.0])
        self.assertEqual(percentile_scores([1, 2, 2, 3]), [0.0, 50.0, 50.0, 100.0])


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


class PeerGroupTests(unittest.TestCase):
    """Ranking a bond fund's Sharpe against an equity fund's produces a number, not a finding."""

    def _row(self, ticker, category, daily_gain, issuer="Vanguard", expense_ratio=0.05):
        closes = rising_closes(260, daily_gain=daily_gain)
        benchmark = daily_returns(rising_closes(260, daily_gain=0.0004))
        return build_etf_row(
            ticker, {"name": ticker, "category": category, "issuer": issuer,
                     "expense_ratio": expense_ratio},
            {"price": closes[-1], "aum": 1e10, "bid": 99.9, "ask": 100.1},
            closes, [2_000_000.0] * 260, benchmark)

    def test_category_maps_to_a_peer_group(self):
        self.assertEqual(peer_group_for({"category": "bonds"}), "fixed_income")
        self.assertEqual(peer_group_for({"category": "thematic"}), "equity_thematic")
        self.assertEqual(peer_group_for({"category": "unheard_of"}), "other")

    def test_an_explicit_peer_group_overrides_the_category_mapping(self):
        self.assertEqual(peer_group_for({"category": "bonds", "peer_group": "custom"}),
                         "custom")

    def test_funds_are_ranked_inside_their_own_group(self):
        rows = [
            *[self._row(f"EQ{index}", "sector", 0.0020 + index * 0.0001) for index in range(4)],
            *[self._row(f"BD{index}", "bonds", 0.0001 + index * 0.00001) for index in range(4)],
        ]
        scored = score_etf_universe(rows)
        groups = {row["ticker"]: row["ranked_against"] for row in scored}
        self.assertEqual(groups["EQ0"], "equity_sector")
        self.assertEqual(groups["BD0"], "fixed_income")
        # The best bond fund tops its own group despite trailing every equity fund.
        best_bond = min((row for row in scored if row["ranked_against"] == "fixed_income"),
                        key=lambda row: row["peer_rank"])
        self.assertEqual(best_bond["peer_rank"], 1)
        self.assertEqual(best_bond["peer_group_size"], 4)

    def test_a_slow_bond_fund_is_not_punished_for_not_being_an_equity_fund(self):
        # The bug this fixes: in one mixed batch, every bond fund landed at the bottom of
        # the performance percentile purely because bonds are not equities.
        mixed = [
            *[self._row(f"EQ{index}", "sector", 0.0025) for index in range(4)],
            *[self._row(f"BD{index}", "bonds", 0.0001) for index in range(4)],
        ]
        scored = {row["ticker"]: row for row in score_etf_universe(mixed)}
        self.assertGreater(scored["BD0"]["scores"]["performance"], 20)

    def test_an_undersized_group_is_pooled_and_flagged(self):
        rows = [
            *[self._row(f"EQ{index}", "sector", 0.002) for index in range(4)],
            self._row("GOLD", "commodity", 0.0005),
        ]
        scored = {row["ticker"]: row for row in score_etf_universe(rows)}
        self.assertEqual(scored["GOLD"]["ranked_against"], "_pooled")
        self.assertTrue(scored["GOLD"]["cross_asset_class_rank"])
        self.assertFalse(scored["EQ0"]["cross_asset_class_rank"])

    def test_beta_is_part_of_the_risk_bucket(self):
        # Beta was computed and then thrown away. Betting-against-beta says it is priced,
        # so a low-beta fund must score better on risk, all else equal.
        closes = rising_closes(260, daily_gain=0.0008)
        benchmark = daily_returns(closes)
        defensive = build_etf_row(
            "DEF", {"name": "DEF", "category": "sector", "issuer": "Vanguard", "expense_ratio": 0.05},
            {"price": closes[-1], "aum": 1e10}, closes, [1e6] * 260, benchmark)
        racy_closes = [value ** 1.0 for value in rising_closes(260, daily_gain=0.0008)]
        racy = build_etf_row(
            "RACY", {"name": "RACY", "category": "sector", "issuer": "Vanguard", "expense_ratio": 0.05},
            {"price": racy_closes[-1], "aum": 1e10}, racy_closes, [1e6] * 260,
            [value * 0.4 for value in benchmark])
        self.assertIsNotNone(defensive["beta"])
        self.assertIsNotNone(racy["beta"])
        self.assertGreater(racy["beta"], defensive["beta"])


class StructuralQualityTests(unittest.TestCase):
    def test_leverage_costs_more_than_a_good_brand_earns(self):
        plain = structural_quality({"issuer": "Vanguard", "aum": 1e10}, {})
        levered = structural_quality({"issuer": "Vanguard", "aum": 1e10}, {"leveraged": True})
        self.assertGreater(plain, levered)

    def test_a_tiny_fund_is_marked_down(self):
        big = structural_quality({"issuer": "iShares", "aum": 2e10}, {})
        tiny = structural_quality({"issuer": "iShares", "aum": 1e8}, {})
        self.assertGreater(big, tiny)

    def test_the_score_stays_inside_zero_to_one_hundred(self):
        worst = structural_quality({"issuer": "ARK", "aum": 1e7},
                                   {"leveraged": True, "replication": "synthetic"})
        self.assertGreaterEqual(worst, 0.0)
        self.assertLessEqual(structural_quality({"issuer": "Vanguard", "aum": 1e12}, {}), 100.0)


class DisclosureTests(unittest.TestCase):
    """SEC Rule 6c-11 makes premium/discount and the 30-day median spread free to obtain."""

    def test_premium_and_discount_are_signed(self):
        self.assertAlmostEqual(etf_disclosure.premium_discount_pct(101.0, 100.0), 1.0)
        self.assertAlmostEqual(etf_disclosure.premium_discount_pct(99.0, 100.0), -1.0)
        self.assertIsNone(etf_disclosure.premium_discount_pct(101.0, 0))

    def test_the_mandated_median_spread_wins_over_a_quoted_snapshot(self):
        official = {"median_bid_ask_spread_pct": 0.02, "quoted_bid_ask_spread_pct": 0.9}
        value, source = etf_disclosure.effective_spread_pct(official)
        self.assertEqual(value, 0.02)
        self.assertEqual(source, "rule_6c11_median_30d")

    def test_the_quote_is_used_only_as_a_labelled_fallback(self):
        value, source = etf_disclosure.effective_spread_pct(
            {"quoted_bid_ask_spread_pct": 0.9})
        self.assertEqual(value, 0.9)
        self.assertEqual(source, "quoted_snapshot")
        self.assertEqual(etf_disclosure.effective_spread_pct({}), (None, None))

    def test_an_issuer_payload_is_normalized_through_the_configured_field_map(self):
        parsed = etf_disclosure.parse_generic_json(
            {"navPerShare": 100.0, "closingPrice": 100.5, "medianSpread30Day": 0.03,
             "asOfDate": "2026-08-01"},
            {"nav": "navPerShare", "market_price": "closingPrice",
             "median_bid_ask_spread_pct": "medianSpread30Day", "as_of": "asOfDate"})
        self.assertEqual(parsed["nav"], 100.0)
        self.assertAlmostEqual(parsed["premium_discount_pct"], 0.5, places=3)
        self.assertEqual(parsed["median_bid_ask_spread_pct"], 0.03)
        self.assertEqual(parsed["source"], etf_disclosure.SOURCE_RULE_6C11)

    def test_the_quote_fallback_labels_itself_honestly(self):
        fallback = etf_disclosure.from_quote({"price": 100.5, "nav": 100.0,
                                              "bid": 100.4, "ask": 100.6})
        self.assertEqual(fallback["source"], etf_disclosure.SOURCE_QUOTE_NAV)
        self.assertIsNone(fallback["median_bid_ask_spread_pct"])
        self.assertIsNotNone(fallback["quoted_bid_ask_spread_pct"])

    def test_the_premium_discount_distribution_says_more_than_one_day(self):
        summary = etf_disclosure.premium_discount_days([0.1, -0.2, -0.3, 0.0, 0.4])
        self.assertEqual(summary["days_at_premium"], 2)
        self.assertEqual(summary["days_at_discount"], 2)
        self.assertEqual(summary["days_at_nav"], 1)
        self.assertIsNone(etf_disclosure.premium_discount_days([]))

    def test_total_cost_does_not_double_count_the_expense_ratio(self):
        # The expense ratio is already inside the fund's return, so it largely *is* the
        # negative tracking difference. Adding them would charge the investor twice.
        cost = etf_disclosure.total_cost_of_ownership(0.20, -0.25, 0.05)
        self.assertAlmostEqual(cost, 0.30, places=4)

    def test_a_premium_paid_at_entry_is_a_real_added_cost(self):
        without = etf_disclosure.total_cost_of_ownership(0.10, -0.10, 0.0)
        with_premium = etf_disclosure.total_cost_of_ownership(0.10, -0.10, 0.5)
        self.assertGreater(with_premium, without)

    def test_no_cost_inputs_at_all_returns_nothing(self):
        self.assertIsNone(etf_disclosure.total_cost_of_ownership(None, None, None))


class TrackingDifferenceTests(unittest.TestCase):
    def test_a_lagging_fund_scores_worse_on_cost_than_a_tracking_one(self):
        index_closes = rising_closes(260, daily_gain=0.0010)
        benchmark = daily_returns(index_closes)
        meta = {"name": "F", "category": "sector", "issuer": "Vanguard",
                "expense_ratio": 0.05, "index_proxy": "IDX"}

        def fund(ticker, gain):
            closes = rising_closes(260, daily_gain=gain)
            return build_etf_row(ticker, {**meta, "name": ticker},
                                 {"price": closes[-1], "aum": 1e10}, closes, [1e6] * 260,
                                 benchmark, index_closes=index_closes)

        tracking = fund("TRACK", 0.0010)
        lagging = fund("LAG", 0.0007)
        self.assertGreater(tracking["tracking_difference_1y"], lagging["tracking_difference_1y"])
        scored = {row["ticker"]: row for row in score_etf_universe(
            [tracking, lagging, fund("A", 0.0009), fund("B", 0.0008)])}
        self.assertGreater(scored["TRACK"]["scores"]["cost"], scored["LAG"]["scores"]["cost"])

    def test_tracking_fields_are_absent_without_an_index_proxy(self):
        closes = rising_closes(260)
        row = build_etf_row("X", {"name": "X", "category": "sector", "issuer": "Vanguard",
                                  "expense_ratio": 0.05},
                            {"price": closes[-1]}, closes, [1e6] * 260, daily_returns(closes))
        self.assertIsNone(row["tracking_difference"])
        self.assertIsNone(row["tracking_difference_1y"])


class GroupIndicesTests(unittest.TestCase):
    def test_small_groups_are_pooled_together(self):
        rows = [{"peer_group": "equity_broad"}] * 5 + [{"peer_group": "crypto"}]
        grouped = group_indices(rows)
        self.assertIn("equity_broad", grouped)
        self.assertEqual(grouped["_pooled"], [5])


if __name__ == "__main__":
    unittest.main()
