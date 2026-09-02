"""Point-in-time capture of the Quality-at-valuation-lows screen's quality composite and its
4 category inputs, for future rank-IC and per-metric attribution validation.

``build_quality_value_screen.py``'s own ``quality_score()`` blends the advisor engine's
already-published ``fundamental_categories`` (profitability, financial_health,
accounting_quality, capital_allocation) - fields ``fetch_advisor.py`` puts on every ``research``
row already, the same population ``growth_pit_store.py`` reads. This hooks into that same spot
rather than build_quality_value_screen.py's own run(): the four category scores this screen's
quality axis needs are available the moment the main score is finalized, before the
quality-value screen itself even runs, so there is no reason to wait for it or duplicate its
formula - the composite itself is recomputed at read time by ``evaluation.composite_score``,
the identical renormalized-weighted-mean ``quality_score()`` implements.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively - a ticker missing every category that day simply
contributes no row.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "quality_pit_store")

CATEGORIES = ("profitability", "financial_health", "accounting_quality", "capital_allocation")


def build_rows(rows, *, recorded_at=None):
    """``rows`` is ``fetch_advisor.py``'s finalized ``research`` list - the same population
    ``growth_pit_store.build_rows`` reads.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    out = []
    for row in rows or []:
        ticker = row.get("ticker")
        price = row.get("price")
        categories = row.get("fundamental_categories") or {}
        if not ticker or not price or row.get("is_etf"):
            continue
        present = {name: categories[name] for name in CATEGORIES
                  if isinstance(categories.get(name), (int, float))}
        if not present:
            continue
        out.append({"ticker": ticker, "recorded_at": recorded_at.isoformat(),
                   "price": price, **present})
    return out


def append_snapshot(rows, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``quality_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
    already recorded for the same UTC date.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    built = build_rows(rows, recorded_at=recorded_at)
    if not built:
        return 0
    store_dir = store_dir or STORE_DIR
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{recorded_at.date().isoformat()}.jsonl")
    with open(path, "w") as handle:
        for row in built:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    LOG.info(f"quality_pit_store: recorded {len(built)} ticker row(s) for "
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
