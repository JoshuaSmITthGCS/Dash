"""Champion versus cross-sectional normalization comparison report."""

import json
import os
import statistics
from datetime import datetime, timezone

from common import LOG
from evaluation import pearson, rank


REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "normalization_diff.json")


def _ranks(rows, key):
    ordered = sorted(rows, key=lambda row: (-row[key], row.get("ticker", "")))
    return {row.get("ticker"): index + 1 for index, row in enumerate(ordered)}


def _sector_statistics(rows, key, minimum_count):
    grouped = {}
    for row in rows:
        sector = row.get("sector") or "Unclassified"
        grouped.setdefault(sector, []).append(row[key])
    return {
        sector: {
            "count": len(values),
            "mean": round(statistics.fmean(values), 3),
            "standard_deviation": round(statistics.pstdev(values), 3),
        }
        for sector, values in sorted(grouped.items())
        if len(values) >= minimum_count
    }


def build_normalization_report(rows, mover_limit, minimum_sector_count, generated_at=None):
    """Summarize rank movement and sector dispersion for the isolated normalization edit."""
    comparable = []
    for row in rows:
        challenger = ((row.get("score_variants") or {}).get("challenger") or {})
        if isinstance(row.get("score"), (int, float)) and isinstance(challenger.get("score"), (int, float)):
            comparable.append({**row, "challenger_score": challenger["score"]})
    champion_ranks = _ranks(comparable, "score")
    challenger_ranks = _ranks(comparable, "challenger_score")
    champion_statistics = _sector_statistics(comparable, "score", minimum_sector_count)
    challenger_statistics = _sector_statistics(comparable, "challenger_score", minimum_sector_count)
    champion_means = {sector: values["mean"] for sector, values in champion_statistics.items()}
    challenger_means = {sector: values["mean"] for sector, values in challenger_statistics.items()}
    champion_dispersion = statistics.pstdev(champion_means.values()) if len(champion_means) > 1 else 0.0
    challenger_dispersion = statistics.pstdev(challenger_means.values()) if len(challenger_means) > 1 else 0.0
    by_sector = {}
    for sector in champion_means:
        sector_rows = [row for row in comparable if (row.get("sector") or "Unclassified") == sector]
        by_sector[sector] = round(statistics.fmean(
            abs(row["challenger_score"] - row["score"]) for row in sector_rows
        ), 3)
    movers = []
    for row in comparable:
        ticker = row.get("ticker")
        challenger = row["score_variants"]["challenger"]
        movers.append({
            "ticker": ticker,
            "sector": row.get("sector") or "Unclassified",
            "champion_score": row["score"],
            "challenger_score": challenger["score"],
            "score_delta": round(challenger["score"] - row["score"], 1),
            "champion_rank": champion_ranks[ticker],
            "challenger_rank": challenger_ranks[ticker],
            "rank_delta": champion_ranks[ticker] - challenger_ranks[ticker],
            "reasons": challenger.get("largest_metric_changes", [])[:3],
        })
    movers.sort(key=lambda item: (abs(item["rank_delta"]), abs(item["score_delta"])), reverse=True)
    correlation = pearson(
        rank([row["score"] for row in comparable]),
        rank([row["challenger_score"] for row in comparable]),
    ) if len(comparable) >= 3 else None
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "comparison": "bands_champion_vs_cross_sectional_challenger",
        "universe_count": len(comparable),
        "spearman_rank_correlation": None if correlation is None else round(correlation, 6),
        "largest_rank_movers": movers[:mover_limit],
        "mean_absolute_score_change_by_sector": by_sector,
        "sector_mean_scores": {
            "champion": champion_means,
            "challenger": challenger_means,
        },
        "sector_score_statistics": {
            sector: {
                "champion": champion_statistics[sector],
                "challenger": challenger_statistics.get(sector),
            }
            for sector in champion_statistics
        },
        "sector_mean_dispersion": {
            "champion": round(champion_dispersion, 6),
            "challenger": round(challenger_dispersion, 6),
            "challenger_is_lower": challenger_dispersion < champion_dispersion,
        },
    }


def write_normalization_report(rows, mover_limit, minimum_sector_count, generated_at=None,
                               path=REPORT_PATH):
    report = build_normalization_report(rows, mover_limit, minimum_sector_count, generated_at)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    dispersion = report["sector_mean_dispersion"]
    LOG.info(
        "Sector mean score dispersion: bands "
        f"{dispersion['champion']:.3f}, cross-sectional {dispersion['challenger']:.3f}"
    )
    return report
