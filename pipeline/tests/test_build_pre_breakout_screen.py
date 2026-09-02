from datetime import date, timedelta

import build_pre_breakout_screen as module
import pre_breakout_signals as pbs


def sessions_from(start, count):
    day, output = date.fromisoformat(start), []
    while len(output) < count:
        if day.weekday() < 5:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def cache_entry(count=400, drift=1.001, volume=5_000_000.0, price=100.0, income=None, balance=None):
    dates = sessions_from("2024-08-01", count)
    closes = [price * (drift ** index) for index in range(count)]
    volumes = [volume] * count
    entry = {"dates": dates, "closes": closes, "volumes": volumes}
    if income is not None:
        entry["income"] = income
    if balance is not None:
        entry["balance"] = balance
    return entry


def universe_row(ticker="AAA", **overrides):
    return {"ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology", "score": 70.0,
           "is_etf": False, "price": 100.0, "market_cap": 5e9, "data_coverage": .9, **overrides}


def entries_for(mapping):
    return lambda ticker, root=None: mapping.get(ticker)


def no_acceleration(ticker, as_of, concept="net_income"):
    return None


def no_sue(ticker, as_of, sessions, config):
    return None


# ---------------------------------------------------------------------------
# The builder
# ---------------------------------------------------------------------------

def test_build_rows_reads_cached_series_and_skips_funds_and_thin_history():
    universe = [universe_row("AAA"), {**universe_row("FUND"), "is_etf": True}, universe_row("NOHIST")]
    entries = entries_for({"AAA": cache_entry()})

    rows = module.build_rows(universe, entry_for=entries, observations={}, observation_rows=[],
                             acceleration_for=no_acceleration, sue_resolver=no_sue,
                             archive_for=lambda ticker: None)

    assert [row["ticker"] for row in rows] == ["AAA"]
    assert rows[0]["history_sessions"] == 400
    assert rows[0]["raw_factors"]["momentum_12_1"] is not None
    assert rows[0]["median_dollar_volume_60d"] > 0


def test_build_rows_computes_margin_turn_and_roa_delta_from_the_cached_statements():
    statement = lambda values: {"periods": ["2025-12-31", "2024-12-31"], "rows": values}
    income = statement({"Total Revenue": [1000.0, 900.0], "Operating Income": [250.0, 200.0],
                        "Net Income": [180.0, 140.0]})
    balance = statement({"Total Assets": [2000.0, 1800.0]})
    universe = [universe_row("AAA")]
    entries = entries_for({"AAA": cache_entry(income=income, balance=balance)})

    rows = module.build_rows(universe, entry_for=entries, observations={}, observation_rows=[],
                             acceleration_for=no_acceleration, sue_resolver=no_sue,
                             archive_for=lambda ticker: None)

    assert rows[0]["raw_factors"]["margin_turn"] is not None
    assert rows[0]["raw_factors"]["roa_delta"] is not None
    # Cross-checked directly against fundamentals_extended, which the module reuses rather
    # than reimplementing.
    import fundamentals_extended as fx
    assert rows[0]["raw_factors"]["margin_turn"] == fx.derive_margins(income)["operating_margin_trend"]
    assert rows[0]["raw_factors"]["roa_delta"] == fx.derive_roa_delta(income, balance)


def test_build_rows_fills_industry_relative_momentum_after_the_peer_pass():
    universe = [universe_row("AAA", sector="Technology"), universe_row("BBB", sector="Technology"),
               universe_row("CCC", sector="Technology"), universe_row("DDD", sector="Technology"),
               universe_row("EEE", sector="Technology")]
    entries = entries_for({row["ticker"]: cache_entry(drift=1.001 + 0.0002 * index)
                          for index, row in enumerate(universe)})

    rows = module.build_rows(universe, entry_for=entries, observations={}, observation_rows=[],
                             acceleration_for=no_acceleration, sue_resolver=no_sue,
                             archive_for=lambda ticker: None)

    # With 5 same-sector peers all resolving momentum_12_1, the leave-one-out benchmark has
    # enough peers (research_screens_v2.industry_relative_returns' minimum_peer_count is 4)
    # to resolve for every row.
    assert all(row["raw_factors"]["industry_relative_momentum"] is not None for row in rows)


def test_build_rows_signs_path_smoothness_by_momentum_direction():
    universe = [universe_row("UP"), universe_row("DOWN")]
    entries = entries_for({"UP": cache_entry(drift=1.003), "DOWN": cache_entry(drift=0.997)})

    rows = module.build_rows(universe, entry_for=entries, observations={}, observation_rows=[],
                             acceleration_for=no_acceleration, sue_resolver=no_sue,
                             archive_for=lambda ticker: None)

    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["UP"]["raw_factors"]["path_smoothness"] > 0
    assert by_ticker["DOWN"]["raw_factors"]["path_smoothness"] < 0


