import math
from datetime import date

import catalyst_screen_signals as css


# ---------------- days_between ----------------

def test_days_between_computes_calendar_days_forward():
    assert css.days_between(date(2026, 9, 1), date(2026, 9, 15)) == 14


def test_days_between_accepts_iso_strings():
    assert css.days_between("2026-09-01", "2026-09-08") == 7


def test_days_between_none_without_a_target():
    assert css.days_between(date(2026, 9, 1), None) is None


# ---------------- straddle_expected_move_pct / iv_implied_move_pct ----------------

def test_straddle_expected_move_matches_the_brenner_subrahmanyam_identity():
    # A $10 straddle on a $100 stock: (10/100) * sqrt(2/pi) ~= 7.98%
    move = css.straddle_expected_move_pct(call_mid=6.0, put_mid=4.0, spot=100)
    assert math.isclose(move, 10 / 100 * math.sqrt(2 / math.pi) * 100, rel_tol=1e-9)


def test_straddle_expected_move_none_without_both_legs_or_spot():
    assert css.straddle_expected_move_pct(None, 4.0, 100) is None
    assert css.straddle_expected_move_pct(6.0, None, 100) is None
    assert css.straddle_expected_move_pct(6.0, 4.0, 0) is None


def test_iv_implied_move_matches_the_same_identity_at_one_year():
    # At dte=365, iv * sqrt(365/365) == iv itself.
    assert math.isclose(css.iv_implied_move_pct(0.30, 365), 30.0, rel_tol=1e-9)


def test_iv_implied_move_none_on_non_positive_inputs():
    assert css.iv_implied_move_pct(None, 10) is None
    assert css.iv_implied_move_pct(0.3, None) is None
    assert css.iv_implied_move_pct(0.0, 10) is None
    assert css.iv_implied_move_pct(0.3, 0) is None


# ---------------- event_isolated_expected_move_pct ----------------

def test_event_isolated_move_isolates_the_incremental_variance():
    # pre: 20% IV over 7 days: variance = 0.20^2 * 7/365
    # post: 40% IV over 10 days (spans earnings): variance = 0.40^2 * 10/365
    # isolated = post_variance - pre_variance, sqrt'd and expressed as a percent.
    pre_iv, pre_dte, post_iv, post_dte = 0.20, 7, 0.40, 10
    expected = math.sqrt((post_iv ** 2) * (post_dte / 365) - (pre_iv ** 2) * (pre_dte / 365)) * 100
    assert math.isclose(css.event_isolated_expected_move_pct(pre_iv, pre_dte, post_iv, post_dte),
                        expected, rel_tol=1e-9)


def test_event_isolated_move_none_when_post_is_not_longer_dated():
    assert css.event_isolated_expected_move_pct(0.30, 10, 0.30, 10) is None
    assert css.event_isolated_expected_move_pct(0.30, 14, 0.30, 7) is None


def test_event_isolated_move_none_when_isolated_variance_is_non_positive():
    # A post-expiry IV low enough that it prices LESS total variance than the pre-expiry
    # over its shorter window - the "event" expiry isn't actually pricing more risk.
    assert css.event_isolated_expected_move_pct(pre_iv=0.90, pre_dte=7, post_iv=0.10, post_dte=10) is None


def test_event_isolated_move_none_on_missing_or_non_positive_iv_inputs():
    assert css.event_isolated_expected_move_pct(None, 7, 0.4, 10) is None
    assert css.event_isolated_expected_move_pct(0.2, 7, None, 10) is None
    assert css.event_isolated_expected_move_pct(0.0, 7, 0.4, 10) is None
    assert css.event_isolated_expected_move_pct(0.2, 7, 0.0, 10) is None


# ---------------- meets_liquidity_floor ----------------

def test_meets_liquidity_floor_requires_the_configured_open_interest():
    liquid = {"open_interest": 600, "spread_pct": 0.05}
    thin = {"open_interest": 100, "spread_pct": 0.05}
    assert css.meets_liquidity_floor(liquid) is True
    assert css.meets_liquidity_floor(thin) is False


def test_meets_liquidity_floor_false_without_a_contract():
    assert css.meets_liquidity_floor(None) is False
    assert css.meets_liquidity_floor({}) is False


# ---------------- gate_reasons ----------------

def _row(**overrides):
    base = {"price": 20, "market_cap": 5e9, "median_dollar_volume_60d": 1e7,
           "days_to_earnings": 5, "expected_move_pct": 4.2}
    return {**base, **overrides}


def test_gate_reasons_clean_row_is_eligible():
    assert css.gate_reasons(_row()) == []


def test_gate_reasons_flags_missing_earnings_date():
    assert "NO_CONFIRMED_EARNINGS_DATE" in css.gate_reasons(_row(days_to_earnings=None))


def test_gate_reasons_flags_outside_the_catalyst_window():
    assert "OUTSIDE_CATALYST_WINDOW" in css.gate_reasons(_row(days_to_earnings=30))


def test_gate_reasons_flags_unresolved_expected_move():
    assert "EXPECTED_MOVE_UNRESOLVED" in css.gate_reasons(_row(expected_move_pct=None))


def test_gate_reasons_flags_price_cap_and_liquidity_floors():
    reasons = css.gate_reasons(_row(price=1, market_cap=1e6, median_dollar_volume_60d=1))
    assert "MINIMUM_PRICE" in reasons
    assert "MINIMUM_MARKET_CAP" in reasons
    assert "MINIMUM_LIQUIDITY" in reasons
