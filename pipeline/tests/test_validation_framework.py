import json

import pytest

from validation_framework import (append_immutable_snapshot, block_bootstrap_excess,
                                  import_external_rankings, label_overlap_periods,
                                  performance_metrics, walk_forward_splits)


def test_shadow_snapshot_is_immutable(tmp_path):
    first = append_immutable_snapshot(tmp_path, "momentum", "2025-01-31", [{"ticker": "A"}])
    assert append_immutable_snapshot(tmp_path, "momentum", "2025-01-31", [{"ticker": "A"}]) == first
    with pytest.raises(FileExistsError):
        append_immutable_snapshot(tmp_path, "momentum", "2025-01-31", [{"ticker": "B"}])


def test_manual_json_import(tmp_path):
    path = tmp_path / "ranking.json"
    path.write_text(json.dumps([{"date": "2025-01-31", "ticker": " aapl ", "rank": "1"}]))
    assert import_external_rankings(path)[0]["ticker"] == "AAPL"


def test_walk_forward_and_net_of_cost_metrics():
    assert len(walk_forward_splits(list(range(12)), 6, 3)) == 2
    metrics = performance_metrics([.02, .01, -.01], [.01, .0, -.02], [1, 1, 1], cost_bps=10)
    assert metrics["net_return"] < metrics["gross_return"]
    assert metrics["net_excess_return"] > 0
    interval = block_bootstrap_excess([.02] * 12, [.01] * 12, samples=100)
    assert interval["probability_positive"] == 1


# --- purge and embargo -----------------------------------------------------------------


def test_default_splits_are_unchanged_by_the_new_parameters():
    """Purge and embargo default to zero, so existing callers see the original behaviour."""
    splits = walk_forward_splits(list(range(12)), 6, 3)
    assert len(splits) == 2
    assert splits[0]["train"] == list(range(6))
    assert splits[0]["test"] == [6, 7, 8]
    assert splits[0]["purged"] == []


def test_purge_removes_training_observations_whose_labels_overlap_the_test_window():
    splits = walk_forward_splits(list(range(12)), 6, 3, purge_periods=2)

    # Periods 4 and 5 are still resolving when the test window opens at 6.
    assert splits[0]["train"] == [0, 1, 2, 3]
    assert splits[0]["purged"] == [4, 5]
    assert splits[0]["test"] == [6, 7, 8]


def test_no_purged_observation_ever_appears_in_training():
    observations = list(range(40))
    for purge in (0, 1, 2, 3):
        splits = walk_forward_splits(observations, 10, 5, purge_periods=purge)
        for split in splits:
            assert not set(split["train"]) & set(split["purged"])
            assert not set(split["train"]) & set(split["test"])
            # Training is strictly earlier than the test window, with the gap enforced.
            if split["train"]:
                assert max(split["train"]) <= min(split["test"]) - purge - 1


def test_embargo_widens_the_gap_on_top_of_the_purge():
    purged_only = walk_forward_splits(list(range(20)), 10, 5, purge_periods=2)
    with_embargo = walk_forward_splits(list(range(20)), 10, 5, purge_periods=2,
                                       embargo_periods=3)

    assert purged_only[0]["train"] == list(range(8))
    assert with_embargo[0]["train"] == list(range(5))
    assert with_embargo[0]["test"] == purged_only[0]["test"]


def test_a_gap_wider_than_the_history_empties_training_rather_than_wrapping():
    splits = walk_forward_splits(list(range(12)), 6, 3, purge_periods=99)
    assert splits[0]["train"] == []


def test_negative_gaps_are_rejected():
    with pytest.raises(ValueError):
        walk_forward_splits(list(range(12)), 6, 3, purge_periods=-1)
    with pytest.raises(ValueError):
        walk_forward_splits(list(range(12)), 6, 3, embargo_periods=-1)


def test_label_overlap_is_derived_from_the_horizon_not_guessed():
    # A 63-session label observed monthly (21 sessions) is still resolving two periods later.
    assert label_overlap_periods(63, sessions_per_period=21) == 2
    # A label no longer than the rebalance interval overlaps nothing.
    assert label_overlap_periods(21, sessions_per_period=21) == 0
    assert label_overlap_periods(252, sessions_per_period=21) == 11
    # A horizon that does not divide evenly still overlaps every period it touches.
    assert label_overlap_periods(64, sessions_per_period=21) == 3
    assert label_overlap_periods(0) == 0


def test_the_contract_horizon_purges_two_periods():
    """The concrete case this exists for: the preregistered 63-session target."""
    purge = label_overlap_periods(63, sessions_per_period=21)
    splits = walk_forward_splits(list(range(30)), 12, 6, purge_periods=purge)
    assert splits[0]["purged"] == [10, 11]
    assert max(splits[0]["train"]) == 9
