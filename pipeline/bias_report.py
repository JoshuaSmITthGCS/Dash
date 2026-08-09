"""Score-bias evidence for the legacy and single-shrinkage challenger paths."""

import json
import math
import os
from datetime import datetime, timezone

from evaluation import pearson, rank


REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "bias_check.json")


def _correlations(rows, score_getter, exposure_getter):
    pairs = []
    for row in rows:
        score = score_getter(row)
        exposure = exposure_getter(row)
        if isinstance(score, (int, float)) and isinstance(exposure, (int, float)):
            pairs.append((float(score), float(exposure)))
    if len(pairs) < 3:
        return {"count": len(pairs), "pearson": None, "spearman": None}
    scores = [pair[0] for pair in pairs]
    exposures = [pair[1] for pair in pairs]
    linear = pearson(scores, exposures)
    ranked = pearson(rank(scores), rank(exposures))
    return {
        "count": len(pairs),
        "pearson": None if linear is None else round(linear, 6),
        "spearman": None if ranked is None else round(ranked, 6),
    }


def _score(row, variant):
    if variant == "champion":
        return row.get("score")
    return ((row.get("score_variants") or {}).get(variant) or {}).get("score")


def build_bias_report(rows, generated_at=None):
    """Compare the old double-confidence penalty with the cumulative single pull path."""
    unique = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            unique.setdefault(ticker, row)
    comparable = [row for row in unique.values()
                  if isinstance(_score(row, "champion"), (int, float))
                  and isinstance(_score(row, "challenger"), (int, float))]
    paths = {
        "old_double_penalty": "champion",
        "new_single_shrinkage": "challenger",
    }
    exposures = {
        "log_market_cap": lambda row: math.log(row["market_cap"])
        if (row.get("market_cap") or 0) > 0 else None,
        "data_coverage": lambda row: row.get("data_coverage"),
        "analyst_coverage_count": lambda row: row.get("analyst_count"),
    }
    correlations = {
        exposure: {
            path: _correlations(
                comparable,
                lambda row, variant=variant: _score(row, variant),
                exposure_getter,
            )
            for path, variant in paths.items()
        }
        for exposure, exposure_getter in exposures.items()
    }
    market = correlations["log_market_cap"]

    def lower_absolute(statistic):
        before = market["old_double_penalty"][statistic]
        after = market["new_single_shrinkage"][statistic]
        return (before is not None and after is not None and abs(after) < abs(before))

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "comparison": "old_double_confidence_penalty_vs_new_single_shrinkage_challenger",
        "comparable_universe_count": len(comparable),
        "path_definitions": {
            "old_double_penalty": "Band-normalized fundamentals are coverage-multiplied, then the final evidence blend is confidence-multiplied again.",
            "new_single_shrinkage": "The challenger starts from raw category evidence and applies one confidence pull toward the configured neutral target before bounded modifiers.",
        },
        "correlations": correlations,
        "market_cap_correlation_absolute_drop": {
            "pearson": lower_absolute("pearson"),
            "spearman": lower_absolute("spearman"),
            "passed": lower_absolute("pearson") and lower_absolute("spearman"),
        },
    }


def write_bias_report(rows, generated_at=None, path=REPORT_PATH):
    report = build_bias_report(rows, generated_at)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report
