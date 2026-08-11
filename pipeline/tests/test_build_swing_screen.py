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


def test_52_week_leg_is_scored_in_the_names_own_volatility():
    """Rule 4: two names equally far below their high must not rank on volatility alone."""
    quiet = swing_signals.high_52w_drawdown_sigmas([100.0] * 100 + [90.0], volatility=.20)
    loud = swing_signals.high_52w_drawdown_sigmas([100.0] * 100 + [90.0], volatility=.60)

    # Same 10% drawdown, but it is a far bigger move for the quiet name and the leg says so.
    assert quiet < loud < 0
    # Without a volatility reading there is no scale, so no factor rather than a raw ratio.
    assert swing_signals.high_52w_drawdown_sigmas([100.0] * 100, volatility=None) is None
    assert swing_signals.high_52w_drawdown_sigmas([100.0] * 100, volatility=0) is None


def test_pead_leg_needs_an_open_drift_window():
    surprised = {"sue": 1.8, "basis": "net_income", "filed": "2026-05-01"}
    assert swing_signals.pead_factor(surprised) == (1.8, "WINDOW_UNKNOWN")

    fresh = {**surprised, "age_trading_days": 3}
    assert swing_signals.pead_factor(fresh) == (1.8, "IN_DRIFT_WINDOW")

    stale = {**surprised, "age_trading_days": 120}
    assert swing_signals.pead_factor(stale) == (None, "DRIFT_WINDOW_CLOSED")

    assert swing_signals.pead_factor(None) == (None, "NO_SUE_HISTORY")
    assert swing_signals.pead_factor({}) == (None, "NO_SUE_HISTORY")


def test_a_missing_leg_scores_neutral_rather_than_rescaling_the_others():
    """Rule 5: less evidence must move a row toward neutral, never onto a wider scale.

    Renormalizing to the resolved weight gave partial rows more dispersion than complete
    ones, so they crowded both tails - and the top tail is the one that gets traded.
    """
    def row(ticker, sue=None):
        factors = {"return_5d": -5.0, "revision_breadth_30d": .6,
                   "high_52w_drawdown_sigmas": -.2, "volume_ratio_1d_50d": 2.0}
        if sue is not None:
            factors["standardized_unexpected_earnings"] = sue
        return {"ticker": ticker, "median_dollar_volume_60d": 1e9, "factors": factors}

    opposite = {"ticker": "MID", "median_dollar_volume_60d": 1e9,
                "factors": {"standardized_unexpected_earnings": -2.0, "return_5d": 5.0,
                            "revision_breadth_30d": -.6, "high_52w_drawdown_sigmas": -2.0,
                            "volume_ratio_1d_50d": .5}}
    scored = {r["ticker"]: r for r in
              swing_signals.swing_scores([row("FULL", sue=2.0), row("PART"), opposite])}

    assert scored["PART"]["dropped_legs"] == ["pead_drift"]
    assert scored["PART"]["coverage"] == .7
    assert scored["FULL"]["coverage"] == 1.0
    # Identical on every leg it could fill, so the missing leg pulls PART toward zero.
    assert 0 < scored["PART"]["score"] < scored["FULL"]["score"]
    # The pre-rule-5 divisor is still published, and is the wider number it always was.
    assert scored["PART"]["score_renormalized"] > scored["PART"]["score"]


def test_heavy_tailed_sue_is_ranked_rather_than_clipped():
    """One firm with a loud quarter must not tie the whole top of a 30%-weight leg."""
    rows = [{"ticker": f"T{index}", "median_dollar_volume_60d": 1e9,
             "factors": {"standardized_unexpected_earnings": value}}
            for index, value in enumerate([-1.0, 0.0, .5, 1.0, 1.5, 2.0, 40.0, 60.0])]

    scored = swing_signals.swing_scores(rows)
    legs = [row["leg_scores"]["pead_drift"] for row in scored]

    assert len(set(legs)) == len(legs)            # no two names share a clip value
    assert legs == sorted(legs, reverse=True)     # and the order still tracks the surprise


def test_short_interest_needs_the_level_and_never_days_to_cover_alone():
    """Rule 3: Boehmer-Jones-Zhang is a top-decile *level* result.

    Days to cover is short interest over average volume, so an absolute threshold on it
    selects low-turnover names. It corroborates and can no longer suppress by itself.
    """
    tradable = {"price": 50.0, "market_cap": 5e9, "history_sessions": 400,
                "median_dollar_volume_60d": 1e9}
    factors = {"high_52w_drawdown_sigmas": -.1, "return_5d": -6.0, "revision_breadth_30d": .5}
    heavy = {**tradable, "ticker": "SHORTED", "short_percent_of_float": .18,
             "days_to_cover": 9.0, "factors": factors}
    # Lightly shorted but slow to trade: the old OR suppressed this, the level rule does not.
    slow = {**tradable, "ticker": "SLOW", "short_percent_of_float": .04,
            "days_to_cover": 7.5, "factors": factors}
    clean = {**tradable, "ticker": "CLEAN", "short_percent_of_float": .01,
             "days_to_cover": 1.0, "factors": factors}

    scored = {row["ticker"]: row for row in swing_signals.swing_scores([heavy, slow, clean])}

    assert scored["SHORTED"]["short_interest"]["suppressed"] is True
    assert "SHORT_INTEREST_SUPPRESSED" in scored["SHORTED"]["reason_codes"]
    assert scored["SHORTED"]["eligibility"] is False
    # Suppression removes eligibility; it never contributes a factor to the composite.
    assert "short_interest" not in scored["SHORTED"]["leg_scores"]

    assert scored["SLOW"]["short_interest"]["suppressed"] is False
    assert scored["SLOW"]["short_interest"]["corroborating_only"]   # recorded, not acted on
    assert scored["SLOW"]["eligibility"] is True
    assert scored["CLEAN"]["eligibility"] is True


def test_short_interest_level_must_also_clear_the_cross_sections_top_decile():
    """An absolute floor alone would suppress on a universe where everything is shorted."""
    tradable = {"price": 50.0, "market_cap": 5e9, "history_sessions": 400,
                "median_dollar_volume_60d": 1e9,
                "factors": {"high_52w_drawdown_sigmas": -.1, "revision_breadth_30d": .5}}
    rows = [{**tradable, "ticker": f"T{index}", "short_percent_of_float": .11 + index / 1000}
            for index in range(20)]

    scored = {row["ticker"]: row for row in swing_signals.swing_scores(rows)}

    # Every name clears the 10% floor, so only the top decile of the level is suppressed.
    suppressed = [t for t, row in scored.items() if row["short_interest"]["suppressed"]]
    assert 0 < len(suppressed) <= 4
    assert "T19" in suppressed and "T0" not in suppressed


def test_capacity_profile_reports_round_trip_cost_and_where_the_book_stops_fitting():
    rows = [{"ticker": f"T{index}", "price": 50.0, "market_cap": 5e9, "history_sessions": 400,
             "median_dollar_volume_60d": 3e7,
             "factors": {"high_52w_drawdown_sigmas": -index / 100, "revision_breadth_30d": index / 20,
                         "realized_volatility_60d": .35}}
            for index in range(20)]

    profile = swing_signals.capacity_profile(swing_signals.swing_scores(rows))

    assert profile["book_size"] > 0
    sizes = profile["by_portfolio_size"]
    costs = [entry["median_round_trip_bps"] for entry in sizes.values()]
    assert costs == sorted(costs)          # impact grows with size, never shrinks
    assert profile["median_position_capacity_at_2pct_adv"] == 600_000.0
    assert profile["spread_source"] == "liquidity_tiered_proxy_not_measured"


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
