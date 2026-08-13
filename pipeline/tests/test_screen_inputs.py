import json

import screen_inputs as module


def test_universe_rows_merge_the_detailed_row_into_the_summary_one():
    advisor = {
        "screen_universe": [{"ticker": "AAA", "sector": "Technology", "score": 70.0}],
        "research": [{"ticker": "AAA", "sector": "Tech", "industry": "Software - Application",
                      "market_cap": 5_000_000_000, "score": 1.0}],
        "portfolio_coverage": [{"ticker": "BBB", "industry": "Banks - Regional",
                                "market_cap": 1_000_000_000}],
    }

    rows = {row["ticker"]: row for row in module.universe_rows(advisor)}

    # The published summary keeps precedence for anything it carries...
    assert rows["AAA"]["score"] == 70.0
    assert rows["AAA"]["sector"] == "Technology"
    # ...and the detailed row supplies what only it has.
    assert rows["AAA"]["industry"] == "Software - Application"
    assert rows["AAA"]["market_cap"] == 5_000_000_000
    assert rows["BBB"]["industry"] == "Banks - Regional"


def test_universe_rows_tolerate_an_empty_snapshot():
    assert module.universe_rows({}) == []


def test_latest_observations_keep_the_newest_reading_per_ticker(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in [
        {"ticker": "AAA", "observed_at": "2026-08-01T00:00:00+00:00", "values": {"altman_z": 1.0}},
        {"ticker": "AAA", "observed_at": "2026-08-08T00:00:00+00:00", "values": {"altman_z": 4.0}},
        {"ticker": "BBB", "observed_at": "2026-08-02T00:00:00+00:00", "values": {"altman_z": 2.0}},
        "not json",
    ]))

    observations = module.latest_observations(str(path))

    assert observations["AAA"] == {"altman_z": 4.0}
    assert observations["BBB"] == {"altman_z": 2.0}


def test_latest_observations_return_nothing_when_the_store_is_absent(tmp_path):
    assert module.latest_observations(str(tmp_path / "missing.jsonl")) == {}


def test_backtest_entry_is_none_for_an_unknown_ticker(tmp_path):
    assert module.backtest_entry("NOPE", root=str(tmp_path)) is None


def test_backtest_entry_survives_a_corrupt_cache_file(tmp_path):
    (tmp_path / "AAA.json").write_text("{ not json")

    assert module.backtest_entry("AAA", root=str(tmp_path)) is None


def test_median_dollar_volume_uses_the_trailing_window_only():
    closes = [1.0] * 100
    volumes = [1.0] * 40 + [100.0] * 60

    assert module.median_dollar_volume(closes, volumes) == 100.0


def test_median_dollar_volume_needs_matching_series():
    assert module.median_dollar_volume([1.0, 2.0], [1.0]) is None
    assert module.median_dollar_volume([], []) is None


def test_percentiles_span_the_full_scale_and_leave_gaps_where_data_is_missing():
    assert module.cross_sectional_percentiles([1, 2, 3, None]) == [0.0, 50.0, 100.0, None]


def test_tied_values_share_a_rank_instead_of_splitting_the_scale():
    assert module.cross_sectional_percentiles([5, 5, 9]) == [25.0, 25.0, 100.0]


def test_a_single_observation_is_neutral_rather_than_top_of_the_market():
    assert module.cross_sectional_percentiles([None, 7, None]) == [None, 50.0, None]


def test_percentiles_of_nothing_are_nothing():
    assert module.cross_sectional_percentiles([None, None]) == [None, None]
    assert module.cross_sectional_percentiles([]) == []


def entry():
    return {"dates": ["2026-08-05", "2026-08-06"], "closes": [10.0, 11.0],
            "raw_closes": [10.0, 11.0], "volumes": [100.0, 200.0]}


def test_current_price_extends_a_stale_cache():
    updated = module.with_current_price(entry(), 12.0, "2026-08-09T08:00:00+00:00")

    assert updated["dates"][-1] == "2026-08-09"
    assert updated["closes"][-1] == 12.0
    assert updated["raw_closes"][-1] == 12.0
    # No volume was published with the price, so none is invented.
    assert updated["volumes"][-1] is None


def test_current_price_is_ignored_when_the_cache_already_covers_it():
    assert module.with_current_price(entry(), 12.0, "2026-08-06T08:00:00+00:00") == entry()
    assert module.with_current_price(entry(), None, "2026-08-09T08:00:00+00:00") == entry()
    assert module.with_current_price({}, 12.0, "2026-08-09T08:00:00+00:00") == {}


def test_median_dollar_volume_skips_sessions_with_no_reported_volume():
    assert module.median_dollar_volume([1.0, 1.0, 1.0], [4.0, 6.0, None]) == 5.0
