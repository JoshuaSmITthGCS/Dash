"""Eviction-aware top-10 membership tracking for the two Fast Growth screens (breakout in
progress, emerging growth).

Deliberately the opposite rule from swing_pit_store.update_first_seen, which keeps a
permanent, all-time "first ever seen" record. Here the question is "how has a name done since
it entered the CURRENT top-10 window" - so an entry is dropped the moment a ticker falls out
of the top 10, and re-entering later starts a fresh clock rather than resuming the old one.
Rank moving around *within* the top 10 after a refresh never resets it - only actually leaving
does, which is why this reads the ranked lists fresh every run rather than only reacting to a
newly-arrived ticker.

Both sub-screens are ranked by fast_growth_rank.py against report.json's own published rows -
the same rows and formulas the site itself renders - so membership here always matches what a
viewer actually sees, never a separately-derived approximation of it.
"""

import json
import os

from fast_growth_rank import rank_breakout_in_progress, rank_emerging_growth

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "growth_pit_store")
STORE_FILENAME = "track_record.json"
TOP_N = 10

# One ranker per published sub-screen key - add an entry here to track a third screen the same
# way, nothing else in this module is sub-screen-specific.
SUB_SCREENS = {
    "breakout": rank_breakout_in_progress,
    "emerging": rank_emerging_growth,
}


def _store_path(store_dir=None):
    return os.path.join(store_dir or STORE_DIR, STORE_FILENAME)


def load(store_dir=None):
    """``{"breakout": {ticker: {date_predicted, price_at_prediction}}, "emerging": {...}}``."""
    path = _store_path(store_dir)
    if not os.path.exists(path):
        return {sub: {} for sub in SUB_SCREENS}
    with open(path) as handle:
        raw = json.load(handle)
    return {sub: raw.get(sub) or {} for sub in SUB_SCREENS}


def update(rows, *, recorded_at_date, store_dir=None, top_n=TOP_N):
    """Re-rank both sub-screens against ``rows``, add an entry for anything newly in the top
    ``top_n``, and remove anything that fell out. ``rows`` is ``report.json``'s own published
    ``research`` rows - already the exact rows and shape a browser would rank. Returns the
    updated store, in the shape published as ``report.json``'s ``fast_growth_track_record``.
    """
    store = load(store_dir)
    changed = False
    for sub, ranker in SUB_SCREENS.items():
        current = {row["ticker"]: row for row in ranker(rows, limit=top_n)
                  if row.get("ticker") and row.get("price")}
        existing = store[sub]
        for ticker in [*existing]:
            if ticker not in current:
                del existing[ticker]
                changed = True
        for ticker, row in current.items():
            if ticker not in existing:
                existing[ticker] = {"date_predicted": recorded_at_date,
                                    "price_at_prediction": row["price"]}
                changed = True
    if changed:
        store_dir = store_dir or STORE_DIR
        os.makedirs(store_dir, exist_ok=True)
        with open(_store_path(store_dir), "w") as handle:
            json.dump(store, handle, sort_keys=True, indent=2)
    return store
