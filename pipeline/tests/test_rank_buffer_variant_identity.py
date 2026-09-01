import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation.rank_buffer_variant_identity import (
    RECOMMENDATION, VERDICTS, check_rank_buffer_variant_identity,
    illustrative_deflated_sharpe_at_trial_counts, remediation_rank_buffer_1_5,
    round6_restated_buffer_150_cagr)


def test_rank_buffer_variant_identity_check():
    """R11 pre-merge gate, Stage 1b: the identity check must return an explicit three-way
    verdict per pair -- confirmed_duplicate / confirmed_distinct / ambiguous -- never a bare
    boolean, and must be reproducible from the two committed evidence sources."""
    rows = check_rank_buffer_variant_identity()

    assert rows == check_rank_buffer_variant_identity(), "must be deterministic"
    assert len(rows) == 2
    assert {row["pair"] for row in rows} == {
        "C4-turnover-controls vs round5/6 restated-buffer-1.5",
        "C7-turnover-walkforward vs round5/6 restated-buffer-1.5",
    }

    for row in rows:
        # The core guard the task asked for: verdict must always be one of the three named
        # outcomes, never True/False/None standing in for one of them.
        assert row["verdict"] in VERDICTS
        assert isinstance(row["verdict"], str)
        assert row["evidence"], "every verdict must carry the numeric/metadata evidence behind it"

    by_id = {row["registry_id"]: row for row in rows}

    # Regression snapshot of the independently-verified evidence as of 2026-09-01: C4's
    # buffer15_cagr (0.1233, 360-symbol cache) does not match the round5/6 trial's CAGR
    # (0.1260, 880-name universe) -- confirmed_distinct. C7 never published a raw CAGR to
    # compare -- ambiguous. Neither is a confirmed duplicate today. If this ever changes (a
    # future re-run makes C7's CAGR exactly 0.1260, or C4's committed metrics are edited to
    # match), this assertion should fail -- update RECOMMENDATION and the harness_freeze.json
    # addendum in the same change rather than loosening this check.
    assert by_id["C4-turnover-controls"]["verdict"] == "confirmed_distinct"
    assert by_id["C7-turnover-walkforward"]["verdict"] == "ambiguous"

    # No confirmed duplicate exists, so the recommendation must not silently apply a
    # correction -- the task explicitly forbids touching dsr_trial_count_used from this check.
    assert "no correction" in RECOMMENDATION
    assert "50" in RECOMMENDATION


def test_identity_evidence_sources_agree_before_use():
    """The check's own internal consistency guard: round6/task4_netcost.py's hard-coded CAGR
    and remediation/before_after.json's rank_buffer_1_5 CAGR must still match exactly before
    either is trusted as the round5/6 trial's identity fingerprint."""
    assert round6_restated_buffer_150_cagr() == remediation_rank_buffer_1_5()["cagr"]


def test_illustrative_deflated_sharpe_is_monotonically_decreasing_in_trial_count():
    """Reference-only sanity check on the illustrative sensitivity figure: deflated Sharpe
    probability must fall as the trial count rises, holding the same synthetic return series
    fixed -- more trials searched means a higher bar to clear, never a lower one."""
    values = illustrative_deflated_sharpe_at_trial_counts([41, 50, 57, 59])
    ordered = [values[t] for t in sorted(values)]
    assert ordered == sorted(ordered, reverse=True)
