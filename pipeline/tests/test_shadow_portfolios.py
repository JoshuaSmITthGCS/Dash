import json

from shadow_portfolios import (append_payload, build_report, matched_returns,
                               selections_from_payload, weighted_turnover)


def fixture_payload(day="2026-08-04", a=100, b=100, spy=500):
    advisor = {
        "generated_at": f"{day}T12:00:00Z",
        "research": [
            {"ticker": "AAA", "score": 90, "price": a},
            {"ticker": "BBB", "score": 80, "price": b},
        ],
        "screen_universe": [],
    }
    benchmark = {"histories": {"SPY": {"dates": [day], "closes": [spy]}}}
    return advisor, benchmark


def test_selections_are_equal_weighted_and_do_not_invent_unavailable_sleeves():
    advisor, benchmark = fixture_payload()
    selected = selections_from_payload(advisor, benchmark, {
        "structural-tactical": {"status": "unavailable", "results": []},
        "momentum": {"status": "success", "results": [
            {"ticker": "BBB", "eligibility": True, "percentile": 99},
        ]},
        "quality-value": {"status": "unavailable", "results": []},
    })
    assert [row["ticker"] for row in selected["production"]] == ["AAA", "BBB"]
    assert selected["production"][0]["weight"] == 0.5
    assert selected["momentum"][0]["ticker"] == "BBB"
    assert selected["structural_tactical"] == []
    assert selected["combined"] == []


def test_turnover_and_forward_returns_use_the_next_immutable_tape():
    start = {"as_of": "2026-08-04", "rows": [
        {"ticker": "AAA", "price": 100, "weight": .5},
        {"ticker": "BBB", "price": 100, "weight": .5},
    ]}
    end = {"as_of": "2026-08-05", "rows": [
        {"ticker": "AAA", "price": 110, "weight": .5},
        {"ticker": "BBB", "price": 90, "weight": .5},
    ]}
    result = matched_returns([start, end], [start, end])
    assert abs(result["returns"][0]) < 1e-12
    assert result["turnover"] == [1]
    assert weighted_turnover(start["rows"], end["rows"]) == 0


def test_pipeline_appends_once_per_day_and_publishes_net_metrics(tmp_path):
    store = tmp_path / "store"
    first_advisor, first_benchmark = fixture_payload("2026-08-04", 100, 100, 500)
    next_advisor, next_benchmark = fixture_payload("2026-08-05", 110, 100, 505)
    empty_screens = {
        "structural-tactical": {"status": "unavailable", "results": []},
        "momentum": {"status": "unavailable", "results": []},
        "quality-value": {"status": "unavailable", "results": []},
    }
    append_payload(first_advisor, first_benchmark, empty_screens, store)
    append_payload(next_advisor, next_benchmark, empty_screens, store)
    # A different same-day payload cannot rewrite the first immutable selection.
    changed = {**next_advisor, "research": [{"ticker": "BBB", "score": 99, "price": 100}]}
    result = append_payload(changed, next_benchmark, empty_screens, store)
    assert "production" in result["preserved"]

    report = build_report(store)
    by_name = {row["strategy"]: row for row in report["strategies"]}
    production = by_name["Existing production model"]
    assert production["observations"] == 1
    assert production["net_return"] == 4.8  # 5% gross less 20bp initial implementation cost
    assert production["window_start"] == "2026-08-04"
    assert by_name["Structural + tactical model"].get("net_return") is None
    snapshot_path = next((store / "production").iterdir())
    assert json.loads(snapshot_path.read_text())["content_sha256"]
