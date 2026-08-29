"""Tests for the swing screen's extended context layer: chaikin_money_flow, weinstein_stage2,
volatility_contraction_pattern (vcp) and sector_relative_strength.

All four are descriptive context, never a scoring leg - see swing_signals.CONTEXT_NOTE. The
contract test at the bottom pins that promise structurally, the same way
test_build_swing_screen.py::test_contraction_setup_is_never_a_declared_leg already pins it for
the older five-signal family.
"""
import math

import swing_signals
import swing_tiers
import validate_data


# ---------------------------------------------------------------------------
# chaikin_money_flow
# ---------------------------------------------------------------------------

def test_chaikin_money_flow_is_none_on_thin_history():
    assert swing_signals.chaikin_money_flow([101.0] * 10, [99.0] * 10, [100.0] * 10,
                                            [1_000_000.0] * 10) is None


def test_chaikin_money_flow_reads_positive_on_a_name_closing_at_its_highs():
    # Every session closes exactly at its own high: the money-flow multiplier is 1.0 on
    # every session, so CMF resolves to exactly 1.0 - the top of its bounded range.
    highs = [110.0] * 20
    lows = [100.0] * 20
    closes = list(highs)
    volumes = [1_000_000.0] * 20

    cmf = swing_signals.chaikin_money_flow(highs, lows, closes, volumes)

    assert cmf == {"cmf": 1.0, "accumulating": True}


def test_chaikin_money_flow_reads_negative_on_a_name_closing_at_its_lows():
    highs = [110.0] * 20
    lows = [100.0] * 20
    closes = list(lows)
    volumes = [1_000_000.0] * 20

    cmf = swing_signals.chaikin_money_flow(highs, lows, closes, volumes)

    assert cmf == {"cmf": -1.0, "accumulating": False}


def test_chaikin_money_flow_is_none_when_a_session_is_unresolvable():
    highs = [110.0] * 19 + [None]
    lows = [100.0] * 20
    closes = [105.0] * 20
    volumes = [1_000_000.0] * 20
    assert swing_signals.chaikin_money_flow(highs, lows, closes, volumes) is None


# ---------------------------------------------------------------------------
# weinstein_stage2
# ---------------------------------------------------------------------------

def test_weinstein_stage2_labels_a_rising_price_above_a_rising_average_as_stage_2():
    closes = [100.0 + index * 0.5 for index in range(200)]
    volumes = [1_000_000.0] * 195 + [2_000_000.0] * 5

    stage = swing_signals.weinstein_stage2(closes, volumes)

    assert stage["stage"] == "stage_2"
    assert stage["above_ma150"] is True
    assert stage["ma150_rising"] is True
    assert stage["volume_confirmed"] is True


def test_weinstein_stage2_labels_a_falling_price_below_a_falling_average_as_stage_4():
    closes = [300.0 - index * 0.5 for index in range(200)]
    volumes = [1_000_000.0] * 200

    stage = swing_signals.weinstein_stage2(closes, volumes)

    assert stage["stage"] == "stage_4"
    assert stage["above_ma150"] is False
    assert stage["ma150_rising"] is False


def test_weinstein_stage2_is_none_on_thin_history():
    assert swing_signals.weinstein_stage2([100.0] * 100, [1_000_000.0] * 100) is None


# ---------------------------------------------------------------------------
# volatility_contraction_pattern (vcp)
# ---------------------------------------------------------------------------

def _decaying_oscillation(count, start_amplitude=20.0, base=100.0, period=5):
    # Amplitude decays linearly toward zero as the series approaches "today" (the end of the
    # list), so any trailing BandWidth checkpoint is narrower than one further back -
    # deterministically "sequentially tightening" regardless of exact checkpoint spacing.
    closes = []
    for index in range(count):
        amplitude = start_amplitude * (1 - index / count)
        closes.append(base + amplitude * math.sin(2 * math.pi * index / period))
    return closes


def test_vcp_flags_sequential_tightening_on_a_decaying_volatility_series():
    closes = _decaying_oscillation(300)

    vcp = swing_signals.volatility_contraction_pattern(closes)

    assert vcp is not None
    assert vcp["sequentially_tightening"] is True
    assert vcp["contraction_count"] >= 2


