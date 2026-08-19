import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import enrichment_ladder as ladder


class ThemeExposureFromScreenTests(unittest.TestCase):
    def test_takes_the_max_exposure_across_qualifying_themes(self):
        by_ticker = {"NVDA": [{"theme_exposure_score": 60.0}, {"theme_exposure_score": 85.0}]}
        self.assertEqual(ladder.theme_exposure_from_screen(by_ticker), {"NVDA": 85.0})

    def test_a_ticker_with_no_resolved_exposure_is_omitted(self):
        by_ticker = {"NVDA": [{"theme_exposure_score": None}]}
        self.assertEqual(ladder.theme_exposure_from_screen(by_ticker), {})

    def test_empty_input_is_a_no_op(self):
        self.assertEqual(ladder.theme_exposure_from_screen(None), {})
        self.assertEqual(ladder.theme_exposure_from_screen({}), {})


class LadderDaySlotsTests(unittest.TestCase):
    def test_day_zero_is_the_current_top_twenty(self):
        preliminary = tuple(f"S{i:03d}" for i in range(200))

        symbols, cursor = ladder.ladder_day_slots(0, preliminary, {}, (), rank_cursor=20)

        self.assertEqual(symbols, list(preliminary[:20]))
        self.assertEqual(cursor, 20)

    def test_day_one_ranks_outsiders_by_exposure_not_opportunity(self):
        preliminary = tuple(f"S{i:03d}" for i in range(30))
        exposure = {"S025": 90.0, "S026": 40.0, "S027": 70.0, "S005": 99.0}  # S005 is in top 20

        symbols, cursor = ladder.ladder_day_slots(1, preliminary, exposure, (), rank_cursor=20)

        # S005 excluded (already in top 20), the rest ordered by descending exposure.
        self.assertEqual(symbols, ["S025", "S027", "S026"])
        self.assertEqual(cursor, 20)

    def test_day_one_excludes_names_already_enriched_this_cycle(self):
        preliminary = tuple(f"S{i:03d}" for i in range(30))
        exposure = {"S025": 90.0, "S026": 40.0}

        symbols, _ = ladder.ladder_day_slots(1, preliminary, exposure, ("S025",), rank_cursor=20)

        self.assertEqual(symbols, ["S026"])

    def test_day_one_ignores_names_with_no_theme_exposure(self):
        preliminary = tuple(f"S{i:03d}" for i in range(30))
        symbols, _ = ladder.ladder_day_slots(1, preliminary, {}, (), rank_cursor=20)
        self.assertEqual(symbols, [])

    def test_day_two_walks_the_next_band_from_the_cursor(self):
        preliminary = tuple(f"S{i:03d}" for i in range(200))

        symbols, cursor = ladder.ladder_day_slots(2, preliminary, {}, (), rank_cursor=20)

        self.assertEqual(symbols, list(preliminary[20:40]))
        self.assertEqual(cursor, 40)

    def test_day_three_continues_from_the_threaded_cursor(self):
        preliminary = tuple(f"S{i:03d}" for i in range(200))

        symbols, cursor = ladder.ladder_day_slots(3, preliminary, {}, (), rank_cursor=40)

        self.assertEqual(symbols, list(preliminary[40:60]))
        self.assertEqual(cursor, 60)

    def test_a_rank_band_day_widens_past_twenty_when_overlap_forces_it_to_skip(self):
        # Reproduces the work order's own Day 5 example: a 40-rank window (61-100) is
        # exactly what happens when half of a 20-wide band is already spoken for.
        preliminary = tuple(f"S{i:03d}" for i in range(200))
        already_enriched = {preliminary[i] for i in range(60, 100, 2)}  # every other name 61-100

        symbols, cursor = ladder.ladder_day_slots(
            4, preliminary, {}, already_enriched, rank_cursor=60)

        self.assertEqual(len(symbols), 20)
        self.assertTrue(all(symbol not in already_enriched for symbol in symbols))
        self.assertEqual(cursor, 100)  # scanned the full 60-100 band to find 20 fresh names

    def test_the_walk_never_rescans_ranks_the_cursor_already_passed(self):
        preliminary = tuple(f"S{i:03d}" for i in range(60))
        _, cursor_after_day_two = ladder.ladder_day_slots(2, preliminary, {}, (), rank_cursor=20)
        symbols, _ = ladder.ladder_day_slots(3, preliminary, {}, (), rank_cursor=cursor_after_day_two)
        self.assertEqual(symbols, list(preliminary[40:60]))

    def test_running_out_of_universe_returns_fewer_than_size(self):
        preliminary = tuple(f"S{i:03d}" for i in range(45))
        symbols, cursor = ladder.ladder_day_slots(2, preliminary, {}, (), rank_cursor=40)
        self.assertEqual(symbols, list(preliminary[40:45]))
        self.assertEqual(cursor, 45)


