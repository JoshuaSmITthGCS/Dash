import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import sector_weight_history as sectors


def payloads():
    advisor = {
        "generated_at": "2026-08-14T12:00:00+00:00",
        "research": [
            {"ticker": "A", "score": 90, "sector": "Technology"},
            {"ticker": "B", "score": 80, "sector": "Energy"},
        ],
    }
    etfs = {
        "generated_at": "2026-08-14T12:01:00+00:00",
        "etfs": [{"ticker": "SPY", "sector_weights": {
            "technology": 0.4, "energy": 0.3, "healthcare": 0.3,
        }}],
    }
    return advisor, etfs


def test_snapshot_has_strategy_benchmark_and_active_weights():
    advisor, etfs = payloads()
    row = sectors.build_snapshot(advisor, etfs, recorded_at="2026-08-14T12:02:00+00:00")
    assert row["strategy_sector_weights"] == {"energy": 0.5, "technology": 0.5}
    assert row["active_sector_weights"]["technology"] == 0.1
    assert row["active_sector_weights"]["healthcare"] == -0.3
    assert row["strategy_classified_weight"] == 1.0


def test_append_is_idempotent_for_the_same_source_refresh():
    advisor, etfs = payloads()
    row = sectors.build_snapshot(advisor, etfs)
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "history.jsonl")
        assert sectors.append_snapshot(row, path) is True
        assert sectors.append_snapshot(row, path) is False
        assert len(sectors.read_history(path)) == 1
        assert json.loads(open(path).readline())["benchmark"] == "SPY"
