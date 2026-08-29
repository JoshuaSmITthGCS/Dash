"""Tests for validate_data.swing_context_signal_errors(): the structural guarantee that a
context-only signal published on screens/swing.json (see swing_signals.CONTEXT_SIGNAL_EVIDENCE
and market_regime.MARKET_REGIME_EVIDENCE) never appears as a declared weight or among a row's
scored legs. Mirrors theme_screen_errors's anti-hype guardrail pattern for a different screen.

Note: this module is validate_data.py, not the differently-named validation_framework.py that
pipeline/tests/test_validation_framework.py already covers - the two are unrelated modules.
"""
import json
import os

import pytest

import validate_data


def _write_swing_json(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(validate_data, "DATA_DIR", str(tmp_path))
    screens_dir = tmp_path / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)
    (screens_dir / "swing.json").write_text(json.dumps(payload))


def test_missing_file_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_data, "DATA_DIR", str(tmp_path))
    assert validate_data.swing_context_signal_errors() == []


def test_a_clean_payload_produces_no_errors(tmp_path, monkeypatch):
    _write_swing_json(tmp_path, monkeypatch, {
        "weights": {"pead_drift": .30, "short_term_reversal": .10},
        "tiers": {"F": {"weights": {"announcement_return": .50},
                       "results": [{"legs": {"announcement_return": {"z": 1.0}}}]}},
        "results": [{"legs": {"pead_drift": {"z": 0.5}}}],
        "regime_gate": {"vix": {"score": 40.0, "label": "restrictive", "as_of": "2026-08-28"}},
    })

    assert validate_data.swing_context_signal_errors() == []


def test_a_context_only_field_in_the_top_level_weights_is_caught(tmp_path, monkeypatch):
    _write_swing_json(tmp_path, monkeypatch, {
        "weights": {"pead_drift": .30, "chaikin_money_flow": .10},
        "results": [],
    })

    errors = validate_data.swing_context_signal_errors()

    assert len(errors) == 1
    assert "declared weights" in errors[0]


def test_a_context_only_field_among_a_rows_scored_legs_is_caught(tmp_path, monkeypatch):
    _write_swing_json(tmp_path, monkeypatch, {
        "weights": {"pead_drift": .30},
        "results": [{"legs": {"pead_drift": {"z": 0.5}, "vcp": {"z": 0.1}}}],
    })

    errors = validate_data.swing_context_signal_errors()

    assert len(errors) == 1
    assert "results.0" in errors[0]


def test_a_context_only_field_inside_a_tiers_weights_or_legs_is_caught(tmp_path, monkeypatch):
    _write_swing_json(tmp_path, monkeypatch, {
        "tiers": {
            "S": {"weights": {"pead_drift": .30, "weinstein_stage2": .05},
                  "results": [{"legs": {"pead_drift": {"z": 0.2},
                                        "sector_relative_strength": {"z": 0.1}}}]},
        },
    })

    errors = validate_data.swing_context_signal_errors()

    assert any("tiers.S:" in error and "declared weights" in error for error in errors)
    assert any("tiers.S.results.0" in error for error in errors)


def test_a_raw_vix_observation_in_the_regime_gate_is_caught(tmp_path, monkeypatch):
    _write_swing_json(tmp_path, monkeypatch, {
        "regime_gate": {"vix": {"score": 40.0, "observations": [{"value": 28.0}]}},
    })

    errors = validate_data.swing_context_signal_errors()

    assert len(errors) == 1
    assert "raw FRED observations" in errors[0]
