import json

import pytest

from validation_framework import (append_immutable_snapshot, block_bootstrap_excess,
                                  import_external_rankings, performance_metrics, walk_forward_splits)


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


def test_purge_drops_observations_whose_label_window_overlaps_the_test_set():
    # Default purge (3 periods, from a 63-session/~3-month label) must drop the 3
    # observations immediately before the test window from training - their forward-return
    # label reaches into the test period even though the observation itself predates it.
    splits = walk_forward_splits(list(range(20)), train_periods=10, test_periods=5)
    split = splits[0]
    assert split["test"] == [10, 11, 12, 13, 14]
    assert split["purged"] == [7, 8, 9]
    assert 7 not in split["train"] and 8 not in split["train"] and 9 not in split["train"]
    assert split["train"] == list(range(7))


def test_embargo_keeps_a_later_splits_train_from_reclaiming_the_excluded_window():
    # test windows: [10,15), [15,20), [20,25); purge_start for split index 2 is 20-2=18,
    # which would ordinarily pull indices 15, 16, 17 (split 0's embargo window) straight
    # back into training - embargo must keep them excluded even two splits later.
    splits = walk_forward_splits(list(range(30)), train_periods=10, test_periods=5,
                                 purge_periods=2, embargo_periods=3)
    embargoed = set(range(15, 18))
    third_train = set(splits[2]["train"])
    assert not (embargoed & third_train)
    without_embargo = walk_forward_splits(list(range(30)), train_periods=10, test_periods=5,
                                          purge_periods=2, embargo_periods=0)
    assert embargoed & set(without_embargo[2]["train"]) == embargoed


def test_purge_and_embargo_can_be_disabled_for_exact_legacy_behavior():
    splits = walk_forward_splits(list(range(12)), 6, 3, purge_periods=0, embargo_periods=0)
    assert splits[0]["train"] == list(range(6))
    assert splits[0]["purged"] == []


def test_split_count_is_unaffected_by_purge_and_embargo():
    # Purge/embargo change what training a split may use, never how many splits exist or
    # where test windows fall - those are the walk-forward contract.
    with_defaults = walk_forward_splits(list(range(12)), 6, 3)
    without = walk_forward_splits(list(range(12)), 6, 3, purge_periods=0, embargo_periods=0)
    assert len(with_defaults) == len(without) == 2
    assert [split["test"] for split in with_defaults] == [split["test"] for split in without]