class RandomArmSlotsTests(unittest.TestCase):
    def test_draws_uniformly_and_excludes_claimed_names(self):
        pool = [f"S{i:03d}" for i in range(50)]
        claimed = pool[:20]
        rng = random.Random(7)

        drawn = ladder.random_arm_slots(pool, claimed, rng, size=3)

        self.assertEqual(len(drawn), 3)
        self.assertTrue(all(symbol not in claimed for symbol in drawn))

    def test_never_carved_from_the_claimed_ranked_slots(self):
        pool = [f"S{i:03d}" for i in range(23)]
        claimed = pool[:20]
        rng = random.Random(1)

        drawn = ladder.random_arm_slots(pool, claimed, rng, size=3)

        self.assertEqual(sorted(drawn), sorted(pool[20:23]))

    def test_a_pool_smaller_than_the_budget_returns_everything_available(self):
        pool = ["S001", "S002"]
        rng = random.Random(1)
        self.assertEqual(ladder.random_arm_slots(pool, [], rng, size=3), ["S001", "S002"])


class AvQuotaOrderTests(unittest.TestCase):
    def test_random_arm_names_come_first(self):
        random_arm = ["R1", "R2"]
        remainder = ["A", "B", "C"]
        rng = random.Random(3)

        order = ladder.av_quota_order(random_arm, {}, remainder, rng)

        self.assertEqual(set(order[:2]), {"R1", "R2"})

    def test_never_ordered_top_down_by_rank_ages_come_before_remainder(self):
        random_arm = []
        remainder = ["FRESH", "STALE"]
        ages = {"FRESH": 1, "STALE": 90}
        rng = random.Random(3)

        order = ladder.av_quota_order(random_arm, ages, remainder, rng)

        self.assertEqual(order, ["STALE", "FRESH"])

    def test_within_tier_order_is_randomized_across_seeds(self):
        random_arm = [f"R{i}" for i in range(20)]
        orders = {tuple(ladder.av_quota_order(random_arm, {}, [], random.Random(seed))[:20])
                  for seed in range(5)}
        self.assertGreater(len(orders), 1)


class RetryQueueTests(unittest.TestCase):
    def test_a_first_failure_is_queued_for_retry(self):
        retry, persistent, counts = ladder.advance_retry_queue(["AAPL"], {})
        self.assertEqual(retry, ["AAPL"])
        self.assertEqual(persistent, [])
        self.assertEqual(counts["AAPL"], 1)

    def test_reaching_max_attempts_marks_persistent_failure(self):
        counts = {"AAPL": 2}
        retry, persistent, updated = ladder.advance_retry_queue(["AAPL"], counts, max_attempts=3)
        self.assertEqual(retry, [])
        self.assertEqual(persistent, ["AAPL"])
        self.assertEqual(updated["AAPL"], 3)

    def test_a_persistent_failure_does_not_grow_past_max_attempts_in_state(self):
        retry, persistent, updated = ladder.advance_retry_queue(
            ["AAPL"], {"AAPL": 5}, max_attempts=3)
        self.assertEqual(persistent, ["AAPL"])
        self.assertEqual(updated["AAPL"], 6)

    def test_reset_clears_a_names_attempt_count_on_success(self):
        counts = {"AAPL": 2, "MSFT": 1}
        updated = ladder.reset_attempt_count("AAPL", counts)
        self.assertNotIn("AAPL", updated)
        self.assertEqual(updated["MSFT"], 1)
        self.assertIn("AAPL", counts)  # original dict left untouched


if __name__ == "__main__":
    unittest.main()
