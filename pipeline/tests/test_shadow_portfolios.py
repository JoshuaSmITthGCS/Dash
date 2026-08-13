import json

from shadow_portfolios import (aligned_period_keys, append_payload, build_report,
                               matched_returns, price_session, selections_from_payload,
                               turnover_components, weighted_turnover)


def snapshot(as_of, session, rows):
    return {"as_of": as_of, "methodology": {"price_session": session}, "rows": rows}


def holding(ticker, price, weight):
    return {"ticker": ticker, "price": price, "weight": weight}


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
    stored = sorted(path.read_text() for path in (store / "production").iterdir())
    # A rerun reading the same tape is a re-read of a session already recorded, and is
    # refused before it can reach the store at all.
    changed = {**next_advisor, "research": [{"ticker": "BBB", "score": 99, "price": 100}]}
    result = append_payload(changed, next_benchmark, empty_screens, store)
    assert "production" in result["stale_tape"]
    assert "production" not in result["appended"]
    assert sorted(path.read_text() for path in (store / "production").iterdir()) == stored

    # A later run on the same calendar date whose tape *has* moved on -- the close landed
    # mid-run -- is still refused, because the first observation of a date is the immutable
    # one.
    later_advisor, _ = fixture_payload("2026-08-05", 120, 100, 510)
    later_benchmark = {"histories": {"SPY": {"dates": ["2026-08-06"], "closes": [510]}}}
    assert "production" in append_payload(
        later_advisor, later_benchmark, empty_screens, store)["preserved"]
    assert sorted(path.read_text() for path in (store / "production").iterdir()) == stored

    report = build_report(store)
    by_name = {row["strategy"]: row for row in report["strategies"]}
    production = by_name["Existing production model"]
    assert production["observations"] == 1
    assert production["net_return"] == 4.8  # 5% gross less 20bp initial implementation cost
    assert production["window_start"] == "2026-08-04"
    assert by_name["Structural + tactical model"].get("net_return") is None
    snapshot_path = next((store / "production").iterdir())
    assert json.loads(snapshot_path.read_text())["content_sha256"]


def test_price_session_reads_the_tape_not_the_clock():
    # A Saturday run and the Friday run before it carry the same Friday closes.
    benchmark = {"histories": {"SPY": {"dates": ["2026-08-06", "2026-08-07"],
                                       "closes": [768.56, 773.26]}}}
    assert price_session(benchmark) == ("2026-08-07", 773.26)


def test_a_tape_that_did_not_advance_is_not_an_observation():
    # Same session stamped twice: the second run re-read Friday's closes on Saturday.
    friday = snapshot("2026-08-07", "2026-08-07", [holding("AAA", 100, 1.0)])
    saturday = snapshot("2026-08-08", "2026-08-07", [holding("AAA", 100, 1.0)])
    result = matched_returns([friday, saturday], [friday, saturday])
    assert result["returns"] == []
    assert result["skipped_detail"][0]["reason"] == "PRICE_SESSION_DID_NOT_ADVANCE"


def test_entry_cost_is_charged_on_the_first_observed_period_not_the_first_pair():
    # The opening pair is voided by a stale tape, so the entry charge belongs to the
    # period after it -- previously that charge was skipped along with the pair.
    first = snapshot("2026-08-05", "2026-08-04", [holding("AAA", 100, 1.0)])
    stale = snapshot("2026-08-06", "2026-08-04", [holding("AAA", 100, 1.0)])
    later = snapshot("2026-08-07", "2026-08-06", [holding("AAA", 110, 1.0)])
    result = matched_returns([first, stale, later], [first, stale, later])
    assert result["turnover"] == [1.0]
    assert len(result["returns"]) == 1


def test_a_holding_missing_from_the_next_tape_is_carried_not_voided():
    # A truncated fetch drops one name from a 20-name portfolio. The period survives with
    # that name carried flat; the whole observation is not thrown away.
    holdings = [holding(f"T{index}", 100, 0.05) for index in range(20)]
    start = snapshot("2026-08-05", "2026-08-04", holdings)
    end = snapshot("2026-08-06", "2026-08-06",
                   [holding(row["ticker"], 110, 0.05) for row in holdings[:-1]])
    result = matched_returns([start, end], [start, end])
    assert len(result["returns"]) == 1
    assert abs(result["returns"][0] - 0.095) < 1e-12  # 19 names up 10%, one carried flat
    assert result["periods"][0]["carried_weight"] == 0.05


def test_an_unpriced_majority_still_voids_the_period():
    holdings = [holding(f"T{index}", 100, 0.5) for index in range(2)]
    start = snapshot("2026-08-05", "2026-08-04", holdings)
    end = snapshot("2026-08-06", "2026-08-06", [holding("T0", 110, 1.0)])
    result = matched_returns([start, end], [start, end])
    assert result["returns"] == []
    assert result["skipped_detail"][0]["reason"] == "NEXT_TAPE_MISSING_PRICES"


def test_coverage_growth_is_composition_change_not_turnover():
    # BBB was not priced anywhere in the previous tape, so it could not have been bought.
    previous = [holding("AAA", 100, 1.0)]
    current = [holding("AAA", 100, 0.5), holding("BBB", 50, 0.5)]
    traded, composition = turnover_components(previous, current, investable={"AAA"})
    assert composition == 0.5
    # AAA was diluted to half the book purely by BBB arriving, which is the same coverage
    # change seen from the other side -- not a sale.
    assert traded == 0.0
    # Without an investable set the whole move is charged, as before.
    assert weighted_turnover(previous, current) == 0.5


