from datetime import date, timedelta

import build_momentum_screen as module


def fake_history(sessions=520, start=date(2023, 1, 1), start_price=100, drift=0.15):
    dates = [(start + timedelta(days=index)).isoformat() for index in range(sessions)]
    closes = [start_price + index * drift for index in range(sessions)]
    volumes = [1_000_000 + (index % 30) * 10_000 for index in range(sessions)]
    return {"dates": dates, "closes": closes, "volumes": volumes}


def make_yahoo_history(per_ticker):
    def _yahoo_history(ticker, yf):
        return per_ticker.get(ticker, {"dates": [], "closes": [], "volumes": []})
    return _yahoo_history


def test_build_rows_scores_tickers_with_enough_history(monkeypatch):
    universe = [
        {"ticker": "AAA", "sector": "Technology", "market_cap": 5e9, "score": 80.0, "confidence": 0.9},
        {"ticker": "BBB", "sector": "Technology", "market_cap": 4e9, "score": 60.0, "confidence": 0.7},
        {"ticker": "CCC", "sector": "Technology", "market_cap": 3e9, "score": 40.0, "confidence": 0.5},
        {"ticker": "DDD", "sector": "Technology", "market_cap": 2e9, "score": 20.0, "confidence": 0.3},
    ]
    per_ticker = {row["ticker"]: fake_history(drift=0.1 * (index + 1)) for index, row in enumerate(universe)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))

    rows = module.build_rows(universe, yf=None)

    assert len(rows) == 4
    assert all(row["history_sessions"] == 520 for row in rows)
    assert all(row["factors"]["momentum_12_1"] is not None for row in rows)
    assert all(row["structural_score"] == entry["score"] for row, entry in zip(rows, universe))


def test_build_rows_skips_tickers_with_thin_history(monkeypatch):
    universe = [{"ticker": "THIN", "sector": "Technology", "market_cap": 1e9}]
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(
        {"THIN": fake_history(sessions=10)}))

    rows = module.build_rows(universe, yf=None)
    assert rows == []


def test_previous_members_reads_current_membership_flags():
    screen = {"results": [
        {"ticker": "AAA", "current_membership": True},
        {"ticker": "BBB", "current_membership": False},
    ]}
    assert module.previous_members(screen) == {"AAA": True}
    assert module.previous_members(None) == {}


def test_run_publishes_scored_results(monkeypatch):
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    universe = [
        {"ticker": ticker, "sector": "Technology", "market_cap": (index + 1) * 1e9,
         "score": 20.0 + index * 10, "confidence": 0.5 + index * 0.05}
        for index, ticker in enumerate(tickers)
    ]
    per_ticker = {row["ticker"]: fake_history(drift=0.1 * (index + 1)) for index, row in enumerate(universe)}
    monkeypatch.setattr(module, "yahoo_history", make_yahoo_history(per_ticker))

    loaded = {"advisor.json": {"research": universe}, "screens/momentum.json": None}
    saved = {}
    monkeypatch.setattr(module, "load_json", lambda name: loaded.get(name))
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.__setitem__(name, payload))

    result = module.run()

    assert result["status"] == "success"
    assert saved["screens/momentum.json"] == result
    assert len(result["results"]) == 6
    ranks = [row["rank"] for row in result["results"]]
    assert ranks == sorted(ranks)
    # Model Risk Register #8 / docs/AUDIT-ROADMAP.md item 27: this screen's calendar
    # month-end momentum_12_1 and the champion's fixed-trading-day-offset momentum_12_1
    # can diverge, and that divergence must be disclosed, not silent.
    assert "calendar month-end" in result["coverage_note"]
    assert "risk_metrics.py" in result["coverage_note"]


def test_run_reports_unavailable_with_no_universe(monkeypatch):
    monkeypatch.setattr(module, "load_json", lambda name: None)
    assert module.run() is None
