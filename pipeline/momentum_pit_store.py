"""Point-in-time capture of the Momentum screen's composite and its 5 standardized factors,
for future rank-IC and per-metric attribution validation.

``research_screens_v2.momentum_scores()`` already computes each factor's standardized,
correlation-capped ``standardized_factors`` value on every row - ``build_momentum_screen.py``
now publishes it (previously computed but never shipped). This just writes it down before it
can drift, one row per (ticker, date), so ``validation/momentum_ic.py`` can grade the
composite and every factor exactly as they were published that day.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively - a row missing its composite or price simply contributes
no observation.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "momentum_pit_store")


def build_rows(results, *, recorded_at=None):
    """``results`` is ``screens/momentum.json``'s own published rows (``to_result()``'s
    output) - the exact composite score and standardized_factors the screen showed.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    rows = []
    for candidate in results or []:
        ticker = candidate.get("ticker")
        score = candidate.get("score")
        price = candidate.get("price")
        if not ticker or score is None or not price:
            continue
        row = {"ticker": ticker, "recorded_at": recorded_at.isoformat(),
              "price": price, "score": score}
        row.update(candidate.get("standardized_factors") or {})
        rows.append(row)
    return rows


def append_snapshot(results, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``momentum_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
    already recorded for the same UTC date.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    built = build_rows(results, recorded_at=recorded_at)
    if not built:
        return 0
    store_dir = store_dir or STORE_DIR
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{recorded_at.date().isoformat()}.jsonl")
    with open(path, "w") as handle:
        for row in built:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    LOG.info(f"momentum_pit_store: recorded {len(built)} ticker row(s) for "
             f"{recorded_at.date().isoformat()}")
    return len(built)


def snapshot_dates(store_dir=None):
    store_dir = store_dir or STORE_DIR
    if not os.path.isdir(store_dir):
        return []
    return sorted(name[:-len(".jsonl")] for name in os.listdir(store_dir)
                  if name.endswith(".jsonl"))


def load_snapshot(date_str, store_dir=None):
    store_dir = store_dir or STORE_DIR
    path = os.path.join(store_dir, f"{date_str}.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as handle:
        return [json.loads(line) for line in handle if line.strip()]
