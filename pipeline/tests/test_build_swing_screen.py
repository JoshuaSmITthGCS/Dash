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


# ---------------------------------------------------------------------------
# Volatility-contraction / mean-reversion context (descriptive, never a leg)
# ---------------------------------------------------------------------------

def test_bandwidth_squeeze_flags_a_name_at_its_own_low_volatility_percentile():
    # A quiet, tightly-ranging series has to actually compress relative to its own trailing
    # 6-month distribution before it reads as squeezed - not merely low-volatility throughout.
    wide = [100 + 20 * ((index % 40) / 40 - .5) for index in range(200)]
    tight = [100 + .2 * ((index % 5) / 5 - .5) for index in range(20)]
    series = wide + tight

    squeeze = swing_signals.bandwidth_squeeze(series)

    assert squeeze is not None
    assert squeeze["squeezed"] is True
    assert squeeze["percentile_of_own_history"] <= swing_signals.BANDWIDTH_SQUEEZE_PERCENTILE


def test_bandwidth_squeeze_is_none_on_thin_history():
    assert swing_signals.bandwidth_squeeze([100.0] * 50) is None


def test_volume_dry_up_flags_volume_meaningfully_below_its_own_average():
    normal = [1_000_000.0] * 50
    thinned = [1_000_000.0] * 40 + [600_000.0] * 10

    assert swing_signals.volume_dry_up(normal)["dried_up"] is False
    dried = swing_signals.volume_dry_up(thinned)
    assert dried["dried_up"] is True
    assert dried["ratio_to_50d_average"] < swing_signals.VOLUME_DRY_UP_THRESHOLD


def test_rsi_2_reads_overbought_on_a_persistent_rally_and_oversold_on_a_selloff():
    rally = [100 * 1.01 ** index for index in range(10)]
    selloff = [100 * .99 ** index for index in range(10)]

    assert swing_signals.rsi_2(rally) > 70
    assert swing_signals.rsi_2(selloff) < 30


def test_true_range_captures_a_gap_the_plain_high_low_range_misses():
    # A session that gapped up 20 points overnight and then barely moved: the plain high-low
    # range for that session is only 1, but the true range has to include the gap from the
    # prior close, which is the entire reason Wilder defined it this way.
    highs = [100.0, 121.0]
    lows = [99.0, 120.0]
    closes = [99.5, 120.5]

    ranges = swing_signals.true_range_series(highs, lows, closes)

    assert ranges == [max(1.0, abs(121.0 - 99.5), abs(120.0 - 99.5))]


def test_true_range_is_none_on_a_session_missing_a_high_or_low():
    highs = [100.0, None, 105.0]
    lows = [99.0, 98.0, 104.0]
    closes = [99.5, 99.0, 104.5]

    ranges = swing_signals.true_range_series(highs, lows, closes)

    # Index 0 has no predecessor (dropped by construction). Index 1's high is missing, so it's
    # None. Index 2's plain range is 105-104=1, but the gap from index 1's close (99.0) to
    # index 2's high (105.0) is 6, which true range has to capture.
    assert ranges == [None, 6.0]


def test_average_true_range_needs_a_fully_resolvable_window():
    # A one-point-a-session uptrend: the plain high-low range is 1 every session, but the
    # steady drift means the previous close always sits 0.5 inside the day's low, so the true
    # range (which has to consider that gap) is 1.5 every session, not 1.
    highs = [100.0 + index for index in range(20)]
    lows = [99.0 + index for index in range(20)]
    closes = [99.5 + index for index in range(20)]

    assert swing_signals.average_true_range(highs, lows, closes, window=14) == 1.5
    assert swing_signals.average_true_range(highs[:10], lows[:10], closes[:10], window=14) is None


def test_narrow_range_flags_todays_range_as_the_tightest_of_the_window():
    highs = [110.0, 108.0, 107.0, 106.0, 105.5, 105.0, 104.5]
    lows = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 104.0]

    nr7 = swing_signals.narrow_range(highs, lows, window=7)

    assert nr7["is_nr7"] is True
    assert nr7["range"] == .5


def test_narrow_range_does_not_flag_a_session_that_is_not_the_tightest():
    highs = [110.0, 100.5, 100.0, 100.0, 100.0, 100.0, 100.0]
    lows = [100.0, 100.0, 90.0, 90.0, 90.0, 90.0, 90.0]

    nr7 = swing_signals.narrow_range(highs, lows, window=7)

    assert nr7["is_nr7"] is False


