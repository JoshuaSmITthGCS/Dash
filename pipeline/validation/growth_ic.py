"""Rank-IC and per-metric attribution validation for the Fast Growth screens
(breakout-in-progress, emerging growth), once enough point-in-time history exists.

Reads ``growth_pit_store.py``'s dated snapshots and recomputes each screen's ``rankScore``
exactly as ``src/lib/researchScreens.js``'s ``rankBreakoutInProgress``/``rankEmergingGrowth``
compute it client-side (same gates, same weights) - this is the one place in the pipeline that
duplicates frontend scoring logic, and it exists only because there is nowhere server-side that
score is otherwise computed. If either JS function's math changes, this module's mirror of it
needs the matching update or the two will silently grade different things; each formula below
is commented with the exact JS lines it mirrors.

Grades, once enough periods accumulate:

  * each screen's composite rank IC against forward return (the same "hone in over time"
    pattern ``theme_ic.py``/``swing_ic.py`` use), and
  * every one of the composite's weighted components (burst/accelScore/trend/volume for
    breakout; growthScore/marginScore/strengthScore/contractionScore for emerging) - the exact
    terms each composite blends, not the raw inputs upstream of them - via
    ``composite_attribution.py``'s ``per_leg_ic``/``drop_one_leg_delta_ic``.

Same discipline as ``theme_ic.py``: a period only counts once both ends of it were actually
recorded, forward return comes from the price recorded in each snapshot, and nothing here
reconstructs a score for a date the pit store did not observe.

Breakout grades at ``horizons_days['1M']`` (a move already underway - a short follow-through
question); emerging grades at ``horizons_days['3M']`` (measurables that "sometimes precede" a
move - a longer setup-to-payoff question). See ``settings.json``'s
``validation._growth_horizon_comment``.

    python pipeline/validation/growth_ic.py
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
import growth_pit_store  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = CONFIG.get("periods_per_year", 12)
HORIZONS_DAYS = CONFIG.get("horizons_days", {})
PUBLIC_NAME = "validation/growth_metrics.json"

BREAKOUT_WEIGHTS = {"burst": 0.4, "accel_score": 0.3, "trend": 0.2, "volume": 0.1}
EMERGING_WEIGHTS = {"growth_score": 0.35, "margin_score": 0.2, "strength_score": 0.2, "contraction_score": 0.15}


def _clamp(value, lo=0.0, hi=100.0):
    return min(hi, max(lo, value))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def breakout_components(row):
    """The 4 terms ``rankBreakoutInProgress`` (researchScreens.js) blends 0.4/0.3/0.2/0.1,
    or ``None`` when the row does not clear the screen's own gates that day (weekReturn > 2,
    monthReturn > 0, acceleration > 0) - a name outside the gate contributes no observation
    for breakout that day, the same "no score, no period" semantics ``theme_ic.py`` uses.
    """
    week_return, month_return = row.get("return_5d"), row.get("return_20d")
    if not _finite(week_return) or not _finite(month_return) or week_return <= 2 or month_return <= 0:
        return None
    prior_pace_5d = (month_return - week_return) / 15 * 5
    acceleration = week_return - prior_pace_5d
    if acceleration <= 0:
        return None
    volume_ratio = row.get("volume_ratio_60d")
    return {
        "burst": _clamp(50 + week_return * 3),
        "accel_score": _clamp(50 + acceleration * 2),
        "trend": _clamp(50 + month_return * 1.2),
        "volume": _clamp(50 + (volume_ratio - 1) * 40) if _finite(volume_ratio) else 50,
    }


def breakout_score(row):
    components = breakout_components(row)
    if components is None:
        return None
    return sum(components[name] * weight for name, weight in BREAKOUT_WEIGHTS.items())


def emerging_components(row):
    """The 4 terms ``rankEmergingGrowth`` (researchScreens.js) blends 0.35/0.2/0.2/0.15
    (renormalized over the weights actually present), or ``None`` when the row does not clear
    the screen's own gates that day. The estimate-revision bonus is omitted -
    ``growth_pit_store.py`` does not record it, and the JS treats it as optional (never
    required, never penalized when absent) so omitting it here changes nothing about
    eligibility, only drops one always-optional term from the weighted mean.
    """
    week_return = row.get("return_5d")
    revenue_growth = row.get("revenue_growth")
    relative_strength = row.get("relative_strength_20d")
    if not _finite(week_return) or week_return > 2:
        return None
    if not _finite(revenue_growth) or revenue_growth <= 0.05:
        return None
    if not _finite(relative_strength) or relative_strength <= 0:
        return None

    recent_vol, longer_vol = row.get("recent_vol_10d"), row.get("longer_vol_60d")
    volatility_contracting = (recent_vol < longer_vol * 0.85
                              if _finite(recent_vol) and _finite(longer_vol) and longer_vol > 0
                              else None)
    margin_trend = row.get("operating_margin_trend")

    return {
        "growth_score": _clamp(50 + revenue_growth * 150),
        "margin_score": _clamp(50 + margin_trend * 300) if _finite(margin_trend) else 50,
        "strength_score": _clamp(50 + relative_strength * 4),
        "contraction_score": 50 if volatility_contracting is None else (70 if volatility_contracting else 40),
    }


def emerging_score(row):
    components = emerging_components(row)
    if components is None:
        return None
    total_weight = sum(EMERGING_WEIGHTS.values())
    return sum(components[name] * weight for name, weight in EMERGING_WEIGHTS.items()) / total_weight


GRADED_SCREENS = {
    "breakout_in_progress": {"score_fn": breakout_score, "components_fn": breakout_components,
                             "weights": BREAKOUT_WEIGHTS, "horizon_key": "1M"},
    "emerging_growth": {"score_fn": emerging_score, "components_fn": emerging_components,
                        "weights": EMERGING_WEIGHTS, "horizon_key": "3M"},
}


def _periods(snapshots, score_fn, horizon_days):
    """One IC observation per (start, end) snapshot pair whose gap covers the horizon."""
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
            score = score_fn(row)
            start_price = row.get("price")
            end_price = end_prices.get(row.get("ticker"))
            if score is None or not start_price or not end_price:
                continue
            scores.append(score)
            forward_returns.append(end_price / start_price - 1)
        ic = rank_ic(scores, forward_returns)
        if ic is not None:
            periods.append({"start_date": start["date"], "end_date": end["date"],
                            "sample_size": len(scores), "rank_ic": ic})
    return periods


def _component_snapshots(snapshots, components_fn):
    """Every snapshot's rows, with a gated component dict added where the row clears the
    screen's own gates that day - the shape ``composite_attribution.periods_from_snapshots``
    expects, built from a pure function of what ``growth_pit_store.py`` already recorded
    rather than a second recorder. Price/ticker are kept even when a row doesn't clear the
    gate (``components_fn`` returns ``None``): that ticker then simply contributes no
    ``leg_scores`` entry when this snapshot is a *start*, exactly the "no score, no period"
    exclusion the ungated case wants - but the row must still be resolvable as an *end*
    snapshot's price for an earlier period, which dropping it entirely would break.
    """
    transformed = []
    for snapshot in snapshots:
        rows = []
        for row in snapshot["rows"]:
            components = components_fn(row) or {}
            rows.append({"ticker": row.get("ticker"), "price": row.get("price"), **components})
        transformed.append({"date": snapshot["date"], "rows": rows})
    return transformed


def _dated_snapshots(store_dir=None):
    dates = growth_pit_store.snapshot_dates(store_dir)
    return [{"date": date, "rows": growth_pit_store.load_snapshot(date, store_dir)} for date in dates]


def build_report(store_dir=None):
    snapshots = _dated_snapshots(store_dir)
    metrics = {}
    for name, spec in GRADED_SCREENS.items():
        horizon_days = HORIZONS_DAYS.get(spec["horizon_key"], 30)
        periods = _periods(snapshots, spec["score_fn"], horizon_days)
        summary = ic_summary([period["rank_ic"] for period in periods], PERIODS_PER_YEAR)
        eligible = summary["periods"] >= MINIMUM_PERIODS

        component_periods = periods_from_snapshots(
            _component_snapshots(snapshots, spec["components_fn"]), list(spec["weights"]), horizon_days)
        attribution = build_attribution_report(component_periods, dict(spec["weights"]),
                                               minimum_periods=MINIMUM_PERIODS, periods_per_year=PERIODS_PER_YEAR)

        metrics[name] = {
            "requires_live_sample": True,
            "horizon_days": horizon_days,
            "eligible_periods": summary["periods"],
            "minimum_icir_periods": MINIMUM_PERIODS,
            "status": "eligible" if eligible else "accumulating",
            "mean_rank_ic": summary["mean_ic"] if eligible else None,
            "icir": summary["icir"] if eligible else None,
            "t_stat": summary["t_stat"] if eligible else None,
            "hit_rate": summary["hit_rate"] if eligible else None,
            "clears_multiple_testing_bar": summary["clears_multiple_testing_bar"] if eligible else False,
            "periods": periods if eligible else [],
            "attribution": attribution,
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before growth_pit_store began recording - this module "
                     "never reconstructs a growth score for a date it did not observe",
        },
        "snapshot_dates_recorded": len(snapshots),
        "metrics": metrics,
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    accumulated = report["snapshot_dates_recorded"]
    LOG.info(f"growth_ic: {accumulated} snapshot date(s) recorded; "
             f"{MINIMUM_PERIODS} eligible periods required before either screen is reported as "
             "meaningful")
    print(f"growth_ic: {accumulated} snapshot dates recorded, "
         f"{sum(1 for m in report['metrics'].values() if m['status'] == 'eligible')} of "
         f"{len(report['metrics'])} screens eligible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
