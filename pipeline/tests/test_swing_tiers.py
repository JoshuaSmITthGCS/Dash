"""The horizon tiers: three books, not one composite sorted three ways.

What these tests are actually guarding is the claim that makes the split worth having. If the
three tiers carry the same legs at the same weights behind the same gates, the structure is
complexity without diversification and should be collapsed back to one book. Several tests
below fail loudly if that ever becomes true.
"""

import math

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


def tier_universe(count=120):
    universe, entries, sues = [], {}, {}
    for index in range(count):
        ticker = f"T{index:03d}"
        entry = cache_entry(count=400, drift=1.0005)
        entry["volumes"] = varied_volumes(spike=3.5 if index % 4 == 0 else 1.0)
        if index % 3 == 0:
            age = 1 + (index % 4)
            jump = 1 + (.09 if index % 6 == 0 else -.06)
            entry["closes"][-(age + 1):] = [close * jump for close in entry["closes"][-(age + 1):]]
            sues[ticker] = {"sue": (index % 9) - 4, "basis": "as_filed",
                            "release_datetime": "2026-08-01T12:00:00Z", "age_trading_days": age,
                            "period_end": "2026-06-30", "release_date": "2026-08-01"}
        row = universe_row(ticker)
        row["market_cap"] = 1e9 * (1 + index % 40)
        row["sector"] = SECTORS[index % len(SECTORS)]
        universe.append(row)
        entries[ticker] = entry
    return universe, entries, sues


def scored_rows():
    universe, entries, sues = tier_universe()
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


def test_announcement_return_is_dropped_once_its_tier_window_closes():
    closes = [100.0] * 300
    closes[-4] = closes[-3] = closes[-2] = closes[-1] = 108.0
    sue = {"sue": 1.0, "release_datetime": "2026-08-01T12:00:00Z", "age_trading_days": 3}
    fast = swing_signals.swing_factors({}, closes=closes, volumes=[1e6] * 300, sue=sue,
                                       config=tiers.tier_config("F"))
    slow = swing_signals.swing_factors({}, closes=closes, volumes=[1e6] * 300, sue=sue,
                                       config=tiers.tier_config("S"))
    assert fast["announcement_return"] is not None
    assert slow["announcement_return"] is not None

    stale = {**sue, "age_trading_days": 30}
    assert swing_signals.swing_factors({}, closes=closes, volumes=[1e6] * 300, sue=stale,
                                       config=tiers.tier_config("F"))["announcement_return"] is None
    assert swing_signals.swing_factors({}, closes=closes, volumes=[1e6] * 300, sue=stale,
                                       config=tiers.tier_config("S"))["announcement_return"] is not None


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
    assert tiers.round_trips_per_year("S") == pytest.approx(6.3)


def test_expected_alpha_scales_with_the_holding_period_not_the_tier_label():
    """A 3-session hold has one thirteenth of a 40-session hold's time to earn anything."""
    assert (tiers.expected_alpha_bps("S") / tiers.expected_alpha_bps("F")
            == pytest.approx(40 / 3))


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
