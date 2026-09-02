"""Rank-IC validation for the Swing screen's composite_z signal, once enough prospective
history exists.

Reuses ``pipeline/shadow_store/swing/`` rather than starting a new point-in-time store: that
directory already holds one immutable, dated snapshot per refresh (ticker, ``signal``
[composite_z], ``price``, rank, weight) written by ``shadow_portfolios.py`` on every scheduled
refresh since 2026-08-02 (see ``STRATEGIES["swing"]`` / ``screen_rows("swing", "composite_z")``
in that module). Building a second recorder for the same score would just be two point-in-time
stores disagreeing about what the swing screen published on a given day.

Same discipline as ``theme_ic.py``: a period only counts once both ends of it were actually
recorded, forward return comes from the price recorded in each snapshot, and nothing here
reconstructs a signal for a date the shadow store did not observe. ``composite_z`` blends all
three swing tiers (F/M/S, see ``pipeline/swing_tiers.py``) into one equal-weight basket with no
tier field of its own, so this grades at one blended horizon
(``settings.json``'s ``validation.swing_horizon_days``, representative of the mid "M" tier)
rather than three separate ones.

    python pipeline/validation/swing_ic.py
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, load_json, save_json  # noqa: E402
from evaluation import ic_summary, rank_ic  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
HORIZON_DAYS = CONFIG.get("swing_horizon_days", 14)
PUBLIC_NAME = "validation/swing_metrics.json"
GRADED_METRIC = "composite_z"

STORE_DIR = os.path.join(PIPELINE_DIR, "shadow_store", "swing")


def _dated_snapshots(store_dir=None):
    """Every immutable snapshot's ``as_of`` date and rows, oldest first.

    One file per date is enforced by ``validation_framework.append_immutable_snapshot`` itself
    (it raises rather than let a second same-day snapshot exist), so no de-duplication is
    needed here.
    """
    store_dir = store_dir or STORE_DIR
    if not os.path.isdir(store_dir):
        return []
    snapshots = []
    for path in sorted(glob.glob(os.path.join(store_dir, "*.json"))):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        as_of = payload.get("as_of")
        rows = payload.get("rows") or []
        if as_of and rows:
            snapshots.append({"date": as_of, "rows": rows})
    snapshots.sort(key=lambda snap: snap["date"])
    return snapshots


def _periods(snapshots, horizon_days=HORIZON_DAYS):
    """One IC observation per (start, end) snapshot pair whose gap covers the horizon.

    Mirrors ``theme_ic._periods``/``ic_harness._forward_periods``: every consecutive pair is a
    candidate start, and the first later snapshot far enough out supplies the end price.
    """
    periods = []
    for index, start in enumerate(snapshots):
        start_date = datetime.fromisoformat(start["date"]).replace(tzinfo=timezone.utc)
        target = start_date.timestamp() + horizon_days * 86400
        end = next((candidate for candidate in snapshots[index + 1:]
                    if datetime.fromisoformat(candidate["date"]).replace(tzinfo=timezone.utc).timestamp()
                    >= target), None)
        if not end:
            continue
        end_prices = {row["ticker"]: row.get("price") for row in end["rows"]}
        scores, forward_returns = [], []
        for row in start["rows"]:
            ticker = row.get("ticker")
            signal = row.get("signal")
            start_price = row.get("price")
            end_price = end_prices.get(ticker)
            if ticker is None or signal is None or not start_price or not end_price:
                continue
            scores.append(signal)
            forward_returns.append(end_price / start_price - 1)
        ic = rank_ic(scores, forward_returns)
        if ic is not None:
            periods.append({"start_date": start["date"], "end_date": end["date"],
                            "sample_size": len(scores), "rank_ic": ic})
    return periods


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    periods = _periods(snapshots)
    summary = ic_summary([period["rank_ic"] for period in periods], PERIODS_PER_YEAR)
    eligible = summary["periods"] >= MINIMUM_PERIODS
    metric = {
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
            "label": "no history exists before shadow_store/swing began recording (2026-08-02) "
                     "- this module never reconstructs a swing signal for a date it did not "
                     "observe",
        },
        "snapshot_dates_recorded": len(snapshots),
        "horizon_days": HORIZON_DAYS,
        "metrics": {GRADED_METRIC: metric},
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    accumulated = report["snapshot_dates_recorded"]
    LOG.info(f"swing_ic: {accumulated} snapshot date(s) recorded; "
             f"{MINIMUM_PERIODS} eligible periods required before composite_z is reported as "
             "meaningful")
    print(f"swing_ic: {accumulated} snapshot dates recorded, "
         f"status={report['metrics'][GRADED_METRIC]['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