def test_narrow_range_is_none_on_thin_history():
    assert swing_signals.narrow_range([100.0] * 5, [99.0] * 5, window=7) is None


def test_atr_compression_flags_a_range_at_its_own_trailing_low():
    # Wide true range for the first 200 sessions, tight for the last 20 - the ATR-percentile
    # analogue of the bandwidth_squeeze test above.
    wide_highs = [100 + 10 * ((index % 20) / 20) for index in range(200)]
    wide_lows = [90 - 10 * ((index % 20) / 20) for index in range(200)]
    tight_highs = [100.1] * 20
    tight_lows = [99.9] * 20
    highs = wide_highs + tight_highs
    lows = wide_lows + tight_lows
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]

    compression = swing_signals.atr_compression(highs, lows, closes)

    assert compression is not None
    assert compression["squeezed"] is True


def test_atr_compression_is_none_on_thin_history():
    assert swing_signals.atr_compression([100.0] * 30, [99.0] * 30, [99.5] * 30) is None


def test_contraction_setup_reads_narrow_range_and_atr_from_the_archive_series_only():
    # The archive series is independent of the long backtest-cache series: passing a short
    # archive alongside a long cache series must not let one substitute for the other.
    long_closes = [100.0 + index for index in range(400)]
    long_volumes = [1_000_000.0] * 400
    archive_highs = [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 100.5]
    archive_lows = [99.0, 99.5, 100.0, 100.5, 101.0, 101.5, 100.0]
    archive_closes = [100.0, 100.5, 101.5, 102.0, 103.0, 104.0, 100.2]

    setup = swing_signals.contraction_setup(long_closes, long_volumes, archive_highs,
                                            archive_lows, archive_closes)

    assert setup["narrow_range"] is not None
    assert setup["narrow_range"]["is_nr7"] is True
    # Too little archive history for a real ATR-percentile distribution yet.
    assert setup["atr_compression"] is None


def test_contraction_setup_is_never_a_declared_leg():
    """These are published beside the five scored legs, never as a sixth one."""
    assert "contraction" not in swing_signals.SWING_WEIGHTS
    assert "contraction" not in swing_signals.SWING_SUBFACTORS
    for subfactors in swing_signals.SWING_SUBFACTORS.values():
        for name, _ in subfactors:
            assert name not in ("bandwidth_squeeze", "volume_dry_up", "rsi_2",
                                "narrow_range", "atr_compression")


def test_contraction_setup_reports_none_components_on_insufficient_history():
    # Ten flat closes are enough for RSI(2) (neutral 50, not a fabricated read) but not for the
    # squeeze, vcp (both need ~6 months) or the volume dry-up (needs a 50-session reference
    # average). No archive series is passed at all, so the two range-based reads are also None.
    setup = swing_signals.contraction_setup([100.0] * 10, [1_000_000.0] * 10)
    assert setup == {"bandwidth_squeeze": None, "volume_dry_up": None, "rsi_2": 50.0,
                     "narrow_range": None, "atr_compression": None, "vcp": None}


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
    surprised = {"sue": 1.8, "basis": "net_income", "filed": "2026-05-15",
                 "release_datetime": "2026-05-01T16:05:00-05:00"}

    fresh = {**surprised, "age_trading_days": 3}
    assert swing_signals.pead_factor(fresh) == (1.8, "IN_DRIFT_WINDOW")

    stale = {**surprised, "age_trading_days": 120}
    assert swing_signals.pead_factor(stale) == (None, "DRIFT_WINDOW_CLOSED")

    # An anchored surprise whose age could not be counted is not scored on an unknown window.
    assert swing_signals.pead_factor(surprised) == (None, "WINDOW_UNKNOWN")

    assert swing_signals.pead_factor(None) == (None, "NO_SUE_HISTORY")
    assert swing_signals.pead_factor({}) == (None, "NO_SUE_HISTORY")


