"""Forward-looking stress and scenario testing: what would a shock like this cost the book.

Every other stress-style read in this pipeline is retrospective - the tax-and-stress group's
``stress_test_2022`` grades a window the backtest actually lived through. This module runs the
other direction: it takes the book's own *measured* exposures (its beta to SPY, its FF5 plus
momentum factor loadings, its beta to long Treasuries as a rate proxy) and projects them
through a scenario, named or hypothetical.

Two scenario families:

  * **Named historical events** - the realized market, rate, and factor returns during the
    2008 GFC, the March 2020 COVID crash, and the 2022 rate-hike drawdown, each a widely
    cited peak-to-trough window, applied to the book's own loadings. This is not a replay of
    the book's own returns during those windows - the strategy did not exist yet for two of
    the three - it is what the book's *current, measured* factor exposure would have cost it
    had it been running through that window.
  * **Hypothetical parametric shocks** - a flat index move ("SPY -30%") or a rate move
    ("rates +200bp"), projected through the same measured betas. The rate shock additionally
    assumes a TLT effective duration (stated below, not hidden) to convert a yield move into
    a bond-price move; that is a real modeling assumption and is reported as one everywhere
    the number is published, not just here.

Both projections are linear extrapolations of a linear model (a beta, a duration) through a
move often larger than the sample that estimated it. Every published metric's ``reads`` field
says so, deliberately, rather than letting a precise-looking percentage imply more than a
beta and a duration constant can actually promise.

Source data: ``public/data/etf/SPY.json`` and ``TLT.json`` (daily total-return history back to
the early 2000s) and ``public/data/factors/french.json`` (monthly Fama-French observations
back to 1963) - both already committed for other parts of the dashboard, read here rather
than fetched again.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ETF_DIR = os.path.join(os.path.dirname(HERE), "public", "data", "etf")

FACTOR_KEYS = ("market_excess", "size", "value", "profitability", "investment", "momentum")

# Peak-to-trough windows, chosen for citability over precision: each is the widely reported
# drawdown window for its event, not a hand-picked worst stretch within it.
NAMED_SCENARIOS = {
    "gfc_2008": {
        "label": "2008 Global Financial Crisis",
        "start": "2007-10-09", "end": "2009-03-09",
        "description": "S&P 500 all-time high (2007-10-09) to the post-crisis trough (2009-03-09).",
    },
    "covid_2020": {
        "label": "March 2020 COVID crash",
        "start": "2020-02-19", "end": "2020-03-23",
        "description": "S&P 500 pre-pandemic high (2020-02-19) to the fastest bear-market trough on record (2020-03-23).",
    },
    "rate_shock_2022": {
        "label": "2022 rate-hike drawdown",
        "start": "2022-01-03", "end": "2022-10-12",
        "description": "S&P 500 high (2022-01-03) to the 2022 bear-market low (2022-10-12), the Fed's steepest hiking cycle in four decades.",
    },
}

# iShares' published effective duration for TLT has run roughly 16-17 years across the period
# this module's data covers. Used only to size the *hypothetical* rate shock -- the named
# historical scenarios use TLT's own realized return and need no duration assumption at all.
TLT_EFFECTIVE_DURATION_YEARS = 17.0
HYPOTHETICAL_SPY_SHOCK_PCT = -30.0
HYPOTHETICAL_RATE_SHOCK_BPS = 200


def read_etf_prices(ticker, etf_dir=ETF_DIR):
    """The daily ``[{date, total_return_index, adjusted_close}]`` series for a committed ETF."""
    path = os.path.join(etf_dir, f"{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return (data.get("price_series") or {}).get("fund") or None


def window_return(prices, start, end):
    """Total return between the first and last priced day inside ``[start, end]``.

    Uses the total-return index (dividends reinvested) rather than the raw close, so a
    scenario built from an equity index and one built from a bond ETF are measuring the same
    thing - what an investor actually earned or lost, not just the price move.
    """
    if not prices:
        return None
    in_window = [row for row in prices
                if row.get("date") and start <= row["date"] <= end
                and (row.get("total_return_index") or row.get("adjusted_close"))]
    if len(in_window) < 2:
        return None
    key = "total_return_index" if in_window[0].get("total_return_index") else "adjusted_close"
    first, last = in_window[0].get(key), in_window[-1].get(key)
    if not first:
        return None
    return round(last / first - 1, 4)


def factor_window_return(observations, start, end, key):
    """Compounded Fama-French factor return over the months touching ``[start, end]``."""
    months = [row for row in observations or []
             if row.get("month") and start[:7] <= row["month"] <= end[:7]
             and row.get(key) is not None]
    if not months:
        return None
    total = 1.0
    for row in months:
        total *= 1 + row[key]
    return round(total - 1, 4)


def scenario_factor_returns(observations, start, end):
    return {key: factor_window_return(observations, start, end, key) for key in FACTOR_KEYS}


def factor_projected_return(loadings, factor_returns):
    """Dot product of measured factor loadings and a scenario's factor returns.

    A leg missing on either side drops out of the sum rather than being treated as zero
    exposure - an unmeasured loading is not the same claim as a measured-and-zero one.
    """
    if not loadings:
        return None
    terms = [loadings[key] * factor_returns[key] for key in FACTOR_KEYS
             if loadings.get(key) is not None and factor_returns.get(key) is not None]
    if not terms:
        return None
    return round(sum(terms), 4)


def aligned_daily_returns(portfolio_history, benchmark_prices):
    """Same-date daily simple returns for the book and a benchmark ETF series.

    Zips by index after restricting both series to shared trading dates, so a beta computed
    from this pair is not silently misaligned by a holiday or data-quality gap present in one
    series and not the other.
    """
    benchmark_by_date = {row["date"]: (row.get("total_return_index") or row.get("adjusted_close"))
                         for row in benchmark_prices or [] if row.get("date")}
    portfolio_by_date = {row["date"]: row.get("value")
                         for row in portfolio_history or [] if row.get("date")}
    shared = sorted(date for date in portfolio_by_date
                    if date in benchmark_by_date and portfolio_by_date[date] and benchmark_by_date[date])
    portfolio_values = [portfolio_by_date[date] for date in shared]
    benchmark_values = [benchmark_by_date[date] for date in shared]
    portfolio_returns = [b / a - 1 for a, b in zip(portfolio_values, portfolio_values[1:]) if a]
    benchmark_returns = [b / a - 1 for a, b in zip(benchmark_values, benchmark_values[1:]) if a]
    return portfolio_returns, benchmark_returns


def named_scenarios(*, spy_prices, tlt_prices, factor_observations, loadings, beta_spy):
    """Every named event: realized SPY/TLT/factor moves, projected through the book's own
    measured exposures. Returns a dict keyed by scenario id."""
    results = {}
    for scenario_id, meta in NAMED_SCENARIOS.items():
        spy_return = window_return(spy_prices, meta["start"], meta["end"])
        tlt_return = window_return(tlt_prices, meta["start"], meta["end"])
        factors = scenario_factor_returns(factor_observations, meta["start"], meta["end"])
        market_beta_projection = (round(beta_spy * spy_return, 4)
                                  if beta_spy is not None and spy_return is not None else None)
        factor_projection = factor_projected_return(loadings, factors)
        results[scenario_id] = {
            "id": scenario_id, "label": meta["label"], "description": meta["description"],
            "start": meta["start"], "end": meta["end"],
            "spy_return_pct": None if spy_return is None else round(spy_return * 100, 2),
            "tlt_return_pct": None if tlt_return is None else round(tlt_return * 100, 2),
            "factor_returns_pct": {key: (None if value is None else round(value * 100, 2))
                                   for key, value in factors.items()},
            "market_beta_projection_pct": None if market_beta_projection is None
            else round(market_beta_projection * 100, 2),
            "factor_model_projection_pct": None if factor_projection is None
            else round(factor_projection * 100, 2),
        }
    return results


def hypothetical_shocks(*, beta_spy, rate_beta, spy_shock_pct=HYPOTHETICAL_SPY_SHOCK_PCT,
                        rate_shock_bps=HYPOTHETICAL_RATE_SHOCK_BPS,
                        tlt_duration_years=TLT_EFFECTIVE_DURATION_YEARS):
    """Parametric what-ifs: a flat index move and a rate move, through measured betas."""
    spy_projection = round(beta_spy * spy_shock_pct, 2) if beta_spy is not None else None
    tlt_price_impact_pct = -tlt_duration_years * (rate_shock_bps / 100)
    rate_projection = (round(rate_beta * tlt_price_impact_pct, 2) if rate_beta is not None else None)
    return {
        "spy_shock": {
            "shock_pct": spy_shock_pct, "beta_spy": beta_spy,
            "projected_return_pct": spy_projection,
        },
        "rate_shock": {
            "shock_bps": rate_shock_bps, "assumed_tlt_duration_years": tlt_duration_years,
            "implied_tlt_price_impact_pct": round(tlt_price_impact_pct, 2),
            "rate_beta": rate_beta, "projected_return_pct": rate_projection,
        },
    }
