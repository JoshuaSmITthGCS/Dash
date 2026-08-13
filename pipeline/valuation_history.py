"""Reconstructs each company's own valuation-multiple history from data already on disk.

The "quality at valuation lows" screen needs, per company, a *series* of past multiples to
say whether today's multiple is cheap against that company's own record. No provider on this
pipeline serves such a series, which is why the screen published
POINT_IN_TIME_VALUATION_HISTORY_NOT_COLLECTED and nothing else.

It can be built rather than bought. The backtest cache already holds, per ticker, a decade of
daily closes plus the recent quarterly income/balance/cash-flow statements. A multiple is
price over a fundamental, so a daily multiple series follows directly - provided the
fundamental attached to a given day is one that was actually public that day. That is the
whole risk here, and REPORTING_LAG_DAYS is the answer to it: a quarter's figures only become
effective REPORTING_LAG_DAYS after the period ends (the SEC's 10-Q deadline for a large
accelerated filer), so no day is ever priced against a statement filed after it.

The window is therefore as deep as the cached statements reach - roughly six to ten months
today, not the multi-year record the screen's title once promised. `multiple_series` reports
`sessions` and `start` for exactly that reason: the caller gates on real depth and publishes
it, instead of quietly presenting an eight-month low as a decade low.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

# A large accelerated filer files its 10-Q within 40 days of quarter end and its 10-K within
# 60. 45 days is the deliberately conservative middle: a few days of pessimism costs a little
# history, while optimism here would price days against statements nobody could read yet.
REPORTING_LAG_DAYS = 45
# Below this, a "percentile versus own history" is a statement about one quarter of weather,
# not a company's valuation record. 100 sessions is roughly five months, which is what the
# cached statements actually support: Yahoo serves about five usable quarters, four of them
# consumed by the first trailing-twelve-month total, so the deepest honest window today runs
# from the quarter before last. The screen publishes the window it measured rather than
# implying a longer one.
MINIMUM_HISTORY_SESSIONS = 100
# ...and at least two statements have to fall inside that window, or the "multiple" never
# moved for any reason except price.
MINIMUM_FUNDAMENTAL_STEPS = 2

# Yahoo's statement row labels, in preference order. The first present row wins.
INCOME_ROWS = {
    "net_income": ("Net Income Common Stockholders", "Net Income",
                   "Net Income From Continuing Operation Net Minority Interest"),
    "revenue": ("Total Revenue", "Operating Revenue"),
    "ebit": ("EBIT", "Operating Income", "Total Operating Income As Reported"),
    "ebitda": ("Normalized EBITDA", "EBITDA"),
}
# A share count is a level, not a flow, so it is read at a period rather than summed across
# four of them. The income statement carries one for every period it reports; the balance
# sheet's own share row is frequently null on older periods, and letting that null decide the
# window would cut the history back to whatever the newest balance sheet covers.
SHARE_ROWS = ("Diluted Average Shares", "Basic Average Shares")
BALANCE_ROWS = {
    "shares": ("Ordinary Shares Number", "Share Issued"),
    "total_debt": ("Total Debt", "Long Term Debt And Capital Lease Obligation"),
    "cash": ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
    "equity": ("Stockholders Equity", "Common Stock Equity"),
    "tangible_book": ("Tangible Book Value", "Net Tangible Assets"),
}
CASHFLOW_ROWS = {"free_cash_flow": ("Free Cash Flow",)}

# Which multiples mean anything for which kind of business. Enterprise value is meaningless
# for a bank (debt is raw material, not leverage) and earnings multiples are meaningless for a
# company that has no earnings, so each profile gets its own applicable set with a weight that
# says how much of the cheapness verdict it should carry. Weights feed
# research_screens_v2.robust_value_score, which takes a weighted median - a single distorted
# multiple cannot swing the result.
APPLICABILITY = {
    "general": {"price_to_earnings": .8, "price_to_sales": .5, "price_to_book": .4,
                "ev_to_ebit": 1.0, "ev_to_ebitda": 1.0, "ev_to_fcf": .8},
    "bank": {"price_to_earnings": 1.0, "price_to_book": 1.0, "price_to_tangible_book": 1.0},
    "property_casualty_insurer": {"price_to_earnings": .8, "price_to_book": 1.0,
                                  "price_to_tangible_book": 1.0},
    "life_insurer": {"price_to_earnings": .8, "price_to_book": 1.0, "price_to_tangible_book": 1.0},
    "diversified_insurer": {"price_to_earnings": .8, "price_to_book": 1.0,
                            "price_to_tangible_book": 1.0},
    "reit": {"ev_to_ebitda": 1.0, "ev_to_fcf": 1.0, "price_to_book": .6, "price_to_sales": .5},
    "utility": {"ev_to_ebitda": 1.0, "ev_to_ebit": .8, "price_to_earnings": .8, "price_to_book": .6},
    "commodity_producer": {"ev_to_ebitda": 1.0, "price_to_book": .8, "price_to_sales": .6,
                           "ev_to_sales": .6},
    "profitable_biotechnology": {"price_to_earnings": .8, "ev_to_ebit": 1.0, "ev_to_ebitda": 1.0,
                                 "ev_to_sales": .6},
    "pre_profit_biotechnology": {"ev_to_sales": 1.0, "price_to_sales": .8, "price_to_book": .5},
    "other_pre_profit": {"ev_to_sales": 1.0, "price_to_sales": .8, "price_to_book": .5},
    # Reached only by sector fallback, for a financial whose industry label the published
    # universe doesn't carry. It is the cautious reading of "Financial Services": drop the
    # enterprise-value multiples, which are meaningless for anything that funds itself with
    # deposits or float, and lean on the price multiples, which stay honest either way.
    "financial": {"price_to_earnings": 1.0, "price_to_book": 1.0, "price_to_tangible_book": .8},
}
# classify_profile keys off industry text, which only the detailed research rows carry. For
# the rest of the cross-section, sector alone still rules out the multiples that would
# actively mislead.
SECTOR_PROFILE_FALLBACK = {
    "utilities": "utility",
    "real estate": "reit",
    "energy": "commodity_producer",
    "basic materials": "commodity_producer",
    "financial services": "financial",
    "financials": "financial",
}
# Every multiple here is cheap when it is low; none of the published set inverts (a yield
# would). Kept explicit so a future addition has to state its own direction.
LOWER_IS_CHEAPER = {"price_to_earnings", "price_to_sales", "price_to_book",
                    "price_to_tangible_book", "ev_to_ebit", "ev_to_ebitda", "ev_to_fcf",
                    "ev_to_sales"}


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def statement_row(statement, names):
    """The first of `names` present in a Yahoo statement block, aligned to its periods."""
    rows = (statement or {}).get("rows") or {}
    for name in names:
        if name in rows:
            return rows[name]
    return None


def _periods(statement):
    return [str(period)[:10] for period in ((statement or {}).get("periods") or [])]


def _quarterly(periods):
    """Whether these period ends are quarters rather than fiscal years.

    Yahoo serves quarterly statements here, but the same cache shape can carry annual ones,
    and summing four annual periods would overstate a trailing year fourfold.
    """
    if len(periods) < 2:
        return True
    try:
        gaps = [abs((date.fromisoformat(periods[index]) - date.fromisoformat(periods[index + 1])).days)
                for index in range(len(periods) - 1)]
    except ValueError:
        return True
    return sorted(gaps)[len(gaps) // 2] <= 200


def trailing_twelve_months(statement, names):
    """{period_end: trailing-twelve-month total} for every period with a full year behind it.

    Periods arrive newest-first. A quarterly series needs four consecutive quarters, all
    present; an annual series is already a trailing year on its own.
    """
    periods, row = _periods(statement), statement_row(statement, names)
    if not periods or row is None:
        return {}
    values = [_finite(value) for value in row][:len(periods)]
    if len(values) < len(periods):
        values += [None] * (len(periods) - len(values))
    if not _quarterly(periods):
        return {period: value for period, value in zip(periods, values) if value is not None}
    output = {}
    for index in range(len(periods) - 3):
        window = values[index:index + 4]
        if all(value is not None for value in window):
            output[periods[index]] = sum(window)
    return output


def reported_series(statement, names):
    """{period_end: value} for the first present row, dropping the periods it left null."""
    periods, row = _periods(statement), statement_row(statement, names)
    if not periods or row is None:
        return {}
    return {period: value for period, value in
            ((period, _finite(row[index]) if index < len(row) else None)
             for index, period in enumerate(periods)) if value is not None}


def _as_of(series, period):
    """The most recent reported value at or before `period`.

    Balance-sheet figures are levels: the last one filed stays true until the next is. Each
    field is walked back on its own, because a period that reports total debt but leaves
    tangible book null should not blank out both.
    """
    candidates = [key for key in series if key <= period]
    return series[max(candidates)] if candidates else None


def point_in_time_fundamentals(entry, reporting_lag_days=REPORTING_LAG_DAYS):
    """Per statement period, the figures and the first date they can legitimately be used.

    Returned oldest-first so a caller can walk it forward alongside a price series.
    """
    income, balance, cashflow = entry.get("income"), entry.get("balance"), entry.get("cashflow")
    trailing = {key: trailing_twelve_months(income, names) for key, names in INCOME_ROWS.items()}
    trailing.update({key: trailing_twelve_months(cashflow, names) for key, names in CASHFLOW_ROWS.items()})
    balance_series = {key: reported_series(balance, names) for key, names in BALANCE_ROWS.items()}
    income_shares = reported_series(income, SHARE_ROWS)

    def balance_at(period):
        figures = {key: _as_of(series, period) for key, series in balance_series.items()}
        if figures.get("shares") is None:
            figures["shares"] = _as_of(income_shares, period)
        return figures

    output = []
    for period in sorted({period for series in trailing.values() for period in series}):
        try:
            effective = (date.fromisoformat(period) + timedelta(days=reporting_lag_days)).isoformat()
        except ValueError:
            continue
        output.append({
            "period_end": period, "effective_from": effective,
            "trailing": {key: series.get(period) for key, series in trailing.items()},
            "balance": balance_at(period),
        })
    return output


def _multiples(close, trailing, balance):
    """Every multiple computable for one day, skipping the ones a denominator makes nonsense.

    A negative or zero denominator is dropped rather than published: a company earning nothing
    does not have an infinitely expensive P/E, it has no P/E, and a -3x EV/EBIT would rank as
    the cheapest name in the market if it were allowed through.
    """
    shares, debt = balance.get("shares"), balance.get("total_debt") or 0
    cash = balance.get("cash") or 0
    if not shares or shares <= 0:
        return {}
    market_cap = close * shares
    enterprise_value = market_cap + debt - cash
    pairs = {
        "price_to_earnings": (market_cap, trailing.get("net_income")),
        "price_to_sales": (market_cap, trailing.get("revenue")),
        "price_to_book": (market_cap, balance.get("equity")),
        "price_to_tangible_book": (market_cap, balance.get("tangible_book")),
        "ev_to_ebit": (enterprise_value, trailing.get("ebit")),
        "ev_to_ebitda": (enterprise_value, trailing.get("ebitda")),
        "ev_to_fcf": (enterprise_value, trailing.get("free_cash_flow")),
        "ev_to_sales": (enterprise_value, trailing.get("revenue")),
    }
    output = {}
    for name, (numerator, denominator) in pairs.items():
        if denominator is None or denominator <= 0 or numerator is None or numerator <= 0:
            continue
        value = _finite(numerator / denominator)
        if value is not None:
            output[name] = value
    return output


def multiple_series(entry, reporting_lag_days=REPORTING_LAG_DAYS, as_of=None):
    """Daily own-history multiples for one ticker: {metric: {history, current, sessions, start}}.

    `history` is every value in the window including today's, which is what a percentile of
    "where does today sit in this company's own record" needs.
    """
    dates = [str(day)[:10] for day in (entry.get("dates") or [])]
    # Unadjusted closes, deliberately. A market cap is shares times the price the stock
    # actually traded at; a dividend-adjusted series quietly marks down every historical price
    # and would make a company look progressively cheaper the further back you look.
    closes = [_finite(close) for close in (entry.get("raw_closes") or entry.get("closes") or [])]
    if not dates or len(dates) != len(closes):
        return {}
    cutoff = str(as_of)[:10] if as_of else None
    fundamentals = point_in_time_fundamentals(entry, reporting_lag_days)
    if not fundamentals:
        return {}

    series, index, active = {}, 0, None
    for day, close in zip(dates, closes):
        if cutoff and day > cutoff:
            break
        while index < len(fundamentals) and fundamentals[index]["effective_from"] <= day:
            active, index = fundamentals[index], index + 1
        if active is None or close is None or close <= 0:
            continue
        for name, value in _multiples(close, active["trailing"], active["balance"]).items():
            series.setdefault(name, {"history": [], "days": [], "periods": set()})
            series[name]["history"].append(value)
            series[name]["days"].append(day)
            series[name]["periods"].add(active["period_end"])
    # `fundamental_steps` is the honest caveat on a short window: with one statement covering
    # every day in it, each multiple is a monotone function of price and the percentile is a
    # price percentile wearing a valuation label. Callers gate on it.
    return {name: {"history": item["history"], "current": item["history"][-1],
                   "sessions": len(item["history"]), "start": item["days"][0],
                   "end": item["days"][-1], "fundamental_steps": len(item["periods"]),
                   "lower_is_cheaper": name in LOWER_IS_CHEAPER}
            for name, item in series.items() if item["history"]}


def profile_for(row, classifier=None):
    """The business profile whose multiples apply to this company.

    `classify_profile` is authoritative when it can decide; its "general" verdict often just
    means the row had no industry label to read, so sector gets the last word before a bank is
    handed an EV/EBITDA.
    """
    if classifier is None:
        from canonical_metrics import classify_profile as classifier  # noqa: PLC0415
    profile = classifier(row)
    if profile != "general":
        return profile
    return SECTOR_PROFILE_FALLBACK.get(str(row.get("sector") or "").strip().lower(), "general")


def applicable_metrics(profile, available, minimum_sessions=MINIMUM_HISTORY_SESSIONS,
                       minimum_steps=MINIMUM_FUNDAMENTAL_STEPS):
    """The subset of a profile's multiples that this ticker actually has enough history for."""
    weights = APPLICABILITY.get(profile) or APPLICABILITY["general"]
    return {name: weight for name, weight in weights.items()
            if (available.get(name) or {}).get("sessions", 0) >= minimum_sessions
            and (available.get(name) or {}).get("fundamental_steps", 0) >= minimum_steps}
