"""The horizon tiers: three books, not one composite sorted three ways.

What these tests are actually guarding is the claim that makes the split worth having. If the
three tiers carry the same legs at the same weights behind the same gates, the structure is
complexity without diversification and should be collapsed back to one book. Several tests
below fail loudly if that ever becomes true.
"""

import math
import random

import pytest

import build_swing_screen as builder
import swing_signals
import swing_tiers as tiers
from test_build_swing_screen import cache_entry, entries_for, universe_row

SECTORS = ["Technology", "Health Care", "Financials", "Energy", "Industrials", "Consumer Staples"]


def varied_volumes(count=400, base=3_000_000.0, spike=1.0):
    """Volume with real dispersion, so abnormal turnover has a scale to measure against.

    A flat series is not a weak case for the abnormal-turnover construct, it is an undefined
    one: zero dispersion means there is no sigma to express a shock in.
    """
    series = [base * (1 + .25 * math.sin(index * 1.7)) for index in range(count)]
    series[-1] *= spike
    return series


def tier_universe(count=300):
    """A synthetic cross-section, seeded so it is deterministic but not self-correlated.

    Sector, announcement timing and the sign of the announcement move are drawn independently.
    An earlier version derived all three from the same index modulus, which meant every name
    that jumped upward was also Technology: the top of every book was one sector, the 30%
    concentration cap trimmed it to a single row, and two tests about how alpha varies across a
    book had nothing to vary over. A fixture whose variables are secretly the same variable
    hides exactly the behaviour it is meant to exercise.
    """
    rng = random.Random(20260813)
    universe, entries, sues = [], {}, {}
    for index in range(count):
        ticker = f"T{index:03d}"
        entry = cache_entry(count=400, drift=1.0005)
        entry["volumes"] = varied_volumes(spike=3.5 if rng.random() < .25 else 1.0)
        if rng.random() < .34:
            # Announcement ages have to straddle every tier's window or the fixture cannot
            # tell a working gate from a broken one. Roughly half are inside the fast book's
            # five sessions and half are stale to it but still open to the slow book, which is
            # the distribution a real cross-section mid-quarter actually has.
            age = rng.randint(1, 4) if rng.random() < .5 else rng.randint(18, 42)
            jump = 1 + rng.uniform(-.08, .10)
            entry["closes"][-(age + 1):] = [close * jump for close in entry["closes"][-(age + 1):]]
            sues[ticker] = {"sue": rng.uniform(-4, 4), "basis": "as_filed",
                            "release_datetime": "2026-08-01T12:00:00Z", "age_trading_days": age,
                            "period_end": "2026-06-30", "release_date": "2026-08-01"}
        row = universe_row(ticker)
        row["market_cap"] = 1e9 * rng.randint(1, 40)
        row["sector"] = rng.choice(SECTORS)
        universe.append(row)
        entries[ticker] = entry
    return universe, entries, sues


def scored_rows(count=300):
    """A cross-section wide enough that each tier's book has real members.

    At 120 names the entry percentile and the sector cap left every book with a single row,
    which quietly made "does alpha vary by row" untestable and let the mean-calibration test
    pass by skipping. A fixture that cannot exhibit the behaviour under test is not a cheaper
    fixture, it is an absent one.
    """
    universe, entries, sues = tier_universe(count)
    return builder.build_rows(universe, entry_for=entries_for(entries), observations={},
                              as_of="2026-08-13", sue_resolver=lambda ticker, *_: sues.get(ticker))


# ---------------------------------------------------------------------------
# The announcement-return leg
# ---------------------------------------------------------------------------

def test_announcement_return_measures_the_zero_to_plus_one_window():
    closes = [100.0] * 300
    closes[-2] = 108.0   # announcement day
    closes[-1] = 108.0   # +1 session
    assert swing_signals.announcement_return(closes, 1) == pytest.approx(8.0)


def test_announcement_return_needs_a_completed_session_after_the_release():
    """An announcement that fired today has no measurable window, and says so."""
    closes = [100.0] * 300
    closes[-1] = 112.0
    assert swing_signals.announcement_return(closes, 0) is None
    assert swing_signals.announcement_return(closes, None) is None


def test_announcement_return_is_abnormal_not_raw():
    """A name that moved exactly with the universe had no announcement surprise."""
    closes = [100.0] * 300
    closes[-2] = closes[-1] = 108.0
    market = swing_signals.universe_daily_returns([closes] * 5)
    assert swing_signals.announcement_return(closes, 1, market) == pytest.approx(0.0, abs=1e-9)


