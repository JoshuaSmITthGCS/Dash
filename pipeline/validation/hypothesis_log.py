"""An append-only, machine-readable record of every hypothesis this repository has tested.

The multiple-testing correction in deflated_sharpe.py takes a trial count as an input, and
that number decides whether an observed result is evidence or arithmetic. A trial count that
lives in someone's memory is a trial count that only ever goes down: the variants that did not
work are the easiest ones to forget, and forgetting them is what turns a deflated statistic
back into an undeflated one.

So the count is not remembered. Every hypothesis is written here with a timestamp when it is
registered, before it is run, and the file is append-only. Reading the count is a file read.
Auditing it is a diff.

    from validation.hypothesis_log import register, trial_count

    register(hypothesis_id="O-3", family="entry_timing_overlay",
             description="trend gate on, rsi_change momentum mode, volume gate on",
             registered_at="2026-08-12T00:00:00+00:00")
    trial_count(family="entry_timing_overlay")

A hypothesis registered twice is idempotent on its id, so a rerun of a registration script
does not inflate the count. A hypothesis whose definition changes needs a new id, which is the
same rule the freeze file applies to variants and for the same reason.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "hypothesis_log.jsonl")

REQUIRED_FIELDS = ("hypothesis_id", "family", "description", "registered_at")


def _read(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def entries(family=None, *, path=LOG_PATH):
    """Every registered hypothesis, optionally filtered to one family."""
    rows = _read(path)
    return [row for row in rows if family is None or row.get("family") == family]


def trial_count(family=None, *, path=LOG_PATH):
    """How many distinct hypotheses have been registered. The N a deflated statistic needs."""
    return len({row.get("hypothesis_id") for row in entries(family, path=path)
                if row.get("hypothesis_id")})


def is_registered(hypothesis_id, *, path=LOG_PATH):
    return any(row.get("hypothesis_id") == hypothesis_id for row in _read(path))


def register(*, hypothesis_id, family, description, registered_at, path=LOG_PATH, **extra):
    """Append one hypothesis. Idempotent on ``hypothesis_id``.

    ``registered_at`` is passed in rather than stamped here, so a registration script that
    writes several hypotheses records them under one deliberate timestamp and so a test can
    write a deterministic file. Registering a hypothesis after its results exist is exactly
    the failure this log prevents, and the timestamp is what makes that visible.
    """
    required = {"hypothesis_id": hypothesis_id, "family": family,
                "description": description, "registered_at": registered_at}
    missing = [field for field in REQUIRED_FIELDS if not required[field]]
    if missing:
        raise ValueError(f"a hypothesis needs {missing} before it can be registered")
    if is_registered(hypothesis_id, path=path):
        return {"status": "already_registered", "hypothesis_id": hypothesis_id}
    record = {"hypothesis_id": hypothesis_id, "family": family, "description": description,
              "registered_at": registered_at, **extra}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return {"status": "registered", **record}


def audit(*, path=LOG_PATH):
    """A summary a reviewer can read without opening the file.

    Reports the count per family and the count overall, which is the number every deflated
    statistic in this repository must be computed at. Duplicated ids are reported rather than
    silently collapsed, because a duplicate usually means two different hypotheses were given
    the same name and one of them is missing from the count.
    """
    rows = _read(path)
    families, seen, duplicates = {}, set(), []
    for row in rows:
        identifier = row.get("hypothesis_id")
        families.setdefault(row.get("family"), set()).add(identifier)
        if identifier in seen:
            duplicates.append(identifier)
        seen.add(identifier)
    return {
        "total_hypotheses": len(seen),
        "by_family": {family: len(ids) for family, ids in sorted(families.items())},
        "duplicate_registrations": sorted(set(duplicates)),
        "log": os.path.relpath(path, os.path.dirname(os.path.dirname(HERE))),
        "note": ("total_hypotheses is the trial count N for every deflated Sharpe ratio "
                 "computed in this repository. It is read from this file, never recalled."),
    }
