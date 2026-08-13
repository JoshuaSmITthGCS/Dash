import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from yahoo_estimates import (collect_estimate_detail, consensus_target, eps_revision_magnitude,
                             net_upgrades, revision_breadth, target_change)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def revisions_frame(up30=7, down30=1):
    return pd.DataFrame(
        {"upLast7days": [2, 1], "upLast30days": [up30, 3], "downLast7days": [0, 0],
         "downLast30days": [down30, 2]},
        index=["0y", "+1y"],
    )


def trend_frame(current=5.72, prior=5.10):
    return pd.DataFrame(
        {"current": [current, 6.4], "7daysAgo": [5.6, 6.3], "30daysAgo": [prior, 6.1],
         "60daysAgo": [5.0, 6.0], "90daysAgo": [4.9, 5.9]},
        index=["0y", "+1y"],
    )


def grades_frame(entries):
    return pd.DataFrame(
        {"Firm": [entry[1] for entry in entries], "Action": [entry[2] for entry in entries]},
        index=[entry[0] for entry in entries],
    )


class RevisionBreadthTests(unittest.TestCase):
    """Breadth, not a raw count: three upgrades out of three analysts is a different
    statement from three out of thirty, and only the ratio compares across coverage."""

    def test_net_upward_revisions_score_positive(self):
        breadth, period = revision_breadth(revisions_frame(up30=7, down30=1))

        self.assertAlmostEqual(breadth, 0.75)
        self.assertEqual(period, "0y")

    def test_net_downward_revisions_score_negative(self):
        breadth, _ = revision_breadth(revisions_frame(up30=1, down30=9))

        self.assertAlmostEqual(breadth, -0.8)

    def test_nobody_revising_is_a_real_neutral_not_missing_data(self):
        breadth, _ = revision_breadth(revisions_frame(up30=0, down30=0))

        self.assertEqual(breadth, 0.0)

    def test_an_empty_frame_resolves_to_nothing(self):
        self.assertEqual(revision_breadth(pd.DataFrame()), (None, None))
        self.assertEqual(revision_breadth(None), (None, None))

    def test_a_plain_dict_from_another_yfinance_version_still_reads(self):
        breadth, _ = revision_breadth({"0y": {"upLast30days": 4, "downLast30days": 0}})

        self.assertEqual(breadth, 1.0)


class RevisionMagnitudeTests(unittest.TestCase):
    def test_reads_the_thirty_day_change_in_the_consensus_estimate(self):
        magnitude, period = eps_revision_magnitude(trend_frame(current=5.72, prior=5.10))

        self.assertAlmostEqual(magnitude, 0.1216, places=3)
        self.assertEqual(period, "0y")

    def test_a_falling_estimate_is_negative(self):
        magnitude, _ = eps_revision_magnitude(trend_frame(current=4.0, prior=5.0))

        self.assertAlmostEqual(magnitude, -0.2)

    def test_a_sign_flip_is_unavailable_rather_than_a_meaningless_percentage(self):
        # A loss narrowing from -1.00 to +0.50 is not "150% better" in any usable sense.
        magnitude, _ = eps_revision_magnitude(trend_frame(current=0.5, prior=-1.0))

        self.assertIsNone(magnitude)

    def test_a_zero_prior_estimate_is_unavailable(self):
        magnitude, _ = eps_revision_magnitude(trend_frame(current=1.0, prior=0.0))

        self.assertIsNone(magnitude)


class UpgradeCountTests(unittest.TestCase):
    def test_counts_upgrades_against_downgrades_inside_the_window(self):
        recent = (NOW - timedelta(days=10)).strftime("%Y-%m-%d")
        frame = grades_frame([
            (recent, "Reuters Bank", "up"), (recent, "Second Bank", "up"),
            (recent, "Third Bank", "down"),
        ])

        self.assertEqual(net_upgrades(frame, now=NOW), 1)

    def test_ignores_reiterations_and_new_coverage(self):
        # A reiteration is not new information; an initiation is coverage, not a change of
        # mind. Counting either lets a busy calendar look like rising conviction.
        recent = (NOW - timedelta(days=5)).strftime("%Y-%m-%d")
        frame = grades_frame([
            (recent, "A", "main"), (recent, "B", "init"), (recent, "C", "reit"),
        ])

        self.assertIsNone(net_upgrades(frame, now=NOW))

    def test_ignores_rating_changes_older_than_the_window(self):
        stale = (NOW - timedelta(days=200)).strftime("%Y-%m-%d")
        frame = grades_frame([(stale, "Old Bank", "up")])

        self.assertIsNone(net_upgrades(frame, now=NOW))

    def test_two_firms_moving_the_same_name_on_one_day_are_both_counted(self):
        # The upgrade frame is indexed by grade date, and a cluster of same-day rating
        # changes is exactly when the signal is strongest - keying by index would drop all
        # but one of them.
        same_day = (NOW - timedelta(days=3)).strftime("%Y-%m-%d")
        frame = grades_frame([(same_day, f"Bank {i}", "up") for i in range(4)])

        self.assertEqual(net_upgrades(frame, now=NOW), 4)

    def test_no_history_at_all_resolves_to_nothing(self):
        self.assertIsNone(net_upgrades(None, now=NOW))
        self.assertIsNone(net_upgrades(pd.DataFrame(), now=NOW))


