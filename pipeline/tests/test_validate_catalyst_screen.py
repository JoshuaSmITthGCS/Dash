"""catalyst_screen_errors(): the semantic-invariant check that stands in for a dedicated
JSON Schema on screens/catalyst.json, matching pre_breakout_screen_errors' own precedent
(see test_validate_data.py). No disk I/O: monkeypatches the module's path constant to a
scratch file.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import validate_data as vd


def _row(ticker, days_to_earnings=5, expected_move_pct=4.2, eligibility=True, reason_codes=()):
    return {"ticker": ticker, "eligibility": eligibility, "days_to_earnings": days_to_earnings,
           "expected_move_pct": expected_move_pct, "reason_codes": list(reason_codes)}


def _screen(results, status="success", window=None):
    return {"status": status,
           "window": window or {"minimum_days_to_earnings": 0, "maximum_days_to_earnings": 14},
           "results": results}


def _write(tmp_path, screen):
    path = tmp_path / "catalyst.json"
    path.write_text(json.dumps(screen))
    return str(path)


def test_missing_file_reports_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", str(tmp_path / "does-not-exist.json"))
    assert vd.catalyst_screen_errors() == []


def test_an_unavailable_status_screen_is_not_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([], status="unavailable")))
    assert vd.catalyst_screen_errors() == []


def test_a_well_formed_screen_reports_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([_row("AAA"), _row("BBB")])))
    assert vd.catalyst_screen_errors() == []


def test_an_eligible_row_with_no_expected_move_is_flagged(tmp_path, monkeypatch):
    row = _row("AAA", expected_move_pct=None)
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([row])))

    errors = vd.catalyst_screen_errors()

    assert any("no resolved expected_move_pct" in error for error in errors)


def test_an_eligible_row_outside_the_declared_window_is_flagged(tmp_path, monkeypatch):
    row = _row("AAA", days_to_earnings=30)
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([row])))

    errors = vd.catalyst_screen_errors()

    assert any("outside the declared" in error for error in errors)


def test_an_eligible_row_with_reason_codes_is_flagged(tmp_path, monkeypatch):
    row = _row("AAA", reason_codes=["MINIMUM_PRICE"])
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([row])))

    errors = vd.catalyst_screen_errors()

    assert any("despite reason_codes" in error for error in errors)


def test_an_ineligible_row_with_no_expected_move_is_not_flagged(tmp_path, monkeypatch):
    """The gate decides eligibility, not publication - a row correctly marked ineligible for
    an unresolved expected move is not itself a data error."""
    row = _row("AAA", expected_move_pct=None, eligibility=False,
              reason_codes=["EXPECTED_MOVE_UNRESOLVED"])
    monkeypatch.setattr(vd, "CATALYST_SCREEN_PATH", _write(tmp_path, _screen([row])))

    assert vd.catalyst_screen_errors() == []
