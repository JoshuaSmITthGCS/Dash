"""Point-in-time capture of theme-screen scores, for future rank-IC validation.

Wholly separate from ``pit_store.py``'s fundamentals tracking and from
``validation/ic_harness.py``'s champion/challenger snapshot store (``pipeline/pit_store/``,
imported there as ``raw_pit_store``): this module neither reads from nor writes into either of
those. It exists because nothing in the codebase today records a theme's exposure, opportunity,
or connectivity score anywhere durable enough to grade against a forward return - Phase 5 of the
structural-theme brief asks for exactly that, and this is where it starts.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively. There is no history before this file starts writing it - a
theme scored today cannot be graded against returns that predate today's run, which is why this
starts capturing now rather than waiting for the first validation request. See
``validation/theme_ic.py`` for what reads it back, once enough dated snapshots exist.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "theme_pit_store")


def build_rows(theme_screen, price_by_ticker=None, *, recorded_at=None, refresh_id=None):
    """One row per (ticker, theme) with an eligible score published this run.

    ``price_by_ticker`` carries each ticker's price at the time of this snapshot - the same
    start/end-price mechanic ``validation/ic_harness._forward_periods`` already uses to derive
    a forward return from two dated snapshots, rather than a separate price history lookup.
    """
    if not theme_screen or not theme_screen.get("themes"):
        return []
    recorded_at = recorded_at or datetime.now(timezone.utc)
    price_by_ticker = price_by_ticker or {}
    connectivity = theme_screen.get("connectivity") or {}
    per_theme = connectivity.get("per_theme") or {}
    conn_by_ticker = connectivity.get("by_ticker") or {}

    rows = []
    for theme in theme_screen["themes"]:
        theme_id = theme["id"]
        structural = (per_theme.get(theme_id) or {}).get("structural_rank") or {}
        for row in theme.get("rows") or []:
            ticker = row.get("ticker")
            if not ticker or row.get("theme_exposure_score") is None:
                continue
            conn = conn_by_ticker.get(ticker) or {}
            rows.append({
                "ticker": ticker,
                "theme_id": theme_id,
                "refresh_id": refresh_id,
                "recorded_at": recorded_at.isoformat(),
                "price": price_by_ticker.get(ticker),
                "theme_exposure_score": row.get("theme_exposure_score"),
                "opportunity_score": row.get("opportunity_score"),
                "eligible": row.get("eligible"),
                "connectivity_score": conn.get("connectivity_score"),
                "effective_theme_count": conn.get("effective_theme_count"),
                "structural_rank_composite": structural.get("composite_score"),
            })
    return rows


def append_snapshot(theme_screen, price_by_ticker=None, *, recorded_at=None, refresh_id=None,
                    store_dir=None):
    """Write today's rows to ``theme_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
    already recorded for the same UTC date - a second run on the same day is a re-run of the
    same observation, not a second one, the same one-file-per-day convention the rest of this
    codebase's point-in-time stores use.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    rows = build_rows(theme_screen, price_by_ticker, recorded_at=recorded_at, refresh_id=refresh_id)
    if not rows:
        return 0
    store_dir = store_dir or STORE_DIR
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{recorded_at.date().isoformat()}.jsonl")
    with open(path, "w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    LOG.info(f"theme_pit_store: recorded {len(rows)} (ticker, theme) row(s) for "
             f"{recorded_at.date().isoformat()}")
    return len(rows)


def snapshot_dates(store_dir=None):
    """Every UTC date this store holds a snapshot for, oldest first."""
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
