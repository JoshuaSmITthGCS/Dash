import json
import os
from datetime import date, timedelta

import build_tactical_screens as module


def sessions_from(start, count):
    day, output = date.fromisoformat(start), []
    while len(output) < count:
        if day.weekday() < 5:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def cache_entry(trend=1.0, count=400, volume=1_000_000.0):
    """A price path with a steady per-session drift, long enough for 12-1 momentum."""
    dates = sessions_from("2024-08-01", count)
    closes = [100.0 * (trend ** index) for index in range(count)]
    return {"dates": dates, "closes": closes, "volumes": [volume] * count}


def universe_row(ticker="AAA", score=70.0, breadth=.3, magnitude=.02, sector="Technology"):
    return {"ticker": ticker, "sector": sector, "score": score, "is_etf": False,
            "score_variants": {"champion": {"confidence": .8}},
            "estimate_detail": {"revision_breadth_30d": breadth,
                                "eps_revision_30d_pct": magnitude}}


def build(rows, entries=None, estimates_root=None):
    entries = entries or {}
    built = module.build_rows(rows, "2026-08-09T00:00:00+00:00",
                              entry_for=lambda ticker: entries.get(ticker),
                              estimates_root=estimates_root or "/nonexistent",
                              observations={})
    return module.score_rows(module.rank_factors(module.attach_tradability(
        module.attach_industry_factors(built))))


def test_realized_volatility_rises_with_the_size_of_the_swings():
    calm = [100.0 + (index % 2) * .1 for index in range(61)]
    wild = [100.0 + (index % 2) * 20.0 for index in range(61)]

    assert module.realized_volatility(calm) < module.realized_volatility(wild)


def test_realized_volatility_needs_a_real_window():
    assert module.realized_volatility([100.0, 101.0]) is None


def test_industry_revision_breadth_excludes_the_company_being_measured():
    rows = build([universe_row("AAA", breadth=1.0), universe_row("BBB", breadth=0.0),
                  universe_row("CCC", breadth=0.0)])
    by_ticker = {row["ticker"]: row for row in rows}

    # AAA's own breadth of 1.0 must not appear in the benchmark it is compared against.
    assert by_ticker["AAA"]["raw"]["industry_revision_breadth"] == 0.0
    assert by_ticker["BBB"]["raw"]["industry_revision_breadth"] == .5


def test_a_company_alone_in_its_peer_group_gets_no_industry_breadth():
    rows = build([universe_row("AAA", sector="Technology"),
                  universe_row("BBB", sector="Utilities")])

    assert all(row["raw"]["industry_revision_breadth"] is None for row in rows)


def test_factors_are_ranked_onto_the_zero_to_hundred_scale_the_model_reads():
    rows = build([universe_row("AAA", breadth=.9), universe_row("BBB", breadth=.1),
                  universe_row("CCC", breadth=.5)])
    by_ticker = {row["ticker"]: row for row in rows}

    assert by_ticker["AAA"]["factors"]["revision_agreement"] == 100.0
    assert by_ticker["CCC"]["factors"]["revision_agreement"] == 50.0
    assert by_ticker["BBB"]["factors"]["revision_agreement"] == 0.0


def test_tradability_rewards_the_liquid_and_calm_name_over_the_thin_volatile_one():
    liquid = cache_entry(trend=1.0005, volume=50_000_000.0)
    thin = {**cache_entry(trend=1.0005, volume=1_000.0)}
    thin["closes"] = [100.0 + (index % 2) * 30.0 for index in range(len(thin["dates"]))]
    rows = build([universe_row("AAA"), universe_row("BBB")],
                 entries={"AAA": liquid, "BBB": thin})
    by_ticker = {row["ticker"]: row for row in rows}

    assert by_ticker["AAA"]["raw"]["risk_tradability"] > by_ticker["BBB"]["raw"]["risk_tradability"]


def test_a_row_with_no_collected_estimate_history_keeps_the_forward_collection_flag():
    rows = build([universe_row("AAA"), universe_row("BBB")])

    assert rows[0]["snapshot_available"] is False
    assert "FORWARD_COLLECTION_ONLY" in rows[0]["reason_codes"]
    assert "REVISION_BACKTEST_UNAVAILABLE" in rows[0]["reason_codes"]


def test_coverage_is_published_and_a_thin_row_is_not_called_eligible():
    rows = build([universe_row("AAA", breadth=None, magnitude=None),
                  universe_row("BBB", breadth=None, magnitude=None)])
    payload = module.timeliness_payload(rows, "2026-08-09T00:00:00Z")

    assert all(result["coverage"] < module.MINIMUM_COVERAGE for result in payload["results"])
    assert not any(result["eligibility"] for result in payload["results"])
    assert all("LOW_FACTOR_COVERAGE" in result["reason_codes"] for result in payload["results"])


def test_timeliness_labels_follow_the_score_bands():
    assert module.timeliness_label(90) == "accelerating expectations"
    assert module.timeliness_label(65) == "improving expectations"
    assert module.timeliness_label(45) == "stable expectations"
    assert module.timeliness_label(10) == "deteriorating expectations"
    assert module.timeliness_label(None) == "not scored"


