"""Write the 2026-08-12 variants into the append-only hypothesis log.

Run once, before any of them produces a result. Idempotent, so rerunning it does not inflate
the trial count.

The eight hypotheses are the three reversal variants (swing-reversal-A/B/C) and the five
entry-timing overlay cells (O-0 through O-4). They are read out of
pipeline/validation/harness_freeze.json rather than restated here, so the log and the freeze
file cannot disagree about what was registered.

    python pipeline/validation/register_swing_v2_hypotheses.py
    python pipeline/validation/register_swing_v2_hypotheses.py --audit
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from hypothesis_log import LOG_PATH, audit, register  # noqa: E402

FREEZE_PATH = os.path.join(HERE, "harness_freeze.json")
REGISTERED_AT = "2026-08-12T00:00:00+00:00"


def hypotheses(freeze_path=FREEZE_PATH):
    with open(freeze_path, encoding="utf-8") as handle:
        freeze = json.load(handle)

    rows = []
    reversal = freeze.get("swing_reversal_variants") or {}
    for variant in reversal.get("variants") or []:
        rows.append({
            "hypothesis_id": variant["variant_id"],
            "family": "swing_reversal",
            "description": variant["definition"],
            "registered_at": reversal.get("registered_at", REGISTERED_AT),
            "is_frozen_baseline": variant.get("is_frozen_baseline", False),
            "clock_start": reversal.get("clock_start"),
            "source": "pipeline/validation/harness_freeze.json:swing_reversal_variants",
        })

    overlay = freeze.get("entry_timing_overlay") or {}
    for variant in overlay.get("variants") or []:
        rows.append({
            "hypothesis_id": variant["variant_id"],
            "family": "entry_timing_overlay",
            "description": variant["label"],
            "registered_at": overlay.get("registered_at", REGISTERED_AT),
            "trend_gate": variant["trend_gate"],
            "momentum_mode": variant["momentum_mode"],
            "volume_gate": variant["volume_gate"],
            "clock_start": overlay.get("clock_start"),
            "acceptance_rule": (overlay.get("acceptance_rule") or {}).get("rule"),
            "source": "pipeline/validation/harness_freeze.json:entry_timing_overlay",
        })
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true",
                        help="print the log summary and register nothing")
    parser.add_argument("--log", default=LOG_PATH)
    args = parser.parse_args(argv)

    if not args.audit:
        for row in hypotheses():
            register(path=args.log, **row)
    print(json.dumps(audit(path=args.log), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
