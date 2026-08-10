"""Phase 5b: are the band cutoffs destroying information the metrics actually carry?

Phase 5 measured every metric as the live model ranks it -- through the 0-100 band score the
scorer assigns. Return on invested capital came back at t = +0.5, nothing. Phase 4 measured the
same quantity *raw*, on the same data over the same window, and its top decile ran at a Sharpe
of 1.29 against the universe's 0.99.

Same input, same period, opposite readings. The only thing between them is the band
configuration. If that is what costs the signal, the remedy is recalibrating cutoffs, which is
a smaller and far safer change than reweighting or removing anything. If it is not, then
cheapness and quality genuinely did not rank stocks over this window, and no amount of
threshold-tuning will fix that. Those two conclusions look identical from outside and lead
opposite places, which is why this measurement exists.

The method is one pass, two rankings:

* **Raw**: the underlying value straight out of the point-in-time snapshot.
* **Scored**: what ``scorer._band_valuation_score`` made of it.

Both are ranked against the same forward returns, over the same companies, on the same dates,
so nothing but the banding differs.

**Direction is inferred, not declared.** Whether a metric is better high or better low is read
each period from the cross-sectional correlation between its raw and scored values -- the bands
themselves say which way the model reads it. Hardcoding a direction table would drift out of
step with ``settings.json`` the first time a cutoff was edited, and would silently invert a
metric's information coefficient when it did. Inference also identifies the two-tailed metrics
for free: ``asset_growth`` and ``capex_to_depreciation`` penalise both extremes, so their raw
values have no monotone direction, their raw-versus-scored comparison is not defined, and they
are reported as such rather than forced onto a line.

What a result means:

* raw IC well above scored IC -- the bands are throwing away information. Recalibrate cutoffs.
* the two close together -- the bands are faithful; the metric itself is what it is.
* scored IC above raw IC -- the bands are adding information, most likely by capping outliers
  that a rank correlation would otherwise be dragged around by.
"""

import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pit_derive import derive  # noqa: E402
from pit_market import (load_universe_prices, last_filing_dates,  # noqa: E402
                        rebalance_dates, universe_as_of)
from pit_fundamentals_store import ShardedStore  # noqa: E402
from pit_shares import shares_as_of  # noqa: E402
from scorer import SCORED_METRICS, _band_valuation_score  # noqa: E402

from baselines import (MINIMUM_CROSS_SECTION, _share_basis, forward_return,  # noqa: E402
                       price_context)
from composite import PERIODS_PER_YEAR, THREE_YEARS, _sectors, _shift_years, snapshot  # noqa: E402
from features import metric_weight_in_model  # noqa: E402
from rank_statistics import bonferroni_threshold, spearman, summarise_series  # noqa: E402

# The snapshot field a metric is built from, where the scorer's name for it differs. Only
# sales_multiple diverges: the scorer prefers an enterprise-value basis and falls back to a
# price basis, and reports the choice separately.
RAW_FIELD = {"sales_multiple": "ev_to_sales"}

# Below this, the raw-to-scored correlation is too weak to call a direction. A two-tailed
# metric lands here by construction, which is the point -- it has no monotone direction to
# infer, and forcing one would manufacture an information coefficient out of a sign choice.
DIRECTIONAL_AT = 0.3

# How much raw must beat scored, in information coefficient, before the bands are worth
# blaming. Below this the two readings are the same measurement twice.
MATERIAL_GAP = 0.005


def infer_direction(raw_values, scored_values):
    """Which way the live bands read a metric, +1 or -1, or None where they are two-tailed.

    Read from the model's own output rather than declared here, so it cannot drift out of step
    with ``settings.json`` the moment a cutoff is edited.
    """
    shared = [ticker for ticker in raw_values if ticker in scored_values]
    if len(shared) < MINIMUM_CROSS_SECTION:
        return None
    correlation = spearman([raw_values[ticker] for ticker in shared],
                           [scored_values[ticker] for ticker in shared])
    if correlation is None or abs(correlation) < DIRECTIONAL_AT:
        return None
    return 1 if correlation > 0 else -1


def verdict(raw, scored):
    """What the pair of information coefficients says about the band configuration."""
    if raw is None or scored is None:
        return "not_comparable"
    gap = raw - scored
    if gap > MATERIAL_GAP:
        return "bands_cost_information"
    if gap < -MATERIAL_GAP:
        return "bands_add_information"
    return "bands_faithful"


