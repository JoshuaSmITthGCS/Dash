"""Generate the normalization ground-truth and point-in-time coverage artifact."""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from common import load_json
from scorer import CrossSectionalNormalizer, SETTINGS, VALUATION_MULTIPLES
import pit_store


REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "normalization_audit.json")
VALIDATION_PIT_ROOT = os.path.join(os.path.dirname(__file__), "pit_store")


def _validation_pit_summary(root=VALIDATION_PIT_ROOT):
    files = []
    rows = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if not name.endswith((".jsonl", ".parquet")):
                continue
            path = os.path.join(root, name)
            files.append(path)
            if name.endswith(".jsonl"):
                with open(path) as handle:
                    for line in handle:
                        try:
                            rows.append(json.loads(line))
                        except ValueError:
                            continue
    refreshes = defaultdict(list)
    for row in rows:
        refreshes[row.get("refresh_id")].append(row)
    latest_id = max(
        refreshes,
        key=lambda key: max((row.get("recorded_at") or "") for row in refreshes[key]),
        default=None,
    )
    latest = refreshes.get(latest_id, [])
    return {
        "file_count": len(files),
        "total_row_count": len(rows),
        "refresh_count": len(refreshes),
        "latest_refresh_id": latest_id,
        "latest_refresh_row_count": len(latest),
        "latest_refresh_champion_score_count": sum(
            isinstance((row.get("scores") or {}).get("champion"), (int, float)) for row in latest
        ),
        "latest_refresh_challenger_score_count": sum(
            isinstance((row.get("scores") or {}).get("challenger"), (int, float)) for row in latest
        ),
        "latest_refresh_complete_metric_detail_count": sum(
            any(isinstance(value, (int, float)) for value in
                ((row.get("normalized_metric_scores") or {}).get("challenger") or {}).values())
            for row in latest
        ),
        "append_only_contract": True,
        "backfill_permitted": False,
    }


def build_normalization_audit(normalizer, payload=None, generated_at=None):
    config = (SETTINGS.get("challengers") or {}).get("cross_sectional_normalization", {})
    metrics = []
    configured = {
        metric
        for weights in SETTINGS["fundamentals"]["metric_weights"].values()
        for metric in weights
    }
    for metric in sorted(configured):
        distribution = normalizer.distributions.get(metric) or {}
        sector_counts = {
            sector: len(values)
            for sector, values in sorted((distribution.get("sector_values") or {}).items())
        }
        metrics.append({
            "metric": metric,
            "champion_resolution": "discrete_bands",
            "challenger_resolution": "cross_sectional_percentile",
            "challenger_status": "available" if distribution else "insufficient_universe",
            "direction": distribution.get("direction"),
            "percentile_universe_size": len(distribution.get("universe_values") or []),
            "sector_observation_counts": sector_counts,
            "normalization_pooling": "sector_with_universe_fallback",
            "sector_minimum_count": config["sector_minimum_count"],
            "eligible_sector_count": sum(
                count >= config["sector_minimum_count"] for count in sector_counts.values()
            ),
            "own_history_percentile_published": metric in VALUATION_MULTIPLES,
        })
    payload = payload or {}
    screen_symbols = {
        row.get("ticker")
        for row in [*(payload.get("research") or []), *(payload.get("screen_universe") or [])]
        if row.get("ticker")
    }
    portfolio_symbols = {
        row.get("ticker") for row in payload.get("portfolio_coverage") or [] if row.get("ticker")
    }
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "normalization_mode_exists": "normalization_mode" in SETTINGS,
        "normalization_mode": SETTINGS.get("normalization_mode"),
        "challenger_enabled": bool(config.get("enabled")),
        "challenger_normalization_mode": config.get("normalization_mode"),
        "all_configured_metrics_have_cross_sectional_challenger": all(
            row["challenger_resolution"] == "cross_sectional_percentile" for row in metrics
        ),
        "winsorization": {
            "lower_percentile": config["winsor_lower_percentile"],
            "upper_percentile": config["winsor_upper_percentile"],
        },
        "sector_policy": {
            "minimum_names_with_metric": config["sector_minimum_count"],
            "fallback": "full_universe",
        },
        "metrics": metrics,
        "point_in_time_store": {
            **_validation_pit_summary(),
            "required_screen_symbol_count": len(screen_symbols),
            "required_portfolio_symbol_count": len(portfolio_symbols),
            "required_combined_symbol_count": len(screen_symbols | portfolio_symbols),
            "watchlist_contract": "Server-supplied watchlist symbols join the refresh universe and are recorded prospectively. Browser-only local storage cannot be read by the scheduled pipeline.",
            "raw_observation_store": pit_store.depth(),
        },
    }


def write_normalization_audit(normalizer, payload=None, generated_at=None, path=REPORT_PATH):
    report = build_normalization_audit(normalizer, payload, generated_at)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report


def main():
    payload = load_json("advisor.json") or {}
    config = (SETTINGS.get("challengers") or {}).get("cross_sectional_normalization", {})
    snapshots = pit_store.latest_snapshots(payload.get("universe"))
    normalizer = CrossSectionalNormalizer(
        snapshots,
        config,
        pit_store.valuation_histories(
            years=config["own_history_years"],
            days_per_year=config["own_history_days_per_year"],
            metrics=VALUATION_MULTIPLES,
        ),
    )
    report = write_normalization_audit(normalizer, payload)
    print(json.dumps({
        "metrics": len(report["metrics"]),
        "pit_files": report["point_in_time_store"]["file_count"],
        "pit_rows": report["point_in_time_store"]["total_row_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
