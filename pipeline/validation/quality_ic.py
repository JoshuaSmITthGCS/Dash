"""Rank-IC and per-metric attribution validation for the Quality-at-valuation-lows screen's
quality composite, once enough point-in-time history exists.

Reads ``quality_pit_store.py``'s dated snapshots (the 4 category scores
``build_quality_value_screen.py``'s ``quality_score()`` blends: profitability,
financial_health, accounting_quality, capital_allocation) and grades, once enough periods
accumulate:

  * the composite's own rank IC against forward return - recomputed via
    ``evaluation.composite_score``, the identical renormalized-weighted-mean formula
    ``quality_score()`` implements (verified equivalent: both drop a missing category and
    reweight over what remains), not a second implementation of it, and
  * every one of the 4 categories' own standalone rank IC and marginal (drop-one) impact on
    the composite, via ``composite_attribution.py``.

Note this grades the *quality axis* specifically, not the whole quality-value screen: that
screen ranks by cheapness (``own_history_score``/``peer_value_score``), with ``quality_score``
published as a separate, secondary axis - a real weighted composite of different values in its
own right, worth its own measurement regardless of whether it is the screen's primary sort key.

Grades at ``horizons_days['3M']``: business-quality categories describe a durable state, not a
near-term catalyst, the same horizon this pipeline's primary IC harness uses for the main
composite.

    python pipeline/validation/quality_ic.py
"""

import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, load_json, save_json  # noqa: E402
from composite_attribution import build_attribution_report, periods_from_snapshots  # noqa: E402
from evaluation import composite_score, ic_summary, rank_ic  # noqa: E402
import quality_pit_store  # noqa: E402
from quality_pit_store import CATEGORIES  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
HORIZON_DAYS = CONFIG.get("horizons_days", {}).get("3M", 91)
PUBLIC_NAME = "validation/quality_metrics.json"

QUALITY_WEIGHTS = {"profitability": .35, "financial_health": .30,
                  "accounting_quality": .20, "capital_allocation": .15}


def _dated_snapshots(store_dir=None):
    dates = quality_pit_store.snapshot_dates(store_dir)
    return [{"date": date, "rows": quality_pit_store.load_snapshot(date, store_dir)} for date in dates]


def _composite_ic(period):
    scores, returns = [], []
    for ticker, forward in (period.get("forward_returns") or {}).items():
        leg_scores = (period.get("leg_scores") or {}).get(ticker) or {}
        score = composite_score(leg_scores, QUALITY_WEIGHTS)
        if score is not None and forward is not None:
            scores.append(score)
            returns.append(forward)
    return rank_ic(scores, returns)


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    periods = periods_from_snapshots(snapshots, list(CATEGORIES), HORIZON_DAYS)
    attribution = build_attribution_report(periods, dict(QUALITY_WEIGHTS), minimum_periods=MINIMUM_PERIODS,
                                           periods_per_year=PERIODS_PER_YEAR)
    composite_summary = ic_summary([_composite_ic(period) for period in periods], PERIODS_PER_YEAR)
    eligible = composite_summary["periods"] >= MINIMUM_PERIODS
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before quality_pit_store began recording - this "
                     "module never reconstructs a category score for a date it did not "
                     "observe",
        },
        "snapshot_dates_recorded": len(snapshots),
        "horizon_days": HORIZON_DAYS,
        "composite": {
            "eligible_periods": composite_summary["periods"],
            "minimum_icir_periods": MINIMUM_PERIODS,
            "status": "eligible" if eligible else "accumulating",
            "mean_rank_ic": composite_summary["mean_ic"] if eligible else None,
            "icir": composite_summary["icir"] if eligible else None,
            "t_stat": composite_summary["t_stat"] if eligible else None,
            "hit_rate": composite_summary["hit_rate"] if eligible else None,
            "clears_multiple_testing_bar": composite_summary["clears_multiple_testing_bar"] if eligible else False,
        },
        "attribution": attribution,
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    LOG.info(f"quality_ic: {report['snapshot_dates_recorded']} snapshot date(s) recorded; "
             f"{MINIMUM_PERIODS} eligible periods required before the composite or any "
             "category is reported as meaningful")
    print(f"quality_ic: {report['snapshot_dates_recorded']} snapshot dates recorded, "
         f"composite status={report['composite']['status']}, "
         f"attribution status={report['attribution']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
