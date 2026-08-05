"""Isolated comparison report for the signal-correction challenger."""

import json
import math
import os
from datetime import datetime, timezone

from evaluation import pearson, rank


REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "signal_diff.json")
ISOLATED_VARIANTS = (
    "normalization", "short_horizon", "confidence_shrinkage", "modifier_recalibration",
    "challenger",
)


def _ranks(values):
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    return {ticker: index + 1 for index, (ticker, _) in enumerate(ordered)}


def _rank_correlation(rows, score_getter, exposure_getter):
    pairs = []
    for row in rows:
        score, exposure = score_getter(row), exposure_getter(row)
        if isinstance(score, (int, float)) and isinstance(exposure, (int, float)):
            pairs.append((score, exposure))
    if len(pairs) < 3:
        return None
    value = pearson(rank([pair[0] for pair in pairs]), rank([pair[1] for pair in pairs]))
    return None if value is None else round(value, 6)


def build_signal_report(rows, generated_at=None):
    """Show score and rank deltas for every edit in isolation and cumulatively."""
    comparable = [row for row in rows if isinstance(row.get("score"), (int, float))]
    champion_ranks = _ranks([(row["ticker"], row["score"]) for row in comparable])
    changes = {}
    for variant_name in ISOLATED_VARIANTS:
        available = [row for row in comparable
                     if isinstance(((row.get("score_variants") or {}).get(variant_name) or {}).get("score"),
                                   (int, float))]
        variant_ranks = _ranks([
            (row["ticker"], row["score_variants"][variant_name]["score"])
            for row in available
        ])
        changes[variant_name] = [{
            "ticker": row["ticker"],
            "sector": row.get("sector"),
            "champion_score": row["score"],
            "variant_score": row["score_variants"][variant_name]["score"],
            "score_delta": round(row["score_variants"][variant_name]["score"] - row["score"], 1),
            "champion_rank": champion_ranks[row["ticker"]],
            "variant_rank": variant_ranks[row["ticker"]],
            "rank_delta": champion_ranks[row["ticker"]] - variant_ranks[row["ticker"]],
        } for row in available]
        changes[variant_name].sort(key=lambda item: abs(item["rank_delta"]), reverse=True)

    champion_market_cap = _rank_correlation(
        comparable,
        lambda row: row.get("score"),
        lambda row: math.log(row["market_cap"]) if (row.get("market_cap") or 0) > 0 else None,
    )
    challenger_market_cap = _rank_correlation(
        comparable,
        lambda row: ((row.get("score_variants") or {}).get("challenger") or {}).get("score"),
        lambda row: math.log(row["market_cap"]) if (row.get("market_cap") or 0) > 0 else None,
    )
    champion_coverage = _rank_correlation(
        comparable, lambda row: row.get("score"), lambda row: row.get("analyst_count"),
    )
    challenger_coverage = _rank_correlation(
        comparable,
        lambda row: ((row.get("score_variants") or {}).get("challenger") or {}).get("score"),
        lambda row: row.get("analyst_count"),
    )
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "universe_count": len(comparable),
        "isolated_changes": changes,
        "rank_correlation": {
            "score_vs_log_market_cap": {
                "champion": champion_market_cap,
                "challenger": challenger_market_cap,
            },
            "score_vs_analyst_coverage": {
                "champion": champion_coverage,
                "challenger": challenger_coverage,
            },
        },
    }


def write_signal_report(rows, generated_at=None, path=REPORT_PATH):
    report = build_signal_report(rows, generated_at)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report
