"""Tests for pipeline/market_regime.py: breadth, the Hurst-exponent trend/mean-reversion
read, the VIX-regime passthrough, and the combined regime_gate() used by build_swing_screen.

Everything here is descriptive context for the swing screen's tier-agnostic regime banner -
never a scoring leg, never an eligibility gate. See MARKET_REGIME_EVIDENCE/REGIME_GATE_NOTE.
"""
import random

import market_regime


# ---------------------------------------------------------------------------
# breadth
# ---------------------------------------------------------------------------

def test_breadth_counts_names_above_their_own_moving_averages():
    above_both = {"closes": [100.0] * 199 + [200.0]}  # flat then a big pop: above both MAs
    below_both = {"closes": [200.0] * 199 + [100.0]}  # flat then a big drop: below both MAs
    entries = {"A": above_both, "B": below_both}

    result = market_regime.breadth(entries, as_of="2026-08-29")

    assert result["universe_count"] == 2
    assert result["above_50dma_pct"] == 50.0
    assert result["above_200dma_pct"] == 50.0
    assert result["as_of"] == "2026-08-29"


def test_breadth_is_none_on_an_empty_universe():
    assert market_regime.breadth({}) is None


def test_breadth_skips_a_ticker_with_no_resolvable_average():
    entries = {"THIN": {"closes": [100.0] * 10}}
    assert market_regime.breadth(entries) is None


# ---------------------------------------------------------------------------
# new_highs_new_lows
# ---------------------------------------------------------------------------

def test_new_highs_new_lows_counts_names_near_their_own_trailing_high_or_low():
    near_high = {"closes": [100.0 + index * 0.1 for index in range(252)]}  # steady climb: at its high
    near_low = {"closes": [200.0 - index * 0.1 for index in range(252)]}  # steady decline: at its low
    entries = {"A": near_high, "B": near_low}

    result = market_regime.new_highs_new_lows(entries, as_of="2026-08-29")

    assert result["universe_count"] == 2
    assert result["near_52w_high_pct"] == 50.0
    assert result["near_52w_low_pct"] == 50.0
    assert result["threshold_pct"] == market_regime.NEW_HIGH_LOW_THRESHOLD_PCT
    assert result["as_of"] == "2026-08-29"


def test_new_highs_new_lows_excludes_a_name_in_the_middle_of_its_range():
    midrange = [100.0] * 100 + [150.0] * 26 + [100.0] * 100 + [125.0] * 26  # oscillates, ends mid-range
    result = market_regime.new_highs_new_lows({"A": {"closes": midrange}})
    assert result["near_52w_high_pct"] == 0.0
    assert result["near_52w_low_pct"] == 0.0


def test_new_highs_new_lows_is_none_on_an_empty_universe():
    assert market_regime.new_highs_new_lows({}) is None


def test_new_highs_new_lows_skips_a_ticker_with_too_short_a_history():
    entries = {"THIN": {"closes": [100.0] * 10}}
    assert market_regime.new_highs_new_lows(entries) is None


# ---------------------------------------------------------------------------
# hurst_regime
# ---------------------------------------------------------------------------

def _trending_returns(count=260):
    # An AR(1) process with a high positive coefficient: each return is mostly last return
    # plus a small shock, the textbook persistent series - R/S analysis should read a Hurst
    # exponent meaningfully above 0.5. Seeded for a deterministic assertion.
    generator = random.Random(1)
    value, series = 0.0, []
    for _ in range(count):
        value = 0.98 * value + generator.gauss(0, 0.002)
        series.append(value)
    return series


def _mean_reverting_returns(count=260):
    # Strict alternation around zero - the canonical anti-persistent series, so R/S analysis
    # should read a Hurst exponent meaningfully below 0.5.
    return [0.01 if index % 2 == 0 else -0.01 for index in range(count)]


def test_hurst_regime_labels_a_persistent_drift_as_trending():
    result = market_regime.hurst_regime(_trending_returns())
    assert result is not None
    assert result["label"] == "trending"
    assert result["hurst"] > 0.55


def test_hurst_regime_labels_strict_alternation_as_mean_reverting():
    result = market_regime.hurst_regime(_mean_reverting_returns())
    assert result is not None
    assert result["label"] == "mean_reverting"
    assert result["hurst"] < 0.45


def test_hurst_regime_is_none_below_the_sample_floor():
    assert market_regime.hurst_regime([0.001] * 10) is None


def test_hurst_regime_is_none_on_empty_input():
    assert market_regime.hurst_regime([]) is None


# ---------------------------------------------------------------------------
# vix_regime
# ---------------------------------------------------------------------------

def test_vix_regime_passes_through_score_label_and_as_of_only():
    macro_regime = {"factors": {"volatility": {"score": 62.0, "label": "supportive",
                                                "as_of": "2026-08-28",
                                                "observations": [{"value": 14.2}]}}}

    result = market_regime.vix_regime(macro_regime)

    assert result == {"score": 62.0, "label": "supportive", "as_of": "2026-08-28"}
    assert "observations" not in result


def test_vix_regime_is_none_when_the_volatility_factor_is_absent():
    assert market_regime.vix_regime({}) is None
    assert market_regime.vix_regime({"factors": {}}) is None
    assert market_regime.vix_regime(None) is None


# ---------------------------------------------------------------------------
# regime_gate - the combined read build_swing_screen.py publishes
# ---------------------------------------------------------------------------

def test_regime_gate_combines_breadth_hurst_and_vix_without_touching_raw_observations():
    universe = [{"ticker": "A", "is_etf": False}, {"ticker": "B", "is_etf": False},
               {"ticker": "ETF", "is_etf": True}]
    entries = {
        "A": {"closes": [100.0 + 0.05 * index for index in range(260)]},
        "B": {"closes": [200.0 + 0.05 * index for index in range(260)]},
        "ETF": {"closes": [50.0] * 260},
    }
    macro_regime = {"factors": {"volatility": {"score": 40.0, "label": "restrictive",
                                                "as_of": "2026-08-28",
                                                "observations": [{"value": 28.0}]}}}

    gate = market_regime.regime_gate(universe, macro_regime,
                                     entry_for=lambda ticker: entries.get(ticker))

    # The ETF is excluded from the breadth read, same as build_swing_screen's own build_rows.
    assert gate["breadth"]["universe_count"] == 2
    assert gate["new_highs_new_lows"]["universe_count"] == 2
    assert gate["hurst"] is not None
    assert gate["vix"] == {"score": 40.0, "label": "restrictive", "as_of": "2026-08-28"}
    assert "observations" not in gate["vix"]
    assert gate["evidence"] is market_regime.MARKET_REGIME_EVIDENCE
    assert gate["note"] == market_regime.REGIME_GATE_NOTE


def test_regime_gate_degrades_gracefully_with_no_universe_or_regime():
    gate = market_regime.regime_gate([], {}, entry_for=lambda ticker: None)
    assert gate["breadth"] is None
    assert gate["new_highs_new_lows"] is None
    assert gate["hurst"] is None
    assert gate["vix"] is None


def test_market_regime_evidence_carries_a_citation_for_every_entry():
    for name, entry in market_regime.MARKET_REGIME_EVIDENCE.items():
        for field in ("label", "horizon", "direction", "citation", "effect", "caveat"):
            assert entry.get(field), f"{name}.{field} is missing or empty"