def test_vcp_does_not_flag_tightening_on_constant_volatility():
    closes = [100.0 + 10 * math.sin(2 * math.pi * index / 5) for index in range(300)]

    vcp = swing_signals.volatility_contraction_pattern(closes)

    assert vcp is not None
    assert vcp["sequentially_tightening"] is False


def test_vcp_is_none_on_thin_history():
    assert swing_signals.volatility_contraction_pattern([100.0] * 50) is None


def test_vcp_is_folded_into_contraction_setup():
    closes = _decaying_oscillation(300)
    setup = swing_signals.contraction_setup(closes, [1_000_000.0] * 300)
    assert "vcp" in setup
    assert setup["vcp"]["sequentially_tightening"] is True


# ---------------------------------------------------------------------------
# sector_relative_strength
# ---------------------------------------------------------------------------

def _row(ticker, group, return_20d):
    return {"ticker": ticker, "peer_group": group, "factors": {"return_20d": return_20d}}


def test_sector_relative_strength_requires_a_minimum_peer_count():
    rows = [_row("A", "tech", 5.0), _row("B", "tech", 3.0), _row("C", "tech", 1.0)]
    result = swing_signals.sector_relative_strength(rows, minimum_peer_count=4)
    assert result["A"]["status"] == "unavailable"
    assert result["A"]["reason_code"] == "INSUFFICIENT_VALID_PEERS"
    assert result["A"]["peer_count"] == 2


def test_sector_relative_strength_is_leave_one_out_against_the_peer_median():
    rows = [_row("A", "tech", 10.0), _row("B", "tech", 2.0), _row("C", "tech", 4.0),
            _row("D", "tech", 6.0), _row("E", "tech", 8.0)]

    result = swing_signals.sector_relative_strength(rows, minimum_peer_count=4)

    # A's own return never enters its own peer benchmark: peers are B(2)/C(4)/D(6)/E(8),
    # median (4 + 6) / 2 = 5.0.
    assert result["A"]["status"] == "success"
    assert result["A"]["peer_count"] == 4
    assert result["A"]["peer_median"] == 5.0
    assert result["A"]["relative_strength"] == 5.0


def test_sector_relative_strength_never_benchmarks_a_different_peer_group():
    rows = [_row("A", "tech", 10.0), _row("B", "tech", 2.0), _row("C", "tech", 4.0),
            _row("D", "tech", 6.0), _row("Z", "energy", 100.0)]
    result = swing_signals.sector_relative_strength(rows, minimum_peer_count=4)
    # Only three tech peers besides A - Z's group never counts toward A's peer set.
    assert result["A"]["status"] == "unavailable"


def test_sector_relative_strength_is_none_when_the_rows_own_field_is_missing():
    rows = [_row("A", "tech", None), _row("B", "tech", 2.0), _row("C", "tech", 4.0),
            _row("D", "tech", 6.0), _row("E", "tech", 8.0)]
    result = swing_signals.sector_relative_strength(rows, minimum_peer_count=4)
    assert result["A"]["status"] == "success"
    assert result["A"]["relative_strength"] is None


# ---------------------------------------------------------------------------
# Contract: none of the new context signals is ever a declared, weighted leg
# ---------------------------------------------------------------------------

def test_new_context_fields_are_never_declared_legs():
    new_fields = {"chaikin_money_flow", "weinstein_stage2", "vcp", "sector_relative_strength"}

    assert new_fields.isdisjoint(swing_signals.SWING_WEIGHTS)
    assert new_fields.isdisjoint(swing_signals.SWING_SUBFACTORS)
    for tier in swing_tiers.TIER_ORDER:
        assert new_fields.isdisjoint(swing_tiers.TIER_SPECS[tier]["weights"])
    for subfactors in swing_signals.SWING_SUBFACTORS.values():
        for name, _ in subfactors:
            assert name not in new_fields

    # validate_data's structural guardrail has to know about every one of these fields too,
    # or a future leg addition could slip past swing_context_signal_errors unnoticed.
    assert new_fields <= validate_data.SWING_CONTEXT_ONLY_FIELDS


def test_new_context_signals_carry_evidence_with_a_citation():
    for name in ("chaikin_money_flow", "weinstein_stage2", "vcp", "sector_relative_strength"):
        entry = swing_signals.CONTEXT_SIGNAL_EVIDENCE[name]
        for field in ("label", "horizon", "direction", "citation", "effect", "caveat"):
            assert entry.get(field), f"{name}.{field} is missing or empty"
