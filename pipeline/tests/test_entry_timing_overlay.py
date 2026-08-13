"""The entry-timing overlay: what it refuses to do matters more than what it computes.

Most of these tests are about the guard rails. The overlay is a timing gate on an already
ranked list, its toggles are transforms of one price series and must never be read as
independent confirmations, and the evidence bar it has to clear is raised rather than standard
(Sullivan, Timmermann & White, Journal of Finance 1999; Harvey, Liu & Zhu, Review of Financial
Studies 29(1), 2016). Each of those is enforced in code and pinned here.
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import swing_signals
from overlay import entry_timing
from overlay.entry_timing import (DEFER, ENTER_NOW, REJECT, OverlayConfigError,
                                  apply_overlay, config_for_variant, default_config,
                                  deferral_distribution, ema, gate_pass_rates,
                                  macd_histogram, relative_volume, rsi, track_deferral,
                                  validate_config)

FREEZE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "validation",
                      "harness_freeze.json")


# ---------------------------------------------------------------------------
# It defaults off and refuses to run unregistered
# ---------------------------------------------------------------------------

def test_the_overlay_defaults_entirely_off():
    block = default_config()["entry_timing_overlay"]

    assert block["enabled"] is False
    assert block["registered_variant_id"] is None
    assert block["trend_gate"]["enabled"] is False
    assert block["momentum_turn"]["mode"] == "off"
    assert block["volume_gate"]["enabled"] is False


def test_enabling_without_a_registered_variant_id_raises():
    config = default_config()
    config["entry_timing_overlay"]["enabled"] = True

    with pytest.raises(OverlayConfigError, match="no registered_variant_id"):
        validate_config(config, freeze_path=FREEZE)


def test_a_variant_id_absent_from_the_freeze_file_raises():
    config = default_config()
    config["entry_timing_overlay"]["enabled"] = True
    config["entry_timing_overlay"]["registered_variant_id"] = "O-9"

    with pytest.raises(OverlayConfigError, match="not in the freeze file"):
        validate_config(config, freeze_path=FREEZE)


def test_the_five_registered_cells_are_the_ones_in_the_freeze_file():
    with open(FREEZE, encoding="utf-8") as handle:
        registered = {variant["variant_id"]
                      for variant in json.load(handle)["entry_timing_overlay"]["variants"]}

    assert registered == set(entry_timing.REGISTERED_VARIANTS)
    assert len(registered) == 5


def test_there_is_no_mode_that_runs_rsi_and_macd_together():
    """RSI and MACD are transforms of the same price series.

    Reading a rising RSI and a turning MACD histogram as two confirmations triple-counts one
    factor. Testing both means registering two variants, and both consume test budget.
    """
    assert entry_timing.MOMENTUM_MODES == ("off", "rsi_change", "macd_hist_slope")

    for attempt in ("rsi_change+macd_hist_slope", "both", "all", ["rsi_change", "macd_hist_slope"]):
        config = default_config()
        config["entry_timing_overlay"]["momentum_turn"]["mode"] = attempt
        with pytest.raises(OverlayConfigError, match="exactly one"):
            validate_config(config, freeze_path=FREEZE)


def test_a_config_that_disagrees_with_its_own_variant_id_raises():
    """No parameter may change after its variant is registered. Changing one is a new variant."""
    config = config_for_variant("O-2")            # trend gate on, no momentum mode, volume on
    config["entry_timing_overlay"]["momentum_turn"]["mode"] = "rsi_change"

    with pytest.raises(OverlayConfigError, match="does not match registered variant"):
        validate_config(config, freeze_path=FREEZE)


def test_each_registered_cell_builds_a_config_that_validates():
    for variant_id in entry_timing.REGISTERED_VARIANTS:
        block = validate_config(config_for_variant(variant_id), freeze_path=FREEZE)
        assert block["registered_variant_id"] == variant_id


def test_an_unregistered_cell_cannot_be_built():
    with pytest.raises(OverlayConfigError, match="unregistered overlay variant"):
        config_for_variant("O-5")


# ---------------------------------------------------------------------------
# It is a gate, never a leg
# ---------------------------------------------------------------------------

def test_neither_rsi_nor_macd_appears_anywhere_in_the_composite():
    """The separation that makes this an overlay rather than a sixth leg.

    The composite's docstring names RSI and MACD to explain why they are not legs, so the
    check is on what the composite computes rather than on what it mentions: no leg, no
    subfactor, no weight and no evidence entry may refer to either.
    """
    named = set(swing_signals.SWING_WEIGHTS) | set(swing_signals.SWING_SUBFACTORS)
    named |= {name for definition in swing_signals.SWING_SUBFACTORS.values()
              for name, _ in definition}
    named |= set(swing_signals.SWING_EVIDENCE)
    named |= set(swing_signals.DEFAULT_CONFIG)
    for variant in swing_signals.SWING_VARIANTS:
        named |= set(swing_signals.variant_weights(variant))

    assert not any("rsi" in name.lower() or "macd" in name.lower() for name in named)
    # And the dependency only points one way: the scorer does not import the overlay.
    source = open(swing_signals.__file__, encoding="utf-8").read()
    assert "import overlay" not in source and "from overlay" not in source


def test_the_overlay_never_reorders_or_rescores_the_ranked_list():
    rows = [{"ticker": f"T{index}", "rank": index + 1, "composite_z": 2.0 - index / 10}
            for index in range(5)]

    overlaid = apply_overlay(rows, lambda ticker: rising_series(), config_for_variant("O-3"),
                             freeze_path=FREEZE)

    assert [row["ticker"] for row in overlaid] == [row["ticker"] for row in rows]
    assert [row["rank"] for row in overlaid] == [row["rank"] for row in rows]
    assert [row["composite_z"] for row in overlaid] == [row["composite_z"] for row in rows]


def test_with_the_overlay_off_every_row_enters_now_and_says_why():
    """O-0 is a real cell of the ablation, not the absence of one."""
    rows = [{"ticker": "AAA"}, {"ticker": "BBB"}]

    overlaid = apply_overlay(rows, lambda ticker: {}, default_config(), freeze_path=FREEZE)

    assert all(row["entry_state"] == ENTER_NOW for row in overlaid)
    assert all(row["entry_reason"] == "OVERLAY_DISABLED" for row in overlaid)


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def rising_series(sessions=200, start=100.0, drift=1.004):
    return {"closes": [start * drift ** index for index in range(sessions)],
            "volumes": [1_000_000.0] * (sessions - 1) + [4_000_000.0]}


def falling_series(sessions=200, start=200.0, drift=0.996):
    return {"closes": [start * drift ** index for index in range(sessions)],
            "volumes": [1_000_000.0] * sessions}


def macd_turn_path():
    """A decline that accelerates and then eases, stopped on the session the slope turns.

    The histogram is still negative here and its slope has just crossed from falling to
    rising, which is precisely the event the trigger fires on and strictly earlier than the
    signal-line crossover.
    """
    closes = [200 * 0.99 ** index for index in range(120)]
    return closes + [closes[-1] * 0.97 ** step for step in range(1, 13)]


def test_ema_needs_its_full_period_before_it_answers():
    assert ema([1.0] * 5, 10) is None
    flat = ema([100.0] * 40, 10)
    assert flat and all(abs(value - 100.0) < 1e-9 for value in flat)


def test_rsi_saturates_on_an_unbroken_advance_and_bottoms_on_an_unbroken_decline():
    up = rsi([100 + index for index in range(60)], 14)
    down = rsi([100 - index for index in range(60)], 14)

    assert up[-1] == pytest.approx(100.0)
    assert down[-1] == pytest.approx(0.0)
    assert rsi([100.0] * 5, 14) is None


def test_the_macd_histogram_is_the_line_less_its_signal_not_the_crossover():
    closes = [100 + 10 * math.sin(index / 12) for index in range(200)]

    histogram = macd_histogram(closes)

    assert histogram and len(histogram) > 10
    # It oscillates around zero rather than trending, which a line-less-signal series must.
    assert min(histogram) < 0 < max(histogram)


def test_relative_volume_measures_a_name_against_its_own_trailing_mean():
    closes = [10.0] * 40
    volumes = [1_000_000.0] * 39 + [3_000_000.0]

    assert relative_volume(closes, volumes, 20) == pytest.approx(3.0)
    assert relative_volume(closes[:5], volumes[:5], 20) is None


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_the_trend_gate_rejects_a_falling_knife():
    """An oversold reading inside a bearish trend is continuation, not reversal."""
    rows = [{"ticker": "FALLING"}]

    overlaid = apply_overlay(rows, lambda ticker: falling_series(),
                             config_for_variant("O-1"), freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == REJECT
    assert overlaid[0]["entry_reason"] in {"EMA_FAST_NOT_RISING", "CLOSE_BELOW_SLOW_EMA"}


def test_the_trend_gate_passes_a_name_in_an_uptrend():
    overlaid = apply_overlay([{"ticker": "RISING"}], lambda ticker: rising_series(),
                             config_for_variant("O-1"), freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == ENTER_NOW
    assert overlaid[0]["entry_gates"]["trend_gate"]["pass"] is True


def test_the_momentum_mode_is_only_evaluated_on_rows_that_pass_the_trend_gate():
    overlaid = apply_overlay([{"ticker": "FALLING"}], lambda ticker: falling_series(),
                             config_for_variant("O-3"), freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == REJECT
    assert "momentum_turn" not in overlaid[0]["entry_gates"]


def test_no_fixed_rsi_level_is_the_primary_trigger():
    """The level-threshold family is the most data-snooped surface in the whole literature.

    A fixed level is chosen on the sample it is then evaluated on, which is where the
    overfitting enters. The trigger here is a change plus an inflection through the name's own
    trailing median, both of which are properties of the series rather than constants.
    """
    momentum = default_config()["entry_timing_overlay"]["momentum_turn"]

    # There is no level parameter to tune, because there is no level rule to tune it for.
    assert set(momentum) == {"mode", "rsi_period", "rsi_change_lookback", "rsi_median_lookback",
                             "macd_fast", "macd_slow", "macd_signal"}
    for forbidden in ("rsi_oversold", "rsi_threshold", "rsi_level", "rsi_entry",
                      "rsi_overbought"):
        assert forbidden not in momentum

    # Every reason the trigger can give is about a change or about the name's own trailing
    # median. None of them is about a level.
    config = dict(momentum)
    reasons = set()
    for closes in ([100 * 1.004 ** index for index in range(200)],
                   [200 * 0.99 ** index for index in range(200)],
                   [100.0] * 200):
        reasons.add(entry_timing.rsi_change_turn(closes, config)["reason"])
    assert reasons <= {"RSI_CHANGE_TURN", "RSI_NOT_RISING",
                       "RSI_HAS_NOT_CROSSED_ITS_TRAILING_MEDIAN",
                       "INSUFFICIENT_HISTORY_FOR_RSI", "INSUFFICIENT_HISTORY_FOR_RSI_MEDIAN"}

    # The reference point is a property of each series, so two different names are measured
    # against two different reference points rather than against one shared constant.
    def trailing_median(closes):
        series = rsi(closes, config["rsi_period"])[-config["rsi_median_lookback"]:]
        ordered = sorted(series)
        middle = len(ordered) // 2
        return (ordered[middle] if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) / 2)

    drifting_up = trailing_median([100 * 1.003 ** index + (index % 5) for index in range(200)])
    drifting_down = trailing_median([200 * 0.997 ** index + (index % 5) for index in range(200)])
    assert drifting_up != drifting_down
    # And neither of them landed on a canonical level, which is the whole point.
    assert drifting_up not in (30.0, 50.0, 70.0)


def test_the_rsi_trigger_needs_both_a_rise_and_a_median_crossing():
    """Either one alone is a state. Together they are an event, which is what is being tested."""
    config = default_config()["entry_timing_overlay"]["momentum_turn"]

    # An unbroken advance: RSI is rising but crossed its trailing median long ago.
    steady = [100 * 1.004 ** index for index in range(200)]
    assert entry_timing.rsi_change_turn(steady, config)["pass"] is False

    # A decline that turns: RSI rises through its own trailing median on the last session.
    # The trigger is an event, so it fires on the crossing session and not on the ones after.
    turning = [200 * 0.99 ** index for index in range(120)]
    turning += [turning[-1] * 1.02]
    reading = entry_timing.rsi_change_turn(turning, config)
    assert reading["pass"] is True
    assert reading["rsi_change"] > 0
    assert reading["rsi"] > reading["rsi_trailing_median"]


def test_the_macd_trigger_is_the_histogram_slope_turn_not_the_crossover():
    """The crossover is later by construction: the histogram must climb back through zero."""
    config = default_config()["entry_timing_overlay"]["momentum_turn"]
    closes = macd_turn_path()

    reading = entry_timing.macd_hist_slope_turn(closes, config)

    assert reading["pass"] is True
    # Fires while the histogram is still negative, which is what makes it earlier.
    assert reading["macd_histogram"] < 0
    assert reading["histogram_slope"] > 0
    # A histogram already above zero is past the point this trigger is about.
    positive = [100 * 1.01 ** index for index in range(200)]
    assert entry_timing.macd_hist_slope_turn(positive, config)["reason"] == \
        "HISTOGRAM_ALREADY_POSITIVE"


def test_the_crossover_lag_is_measured_rather_than_argued_about():
    """Every fired signal records how many sessions the crossover version would have waited."""
    config = default_config()["entry_timing_overlay"]["momentum_turn"]
    at_the_turn = macd_turn_path()

    reading = entry_timing.macd_hist_slope_turn(at_the_turn, config)
    assert reading["pass"] is True
    # No crossover yet on this path, which is itself the finding for this signal.
    assert reading["sessions_to_crossover"] is None

    # Carry the same path forward until the histogram climbs back through zero, and the lag
    # between the slope turn and the crossover becomes measurable.
    later = at_the_turn + [at_the_turn[-1] * 1.01 ** step for step in range(1, 25)]
    lag = entry_timing._sessions_to_crossover(macd_histogram(later, 12, 26, 9))

    assert lag is not None and lag > 0


def test_the_volume_gate_is_testable_on_its_own():
    """O-2 exists because Gervais-Kaniel-Mingelgrin is the one Tier-1 result at this horizon."""
    declared = entry_timing.REGISTERED_VARIANTS["O-2"]

    assert declared["momentum_mode"] == "off"
    assert declared["volume_gate"] is True
    assert declared["trend_gate"] is True


def test_a_quiet_name_is_deferred_by_the_volume_gate():
    quiet = {"closes": [100 * 1.004 ** index for index in range(200)],
             "volumes": [1_000_000.0] * 200}

    overlaid = apply_overlay([{"ticker": "QUIET"}], lambda ticker: quiet,
                             config_for_variant("O-2"), freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == DEFER
    assert overlaid[0]["entry_reason"] == "RVOL_BELOW_THRESHOLD"


# ---------------------------------------------------------------------------
# Deferral
# ---------------------------------------------------------------------------

def test_a_failed_momentum_turn_defers_rather_than_rejects():
    quiet = {"closes": [100 * 1.004 ** index for index in range(200)],
             "volumes": [1_000_000.0] * 199 + [4_000_000.0]}

    overlaid = apply_overlay([{"ticker": "STEADY"}], lambda ticker: quiet,
                             config_for_variant("O-3"), freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == DEFER
    assert overlaid[0]["sessions_deferred"] == 1


def test_the_defer_budget_is_finite():
    quiet = {"closes": [100 * 1.004 ** index for index in range(200)],
             "volumes": [1_000_000.0] * 199 + [4_000_000.0]}
    deferrals = {"STEADY": {"sessions_deferred": 3}}

    overlaid = apply_overlay([{"ticker": "STEADY"}], lambda ticker: quiet,
                             config_for_variant("O-3"), deferrals=deferrals,
                             freeze_path=FREEZE)

    assert overlaid[0]["entry_state"] == REJECT
    assert overlaid[0]["entry_reason"] == "DEFER_BUDGET_EXHAUSTED"


def test_a_deferral_records_what_entering_immediately_would_have_returned():
    """The core measurement: does waiting help, or does it cost the first three days?"""
    record = track_deferral("AAA", deferred_at_close=100.0, entered_at_close=104.0,
                            immediate_forward_return_pct=8.0,
                            deferred_forward_return_pct=3.0, sessions_deferred=2)

    assert record["price_drift_while_waiting_pct"] == pytest.approx(4.0)
    # Waiting cost five points of forward return on this name, and the sign says so.
    assert record["deferral_benefit_pct"] == pytest.approx(-5.0)


def test_the_deferral_counterfactual_is_reported_as_a_distribution():
    """A mean cannot tell a filter that clips disasters from one that misses the tail."""
    deferrals = [track_deferral(f"T{index}", deferred_at_close=100.0, entered_at_close=101.0,
                                immediate_forward_return_pct=value,
                                deferred_forward_return_pct=1.0, sessions_deferred=2)
                 for index, value in enumerate([-20, -8, -3, 0, 1, 2, 3, 4, 9, 30])]

    distribution = deferral_distribution(deferrals)

    assert distribution["measured"] == 10
    assert set(distribution["deciles"]) == {f"p{value}" for value in range(10, 100, 10)}
    assert distribution["worst"] < distribution["best"]
    assert 0 < distribution["share_where_waiting_helped"] < 1
    # The mean is present but it is not the headline, and the reading says so out loud.
    assert "share_where_waiting_helped is the headline" in distribution["reading"]


def test_gate_pass_rates_are_logged():
    """A gate that passes everything is not filtering and a reader has to be able to see that."""
    rows = [{"ticker": "RISING"}, {"ticker": "FALLING"}]
    series = {"RISING": rising_series(), "FALLING": falling_series()}

    overlaid = apply_overlay(rows, lambda ticker: series[ticker],
                             config_for_variant("O-1"), freeze_path=FREEZE)
    rates = gate_pass_rates(overlaid)

    assert rates["gates"]["trend_gate"]["evaluated"] == 2
    assert rates["gates"]["trend_gate"]["pass_rate"] == 0.5
    assert rates["entry_states"][ENTER_NOW] == 1
    assert rates["entry_states"][REJECT] == 1
