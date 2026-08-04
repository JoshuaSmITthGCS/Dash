import early_session_research
from early_session_research import capability_report, enforce_candidate_contract


def test_hard_data_gates_kill_unsupported_live_screens(monkeypatch):
    monkeypatch.setattr(early_session_research, "marketstack_depth",
                        lambda: {"rows": 0, "modes": [], "last_observed": None})
    report = capability_report(generated_at="2026-08-03T12:00:00+00:00")
    assert report["screens"]["premarket_reversal"]["status"] == "killed"
    assert report["screens"]["first_hour_reversal"]["status"] == "killed"
    assert report["screens"]["premarket_reversal"]["reason_code"] == "NO_EXTENDED_HOURS_OHLCV"
    assert report["execution_quality"]["status"] == "unavailable"
    assert all(screen["candidate_count"] == 0 for screen in report["screens"].values())
    premarket = next(row for row in report["capabilities"] if row["capability"] == "Premarket and after-hours OHLCV")
    assert premarket["available"] is False


def test_collected_marketstack_data_unblocks_the_data_capability_but_not_the_screen(monkeypatch):
    monkeypatch.setattr(early_session_research, "marketstack_depth", lambda: {
        "rows": 42, "modes": ["intraday"], "last_observed": "2026-08-04T21:00:00+00:00"})
    report = capability_report(generated_at="2026-08-04T21:05:00+00:00")

    premarket = next(row for row in report["capabilities"] if row["capability"] == "Premarket and after-hours OHLCV")
    first_hour = next(row for row in report["capabilities"] if row["capability"] == "First-hour intraday bars")
    assert premarket["available"] is True
    assert first_hour["available"] is True
    assert "Marketstack" in premarket["provider"]
    # Data flowing does not make the reversal screens live - detection logic still doesn't exist.
    assert report["screens"]["premarket_reversal"]["status"] == "killed"
    assert report["screens"]["premarket_reversal"]["reason_code"] == "SUPPORT_ZONE_ENGINE_NOT_BUILT"


def test_missing_contract_field_never_becomes_actionable():
    candidate = enforce_candidate_contract({
        "setup": "Gap stabilized near a possible support zone",
        "trigger": "VWAP reclaim",
        "confirmation": "",
        "invalidation": "Loss of support",
        "state": "confirmed_reversal",
        "actionable": True,
        "data_quality": {"fresh": True},
    })
    assert candidate["state"] == "watch"
    assert candidate["actionable"] is False
    assert candidate["missing_contract_fields"] == ["confirmation"]


def test_stale_data_overrides_complete_positive_candidate():
    candidate = enforce_candidate_contract({
        "setup": "Eligible", "trigger": "Reclaim", "confirmation": "Volume and RS",
        "invalidation": "Support loss", "state": "confirmed_reversal", "actionable": True,
        "data_quality": {"fresh": False},
    })
    assert candidate["state"] == "insufficient_data"
    assert candidate["actionable"] is False
