import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import insider_signal as ins

TODAY = date(2026, 8, 2)


def trade(side, days_ago, *, cik="0001", name="Jane Doe", value=250_000, roles=("director",),
          when=None):
    trade_date = when or (TODAY - timedelta(days=days_ago)).isoformat()
    return {"side": side, "date": trade_date, "value": value, "owner_cik": cik,
            "owner_name": name, "roles": list(roles)}


class ClassificationTests(unittest.TestCase):
    def test_same_month_every_year_is_routine(self):
        # The Cohen-Malloy-Pomorski definition: an insider trading the same calendar month
        # across years is on a schedule, and scheduled trades carry no information.
        history = [trade("sale", 0, when=f"{year}-03-15") for year in (2024, 2025, 2026)]
        classified = ins.classify_transactions(history)
        newest = max(classified, key=lambda row: row["date"])
        self.assertEqual(newest["classification"], "routine")
        self.assertEqual(newest["prior_same_month_years"], [2024, 2025])

    def test_a_trade_breaking_the_pattern_is_opportunistic(self):
        history = [trade("purchase", 0, when=f"{year}-03-15") for year in (2024, 2025)]
        history.append(trade("purchase", 0, when="2026-09-04"))
        classified = ins.classify_transactions(history)
        september = next(row for row in classified if row["date"] == "2026-09-04")
        self.assertEqual(september["classification"], "opportunistic")

    def test_two_insiders_are_classified_independently(self):
        history = [
            *[trade("sale", 0, cik="0001", when=f"{year}-03-15") for year in (2024, 2025, 2026)],
            trade("purchase", 3, cik="0002", name="New Buyer"),
        ]
        classified = ins.classify_transactions(history)
        by_key = {row["insider_key"]: row["classification"] for row in classified}
        self.assertEqual(by_key["cik:1"], "routine")
        self.assertEqual(by_key["cik:2"], "opportunistic")

    def test_thin_history_is_flagged_low_confidence_not_asserted_irregular(self):
        classified = ins.classify_transactions([trade("purchase", 5)])
        self.assertEqual(classified[0]["classification"], "opportunistic")
        self.assertEqual(classified[0]["pattern_confidence"], "low")

    def test_undated_transactions_are_dropped_rather_than_guessed(self):
        self.assertEqual(ins.classify_transactions([{"side": "purchase", "value": 1}]), [])


class ScoringTests(unittest.TestCase):
    def test_fresh_opportunistic_cluster_buying_scores_positive(self):
        transactions = [trade("purchase", 4, cik=f"000{index}", name=f"Buyer {index}")
                        for index in range(3)]
        points, detail = ins.score_insider_activity(transactions, as_of=TODAY)
        self.assertGreater(points, 0)
        self.assertEqual(detail["buy_cluster"]["insider_count"], 3)
        self.assertTrue(detail["notes"])

    def test_routine_selling_scores_exactly_zero(self):
        # The paper's finding, encoded: routine trades' returns are essentially zero, so a
        # fresh calendar-scheduled sale must not move the score in either direction. Only
        # the 2026 leg is provably routine - the earlier ones had no prior years to compare
        # against yet - but those are long stale, so nothing is left to score.
        transactions = [trade("sale", 0, when=f"{year}-03-15") for year in (2024, 2025, 2026)]
        points, detail = ins.score_insider_activity(transactions, as_of=date(2026, 3, 20))
        self.assertEqual(points, 0.0)
        newest = max(ins.classify_transactions(transactions), key=lambda row: row["date"])
        self.assertEqual(newest["classification"], "routine")
        self.assertEqual(detail["routine"], 1)

    def test_an_identical_but_unscheduled_sale_does_move_the_score(self):
        # The control for the test above: same insider, same size, same freshness - the
        # only difference is that it does not fall on their usual calendar month.
        scheduled = [trade("sale", 0, when=f"{year}-03-15") for year in (2024, 2025, 2026)]
        unscheduled = [*scheduled[:2], trade("sale", 0, when="2026-03-15", cik="0002",
                                             name="Irregular Seller")]
        points, _ = ins.score_insider_activity(unscheduled, as_of=date(2026, 3, 20))
        self.assertLess(points, 0.0)

    def test_buying_outweighs_equivalent_selling(self):
        buys = [trade("purchase", 3, cik=f"a{i}", name=f"Buyer {i}") for i in range(3)]
        sells = [trade("sale", 3, cik=f"b{i}", name=f"Seller {i}") for i in range(3)]
        buy_points, _ = ins.score_insider_activity(buys, as_of=TODAY)
        sell_points, _ = ins.score_insider_activity(sells, as_of=TODAY)
        self.assertGreater(buy_points, abs(sell_points))

    def test_more_insiders_beat_one_insider_trading_larger(self):
        crowd = [trade("purchase", 3, cik=f"c{i}", name=f"Buyer {i}", value=200_000)
                 for i in range(4)]
        lone = [trade("purchase", 3, cik="solo", name="Solo", value=5_000_000)]
        crowd_points, _ = ins.score_insider_activity(crowd, as_of=TODAY)
        lone_points, _ = ins.score_insider_activity(lone, as_of=TODAY)
        self.assertGreater(crowd_points, lone_points)

    def test_the_signal_decays_with_age(self):
        fresh = [trade("purchase", 2, cik=f"f{i}", name=f"B{i}") for i in range(3)]
        old = [trade("purchase", 80, cik=f"o{i}", name=f"B{i}") for i in range(3)]
        fresh_points, _ = ins.score_insider_activity(fresh, as_of=TODAY)
        old_points, _ = ins.score_insider_activity(old, as_of=TODAY)
        self.assertGreater(fresh_points, old_points)
        self.assertGreater(old_points, 0)

    def test_stale_activity_contributes_nothing(self):
        stale = [trade("purchase", 200, cik=f"s{i}", name=f"B{i}") for i in range(3)]
        points, _ = ins.score_insider_activity(stale, as_of=TODAY)
        self.assertEqual(points, 0.0)

    def test_token_purchases_below_the_materiality_floor_are_ignored(self):
        tiny = [trade("purchase", 2, cik=f"t{i}", name=f"B{i}", value=500) for i in range(3)]
        points, detail = ins.score_insider_activity(tiny, as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["material_opportunistic"], 0)

    def test_score_is_bounded_by_config(self):
        flood = [trade("purchase", 0, cik=f"x{i}", name=f"B{i}", value=1e9) for i in range(20)]
        points, _ = ins.score_insider_activity(flood, as_of=TODAY,
                                               config={"max_points": 5.0})
        self.assertLessEqual(points, 5.0)

    def test_no_transactions_reports_unavailable_rather_than_neutral_zero(self):
        points, detail = ins.score_insider_activity([], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_summary_is_publishable(self):
        summary = ins.summarize([trade("purchase", 3)], as_of=TODAY)
        self.assertEqual(summary["source"], "SEC EDGAR Form 4")
        self.assertEqual(summary["recent_acquisitions"], 1)
        self.assertIn("score_points", summary)


class DecayTests(unittest.TestCase):
    def test_half_life_halves_the_weight(self):
        self.assertEqual(ins.decay(0), 1.0)
        self.assertAlmostEqual(ins.decay(ins.SIGNAL_HALF_LIFE_DAYS), 0.5, places=3)
        self.assertEqual(ins.decay(ins.MAX_AGE_DAYS + 1), 0.0)
        self.assertEqual(ins.decay(None), 0.0)


if __name__ == "__main__":
    unittest.main()
