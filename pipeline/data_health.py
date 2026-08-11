"""Provider-health monitoring and the coverage publication gate.

Round 4 (docs/AUDIT-ROUND-4-FINDINGS.md) established that the 2026-08-06 statement-provider
outage silently degraded the champion score into a ranking of data availability for five
days: coverage predicted the final score at Spearman +0.63 and nothing in the pipeline
flagged it. This module makes that failure mode loud.

Two mechanisms:

1. Statement-coverage health. Compare the refresh's realized coverage on monitored
   statement-derived metrics against the expected baseline. Below ``degraded_below`` the
   refresh is DEGRADED, below ``critical_below`` it is CRITICAL. The state ships in the
   run manifest and diagnostics so the UI can label the leaderboard instead of publishing
   a silently misleading ranking.

2. Per-name publication gate. A research score for a name whose fundamentals coverage
   sits below ``min_publication_coverage`` is not published as a ranked score. The name
   stays visible with its diagnostics, the way INSUFFICIENT DATA already works, because
   the alternative measured in Round 3 item 4 is a leaderboard where identical evidence
   scores up to 1.87x apart on data availability alone.

Thresholds live in settings.json under ``data_health`` so they are config, not code.
Defaults here are the measured baseline: the enriched cohort's statement coverage runs
0.85 to 0.95, the outage floor ran 0.10 to 0.20, and the pre-outage published universe
carried a median fundamentals coverage near 0.9 for enriched names.
"""
from __future__ import annotations

DEFAULTS = {
    "monitored_metrics": [
        "ev_to_ebitda", "ev_to_ebit", "return_on_invested_capital",
        "gross_profits_to_assets", "piotroski_f", "net_buyback_yield",
        "altman_z", "stock_comp_to_revenue", "accruals_ratio",
    ],
    "expected_statement_coverage": 0.70,
    "degraded_below": 0.50,
    "critical_below": 0.30,
    "min_publication_coverage": 0.35,
}


def config(settings):
    return {**DEFAULTS, **(settings.get("data_health") or {})}


def statement_coverage(rows, monitored):
    """Per-metric and mean coverage of monitored statement metrics across scored rows.

    ``rows`` are per-name metric dicts (raw values or normalized scores, either works:
    presence is the measurement).
    """
    if not rows:
        return {"per_metric": {}, "mean": 0.0, "n": 0}
    per_metric = {}
    for metric in monitored:
        resolved = sum(1 for row in rows if row.get(metric) is not None)
        per_metric[metric] = round(resolved / len(rows), 3)
    mean = round(sum(per_metric.values()) / len(per_metric), 3) if per_metric else 0.0
    return {"per_metric": per_metric, "mean": mean, "n": len(rows)}


def statement_health(rows, settings):
    """One health verdict for the refresh: healthy, degraded, or critical."""
    cfg = config(settings)
    coverage = statement_coverage(rows, cfg["monitored_metrics"])
    mean = coverage["mean"]
    if mean < cfg["critical_below"]:
        state = "critical"
    elif mean < cfg["degraded_below"]:
        state = "degraded"
    else:
        state = "healthy"
    return {
        "state": state,
        "mean_statement_coverage": mean,
        "expected_statement_coverage": cfg["expected_statement_coverage"],
        "per_metric_coverage": coverage["per_metric"],
        "rows_measured": coverage["n"],
        "thresholds": {"degraded_below": cfg["degraded_below"],
                       "critical_below": cfg["critical_below"]},
    }


def publication_gate(fundamentals_coverage, settings):
    """Whether a name's research score may publish as a ranked score.

    Returns (publishable, reason). Names failing the gate keep their diagnostics and
    challenger output; only the ranked champion score is withheld.
    """
    cfg = config(settings)
    floor = cfg["min_publication_coverage"]
    value = fundamentals_coverage if isinstance(fundamentals_coverage, (int, float)) else 0.0
    if value >= floor:
        return True, None
    return False, (f"fundamentals coverage {value:.2f} below publication floor "
                   f"{floor:.2f} (data_health.min_publication_coverage)")
