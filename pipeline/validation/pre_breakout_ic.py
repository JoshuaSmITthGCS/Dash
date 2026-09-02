"""Rank-IC and per-metric attribution validation for the Pre-breakout screen, once enough
point-in-time history exists.

Reads ``pre_breakout_pit_store.py``'s dated snapshots (composite_z plus all 11 standardized
subfactors, exactly as ``pre_breakout_signals.py`` published them that day) and grades, once
enough periods accumulate:

  * the composite's own rank IC against forward return (the same "hone in over time" pattern
    ``theme_ic.py``/``swing_ic.py``/``growth_ic.py`` use), and
  * every one of the 11 subfactors' own standalone rank IC and marginal (drop-one) impact on
    the composite, via ``composite_attribution.py`` - the same ``per_leg_ic``/
    ``drop_one_leg_delta_ic`` machinery that already grades the main advisor composite's
    fundamentals legs for ``signal_metrics.json``.

Flat per-subfactor weight is ``PRE_BREAKOUT_WEIGHTS[leg] * SUBWEIGHTS_BY_LEG[leg][subfactor]``
- the same flattening ``backtest_monthly.panel_leg_weights()`` already does for the main
score's two-level fundamentals blend, applied here to this screen's own two-level blend.

Grades at ``horizons_days['3M']``: a Stage-0 "about to move, not yet" setup screen
(``classify_stage`` distinguishes "coiling" from already-"breaking_out") is a setup-to-payoff
question, the same horizon ``growth_ic.py`` uses for the analogous emerging-growth screen.

    python pipeline/validation/pre_breakout_ic.py
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
from pre_breakout_signals import PRE_BREAKOUT_WEIGHTS, SUBWEIGHTS_BY_LEG  # noqa: E402
import pre_breakout_pit_store  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
HORIZON_DAYS = CONFIG.get("horizons_days", {}).get("3M", 91)
PUBLIC_NAME = "validation/pre_breakout_metrics.json"

FLAT_WEIGHTS = {subfactor: PRE_BREAKOUT_WEIGHTS[leg] * weight
               for leg, subweights in SUBWEIGHTS_BY_LEG.items()
               for subfactor, weight in subweights.items()}


def _dated_snapshots(store_dir=None):
    dates = pre_breakout_pit_store.snapshot_dates(store_dir)
    return [{"date": date, "rows": pre_breakout_pit_store.load_snapshot(date, store_dir)} for date in dates]


def _composite_ic(period):
    """The composite's own IC for one period, read out of the same ``leg_scores`` the
    attribution machinery uses (``composite_z`` rides along as an extra, unweighted key) -
    one snapshot pairing pass instead of two.
    """
    scores, returns = [], []
    for ticker, forward in (period.get("forward_returns") or {}).items():
        score = (period.get("leg_scores") or {}).get(ticker, {}).get("composite_z")
        if score is not None and forward is not None:
            scores.append(score)
            returns.append(forward)
    return rank_ic(scores, returns)


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    periods = periods_from_snapshots(snapshots, ["composite_z", *FLAT_WEIGHTS], HORIZON_DAYS)
    attribution = build_attribution_report(periods, FLAT_WEIGHTS, minimum_periods=MINIMUM_PERIODS,
                                           periods_per_year=PERIODS_PER_YEAR)
    composite_summary = ic_summary([_composite_ic(period) for period in periods], PERIODS_PER_YEAR)
    eligible = composite_summary["periods"] >= MINIMUM_PERIODS
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before pre_breakout_pit_store began recording - this "
                     "module never reconstructs a composite or subfactor score for a date it "
                     "did not observe",
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
    LOG.info(f"pre_breakout_ic: {report['snapshot_dates_recorded']} snapshot date(s) recorded; "
             f"{MINIMUM_PERIODS} eligible periods required before the composite or any "
             "subfactor is reported as meaningful")
    print(f"pre_breakout_ic: {report['snapshot_dates_recorded']} snapshot dates recorded, "
         f"composite status={report['composite']['status']}, "
         f"attribution status={report['attribution']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
