"""Shared machinery for grading a composite score's weighted sub-metrics, not just the blend
itself: does each metric predict on its own, and does the composite actually need it.

Reuses ``evaluation.py``'s ``per_leg_ic``/``drop_one_leg_delta_ic``/``leg_correlation_matrix``
directly - the same functions that already grade the main advisor composite's fundamentals
legs for ``signal_metrics.json`` (fed there by ``backtest_monthly.py``'s month-end panel).
This module is the other on-ramp into that same math: instead of a month-end panel, it builds
one from a point-in-time store shaped like ``theme_pit_store.py``'s (dated snapshots of
``{ticker, price, <metric fields>}``), the shape every screen-specific PIT store in this
pipeline already uses (``growth_pit_store.py``, and a per-screen one for anything else
that wants this).

Two questions per metric, matching what a weighted composite actually needs defended:
  * does this metric predict on its own (``per_leg_ic`` - its own rank IC against forward
    return, ignoring the blend entirely)
  * does the composite actually need it (``drop_one_leg_delta_ic`` - full composite IC minus
    the IC with that metric's weight removed and the rest renormalized over what remains; a
    *negative* delta means the composite predicts better once that metric is gone)

    from validation.composite_attribution import periods_from_snapshots, build_attribution_report
"""

from datetime import datetime, timezone

from evaluation import drop_one_leg_delta_ic, per_leg_ic


def periods_from_snapshots(snapshots, metric_fields, horizon_days):
    """One ``{leg_scores, forward_returns}`` period per (start, end) snapshot pair whose gap
    covers ``horizon_days`` - the same start/end pairing ``theme_ic.py``/``swing_ic.py`` use
    for a single score, generalized to a dict of metric scores per ticker so
    ``evaluation.py``'s leg-shaped functions can read it directly.
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
        leg_scores, forward_returns = {}, {}
        for row in start["rows"]:
            ticker = row.get("ticker")
            start_price = row.get("price")
            end_price = end_prices.get(ticker)
            if not ticker or not start_price or not end_price:
                continue
            scores = {metric: row[metric] for metric in metric_fields if row.get(metric) is not None}
            if not scores:
                continue
            leg_scores[ticker] = scores
            forward_returns[ticker] = end_price / start_price - 1
        if leg_scores:
            periods.append({"start_date": start["date"], "end_date": end["date"],
                            "leg_scores": leg_scores, "forward_returns": forward_returns})
    return periods


def build_attribution_report(periods, weights, *, minimum_periods=24, periods_per_year=12):
    """Composite-level rank IC plus, per weighted metric, its own standalone IC and its
    marginal (drop-one) impact on the composite - hidden behind the same eligibility gate
    every other prospective report here uses, so an early, noisy read never gets published as
    a conclusion.
    """
    per_leg = per_leg_ic(periods, list(weights), periods_per_year=periods_per_year)
    drop_one = drop_one_leg_delta_ic(periods, weights, periods_per_year=periods_per_year)
    composite_summary = drop_one["composite"]
    eligible = composite_summary["periods"] >= minimum_periods
    return {
        "eligible_periods": composite_summary["periods"],
        "minimum_icir_periods": minimum_periods,
        "status": "eligible" if eligible else "accumulating",
        "composite": {
            "mean_rank_ic": composite_summary["mean_ic"] if eligible else None,
            "icir": composite_summary["icir"] if eligible else None,
            "t_stat": composite_summary["t_stat"] if eligible else None,
            "hit_rate": composite_summary["hit_rate"] if eligible else None,
            "clears_multiple_testing_bar": composite_summary["clears_multiple_testing_bar"] if eligible else False,
        },
        "metrics": {
            leg: {
                "weight": weights.get(leg),
                "own_eligible_periods": (per_leg.get(leg) or {}).get("periods", 0),
                "own_rank_ic": (per_leg.get(leg) or {}).get("mean_ic") if eligible else None,
                "own_icir": (per_leg.get(leg) or {}).get("icir") if eligible else None,
                "delta_ic": (drop_one["legs"].get(leg) or {}).get("delta_ic") if eligible else None,
                "hurts_composite": (drop_one["legs"].get(leg) or {}).get("hurts_composite", False) if eligible else False,
            }
            for leg in weights
        },
    }
