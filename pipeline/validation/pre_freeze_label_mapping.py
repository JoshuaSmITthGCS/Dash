"""Part 1 of the R11 pre-merge gate: trace harness_freeze.json's 8 pre-freeze trial-count
category labels to pipeline/experiment_registry.py's pre-freeze entries.

This is the question harness_freeze_evaluator.py's docstring explicitly left open: "Whether
experiment_registry.py's WO-1..C7 entries (dated 2026-08-07..10, before the freeze) overlap
with harness_freeze.json's other pre-freeze categories... could not be established from
either file's text." That module declined to guess rather than fabricate a reconciliation.
This module answers it the only defensible way available without an explicit run-id or commit
linking the two systems: a mechanical, re-runnable check of whether a pre-freeze registry
entry's own ``configuration`` names a file under the ``research/audit`` directory the label's
name points at. It is deliberately NOT a similarity match on hypothesis text or category --
that would be a second guess dressed up as determinism, exactly what harness_freeze_evaluator
refused to do.

``LABEL_AUDIT_DIRS`` is hand-declared once, from each label's own literal name (``r3`` ->
``round3``, ``survivorship_reconstruction_runs`` -> ``survivorship``, etc). It is data, read
by the check below, not inferred at runtime -- if harness_freeze.json ever gains or renames a
pre-freeze label, ``map_pre_freeze_labels_to_registry`` raises a ``KeyError`` rather than
silently skipping it.

Finding as of 2026-09-01 (see the dated addendum this module's output was written into,
``pipeline/validation/harness_freeze.json``'s
``trial_count_for_deflated_statistics.pre_freeze_label_registry_mapping_addendum_2026-09-01``):
none of the 14 pre-freeze-dated registry entries (WO-1..WO-5, A1-NEWS-NEUTRAL,
A3-FULL-UNIVERSE-ENRICHMENT, C1..C7) cite a ``research/audit/{round3,round4,round5,round6,
survivorship,preFreeze}`` path in their ``configuration``. All 8 labels come back UNMATCHED by
this check. This does NOT mean the underlying work is untraceable, only that it is not
traceable *to a registry entry* by config pointer -- two labels match audit-script content by
exact count at the file level (``backtest_variants_r5`` == 12 == the ``af_*`` VARIANTS in
``research/audit/round6/task5_dsr_pbo.py``; ``pre_freeze_construction_runs`` == 5 == the 5
variant branches in ``research/audit/preFreeze/preFreeze_backtests.py``), but neither of those
files is itself cited by any registry entry, so the match stops at the file, not the registry.
This module does not attempt to resolve that content-level correspondence programmatically --
see the addendum for that discussion in prose, and for the separately-flagged double-counting
risk around rank-buffer variants shared between the round3-6 audit scripts and the registry's
``C4-turnover-controls``/``C7-turnover-walkforward`` entries, which this module also does not
attempt to resolve.

Per the pre-merge gate's own instruction: this module and its addendum change no numbers in
``trial_count_for_deflated_statistics`` and no promotion-criteria constant. It is a
documentation/traceability exercise only.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(HERE)
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from experiment_registry import REGISTRY  # noqa: E402

FREEZE_PATH = os.path.join(HERE, "harness_freeze.json")

# Labels present in trial_count_for_deflated_statistics that are dated after the 2026-08-11
# freeze (frozen_at) -- the swing_reversal/entry_timing_overlay families registered 2026-08-12
# -- and are therefore out of scope for a *pre-freeze* mapping.
POST_FREEZE_LABELS = {
    "swing_reversal_variants_2026_08_12",
    "entry_timing_overlay_variants_2026_08_12",
}

# Summary/meta keys in trial_count_for_deflated_statistics that are not category labels.
NON_LABEL_KEYS = {
    "total_enumerated", "dsr_trial_count_used", "note",
    "pre_freeze_label_registry_mapping_addendum_2026-09-01",
}

# The research/audit directory each label's own name points at. Declared by hand from the
# label's literal name, not guessed from its content -- see the module docstring.
LABEL_AUDIT_DIRS = {
    "backtest_variants_r3": ("research/audit/round3",),
    "backtest_variants_r4": ("research/audit/round4",),
    "backtest_variants_r5": ("research/audit/round5", "research/audit/round6"),
    "turnover_control_sweep_pre_r3": ("research/audit/round3",),
    "scoring_variants": ("research/audit/round4", "research/audit/round5"),
    "regression_constructions": ("research/audit/round3", "research/audit/round4"),
    "survivorship_reconstruction_runs": ("research/audit/survivorship",),
    "pre_freeze_construction_runs": ("research/audit/preFreeze",),
}


def load_pre_freeze_harness_labels(freeze_path=FREEZE_PATH):
    """Return (labels dict, frozen_at) for the pre-freeze-dated labels currently in
    harness_freeze.json -- i.e. everything in trial_count_for_deflated_statistics except the
    summary/meta keys and the two 2026-08-12 (post-freeze) families."""
    with open(freeze_path, encoding="utf-8") as handle:
        freeze = json.load(handle)
    trial_counts = freeze["trial_count_for_deflated_statistics"]
    labels = {
        key: value
        for key, value in trial_counts.items()
        if key not in NON_LABEL_KEYS and key not in POST_FREEZE_LABELS
    }
    return labels, freeze["frozen_at"]


def _config_paths(entry):
    """Flatten an experiment_registry.py entry's configuration file/files/script fields into
    a list of path strings."""
    config = entry.get("configuration", {})
    paths = []
    for key in ("file", "files", "script"):
        value = config.get(key)
        if value is None:
            continue
        paths.extend(value if isinstance(value, list) else [value])
    return paths


def load_pre_freeze_registry_entries(frozen_at=None):
    """Registry entries declared strictly before frozen_at."""
    if frozen_at is None:
        _, frozen_at = load_pre_freeze_harness_labels()
    return [entry for entry in REGISTRY if entry["declared_at"] < frozen_at]


def map_pre_freeze_labels_to_registry():
    """Deterministic label -> registry mapping.

    A registry entry matches a label only when the entry's own configuration file/files/script
    field names a path under one of the research/audit directories LABEL_AUDIT_DIRS declares
    for that label. A label with no such entry comes back UNMATCHED -- never silently promoted
    to a match on hypothesis or category text similarity.

    Returns a list of dicts, one per pre-freeze label currently in harness_freeze.json, each
    with: label, harness_count, matched_registry_ids, confidence ("MATCHED" or "UNMATCHED").
    """
    labels, frozen_at = load_pre_freeze_harness_labels()
    registry_entries = load_pre_freeze_registry_entries(frozen_at)

    rows = []
    for label in sorted(labels):
        harness_count = labels[label]
        audit_dirs = LABEL_AUDIT_DIRS[label]
        matched_ids = [
            entry["id"]
            for entry in registry_entries
            if any(path.startswith(d) for path in _config_paths(entry) for d in audit_dirs)
        ]
        rows.append({
            "label": label,
            "harness_count": harness_count,
            "matched_registry_ids": matched_ids,
            "confidence": "MATCHED" if matched_ids else "UNMATCHED",
        })
    return rows


if __name__ == "__main__":
    for row in map_pre_freeze_labels_to_registry():
        print(f"{row['label']:35s} count={row['harness_count']:>3}  "
              f"{row['confidence']:9s} {row['matched_registry_ids']}")