def run(*, start="2017-01-01", end="2026-06-01", every_days=21, horizon_days=21,
        universe_limit=None, store_dir=None, cache_dir=None):
    """Raw versus banded information coefficient for every metric, same dates and universe."""
    store = ShardedStore(store_dir or os.path.join(ROOT, "pipeline", "data", "pit", "fundamentals"))
    observations = store.load()
    by_cik = {}
    for row in observations:
        by_cik.setdefault(row["cik"], []).append(row)
    filings = last_filing_dates(observations)

    with open(os.path.join(ROOT, "pipeline", "data", "pit", "entity_audit.json"),
              encoding="utf-8") as handle:
        cik_by_ticker = json.load(handle)["resolved_map"]
    if universe_limit:
        cik_by_ticker = dict(list(cik_by_ticker.items())[:universe_limit])
    prices = load_universe_prices(cik_by_ticker, cache_dir)
    share_basis = {cik: _share_basis(rows) for cik, rows in by_cik.items()}
    sectors = _sectors(cik_by_ticker, cache_dir)

    grid = rebalance_dates(start, end, every_days=every_days)
    warmup = rebalance_dates(_shift_years(start, THREE_YEARS // PERIODS_PER_YEAR), start,
                             every_days=every_days)
    full_grid = warmup[:-1] + grid

    metrics = list(SCORED_METRICS)
    raw_ic = {metric: [] for metric in metrics}
    scored_ic = {metric: [] for metric in metrics}
    directions = {metric: [] for metric in metrics}
    matched_dates = {metric: 0 for metric in metrics}
    history, dates_used = {}, []

    for index, when in enumerate(full_grid):
        trading = index >= len(warmup) - 1
        members, _ = universe_as_of(when, prices=prices, cik_by_ticker=cik_by_ticker,
                                    last_filings=filings)
        tradable = set(members)
        current, snaps, scores, forwards = {}, {}, {}, {}
        for ticker in cik_by_ticker:
            cik = cik_by_ticker[ticker]
            derived = derive(by_cik.get(cik, []), when, cik=cik)
            current[ticker] = derived
            if not trading or ticker not in tradable:
                continue
            forward = forward_return(prices[ticker], when, horizon_days)
            if forward is None:
                continue
            context = price_context(prices[ticker], when,
                                    shares=shares_as_of(share_basis.get(cik, []), when))
            snap = snapshot(derived, history.get((index - PERIODS_PER_YEAR, ticker)),
                            history.get((index - THREE_YEARS, ticker)),
                            context, sectors.get(ticker), ticker)
            total, detail = _band_valuation_score(snap)
            if total is None:
                continue
            snaps[ticker], scores[ticker], forwards[ticker] = snap, detail, forward

        for ticker, derived in current.items():
            history[(index, ticker)] = derived
        for stale in [key for key in history if key[0] < index - THREE_YEARS]:
            del history[stale]
        if not trading or len(forwards) < MINIMUM_CROSS_SECTION:
            continue
        dates_used.append(when)

        for metric in metrics:
            field = RAW_FIELD.get(metric, metric)
            raw_values = {ticker: snap[field] for ticker, snap in snaps.items()
                          if snap.get(field) is not None}
            scored_values = {ticker: detail[metric] for ticker, detail in scores.items()
                             if detail.get(metric) is not None}
            # The same companies for both readings. A metric scored for a company whose raw
            # value is absent -- or the reverse -- would otherwise compare two populations and
            # call the difference an effect of banding.
            shared = [ticker for ticker in raw_values if ticker in scored_values]
            if len(shared) < MINIMUM_CROSS_SECTION:
                continue
            direction = infer_direction(raw_values, scored_values)
            directions[metric].append(direction)
            if direction is None:
                continue
            matched_dates[metric] += 1
            returns = [forwards[ticker] for ticker in shared]
            raw_coefficient = spearman([raw_values[ticker] * direction for ticker in shared],
                                       returns)
            scored_coefficient = spearman([scored_values[ticker] for ticker in shared], returns)
            if raw_coefficient is not None:
                raw_ic[metric].append(raw_coefficient)
            if scored_coefficient is not None:
                scored_ic[metric].append(scored_coefficient)

    results = {}
    for metric in metrics:
        raw_summary = summarise_series(raw_ic[metric])
        scored_summary = summarise_series(scored_ic[metric])
        raw_mean, scored_mean = raw_summary.get("mean_ic"), scored_summary.get("mean_ic")
        resolved = [value for value in directions[metric] if value is not None]
        entry = {
            "comparable_dates": matched_dates[metric],
            "direction": (statistics.mode(resolved) if resolved else None),
            "two_tailed": bool(directions[metric]) and not resolved,
            "raw": raw_summary,
            "scored": scored_summary,
            "ic_gap_raw_minus_scored": (None if raw_mean is None or scored_mean is None
                                        else raw_mean - scored_mean),
            "verdict": verdict(raw_mean, scored_mean),
        }
        entry.update(metric_weight_in_model(metric))
        results[metric] = entry

    costly = sorted((entry for entry in results.values()
                     if entry["verdict"] == "bands_cost_information"),
                    key=lambda entry: -(entry["ic_gap_raw_minus_scored"] or 0))
    return {
        "settings": {"start": start, "end": end, "rebalance_every_days": every_days,
                     "holding_days": horizon_days, "directional_threshold": DIRECTIONAL_AT,
                     "material_gap": MATERIAL_GAP,
                     "bonferroni_t": bonferroni_threshold(len(metrics))},
        "dates": len(dates_used),
        "results": results,
        "summary": {
            "bands_cost_information": sum(1 for entry in results.values()
                                          if entry["verdict"] == "bands_cost_information"),
            "bands_faithful": sum(1 for entry in results.values()
                                  if entry["verdict"] == "bands_faithful"),
            "bands_add_information": sum(1 for entry in results.values()
                                         if entry["verdict"] == "bands_add_information"),
            "not_comparable": sum(1 for entry in results.values()
                                  if entry["verdict"] == "not_comparable"),
            "weight_on_metrics_whose_bands_cost_information": sum(
                entry["weight_in_score"] for entry in costly),
        },
        "how_to_read": (
            "Both columns rank the same companies against the same forward returns on the same "
            "dates; only the banding differs. raw is the underlying value, signed by the "
            "direction the live bands themselves imply. A raw information coefficient well "
            "above the scored one means the cutoffs are discarding information the metric "
            "carries, and the remedy is recalibration rather than reweighting. The two close "
            "together means the bands are faithful and the metric is simply what it is."),
        "limitations": [
            "Survivorship, one regime, and the same statistical power limit as Phase 5: this "
            "sample cannot resolve an information coefficient below roughly 0.028 after "
            "multiple-testing correction, and every effect here is smaller than that.",
            "A gap in information coefficient is evidence about ranking, not proof that a "
            "recalibrated band would earn the difference. Any proposed cutoff change still "
            "has to survive the design/test split in research/candidate.py.",
            "Two-tailed metrics have no monotone raw direction and are reported as "
            "not_comparable rather than forced onto a line.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
