"""Point-in-time capture of the two Fast Growth screens' raw inputs, for future rank-IC
validation.

``src/lib/researchScreens.js``'s ``rankBreakoutInProgress`` and ``rankEmergingGrowth`` are
computed entirely client-side from fields already published on each research row
(``technical_detail``, ``fundamental_detail``, price history) - there is no server-side
"growth score" anywhere in this pipeline to snapshot. This module records the raw inputs
those two functions read, at the moment each refresh finalizes them, so
``validation/growth_ic.py`` can recompute both screens' scores for a past date exactly as they
were published that day and grade them against a forward return - the same discipline
``theme_pit_store.py`` established, applied to a screen that lives in the frontend rather than
in a Python scorer.

Same rules as every other point-in-time store here: append-only, one file per UTC date, never
reconstructed retroactively - a ticker not carrying the fields either screen needs on a given
day simply contributes no row for that day, not an imputed one.
"""

import json
import math
import os
from datetime import datetime, timezone

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "growth_pit_store")


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _volatility_contraction(closes):
    """(recent 10-day, longer 60-day) stdev of daily returns, mirroring
    ``rankEmergingGrowth``'s in-browser calculation over ``row.history.closes`` exactly, so the
    two never disagree about what "contracting" meant on a given day.
    """
    closes = [value for value in (closes or []) if _finite(value)]
    if len(closes) < 61:
        return None, None

    def daily_returns(series):
        return [series[i] / series[i - 1] - 1 for i in range(1, len(series)) if series[i - 1]]

    def stdev(values):
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5

    recent = stdev(daily_returns(closes[-11:]))
    longer = stdev(daily_returns(closes[-61:]))
    return recent, longer


def build_rows(rows, *, recorded_at=None):
    """One row per ticker with at least one of the two screens' price-behavior inputs present.

    ``rows`` is ``fetch_advisor.py``'s finalized ``research`` list (the whole scored universe,
    before it is split into published leaders and the lightweight ``screen_universe`` tail) -
    the same population ``FastGrowthScreen.jsx`` scans client-side.
    """
    recorded_at = recorded_at or datetime.now(timezone.utc)
    out = []
    for row in rows or []:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        technical = row.get("technical_detail") or {}
        fundamental = row.get("fundamental_detail") or {}
        price = row.get("price")
        return_5d = technical.get("return_5d")
        return_20d = technical.get("return_20d")
        if return_5d is None and return_20d is None and fundamental.get("revenue_growth") is None:
            continue
        recent_vol, longer_vol = _volatility_contraction((row.get("history") or {}).get("closes"))
        out.append({
            "ticker": ticker,
            "recorded_at": recorded_at.isoformat(),
            "price": price,
            "return_5d": return_5d,
            "return_20d": return_20d,
            "volume_ratio_60d": technical.get("volume_ratio_60d"),
            "revenue_growth": fundamental.get("revenue_growth"),
            "operating_margin_trend": fundamental.get("operating_margin_trend"),
            "relative_strength_20d": technical.get("relative_strength_20d"),
            "recent_vol_10d": recent_vol,
            "longer_vol_60d": longer_vol,
        })
    return out


def append_snapshot(rows, *, recorded_at=None, store_dir=None):
    """Write today's rows to ``growth_pit_store/YYYY-MM-DD.jsonl``, replacing any snapshot
    already recorded for the same UTC date - a second run on the same day is a re-run of the
    same observation, not a second one.
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
    LOG.info(f"growth_pit_store: recorded {len(built)} ticker row(s) for "
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