def test_the_announcement_window_is_a_tier_decision_not_a_factor_decision():
    """Regression: the gate must run per tier, on the scored cross-section.

    Factors are built once per row and scored three times. Gating inside swing_factors applied
    whichever config happened to build the row to all three tiers, which silently ran the 3-day
    book's five-session event window at the default sixty and made the fast tier's whole
    event-trigger design a no-op. Caught only on the real universe: the fast tier's
    announcement leg resolved on 83% of names, which no five-session window can do.

    So this asserts through score_tier, not through swing_factors.
    """
    rows = scored_rows()
    ages = [(row.get("factors") or {}).get("announcement_age_sessions") for row in rows]
    assert any(age is not None and age > 5 for age in ages), "fixture has no stale announcements"

    fast = tiers.score_tier(rows, "F")
    slow = tiers.score_tier(rows, "S")

    # Read the age off each scored row rather than zipping against the input order:
    # score_tier returns the cross-section sorted by score, not in the order it was given.
    fast_limit = tiers.tier_config("F")["announcement_window_max_age"]
    for row in fast:
        age = (row.get("factors") or {}).get("announcement_age_sessions")
        if age is not None and age > fast_limit:
            assert row["leg_scores"]["announcement_return"] is None, row["ticker"]

    # The same rows, read through the slow tier's wider window, still resolve.
    resolved_slow = sum(1 for row in slow if row["leg_scores"]["announcement_return"] is not None)
    resolved_fast = sum(1 for row in fast if row["leg_scores"]["announcement_return"] is not None)
    assert resolved_slow > resolved_fast


def test_raw_announcement_return_is_stored_ungated():
    """The stored factor is the measurement. The window is applied when it is read."""
    closes = [100.0] * 300
    closes[-32] = closes[-31] = 108.0
    sue = {"sue": 1.0, "release_datetime": "2026-08-01T12:00:00Z", "age_trading_days": 30}
    factors = swing_signals.swing_factors({}, closes=closes, volumes=[1e6] * 300, sue=sue,
                                          config=tiers.tier_config("F"))
    assert factors["announcement_return"] is not None
    assert factors["announcement_age_sessions"] == 30


# ---------------------------------------------------------------------------
# Abnormal turnover
# ---------------------------------------------------------------------------

def test_abnormal_turnover_is_undefined_on_a_flat_baseline():
    """Zero dispersion has no sigma to express a shock in, and must not fabricate one.

    Fifty identical volumes give a floating-point variance near 1e-30 rather than exactly
    zero, and dividing a comparably tiny numerator by it returns a confident-looking z of
    roughly 1 for a name whose volume has not moved at all.
    """
    assert swing_signals.abnormal_turnover([1_000_000.0] * 60) is None


def test_abnormal_turnover_does_not_reward_a_quiet_baseline_the_way_a_raw_ratio_does():
    """The liquidity tilt the raw ratio imports, and the reason the tiers do not use it."""
    quiet = varied_volumes(count=60, base=1_000_000.0)
    busy = varied_volumes(count=60, base=1_000_000.0)
    quiet = [value * .2 for value in quiet]
    # Same proportional shock on both, different baseline levels.
    quiet[-1] *= 4
    busy[-1] *= 4
    assert swing_signals.abnormal_turnover(quiet) == pytest.approx(
        swing_signals.abnormal_turnover(busy), rel=1e-6)


# ---------------------------------------------------------------------------
# The tiers are actually different books
# ---------------------------------------------------------------------------

def test_every_tier_declares_weights_summing_to_one():
    for tier in tiers.TIER_ORDER:
        assert round(sum(tiers.tier_spec(tier)["weights"].values()), 6) == 1.0


def test_no_two_tiers_carry_the_same_leg_set():
    """If they did, the three-book structure would be one book sorted three ways."""
    sets = [frozenset(tiers.tier_spec(tier)["weights"]) for tier in tiers.TIER_ORDER]
    assert len(set(sets)) == len(sets)


def test_each_leg_only_enters_a_tier_where_its_payoff_lands():
    """Rule 1: below roughly 20% decay capture a leg is being paid for before it has paid."""
    for tier in tiers.TIER_ORDER:
        for leg in tiers.tier_spec(tier)["weights"]:
            captured = tiers.DECAY_CAPTURE[leg][tier]
            assert captured is not None, f"{leg} has no payoff left at tier {tier}"
            assert captured >= .20, f"{leg} captures only {captured:.0%} at tier {tier}"


