"""Append prospective production-versus-SPY sector weights on every data refresh.

Sector classifications and ETF look-through weights are current observations. They cannot be
backfilled into an old backtest without look-ahead, so this store begins at the first run and
remains append-only. ``signal_metrics.py`` reads it to publish active sector weights and their
dated history.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
DEFAULT_ADVISOR = REPO_ROOT / "public" / "data" / "advisor.json"
DEFAULT_ETFS = REPO_ROOT / "public" / "data" / "etfs.json"
DEFAULT_STORE = PIPELINE_DIR / "data" / "validation" / "sector_weight_history.jsonl"

SECTOR_ALIASES = {
    "basicmaterials": "basic_materials",
    "communicationservices": "communication_services",
    "consumercyclical": "consumer_cyclical",
    "consumerdefensive": "consumer_defensive",
    "financialservices": "financial_services",
    "realestate": "real_estate",
}


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def canonical_sector(value):
    compact = "".join(character for character in str(value or "").lower()
                      if character.isalnum())
    if not compact:
        return "unclassified"
    return SECTOR_ALIASES.get(compact, compact)


def _finite_weight(value):
    return (value is not None and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) >= 0)


def _complete_weights(weights):
    combined = {}
    for sector, value in (weights or {}).items():
        if _finite_weight(value):
            key = canonical_sector(sector)
            combined[key] = combined.get(key, 0.0) + float(value)
    total = sum(combined.values())
    if total < 1.0 - 1e-8:
        combined["unclassified"] = combined.get("unclassified", 0.0) + 1.0 - total
    return {key: round(value, 8) for key, value in sorted(combined.items())}


def _strategy_weights(advisor, limit=20):
    ranked = sorted(
        (row for row in advisor.get("research") or []
         if row.get("ticker") and _finite_weight(row.get("score"))),
        key=lambda row: float(row["score"]), reverse=True,
    )[:limit]
    if not ranked:
        return {}, 0.0, []
    weight = 1.0 / len(ranked)
    weights = {}
    holdings = []
    classified = 0.0
    for row in ranked:
        sector = canonical_sector(row.get("sector"))
        weights[sector] = weights.get(sector, 0.0) + weight
        if sector != "unclassified":
            classified += weight
        holdings.append({"ticker": row["ticker"], "sector": sector,
                         "weight": round(weight, 8)})
    return _complete_weights(weights), round(classified, 8), holdings


def _benchmark_weights(etfs, ticker="SPY"):
    row = next((item for item in etfs.get("etfs") or []
                if str(item.get("ticker") or "").upper() == ticker), None)
    if not row or not row.get("sector_weights"):
        return {}, 0.0
    raw = row["sector_weights"]
    coverage = sum(float(value) for value in raw.values() if _finite_weight(value))
    return _complete_weights(raw), round(min(coverage, 1.0), 8)


def build_snapshot(advisor, etfs, *, benchmark="SPY", recorded_at=None):
    strategy, strategy_coverage, holdings = _strategy_weights(advisor)
    benchmark_weights, benchmark_coverage = _benchmark_weights(etfs, benchmark)
    if not strategy:
        raise ValueError("advisor.json has no scoreable production holdings")
    if not benchmark_weights:
        raise ValueError(f"etfs.json has no {benchmark} sector look-through weights")
    sectors = sorted(set(strategy) | set(benchmark_weights))
    active = {sector: round(strategy.get(sector, 0.0)
                            - benchmark_weights.get(sector, 0.0), 8)
              for sector in sectors}
    advisor_at = advisor.get("generated_at")
    etfs_at = etfs.get("generated_at")
    recorded_at = recorded_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "as_of": advisor_at or etfs_at or recorded_at,
        "session_date": str(advisor_at or etfs_at or recorded_at)[:10],
        "recorded_at": recorded_at,
        "strategy": "production_shadow_equal_weight_top20",
        "benchmark": benchmark,
        "strategy_sector_weights": strategy,
        "benchmark_sector_weights": benchmark_weights,
        "active_sector_weights": active,
        "strategy_classified_weight": strategy_coverage,
        "benchmark_classified_weight": benchmark_coverage,
        "holdings": holdings,
        "source_generated_at": {"advisor": advisor_at, "etfs": etfs_at},
    }


def read_history(path=DEFAULT_STORE):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def append_snapshot(snapshot, path=DEFAULT_STORE):
    path = Path(path)
    history = read_history(path)
    source = snapshot.get("source_generated_at")
    if any(row.get("source_generated_at") == source for row in history):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--advisor", default=str(DEFAULT_ADVISOR))
    parser.add_argument("--etfs", default=str(DEFAULT_ETFS))
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    args = parser.parse_args(argv)
    snapshot = build_snapshot(_read_json(args.advisor), _read_json(args.etfs))
    appended = append_snapshot(snapshot, args.store)
    print(f"Sector weights: {'appended' if appended else 'already recorded'} "
          f"{snapshot['session_date']} ({len(snapshot['active_sector_weights'])} sectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