def test_timeliness_ranks_the_stronger_revisions_first():
    rows = build([universe_row("AAA", breadth=.9, magnitude=.09),
                  universe_row("BBB", breadth=-.9, magnitude=-.09),
                  universe_row("CCC", breadth=.1, magnitude=.01)])

    payload = module.timeliness_payload(rows, "2026-08-09T00:00:00Z")

    assert [result["ticker"] for result in payload["results"]][0] == "AAA"
    assert payload["results"][0]["percentile"] == 100.0
    assert payload["status"] == "success"
    assert payload["model_version"] == "tactical-v1.0.0"


def test_the_matrix_only_publishes_rows_that_have_both_axes():
    rows = build([universe_row("AAA"), universe_row("BBB", score=None)])

    payload = module.matrix_payload(rows, "2026-08-09T00:00:00Z")

    assert [result["ticker"] for result in payload["results"]] == ["AAA"]
    assert payload["model_version"] == "matrix-v1.0.0"
    assert sum(payload["quadrants"].values()) == 1


def test_matrix_quadrants_separate_the_two_horizons():
    rows = build([universe_row("AAA", score=90.0, breadth=.9, magnitude=.09),
                  universe_row("BBB", score=90.0, breadth=-.9, magnitude=-.09),
                  universe_row("CCC", score=10.0, breadth=.9, magnitude=.09)])

    payload = module.matrix_payload(rows, "2026-08-09T00:00:00Z")
    by_ticker = {result["ticker"]: result["classification"] for result in payload["results"]}

    assert by_ticker["AAA"] == "high-conviction candidate"
    assert by_ticker["BBB"] == "quality company, wait"
    assert by_ticker["CCC"] == "tactical-only candidate"


def test_an_empty_universe_publishes_a_reason_code_not_an_empty_success():
    timeliness = module.timeliness_payload([], "2026-08-09T00:00:00Z")
    matrix = module.matrix_payload([], "2026-08-09T00:00:00Z")

    assert timeliness["status"] == "unavailable"
    assert timeliness["reason_code"] == "NO_TACTICAL_FACTORS_AVAILABLE"
    assert matrix["status"] == "unavailable"
    assert matrix["reason_code"] == "NO_TWO_AXIS_COVERAGE"


def snapshot(observed_at, consensus, dispersion=.2):
    return {"schema_version": "1.0.0", "ticker": "AAA", "observed_at": observed_at,
            "source": "test", "point_in_time": True, "content_sha256": "x",
            "estimates": {"horizons": {"current_year": {"eps_consensus": consensus,
                                                        "dispersion": dispersion}}}}


def test_estimate_diagnostics_report_a_narrowing_spread_as_a_positive_trend(tmp_path):
    directory = tmp_path / "AAA"
    directory.mkdir()
    for name, payload in (("20260601T000000Z-a.json", snapshot("2026-06-01T00:00:00+00:00", 10.0, .4)),
                          ("20260801T000000Z-b.json", snapshot("2026-08-01T00:00:00+00:00", 11.0, .1))):
        (directory / name).write_text(json.dumps(payload))

    diagnostics = module.estimate_diagnostics("AAA", "2026-08-09T00:00:00+00:00",
                                              root=str(tmp_path))

    assert diagnostics["dispersion_trend"] == (.4 - .1) / .4


def test_estimate_diagnostics_stay_unavailable_on_a_single_observation(tmp_path):
    directory = tmp_path / "AAA"
    directory.mkdir()
    (directory / "20260801T000000Z-b.json").write_text(
        json.dumps(snapshot("2026-08-01T00:00:00+00:00", 11.0)))

    diagnostics = module.estimate_diagnostics("AAA", "2026-08-09T00:00:00+00:00",
                                              root=str(tmp_path))

    assert diagnostics == {"available": False, "revision_acceleration": None,
                           "dispersion_trend": None}


def test_estimate_diagnostics_tolerate_a_store_that_does_not_exist():
    diagnostics = module.estimate_diagnostics("AAA", "2026-08-09T00:00:00+00:00",
                                              root=os.path.join("nowhere", "at", "all"))

    assert diagnostics["available"] is False


def test_both_tactical_screens_cap_their_published_head(monkeypatch):
    monkeypatch.setattr(module, "PUBLISH_LIMIT", 2)
    rows = build([universe_row(ticker) for ticker in ("AAA", "BBB", "CCC", "DDD")])

    timeliness = module.timeliness_payload(rows, "2026-08-09T00:00:00Z")
    matrix = module.matrix_payload(rows, "2026-08-09T00:00:00Z")

    assert len(timeliness["results"]) == 2
    assert timeliness["universe_scored"] == 4
    assert len(matrix["results"]) == 2
    # The quadrant split describes everything scored, not just the published head.
    assert sum(matrix["quadrants"].values()) == 4