def test_the_slow_book_carries_no_volume_leg_and_the_fast_book_no_52_week_leg():
    """The two clearest consequences of the decay matrix, pinned so they cannot drift back."""
    assert "high_volume_premium" not in tiers.tier_spec("S")["weights"]
    assert "high_52w_proximity" not in tiers.tier_spec("F")["weights"]
    assert "pead_drift" not in tiers.tier_spec("F")["weights"]


def test_tier_subfactors_use_abnormal_turnover_rather_than_the_raw_ratio():
    for tier in ("F", "M"):
        names = [name for name, _ in tiers.tier_subfactors(tier)["high_volume_premium"]]
        assert names == ["abnormal_turnover_1d", "abnormal_turnover_5d"]


def test_liquidity_floors_tighten_as_the_horizon_shortens():
    """A faster book pays its round trip more often, so it can afford less of the cost curve."""
    floors = [tiers.tier_config(tier)["minimum_median_dollar_volume_60d"]
              for tier in tiers.TIER_ORDER]
    assert floors == sorted(floors, reverse=True)


def test_tiers_do_not_pollute_the_registered_variant_registry():
    """harness_freeze.json registers SWING_VARIANTS. Tiers are books, not competing specs.

    Registering three tiers as variants would multiply the registered search path by three
    for no measurement gain.
    """
    for tier in tiers.TIER_ORDER:
        assert tiers.tier_spec(tier)["id"] not in {
            spec["id"] for spec in swing_signals.SWING_VARIANTS.values()}


# ---------------------------------------------------------------------------
# The event trigger on the fast book
# ---------------------------------------------------------------------------

def test_the_fast_book_only_admits_names_that_just_reported():
    rows = scored_rows()
    scored = tiers.score_tier(rows, "F")
    admitted = [row for row in scored if row["eligibility"]]
    assert admitted, "the fast tier admitted nothing at all"
    for row in admitted:
        assert row["leg_scores"]["announcement_return"] is not None
    gated = [row for row in scored if "TIER_TRIGGER_UNRESOLVED" in row["reason_codes"]]
    assert gated, "the event gate never fired"
    # Gated rows stay published with a reason rather than vanishing from the count.
    assert all(row["percentile"] is None for row in gated)


def test_the_slower_books_have_no_event_trigger():
    for tier in ("M", "S"):
        scored = tiers.score_tier(scored_rows(), tier)
        assert not any("TIER_TRIGGER_UNRESOLVED" in row["reason_codes"] for row in scored)


def test_percentiles_are_recomputed_after_the_trigger_gate():
    """A gated row must not leave the survivors ranked against a cross-section they left."""
    scored = tiers.score_tier(scored_rows(), "F")
    ranked = sorted((row for row in scored if row["percentile"] is not None),
                    key=lambda row: row["percentile"])
    assert ranked
    assert ranked[0]["percentile"] == 0
    assert ranked[-1]["percentile"] == pytest.approx(100)


# ---------------------------------------------------------------------------
# The cost arithmetic, which is the point of the split
# ---------------------------------------------------------------------------

def test_round_trips_per_year_follow_the_holding_period():
    assert tiers.round_trips_per_year("F") == pytest.approx(84.0)
    assert tiers.round_trips_per_year("M") == pytest.approx(25.2)
    assert tiers.round_trips_per_year("S") == pytest.approx(252 / 65)


def test_expected_alpha_scales_with_the_holding_period_not_the_tier_label():
    """A 3-session hold has one thirteenth of a 40-session hold's time to earn anything."""
    assert (tiers.expected_alpha_bps("S") / tiers.expected_alpha_bps("F")
            == pytest.approx(65 / 3))


def test_the_fast_book_needs_far_more_alpha_per_month_than_the_slow_one():
    """The whole reason the tiers cannot share a cost budget."""
    rows = scored_rows()
    summaries = {tier: tiers.tier_summary(tiers.score_tier(rows, tier), tier)
                 for tier in tiers.TIER_ORDER}
    breakevens = [summaries[tier]["break_even_alpha_bps_per_month"] for tier in tiers.TIER_ORDER]
    assert all(value is not None for value in breakevens), summaries
    assert breakevens == sorted(breakevens, reverse=True)


