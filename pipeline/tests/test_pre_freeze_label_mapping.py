import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation.pre_freeze_label_mapping import (
    LABEL_AUDIT_DIRS, load_pre_freeze_harness_labels, map_pre_freeze_labels_to_registry)


def test_pre_freeze_label_registry_mapping():
    """R11 pre-merge gate, Part 1: the mapping table must be generated deterministically from
    the two source files (harness_freeze.json, experiment_registry.py), and no assertion here
    may silently treat "unmatched" as "matched"."""
    rows = map_pre_freeze_labels_to_registry()

    # Determinism: re-running against the same two committed source files must be byte-for-byte
    # reproducible -- this is a traceability exercise, not a one-off guess.
    assert rows == map_pre_freeze_labels_to_registry()

    labels, _ = load_pre_freeze_harness_labels()
    assert {row["label"] for row in rows} == set(labels), (
        "must cover exactly the pre-freeze labels currently in harness_freeze.json's "
        "trial_count_for_deflated_statistics -- no more, no fewer"
    )
    assert set(labels) == set(LABEL_AUDIT_DIRS), (
        "every pre-freeze label currently in the freeze file must have a declared audit-dir "
        "mapping; a label with none must fail loudly here, not be silently skipped"
    )

    for row in rows:
        assert row["harness_count"] == labels[row["label"]]
        if row["matched_registry_ids"]:
            assert row["confidence"] == "MATCHED"
        else:
            # The core guard the task asked for: an empty match list must never be reported
            # as anything but UNMATCHED.
            assert row["confidence"] == "UNMATCHED"

    # Regression snapshot of the independently-verified state as of 2026-09-01 (see the dated
    # addendum in harness_freeze.json and the module docstring): none of the 14 pre-freeze
    # experiment_registry.py entries (WO-1..WO-5, A1-NEWS-NEUTRAL, A3-FULL-UNIVERSE-ENRICHMENT,
    # C1..C7) cite a research/audit/{round3,round4,round5,round6,survivorship,preFreeze} path
    # in their configuration, so all 8 labels are UNMATCHED today. If a future registry entry
    # or freeze-file edit changes that, this assertion should fail -- update the addendum in
    # the same change rather than loosening this check.
    assert all(row["confidence"] == "UNMATCHED" for row in rows), (
        "expected all 8 pre-freeze labels to be UNMATCHED against the registry as of "
        "2026-09-01; if a real match now exists, update "
        "pre_freeze_label_registry_mapping_addendum_2026-09-01 in harness_freeze.json in the "
        "same change instead of relaxing this assertion"
    )


def test_post_freeze_labels_are_excluded_from_the_pre_freeze_mapping():
    labels, _ = load_pre_freeze_harness_labels()
    assert "swing_reversal_variants_2026_08_12" not in labels
    assert "entry_timing_overlay_variants_2026_08_12" not in labels


def test_pre_freeze_label_counts_match_the_committed_freeze_file():
    labels, _ = load_pre_freeze_harness_labels()
    assert labels == {
        "backtest_variants_r3": 5,
        "backtest_variants_r4": 3,
        "backtest_variants_r5": 12,
        "turnover_control_sweep_pre_r3": 4,
        "scoring_variants": 7,
        "regression_constructions": 4,
        "survivorship_reconstruction_runs": 2,
        "pre_freeze_construction_runs": 5,
    }
