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
