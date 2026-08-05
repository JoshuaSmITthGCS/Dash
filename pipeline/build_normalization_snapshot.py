"""Build the normalization challenger from checked-in point-in-time observations.

This command performs no provider calls. It is useful after a scoring-code change because
it fits on the broadest universe that was actually observed, then adds the challenger to
full published research rows without changing the production champion.
"""

from advisor_engine import cross_sectional_challenger, signal_correction_variants
from common import load_json, save_json
from fetch_advisor import report_snapshot
from normalization_report import write_normalization_report
from signal_report import write_signal_report
from observability import diagnostics_payload
import pit_store
from scorer import (CrossSectionalNormalizer, SETTINGS, sector_percentile_ranks,
                    valuation_score)


def main():
    payload = load_json("advisor.json") or {}
    config = (SETTINGS.get("challengers") or {}).get("cross_sectional_normalization", {})
    if not config.get("enabled"):
        raise SystemExit("cross-sectional normalization challenger is disabled")
    snapshots = pit_store.latest_snapshots(payload.get("universe"))
    if not snapshots:
        raise SystemExit("no point-in-time observations are available")
    normalizer = CrossSectionalNormalizer(snapshots, config)
    signal_config = (SETTINGS.get("challengers") or {}).get("signal_corrections", {})
    short_interest_ranks = sector_percentile_ranks(
        snapshots,
        "short_percent_of_float",
        signal_config["short_interest_sector_minimum_count"],
    ) if signal_config.get("enabled") else {}
    by_ticker = {row["ticker"]: row for row in snapshots}
    for collection in (payload.get("research", []), payload.get("portfolio_coverage", [])):
        for row in collection:
            snapshot = {**by_ticker.get(row.get("ticker"), {}), **row}
            if not snapshot.get("ticker") or not row.get("components"):
                continue
            variants = {
                "champion": {
                    "variant": "bands_champion",
                    "normalization_mode": SETTINGS.get("normalization_mode", "bands"),
                    "score": row.get("score"),
                    "base_score": row.get("base_score"),
                    "confidence": row.get("confidence"),
                    "components": row.get("components"),
                    "fundamental_categories": row.get("fundamental_categories"),
                },
            }
            if signal_config.get("enabled"):
                variants.update(signal_correction_variants(
                    row,
                    snapshot,
                    normalizer,
                    signal_config,
                    short_interest_ranks.get(snapshot["ticker"]),
                    ((payload.get("market") or {}).get("macro") or {}).get("regime"),
                    row.get("insider_activity"),
                ))
            else:
                variants["challenger"] = cross_sectional_challenger(row, snapshot, normalizer)
            row["score_variants"] = variants
    comparison_rows = []
    for snapshot in snapshots:
        champion_score, champion_detail = valuation_score(snapshot, mode="bands")
        challenger_score, challenger_detail = valuation_score(
            snapshot, mode="cross_sectional", normalizer=normalizer,
        )
        if champion_score is None or challenger_score is None:
            continue
        metric_changes = sorted((
            {
                "metric": metric,
                "champion": champion_detail.get(metric),
                "challenger": value,
                "delta": round(value - champion_detail[metric], 1),
            }
            for metric, value in challenger_detail.items()
            if isinstance(value, (int, float))
            and isinstance(champion_detail.get(metric), (int, float))
            and metric not in {"coverage", "raw_score"}
        ), key=lambda item: abs(item["delta"]), reverse=True)
        comparison_rows.append({
            "ticker": snapshot["ticker"],
            "sector": snapshot.get("sector"),
            "score": champion_score,
            "score_variants": {"challenger": {
                "score": challenger_score,
                "largest_metric_changes": metric_changes[:5],
            }},
        })
    comparison = write_normalization_report(
        comparison_rows,
        config["largest_movers_count"],
        config["sector_minimum_count"],
        payload.get("generated_at"),
    )
    payload["normalization_distributions"] = {
        **normalizer.published_distributions(),
        "fit_source": "point_in_time_observations",
        "observed_universe_count": len(snapshots),
    }
    payload["normalization_comparison"] = comparison
    payload["signal_comparison"] = (
        write_signal_report(payload.get("research", []), payload.get("generated_at"))
        if signal_config.get("enabled") else None
    )
    payload.setdefault("methodology", {})["normalization"] = {
        "champion": SETTINGS.get("normalization_mode", "bands"),
        "challenger": config.get("normalization_mode"),
        "challenger_enabled": True,
    }
    payload["methodology"]["signal_corrections"] = {
        key: value for key, value in signal_config.items() if not key.startswith("_")
    }
    save_json("advisor.json", payload)
    save_json("report.json", report_snapshot(payload))
    save_json("diagnostics.json", diagnostics_payload(payload))
    print(f"Published normalization challenger for {comparison['universe_count']} comparable rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