def test_a_real_rotation_is_still_charged_as_turnover():
    # CCC was priced and passed over last time, so choosing it now is a decision, not
    # coverage widening -- the renormalization must not launder a genuine trade.
    previous = [holding("AAA", 100, 0.5), holding("BBB", 100, 0.5)]
    current = [holding("AAA", 100, 0.5), holding("CCC", 100, 0.5)]
    traded, composition = turnover_components(previous, current,
                                              investable={"AAA", "BBB", "CCC"})
    assert composition == 0.0
    assert traded == 0.5


def test_aligned_window_is_the_intersection_of_observed_sessions(tmp_path):
    store = tmp_path / "store"
    screens = {"structural-tactical": {"status": "unavailable", "results": []},
               "quality-value": {"status": "unavailable", "results": []}}
    momentum = {"status": "success", "results": [{"ticker": "AAA", "eligibility": True,
                                                  "percentile": 99}]}
    for day, price, spy in (("2026-08-04", 100, 500), ("2026-08-05", 110, 505),
                            ("2026-08-06", 120, 510)):
        advisor = {"generated_at": f"{day}T12:00:00Z",
                   "research": [{"ticker": "AAA", "score": 90, "price": price}]}
        benchmark = {"histories": {"SPY": {"dates": [day], "closes": [spy]}}}
        # The momentum sleeve only starts publishing on the second day, so it observes one
        # fewer period than production and SPY do.
        append_payload(advisor, benchmark,
                       {**screens, "momentum": momentum if day > "2026-08-04"
                        else {"status": "unavailable", "results": []}}, store)
    assert aligned_period_keys(store) == {("2026-08-05", "2026-08-06")}

    report = build_report(store)
    assert report["aligned_window"]["observations"] == 1
    by_name = {row["strategy"]: row for row in report["strategies"]}
    production = by_name["Existing production model"]
    # Over its own window production compounds two periods; the aligned window is the one
    # period the later-starting sleeve was also in the market for.
    assert production["observations"] == 2
    assert production["aligned"]["observations"] == 1
    assert production["aligned"]["window_start"] == "2026-08-05"
    assert by_name["Momentum sleeve"]["aligned"]["observations"] == 1


def test_swing_and_disclosure_strategies_select_from_their_own_screens():
    advisor, benchmark = fixture_payload()
    selected = selections_from_payload(advisor, benchmark, {
        "swing": {"status": "success", "results": [
            {"ticker": "BBB", "eligibility": True, "composite_z": 1.4},
            {"ticker": "AAA", "eligibility": False, "composite_z": 2.0},
        ]},
        "congress-trades": {"status": "partial", "results": [
            {"symbol": "AAA", "disclosure_date": "2026-08-01", "transaction_date": "2026-07-01",
             "representative": "Rep A", "amount_lower": 50000.0, "transaction_type": "Purchase",
             "asset_type": "Stock", "flags": []},
        ]},
        "institutional-13f": {"status": "success", "results": []},
    }, as_of="2026-08-04")

    # The swing sleeve holds only the eligible row; the ineligible one is not backfilled.
    assert [row["ticker"] for row in selected["swing"]] == ["BBB"]
    assert [row["ticker"] for row in selected["political_institutional"]] == ["AAA"]
    assert selected["political_institutional"][0]["weight"] == 1.0


def test_the_disclosure_strategy_collects_from_a_partial_congress_screen():
    # congress-trades.json publishes status "partial" whenever any one of its four upstream
    # sources is dark, which is its normal state. Requiring "success" would mean this
    # strategy silently never collected a snapshot at all.
    advisor, benchmark = fixture_payload()
    congress = {"status": "partial", "results": [
        {"symbol": "AAA", "disclosure_date": "2026-08-01", "transaction_date": "2026-07-01",
         "representative": "Rep A", "amount_lower": 50000.0, "transaction_type": "Purchase",
         "asset_type": "Stock", "flags": []},
    ]}
    selected = selections_from_payload(advisor, benchmark, {"congress-trades": congress},
                                       as_of="2026-08-04")
    assert [row["ticker"] for row in selected["political_institutional"]] == ["AAA"]

    skipped = selections_from_payload(
        advisor, benchmark, {"congress-trades": {**congress, "status": "skipped"}},
        as_of="2026-08-04")
    assert skipped["political_institutional"] == []


def test_a_disclosure_is_aged_against_the_snapshot_date_not_the_wall_clock():
    # Bootstrapping replays archived payloads. Scoring a months-old commit's disclosures with
    # today's freshness decay would give the reconstructed history a signal that was never
    # visible then.
    advisor, benchmark = fixture_payload()
    screens = {"congress-trades": {"status": "partial", "results": [
        {"symbol": "AAA", "disclosure_date": "2026-08-01", "transaction_date": "2026-07-01",
         "representative": "Rep A", "amount_lower": 50000.0, "transaction_type": "Purchase",
         "asset_type": "Stock", "flags": []},
    ]}}

    fresh = selections_from_payload(advisor, benchmark, screens, as_of="2026-08-04")
    before_disclosure = selections_from_payload(advisor, benchmark, screens, as_of="2026-07-15")

    assert fresh["political_institutional"]
    assert before_disclosure["political_institutional"] == []


def test_the_report_covers_every_declared_strategy_including_the_new_ones():
    labels = {row["strategy"] for row in build_report("/nonexistent")["strategies"]}
    assert "Swing signals only" in labels
    assert "Political + institutional trades only" in labels