def test_pead_leg_refuses_to_fall_back_to_the_filing_date():
    """Spec amendment SA-2026-08-12-02: the filing date is provenance, never an anchor.

    A 10-Q lands days after the press release that carried the number, so anchoring on it
    reports every drift window as younger than it is, and always in the same direction. At a
    2-to-10-session hold that error is a large fraction of the window, so a row with no
    release datetime scores nothing here rather than scoring on a date known to be wrong.
    """
    unanchored = {"sue": 2.4, "basis": "net_income", "filed": "2026-05-15",
                  "release_datetime": None, "age_trading_days": 2}

    assert swing_signals.pead_factor(unanchored) == (None, "RELEASE_DATE_UNRESOLVED")


def test_pead_anchor_diagnostic_quotes_the_coverage_the_re_anchoring_cost():
    scored = [{"factors": {"pead_status": status}} for status in
              ["IN_DRIFT_WINDOW"] * 4 + ["RELEASE_DATE_UNRESOLVED"] * 5 + ["NO_SUE_HISTORY"]]

    diagnostic = swing_signals.pead_anchor_diagnostic(scored)

    assert diagnostic["rows_without_a_release_datetime"] == 5
    assert diagnostic["pead_coverage_now"] == .4
    assert diagnostic["coverage_dropped_below_reference"] is True
    # The delta is surfaced explicitly rather than left to be inferred from a smaller number.
    assert diagnostic["coverage_delta"] == round(.4 - .85, 4)