class TargetDriftTests(unittest.TestCase):
    """Yahoo has no as-of-a-past-date target, so the comparison point is this repository's
    own archive - which is the argument for stamping and storing snapshots from day one."""

    def test_measures_drift_against_the_previously_stored_target(self):
        self.assertAlmostEqual(target_change(112.0, 90.0), 24.44, places=2)

    def test_no_prior_snapshot_means_unknown_rather_than_no_change(self):
        self.assertIsNone(target_change(112.0, None))

    def test_reads_the_mean_target_whatever_shape_the_provider_returned(self):
        self.assertEqual(consensus_target({"current": 100, "mean": 112.0, "high": 130}), 112.0)
        self.assertEqual(consensus_target({"targetMeanPrice": 95.0}), 95.0)
        self.assertIsNone(consensus_target(None))


class _FakeTicker:
    """One company's analyst endpoints, each independently able to fail."""

    def __init__(self, **overrides):
        self._data = {
            "eps_revisions": revisions_frame(),
            "eps_trend": trend_frame(),
            "upgrades_downgrades": grades_frame([
                ((NOW - timedelta(days=10)).strftime("%Y-%m-%d"), "Bank", "up"),
            ]),
            "analyst_price_targets": {"mean": 112.0},
        }
        self._data.update(overrides)

    def _get(self, key):
        value = self._data[key]
        if isinstance(value, Exception):
            raise value
        return value

    def get_eps_revisions(self):
        return self._get("eps_revisions")

    def get_eps_trend(self):
        return self._get("eps_trend")

    def get_upgrades_downgrades(self):
        return self._get("upgrades_downgrades")

    def get_analyst_price_targets(self):
        return self._get("analyst_price_targets")


class CollectionTests(unittest.TestCase):
    def test_a_healthy_company_resolves_every_expectation_input(self):
        detail = collect_estimate_detail("MU", _FakeTicker(), previous_target=90.0, now=NOW)

        self.assertAlmostEqual(detail["revision_breadth_30d"], 0.75)
        self.assertAlmostEqual(detail["eps_revision_30d_pct"], 0.1216, places=3)
        self.assertEqual(detail["net_upgrades_90d"], 1)
        self.assertAlmostEqual(detail["target_change_30d_pct"], 24.44, places=2)
        self.assertEqual(detail["inputs_resolved"], 4)

    def test_one_failing_endpoint_does_not_discard_the_others(self):
        # These calls fail independently; losing the upgrade history is not a reason to throw
        # away revision data that already came back.
        detail = collect_estimate_detail(
            "MU", _FakeTicker(upgrades_downgrades=RuntimeError("crumb negotiation failed")),
            previous_target=90.0, now=NOW)

        self.assertAlmostEqual(detail["revision_breadth_30d"], 0.75)
        self.assertIsNone(detail["net_upgrades_90d"])
        self.assertEqual(detail["inputs_resolved"], 3)

    def test_every_reading_is_stamped_with_when_it_was_observed(self):
        # Without an available_at there is no honest way to reconstruct later what the model
        # would have known on a given date.
        detail = collect_estimate_detail("MU", _FakeTicker(), now=NOW)

        self.assertEqual(detail["available_at"], NOW.isoformat())

    def test_a_company_with_no_coverage_at_all_returns_zero_resolved_inputs(self):
        detail = collect_estimate_detail("QUIET", _FakeTicker(
            eps_revisions=None, eps_trend=None, upgrades_downgrades=None,
            analyst_price_targets=None), now=NOW)

        self.assertEqual(detail["inputs_resolved"], 0)
        self.assertIsNone(detail["revision_breadth_30d"])

    def test_no_ticker_object_yields_nothing_rather_than_raising(self):
        self.assertEqual(collect_estimate_detail("MU", None), {})


if __name__ == "__main__":
    unittest.main()
