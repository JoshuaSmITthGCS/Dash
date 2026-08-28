"""The one-time high/low backfill: append-only, resumable, and it must not touch backtest_cache."""
import json

import backfill_price_ranges
import price_archive


def test_live_universe_tickers_matches_price_archive_run_daily():
    # Same source, same shape as price_archive.run_daily's own universe gathering, so a name
    # the daily job would archive is also a name this backfill covers.
    payload = {"research": [{"ticker": "aapl"}], "portfolio_coverage": [{"ticker": "MSFT"}],
              "screen_universe": [{"ticker": "IGNORED"}]}
    assert backfill_price_ranges.live_universe_tickers(payload) == ["AAPL", "MSFT"]


def test_live_universe_tickers_ignores_rows_with_no_ticker(monkeypatch):
    payload = {"research": [{"ticker": ""}, {"name": "no ticker field"}], "portfolio_coverage": []}
    assert backfill_price_ranges.live_universe_tickers(payload) == []


def test_backfill_archives_a_full_history_with_highs_and_lows(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    histories = {
        "AAPL": {"dates": ["2024-01-02", "2024-01-03"], "closes": [190.0, 191.0],
                 "volumes": [1000, 1100], "highs": [191.0, 192.0], "lows": [189.0, 190.0]},
    }

    summary = backfill_price_ranges.backfill(["AAPL"], lambda ticker: histories.get(ticker))

    assert summary == {"tickers_requested": 1, "tickers_archived": 1, "rows_added": 2,
                       "conflicts": 0, "failures": 0}
    rows = json.load(open(tmp_path / "AAPL.json"))["rows"]
    assert rows["2024-01-02"] == [190.0, 1000, 191.0, 189.0]


def test_backfill_never_overwrites_a_date_the_daily_job_already_wrote(tmp_path, monkeypatch):
    # First-write-wins applies here exactly as it does to any other append_series caller: a
    # date the daily job already recorded (close/volume only, from before SA-2026-08-28-01)
    # does not retroactively gain a high/low just because the backfill runs later.
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    price_archive.append_series("AAPL", ["2024-01-02"], [190.0], [1000], "run_daily")
    histories = {"AAPL": {"dates": ["2024-01-02"], "closes": [190.0], "volumes": [1000],
                          "highs": [191.0], "lows": [189.0]}}

    backfill_price_ranges.backfill(["AAPL"], lambda ticker: histories.get(ticker))

    rows = json.load(open(tmp_path / "AAPL.json"))["rows"]
    assert rows["2024-01-02"] == [190.0, 1000]


def test_backfill_is_resumable_a_second_run_adds_nothing_new(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    histories = {"AAPL": {"dates": ["2024-01-02"], "closes": [190.0], "volumes": [1000],
                          "highs": [191.0], "lows": [189.0]}}
    fetcher = lambda ticker: histories.get(ticker)

    first = backfill_price_ranges.backfill(["AAPL"], fetcher)
    second = backfill_price_ranges.backfill(["AAPL"], fetcher)

    assert first["rows_added"] == 1
    assert second["rows_added"] == 0


def test_backfill_records_a_failure_rather_than_raising_on_an_unresolvable_ticker():
    summary = backfill_price_ranges.backfill(["GHOST"], lambda ticker: None)
    assert summary == {"tickers_requested": 1, "tickers_archived": 0, "rows_added": 0,
                       "conflicts": 0, "failures": 1}


def test_run_wires_the_live_universe_into_backfill_and_records_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    monkeypatch.setattr(price_archive, "MANIFEST", str(tmp_path / "manifest.json"))
    fake_advisor = {"research": [{"ticker": "AAPL"}], "portfolio_coverage": []}
    monkeypatch.setattr("common.load_json", lambda name: fake_advisor if name == "advisor.json" else None)
    histories = {"AAPL": {"dates": ["2024-01-02"], "closes": [190.0], "volumes": [1000],
                          "highs": [191.0], "lows": [189.0]}}
    monkeypatch.setattr(backfill_price_ranges, "_default_history_fetcher",
                        lambda: (lambda ticker: histories.get(ticker)))

    summary = backfill_price_ranges.run()

    assert summary["tickers_archived"] == 1
    manifest = json.load(open(tmp_path / "manifest.json"))
    assert manifest["runs"][-1]["mode"] == "backfill_price_ranges"


def test_backfill_respects_a_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(price_archive, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(price_archive, "CONFLICTS", str(tmp_path / "conflicts.jsonl"))
    calls = []

    def fetcher(ticker):
        calls.append(ticker)
        return {"dates": ["2024-01-02"], "closes": [1.0], "volumes": [1], "highs": [1.1], "lows": [.9]}

    backfill_price_ranges.backfill(["AAA", "BBB", "CCC"], fetcher, limit=2)

    assert calls == ["AAA", "BBB"]
