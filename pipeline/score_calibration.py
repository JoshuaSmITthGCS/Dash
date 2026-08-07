"""What has historically happened to stocks scoring 80-85? Right now: unknown, and it says so.

A 0-100 score with no calibration is an opinion with a decimal point. The end state this builds
toward is a table a user can read directly:

    Score 80-85   n = 3,412   63d sector-relative median +1.8%   beat sector 58.9%

Getting there needs prospective observations whose forward windows have closed. The IC harness
has **0 of the 24 required periods** and the PIT store is three days deep, so this publishes
`insufficient_data` with real bucket definitions and zero counts.

That is the point. The machinery exists, the gate is explicit, and nothing populates until the
evidence does -- so `confidence_detail.historical_calibration` cannot quietly acquire a
plausible-looking number. Fabricating calibration is worse than having none: it converts an
admitted unknown into a false claim, and it is the specific failure this module is built to
make impossible.

Buckets are adaptive by default. Fixed score bands look tidier but starve at the tails, where
the interesting behaviour is -- a "90+" bucket with four observations reports noise with a
confidence interval attached to it.

Usage: python pipeline/score_calibration.py
Output: pipeline/reports/score_calibration.json
"""

import json
import math
import os
import sys
from statistics import mean, median, pstdev

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from common import load_json  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
VALIDATION = SETTINGS.get("validation", {})
CONFIDENCE = SETTINGS.get("confidence", {})
OUT_PATH = os.path.join(HERE, "reports", "score_calibration.json")

# A bucket below this many observations reports nothing. Chosen before looking at any result:
# roughly the point at which a proportion's 95% interval is narrower than +/-15 points, which
# is the coarsest resolution at which a "beat sector" rate is worth showing anyone.
MINIMUM_BUCKET_OBSERVATIONS = 30
DEFAULT_BUCKET_COUNT = 5

# Reported alongside the adaptive buckets so the published table can be read in score terms.
FIXED_BANDS = ((80, 101), (75, 80), (70, 75), (65, 70), (60, 65), (0, 60))


def _proportion_interval(successes, total):
    """Wald interval on a proportion, wide and honest rather than clever."""
    if not total:
        return [None, None]
    rate = successes / total
    error = 1.96 * math.sqrt(max(rate * (1 - rate), 0.0) / total)
    return [round(max(0.0, rate - error), 4), round(min(1.0, rate + error), 4)]


def _mean_interval(values):
    if len(values) < 2:
        return [None, None]
    error = 1.96 * pstdev(values) / math.sqrt(len(values))
    return [round(mean(values) - error, 5), round(mean(values) + error, 5)]


def summarize_bucket(label, rows, minimum=MINIMUM_BUCKET_OBSERVATIONS):
    """Outcome statistics for one score bucket, or a refusal with the shortfall named."""
    outcomes = [row["residual_forward_return"] for row in rows
                if row.get("residual_forward_return") is not None]
    if len(outcomes) < minimum:
        return {
            "bucket": label,
            "observations": len(outcomes),
            "status": "insufficient_data",
            "minimum_observations": minimum,
            "shortfall": minimum - len(outcomes),
        }
    beat = sum(1 for value in outcomes if value > 0)
    ordered = sorted(outcomes)
    equity, peak, worst = 1.0, 1.0, 0.0
    for value in ordered:
        equity *= 1 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    return {
        "bucket": label,
        "observations": len(outcomes),
        "status": "measured",
        "mean_residual_return": round(mean(outcomes), 5),
        "median_residual_return": round(median(outcomes), 5),
        "mean_confidence_interval_95": _mean_interval(outcomes),
        "beat_sector_rate": round(beat / len(outcomes), 4),
        "beat_sector_confidence_interval_95": _proportion_interval(beat, len(outcomes)),
        "volatility": round(pstdev(outcomes), 5) if len(outcomes) > 1 else None,
        "worst_observation": round(ordered[0], 5),
        "best_observation": round(ordered[-1], 5),
        "drawdown_of_sorted_outcomes": round(worst, 5),
    }


