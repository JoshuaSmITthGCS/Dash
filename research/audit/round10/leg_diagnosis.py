"""Round 10 - diagnose the leg and quantile-spread problem.

Diagnostic only: reads pipeline/backtest_signal_panel.json (the same panel
research/audit/round7/reweighting_backtest.py used) and pipeline/evaluation.py's existing
leg-diagnostic functions (per_leg_ic, drop_one_leg_delta_ic, composite_score, walk_forward).
Computes nothing that isn't already read-only over committed data; never writes to
pipeline/config, never touches production weights, never runs a live fetch.

Usage: PYTHONPATH=pipeline python3 research/audit/round10/leg_diagnosis.py
Output: research/audit/round10/leg_diagnosis_results.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.join(HERE, "..", "..", "..", "pipeline")
sys.path.insert(0, PIPELINE_DIR)

from evaluation import (composite_score, drop_one_leg_delta_ic, per_leg_ic,  # noqa: E402
                        quantile_buckets, quantile_spread, walk_forward)

PANEL_PATH = os.path.join(PIPELINE_DIR, "backtest_signal_panel.json")
OUT_PATH = os.path.join(HERE, "leg_diagnosis_results.json")

DRAG_LEGS = ("growth", "news_sentiment", "capital_allocation", "accounting_quality")
NON_DRAG_LEGS = ("valuation", "profitability", "financial_health", "market_behavior")
A1_DECLARED_AT = "2026-08-07"
NEUTRAL_NEWS_SCORE = 50.0


def leg_coverage(periods, legs):
    """Fraction of ticker-periods where a leg resolved a real number, per leg."""
    coverage = {}
    for leg in legs:
        present = total = 0
        for period in periods:
            for scores in (period.get("leg_scores") or {}).values():
                total += 1
                if isinstance(scores.get(leg), (int, float)):
                    present += 1
        coverage[leg] = {"present": present, "total": total,
                         "coverage_pct": round(100 * present / total, 1) if total else None}
    return coverage


def per_leg_ic_all_horizons(periods, legs, horizon_field):
    """per_leg_ic re-run once per horizon by substituting forward_returns_by_horizon[h]."""
    output = {}
    for horizon in horizon_field:
        substituted = [{**period, "forward_returns": (period.get("forward_returns_by_horizon") or {}).get(horizon, {})}
                      for period in periods]
        output[horizon] = per_leg_ic(substituted, legs=legs)
    return output


def news_sentiment_neutral_pileup(periods):
    """How much of the news_sentiment leg's history sits exactly at the old neutral default.

    A1-NEWS-NEUTRAL (pipeline/experiment_registry.py) fixed weighted_sentiment defaulting
    zero-coverage names to 50.0 instead of publishing unavailable. That fix landed
    2026-08-07; this panel (backtest_signal_panel.json) carries monthly periods back to
    2021-08 read from the point-in-time store, which is append-only, so a period dated
    before the fix cannot retroactively reflect it even though the panel *file* itself was
    reassembled afterward. This measures the pileup directly rather than assuming either way.
    """
    before, after, before_at_neutral, after_at_neutral = 0, 0, 0, 0
    for period in periods:
        is_after = str(period.get("date") or "") >= A1_DECLARED_AT
        for scores in (period.get("leg_scores") or {}).values():
            value = scores.get("news_sentiment")
            if not isinstance(value, (int, float)):
                continue
            at_neutral = abs(value - NEUTRAL_NEWS_SCORE) < 1e-6
            if is_after:
                after += 1
                after_at_neutral += at_neutral
            else:
                before += 1
                before_at_neutral += at_neutral
    return {
        "periods_before_a1": sum(1 for p in periods if str(p.get("date") or "") < A1_DECLARED_AT),
        "periods_on_or_after_a1": sum(1 for p in periods if str(p.get("date") or "") >= A1_DECLARED_AT),
        "before_a1": {"observations": before, "at_neutral_50": before_at_neutral,
                      "pileup_pct": round(100 * before_at_neutral / before, 1) if before else None},
        "on_or_after_a1": {"observations": after, "at_neutral_50": after_at_neutral,
                           "pileup_pct": round(100 * after_at_neutral / after, 1) if after else None},
    }


def diagnostic_quantile_spread(periods, weights, legs_to_use, quantiles=5):
    """walk_forward's mean_quantile_spread for a composite built from only `legs_to_use`.

    Renormalized over legs_to_use (composite_score already renormalizes over whichever legs
    it is handed), so this is a genuine "what if only these legs existed" reading, not the
    full composite with the others silently zeroed in the denominator too.
    """
    restricted_weights = {leg: weight for leg, weight in weights.items() if leg in legs_to_use}
    synthetic_periods = []
    for period in periods:
        leg_scores = period.get("leg_scores") or {}
        scores = {ticker: composite_score(scores_for_ticker, restricted_weights)
                  for ticker, scores_for_ticker in leg_scores.items()}
        scores = {ticker: value for ticker, value in scores.items() if value is not None}
        synthetic_periods.append({"date": period.get("date"), "scores": scores,
                                  "forward_returns": period.get("forward_returns") or {}})
    return walk_forward(synthetic_periods, quantiles=quantiles)


def quantile_membership_turnover(periods, weights, quantiles=5):
    """Consecutive-period Jaccard turnover of the top and bottom quantile membership sets.

    Low turnover (sets barely change month to month) would mute any spread individual-name
    dispersion could otherwise produce, independent of whether the score itself is any good;
    high turnover with a flat spread points at the legs themselves instead.
    """
    membership = []
    for period in periods:
        leg_scores = period.get("leg_scores") or {}
        forwards = period.get("forward_returns") or {}
        scores = {ticker: composite_score(scores_for_ticker, weights)
                  for ticker, scores_for_ticker in leg_scores.items()}
        tickers = [ticker for ticker in scores if scores[ticker] is not None and ticker in forwards]
        if len(tickers) < quantiles * 2:
            membership.append(None)
            continue
        ordered = sorted(tickers, key=lambda ticker: scores[ticker], reverse=True)
        size = len(ordered) // quantiles
        membership.append({"top": set(ordered[:size]), "bottom": set(ordered[-size:])})

    def jaccard(a, b):
        if not a and not b:
            return None
        union = a | b
        return round(len(a & b) / len(union), 4) if union else None

    top_turnover, bottom_turnover = [], []
    for previous, current in zip(membership, membership[1:]):
        if previous is None or current is None:
            continue
        top_turnover.append(jaccard(previous["top"], current["top"]))
        bottom_turnover.append(jaccard(previous["bottom"], current["bottom"]))
    return {
        "periods_compared": len(top_turnover),
        "mean_top_quintile_overlap_with_prior_period": round(sum(top_turnover) / len(top_turnover), 4) if top_turnover else None,
        "mean_bottom_quintile_overlap_with_prior_period": round(sum(bottom_turnover) / len(bottom_turnover), 4) if bottom_turnover else None,
        "note": "Overlap near 1.0 means the same names stay in the bucket; near 0 means full turnover each period.",
    }


def main():
    from panel_io import load_panel
    panel = load_panel(PANEL_PATH)
    if panel is None:
        raise SystemExit(f"panel not found at {PANEL_PATH}(.gz)")
    periods = panel["periods"]
    weights = panel["leg_weights"]
    horizon_field = panel["horizon_trading_days"]
    legs = sorted(weights)

    report = {
        "panel_generated_at": panel["generated_at"],
        "panel_periods": len(periods),
        "panel_date_range": [periods[0]["date"], periods[-1]["date"]] if periods else None,
        "leg_weights": weights,
        "leg_coverage": leg_coverage(periods, legs),
        "per_leg_ic_primary_horizon_21d": per_leg_ic(periods, legs=legs),
        "per_leg_ic_all_horizons": per_leg_ic_all_horizons(periods, DRAG_LEGS, horizon_field),
        "drop_one_leg_delta_ic": drop_one_leg_delta_ic(periods, weights),
        "news_sentiment_neutral_pileup": news_sentiment_neutral_pileup(periods),
        "quantile_spread_full_composite": diagnostic_quantile_spread(periods, weights, legs),
        "quantile_spread_non_drag_legs_only": diagnostic_quantile_spread(periods, weights, NON_DRAG_LEGS),
        "quantile_membership_turnover_full_composite": quantile_membership_turnover(periods, weights),
    }

    os.makedirs(HERE, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
        handle.write("\n")

    print(f"Panel: {report['panel_periods']} periods, {report['panel_date_range']}")
    print("\nLeg coverage:")
    for leg, stats in report["leg_coverage"].items():
        flag = " <-- drag leg" if leg in DRAG_LEGS else ""
        print(f"  {leg:<20} {stats['coverage_pct']}% ({stats['present']}/{stats['total']}){flag}")
    print("\nDrop-one-leg delta IC (21d horizon):")
    for leg, stats in report["drop_one_leg_delta_ic"]["legs"].items():
        flag = " <-- drag leg" if leg in DRAG_LEGS else ""
        print(f"  {leg:<20} delta {stats['delta_ic']}  hurts_composite={stats['hurts_composite']}{flag}")
    print(f"\nFull composite IC (21d): {report['drop_one_leg_delta_ic']['composite']['mean_ic']}"
          f" (t={report['drop_one_leg_delta_ic']['composite']['t_stat']})")
    print("\nPer-horizon IC for the 4 flagged drag legs:")
    for horizon, per_leg in report["per_leg_ic_all_horizons"].items():
        print(f"  {horizon}:")
        for leg in DRAG_LEGS:
            stats = per_leg.get(leg, {})
            print(f"    {leg:<20} mean_ic={stats.get('mean_ic')} periods={stats.get('periods')}")
    pileup = report["news_sentiment_neutral_pileup"]
    print(f"\nnews_sentiment neutral-50 pileup: before A1 (n={pileup['before_a1']['observations']}) "
          f"{pileup['before_a1']['pileup_pct']}% at exactly 50.0; "
          f"on/after A1 (n={pileup['on_or_after_a1']['observations']}) "
          f"{pileup['on_or_after_a1']['pileup_pct']}% at exactly 50.0")
    full_spread = report["quantile_spread_full_composite"]["mean_quantile_spread"]
    non_drag_spread = report["quantile_spread_non_drag_legs_only"]["mean_quantile_spread"]
    print(f"\nMean quantile spread, full 8-leg composite:  {full_spread}")
    print(f"Mean quantile spread, 4 non-drag legs only:  {non_drag_spread}")
    turnover = report["quantile_membership_turnover_full_composite"]
    print(f"\nTop-quintile month-over-month overlap: {turnover['mean_top_quintile_overlap_with_prior_period']}")
    print(f"Bottom-quintile month-over-month overlap: {turnover['mean_bottom_quintile_overlap_with_prior_period']}")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
