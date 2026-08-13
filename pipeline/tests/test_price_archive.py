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


def _iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def test_resolvable_delisted_tickers_filters_by_age_and_universe(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "REPO", str(tmp_path))
    log_dir = tmp_path / "research" / "audit" / "survivorship" / "data"
    log_dir.mkdir(parents=True)
    json.dump([
        {"ticker": "FRESH", "event_date": _iso_days_ago(30)},       # recent, not in universe: kept
        {"ticker": "STALE", "event_date": _iso_days_ago(400)},      # past the retention window: dropped
        {"ticker": "LIVE", "event_date": _iso_days_ago(10)},        # in the live universe: dropped
        {"ticker": None, "event_date": _iso_days_ago(10)},          # unresolvable record: skipped
    ], open(log_dir / "delisting_log.json", "w"))
    resolvable = price_archive._resolvable_delisted_tickers({"LIVE"})
    assert resolvable == {"FRESH"}


def test_run_daily_appends_universe_and_resolvable_delisted(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "archive" / "conflicts.jsonl"))
    monkeypatch.setattr(price_archive, "MANIFEST", str(tmp_path / "archive" / "manifest.json"))
    monkeypatch.setattr(price_archive, "REPO", str(tmp_path))
    log_dir = tmp_path / "research" / "audit" / "survivorship" / "data"
    log_dir.mkdir(parents=True)
    json.dump([{"ticker": "DEADCO", "event_date": _iso_days_ago(30)}],
              open(log_dir / "delisting_log.json", "w"))

    fake_advisor = {"research": [{"ticker": "AAPL"}], "portfolio_coverage": [{"ticker": "MSFT"}]}
    monkeypatch.setattr("common.load_json", lambda name: fake_advisor if name == "advisor.json" else None)

    histories = {
        "AAPL": {"dates": ["2026-08-12"], "closes": [200.0], "volumes": [1000]},
        "MSFT": {"dates": ["2026-08-12"], "closes": [300.0], "volumes": [2000]},
        "DEADCO": {"dates": ["2026-08-01"], "closes": [1.0], "volumes": [500]},
    }
    tickers, rows = price_archive.run_daily(history_fetcher=lambda ticker: histories.get(ticker, {}))
    assert tickers == 3
    assert rows == 3
    for ticker in ("AAPL", "MSFT", "DEADCO"):
        assert json.load(open(tmp_path / "archive" / f"{ticker}.json"))["rows"]
    manifest = json.load(open(tmp_path / "archive" / "manifest.json"))
    last_run = manifest["runs"][-1]
    assert last_run["mode"] == "run_daily"
    assert last_run["delisted_tickers_polled"] == 1