def test_every_row_publishes_its_own_round_trip_against_its_own_expected_alpha():
    scored = tiers.score_tier(scored_rows(), "M")
    row = next(row for row in scored if row["eligibility"])
    economics = row["economics"]
    assert economics["round_trip_bps"] == pytest.approx(economics["one_way_bps"] * 2)
    assert economics["net_edge_bps"] == pytest.approx(
        economics["expected_alpha_bps"] - economics["round_trip_bps"])
    assert economics["clears_cost"] is (economics["net_edge_bps"] > 0)
    # The spread limitation travels with the number rather than living in a docstring.
    assert economics["spread_source"] == "liquidity_tiered_proxy_not_measured"


def test_a_bigger_book_costs_more_per_round_trip():
    """Impact is a function of position size, so a cost column without a book size is empty."""
    rows = scored_rows()
    small = tiers.tier_summary(tiers.score_tier(rows, "S", book_dollars=1_000_000), "S",
                               book_dollars=1_000_000)
    large = tiers.tier_summary(tiers.score_tier(rows, "S", book_dollars=250_000_000), "S",
                               book_dollars=250_000_000)
    assert large["median_round_trip_bps"] > small["median_round_trip_bps"]


# ---------------------------------------------------------------------------
# What the screen publishes
# ---------------------------------------------------------------------------

def test_the_screen_publishes_three_books_each_with_its_own_legs():
    universe, entries, sues = tier_universe()
    rows = builder.build_rows(universe, entry_for=entries_for(entries), observations={},
                              as_of="2026-08-13", sue_resolver=lambda ticker, *_: sues.get(ticker))
    previous = {tier: {} for tier in tiers.TIER_ORDER}
    for tier in tiers.TIER_ORDER:
        book = builder.tier_book(rows, tier, previous)
        assert book["tier"] == tier
        assert set(book["weights"]) == set(tiers.tier_spec(tier)["weights"])
        assert set(book["leg_coverage"]) == set(book["weights"])
        assert set(book["evidence"]) == set(book["weights"])
        assert book["results"], f"tier {tier} published nothing"
        for row in book["results"]:
            assert row["tier"] == tier
            assert set(row["legs"]) == set(book["weights"])
            assert "economics_net_edge_bps" in row


def test_the_published_alpha_figure_is_labelled_an_assumption():
    """It is the weakest link in every cost column, so it may never travel unlabelled."""
    assert "assumption" in tiers.ALPHA_NOTE.lower()
    assert "not a measurement" in tiers.ALPHA_NOTE.lower()


def test_the_sector_cap_is_recomputed_after_the_trigger_gate():
    """The cap trims the crowded sector's weakest name, and which name that is moves.

    The gate runs after swing_scores has already ranked and capped, so without a re-cap the
    fast book carries trims decided against a book several times larger. A capped row must
    never survive as capped when it would not have been capped against the book it is in.
    """
    scored = tiers.score_tier(scored_rows(), "F")
    config = tiers.tier_config("F")
    book = [row for row in scored
            if row["eligibility"] and not row.get("sector_capped")
            and (row.get("percentile") or 0) >= config["entry_percentile"]]
    if not book:
        pytest.skip("no fast-tier book on this fixture to check the cap against")
    counts = {}
    for row in book:
        counts[row["sector"]] = counts.get(row["sector"], 0) + 1
    allowed = max(1, int(config["sector_concentration_cap"] * len(book)))
    assert max(counts.values()) <= allowed, counts

    # Nothing may carry a trim without also carrying the reason code, in either direction.
    for row in scored:
        capped = bool(row.get("sector_capped"))
        assert capped == ("SECTOR_CONCENTRATION_CAP" in row["reason_codes"])
        assert capped == (row.get("sector_trim") is not None)


def test_the_trigger_gate_does_not_compound_sector_trims():
    """Re-running the cap must reset the previous pass's marks, not stack on top of them."""
    scored = tiers.score_tier(scored_rows(), "F")
    for row in scored:
        assert row["reason_codes"].count("SECTOR_CONCENTRATION_CAP") <= 1


# ---------------------------------------------------------------------------
# Trend state: descriptive price position, never a signal
# ---------------------------------------------------------------------------

def _path(fn, count=300):
    return [fn(index) for index in range(count)]


def test_trend_state_names_the_obvious_shapes():
    cases = {
        "at_high": _path(lambda i: 100 * (1.002 ** i)),
        "at_low": _path(lambda i: 200 * (0.998 ** i)),
    }
    for expected, series in cases.items():
        assert swing_signals.trend_state(series)["state"] == expected, expected


