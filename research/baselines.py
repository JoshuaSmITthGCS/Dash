"""Phase 4: baselines, measured on point-in-time data, before anything is optimised.

The brief's instruction was to establish baselines *before* optimising anything, and to say
plainly if the complicated model cannot beat simple factor combinations after costs. This is
the harness that makes that answerable. It lives in ``research/`` and touches no production
code path.

Every input is point-in-time by construction:

* fundamentals come from ``pit_derive``, which reads only filings accepted by the rebalance
  date, with trailing twelve months built from as-reported quarters;
* universe membership comes from ``pit_market.universe_as_of``, evaluated with prices and
  filing recency as they stood on that date;
* forward returns come from adjusted closes, whose ratios depend only on corporate actions
  inside the holding window.

What it still cannot fix, and states in every result it writes:

* **Survivorship.** The candidate set is today's price cache. Companies that delisted before
  it was built are absent, so every number here is biased upward by an unquantified amount.
* **A short window.** Prices begin 2016-08; fundamentals reach 2010 but cannot be traded
  against prices that do not exist.
* **One market regime.** 2016 onward is mostly a bull market with two sharp drawdowns. Nine
  years is not enough to separate a factor from luck, and the multiple-testing correction the
  brief asks for in Phase 7 will have very little to work with.

Results are therefore evidence about *relative* ordering between simple strategies over one
period, not an estimate of what any of them will return.
"""

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "pipeline"))

from pit_derive import derive  # noqa: E402
from pit_market import (load_universe_prices, last_filing_dates,  # noqa: E402
                        rebalance_dates, universe_as_of)
from pit_fundamentals_store import ShardedStore  # noqa: E402
from pit_shares import current_basis_shares, shares_as_of  # noqa: E402

TRADING_DAYS = 252

# A company must have this many rankable names beside it before a cross-section means
# anything. Below it the rebalance is skipped outright rather than ranked thinly.
MINIMUM_CROSS_SECTION = 30

MINIMUM_PLAUSIBLE_MARKET_CAP = 1e7
MAXIMUM_PLAUSIBLE_MARKET_CAP = 1e13


def _rank(values, *, descending=True):
    ordered = sorted((value for value in values.values() if value is not None),
                     reverse=descending)
    if not ordered:
        return {}
    return {name: ordered.index(value) for name, value in values.items() if value is not None}


# Each baseline maps a company's derived metrics to a score; higher ranks first. Every one is
# a published, well-known construction rather than anything tuned here -- that is the point.
def value_score(metrics, price_context):
    """Earnings yield. Cheap on trailing earnings against market value."""
    market_cap = price_context.get("market_cap")
    earnings = metrics.get("net_income_ttm")
    if not market_cap or earnings is None:
        return None
    return earnings / market_cap


def quality_score(metrics, _price_context):
    """Return on invested capital -- the profitability leg of quality-minus-junk."""
    return metrics.get("return_on_invested_capital")


def profitability_score(metrics, _price_context):
    """Gross-profits-to-assets, Novy-Marx's measure, approximated from operating income
    where a filer reports no gross-profit line."""
    assets = metrics.get("assets")
    profit = metrics.get("operating_income_ttm")
    if not assets or profit is None:
        return None
    return profit / assets


def momentum_score(_metrics, price_context):
    """12-1 momentum: twelve-month return skipping the most recent month."""
    return price_context.get("momentum_12_1")


def low_accruals_score(metrics, _price_context):
    accruals = metrics.get("accruals_ratio")
    return None if accruals is None else -accruals


BASELINES = {
    "value_earnings_yield": value_score,
    "quality_roic": quality_score,
    "profitability": profitability_score,
    "momentum_12_1": momentum_score,
    "low_accruals": low_accruals_score,
}

COMBINATIONS = {
    "value_and_momentum": ("value_earnings_yield", "momentum_12_1"),
    "quality_and_momentum": ("quality_roic", "momentum_12_1"),
    "value_quality_momentum": ("value_earnings_yield", "quality_roic", "momentum_12_1"),
}


def price_context(history, when, shares=None):
    """Price-derived inputs for a rebalance date, using only sessions up to it.

    ``shares`` must already be on the price series' split basis -- ``pit_shares`` is what
    puts it there. Multiplying a price level by an as-filed share count is the four-fold
    error that module exists to prevent, so no share count is defaulted here.
    """
    index = history._index_at(when)  # noqa: SLF001 - same module family
    if index is None:
        return {}
    price = history.price(when)
    context = {"price": price}
    if shares and price:
        market_cap = price * shares
        # A residual scale error survives the reconstruction for a handful of pre-IPO
        # periods, and it lands where it does the most damage: a market cap a thousand times
        # too small makes a stock the single cheapest name in the universe and puts it in
        # every value portfolio. Nothing in this universe -- every member clears $1m of daily
        # volume -- trades below $10m or above $10tn, so outside that band the number is
        # wrong rather than extreme, and it is dropped rather than ranked.
        if MINIMUM_PLAUSIBLE_MARKET_CAP <= market_cap <= MAXIMUM_PLAUSIBLE_MARKET_CAP:
            context["market_cap"] = market_cap
    if index >= TRADING_DAYS:
        skip = max(0, index - 21)
        start = max(0, index - TRADING_DAYS)
        if history.adjusted[start]:
            context["momentum_12_1"] = history.adjusted[skip] / history.adjusted[start] - 1
    return context


