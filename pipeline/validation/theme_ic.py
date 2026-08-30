"""Rank-IC validation for theme-screen scores, once enough point-in-time history exists.

Wholly separate from ``validation/ic_harness.py``'s champion/challenger fundamentals harness:
this reads ``theme_pit_store.py``'s own dated snapshots, never ``pit_store``/``raw_pit_store``,
and grades a different set of scores (``theme_exposure_score``, ``connectivity_score``,
``structural_rank_composite``) that harness has never seen. Same discipline throughout: a period
only counts once both ends of it were actually recorded, forward return is computed from the
price recorded in each snapshot exactly the way ``ic_harness._forward_periods`` already does,
and nothing here reconstructs a score for a date before ``theme_pit_store`` started writing it.

``theme_pit_store`` starts empty on this brief's own delivery date, so the first many runs of
this module will correctly report zero eligible periods - not a bug, and not something this
module works around. ``settings.json``'s ``validation.minimum_icir_periods`` (24, shared with
the fundamentals harness) is the same bar applied here before anything is presented as a
measurement rather than an accumulating count.

    python pipeline/validation/theme_ic.py
"""

import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, load_json, save_json  # noqa: E402
from evaluation import ic_summary, rank_ic  # noqa: E402
import theme_pit_store  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
PUBLIC_NAME = "validation/theme_metrics.json"

# The scores this module grades - never theme_exposure_score's own inputs, never a price-derived
# reading folded back into exposure. connectivity_score and structural_rank_composite are new,
# unvalidated metrics from this brief; theme_exposure_score already has a validated fundamentals
# precedent in ic_harness.py, graded here on its own theme-specific forward-return sample rather
# than reusing that harness's periods, which are keyed to a different snapshot cadence.
GRADED_METRICS = ("theme_exposure_score", "connectivity_score", "structural_rank_composite")


def _dated_snapshots(store_dir=None):
    """Every recorded date's rows, keyed by (ticker, theme_id)."""
    dates = theme_pit_store.snapshot_dates(store_dir)
    return [{"date": date, "rows": theme_pit_store.load_snapshot(date, store_dir)} for date in dates]


def _periods(snapshots, metric):
    """One IC observation per (start, end) snapshot pair whose gap covers the primary horizon.

    Mirrors ``ic_harness._forward_periods``: every consecutive pair is a candidate start, and
    the first later snapshot far enough out supplies the end price. A metric with no scored
    rows on a given start date simply contributes no period for that date, rather than raising.
    """
    horizon_days = CONFIG.get("horizons_days", {}).get(CONFIG.get("primary_horizon", "3M"), 91)
    periods = []
    for index, start in enumerate(snapshots):
        start_date = datetime.fromisoformat(start["date"]).replace(tzinfo=timezone.utc)
        target = start_date.timestamp() + horizon_days * 86400
        end = next((candidate for candidate in snapshots[index + 1:]
                    if datetime.fromisoformat(candidate["date"]).replace(tzinfo=timezone.utc).timestamp()
                    >= target), None)
        if not end:
            continue
        end_prices = {(row["ticker"], row["theme_id"]): row.get("price") for row in end["rows"]}
        scores, forward_returns = [], []
        for row in start["rows"]:
            score = row.get(metric)
            start_price = row.get("price")
            end_price = end_prices.get((row["ticker"], row["theme_id"]))
            if score is None or not start_price or not end_price:
                continue
            scores.append(score)
            forward_returns.append(end_price / start_price - 1)
        ic = rank_ic(scores, forward_returns)
        if ic is not None:
            periods.append({"start_date": start["date"], "end_date": end["date"],
                            "sample_size": len(scores), "rank_ic": ic})
    return periods


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    metrics = {}
    for metric in GRADED_METRICS:
        periods = _periods(snapshots, metric)
        summary = ic_summary([period["rank_ic"] for period in periods], PERIODS_PER_YEAR)
        eligible = summary["periods"] >= MINIMUM_PERIODS
        metrics[metric] = {
            "requires_live_sample": True,
            "eligible_periods": summary["periods"],
            "minimum_icir_periods": MINIMUM_PERIODS,
            "status": "eligible" if eligible else "accumulating",
            "mean_rank_ic": summary["mean_ic"] if eligible else None,
            "icir": summary["icir"] if eligible else None,
            "t_stat": summary["t_stat"] if eligible else None,
            "hit_rate": summary["hit_rate"] if eligible else None,
            "clears_multiple_testing_bar": summary["clears_multiple_testing_bar"] if eligible else False,
            "periods": periods if eligible else [],
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before theme_pit_store began recording - this module "
                     "never reconstructs a theme score for a date it did not observe",
        },
        "snapshot_dates_recorded": len(snapshots),
        "primary_horizon": CONFIG.get("primary_horizon", "3M"),
        "metrics": metrics,
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    accumulated = report["snapshot_dates_recorded"]
    LOG.info(f"theme_ic: {accumulated} snapshot date(s) recorded; "
             f"{MINIMUM_PERIODS} eligible periods required before any metric is reported as "
             "meaningful")
    print(f"theme_ic: {accumulated} snapshot dates recorded, "
         f"{sum(1 for m in report['metrics'].values() if m['status'] == 'eligible')} of "
         f"{len(report['metrics'])} metrics eligible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
