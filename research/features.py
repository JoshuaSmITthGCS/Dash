"""Phase 5: which of the model's inputs carry information, and which repeat each other.

The live model scores thirty-two metrics, weights them inside six categories, and weights the
categories into one number. Phase 4 measured five textbook factors and Phase 6 measured the
whole composite. Neither says which of the thirty-two are doing work. This does.

Three measurements per metric, and one across them:

**Information coefficient.** The rank correlation between a metric's *scored* value on a date
and the return over the following month, computed per date and then summarised across dates.
Scored rather than raw on purpose: the live model does not rank on return-on-invested-capital,
it ranks on the 0-100 band score it assigns to return-on-invested-capital, so the cutoffs are
under test as much as the metric. A metric whose raw ordering predicts returns but whose bands
flatten it into three values is a metric the model has broken, and only the scored reading
shows that.

**Decile ladders, in return and in Sharpe.** Phase 4's correction is the reason both are here.
Return-on-invested-capital's return ladder is U-shaped and reads as no signal; its Sharpe
ladder runs 1.29 down to 0.94 and reads as a good signal whose bottom decile is simply risky.
A monotonicity computed on returns alone scores those identically.

**Redundancy.** The average cross-sectional rank correlation between every pair of scored
metrics. Two metrics correlated at 0.9 that each carry 10% of a category are not two
independent 10% opinions; they are one opinion at 20%, and the model's stated weights are not
its effective weights. Phase 0 asserted this was happening. This measures it.

**Multiple testing.** Thirty-two metrics tested at once will produce apparent winners from
noise alone. Rebalances are spaced a full holding period apart, so the per-date coefficients
do not overlap and the t-statistic is honest for a single metric -- but a threshold of two is
not honest across thirty-two. Both are reported, and the Bonferroni one is the one that means
anything.

Nothing here is tuned, fitted, or selected on. It is a description of inputs the model already
has, measured on data it has never been measured on.
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
from scorer import SCORED_METRICS, SETTINGS, _band_valuation_score  # noqa: E402

from baselines import (DECILES, MINIMUM_CROSS_SECTION, TRADING_DAYS,  # noqa: E402
                       _monotonicity, _share_basis, _split_into_deciles, annualised,
                       decile_risk, forward_return, price_context)
from composite import PERIODS_PER_YEAR, THREE_YEARS, _sectors, _shift_years, snapshot  # noqa: E402
from rank_statistics import bonferroni_threshold, spearman, summarise_series  # noqa: E402

# A pair of metrics must co-occur on this many names before their correlation is recorded.
# Two metrics overlapping on twenty companies can correlate at 0.9 by accident.
MINIMUM_PAIR_OVERLAP = 100

# Two-sided 5% for one test. Across thirty-two metrics the honest threshold is this scaled by
# Bonferroni, computed below -- reporting only the nominal one is how a research programme
# talks itself into discoveries it does not have.
NOMINAL_T = 1.96

# Above this average rank correlation, two metrics are not two opinions.
REDUNDANT_AT = 0.7


def metric_weight_in_model(metric):
    """The share of the total score this metric carries, per the live configuration."""
    cfg = SETTINGS["fundamentals"]
    for category, weights in cfg["metric_weights"].items():
        if metric in weights:
            return {"category": category,
                    "weight_in_category": weights[metric],
                    "weight_in_score": cfg["category_weights"].get(category, 0) * weights[metric]}
    return {"category": None, "weight_in_category": None, "weight_in_score": 0.0}


def run(*, start="2017-01-01", end="2026-06-01", every_days=21, horizon_days=21,
        universe_limit=None, store_dir=None, cache_dir=None):
    """Per-metric information, decile behaviour and redundancy, on point-in-time data."""
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
    information = {metric: [] for metric in metrics}
    coverage = {metric: [] for metric in metrics}
    constant = {metric: 0 for metric in metrics}
    deciles = {metric: [[] for _ in range(DECILES)] for metric in metrics}
    pairs = {}
    history, dates_used = {}, []

    for index, when in enumerate(full_grid):
        trading = index >= len(warmup) - 1
        members, _ = universe_as_of(when, prices=prices, cik_by_ticker=cik_by_ticker,
                                    last_filings=filings)
        tradable = set(members)
        current, scored, forwards = {}, {}, {}
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
            scored[ticker] = detail
            forwards[ticker] = forward

        for ticker, derived in current.items():
            history[(index, ticker)] = derived
        for stale in [key for key in history if key[0] < index - THREE_YEARS]:
            del history[stale]
        if not trading or len(forwards) < MINIMUM_CROSS_SECTION:
            continue
        dates_used.append(when)

        columns = {}
        for metric in metrics:
            present = [(ticker, detail[metric]) for ticker, detail in scored.items()
                       if detail.get(metric) is not None]
            coverage[metric].append(len(present) / len(scored) if scored else 0.0)
            if len(present) < MINIMUM_CROSS_SECTION:
                continue
            columns[metric] = dict(present)
            values = [value for _, value in present]
            returns = [forwards[ticker] for ticker, _ in present]
            coefficient = spearman(values, returns)
            if coefficient is None:
                # Every company scored identically: the bands collapsed the cross-section.
                constant[metric] += 1
                continue
            information[metric].append(coefficient)
            ordered = sorted(columns[metric], key=lambda t: columns[metric][t], reverse=True)
            for bucket_index, bucket in enumerate(_split_into_deciles(ordered)):
                if bucket:
                    deciles[metric][bucket_index].append(
                        statistics.mean(forwards[t] for t in bucket))

        names = sorted(columns)
        for first_index, first in enumerate(names):
            for second in names[first_index + 1:]:
                shared = [t for t in columns[first] if t in columns[second]]
                if len(shared) < MINIMUM_PAIR_OVERLAP:
                    continue
                coefficient = spearman([columns[first][t] for t in shared],
                                       [columns[second][t] for t in shared])
                if coefficient is not None:
                    pairs.setdefault((first, second), []).append(coefficient)

    periods_per_year = TRADING_DAYS / every_days
    bonferroni_t = bonferroni_threshold(len(metrics))

    results = {}
    for metric in metrics:
        summary = summarise_series(information[metric])
        summary.update(metric_weight_in_model(metric))
        summary["median_coverage"] = (statistics.median(coverage[metric])
                                      if coverage[metric] else 0.0)
        summary["dates_with_no_variation"] = constant[metric]
        ladder = [annualised(bucket, periods_per_year) if bucket else None
                  for bucket in deciles[metric]]
        summary["decile_cagr"] = ladder
        summary["decile_risk"] = decile_risk(deciles[metric], periods_per_year)
        summary["decile_monotonicity"] = _monotonicity(ladder)
        summary["sharpe_monotonicity"] = _monotonicity(
            [entry["sharpe"] if entry else None for entry in summary["decile_risk"]])
        t_statistic = summary.get("t_statistic")
        summary["significant_nominally"] = (t_statistic is not None
                                            and abs(t_statistic) > NOMINAL_T)
        summary["significant_after_multiple_testing"] = (t_statistic is not None
                                                         and abs(t_statistic) > bonferroni_t)
        results[metric] = summary

    redundant = []
    for (first, second), values in pairs.items():
        if len(values) < 12:
            continue
        average = statistics.mean(values)
        if abs(average) >= REDUNDANT_AT:
            redundant.append({
                "metrics": [first, second],
                "average_rank_correlation": average,
                "dates": len(values),
                "combined_weight_in_score": (metric_weight_in_model(first)["weight_in_score"]
                                             + metric_weight_in_model(second)["weight_in_score"]),
                "same_category": (metric_weight_in_model(first)["category"]
                                  == metric_weight_in_model(second)["category"]),
            })
    redundant.sort(key=lambda row: -abs(row["average_rank_correlation"]))

    return {
        "settings": {"start": start, "end": end, "rebalance_every_days": every_days,
                     "holding_days": horizon_days, "metrics_tested": len(metrics),
                     "nominal_t": NOMINAL_T, "bonferroni_t": bonferroni_t,
                     "redundant_at": REDUNDANT_AT},
        "dates": len(dates_used),
        "results": results,
        "redundant_pairs": redundant,
        "how_to_read": (
            "mean_ic is the average rank correlation between a metric's scored value and the "
            "next month's return; positive means the model's scoring of it points the right "
            "way. t_statistic uses non-overlapping rebalances, so it is not inflated by "
            "reusing returns, but thirty-two metrics were tested together and only "
            "significant_after_multiple_testing should be treated as a result. "
            "dates_with_no_variation counts rebalances where every company received the same "
            "score for that metric -- a band configuration that cannot rank anything. "
            "sharpe_monotonicity is the ladder measure that survives the Phase 4 correction: "
            "a factor can look flat in return while sorting cleanly in risk-adjusted terms."),
        "limitations": [
            "Survivorship: measured on companies that still have a price feed today.",
            "Four inputs cannot be reconstructed point-in-time (forward_pe, peg, "
            "earnings_surprise, altman_z) and are absent throughout rather than tested.",
            "One regime, roughly nine years. A metric that failed here failed in this sample.",
            "Redundancy is measured on scored values, which is what the model actually adds "
            "up. Two metrics can be redundant after banding without being redundant before.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
