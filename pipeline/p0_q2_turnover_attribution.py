"""P0 WO-5 (Q2) -- what actually drives the backtest's 64.9% monthly turnover?

Two things are measured here, and they are NOT the same phenomenon, which matters for reading
the numbers below correctly:

1. The brief's real target is the *5-year backtest's* month-over-month rank churn (64.9%/month,
   measured over 60 monthly rebalances against historical fundamentals). Attributing THAT churn
   into (a) band crossings on unchanged values, (b) genuine input changes, (c) metric
   availability flicker, and (d) price-driven moves requires re-running rank_week() with
   instrumentation across the full 5-year historical universe -- the same ~860-name, 5-year
   Yahoo price+statement history WO-3 already found is not committed to disk and cannot be
   re-fetched from this session (network policy blocks Yahoo; see docs/P0-REPAIRS.md WO-3). That
   attribution, and the "re-run under cross_sectional normalization, does turnover fall"
   experiment the brief also asks for, are BOTH skipped here for that reason. Reproduction
   commands are given in docs/P0-Q2-TURNOVER.md.

2. What IS on disk is pipeline/pit_store/*.jsonl -- the validation harness's append-only,
   immutable scored-refresh log, currently 2 days deep across 5 "advisor-" refreshes (4
   transitions). This is LIVE production refresh-to-refresh churn (same-day and next-day
   re-scoring of a ~400-name intraday universe), not the monthly backtest's churn. It is a
   legitimate, real, on-disk measurement of the same underlying mechanism (band quantization vs
   genuine change vs availability flicker) at a much shorter horizon, and it is what this script
   attributes. Read the two numbers as related evidence about the same suspected cause, not as
   the same statistic at different sample sizes.

Attribution buckets, computed per (ticker, metric) instance where a metric's *banded* score
(normalized_metric_scores, 0-100) changed between two consecutive refreshes for the champion
variant:

  (a) band_crossing_unchanged_value: the metric's *raw* input (raw_metric_inputs) changed by
      less than BAND_CROSSING_RELATIVE_THRESHOLD (2%, relative) between the two refreshes, yet
      its banded score moved. This is a discretization artifact: the metric barely moved and the
      band edge caught it anyway.
  (b) genuine_input_change: the raw input changed by 2% or more. A real change in the evidence.
  (c) availability_flicker: the metric flipped between present and missing (from
      decompose_score_delta(), already built and tested in stability_report.py).

  (d) price_driven_move: NOT a per-metric bucket -- it is the ticker-level residual of the
      overall champion score delta after subtracting the reconstructed fundamentals-weighted
      contribution (settings.json fundamentals.category_weights, blended at 0.78) and the
      modifier-total delta, both of which ARE present in the PIT store snapshot. What's left over
      is attributed to market_behavior + news (neither of which the snapshot schema tracks
      separately yet -- see docs/P0-Q2-TURNOVER.md for why, and what tracking them would take).
      This is a reconstruction, not a direct read, and is reported with that caveat.

"Total rank movement" (the denominator the brief asks the buckets be expressed against) is the
sum of |rank_delta| for tickers shared between two consecutive refreshes, ranked by champion
score within the shared set, at the top-100 depth (matching stability_report.py's existing
top_ns).

Usage: python pipeline/p0_q2_turnover_attribution.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from common import LOG, load_json  # noqa: E402
from stability_report import decompose_score_delta, load_refresh_rows  # noqa: E402

OUT_PATH = os.path.join(HERE, "reports", "turnover_attribution.json")
BAND_CROSSING_RELATIVE_THRESHOLD = 0.02
RANK_DEPTH = 100

SETTINGS = load_json("settings.json", from_config=True) or {}
CATEGORY_WEIGHTS = SETTINGS["fundamentals"]["category_weights"]
FUNDAMENTALS_WEIGHT = SETTINGS["ranking_weights"]["fundamentals"]


def _relative_change(before, after):
    if before is None or after is None:
        return None
    if before == 0:
        return None if after == 0 else float("inf")
    return abs(after - before) / abs(before)


def _rank_key(row):
    score = (row.get("scores") or {}).get("champion")
    return score if isinstance(score, (int, float)) else float("-inf")


def _ranks(rows_by_ticker):
    ordered = sorted(rows_by_ticker.items(), key=lambda item: (-_rank_key(item[1]), item[0]))
    return {ticker: index + 1 for index, (ticker, _row) in enumerate(ordered[:RANK_DEPTH])}


def _fundamentals_reconstruction(row):
    categories = (row.get("category_scores") or {}).get("champion") or {}
    weighted, weight_sum = 0.0, 0.0
    for category, weight in CATEGORY_WEIGHTS.items():
        if category in categories and isinstance(categories[category], (int, float)):
            weighted += weight * categories[category]
            weight_sum += weight
    if weight_sum == 0:
        return None
    return weighted / weight_sum  # coverage-shrunk average, matches the reweight-within-category rule


def attribute_transition(previous_rows, current_rows):
    previous_by_ticker = {row["ticker"]: row for row in previous_rows}
    current_by_ticker = {row["ticker"]: row for row in current_rows}
    shared = sorted(set(previous_by_ticker) & set(current_by_ticker))

    previous_ranks = _ranks(previous_by_ticker)
    current_ranks = _ranks(current_by_ticker)
    total_rank_movement = sum(
        abs(current_ranks[t] - previous_ranks[t])
        for t in shared if t in previous_ranks and t in current_ranks
    )

    counts = {"band_crossing_unchanged_value": 0, "genuine_input_change": 0, "availability_flicker": 0}
    price_driven_deltas = []
    for ticker in shared:
        previous_row, current_row = previous_by_ticker[ticker], current_by_ticker[ticker]
        decomposition = decompose_score_delta(previous_row, current_row, "champion")
        counts["availability_flicker"] += len(decomposition["metrics_with_availability_change"])

        previous_raw = previous_row.get("raw_metric_inputs") or {}
        current_raw = current_row.get("raw_metric_inputs") or {}
        for metric in decomposition["metrics_with_value_change"]:
            relative = _relative_change(previous_raw.get(metric), current_raw.get(metric))
            if relative is not None and relative < BAND_CROSSING_RELATIVE_THRESHOLD:
                counts["band_crossing_unchanged_value"] += 1
            else:
                counts["genuine_input_change"] += 1

        previous_fundamentals = _fundamentals_reconstruction(previous_row)
        current_fundamentals = _fundamentals_reconstruction(current_row)
        previous_modifier_total = ((previous_row.get("modifiers") or {}).get("champion") or {}).get("total")
        current_modifier_total = ((current_row.get("modifiers") or {}).get("champion") or {}).get("total")
        previous_score = (previous_row.get("scores") or {}).get("champion")
        current_score = (current_row.get("scores") or {}).get("champion")
        if None not in (previous_fundamentals, current_fundamentals, previous_modifier_total,
                        current_modifier_total, previous_score, current_score):
            fundamentals_contribution = FUNDAMENTALS_WEIGHT * (current_fundamentals - previous_fundamentals)
            modifier_contribution = current_modifier_total - previous_modifier_total
            overall_delta = current_score - previous_score
            residual = overall_delta - fundamentals_contribution - modifier_contribution
            price_driven_deltas.append(residual)

    total_events = sum(counts.values())
    return {
        "shared_tickers": len(shared),
        "total_rank_movement_top_100": total_rank_movement,
        "metric_level_events": counts,
        "metric_level_events_total": total_events,
        "metric_level_events_pct": {
            key: round(value / total_events, 4) if total_events else None
            for key, value in counts.items()
        },
        "price_driven_residual": {
            "tickers_measured": len(price_driven_deltas),
            "mean_abs_residual": (
                round(sum(abs(x) for x in price_driven_deltas) / len(price_driven_deltas), 4)
                if price_driven_deltas else None
            ),
            "note": "Reconstructed residual (overall champion score delta minus the "
                    "fundamentals- and modifier-weighted reconstruction), not a directly stored "
                    "market_behavior delta -- see script docstring.",
        },
    }


def main():
    by_refresh = load_refresh_rows()
    refresh_ids = sorted(by_refresh, key=lambda refresh_id: refresh_id.split("advisor-", 1)[-1])
    transitions = []
    for previous_id, current_id in zip(refresh_ids, refresh_ids[1:]):
        result = attribute_transition(by_refresh[previous_id], by_refresh[current_id])
        result["previous_refresh"] = previous_id
        result["current_refresh"] = current_id
        transitions.append(result)

    aggregate_counts = {"band_crossing_unchanged_value": 0, "genuine_input_change": 0, "availability_flicker": 0}
    for transition in transitions:
        for key, value in transition["metric_level_events"].items():
            aggregate_counts[key] += value
    aggregate_total = sum(aggregate_counts.values())

    output = {
        "note": "See pipeline/p0_q2_turnover_attribution.py docstring: this measures live "
                "refresh-to-refresh churn (2 days of PIT store, 4 transitions), NOT the "
                "backtest's monthly turnover directly, which requires network access this "
                "session does not have.",
        "refreshes_observed": len(refresh_ids),
        "transitions": transitions,
        "aggregate_metric_level_events": aggregate_counts,
        "aggregate_metric_level_events_pct": {
            key: round(value / aggregate_total, 4) if aggregate_total else None
            for key, value in aggregate_counts.items()
        },
        "band_crossing_relative_threshold": BAND_CROSSING_RELATIVE_THRESHOLD,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
    LOG.info(f"Wrote {OUT_PATH}")
    print(json.dumps(output["aggregate_metric_level_events_pct"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
