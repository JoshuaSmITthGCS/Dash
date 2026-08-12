"""The documentation integrity gate.

A caveat trimmed for length, a hedge dropped from a summary, and three edits later a page
asserts a backtest nobody ran. These tests check the gate catches that, that it does not fire
on a document quoting a claim in order to deny it, and that the repository is currently clean.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import validate_documentation_claims as gate


def test_the_repository_currently_claims_nothing_it_cannot_support():
    report = gate.scan()

    assert report["ok"], report["unsupported_claims"]
    assert report["files_scanned"] > 0


def test_no_registered_result_files_exist_yet():
    """The correct state today: the prospective clock has not started."""
    assert gate.registered_results() == {}
    assert gate.scan()["state_of_the_evidence"]["prospective_clock_started"] is False


def test_a_claim_of_confirmed_replication_fails():
    text = "The swing composite successfully replicates the published Bernard-Thomas result."
    assert not gate.scan_text(text)     # "replicates" alone is not the claim pattern

    claimed = "Our replication is confirmed against the original sample."
    findings = gate.scan_text(claimed, source="report.md")
    assert [finding["claim"] for finding in findings] == ["CONFIRMED_REPLICATION"]


def test_a_claim_of_surviving_data_snooping_correction_fails():
    findings = gate.scan_text("The overlay survives the data-snooping correction.",
                              source="report.md")

    assert findings[0]["claim"] == "SURVIVED_DATA_SNOOPING"
    assert "deflated Sharpe" in findings[0]["would_require"]


def test_a_claim_of_matching_published_returns_fails():
    findings = gate.scan_text("Realized performance matches the published returns.",
                              source="report.md")

    assert findings[0]["claim"] == "MATCHED_PUBLISHED_RETURNS"


def test_a_claim_of_out_of_sample_validation_fails():
    findings = gate.scan_text("The model is validated out-of-sample.", source="report.md")

    assert findings[0]["claim"] == "VALIDATED_OUT_OF_SAMPLE"
    assert "2026-09-01" in findings[0]["would_require"]


def test_a_claim_that_a_backtest_proves_something_fails():
    findings = gate.scan_text("The backtest confirms the leg weights.", source="report.md")

    assert findings[0]["claim"] == "BACKTEST_PROVES"


def test_a_document_denying_the_claim_does_not_trip_the_gate():
    """A page explaining what it cannot say is the opposite of a page saying it."""
    honest = ("This model has no out-of-sample record. Nothing here is validated "
              "out-of-sample, and no backtest confirms these weights. Any artifact "
              "claiming otherwise is a bug.")

    assert gate.scan_text(honest, source="README.md") == []


def test_a_claim_is_supported_only_by_a_result_registered_for_that_claim(tmp_path):
    """One registered replication does not license a sentence about data snooping."""
    results = tmp_path / "results"
    results.mkdir()
    (results / "replication.json").write_text(json.dumps({
        "supports_claims": ["CONFIRMED_REPLICATION"],
        "registered_at": "2028-09-01T00:00:00+00:00",
    }), encoding="utf-8")

    supported = gate.registered_results(str(results))

    assert supported == {"CONFIRMED_REPLICATION": ["replication.json"]}
    assert "SURVIVED_DATA_SNOOPING" not in supported


def test_a_registered_result_lets_its_own_claim_through(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "report.md").write_text(
        "The strategy is validated out-of-sample over 24 periods.", encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    (results / "prospective.json").write_text(json.dumps({
        "supports_claims": ["VALIDATED_OUT_OF_SAMPLE"],
        "registered_at": "2028-09-01T00:00:00+00:00",
    }), encoding="utf-8")

    blocked = gate.scan(str(repo), paths=("docs",), results_dir=str(tmp_path / "missing"))
    allowed = gate.scan(str(repo), paths=("docs",), results_dir=str(results))

    assert blocked["ok"] is False
    assert allowed["ok"] is True
    assert allowed["claims_found"][0]["supported_by"] == ["prospective.json"]


def test_the_gate_exits_non_zero_when_a_document_overclaims(tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "summary.md").write_text(
        "Performance matches the published returns across the sample.", encoding="utf-8")

    report = gate.scan(str(repo), paths=("docs",), results_dir=str(tmp_path / "none"))

    assert report["ok"] is False
    assert report["unsupported_claims"][0]["source"] == os.path.join("docs", "summary.md")


def test_the_state_of_the_evidence_is_stated_in_one_place():
    text = gate.state_of_the_evidence_text()

    assert "no out-of-sample record" in text
    assert "2026-09-01" in text
    assert "before costs and before decay" in text