def test_build_rows_wires_insider_activity_and_observed_solvency_fields():
    universe = [universe_row("AAA", insider_activity={"score_points": 2.5})]
    entries = entries_for({"AAA": cache_entry()})
    observations = {"AAA": {"altman_z": 1.2, "interest_coverage": 6.0, "market_cap": 4e9}}

    rows = module.build_rows(universe, entry_for=entries, observations=observations,
                             observation_rows=[], acceleration_for=no_acceleration,
                             sue_resolver=no_sue, archive_for=lambda ticker: None)

    assert rows[0]["raw_factors"]["insider_cluster_score"] == 2.5
    assert rows[0]["observed"]["altman_z"] == 1.2
    assert rows[0]["observed"]["interest_coverage"] == 6.0


def test_build_rows_computes_short_interest_change_from_the_observation_history():
    universe = [universe_row("AAA")]
    entries = entries_for({"AAA": cache_entry()})
    observation_rows = [
        {"ticker": "AAA", "observed_at": "2024-01-01", "values": {"short_percent_of_float": 5.0}},
        {"ticker": "AAA", "observed_at": "2024-02-01", "values": {"short_percent_of_float": 10.0}},
        {"ticker": "AAA", "observed_at": "2024-03-01", "values": {"short_percent_of_float": 6.0}},
    ]

    # No as_of override: the observation_rows are dated 2024, safely before "today" whatever
    # that is, and the momentum leg needs its own as_of to fall inside cache_entry()'s price
    # series (which starts 2024-08-01), not before it.
    rows = module.build_rows(universe, entry_for=entries, observations={},
                             observation_rows=observation_rows, acceleration_for=no_acceleration,
                             sue_resolver=no_sue, archive_for=lambda ticker: None)

    assert rows[0]["raw_factors"]["short_interest_change"] == (10.0 - 6.0) / 10.0


def test_sue_resolver_drops_a_surprise_once_its_drift_window_has_closed():
    sessions = sessions_from("2024-08-01", 400)
    fresh = {"sue": 2.0, "release_datetime": sessions[-2] + "T20:00:00Z"}
    stale = {"sue": 2.0, "release_datetime": sessions[-100] + "T20:00:00Z"}

    resolved_fresh = module.resolve_sue("AAA", sessions[-1], sessions, pbs.DEFAULT_CONFIG,
                                        sue_for=lambda ticker, as_of: fresh)
    resolved_stale = module.resolve_sue("AAA", sessions[-1], sessions, pbs.DEFAULT_CONFIG,
                                        sue_for=lambda ticker, as_of: stale)

    assert resolved_fresh == fresh
    assert resolved_stale is None


def test_run_publishes_ranked_rows_with_their_evidence(monkeypatch):
    universe = [universe_row(f"T{index}", price=50.0 + index) for index in range(8)]
    entries = {row["ticker"]: cache_entry(drift=1.001 + index / 2000) for index, row in enumerate(universe)}
    saved = {}
    monkeypatch.setattr(module, "universe_rows", lambda: universe)
    monkeypatch.setattr(module, "backtest_entry", lambda ticker, root=None: entries.get(ticker))
    monkeypatch.setattr(module, "latest_observations", lambda: {})
    monkeypatch.setattr(module, "_read_observation_rows", lambda: [])
    monkeypatch.setattr(module, "archive_series_for", lambda ticker: None)
    monkeypatch.setattr(module, "load_json", lambda name: None)
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update({name: payload}))
    recorded = {}
    monkeypatch.setattr(module.pre_breakout_pit_store, "append_snapshot",
                        lambda results, **kwargs: recorded.__setitem__("results", results))

    result = module.run()

    assert saved["screens/pre-breakout.json"] is result
    assert recorded["results"] == result["results"]
    assert result["status"] == "success"
    assert result["scored_count"] == 8
    assert [row["rank"] for row in result["results"]] == list(range(1, len(result["results"]) + 1))
    assert set(result["weights"]) == {"fundamental_inflection", "momentum_rs", "flow_sentiment"}
    assert set(result["evidence"]) == set(result["weights"])
    assert result["evidence"]["fundamental_inflection"]["citation"]
    assert set(result["leg_coverage"]) == set(pbs.PRE_BREAKOUT_WEIGHTS)
    assert "harness_freeze.json" in result["coverage_note"]
    for row in result["results"]:
        assert set(row["sub_scores"]) == {"fundamental_inflection", "momentum_rs", "flow_sentiment"}


def test_run_publishes_an_unavailable_file_rather_than_nothing(monkeypatch):
    saved = {}
    monkeypatch.setattr(module, "universe_rows", lambda: [universe_row("AAA")])
    monkeypatch.setattr(module, "backtest_entry", lambda ticker, root=None: None)
    monkeypatch.setattr(module, "latest_observations", lambda: {})
    monkeypatch.setattr(module, "_read_observation_rows", lambda: [])
    monkeypatch.setattr(module, "load_json", lambda name: None)
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update({name: payload}))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "INSUFFICIENT_PRICE_HISTORY"
    assert result["results"] == []


def test_publishable_returns_only_eligible_rows_ranked_by_score():
    scored = [
        {"ticker": "GOOD", "score": 2.0, "eligibility": True},
        {"ticker": "INELIGIBLE", "score": 3.0, "eligibility": False},
        {"ticker": "OK", "score": 1.0, "eligibility": True},
    ]

    published = [row["ticker"] for row in module.publishable(scored)]

    assert published == ["GOOD", "OK"]