def forward_return(history, start, horizon_days=21):
    """Return over the holding period following a rebalance date.

    ``None`` where the window crosses an identity break -- a ticker that stopped denoting one
    security and started denoting another. Chord Energy's Chapter 11 emergence reads as a
    +39,130% month otherwise, which is enough on its own to make a factor's annualised
    volatility exceed 500%.
    """
    index = history._index_at(start)  # noqa: SLF001
    if index is None:
        return None
    end = min(index + horizon_days, len(history.dates) - 1)
    if end <= index or history.spans_identity_break(index, end):
        return None
    first, last = history.adjusted[index], history.adjusted[end]
    if not first:
        return None
    return last / first - 1


def annualised(period_returns, periods_per_year):
    if not period_returns:
        return None
    growth = 1.0
    for value in period_returns:
        growth *= (1 + value)
    years = len(period_returns) / periods_per_year
    return growth ** (1 / years) - 1 if years > 0 and growth > 0 else None


def summarise(period_returns, periods_per_year, *, costs_bps=0):
    """Headline statistics for one strategy's realised period returns."""
    if not period_returns:
        return {"periods": 0}
    net = [value - costs_bps / 10_000 for value in period_returns]
    mean = statistics.mean(net)
    deviation = statistics.pstdev(net) if len(net) > 1 else 0.0
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for value in net:
        equity *= (1 + value)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    downside = [value for value in net if value < 0]
    return {
        "periods": len(net),
        "cagr": annualised(net, periods_per_year),
        "mean_period_return": mean,
        "volatility_annualised": deviation * (periods_per_year ** 0.5),
        "sharpe": (mean / deviation * (periods_per_year ** 0.5)) if deviation else None,
        "sortino": (mean / statistics.pstdev(downside) * (periods_per_year ** 0.5)
                    if len(downside) > 1 and statistics.pstdev(downside) else None),
        "max_drawdown": drawdown,
        "win_rate": sum(1 for value in net if value > 0) / len(net),
        "costs_bps_per_side": costs_bps,
    }


def _share_basis(rows):
    """Split-basis share counts for one company, diluted where filed and basic otherwise.

    Some filers -- Exxon among them -- tag no weighted-average *diluted* count in the
    concepts this store collects. Basic is a slightly smaller number, not a made-up one, so
    it is a legitimate fallback where diluted is genuinely absent; the alternative is
    dropping the company from every value factor.
    """
    series, _ = current_basis_shares(rows)
    if not series:
        series, _ = current_basis_shares(rows, concept="shares_basic")
    return series


def _truncated_histories(by_cik, cik_by_ticker, prices, *, months=24):
    """Tickers priced well before their earliest filed period.

    A successor registrant -- a holding company formed above the old one, a redomiciliation,
    a merger of equals -- gets a new CIK, and the SEC ticker map points at it. The
    predecessor's decade of filings is then unreachable under the ticker's current key, so
    the company looks like it IPO'd on the day it reorganised. Counting them is not a fix,
    but it names how many companies carry no fundamentals for part of this window.
    """
    earliest = {}
    for cik, rows in by_cik.items():
        ends = [row["period_end"] for row in rows if row.get("period_end")]
        if ends:
            earliest[cik] = min(ends)
    flagged = {}
    for ticker, history in prices.items():
        filed_from = earliest.get(cik_by_ticker.get(ticker))
        priced_from = history.dates[0]
        if filed_from is None:
            flagged[ticker] = {"priced_from": priced_from, "filings_from": None}
            continue
        gap = ((int(filed_from[:4]) - int(priced_from[:4])) * 12
               + int(filed_from[5:7]) - int(priced_from[5:7]))
        if gap > months:
            flagged[ticker] = {"priced_from": priced_from, "filings_from": filed_from,
                               "gap_months": gap}
    return flagged


