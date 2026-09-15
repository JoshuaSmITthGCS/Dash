"""Point-in-time capture of the Pre-breakout screen's composite and its 11 standardized
subfactors, for future rank-IC and per-metric attribution validation.

The 3-leg, 11-subfactor composite (``pre_breakout_signals.py``) already publishes each
subfactor's standardized, sign-adjusted z-score on every row (``sub_scores[leg]["subfactor_z"]``,
see that module's ``_score_row``) - this just writes it down before it can drift, one row per
(ticker, date), so ``validation/pre_breakout_ic.py`` can grade the composite and every
subfactor exactly as they were published that day.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively - a row missing its composite or price simply contributes
no observation.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "pre_breakout_pit_store")
FIRST_SEEN_FILENAME = "top10.json"


def build_rows(results, *, recorded_at=None):
    """``results`` is ``screens/pre-breakout.json``'s own published rows (``to_result()``'s
    output) - the exact composite_z and sub_scores the screen showed, not a recomputation.
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
        for leg_detail in (candidate.get("sub_scores") or {}).values():
            row.update((leg_detail.get("subfactor_z") or {}))
        rows.append(row)
    return rows


def append_snapshot(results, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``pre_breakout_pit_store/YYYY-MM-DD.jsonl``, replacing any
    snapshot already recorded for the same UTC date.
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
    LOG.info(f"pre_breakout_pit_store: recorded {len(built)} ticker row(s) for "
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


def _first_seen_path(store_dir=None):
    return os.path.join(store_dir or STORE_DIR, FIRST_SEEN_FILENAME)


def load_first_seen(store_dir=None):
    """Ticker -> {date_predicted, price_at_prediction} for every name currently in the
    pre-breakout screen's top 10."""
    path = _first_seen_path(store_dir)
    if not os.path.exists(path):
        return {}
    with open(path) as handle:
        return json.load(handle)


def update_first_seen(results, *, recorded_at=None, store_dir=None, top_n=10):
    """Eviction-based top-10 membership, unlike swing_pit_store's permanent record: an entry
    is kept while a ticker's rank stays <= ``top_n`` (rank moving around within the top 10 is
    fine and does not reset it), and removed the moment it falls outside ``top_n``. Re-entering
    later starts a fresh clock rather than resuming the old one.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    existing = load_first_seen(store_dir)
    current = {row["ticker"]: row for row in (results or [])
              if row.get("ticker") and row.get("rank") is not None
              and row["rank"] <= top_n and row.get("price")}
    changed = False
    for ticker in [*existing]:
        if ticker not in current:
            del existing[ticker]
            changed = True
    for ticker, row in current.items():
        if ticker not in existing:
            existing[ticker] = {"date_predicted": recorded_at.date().isoformat(),
                                "price_at_prediction": row["price"]}
            changed = True
    if changed:
        store_dir = store_dir or STORE_DIR
        os.makedirs(store_dir, exist_ok=True)
        with open(_first_seen_path(store_dir), "w") as handle:
            json.dump(existing, handle, sort_keys=True, indent=2)
    return existing
