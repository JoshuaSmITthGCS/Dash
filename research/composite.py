"""Phase 6: the live ValueSignal composite, measured against the Phase 4 baselines.

Phase 4 established the bar: an equal-weighted holding of the universe returned 18.0%
annualised over 2017-2026, and of the simple factors the model is built from, momentum sorted
the cross-section, earnings yield sorted it backwards, and return on invested capital did not
sort it at all. The obvious question follows -- whether the composite that weights those
inputs does better than the inputs did.

This answers it by scoring the **real model**, not a reimplementation of it. Snapshots built
from point-in-time filings are passed to ``scorer._band_valuation_score``, so the category
weights, the metric weights inside each category, the band cutoffs, the applicability
suppressions and the coverage multiplier are all the live ones, read from
``pipeline/config/settings.json`` at run time. If the weights change, this measurement changes
with them.

**What the model cannot see here, and why that is fair rather than crippling.** Four inputs
depend on analyst estimates or on concepts the fundamentals backfill does not collect:
``forward_pe`` and ``peg`` (forward estimates), ``earnings_surprise`` (estimates), and
``altman_z`` (retained earnings). They are passed as absent, which is what the live model
already does for a company whose provider returns nothing -- ``weighted_available``
redistributes their weight across the metrics that did resolve, and ``weighted_coverage``
lowers the confidence multiplier accordingly. So the composite here is the live composite
running at reduced coverage, and its coverage is reported alongside its return.

It is worth being explicit that this understates one thing and overstates another. Forward
P/E carries 15% of the valuation category, and its absence shifts that weight onto trailing
multiples. Against that, every remaining input is genuinely point-in-time, where the live
pipeline's provider data is restated -- so the live model has never been measured on data this
clean, and could not have been before Phase 2.

Trend and growth metrics read the same company twelve rebalances earlier -- a real prior
observation on the grid, never a recomputation with today's knowledge.
"""

import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pit_derive import derive  # noqa: E402
from pit_market import load_universe_prices, last_filing_dates, rebalance_dates, universe_as_of  # noqa: E402
from pit_fundamentals_store import ShardedStore  # noqa: E402
from pit_shares import shares_as_of  # noqa: E402
from scorer import _band_valuation_score  # noqa: E402

from baselines import (DECILES, MINIMUM_CROSS_SECTION, MAXIMUM_PLAUSIBLE_MARKET_CAP,  # noqa: E402
                       MINIMUM_PLAUSIBLE_MARKET_CAP, TRADING_DAYS, _monotonicity,
                       _share_basis, _split_into_deciles, annualised, forward_return,
                       price_context, summarise)

# Twelve rebalances at 21 sessions is a year, so a year-ago reading is a point already on the
# grid rather than a second derivation. Three years back is the fcf_growth_3y leg.
PERIODS_PER_YEAR = 12
THREE_YEARS = 36


def _ratio(numerator, denominator, *, allow_negative=False):
    if numerator is None or not denominator:
        return None
    if denominator < 0 and not allow_negative:
        return None
    return numerator / denominator


def _trend(current, earlier):
    """Change in a level between two point-in-time readings, as a fraction of the earlier."""
    if current is None or earlier in (None, 0):
        return None
    return (current - earlier) / abs(earlier)


