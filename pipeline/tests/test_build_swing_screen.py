from datetime import date, timedelta

import build_swing_screen as module
import swing_signals


def sessions_from(start, count):
    day, output = date.fromisoformat(start), []
    while len(output) < count:
        if day.weekday() < 5:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def cache_entry(count=400, drift=1.001, volume=5_000_000.0, price=100.0, volume_spike=1.0):
    """A price path with a steady per-session drift and a controllable final-week volume."""
    dates = sessions_from("2024-08-01", count)
    closes = [price * (drift ** index) for index in range(count)]
    volumes = [volume] * (count - 5) + [volume * volume_spike] * 5
    return {"dates": dates, "closes": closes, "volumes": volumes}


def universe_row(ticker="AAA", score=70.0, breadth=.3, magnitude=.02, short_pct=.02, days_to_cover=1.5):
    return {
        "ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology", "score": score,
        "is_etf": False, "price": 100.0, "market_cap": 5e9, "data_coverage": .9,
        "short_percent_of_float": short_pct, "days_to_cover": days_to_cover,
        "estimate_detail": {"revision_breadth_30d": breadth, "eps_revision_30d_pct": magnitude,
                            "net_upgrades_90d": 2, "target_change_30d_pct": .03},
    }


def entries_for(mapping):
    return lambda ticker, root=None: mapping.get(ticker)


# ---------------------------------------------------------------------------
# The signal legs themselves
# ---------------------------------------------------------------------------

def test_52_week_proximity_is_a_ratio_of_the_trailing_high_not_a_return():
    rising = [100 + index for index in range(300)]
    assert swing_signals.high_52w_proximity(rising) == 1.0
    faded = rising + [200.0, 150.0]
    assert swing_signals.high_52w_proximity(faded) < .8


def test_volume_surge_measures_a_stock_against_its_own_normal():
    quiet = [1_000_000.0] * 60
    assert swing_signals.volume_surge(quiet) == 1.0
    spiked = [1_000_000.0] * 60 + [4_000_000.0]
    assert swing_signals.volume_surge(spiked) == 4.0
    # Not enough reference history to say what normal is, so no factor rather than a guess.
    assert swing_signals.volume_surge([1_000_000.0] * 10) is None


def test_reversal_leg_is_signed_against_the_prior_week():
    rows = [
        {"ticker": "UP", "median_dollar_volume_60d": 1e9, "factors": {"return_5d": 12.0}},
        {"ticker": "FLAT", "median_dollar_volume_60d": 1e9, "factors": {"return_5d": 0.0}},
        {"ticker": "DOWN", "median_dollar_volume_60d": 1e9, "factors": {"return_5d": -12.0}},
    ]
    scored = {row["ticker"]: row for row in swing_signals.swing_scores(rows)}

    assert scored["DOWN"]["leg_scores"]["short_term_reversal"] > 0
    assert scored["UP"]["leg_scores"]["short_term_reversal"] < 0


def test_reversal_leg_is_cost_gated_out_of_illiquid_names():
    liquid = {"ticker": "LIQ", "median_dollar_volume_60d": 5e8, "factors": {"return_5d": -8.0}}
    thin = {"ticker": "THIN", "median_dollar_volume_60d": 1e5, "factors": {"return_5d": -8.0}}

    scored = {row["ticker"]: row for row in swing_signals.swing_scores([liquid, thin])}

    assert scored["LIQ"]["leg_scores"]["short_term_reversal"] is not None
    assert scored["THIN"]["leg_scores"]["short_term_reversal"] is None
    assert "REVERSAL_LEG_COST_GATED" in scored["THIN"]["reason_codes"]