def test_a_narrow_range_is_not_a_52_week_high():
    """A name oscillating 3% around one level is at its 52-week high most weeks.

    Saying so is true and useless: in a column being scanned it reads as a breakout. Below
    MINIMUM_MEANINGFUL_52W_RANGE the extremes are suppressed and the row falls through to the
    trending cases, which describe such a name correctly.
    """
    narrow = _path(lambda i: 100 + 3 * math.sin(i / 9))
    wide = _path(lambda i: 100 + 30 * math.sin(i / 9))
    assert swing_signals.range_position_52w(narrow) > .97
    assert swing_signals.trend_state(narrow)["state"] != "at_high"
    # Same shape, meaningful amplitude, and the label is now the useful one.
    assert swing_signals.range_position_52w(wide) > .97
    assert swing_signals.trend_state(wide)["state"] == "at_high"


def test_a_bounce_off_the_low_is_separated_from_both_the_low_and_a_plain_uptrend():
    series = _path(lambda i: 200 * (0.997 ** i))
    series = series[:-15] + [series[-15] * (1.012 ** step) for step in range(1, 16)]
    state = swing_signals.trend_state(series)
    assert state["state"] == "turning_up"
    assert state["label"] == "Turning up off the low"


def test_trend_state_needs_history_and_says_so():
    assert swing_signals.trend_state([100.0] * 30) is None
    assert swing_signals.range_position_52w([100.0] * 30) is None


def test_trend_is_never_a_scoring_leg():
    """The whole technical canon is excluded from the weights. This must not smuggle it back."""
    scored = tiers.score_tier(scored_rows(), "S")
    for tier in tiers.TIER_ORDER:
        weights = tiers.tier_spec(tier)["weights"]
        assert "trend" not in weights
        assert "range_position_52w" not in weights
        for subfactors in tiers.tier_subfactors(tier).values():
            names = [name for name, _ in subfactors]
            assert "range_position_52w" not in names
            assert "trend" not in names
    # And it is not readable as a subfactor on any row's leg scores.
    assert all("trend" not in (row.get("leg_scores") or {}) for row in scored)


# ---------------------------------------------------------------------------
# Predicted upside
# ---------------------------------------------------------------------------

def test_predicted_upside_varies_by_row_rather_than_being_a_tier_constant():
    scored = tiers.score_tier(scored_rows(), "S")
    book = [row for row in scored if row.get("current_membership")]
    assert len(book) > 2
    alphas = {row["economics"]["expected_alpha_bps"] for row in book}
    assert len(alphas) > 1, "every row carries the same alpha, so it is not scaled by score"
    assert all(row["economics"]["alpha_basis"] == "scaled_by_composite_score" for row in book)


def test_a_higher_scoring_row_carries_more_implied_alpha():
    scored = tiers.score_tier(scored_rows(), "S")
    book = sorted((row for row in scored if row.get("current_membership")),
                  key=lambda row: row["score"])
    assert (book[-1]["economics"]["expected_alpha_bps"]
            > book[0]["economics"]["expected_alpha_bps"])


def test_the_books_mean_row_carries_the_tiers_assumed_alpha():
    """The calibration anchor: per-row numbers must not invent a second assumption."""
    for tier in tiers.TIER_ORDER:
        scored = tiers.score_tier(scored_rows(), tier)
        book = [row for row in scored if row.get("current_membership")]
        assert len(book) >= 2, f"tier {tier} book too small to check the calibration against"
        mean = sum(row["economics"]["expected_alpha_bps"] for row in book) / len(book)
        assert mean == pytest.approx(tiers.expected_alpha_bps(tier), rel=.02), tier


def test_the_model_edge_is_net_of_that_rows_own_cost():
    scored = tiers.score_tier(scored_rows(), "S")
    row = next(row for row in scored if row.get("current_membership"))
    economics = row["economics"]
    assert economics["net_edge_bps"] == pytest.approx(
        economics["expected_alpha_bps"] - economics["round_trip_bps"])
    # clears_cost is about the model's edge surviving cost, not about the published upside,
    # which is dominated by the name's own travel and would make a volatile name look like a
    # buy the model never had a view on.
    assert economics["clears_cost"] is (economics["net_edge_bps"] > 0)


