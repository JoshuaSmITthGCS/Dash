"""Phase 6b: a candidate ranking, designed on one half of the history and tested on the other.

The live composite's top twenty returned 19.2% a year over 2017-2026 while equal-weighting the
universe returned 18.0%. The brief for this module is to beat that. The brief for the
*engagement* is not to lie about having done so, and those two pull against each other hard
enough that the guard has to be structural rather than a promise.

**The guard.** The window is cut in half. Every candidate is measured on the design half
(2017 to 2021); the selection rule picks a winner from those numbers alone, in code, before
the test half is read; the reported result is that one candidate's performance over the test
half (2022 to 2026), which nothing in the design saw. Report the design half's winner
performance and you have reported the maximum of eight noisy numbers, which is a statistic
about searching, not about investing.

**The selection rule, fixed here rather than chosen afterwards.** Highest Sharpe-decile
monotonicity on the design half, tie-broken by top-decile Sharpe. Not top-twenty return:
Phase 4 found three factors that beat the universe in a concentrated portfolio while failing to
rank the cross-section at all, and a concentrated return is the most overfittable number
available.

**The candidates, and why these eight.** Each comes from a measurement already made, not from a
search. Momentum and return on invested capital both sorted on their own (Phase 4: top-decile
Sharpe 1.40 and 1.29 against the universe's 0.99), and their combination sorted best of
anything measured (+0.81 monotonicity). Valuation inverted through four independent multiples
(Phase 5), so one candidate removes it from the live model and changes nothing else. Eight is
few on purpose: each additional candidate raises the chance the winner is lucky, and with a
single test half there is no second chance to find out.

Two constructions use **raw** metrics rather than the live model's band scores, because Phase 5
left an open question worth answering here: scored return on invested capital measured at
t = +0.5, nothing, while Phase 4's raw version had a top-decile Sharpe of 1.29. If the raw
constructions beat the banded one on the same data, the cutoffs are the defect and recalibrating
them is a smaller, safer change than reweighting anything.
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
from scorer import SETTINGS, _band_valuation_score, weighted_available  # noqa: E402

from baselines import (DECILES, MINIMUM_CROSS_SECTION, TRADING_DAYS,  # noqa: E402
                       _monotonicity, _share_basis, _split_into_deciles, annualised,
                       decile_risk, forward_return, price_context, summarise)
from composite import PERIODS_PER_YEAR, THREE_YEARS, _sectors, _shift_years, snapshot  # noqa: E402

# The cut. Everything before it designs; everything after it reports. Chosen as the midpoint of
# the tradeable window rather than for what it does to any result.
DESIGN_ENDS = "2021-07-01"


def percentile_ranks(values):
    """Cross-sectional percentile of each name, 0 worst to 1 best, ties averaged.

    Rank rather than z-score throughout: a percentile is immune to the outliers that a
    fundamentals feed produces routinely, and needs no winsorisation constant to argue about.
    """
    present = [(name, value) for name, value in values.items() if value is not None]
    if len(present) < MINIMUM_CROSS_SECTION:
        return {}
    present.sort(key=lambda row: row[1])
    ranks, index = {}, 0
    while index < len(present):
        end = index
        while end + 1 < len(present) and present[end + 1][1] == present[index][1]:
            end += 1
        shared = (index + end) / 2.0
        for position in range(index, end + 1):
            ranks[present[position][0]] = shared / max(len(present) - 1, 1)
        index = end + 1
    return ranks


def _blend(*rank_maps):
    """Average percentile across signals, for names present in all of them."""
    if not rank_maps or any(not row for row in rank_maps):
        return {}
    shared = set(rank_maps[0])
    for row in rank_maps[1:]:
        shared &= set(row)
    return {name: statistics.mean(row[name] for row in rank_maps) for name in shared}


def composite_without_valuation(detail):
    """The live model with the valuation category removed and the rest renormalised.

    The smallest change that acts on Phase 5's clearest finding. Every band, every metric
    weight and every other category stays exactly as configured; only the 28% on valuation is
    redistributed across the five remaining categories in their existing proportions.
    """
    cfg = SETTINGS["fundamentals"]
    categories = {name: value for name, value in (detail.get("categories") or {}).items()
                  if name != "valuation"}
    weights = {name: weight for name, weight in cfg["category_weights"].items()
               if name != "valuation"}
    return weighted_available(categories, weights)


def candidates(*, raw, banded):
    """Every candidate's score for one rebalance date, keyed by name.

    ``raw`` holds percentile ranks of raw point-in-time metrics; ``banded`` holds the live
    model's own outputs. Nothing here is fitted -- each entry is a stated hypothesis.
    """
    momentum = raw.get("momentum_12_1", {})
    roic = raw.get("return_on_invested_capital", {})
    gross = raw.get("gross_profits_to_assets", {})
    accruals = raw.get("low_accruals", {})
    return {
        # References, so the report compares like with like in the same window.
        "live_composite": banded.get("composite", {}),
        "live_composite_raw_score": banded.get("composite_raw", {}),
        # The one-line change to the live model.
        "composite_without_valuation": banded.get("without_valuation", {}),
        # Constructions from raw metrics, motivated by Phase 4's risk-adjusted ladders.
        "momentum_only": momentum,
        "roic_only": roic,
        "roic_and_momentum": _blend(roic, momentum),
        "roic_momentum_gross_profits": _blend(roic, momentum, gross),
        "roic_momentum_accruals": _blend(roic, momentum, accruals),
    }


CANDIDATE_NAMES = ("live_composite", "live_composite_raw_score", "composite_without_valuation",
                   "momentum_only", "roic_only", "roic_and_momentum",
                   "roic_momentum_gross_profits", "roic_momentum_accruals")

# Candidates that are references rather than proposals. They are measured identically and
# excluded from selection, because "the thing we are trying to beat" winning its own bake-off
# would not be a selection.
REFERENCES = ("live_composite", "live_composite_raw_score")


def select(design_results):
    """The winner, by the rule stated in this module's docstring and applied mechanically.

    Takes design-half statistics only. Returns ``(name, reason)``.
    """
    ranked = []
    for name, stats in design_results.items():
        if name in REFERENCES:
            continue
        monotonicity = stats.get("sharpe_monotonicity")
        risk = stats.get("decile_risk") or []
        top = risk[0]["sharpe"] if risk and risk[0] and risk[0].get("sharpe") else None
        if monotonicity is None or top is None:
            continue
        ranked.append((monotonicity, top, name))
    if not ranked:
        return None, "no candidate produced a usable ladder on the design half"
    ranked.sort(reverse=True)
    monotonicity, top, name = ranked[0]
    return name, (f"highest Sharpe-decile monotonicity on the design half "
                  f"({monotonicity:+.2f}), top-decile Sharpe {top:.2f}")


def _statistics(period_returns, deciles, periods_per_year, *, costs_bps):
    summary = summarise(period_returns, periods_per_year, costs_bps=costs_bps)
    ladder = [annualised(bucket, periods_per_year) if bucket else None for bucket in deciles]
    risk = decile_risk(deciles, periods_per_year)
    summary["decile_cagr"] = ladder
    summary["decile_risk"] = risk
    summary["decile_monotonicity"] = _monotonicity(ladder)
    summary["sharpe_monotonicity"] = _monotonicity(
        [entry["sharpe"] if entry else None for entry in risk])
    return summary


def run(*, start="2017-01-01", end="2026-06-01", design_ends=DESIGN_ENDS, every_days=21,
        top_n=20, horizon_days=21, costs_bps=10, universe_limit=None, store_dir=None,
        cache_dir=None):
    """Measure every candidate on both halves; select on the first; report the second."""
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

    halves = ("design", "test")
    realised = {half: {name: [] for name in (*CANDIDATE_NAMES, "equal_weight_universe")}
                for half in halves}
    deciles = {half: {name: [[] for _ in range(DECILES)] for name in CANDIDATE_NAMES}
               for half in halves}
    turnover = {half: {name: [] for name in CANDIDATE_NAMES} for half in halves}
    held = {name: set() for name in CANDIDATE_NAMES}
    dates = {half: [] for half in halves}
    history = {}

    for index, when in enumerate(full_grid):
        trading = index >= len(warmup) - 1
        members, _ = universe_as_of(when, prices=prices, cik_by_ticker=cik_by_ticker,
                                    last_filings=filings)
        tradable = set(members)
        current, forwards = {}, {}
        raw_values = {"return_on_invested_capital": {}, "gross_profits_to_assets": {},
                      "low_accruals": {}, "momentum_12_1": {}}
        banded_values = {"composite": {}, "composite_raw": {}, "without_valuation": {}}

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
            metrics, parts = derived["metrics"], derived["components"]
            forwards[ticker] = forward
            raw_values["return_on_invested_capital"][ticker] = \
                metrics.get("return_on_invested_capital")
            raw_values["momentum_12_1"][ticker] = context.get("momentum_12_1")
            assets, gross_profit = metrics.get("assets"), parts.get("gross_profit")
            raw_values["gross_profits_to_assets"][ticker] = (
                gross_profit / assets if assets and gross_profit is not None else None)
            accruals = metrics.get("accruals_ratio")
            raw_values["low_accruals"][ticker] = None if accruals is None else -accruals

            snap = snapshot(derived, history.get((index - PERIODS_PER_YEAR, ticker)),
                            history.get((index - THREE_YEARS, ticker)),
                            context, sectors.get(ticker), ticker)
            total, detail = _band_valuation_score(snap)
            if total is not None:
                banded_values["composite"][ticker] = total
                banded_values["composite_raw"][ticker] = detail.get("raw_score")
                banded_values["without_valuation"][ticker] = composite_without_valuation(detail)

        for ticker, derived in current.items():
            history[(index, ticker)] = derived
        for stale in [key for key in history if key[0] < index - THREE_YEARS]:
            del history[stale]
        if not trading or len(forwards) < MINIMUM_CROSS_SECTION:
            continue

        half = "design" if when < design_ends else "test"
        dates[half].append(when)
        realised[half]["equal_weight_universe"].append(
            statistics.mean(forwards[ticker] for ticker in forwards))

        scores = candidates(
            raw={name: percentile_ranks(values) for name, values in raw_values.items()},
            banded={name: percentile_ranks(values) for name, values in banded_values.items()})

        for name in CANDIDATE_NAMES:
            values = scores.get(name) or {}
            rankable = [t for t, value in values.items() if value is not None and t in forwards]
            if len(rankable) < MINIMUM_CROSS_SECTION:
                continue
            ordered = sorted(rankable, key=lambda t: values[t], reverse=True)
            for bucket_index, bucket in enumerate(_split_into_deciles(ordered)):
                if bucket:
                    deciles[half][name][bucket_index].append(
                        statistics.mean(forwards[t] for t in bucket))
            chosen = ordered[:top_n]
            realised[half][name].append(statistics.mean(forwards[t] for t in chosen))
            selection = set(chosen)
            turnover[half][name].append(len(selection - held[name]) / max(len(selection), 1))
            held[name] = selection

    periods_per_year = TRADING_DAYS / every_days
    summaries = {}
    for half in halves:
        summaries[half] = {}
        for name in CANDIDATE_NAMES:
            summary = _statistics(realised[half][name], deciles[half][name], periods_per_year,
                                  costs_bps=costs_bps)
            summary["average_turnover"] = (statistics.mean(turnover[half][name])
                                           if turnover[half][name] else None)
            summaries[half][name] = summary
        summaries[half]["equal_weight_universe"] = summarise(
            realised[half]["equal_weight_universe"], periods_per_year, costs_bps=0)

    winner, reason = select(summaries["design"])
    benchmark = summaries["test"]["equal_weight_universe"]
    live = summaries["test"]["live_composite"]
    result = summaries["test"].get(winner) if winner else None

    return {
        "settings": {"start": start, "design_ends": design_ends, "end": end,
                     "rebalance_every_days": every_days, "top_n": top_n,
                     "holding_days": horizon_days, "costs_bps_per_side": costs_bps,
                     "candidates_considered": len(CANDIDATE_NAMES) - len(REFERENCES),
                     "selection_rule": ("highest Sharpe-decile monotonicity on the design "
                                        "half, tie-broken by top-decile Sharpe")},
        "rebalances": {half: len(dates[half]) for half in halves},
        "design": summaries["design"],
        "test": summaries["test"],
        "selected": {"name": winner, "reason": reason},
        "verdict": _verdict(winner, result, live, benchmark),
        "limitations": [
            "One test half, roughly five years and one regime. A candidate that wins here has "
            "survived a single honest trial, which is the minimum bar rather than a strong one.",
            "Survivorship: measured on companies that still have a price feed today, so every "
            "level of return is biased upward. The comparison between candidates is far more "
            "trustworthy than any of their absolute numbers.",
            "Selecting on the design half still consumes some of the sample's evidence. The "
            "test half is honest about the winner; it is not a fresh sample for the runners-up, "
            "whose test numbers are reported for context and should not be mined.",
            "Costs are a flat 10bps per side and ignore market impact, which the highest "
            "turnover candidates would feel most.",
        ],
    }


def _verdict(winner, result, live, benchmark):
    """The comparison stated in full, including when it goes the wrong way."""
    if not winner or not result or not result.get("cagr"):
        return {"beat_live_model": None,
                "note": "no candidate produced a testable result on the test half"}
    return {
        "candidate": winner,
        "test_half_cagr": result.get("cagr"),
        "live_composite_cagr": live.get("cagr"),
        "universe_cagr": benchmark.get("cagr"),
        "test_half_sharpe": result.get("sharpe"),
        "live_composite_sharpe": live.get("sharpe"),
        "universe_sharpe": benchmark.get("sharpe"),
        "beat_live_model": (result.get("cagr") or 0) > (live.get("cagr") or 0),
        "beat_universe": (result.get("cagr") or 0) > (benchmark.get("cagr") or 0),
        "beat_live_model_risk_adjusted": (result.get("sharpe") or 0) > (live.get("sharpe") or 0),
        "beat_universe_risk_adjusted": (result.get("sharpe") or 0) > (benchmark.get("sharpe") or 0),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