def adaptive_buckets(rows, count=DEFAULT_BUCKET_COUNT):
    """Equal-count score quantiles, so no bucket starves while another overflows."""
    scored = sorted((row for row in rows if row.get("score") is not None),
                    key=lambda row: row["score"])
    if not scored:
        return []
    buckets = []
    for index in range(count):
        start = round(index * len(scored) / count)
        end = round((index + 1) * len(scored) / count)
        chunk = scored[start:end]
        if not chunk:
            continue
        label = f"q{index + 1} ({chunk[0]['score']:.1f}-{chunk[-1]['score']:.1f})"
        buckets.append(summarize_bucket(label, chunk))
    return buckets


def fixed_band_buckets(rows, bands=FIXED_BANDS):
    """The score bands a user actually reads, reported even when they are empty."""
    return [
        summarize_bucket(
            f"{low}-{high - 1}" if high <= 100 else f"{low}+",
            [row for row in rows if row.get("score") is not None and low <= row["score"] < high],
        )
        for low, high in bands
    ]


def is_eligible(buckets):
    """Whether any bucket in the set cleared the observation minimum.

    Applied to the **fixed score bands**, because those are what
    ``confidence.historical_calibration_component`` reads. Gating on the adaptive quintiles
    instead would let the two disagree: a run whose observations all sit in one score band
    measures that band fine while every equal-count quintile starves, and the consumer would
    then read a measured bucket out of a report flagged unpublishable.
    """
    return any(bucket["status"] == "measured" for bucket in buckets)


def build_report(rows=None):
    """``rows`` are closed observations: {score, residual_forward_return}.

    They come from the IC harness's completed forward periods. With zero completed periods
    this is an empty list, and every bucket reports its shortfall.
    """
    rows = rows or []
    adaptive = adaptive_buckets(rows)
    fixed = fixed_band_buckets(rows)
    eligible = is_eligible(fixed)
    return {
        "schema_version": 1,
        "target": "residual_forward_return",
        "horizon_sessions": VALIDATION.get("horizons_sessions", {}).get(
            VALIDATION.get("primary_horizon", "3M")),
        "status": "measured" if eligible else "insufficient_data",
        "observations": len(rows),
        "minimum_observations_per_bucket": MINIMUM_BUCKET_OBSERVATIONS,
        "required_ic_periods": VALIDATION.get("minimum_icir_periods"),
        "adaptive_buckets": adaptive,
        "fixed_score_bands": fixed,
        "publishable_to_confidence_detail": eligible,
        "note": ("historical_calibration stays null in confidence_detail until at least one "
                 "bucket clears the observation minimum. A score bucket with no closed "
                 "forward windows has no outcome distribution, and inventing one would turn "
                 "an admitted unknown into a false claim."),
        "what_would_populate_this": (
            f"{VALIDATION.get('minimum_icir_periods')} monthly point-in-time periods whose "
            f"{VALIDATION.get('horizons_sessions', {}).get('3M')}-session forward windows have "
            "closed; roughly two years of production refreshes, or a point-in-time "
            "reconstruction from SEC EDGAR filing dates"),
    }


def observations_from_harness(report=None):
    """Closed (score, residual return) pairs from the IC harness's own periods."""
    from validation.ic_harness import _forward_periods, _monthly_refreshes, _refreshes, read_snapshots

    horizon = VALIDATION.get("horizons_sessions", {}).get(VALIDATION.get("primary_horizon", "3M"))
    refreshes = _monthly_refreshes(_refreshes(read_snapshots()))
    rows = []
    for period in _forward_periods(refreshes, "champion", horizon):
        rows.extend({"score": row["score"],
                     "residual_forward_return": row["residual_forward_return"]}
                    for row in period["rows"])
    return rows


def main():
    report = build_report(observations_from_harness())
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"status: {report['status']}  observations: {report['observations']}")
    for bucket in report["fixed_score_bands"]:
        if bucket["status"] == "measured":
            print(f"  {bucket['bucket']:<8} n={bucket['observations']:<6} "
                  f"median {bucket['median_residual_return']:+.2%}  "
                  f"beat sector {bucket['beat_sector_rate']:.1%}")
        else:
            print(f"  {bucket['bucket']:<8} n={bucket['observations']:<6} "
                  f"insufficient (needs {bucket['shortfall']} more)")
    print(f"publishable to confidence_detail: {report['publishable_to_confidence_detail']}")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
