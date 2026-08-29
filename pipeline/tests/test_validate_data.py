"""pre_breakout_screen_errors(): the semantic-invariant check that stands in for a dedicated
JSON Schema on screens/pre-breakout.json, matching how theme_screen_errors covers the theme
screen. No disk I/O: monkeypatches the module's path constant to a scratch file.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import validate_data as vd


def _row(ticker, sub_scores=("fundamental_inflection", "momentum_rs", "flow_sentiment"),
        legs_resolved=3, eligibility=True):
    return {"ticker": ticker, "eligibility": eligibility, "legs_resolved": legs_resolved,
           "sub_scores": {leg: {"z": 0.5} for leg in sub_scores}}


def _screen(results, weights=None, status="success", thresholds=None):
    return {"status": status, "weights": weights or {"fundamental_inflection": 1 / 3,
                                                      "momentum_rs": 1 / 3, "flow_sentiment": 1 / 3},
           "thresholds": thresholds or {"minimum_legs_resolved": 2}, "results": results}


def _write(tmp_path, screen):
    path = tmp_path / "pre-breakout.json"
    path.write_text(json.dumps(screen))
    return str(path)


def test_missing_file_reports_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH", str(tmp_path / "does-not-exist.json"))
    assert vd.pre_breakout_screen_errors() == []


def test_an_unavailable_status_screen_is_not_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH",
                        _write(tmp_path, _screen([], status="unavailable")))
    assert vd.pre_breakout_screen_errors() == []


def test_a_well_formed_screen_reports_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH",
                        _write(tmp_path, _screen([_row("AAA"), _row("BBB")])))
    assert vd.pre_breakout_screen_errors() == []


def test_a_leg_weight_above_one_third_plus_epsilon_is_flagged(tmp_path, monkeypatch):
    weights = {"fundamental_inflection": 0.5, "momentum_rs": 0.25, "flow_sentiment": 0.25}
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH",
                        _write(tmp_path, _screen([_row("AAA")], weights=weights)))

    errors = vd.pre_breakout_screen_errors()

    assert any("fundamental_inflection" in error and "exceeds" in error for error in errors)


def test_a_row_missing_a_named_sub_score_is_flagged(tmp_path, monkeypatch):
    row = _row("AAA", sub_scores=("fundamental_inflection", "momentum_rs"))
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH", _write(tmp_path, _screen([row])))

    errors = vd.pre_breakout_screen_errors()

    assert any("missing sub_scores" in error and "flow_sentiment" in error for error in errors)


def test_an_eligible_row_below_the_minimum_legs_resolved_floor_is_flagged(tmp_path, monkeypatch):
    row = _row("AAA", legs_resolved=1, eligibility=True)
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH", _write(tmp_path, _screen([row])))

    errors = vd.pre_breakout_screen_errors()

    assert any("eligible despite resolving only" in error for error in errors)


def test_an_ineligible_thin_row_is_not_flagged(tmp_path, monkeypatch):
    """The floor gates eligibility, not publication -- a row correctly marked ineligible for
    resolving too few legs is not itself a data error."""
    row = _row("AAA", legs_resolved=1, eligibility=False)
    monkeypatch.setattr(vd, "PRE_BREAKOUT_SCREEN_PATH", _write(tmp_path, _screen([row])))

    assert vd.pre_breakout_screen_errors() == []
