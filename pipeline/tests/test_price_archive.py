"""The price archive is append-only, conflict-logging, and loud when stale."""
import json
from datetime import datetime, timedelta, timezone

import price_archive


def test_append_only_first_write_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    added, conflicts = price_archive.append_series(
        "DEAD", ["2026-01-02", "2026-01-03"], [10.0, 11.0], [100, 200], "test")
    assert (added, conflicts) == (2, 0)
    added, conflicts = price_archive.append_series(
        "DEAD", ["2026-01-03", "2026-01-06"], [99.0, 12.0], [1, 300], "restated")
    assert added == 1
    assert conflicts == 1
    rows = json.load(open(tmp_path / "DEAD.json"))["rows"]
    assert rows["2026-01-03"][0] == 11.0  # first write survives the restatement
    logged = open(tmp_path / "conflicts.jsonl").read()
    assert "restated" in logged


def test_health_goes_critical_when_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "MANIFEST", str(tmp_path / "m.json"))
    assert price_archive.archive_health()["state"] == "critical"
    json.dump({"runs": [{"at": datetime.now(timezone.utc).isoformat(), "tickers": 5}]},
              open(tmp_path / "m.json", "w"))
    assert price_archive.archive_health()["state"] == "healthy"
    stale = datetime.now(timezone.utc) + timedelta(days=10)
    assert price_archive.archive_health(now=stale)["state"] == "critical"
