from early_session_research import capability_report, enforce_candidate_contract


def test_hard_data_gates_kill_unsupported_live_screens():
    report = capability_report(generated_at="2026-08-03T12:00:00+00:00")
    assert report["screens"]["premarket_reversal"]["status"] == "killed"
    assert report["screens"]["first_hour_reversal"]["status"] == "killed"
    assert report["execution_quality"]["status"] == "unavailable"
    assert all(screen["candidate_count"] == 0 for screen in report["screens"].values())


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
