"""Build the normalization challenger from checked-in point-in-time observations.

This command performs no provider calls. It is useful after a scoring-code change because
it fits on the broadest universe that was actually observed, then adds the challenger to
full published research rows without changing the production champion.
"""

from advisor_engine import (cross_sectional_challenger, normalized_metric_scores,
                            signal_correction_variants)
from common import load_json, save_json
from fetch_advisor import report_snapshot
from normalization_report import write_normalization_report
from normalization_audit import write_normalization_audit
from bias_report import write_bias_report
from signal_report import write_signal_report
from validation.ic_harness import read_snapshots, write_report as write_ic_report
from observability import diagnostics_payload
from explainability import attach_explainability, attribution_errors, build_score_history
import pit_store
from scorer import (CrossSectionalNormalizer, SETTINGS, VALUATION_MULTIPLES,
                    sector_percentile_ranks, valuation_score)


def main():
    payload = load_json("advisor.json") or {}
    payload["schema_version"] = SETTINGS["model"]["advisor_schema_version"]
    payload["model_version"] = SETTINGS["model"]["semantic_version"]
    config = (SETTINGS.get("challengers") or {}).get("cross_sectional_normalization", {})
    if not config.get("enabled"):
        raise SystemExit("cross-sectional normalization challenger is disabled")
    snapshots = pit_store.latest_snapshots(payload.get("universe"))
    if not snapshots:
        raise SystemExit("no point-in-time observations are available")
    normalizer = CrossSectionalNormalizer(
        snapshots,
        config,
        pit_store.valuation_histories(
            years=config["own_history_years"],
            days_per_year=config["own_history_days_per_year"],
            metrics=VALUATION_MULTIPLES,
        ),
    )
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
                    "data_coverage": row.get("data_coverage"),
                    "components": row.get("components"),
                    "fundamental_categories": row.get("fundamental_categories"),
                    "normalized_metric_scores": normalized_metric_scores(
                        row.get("fundamental_detail") or {}
                    ),
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
    bias = write_bias_report(
        payload.get("research") or [],
        payload.get("generated_at"),
    )
    audit = write_normalization_audit(normalizer, payload, payload.get("generated_at"))
    payload["normalization_distributions"] = {
        **normalizer.published_distributions(),
        "fit_source": "point_in_time_observations",
        "observed_universe_count": len(snapshots),
    }
    payload["normalization_comparison"] = comparison
    payload["normalization_audit"] = {
        "all_metrics_cross_sectional": audit["all_configured_metrics_have_cross_sectional_challenger"],
        "pit_file_count": audit["point_in_time_store"]["file_count"],
        "pit_row_count": audit["point_in_time_store"]["total_row_count"],
    }
    payload["bias_check"] = {
        "comparable_universe_count": bias["comparable_universe_count"],
        "market_cap_correlation_drop_passed": bias["market_cap_correlation_absolute_drop"]["passed"],
    }
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
    payload["methodology"]["position_risk"] = SETTINGS.get("position_risk", {})
    validation_report = write_ic_report()
    payload["validation_harness"] = {
        "snapshot_refreshes": validation_report["snapshot_refreshes"],
        "monthly_score_snapshots": validation_report["monthly_score_snapshots"],
        "champion_1m_status": validation_report["variants"]["champion"]["1M"]["status_message"],
        "challenger_1m_status": validation_report["variants"]["challenger"]["1M"]["status_message"],
    }
    score_history = build_score_history(read_snapshots())
    theme_by_ticker = (payload.get("theme_screen") or {}).get("by_ticker") or {}
    for collection in (payload.get("research", []), payload.get("portfolio_coverage", [])):
        for row in collection:
            row["theme_exposure"] = theme_by_ticker.get(row.get("ticker"), [])
            attach_explainability(row, score_history.get(row.get("ticker")))
    reconciliation_failures = attribution_errors(payload.get("research") or [])
    if reconciliation_failures:
        raise ValueError(f"Score attribution failed to reconcile: {reconciliation_failures[:5]}")
    save_json("score-history.json", {
        "schema_version": 1,
        "generated_at": payload.get("generated_at"),
        "minimum_months": SETTINGS["explainability"]["score_history_minimum_months"],
        "by_ticker": score_history,
    })
    save_json("advisor.json", payload)
    save_json("report.json", report_snapshot(payload))
    save_json("diagnostics.json", diagnostics_payload(payload))
    print(f"Published normalization challenger for {comparison['universe_count']} comparable rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