def run(*, start="2017-01-01", end="2026-06-01", every_days=21, top_n=20,
        horizon_days=21, costs_bps=10, universe_limit=None, store_dir=None,
        cache_dir=None):
    """Rank the universe by each baseline at every rebalance date and hold the top names."""
    store = ShardedStore(store_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pipeline", "data", "pit", "fundamentals"))
    observations = store.load()
    by_cik = {}
    for row in observations:
        by_cik.setdefault(row["cik"], []).append(row)
    filings = last_filing_dates(observations)

    audit_path = os.path.join(os.path.dirname(store.directory), "entity_audit.json")
    with open(audit_path, encoding="utf-8") as handle:
        cik_by_ticker = json.load(handle)["resolved_map"]
    if universe_limit:
        cik_by_ticker = dict(list(cik_by_ticker.items())[:universe_limit])
    prices = load_universe_prices(cik_by_ticker, cache_dir)

    share_basis = {cik: _share_basis(rows) for cik, rows in by_cik.items()}
    truncated = _truncated_histories(by_cik, cik_by_ticker, prices)

    names = [*BASELINES, *COMBINATIONS, "equal_weight_universe"]
    realised = {name: [] for name in names}
    turnover = {name: [] for name in names}
    held = {name: set() for name in names}
    membership = []
    coverage = []
    scored = {name: [] for name in names}

    for when in rebalance_dates(start, end, every_days=every_days):
        members, diagnostics = universe_as_of(
            when, prices=prices, cik_by_ticker=cik_by_ticker, last_filings=filings)
        membership.append(diagnostics)
        if len(members) < MINIMUM_CROSS_SECTION:
            continue
        metrics, contexts, forwards = {}, {}, {}
        for ticker in members:
            cik = cik_by_ticker[ticker]
            history = prices[ticker]
            forward = forward_return(history, when, horizon_days)
            if forward is None:
                continue
            derived = derive(by_cik.get(cik, []), when, cik=cik)
            metrics[ticker] = derived["metrics"]
            contexts[ticker] = price_context(
                history, when, shares=shares_as_of(share_basis.get(cik, []), when))
            forwards[ticker] = forward
        if len(forwards) < MINIMUM_CROSS_SECTION:
            continue
        coverage.append({
            "as_of": when,
            "rankable": len(forwards),
            "with_market_cap": sum(1 for row in contexts.values() if row.get("market_cap")),
            "with_momentum": sum(1 for row in contexts.values() if row.get("momentum_12_1")),
        })

        realised["equal_weight_universe"].append(
            statistics.mean(forwards[ticker] for ticker in forwards))

        scores = {}
        for name, scorer in BASELINES.items():
            scores[name] = {ticker: scorer(metrics[ticker], contexts[ticker])
                            for ticker in forwards}
        for name, parts in COMBINATIONS.items():
            ranks = {part: _rank(scores[part]) for part in parts}
            combined = {}
            for ticker in forwards:
                positions = [ranks[part][ticker] for part in parts if ticker in ranks[part]]
                if len(positions) == len(parts):
                    combined[ticker] = -statistics.mean(positions)
            scores[name] = combined

        for name, values in scores.items():
            rankable = [ticker for ticker, value in values.items() if value is not None]
            scored[name].append(len(rankable))
            # A factor that can only rank a handful of names is not being measured against
            # the cross-section; it is being measured against whoever happened to file a
            # usable number. Skip the date rather than report the result of that.
            if len(rankable) < MINIMUM_CROSS_SECTION:
                continue
            ranked = sorted(rankable, key=lambda ticker: values[ticker],
                            reverse=True)[:top_n]
            realised[name].append(statistics.mean(forwards[ticker] for ticker in ranked))
            selection = set(ranked)
            turnover[name].append(len(selection - held[name]) / max(len(selection), 1))
            held[name] = selection

    periods_per_year = TRADING_DAYS / every_days
    results = {}
    for name in names:
        summary = summarise(realised[name], periods_per_year,
                            costs_bps=0 if name == "equal_weight_universe" else costs_bps)
        summary["average_turnover"] = (statistics.mean(turnover[name])
                                       if turnover[name] else None)
        summary["median_names_rankable"] = (statistics.median(scored[name])
                                            if scored[name] else 0)
        summary["rebalances_skipped_thin"] = sum(1 for count in scored[name]
                                                 if count < MINIMUM_CROSS_SECTION)
        results[name] = summary
    return {
        "settings": {"start": start, "end": end, "rebalance_every_days": every_days,
                     "top_n": top_n, "holding_days": horizon_days,
                     "costs_bps_per_side": costs_bps,
                     "minimum_cross_section": MINIMUM_CROSS_SECTION},
        "rebalances": len(membership),
        "universe": {
            "median_members": (statistics.median(row["members"] for row in membership)
                               if membership else 0),
            "first": membership[0] if membership else None,
            "last": membership[-1] if membership else None,
        },
        "coverage": {
            "median_rankable": (statistics.median(row["rankable"] for row in coverage)
                                if coverage else 0),
            "median_with_market_cap": (statistics.median(row["with_market_cap"]
                                                         for row in coverage)
                                       if coverage else 0),
            "tickers_with_truncated_filing_history": len(truncated),
            "truncated_examples": dict(list(truncated.items())[:10]),
        },
        "results": results,
        "limitations": [
            "Survivorship: the candidate set is today's price cache, so companies that "
            "delisted before it was built are absent. Every return here is biased upward by "
            "an amount this pipeline cannot yet quantify.",
            "Window: prices begin 2016-08, so this covers roughly nine years dominated by "
            "one regime. That is too short to separate a factor from luck.",
            "Successor registrants: companies that reorganised under a new CIK carry no "
            "fundamentals before that date, so they sit out the fundamental factors and "
            "stay in momentum. See coverage.tickers_with_truncated_filing_history.",
            "Recent splits: a split not yet restated into any filing is in the price series "
            "and in no share count, so a market cap in that window is wrong by the split. "
            "The window is at most one filing period per company.",
            "No multiple-testing correction has been applied. These are baselines to be "
            "beaten, not findings.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
