"""Rank-IC and per-metric attribution validation for the Earnings-timeliness screen, once
enough point-in-time history exists.

Reads ``earnings_timeliness_pit_store.py``'s dated snapshots (``tactical_score`` plus all 15
factor ranks, exactly as ``research_screens_v2.tactical_score()`` computed them that day) and
grades, once enough periods accumulate:

  * the composite's own rank IC against forward return (the same "hone in over time" pattern
    ``theme_ic.py``/``momentum_ic.py``/``pre_breakout_ic.py`` use), and
  * every one of the 15 factors' own standalone rank IC and marginal (drop-one) impact on the
    composite, via ``composite_attribution.py``.

Factors are already cross-sectional 0-100 ranks (``build_tactical_screens.rank_factors``), the
comparable scale ``tactical_score()`` weights directly - no separate standardization step,
unlike the two-level pre-breakout/swing composites.

Grades at ``horizons_days['1M']``: this screen's own factors (revision agreement/magnitude/
acceleration, earnings surprise, post-earnings drift) are near-term catalysts by construction -
the "timeliness" the screen is named for - not a multi-quarter thesis.

    python pipeline/validation/earnings_timeliness_ic.py
"""

import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, load_json, save_json  # noqa: E402
from composite_attribution import build_attribution_report, periods_from_snapshots  # noqa: E402
from evaluation import ic_summary, rank_ic  # noqa: E402
import earnings_timeliness_pit_store  # noqa: E402
from research_screens_v2 import TACTICAL_WEIGHTS  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
HORIZON_DAYS = CONFIG.get("horizons_days", {}).get("1M", 30)
PUBLIC_NAME = "validation/earnings_timeliness_metrics.json"


def _dated_snapshots(store_dir=None):
    dates = earnings_timeliness_pit_store.snapshot_dates(store_dir)
    return [{"date": date, "rows": earnings_timeliness_pit_store.load_snapshot(date, store_dir)}
            for date in dates]


def _composite_ic(period):
    scores, returns = [], []
    for ticker, forward in (period.get("forward_returns") or {}).items():
        score = (period.get("leg_scores") or {}).get(ticker, {}).get("tactical_score")
        if score is not None and forward is not None:
            scores.append(score)
            returns.append(forward)
    return rank_ic(scores, returns)


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    periods = periods_from_snapshots(snapshots, ["tactical_score", *TACTICAL_WEIGHTS], HORIZON_DAYS)
    attribution = build_attribution_report(periods, dict(TACTICAL_WEIGHTS), minimum_periods=MINIMUM_PERIODS,
                                           periods_per_year=PERIODS_PER_YEAR)
    composite_summary = ic_summary([_composite_ic(period) for period in periods], PERIODS_PER_YEAR)
    eligible = composite_summary["periods"] >= MINIMUM_PERIODS
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before earnings_timeliness_pit_store began recording "
                     "- this module never reconstructs a composite or factor score for a date "
                     "it did not observe",
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
    LOG.info(f"earnings_timeliness_ic: {report['snapshot_dates_recorded']} snapshot date(s) "
             f"recorded; {MINIMUM_PERIODS} eligible periods required before the composite or "
             "any factor is reported as meaningful")
    print(f"earnings_timeliness_ic: {report['snapshot_dates_recorded']} snapshot dates "
         f"recorded, composite status={report['composite']['status']}, "
         f"attribution status={report['attribution']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
