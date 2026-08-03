import pytest

from estimate_snapshots import append_estimate_snapshot, snapshots_at_or_before


def test_point_in_time_lookup_never_uses_future_snapshot(tmp_path):
    append_estimate_snapshot(tmp_path, "AAPL", "2025-01-01T12:00:00Z", {"fy1": 5}, "manual")
    append_estimate_snapshot(tmp_path, "AAPL", "2025-02-01T12:00:00Z", {"fy1": 6}, "manual")
    rows = snapshots_at_or_before(tmp_path, "AAPL", "2025-01-15T00:00:00Z")
    assert [row["estimates"]["fy1"] for row in rows] == [5]


def test_snapshot_is_append_only(tmp_path):
    append_estimate_snapshot(tmp_path, "AAPL", "2025-01-01T12:00:00Z", {"fy1": 5}, "manual")
    with pytest.raises(FileExistsError):
        append_estimate_snapshot(tmp_path, "AAPL", "2025-01-01T12:00:00Z", {"fy1": 6}, "manual")