def piotroski_f(now, before):
    """The nine-point F-score, from point-in-time levels at two dates a year apart.

    Returns ``None`` rather than a partial tally when the prior year is unavailable: a
    five-signal F-score compared against a nine-signal band is a different measurement
    wearing the same name.
    """
    if not before:
        return None
    need = ("net_income", "operating_cash_flow", "assets", "long_term_debt", "current_assets",
            "current_liabilities", "revenue", "gross_profit")
    if any(now.get(key) is None for key in need) or any(before.get(key) is None for key in need):
        return None
    roa_now = _ratio(now["net_income"], now["assets"])
    roa_before = _ratio(before["net_income"], before["assets"])
    leverage_now = _ratio(now["long_term_debt"], now["assets"])
    leverage_before = _ratio(before["long_term_debt"], before["assets"])
    current_now = _ratio(now["current_assets"], now["current_liabilities"])
    current_before = _ratio(before["current_assets"], before["current_liabilities"])
    margin_now = _ratio(now["gross_profit"], now["revenue"])
    margin_before = _ratio(before["gross_profit"], before["revenue"])
    turnover_now = _ratio(now["revenue"], now["assets"])
    turnover_before = _ratio(before["revenue"], before["assets"])
    if None in (roa_now, roa_before, current_now, current_before, margin_now, margin_before,
                turnover_now, turnover_before):
        return None
    signals = [
        roa_now > 0,
        now["operating_cash_flow"] > 0,
        roa_now > roa_before,
        now["operating_cash_flow"] > now["net_income"],
        (leverage_now or 0) <= (leverage_before or 0),
        current_now >= current_before,
        # Share count falling is the ninth signal; buybacks stand in for it, since a
        # weighted-average count that fell for a split reason is not a capital decision.
        (now.get("share_repurchases") or 0) >= 0,
        margin_now >= margin_before,
        turnover_now >= turnover_before,
    ]
    return float(sum(1 for signal in signals if signal))


def snapshot(derived, earlier, older, context, sector, ticker):
    """One company's live-model snapshot, built only from filings readable on the date.

    Field names are the live scorer's. A field this data cannot support is absent, never
    filled with a neutral stand-in -- the model's own renormalisation is what handles it.
    """
    metrics = derived["metrics"]
    parts = derived["components"]
    before = (earlier or {}).get("components") or {}
    market_cap = context.get("market_cap")

    cash = parts.get("cash") or 0
    debt = metrics.get("total_debt")
    enterprise_value = None
    if market_cap and debt is not None:
        enterprise_value = market_cap + debt - cash
    ebitda = None
    if parts.get("operating_income") is not None and parts.get("depreciation_amortization") is not None:
        ebitda = parts["operating_income"] + parts["depreciation_amortization"]
    tangible_book = None
    if metrics.get("equity") is not None:
        tangible_book = (metrics["equity"] - (parts.get("goodwill") or 0)
                         - (parts.get("intangibles") or 0))

    days_sales_now = _ratio(parts.get("receivables"), parts.get("revenue"))
    days_sales_before = _ratio(before.get("receivables"), before.get("revenue"))
    inventory_now = _ratio(parts.get("inventory"), parts.get("cost_of_revenue"))
    inventory_before = _ratio(before.get("inventory"), before.get("cost_of_revenue"))
    margin_now = metrics.get("operating_margin")
    margin_before = _ratio(before.get("operating_income"), before.get("revenue"))

    free_cash_flow = parts.get("free_cash_flow")
    fcf_three_years_ago = ((older or {}).get("components") or {}).get("free_cash_flow")

    return {
        "symbol": ticker,
        "sector": sector,
        "is_etf": False,
        # Valuation. forward_pe and peg need analyst estimates and stay absent.
        "ev_to_sales": _ratio(enterprise_value, parts.get("revenue")),
        "price_to_book": _ratio(market_cap, metrics.get("equity")),
        "price_to_tangible_book": _ratio(market_cap, tangible_book),
        "ev_to_ebitda": _ratio(enterprise_value, ebitda),
        "ev_to_ebit": _ratio(enterprise_value, parts.get("operating_income")),
        "ev_to_fcf": _ratio(enterprise_value, free_cash_flow),
        # Profitability.
        "return_on_equity": metrics.get("return_on_equity"),
        "return_on_invested_capital": metrics.get("return_on_invested_capital"),
        "gross_profits_to_assets": _ratio(parts.get("gross_profit"), metrics.get("assets")),
        "cash_conversion": metrics.get("cash_conversion"),
        "free_cash_flow_yield": _ratio(free_cash_flow, market_cap),
        "profit_margin": metrics.get("profit_margin"),
        # Financial health. altman_z needs retained earnings, which the backfill does not collect.
        "debt_to_equity": metrics.get("debt_to_equity"),
        "current_ratio": metrics.get("current_ratio"),
        "interest_coverage": metrics.get("interest_coverage"),
        "net_debt_to_ebitda": _ratio((debt - cash) if debt is not None else None, ebitda,
                                     allow_negative=True),
        # Growth. earnings_surprise needs estimates.
        "revenue_growth": _trend(parts.get("revenue"), before.get("revenue")),
        "earnings_growth": _trend(parts.get("net_income"), before.get("net_income")),
        "fcf_growth_3y": _trend(free_cash_flow, fcf_three_years_ago),
        "operating_margin_trend": (None if None in (margin_now, margin_before)
                                   else margin_now - margin_before),
        # Capital allocation.
        "net_buyback_yield": _ratio(parts.get("share_repurchases"), market_cap),
        "stock_comp_to_revenue": metrics.get("stock_comp_to_revenue"),
        "capex_to_depreciation": metrics.get("capex_to_depreciation"),
        "asset_growth": _trend(metrics.get("assets"), before.get("assets")),
        # Accounting quality.
        "accruals_ratio": metrics.get("accruals_ratio"),
        "piotroski_f": piotroski_f(parts, before),
        "days_sales_outstanding_trend": (None if None in (days_sales_now, days_sales_before)
                                         else days_sales_now - days_sales_before),
        "inventory_days_trend": (None if None in (inventory_now, inventory_before)
                                 else inventory_now - inventory_before),
    }