def test_a_missing_leg_is_renormalized_away_rather_than_zero_filled():
    """Rule 5 as amended (SA-2026-08-12-04).

    Zero-filling a missing leg pulled every thin row toward the cross-sectional mean, and
    thinness tracks size and liquidity, so the old rule ran an undeclared tilt that muted the
    high-idiosyncratic-volatility names where McLean & Pontiff (Journal of Finance 2016)
    measure decay to be worst. A leg that resolves now carries the influence its declared
    weight promises regardless of what else is missing.
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
    assert scored["PART"]["legs_resolved"] == 4
    assert scored["FULL"]["coverage"] == 1.0
    assert scored["FULL"]["legs_resolved"] == 5
    # PART and FULL agree on every leg PART could fill, so PART is no longer dragged toward
    # neutral by the leg it could not fill.
    assert scored["PART"]["score"] > 0
    assert scored["PART"]["score"] > scored["PART"]["score_zero_filled"]
    # The four legs PART resolved now sum to the full weight between them.
    assert round(sum(scored["PART"]["leg_contributions"].values()), 6) == \
        round(scored["PART"]["score"], 6)
    assert round(scored["PART"]["renormalization_factor"], 4) == round(1 / .7, 4)


def test_a_row_too_thin_to_renormalize_is_excluded_from_the_ranking():
    """The floor that makes renormalization safe: three of five legs, or no rank at all.

    Renormalizing a two-leg row puts it on the same centre as a five-leg row but not on the
    same dispersion, and it is the top tail that gets traded. The old rule handled that by
    muting thin rows; this one handles it by removing them and saying so.
    """
    tradable = {"price": 50.0, "market_cap": 5e9, "history_sessions": 400,
                "median_dollar_volume_60d": 1e9}
    thin = {**tradable, "ticker": "THIN",
            "factors": {"return_5d": -4.0, "revision_breadth_30d": .5}}
    thick = {**tradable, "ticker": "THICK",
             "factors": {"return_5d": -4.0, "revision_breadth_30d": .5,
                         "volume_ratio_1d_50d": 2.0, "high_52w_drawdown_sigmas": -.2}}

    scored = {row["ticker"]: row for row in swing_signals.swing_scores([thin, thick])}

    assert scored["THIN"]["legs_resolved"] == 2
    assert "INSUFFICIENT_LEGS_RESOLVED" in scored["THIN"]["reason_codes"]
    assert scored["THIN"]["eligibility"] is False
    assert scored["THIN"]["percentile"] is None
    assert scored["THICK"]["legs_resolved"] == 4
    assert scored["THICK"]["eligibility"] is True

    distribution = swing_signals.legs_resolved_distribution([thin_row for thin_row in scored.values()])
    assert distribution["rows_excluded_below_floor"] == 1
    assert distribution["minimum_legs_resolved"] == 3


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


def costed_rows(count=20, sectors=None):
    sectors = sectors or ["Technology"] * count
    return [{"ticker": f"T{index}", "price": 50.0, "market_cap": 5e9, "history_sessions": 400,
             "median_dollar_volume_60d": 3e7, "adv_20d_dollar_volume": 3e7,
             "sector": sectors[index],
             "factors": {"high_52w_drawdown_sigmas": -index / 100,
                         "revision_breadth_30d": index / 20,
                         "volume_ratio_1d_50d": 1 + index / 20,
                         "realized_volatility_60d": .35}}
            for index in range(count)]


def test_capacity_profile_reports_round_trip_cost_and_where_the_book_stops_fitting():
    profile = swing_signals.capacity_profile(swing_signals.swing_scores(costed_rows()))

    assert profile["book_size"] > 0
    sizes = profile["by_book_dollar_value"]
    costs = [entry["median_position_round_trip_bps"] for entry in sizes.values()]
    assert costs == sorted(costs)          # impact grows with size, never shrinks
    # Book size and position size are separate numbers and both are labelled as such.
    for entry in sizes.values():
        assert entry["position_dollar_value"] == round(
            entry["book_dollar_value"] / entry["positions_held"], 2)
    assert profile["median_position_capacity_at_participation_cap"] == 1_500_000.0
    assert profile["spread_source"] == "liquidity_tiered_proxy_not_measured"
    assert "not a measured quoted spread" in profile["spread_caveat"]


def test_every_quoted_cost_point_sits_on_one_square_root_curve():
    """Spec amendment SA-2026-08-12-06: one heading, one cost model.

    Quoting a set of round-trip figures that do not satisfy the square-root law means the
    capacity conclusion depends on which point a reader happens to take.
    """
    profile = swing_signals.capacity_profile(swing_signals.swing_scores(costed_rows()))

    consistency = profile["curve_consistency"]
    assert consistency["status"] == "consistent"
    assert consistency["max_relative_deviation"] <= consistency["tolerance"]


def test_a_position_breaching_the_participation_cap_is_not_scored_tradable():
    row = {"ticker": "TIGHT", "median_dollar_volume_60d": 1e7, "adv_20d_dollar_volume": 1e7,
           "factors": {"realized_volatility_60d": .35}}

    inside = swing_signals.cost_profile(row, 400_000)     # 4% of ADV, under the 5% default
    outside = swing_signals.cost_profile(row, 900_000)    # 9% of ADV, over it

    assert inside["tradable"] is True
    assert inside["participation"]["status"] == "within_cap"
    assert outside["tradable"] is False
    assert outside["participation"]["breaches_cap"] is True
    assert outside["participation"]["max_position_dollar_value"] == 500_000.0
    assert outside["participation"]["adv_source"] == "trailing_20d_mean_dollar_volume"


def test_membership_uses_hysteresis_so_the_list_does_not_flicker():
    rows = [{"ticker": f"T{index}", "median_dollar_volume_60d": 1e9,
             "price": 50, "market_cap": 5e9, "history_sessions": 400,
             "factors": {"high_52w_drawdown_sigmas": -1 + index / 100, "return_5d": -index,
                         "volume_ratio_1d_50d": 1 + index / 20,
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
# The analyst revision leg's sign (spec amendment SA-2026-08-12-01)
# ---------------------------------------------------------------------------

def revision_row(ticker, *, breadth, magnitude, upgrades, target_change):
    """One row carrying only revision inputs, plus enough other legs to stay rankable."""
    return {"ticker": ticker, "median_dollar_volume_60d": 1e9, "sector": "Technology",
            "price": 50.0, "market_cap": 5e9, "history_sessions": 400,
            "factors": {"revision_breadth_30d": breadth, "eps_revision_30d_pct": magnitude,
                        "net_upgrades_90d": upgrades, "target_change_30d_pct": target_change,
                        "volume_ratio_1d_50d": 1.0, "high_52w_drawdown_sigmas": -.5}}


def test_rising_consensus_scores_positive_on_the_revision_leg():
    """Three consecutive quarters of rising consensus EPS must map to a positive leg score.

    The whole chain is under test here, not one function: the raw consensus input, the
    differencing that turns a level into a change, the standardization, the sign convention in
    SWING_SUBFACTORS, and the direction of the cross-sectional rank. An inversion anywhere in
    it inverts the leg, and an inverted 25%-weight leg is a screen that systematically buys
    the names analysts are cutting.
    """
    # A firm whose consensus EPS ran 4.80 -> 5.10 -> 5.45 -> 5.72 over four quarters: breadth
    # of revisions net upward, magnitude positive, more upgrades than downgrades, target up.
    # Sat in a cross-section wide enough that winsorization has room to work, since a
    # three-name universe clips its own extremes onto the middle name and would hide a tie.
    rising = revision_row("RISING", breadth=.75, magnitude=.062, upgrades=6, target_change=8.4)
    flat = revision_row("FLAT", breadth=0.0, magnitude=0.0, upgrades=0, target_change=0.0)
    falling = revision_row("FALLING", breadth=-.75, magnitude=-.062, upgrades=-6,
                           target_change=-8.4)
    filler = [revision_row(f"F{index}", breadth=(index - 9) / 30, magnitude=(index - 9) / 500,
                           upgrades=index - 9, target_change=(index - 9) / 3)
              for index in range(19)]

    scored = {row["ticker"]: row
              for row in swing_signals.swing_scores([rising, flat, falling] + filler)}

    assert scored["RISING"]["leg_scores"]["analyst_revision"] > 0
    assert scored["FALLING"]["leg_scores"]["analyst_revision"] < 0
    assert (scored["RISING"]["leg_scores"]["analyst_revision"]
            > scored["FLAT"]["leg_scores"]["analyst_revision"]
            > scored["FALLING"]["leg_scores"]["analyst_revision"])
    # And the sign survives into the composite rank, which is the thing actually traded.
    assert scored["RISING"]["score"] > scored["FALLING"]["score"]


def test_falling_consensus_scores_negative_on_every_revision_subfactor_alone():
    """The mirror case, one subfactor at a time, so a single inverted input cannot hide.

    Averaging four subfactors into one leg means three correct signs can mask a fourth that
    is backwards. Each is therefore driven on its own.
    """
    subfactors = ("revision_breadth_30d", "eps_revision_30d_pct", "net_upgrades_90d",
                  "target_change_30d_pct")
    for name in subfactors:
        rows = [{"ticker": f"T{index}", "median_dollar_volume_60d": 1e9,
                 "factors": {name: (index - 10) / 10, "volume_ratio_1d_50d": 1.0,
                             "high_52w_drawdown_sigmas": -.5}}
                for index in range(21)]

        scored = {row["ticker"]: row for row in swing_signals.swing_scores(rows)}

        assert scored["T20"]["leg_scores"]["analyst_revision"] > 0, name
        assert abs(scored["T10"]["leg_scores"]["analyst_revision"]) < 1e-9, name
        assert scored["T0"]["leg_scores"]["analyst_revision"] < 0, name


def test_the_revision_leg_declares_its_long_only_asymmetry_as_a_warning():
    """Womack (Journal of Finance 1996) measures the effect concentrated on the sell side.

    New sells drift -9.1% over six months against new buys at +2.4%. A long-only book cannot
    harvest the larger half, so this leg's 0.25 weight must never be read as a claim on the
    full published spread. The disclosure is machine-readable metadata rather than prose so a
    downstream artifact cannot quote the weight without it.
    """
    evidence = swing_signals.SWING_EVIDENCE["analyst_revision"]
    warnings = {warning["code"]: warning for warning in evidence["warnings"]}

    assert "LONG_ONLY_ASYMMETRY" in warnings
    warning = warnings["LONG_ONLY_ASYMMETRY"]
    assert warning["capturable_side_effect_pct"] == 2.4
    assert warning["unreachable_side_effect_pct"] == -9.1
    assert "Womack" in warning["citation"] and "1996" in warning["citation"]
    assert evidence["sign_convention"] == "rising consensus scores positive"


# ---------------------------------------------------------------------------
# Sector concentration (spec amendment SA-2026-08-12-07)
# ---------------------------------------------------------------------------

def test_the_sector_cap_trims_the_lowest_scoring_names_in_the_crowded_sector():
    """Four of five legs are continuation signals and continuation clusters by sector.

    Without the cap the top of this ranking is a mega-cap technology bet wearing a five-leg
    label. The trim removes the weakest expressions of the crowded view, never the strongest,
    because the ranking is still the model's opinion and the cap is a constraint on top of it.
    """
    rows = costed_rows(20, sectors=["Technology"] * 16 + ["Energy", "Utilities",
                                                          "Healthcare", "Financials"])
    scored = swing_signals.swing_scores(rows, config={"entry_percentile": 0})

    trims = swing_signals.sector_cap_log(scored)
    book = swing_signals.book_rows(scored, {"entry_percentile": 0})
    held_tech = [row for row in book if row["sector"] == "Technology"]

    assert trims, "a 16-of-20 technology book must be trimmed at a 30% cap"
    assert len(held_tech) <= max(1, int(.30 * len(book)))
    assert all(trim["sector"] == "Technology" for trim in trims)
    # The trimmed names are the lowest-scoring technology names, not an arbitrary selection.
    trimmed_scores = [trim["score"] for trim in trims]
    assert max(trimmed_scores) <= min(row["score"] for row in held_tech)
    # Every trim is logged with what it was measured against.
    assert all(trim["cap"] == .30 and trim["book_size_before"] for trim in trims)


def test_a_capped_name_stays_published_with_its_reason_rather_than_disappearing():
    rows = costed_rows(20, sectors=["Technology"] * 16 + ["Energy", "Utilities",
                                                          "Healthcare", "Financials"])
    scored = {row["ticker"]: row for row in
              swing_signals.swing_scores(rows, config={"entry_percentile": 0})}

    capped = [row for row in scored.values() if row["sector_capped"]]

    assert capped
    for row in capped:
        assert "SECTOR_CONCENTRATION_CAP" in row["reason_codes"]
        assert row["current_membership"] is False
        assert row["sector_trim"]["ticker"] == row["ticker"]


def test_the_sector_cap_always_leaves_one_name_per_sector():
    """On a book of three a 30% cap is otherwise unsatisfiable and would trim to nothing."""
    rows = costed_rows(3, sectors=["Technology", "Technology", "Energy"])

    scored = swing_signals.swing_scores(rows, config={"entry_percentile": 0})
    book = swing_signals.book_rows(scored, {"entry_percentile": 0})

    assert len(book) >= 2
    assert {row["sector"] for row in book} == {"Technology", "Energy"}


# ---------------------------------------------------------------------------
# Registered reversal variants (spec amendment SA-2026-08-12-08)
# ---------------------------------------------------------------------------

def test_variant_a_is_the_frozen_baseline_and_is_unchanged():
    assert swing_signals.BASELINE_VARIANT == "A"
    assert swing_signals.SWING_VARIANTS["A"]["is_frozen_baseline"] is True
    assert swing_signals.variant_weights("A") == swing_signals.SWING_WEIGHTS
    assert swing_signals.SWING_WEIGHTS["short_term_reversal"] == .10


def test_variant_b_drops_reversal_and_redistributes_its_weight_proportionally():
    weights = swing_signals.variant_weights("B")

    assert "short_term_reversal" not in weights
    assert round(sum(weights.values()), 9) == 1.0
    # Proportional, so the evidence ordering among the four survivors is unchanged.
    assert round(weights["pead_drift"], 6) == round(.30 / .90, 6)
    assert round(weights["analyst_revision"], 6) == round(.25 / .90, 6)
    ratio_before = swing_signals.SWING_WEIGHTS["pead_drift"] / swing_signals.SWING_WEIGHTS["analyst_revision"]
    assert round(weights["pead_drift"] / weights["analyst_revision"], 9) == round(ratio_before, 9)


def test_variant_c_scores_a_residualized_reversal_at_the_same_weight():
    weights = swing_signals.variant_weights("C")
    assert weights == swing_signals.SWING_WEIGHTS
    assert swing_signals.variant_subfactors("C")["short_term_reversal"] == \
        (("residual_return_5d", True),)


def test_the_residual_reversal_removes_the_industry_and_other_leg_components():
    """Da, Liu & Schaumburg (Management Science 2014): the residual is what survives.

    Build a cross-section where the prior-week return is entirely explained by the sector's
    own move. The raw leg scores that as reversal; the residualized leg must score close to
    nothing, because there is nothing left after the industry return is removed.
    """
    rows = []
    for index in range(24):
        sector = "Technology" if index % 2 else "Energy"
        sector_move = 6.0 if sector == "Technology" else -6.0
        rows.append({"ticker": f"T{index}", "median_dollar_volume_60d": 1e9, "sector": sector,
                     "price": 50.0, "market_cap": 5e9, "history_sessions": 400,
                     # Deliberately not collinear with one another, so the regression has four
                     # genuinely separate controls rather than one repeated three times.
                     "factors": {"return_5d": sector_move,
                                 "revision_breadth_30d": (index * 7 % 11) / 11,
                                 "volume_ratio_1d_50d": 1 + (index * 5 % 7) / 7,
                                 "high_52w_drawdown_sigmas": -(index * 3 % 13) / 13}})

    raw = swing_signals.swing_scores(rows, variant="A")
    residual = swing_signals.swing_scores(rows, variant="C")

    raw_legs = [row["leg_scores"]["short_term_reversal"] for row in raw]
    residual_legs = [row["leg_scores"]["short_term_reversal"] for row in residual]

    assert max(abs(value) for value in raw_legs) > 0.5
    # Everything the raw leg saw was the sector move, so the residual leg has nothing to say.
    assert max(abs(value) for value in residual_legs) < 1e-6


def test_an_unregistered_variant_raises_rather_than_silently_falling_back():
    import pytest

    with pytest.raises(ValueError, match="unregistered swing variant"):
        swing_signals.swing_scores([], variant="D")


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


def test_build_rows_wires_the_archive_series_into_narrow_range():
    universe = [universe_row("AAA")]
    entries = entries_for({"AAA": cache_entry()})
    archive = {
        "AAA": {
            "dates": sessions_from("2026-08-01", 7),
            "highs": [110.0, 108.0, 107.0, 106.0, 105.5, 105.0, 104.5],
            "lows": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 104.0],
            "closes": [105.0, 104.0, 103.5, 103.0, 102.5, 102.0, 104.2],
        },
    }

    rows = module.build_rows(universe, entry_for=entries, observations={},
                             archive_for=lambda ticker: archive.get(ticker))

    assert rows[0]["factors"]["contraction"]["narrow_range"]["is_nr7"] is True


def test_build_rows_defaults_to_no_archive_series_rather_than_erroring():
    universe = [universe_row("AAA")]
    entries = entries_for({"AAA": cache_entry()})

    rows = module.build_rows(universe, entry_for=entries, observations={},
                             archive_for=lambda ticker: None)

    assert rows[0]["factors"]["contraction"]["narrow_range"] is None
    assert rows[0]["factors"]["contraction"]["atr_compression"] is None


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
    recorded = {}
    monkeypatch.setattr(module.swing_pit_store, "append_snapshot",
                        lambda results, **kwargs: recorded.__setitem__("results", results))

    result = module.run()

    assert saved["screens/swing.json"] is result
    assert recorded["results"] == result["results"]
    assert result["status"] == "success"
    assert result["scored_count"] == 8
    assert [row["rank"] for row in result["results"]] == list(range(1, len(result["results"]) + 1))
    # The file has to carry why each leg is there, not just the number it produced. Containment
    # rather than equality since the horizon tiers landed: `evidence` now also covers legs no
    # tier-agnostic weight vector declares (the announcement return), and every one of those
    # still has to arrive with its citation attached.
    assert set(result["weights"]) <= set(result["evidence"])
    assert all(result["evidence"][leg].get("citation")
               for tier in result["tier_order"]
               for leg in result["tiers"][tier]["weights"])
    assert result["evidence"]["pead_drift"]["citation"].startswith("Bernard & Thomas")
    assert result["decay_haircut"]["post_publication"] == .58
    assert set(result["leg_coverage"]) == set(swing_signals.SWING_WEIGHTS)
    assert result["negative_screen"]["direction"].startswith("negative")
    # The contraction context is published beside the score on every row, and its evidence
    # travels with it, but it must never be one of the declared, weighted legs.
    assert all("contraction" in row for row in result["results"])
    assert set(result["context_signal_evidence"]) == {
        "bandwidth_squeeze", "volume_dry_up", "rsi_2", "narrow_range", "atr_compression",
        "chaikin_money_flow", "weinstein_stage2", "vcp", "sector_relative_strength"}
    assert not set(result["context_signal_evidence"]) & set(result["weights"])
    # The new accumulation/trend-stage context is published beside the score on every row too,
    # and the market-wide regime gate is published once at the top level.
    assert all("context" in row for row in result["results"])
    assert "regime_gate" in result


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