def test_pead_leg_needs_an_open_drift_window():
    with_surprise = {"earnings_surprise": .08}
    assert swing_signals.pead_factor(with_surprise) == (.08, "WINDOW_UNKNOWN")

    fresh = {**with_surprise, "evidence": {"news_events": [
        {"event_types": ["earnings"], "age_trading_days": 3}]}}
    assert swing_signals.pead_factor(fresh) == (.08, "IN_DRIFT_WINDOW")

    stale = {**with_surprise, "evidence": {"news_events": [
        {"event_types": ["earnings"], "age_trading_days": 120}]}}
    assert swing_signals.pead_factor(stale) == (None, "DRIFT_WINDOW_CLOSED")

    assert swing_signals.pead_factor({}) == (None, "NO_SURPRISE_HISTORY")


def test_dropped_legs_renormalize_rather_than_scoring_zero():
    """A row missing the 30%-weighted PEAD leg is scored on the rest, not marked down for it."""
    complete = {"ticker": "FULL", "median_dollar_volume_60d": 1e9,
                "factors": {"earnings_surprise": .05, "return_5d": -5.0, "revision_breadth_30d": .6,
                            "high_52w_proximity": .95, "volume_ratio_1d_50d": 2.0}}
    partial = {"ticker": "PART", "median_dollar_volume_60d": 1e9,
               "factors": {"return_5d": -5.0, "revision_breadth_30d": .6,
                           "high_52w_proximity": .95, "volume_ratio_1d_50d": 2.0}}
    neutral = {"ticker": "MID", "median_dollar_volume_60d": 1e9,
               "factors": {"earnings_surprise": -.05, "return_5d": 5.0, "revision_breadth_30d": -.6,
                           "high_52w_proximity": .5, "volume_ratio_1d_50d": .5}}

    scored = {row["ticker"]: row for row in swing_signals.swing_scores([complete, partial, neutral])}

    assert scored["PART"]["dropped_legs"] == ["pead_drift"]
    assert scored["PART"]["coverage"] == .7
    assert scored["FULL"]["coverage"] == 1.0
    # Identical on every leg it could fill, so the missing leg costs coverage, not score.
    assert scored["PART"]["score"] > 0


def test_short_interest_suppresses_instead_of_scoring_a_short_leg():
    tradable = {"price": 50.0, "market_cap": 5e9, "history_sessions": 400,
                "median_dollar_volume_60d": 1e9}
    heavy = {**tradable, "ticker": "SHORTED",
             "short_percent_of_float": .18, "days_to_cover": 9.0,
             "factors": {"high_52w_proximity": .99, "return_5d": -6.0, "revision_breadth_30d": .5}}
    clean = {**tradable, "ticker": "CLEAN",
             "short_percent_of_float": .01, "days_to_cover": 1.0,
             "factors": {"high_52w_proximity": .98, "return_5d": -5.0, "revision_breadth_30d": .4}}

    scored = {row["ticker"]: row for row in swing_signals.swing_scores([heavy, clean])}

    assert scored["SHORTED"]["short_interest"]["suppressed"] is True
    assert "SHORT_INTEREST_SUPPRESSED" in scored["SHORTED"]["reason_codes"]
    assert scored["SHORTED"]["eligibility"] is False
    # Suppression removes eligibility; it never contributes a factor to the composite.
    assert "short_interest" not in scored["SHORTED"]["leg_scores"]
    assert scored["CLEAN"]["eligibility"] is True


def test_membership_uses_hysteresis_so_the_list_does_not_flicker():
    rows = [{"ticker": f"T{index}", "median_dollar_volume_60d": 1e9,
             "price": 50, "market_cap": 5e9, "history_sessions": 400,
             "factors": {"high_52w_proximity": .5 + index / 100, "return_5d": -index,
                         "revision_breadth_30d": index / 20}}
            for index in range(20)]

    fresh = {row["ticker"]: row for row in swing_signals.swing_scores(rows)}
    held = {row["ticker"]: row for row in swing_signals.swing_scores(
        rows, current_members={row["ticker"]: True for row in rows})}

    mid = next(ticker for ticker, row in fresh.items()
               if row["percentile"] is not None and 75 <= row["percentile"] < 90)
    assert fresh[mid]["current_membership"] is False   # not high enough to enter
    assert held[mid]["current_membership"] is True     # but high enough to stay


# ---------------------------------------------------------------------------
# The builder
# ---------------------------------------------------------------------------

