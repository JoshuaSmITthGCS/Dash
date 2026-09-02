"""Point-in-time capture of the Short-term trades options screen's recommended positions, for
future realized-payoff validation.

Every recommended position already carries everything ``validation/options_ic.py`` needs to
grade it later (ticker, strategy, entry stock price, strike, premium, its own expiration date,
and the mechanism's standardized selection factors) - this just writes that down before it can
drift, exactly as ``screens/short-term-trades.json`` published it, so a later grading run reads
what was actually recommended rather than recomputing it from scratch.

Same discipline as every other point-in-time store here: append-only, one file per UTC date,
never reconstructed retroactively - a recommendation missing any of those fields simply
contributes no row.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "options_pit_store")


def build_rows(short_term_results, *, recorded_at=None):
    recorded_at = recorded_at or datetime.now(timezone.utc)
    rows = []
    for candidate in short_term_results or []:
        ticker = candidate.get("ticker")
        legs = candidate.get("legs") or []
        leg = legs[0] if legs else {}
        strike, premium = leg.get("strike"), leg.get("mid")
        score = candidate.get("score")
        entry_price = candidate.get("price")
        expiration = candidate.get("expiration")
        if not ticker or strike is None or premium is None or score is None \
                or not entry_price or not expiration:
            continue
        rows.append({
            "ticker": ticker,
            "recorded_at": recorded_at.isoformat(),
            "strategy": candidate.get("strategy"),
            "score": score,
            "entry_price": entry_price,
            "strike": strike,
            "premium": premium,
            "expiration": expiration,
            "days_to_expiration": candidate.get("days_to_expiration"),
            # Kept nested, not flattened onto the row: each mechanism (buy/sell_call/
            # sell_put) has its own field names and weights (see options_ic.py's
            # STRATEGY_WEIGHTS), so a factor like "liquidity" from one mechanism must never
            # be blended with another's in a mechanism-mixed attribution read.
            "factors": candidate.get("standardized_factors") or {},
        })
    return rows


def append_snapshot(short_term_results, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``options_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
    already recorded for the same UTC date.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    built = build_rows(short_term_results, recorded_at=recorded_at)
    if not built:
        return 0
    store_dir = store_dir or STORE_DIR
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{recorded_at.date().isoformat()}.jsonl")
    with open(path, "w") as handle:
        for row in built:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    LOG.info(f"options_pit_store: recorded {len(built)} position(s) for "
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


def all_rows(store_dir=None):
    """Every recorded position across every date, for a reader that grades by each row's own
    expiration rather than by (start, end) snapshot pairs.
    """
    return [row for date in snapshot_dates(store_dir) for row in load_snapshot(date, store_dir)]
