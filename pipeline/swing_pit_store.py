"""Point-in-time capture of the Swing screen's composite and its 5 leg z-scores, for future
per-metric attribution validation.

Separate from ``shadow_portfolios.py``'s ``shadow_store/swing/`` (which ``validation/swing_ic.py``
already reads for the composite's own rank IC): that store only carries the equal-weight
basket's ``signal``/price/rank, not the leg breakdown, because it exists to price a tradable
selection, not to explain one. ``build_swing_screen.py``'s ``to_result()`` already publishes
each leg's standardized z (``legs[leg]["z"]``) on every row - this just writes that down
before it can drift, one row per (ticker, date), so
``validation/swing_attribution_ic.py`` can grade every leg's own predictive power and marginal
impact on the composite exactly as they were published that day.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively - a row missing its composite or price simply contributes
no observation.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "swing_pit_store")


def build_rows(results, *, recorded_at=None):
    """``results`` is ``screens/swing.json``'s own published rows (the single-book screen's
    ``to_result()`` output, not a horizon tier) - the exact composite_z and leg z's the
    screen showed.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    rows = []
    for candidate in results or []:
        ticker = candidate.get("ticker")
        composite_z = candidate.get("composite_z")
        price = candidate.get("price")
        if not ticker or composite_z is None or not price:
            continue
        row = {"ticker": ticker, "recorded_at": recorded_at.isoformat(),
              "price": price, "composite_z": composite_z}
        for leg, detail in (candidate.get("legs") or {}).items():
            if detail.get("z") is not None:
                row[leg] = detail["z"]
        rows.append(row)
    return rows


def append_snapshot(results, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``swing_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
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
    LOG.info(f"swing_pit_store: recorded {len(built)} ticker row(s) for "
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