def test_build_rows_reads_cached_series_and_skips_funds():
    universe = [universe_row("AAA"), {**universe_row("FUND"), "is_etf": True}, universe_row("NOHIST")]
    entries = entries_for({"AAA": cache_entry(), "FUND": cache_entry()})

    rows = module.build_rows(universe, entry_for=entries, observations={})

    assert [row["ticker"] for row in rows] == ["AAA"]
    assert rows[0]["history_sessions"] == 400
    assert rows[0]["factors"]["high_52w_proximity"] is not None
    assert rows[0]["median_dollar_volume_60d"] > 0


def test_run_publishes_ranked_rows_with_their_evidence(monkeypatch, tmp_path):
    universe = [universe_row(f"T{index}", breadth=index / 10, magnitude=index / 100)
                for index in range(8)]
    entries = {row["ticker"]: cache_entry(volume_spike=1 + row_index / 4)
               for row_index, row in enumerate(universe)}
    saved = {}
    monkeypatch.setattr(module, "universe_rows", lambda: universe)
    monkeypatch.setattr(module, "backtest_entry", lambda ticker, root=None: entries.get(ticker))
    monkeypatch.setattr(module, "latest_observations", lambda: {})
    monkeypatch.setattr(module, "load_json", lambda name: None)
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update({name: payload}))

    result = module.run()

    assert saved["screens/swing.json"] is result
    assert result["status"] == "success"
    assert result["scored_count"] == 8
    assert [row["rank"] for row in result["results"]] == list(range(1, len(result["results"]) + 1))
    # The file has to carry why each leg is there, not just the number it produced.
    assert set(result["weights"]) == set(result["evidence"])
    assert result["evidence"]["pead_drift"]["citation"].startswith("Bernard & Thomas")
    assert result["decay_haircut"]["post_publication"] == .58
    assert set(result["leg_coverage"]) == set(swing_signals.SWING_WEIGHTS)
    assert result["negative_screen"]["direction"].startswith("negative")


def test_run_publishes_an_unavailable_file_rather_than_nothing(monkeypatch):
    saved = {}
    monkeypatch.setattr(module, "universe_rows", lambda: [universe_row("AAA")])
    monkeypatch.setattr(module, "backtest_entry", lambda ticker, root=None: None)
    monkeypatch.setattr(module, "latest_observations", lambda: {})
    monkeypatch.setattr(module, "load_json", lambda name: None)
    monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update({name: payload}))

    result = module.run()

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "INSUFFICIENT_PRICE_HISTORY"
    assert result["results"] == []


def test_publishable_keeps_suppressed_names_visible_in_the_head():
    scored = [
        {"ticker": "GOOD", "score": 2.0, "eligibility": True, "short_interest": {"suppressed": False}},
        {"ticker": "SHORTED", "score": 1.5, "eligibility": False, "short_interest": {"suppressed": True}},
        {"ticker": "THIN", "score": 1.9, "eligibility": False, "short_interest": {"suppressed": False}},
    ]

    published = [row["ticker"] for row in module.publishable(scored)]

    assert published == ["GOOD", "SHORTED"]


def test_weights_are_declared_once_and_sum_to_one():
    assert round(sum(swing_signals.SWING_WEIGHTS.values()), 6) == 1.0
    assert set(swing_signals.SWING_SUBFACTORS) == set(swing_signals.SWING_WEIGHTS)
    # The reversal leg is the only contrarian one, and nothing else may quietly become so.
    negated = {leg for leg, subfactors in swing_signals.SWING_SUBFACTORS.items()
               if any(negate for _, negate in subfactors)}
    assert negated == {"short_term_reversal"}


def test_no_raw_trailing_return_appears_in_two_legs():
    """The sign flip guard: one return window, one leg, or the composite cancels itself."""
    used = [name for subfactors in swing_signals.SWING_SUBFACTORS.values() for name, _ in subfactors]
    assert len(used) == len(set(used))
    assert [name for name in used if name.startswith("return_")] == ["return_5d"]