def run(*, start="2017-01-01", end="2026-06-01", every_days=21, top_n=20, horizon_days=21,
        costs_bps=10, universe_limit=None, store_dir=None, cache_dir=None):
    """Rank by the live composite at every rebalance date, and by its categories separately."""
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

    # Derivation starts three years before the first traded date so the growth and trend legs
    # have a real prior observation rather than an absence that renormalises away.
    grid = rebalance_dates(start, end, every_days=every_days)
    warmup = rebalance_dates(_shift_years(start, THREE_YEARS // PERIODS_PER_YEAR), start,
                             every_days=every_days)
    full_grid = warmup[:-1] + grid

    names = ["composite", "composite_raw", "valuation", "profitability", "financial_health",
             "growth", "capital_allocation", "accounting_quality"]
    realised = {name: [] for name in names}
    realised["equal_weight_universe"] = []
    turnover = {name: [] for name in names}
    held = {name: set() for name in names}
    deciles = {name: [[] for _ in range(DECILES)] for name in names}
    scored = {name: [] for name in names}
    coverages, membership = [], []
    history = {}

    for index, when in enumerate(full_grid):
        trading = index >= len(warmup) - 1
        members, diagnostics = universe_as_of(
            when, prices=prices, cik_by_ticker=cik_by_ticker, last_filings=filings)
        snapshots, forwards = {}, {}
        current = {}
        tradable = set(members)
        # Derivation covers every company with filings, not only universe members. The two
        # are different questions: whether a company was investable on a date, and whether it
        # had filed. Tying them together left the warm-up empty -- the universe requires 252
        # sessions of price history and the cache begins 2016-08, so no company is a member
        # until late 2017, and every growth and trend leg silently renormalised away.
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
            snapshots[ticker] = snapshot(
                derived,
                history.get((index - PERIODS_PER_YEAR, ticker)),
                history.get((index - THREE_YEARS, ticker)),
                context, sectors.get(ticker), ticker)
            forwards[ticker] = forward
        # Keep a rolling three years of derivations so the trend legs read a real prior
        # observation off the grid rather than re-deriving with today's knowledge.
        for ticker, derived in current.items():
            history[(index, ticker)] = derived
        for stale in [key for key in history if key[0] < index - THREE_YEARS]:
            del history[stale]

        if not trading:
            continue
        membership.append(diagnostics)
        if len(forwards) < MINIMUM_CROSS_SECTION:
            continue

        realised["equal_weight_universe"].append(
            statistics.mean(forwards[ticker] for ticker in forwards))

        scores = {name: {} for name in names}
        coverage_readings = []
        for ticker, snap in snapshots.items():
            total, detail = _band_valuation_score(snap)
            if total is None:
                continue
            scores["composite"][ticker] = total
            scores["composite_raw"][ticker] = detail.get("raw_score")
            coverage_readings.append(detail.get("coverage") or 0.0)
            for category in ("valuation", "profitability", "financial_health", "growth",
                             "capital_allocation", "accounting_quality"):
                value = (detail.get("categories") or {}).get(category)
                if value is not None:
                    scores[category][ticker] = value
        coverages.append({"as_of": when, "scored": len(scores["composite"]),
                          "median_coverage": (statistics.median(coverage_readings)
                                              if coverage_readings else None)})

        for name, values in scores.items():
            rankable = [t for t, value in values.items() if value is not None and t in forwards]
            scored[name].append(len(rankable))
            if len(rankable) < MINIMUM_CROSS_SECTION:
                continue
            ordered = sorted(rankable, key=lambda t: values[t], reverse=True)
            for bucket_index, bucket in enumerate(_split_into_deciles(ordered)):
                if bucket:
                    deciles[name][bucket_index].append(
                        statistics.mean(forwards[t] for t in bucket))
            ranked = ordered[:top_n]
            realised[name].append(statistics.mean(forwards[t] for t in ranked))
            selection = set(ranked)
            turnover[name].append(len(selection - held[name]) / max(len(selection), 1))
            held[name] = selection

    periods_per_year = TRADING_DAYS / every_days
    results = {}
    for name in [*names, "equal_weight_universe"]:
        summary = summarise(realised[name], periods_per_year,
                            costs_bps=0 if name == "equal_weight_universe" else costs_bps)
        summary["average_turnover"] = (statistics.mean(turnover[name])
                                       if turnover.get(name) else None)
        summary["median_names_rankable"] = (statistics.median(scored[name])
                                            if scored.get(name) else 0)
        ladder = [annualised(bucket, periods_per_year) if bucket else None
                  for bucket in deciles.get(name, [])]
        summary["decile_cagr"] = ladder or None
        summary["decile_spread"] = (None if not ladder or None in (ladder[0], ladder[-1])
                                    else ladder[0] - ladder[-1])
        summary["decile_monotonicity"] = _monotonicity(ladder) if ladder else None
        results[name] = summary

    return {
        "settings": {"start": start, "end": end, "rebalance_every_days": every_days,
                     "top_n": top_n, "holding_days": horizon_days,
                     "costs_bps_per_side": costs_bps,
                     "model_weights": _weights_in_force()},
        "rebalances": len(membership),
        "scoring": {
            "median_scored": (statistics.median(row["scored"] for row in coverages)
                              if coverages else 0),
            "median_data_coverage": (statistics.median(
                row["median_coverage"] for row in coverages
                if row["median_coverage"] is not None) if coverages else None),
            "inputs_unavailable_point_in_time": [
                "forward_pe", "peg", "earnings_surprise", "altman_z"],
            "note": ("Those four need analyst estimates or retained earnings, which this "
                     "store does not hold. They are passed absent, so the live model's own "
                     "renormalisation redistributes their weight and its coverage multiplier "
                     "falls -- the same treatment a company with a silent provider gets "
                     "today. The composite measured here is the live composite at reduced "
                     "coverage, not a different model."),
        },
        "results": results,
        "limitations": [
            "Survivorship: the candidate set is today's price cache. Every return here is "
            "biased upward by an amount this pipeline cannot yet quantify, and the "
            "comparison against equal_weight_universe is the only reading that partly "
            "controls for it.",
            "Window: roughly nine years, one regime, and the one in which value performed "
            "worst in decades. A composite weighting valuation at 28% is being measured in "
            "its most hostile sample.",
            "Four inputs are absent point-in-time; see scoring.inputs_unavailable_point_in_time.",
            "No multiple-testing correction has been applied.",
        ],
    }


def _shift_years(date_string, years):
    return f"{int(str(date_string)[:4]) - years}{str(date_string)[4:10]}"


def _weights_in_force():
    from scorer import SETTINGS
    cfg = SETTINGS["fundamentals"]
    return {"category_weights": cfg["category_weights"],
            "metric_weights": cfg["metric_weights"]}


def _sectors(tickers, cache_dir):
    from pit_market import CACHE_DIR
    directory = cache_dir or CACHE_DIR
    sectors = {}
    for ticker in tickers:
        path = os.path.join(directory, f"{ticker}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            sectors[ticker] = json.load(handle).get("sector")
    return sectors


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
