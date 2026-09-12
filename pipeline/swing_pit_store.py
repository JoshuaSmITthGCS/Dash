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
FIRST_SEEN_FILENAME = "first_top10.json"

# The date the track-record feature shipped. Daily snapshots dated before this already existed
# as this module's own composite/leg log, from the single-book composite the horizon tiers
# replaced - real, previously-published numbers, not reconstructed ones - so they seed
# first_top10.json once, tagged "legacy" so a sighting there is never confused with a sighting
# in one of the three current tiers. A fixed constant rather than "before today": append_snapshot
# keeps writing a new dated file every day after launch too, and without a fixed cutoff this
# backfill would silently re-scope itself to "every day so far" forever instead of the ~1.5
# weeks of real history that predates the feature.
LEGACY_BACKFILL_CUTOFF = "2026-09-12"


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


def _first_seen_path(store_dir=None):
    return os.path.join(store_dir or STORE_DIR, FIRST_SEEN_FILENAME)


def load_first_seen(store_dir=None):
    """Ticker -> {date_predicted, tier, price_at_prediction} for every name that has ever
    ranked top 10 in a horizon tier, or (``tier: "legacy"``) in the pre-launch single-book
    composite - see LEGACY_BACKFILL_CUTOFF. Written once per ticker and never overwritten
    after - the "date predicted" this backs is the first time it happened, not the most recent.
    """
    path = _first_seen_path(store_dir)
    if not os.path.exists(path):
        return {}
    with open(path) as handle:
        return json.load(handle)


def _legacy_backfill(store_dir=None, top_n=10):
    """First-seen entries recoverable from the daily composite log dated before this feature
    shipped (see LEGACY_BACKFILL_CUTOFF) - the single-book composite's real, already-published
    composite_z and price, sorted into that day's top ``top_n``. A ticker's earliest qualifying
    date wins, the same rule the live per-tier path uses.
    """
    backfilled = {}
    for date in snapshot_dates(store_dir):
        if date >= LEGACY_BACKFILL_CUTOFF:
            break
        ranked = sorted(
            (row for row in load_snapshot(date, store_dir)
             if row.get("ticker") and row.get("composite_z") is not None and row.get("price")),
            key=lambda row: row["composite_z"], reverse=True)
        for row in ranked[:top_n]:
            ticker = row["ticker"]
            if ticker not in backfilled:
                backfilled[ticker] = {"date_predicted": date, "tier": "legacy",
                                      "price_at_prediction": row["price"]}
    return backfilled


def update_first_seen(tier_results, *, recorded_at=None, store_dir=None, top_n=10):
    """Record, for every ticker ranking ``top_n`` today in any tier, the first time that ever
    happened - never today's, if one is already on file.

    ``tier_results`` is ``{tier: published_rows}`` for every horizon tier, already ranked. On
    the first call this also seeds the ~1.5 weeks of real history already on file from before
    this feature shipped (see _legacy_backfill) - never re-derived after that, since it is
    already on file and a later legacy-tagged date must never overwrite an earlier one.

    This reads and rewrites ``first_top10.json`` rather than scanning the daily jsonl
    snapshots ``append_snapshot`` writes on every call: the fact this needs is "was this
    ticker ever top_n before", which a small running file answers in O(new entrants) per run
    instead of rescanning years of per-ticker history every time the screen refreshes.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    existing = load_first_seen(store_dir)
    changed = False
    for ticker, entry in _legacy_backfill(store_dir, top_n).items():
        if ticker not in existing:
            existing[ticker] = entry
            changed = True
    for tier, rows in (tier_results or {}).items():
        for row in rows or []:
            ticker, rank, price = row.get("ticker"), row.get("rank"), row.get("price")
            if not ticker or rank is None or rank > top_n or not price or ticker in existing:
                continue
            existing[ticker] = {"date_predicted": recorded_at.date().isoformat(),
                                "tier": tier, "price_at_prediction": price}
            changed = True
    if changed:
        store_dir = store_dir or STORE_DIR
        os.makedirs(store_dir, exist_ok=True)
        with open(_first_seen_path(store_dir), "w") as handle:
            json.dump(existing, handle, sort_keys=True, indent=2)
    return existing