def test_upside_falls_back_to_the_flat_figure_without_a_cross_section():
    """One row and no book cannot calibrate, and must say so rather than guess."""
    scored = tiers.score_tier(scored_rows(), "S")
    economics = tiers.row_economics(scored[0], "S")
    assert economics["alpha_basis"] == "tier_flat"
    assert economics["expected_alpha_bps"] == pytest.approx(tiers.expected_alpha_bps("S"), abs=.01)


def test_the_upside_note_refuses_the_word_forecast():
    """It is a shared-out assumption. The page must never let it read as a price forecast."""
    assert "not a forecast" in tiers.UPSIDE_NOTE.lower()
    assert "no out-of-sample record" in tiers.UPSIDE_NOTE.lower()


# ---------------------------------------------------------------------------
# Upside grounded in the name's own past travel
# ---------------------------------------------------------------------------

def test_forward_returns_describe_how_far_a_name_travels_in_a_window():
    steady = [100 * (1.0008 ** index) for index in range(400)]
    distribution = swing_signals.forward_return_distribution(steady, 65)
    assert distribution["windows"] == 335
    assert distribution["p50"] == pytest.approx(5.34, abs=.05)
    assert distribution["share_positive"] == 1.0
    # A choppy name travels far less over the same window, which is the whole point.
    choppy = [100 + 8 * math.sin(index / 11) for index in range(400)]
    assert abs(swing_signals.forward_return_distribution(choppy, 65)["p50"]) < 1


def test_forward_returns_refuse_to_describe_too_few_windows():
    """Six overlapping windows is not a distribution, and must not be published as one."""
    short = [100 * (1.001 ** index) for index in range(80)]
    assert swing_signals.forward_return_distribution(short, 65) is None
    assert swing_signals.forward_return_distribution(short, 3) is not None


def test_quantiles_are_ordered():
    series = [100 * (1 + .01 * math.sin(index / 7)) for index in range(400)]
    for horizon in (3, 10, 65):
        d = swing_signals.forward_return_distribution(series, horizon)
        assert d["p25"] <= d["p50"] <= d["p75"], horizon


def test_upside_is_the_names_own_travel_plus_the_model_edge_less_cost():
    scored = tiers.score_tier(scored_rows(), "S")
    row = next(r for r in scored if r["economics"].get("typical_move_pct") is not None)
    economics = row["economics"]
    assert economics["upside_basis"] == "historical_travel_plus_model_edge"
    assert economics["predicted_upside_pct"] == pytest.approx(
        economics["typical_move_pct"] + economics["net_edge_bps"] / 100, abs=.01)


def test_each_tier_measures_travel_over_its_own_holding_period():
    """A 3-session book must not be sized by how far a name moves in 65 sessions."""
    rows = scored_rows()
    by_tier = {}
    for tier in tiers.TIER_ORDER:
        scored = tiers.score_tier(rows, tier)
        moves = [r["economics"]["typical_move_pct"] for r in scored
                 if r["economics"].get("typical_move_pct") is not None]
        assert moves, tier
        by_tier[tier] = sum(moves) / len(moves)
    # Longer hold, more travel. These fixtures drift upward, so this is monotone.
    assert by_tier["F"] < by_tier["M"] < by_tier["S"]


def test_upside_falls_back_to_the_model_edge_when_history_is_too_short():
    scored = tiers.score_tier(scored_rows(), "S")
    row = dict(scored[0])
    row["factors"] = {**row["factors"], "forward_returns": {}}
    economics = tiers.row_economics(row, "S")
    assert economics["upside_basis"] == "model_edge_only_no_price_history"
    assert economics["typical_move_pct"] is None
    assert economics["predicted_upside_pct"] == pytest.approx(economics["net_edge_bps"] / 100, abs=.01)


def test_the_verdict_still_turns_on_the_model_edge_not_on_past_travel():
    """A name that travels far is not thereby a buy.

    Upside is dominated by historical travel, so if the buy/avoid decision keyed off upside a
    volatile name the model has no view on would read as the best idea on the page. It keys
    off net_edge_bps, which is the model's own edge after cost.
    """
    scored = tiers.score_tier(scored_rows(), "S")
    for row in scored:
        economics = row["economics"]
        if economics["clears_cost"]:
            assert economics["net_edge_bps"] > 0


def test_the_upside_note_names_which_term_sets_the_scale():
    note = tiers.UPSIDE_NOTE.lower()
    assert "not a forecast" in note
    assert "no out-of-sample record" in note
    assert "it is not alpha" in note
    assert "optimistic" in note
