"""The IV archive is append-only, first-write-wins, loud when stale, and never fabricates
a percentile off a handful of points. Mirrors test_price_archive.py's fixtures and style.
"""
import json
from datetime import datetime, timedelta, timezone

import iv_archive


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(iv_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(iv_archive, "MANIFEST", str(tmp_path / "archive_manifest.json"))


def test_append_observation_adds_a_new_date(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    added = iv_archive.append_observation("AAA", "2026-01-02", 0.32, 7, "test")
    assert added is True
    rows = json.load(open(tmp_path / "AAA.json"))["rows"]
    assert rows["2026-01-02"] == [0.32, 7]


def test_append_observation_first_write_wins(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    iv_archive.append_observation("AAA", "2026-01-02", 0.32, 7, "test")
    added = iv_archive.append_observation("AAA", "2026-01-02", 0.50, 7, "rerun")
    assert added is False
    rows = json.load(open(tmp_path / "AAA.json"))["rows"]
    assert rows["2026-01-02"][0] == 0.32  # first write survives


def test_append_observation_rejects_non_finite_or_non_positive_iv(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    assert iv_archive.append_observation("AAA", "2026-01-02", None, 7, "test") is False
    assert iv_archive.append_observation("AAA", "2026-01-02", 0.0, 7, "test") is False
    assert iv_archive.append_observation("AAA", "2026-01-02", -0.1, 7, "test") is False
    assert iv_archive.append_observation("AAA", "2026-01-02", float("nan"), 7, "test") is False
    assert not (tmp_path / "AAA.json").exists()


def test_load_series_is_all_empty_for_a_never_archived_ticker(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    assert iv_archive.load_series("NEVER") == {"dates": [], "ivs": [], "dtes": []}


def test_load_series_returns_oldest_first(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    iv_archive.append_observation("AAA", "2026-01-03", 0.40, 7, "test")
    iv_archive.append_observation("AAA", "2026-01-02", 0.30, 7, "test")
    series = iv_archive.load_series("AAA")
    assert series["dates"] == ["2026-01-02", "2026-01-03"]
    assert series["ivs"] == [0.30, 0.40]
    assert series["dtes"] == [7, 7]


def test_iv_percentile_none_below_minimum_samples(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    for day in range(1, 30):  # far short of the 60-sample floor
        iv_archive.append_observation("AAA", f"2026-01-{day:02d}", 0.30, 7, "test")
    assert iv_archive.iv_percentile("AAA") is None


def test_iv_percentile_ranks_the_latest_reading_among_its_own_history(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    base = datetime(2026, 1, 1)
    # 60 quiet readings at 0.20, then a spike to 0.90 as the 61st (latest) observation -
    # the latest reading should rank at (or very near) the top of its own history.
    for offset in range(60):
        iv_archive.append_observation("AAA", (base + timedelta(days=offset)).date().isoformat(), 0.20, 7, "test")
    iv_archive.append_observation("AAA", (base + timedelta(days=60)).date().isoformat(), 0.90, 7, "test")
    percentile = iv_archive.iv_percentile("AAA")
    assert percentile is not None
    assert percentile == 100.0  # strictly the highest of all 61 readings


def test_iv_percentile_never_fabricated_for_a_never_archived_ticker(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    assert iv_archive.iv_percentile("NEVER") is None


def test_archive_health_critical_before_any_run(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    health = iv_archive.archive_health()
    assert health["state"] == "critical"


def test_archive_health_healthy_after_a_recent_run(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    iv_archive.record_run({"mode": "run", "tickers_seen": 3, "rows_added": 3})
    health = iv_archive.archive_health()
    assert health["state"] == "healthy"
    assert health["tickers"] == 3


def test_archive_health_critical_when_stale(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    manifest = {"runs": [{"at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                          "tickers_seen": 1, "rows_added": 1, "archive_tree_sha256": "x"}]}
    json.dump(manifest, open(tmp_path / "archive_manifest.json", "w"))
    health = iv_archive.archive_health()
    assert health["state"] == "critical"
