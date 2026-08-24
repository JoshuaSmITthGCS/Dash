"""
backtest_historical.py

Point-in-time historical backtest of the real research algorithm (scorer.valuation_score +
advisor_engine.technical_factors / build_research), not a replay of today's picks.

For each week over the trailing window, it reconstructs what every candidate's fundamentals
score WOULD have looked like using only data that existed as of that week (quarterly financial
statements, offset by a realistic reporting lag, plus that week's actual closing price), re-ranks
the full universe, and simulates a portfolio that contributes $1,000/month into the current top
20, sells positions that drop out of the top 20 or get flagged SELL, and redeploys the proceeds
into that week's new top 20 -- then compares the result to buying SPY/QQQ/DIA/IWM on the same
$1,000/month schedule.

WHY THIS IS AN APPROXIMATION, NOT A REPLAY:
Yahoo Finance's free `info` endpoint only ever reflects *today*. Several inputs to the live score
are only available as a current snapshot and cannot be reconstructed retroactively for free:
  - forward P/E, analyst consensus rating, analyst price target / upside
  - short interest, institutional/insider ownership
  - sector/macro-regime context beyond what's derivable from that week's own universe
Those fields are simply left absent for historical weeks (None), and the scoring functions
already reweight around missing inputs rather than penalizing for them -- that's how the
production pipeline treats missing data too. What IS reconstructed point-in-time from actual
historical data: trailing valuation multiples (P/S, P/B, a trailing-P/E used in place of forward
P/E, an approximate PEG), ROE/ROIC, margins, debt/coverage ratios, Altman Z, Piotroski F,
accruals, capital allocation, growth, and the full price/volume-based technical score. News
sentiment has no historical article archive to replay (rank_week always passes an empty news
list), so it is correctly absent (None) for every historical week, not defaulted to neutral --
same as live production has reported it since A1-NEWS-NEUTRAL (2026-08-07).

Quarterly statement history from yfinance typically only reaches back ~2 years (about 8
quarters), so year-over-year revenue/earnings growth built from Yahoo alone thins out for the
earliest weeks in a long lookback window. Since Round 11 Priority 4, ``build_snapshot`` falls
back to the EDGAR point-in-time fundamentals store (``pipeline/data/pit/fundamentals/``, filed
timestamps back to 2009) for whichever of the two Yahoo's quarters can't reach, via
``edgar_pit_growth_fallback`` -- filed<=as_of enforced, no look-ahead. Revenue growth is
skipped for bank/insurer/REIT profiles (see ``REVENUE_GROWTH_EXCLUDED_PROFILES``); a name with
no resolvable CIK, or with EDGAR history that also doesn't reach back far enough, still shows
``None``, which is a real data-availability limit rather than a bug, and the scorer already
reweights around it. Set ``DISABLE_EDGAR_PIT_BACKTEST_GROWTH=1`` to reproduce the pre-Round-11
Yahoo-only behavior.

Growth wasn't the only casualty of that ~2-year window, just the one first diagnosed: for an
as_of date entirely outside it, Yahoo's cached quarters resolve *no* known statement date at
all (``build_ttm_statements`` never runs), so valuation, profitability, financial_health,
capital_allocation, and accounting_quality were silently left at ``None`` too -- everywhere
older than roughly the trailing 1.5-2 years of a multi-year backtest, which for a 5-10 year
window is most of it. Round 11 Priority 7 closes this the same way: ``edgar_ttm_statements``
already returns full income/balance/cashflow dicts in the shape ``build_ttm_statements``
produces, so ``edgar_pit_statement_fallback`` substitutes them directly for that empty
window rather than reconstructing just two numbers. EDGAR's balance mapping carries no
shares-outstanding concept, so market-cap-dependent ratios there fall back further, to
diluted (then basic) weighted-average shares from the income statement -- a standard,
disclosed stand-in, not a precise point-in-time float count. Set
``DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS=1`` to reproduce the pre-Priority-7 behavior (only
growth filled, every other ratio empty outside Yahoo's window).

Needs real network access + yfinance (this script is meant to be run locally, not in a sandboxed
agent session): `python3 pipeline/backtest_historical.py --help`
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import LOG, load_json  # noqa: E402
from advisor_engine import build_research  # noqa: E402
from canonical_metrics import classify_profile  # noqa: E402
from edgar_enrichment import edgar_ttm_statements  # noqa: E402
from fundamentals_extended import at, derive_extended, line, statement_series  # noqa: E402
from market_history import sector_percentiles  # noqa: E402
from policy_backtest import compare_policies  # noqa: E402
from scorer import valuation_score  # noqa: E402

REPORT_LAG_DAYS_DEFAULT = 45
QUARTERS_NEEDED_FOR_TTM = 4
# Round 11 Priority 4: Yahoo's quarterly statement history typically reaches back only ~8
# quarters, so this reconstruction's own year-over-year growth (below) frequently can't find
# a prior TTM window -- the panel-wide 0% growth-leg coverage Round 10 diagnosed. The EDGAR
# PIT fundamentals store already collected (pipeline/data/pit/fundamentals/, filed timestamps
# back to 2009) can reach much further; edgar_ttm_statements() already enforces filed<=as_of,
# the same no-look-ahead guarantee this file's own report_lag_days approximation is for.
# Revenue growth specifically is skipped for bank/insurer/REIT profiles: the generic
# "Revenues" XBRL concept nets premiums/losses/interest oddly for those (Round 11's pilot
# found this exact pattern on AGO), the same reason EXCLUDED_EXPANSION_PROFILES in
# fetch_advisor.py already special-cases them. Earnings growth (net income) doesn't share
# that ambiguity and is not excluded.
REVENUE_GROWTH_EXCLUDED_PROFILES = {
    "bank", "life_insurer", "property_casualty_insurer", "diversified_insurer", "reit",
}
DISABLE_EDGAR_PIT_BACKTEST_GROWTH = os.getenv("DISABLE_EDGAR_PIT_BACKTEST_GROWTH", "").lower() in {
    "1", "true", "yes",
}
# Round 11 Priority 7: edgar_pit_growth_fallback (above) only ever fills the two YoY growth
# figures -- for an as_of date entirely outside Yahoo's ~2-year quarterly window (start_idx
# None below), income_ttm/balance_now/cashflow_ttm themselves were left as *empty* statements,
# not just growth. Every ratio basic_ratios()/derive_extended() compute from them --
# valuation, profitability, financial_health, capital_allocation, accounting_quality --
# silently went to None for that whole stretch, while growth (via the fallback above) and
# market_behavior (pure price/volume) kept working. A 5-10 year backtest is mostly older than
# Yahoo's window, so this was near-total: five of eight research-score legs carried almost no
# real signal outside the most recent ~1.5 years. edgar_ttm_statements() already returns full
# income/balance/cashflow dicts in the exact shape build_ttm_statements() produces, so this
# reuses it directly as those statements' fallback, not just a source for two numbers.
DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS = os.getenv(
    "DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS", "").lower() in {"1", "true", "yes"}


def _edgar_ttm_line(symbol, as_of_str, label):
    try:
        statements = edgar_ttm_statements(symbol, as_of_str)
    except Exception:  # noqa: BLE001 - a PIT-store read must never sink the backtest
        return None
    if not statements:
        return None
    rows = statements.get("income", {}).get("rows", {}).get(label)
    return rows[0] if rows else None


def edgar_pit_growth_fallback(ticker_data, as_of, *, need_revenue, need_earnings):
    """Reconstruct whichever of revenue/earnings TTM YoY growth Yahoo's history couldn't.

    Returns ``(revenue_growth, earnings_growth)``, each ``None`` if not needed, not
    available, or (for revenue) excluded for this business profile. Never raises: a PIT-store
    miss for one ticker must not sink the run, matching edgar_enrichment.merge_edgar_fallback's
    own contract for the live pipeline.
    """
    if DISABLE_EDGAR_PIT_BACKTEST_GROWTH or not (need_revenue or need_earnings):
        return None, None
    as_of_str = as_of.isoformat()
    prior_str = (as_of - timedelta(days=365)).isoformat()

    revenue_growth = None
    if need_revenue:
        profile = classify_profile({"sector": ticker_data.get("sector"),
                                    "industry": ticker_data.get("industry"),
                                    "is_etf": ticker_data.get("is_etf"),
                                    "ticker": ticker_data.get("symbol")})
        if profile not in REVENUE_GROWTH_EXCLUDED_PROFILES:
            now = _edgar_ttm_line(ticker_data["symbol"], as_of_str, "Total Revenue")
            prior = _edgar_ttm_line(ticker_data["symbol"], prior_str, "Total Revenue")
            if now is not None and prior and prior > 0:
                revenue_growth = round(now / prior - 1, 4)

    earnings_growth = None
    if need_earnings:
        now = _edgar_ttm_line(ticker_data["symbol"], as_of_str, "Net Income")
        prior = _edgar_ttm_line(ticker_data["symbol"], prior_str, "Net Income")
        if now is not None and prior not in (None, 0):
            earnings_growth = round(now / prior - 1, 4)

    return revenue_growth, earnings_growth


def edgar_pit_statement_fallback(ticker_data, as_of):
    """Full (income, balance, cashflow) TTM statements from the EDGAR PIT store, for an
    as_of date entirely outside Yahoo's cached quarterly window.

    Returns ``(None, None, None)`` if disabled, the ticker has no resolvable CIK, or EDGAR
    history doesn't reach back far enough either -- callers fall back to the pre-existing
    empty-statement behavior in that case. Never raises, matching
    edgar_pit_growth_fallback's own contract: a PIT-store read must never sink the backtest.
    """
    if DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS:
        return None, None, None
    try:
        statements = edgar_ttm_statements(ticker_data["symbol"], as_of.isoformat())
    except Exception:  # noqa: BLE001 - a PIT-store read must never sink the backtest
        return None, None, None
    if not statements:
        return None, None, None
    empty = {"periods": [], "rows": {}}
    return (statements.get("income") or empty, statements.get("balance") or empty,
           statements.get("cashflow") or empty)


# ---------------- data collection ----------------

def load_universe(limit, tickers_arg):
    if tickers_arg:
        return [t.strip().upper() for t in tickers_arg.split(",") if t.strip()]
    universe = load_json("advisor_universe.json", from_config=True) or {}
    symbols = universe.get("symbols", [])
    return symbols[:limit] if limit else symbols


def fetch_ticker_data(yf, symbol, delay, history_period="2y", include_current_metadata=True):
    """Everything one ticker needs: daily prices plus available quarterly statements.

    ``history_period`` is explicit so longer walk-forward runners can request enough price
    warm-up without changing the legacy weekly backtest's network footprint.
    """
    try:
        ticker_obj = yf.Ticker(symbol)
        # ``info`` is a current snapshot and is intentionally optional in strict historical
        # runs. It also costs another Yahoo request for every symbol.
        info = ticker_obj.info or {} if include_current_metadata else {}
        hist = ticker_obj.history(period=history_period, auto_adjust=False).dropna(subset=["Close"])
        dates = [str(idx)[:10] for idx in hist.index]
        raw_closes = [float(v) for v in hist["Close"].tolist()]
        adjusted = hist["Adj Close"] if "Adj Close" in hist.columns else hist["Close"]
        closes = [float(v) for v in adjusted.tolist()]
        volumes = [float(v) for v in hist["Volume"].fillna(0).tolist()]
        income = statement_series(ticker_obj.quarterly_income_stmt)
        balance = statement_series(ticker_obj.quarterly_balance_sheet)
        cashflow = statement_series(ticker_obj.quarterly_cashflow)
    except Exception as exc:  # noqa: BLE001 - one bad ticker must not sink the run
        LOG.warn(f"{symbol}: fetch failed ({type(exc).__name__}: {exc})")
        return None
    finally:
        time.sleep(delay)

    if len(closes) < 60 or not income["periods"]:
        LOG.warn(f"{symbol}: insufficient price or statement history, skipping")
        return None

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "is_etf": info.get("quoteType") == "ETF",
        "current_shares_outstanding": info.get("sharesOutstanding"),
        "dates": dates,
        "closes": closes,
        "raw_closes": raw_closes,
        "volumes": volumes,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
    }


def fetch_benchmark(yf, symbol, delay, history_period="2y"):
    try:
        ticker_obj = yf.Ticker(symbol)
        hist = ticker_obj.history(period=history_period, auto_adjust=False).dropna(subset=["Close"])
        adjusted = hist["Adj Close"] if "Adj Close" in hist.columns else hist["Close"]
        return {
            "dates": [str(idx)[:10] for idx in hist.index],
            "closes": [float(v) for v in adjusted.tolist()],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: benchmark fetch failed ({type(exc).__name__})")
        return None
    finally:
        time.sleep(delay)


# ---------------- point-in-time reconstruction ----------------

def quarter_known_dates(periods, report_lag_days):
    """Each quarter's period-end date, shifted by a filing-lag approximation."""
    out = []
    for period in periods:
        try:
            end = date.fromisoformat(period[:10])
        except ValueError:
            out.append(None)
            continue
        out.append(end + timedelta(days=report_lag_days))
    return out


def most_recent_known_index(known_dates, as_of):
    """Index of the newest quarter whose (period end + lag) is on/before as_of. None if none known yet."""
    for idx, known in enumerate(known_dates):
        if known is not None and known <= as_of:
            return idx
    return None


def ttm_flow(rows, start_idx):
    """Sum four consecutive quarters for an income/cashflow line. None unless all four are present."""
    out = {}
    for name, values in rows.items():
        window = values[start_idx:start_idx + QUARTERS_NEEDED_FOR_TTM]
        out[name] = sum(window) if len(window) == QUARTERS_NEEDED_FOR_TTM and all(v is not None for v in window) else None
    return out


def point_snapshot(rows, idx):
    """A balance-sheet line at a single quarter index (no summing - it's a stock, not a flow)."""
    out = {}
    for name, values in rows.items():
        out[name] = values[idx] if idx is not None and idx < len(values) else None
    return out


def build_ttm_statements(ticker_data, start_idx):
    """Two trailing-twelve-month periods (current, and one year earlier) for derive_extended.

    Shaped like the 'annual' statements derive_extended already expects: {periods, rows},
    index 0 = TTM ending at start_idx, index 1 = TTM ending 4 quarters before that (for YoY).
    """
    offsets = [start_idx, start_idx + QUARTERS_NEEDED_FOR_TTM]
    income_rows, cashflow_rows = ticker_data["income"]["rows"], ticker_data["cashflow"]["rows"]
    balance_rows = ticker_data["balance"]["rows"]

    def flow_series(rows):
        per_offset = [ttm_flow(rows, o) for o in offsets]
        names = set().union(*[d.keys() for d in per_offset]) if per_offset else set()
        return {name: [d.get(name) for d in per_offset] for name in names}

    def stock_series(rows):
        per_offset = [point_snapshot(rows, o) for o in offsets]
        names = set().union(*[d.keys() for d in per_offset]) if per_offset else set()
        return {name: [d.get(name) for d in per_offset] for name in names}

    periods = [str(o) for o in offsets]
    return (
        {"periods": periods, "rows": flow_series(income_rows)},
        {"periods": periods, "rows": stock_series(balance_rows)},
        {"periods": periods, "rows": flow_series(cashflow_rows)},
    )


def nearest_close(dates, closes, as_of):
    """Most recent close on/before as_of; falls back to the earliest available if as_of predates history."""
    as_of_str = as_of.isoformat()
    best = None
    for d, c in zip(dates, closes):
        if d <= as_of_str:
            best = c
        else:
            break
    return best if best is not None else (closes[0] if closes else None)


def price_index(dates, as_of):
    as_of_str = as_of.isoformat()
    idx = None
    for i, d in enumerate(dates):
        if d <= as_of_str:
            idx = i
        else:
            break
    return idx


def basic_ratios(income_ttm, balance_now, market_cap, revenue_growth):
    """The subset of `snap` that fetch_snapshot() normally reads off Yahoo's *current* `info`
    blob (forward P/E, PEG, P/S, P/B, ROE, debt/equity, current ratio, growth). Reconstructed
    here from trailing statement data instead, since `info` cannot be queried historically.
    """
    revenue = at(line(income_ttm, "revenue"))
    net_income = at(line(income_ttm, "net_income"))
    equity = at(line(balance_now, "equity"))
    total_debt = at(line(balance_now, "total_debt"))
    current_assets = at(line(balance_now, "current_assets"))
    current_liabilities = at(line(balance_now, "current_liabilities"))

    price_to_sales = market_cap / revenue if market_cap and revenue and revenue > 0 else None
    price_to_book = market_cap / equity if market_cap and equity and equity > 0 else None
    trailing_pe = market_cap / net_income if market_cap and net_income and net_income > 0 else None
    peg = None
    if trailing_pe is not None and revenue_growth is not None and revenue_growth > 0.01:
        peg = round(trailing_pe / (revenue_growth * 100), 2)

    return {
        "price_to_sales": round(price_to_sales, 2) if price_to_sales else None,
        "price_to_book": round(price_to_book, 2) if price_to_book else None,
        # No historical forward-estimate data is available for free; trailing P/E stands in.
        "forward_pe": round(trailing_pe, 2) if trailing_pe else None,
        "trailing_pe": round(trailing_pe, 2) if trailing_pe else None,
        "peg": peg,
        "return_on_equity": round(net_income / equity, 4) if net_income and equity and equity > 0 else None,
        "debt_to_equity": round(total_debt / equity, 2) if total_debt is not None and equity else None,
        "current_ratio": round(current_assets / current_liabilities, 2)
                          if current_assets and current_liabilities else None,
        "profit_margin": round(net_income / revenue, 4) if net_income is not None and revenue else None,
        "free_cash_flow": None,  # filled by caller once FCF is known
        "free_cash_flow_yield": None,
    }


def build_snapshot(ticker_data, as_of, report_lag_days, allow_current_shares=True,
                   allow_empty_fundamentals=False):
    """The full point-in-time `snap` dict scorer.valuation_score expects, or None if too early."""
    known_dates = quarter_known_dates(ticker_data["income"]["periods"], report_lag_days)
    start_idx = most_recent_known_index(known_dates, as_of)
    if start_idx is None and not allow_empty_fundamentals:
        return None

    if start_idx is None:
        income_ttm, balance_now, cashflow_ttm = edgar_pit_statement_fallback(ticker_data, as_of)
        if income_ttm is None:
            empty = {"periods": [], "rows": {}}
            income_ttm, balance_now, cashflow_ttm = empty, empty, empty
    else:
        income_ttm, balance_now, cashflow_ttm = build_ttm_statements(ticker_data, start_idx)
    raw_closes = ticker_data.get("raw_closes") or ticker_data["closes"]
    price = nearest_close(ticker_data["dates"], raw_closes, as_of)
    if price is None:
        return None
    shares = ticker_data["current_shares_outstanding"] if allow_current_shares else None
    balance_shares = at(line(balance_now, "shares_outstanding"))
    if balance_shares:
        shares = balance_shares
    elif not shares:
        # Neither a live share count (blocked by allow_current_shares for point-in-time
        # correctness) nor a balance-sheet share count resolved -- EDGAR's balance mapping
        # carries no shares-outstanding concept at all (edgar_enrichment.BALANCE_ROWS), so
        # its statements never populate ``balance_shares`` above. Diluted/basic weighted
        # average shares from the income statement is not the same figure, but it's a
        # standard, disclosed practical stand-in for market cap here, and strictly better
        # than leaving every market-cap-dependent valuation ratio at None for this stretch.
        shares = at(line(income_ttm, "diluted_shares"))
    market_cap = price * shares if shares else None

    revenue_now = at(line(income_ttm, "revenue"), 0)
    revenue_prior = at(line(income_ttm, "revenue"), 1)
    revenue_growth = (revenue_now / revenue_prior - 1) if (revenue_now and revenue_prior and revenue_prior > 0) else None
    net_income_now = at(line(income_ttm, "net_income"), 0)
    net_income_prior = at(line(income_ttm, "net_income"), 1)
    earnings_growth = (net_income_now / net_income_prior - 1) if (
        net_income_now is not None and net_income_prior not in (None, 0)) else None

    if revenue_growth is None or earnings_growth is None:
        edgar_revenue_growth, edgar_earnings_growth = edgar_pit_growth_fallback(
            ticker_data, as_of, need_revenue=revenue_growth is None,
            need_earnings=earnings_growth is None)
        if revenue_growth is None:
            revenue_growth = edgar_revenue_growth
        if earnings_growth is None:
            earnings_growth = edgar_earnings_growth

    ttm_for_ratios = {"periods": income_ttm["periods"][:1], "rows": {k: v[:1] for k, v in income_ttm["rows"].items()}}
    balance_for_ratios = {"periods": balance_now["periods"][:1], "rows": {k: v[:1] for k, v in balance_now["rows"].items()}}
    snap = basic_ratios(ttm_for_ratios, balance_for_ratios, market_cap, revenue_growth)
    snap.update({
        "ticker": ticker_data["symbol"],
        "name": ticker_data["name"],
        "sector": ticker_data["sector"],
        "is_etf": ticker_data["is_etf"],
        "market_cap": market_cap,
        "price": price,
        "revenue_growth": round(revenue_growth, 4) if revenue_growth is not None else None,
        "earnings_growth": round(earnings_growth, 4) if earnings_growth is not None else None,
    })

    idx = price_index(ticker_data["dates"], as_of)
    closes_to_date = ticker_data["closes"][:idx + 1] if idx is not None else []
    volumes_to_date = ticker_data["volumes"][:idx + 1] if idx is not None else []

    extended = derive_extended(
        annual={"income": income_ttm, "balance": balance_now, "cashflow": cashflow_ttm},
        info={}, market_cap=market_cap, price=price, sector=ticker_data["sector"],
        closes=closes_to_date, volumes=volumes_to_date,
    )
    snap.update(extended)
    ttm_fcf = at(line(cashflow_ttm, "free_cash_flow"))
    if ttm_fcf is None:
        op_cf, capex = at(line(cashflow_ttm, "operating_cash_flow")), at(line(cashflow_ttm, "capex"))
        ttm_fcf = None if op_cf is None else op_cf - abs(capex or 0)
    snap["free_cash_flow"] = round(ttm_fcf) if ttm_fcf is not None else None
    snap["free_cash_flow_yield"] = round(ttm_fcf / market_cap, 4) if ttm_fcf and market_cap else None

    return snap, closes_to_date, volumes_to_date


# ---------------- weekly ranking ----------------

def weekly_dates(weeks):
    today = date.today()
    return [today - timedelta(weeks=i) for i in range(weeks, 0, -1)]


def rank_week(universe_data, benchmark_closes_to_date, as_of, report_lag_days,
              allow_current_shares=True, allow_empty_fundamentals=False):
    """Score every ticker as of `as_of` using the real scoring functions, ranked best first."""
    prepared = {}
    for symbol, ticker_data in universe_data.items():
        built = build_snapshot(
            ticker_data, as_of, report_lag_days, allow_current_shares,
            allow_empty_fundamentals,
        )
        if built is None:
            continue
        snap, closes_to_date, volumes_to_date = built
        prepared[symbol] = (snap, closes_to_date, volumes_to_date)

    prelim_categories = []
    for symbol, (snap, _, _) in prepared.items():
        _, parts = valuation_score(snap)
        prelim_categories.append({"ticker": symbol, "sector": snap.get("sector"), "categories": parts.get("categories", {})})
    percentiles = sector_percentiles(prelim_categories)

    rows = []
    for symbol, (snap, closes_to_date, volumes_to_date) in prepared.items():
        row = build_research(
            symbol, snap, closes_to_date, benchmark_closes_to_date, [],
            volumes=volumes_to_date, extended=snap, sector_percentile=percentiles.get(symbol),
            macro_regime=None,
        )
        row["action"] = (row.get("recommendation") or {}).get("action")
        rows.append(row)
    # Ticker is the deterministic tie-breaker. Concurrent cache loading must never change
    # which equally scored name enters the portfolio at the top-N boundary.
    rows.sort(key=lambda r: (-r["score"], r["ticker"]))
    return rows


# ---------------- portfolio simulation ----------------

def simulate_portfolio(weekly_rankings, week_dates, top_n, monthly_contribution):
    """$X/month DCA into the current top N, weekly rebalance: sell drop-outs/SELL, redeploy."""
    holdings = {}  # ticker -> shares
    cash = 0.0
    total_invested = 0.0
    last_month = None
    history = []

    for week_idx, (rows, as_of) in enumerate(zip(weekly_rankings, week_dates)):
        price_by_ticker = {r["ticker"]: r["price"] for r in rows if r.get("price")}
        top = rows[:top_n]
        top_tickers = {r["ticker"] for r in top}
        action_by_ticker = {r["ticker"]: r.get("action") for r in rows}

        for ticker in list(holdings.keys()):
            price = price_by_ticker.get(ticker)
            should_sell = ticker not in top_tickers or action_by_ticker.get(ticker) == "SELL"
            if should_sell and price:
                cash += holdings.pop(ticker) * price
            elif should_sell:
                holdings.pop(ticker, None)  # no price this week; can't value it, drop silently

        month_key = (as_of.year, as_of.month)
        if month_key != last_month:
            cash += monthly_contribution
            total_invested += monthly_contribution
            last_month = month_key

        if cash > 0 and top:
            per_stock = cash / len(top)
            for row in top:
                price = row.get("price")
                if price:
                    holdings[row["ticker"]] = holdings.get(row["ticker"], 0.0) + per_stock / price
            cash = 0.0

        value = cash + sum(shares * price_by_ticker.get(ticker, 0.0) for ticker, shares in holdings.items())
        history.append({
            "date": as_of.isoformat(), "value": round(value, 2), "invested": total_invested,
            "holdings": sorted(holdings.keys()), "top20": [r["ticker"] for r in top],
        })

    final_value = history[-1]["value"] if history else 0.0
    return {
        "history": history, "total_invested": total_invested, "final_value": round(final_value, 2),
        "return_pct": round((final_value / total_invested - 1) * 100, 2) if total_invested else None,
    }


def simulate_benchmark_dca(dates, closes, week_dates, monthly_contribution):
    shares, invested, last_month, history = 0.0, 0.0, None, []
    for as_of in week_dates:
        price = nearest_close(dates, closes, as_of)
        month_key = (as_of.year, as_of.month)
        if month_key != last_month and price:
            shares += monthly_contribution / price
            invested += monthly_contribution
            last_month = month_key
        value = shares * (price or 0)
        history.append({"date": as_of.isoformat(), "value": round(value, 2), "invested": invested})
    final_value = history[-1]["value"] if history else 0.0
    return {
        "history": history, "total_invested": invested, "final_value": round(final_value, 2),
        "return_pct": round((final_value / invested - 1) * 100, 2) if invested else None,
    }


def score_out_of_ten(strategy_return_pct, benchmark_return_pct):
    """Transparent, explainable 0-10: 5 = matched the benchmark, +/-1 point per 5 points of
    out/under-performance, capped at the ends. Not a black box - just documented arithmetic."""
    if strategy_return_pct is None or benchmark_return_pct is None:
        return None
    delta = strategy_return_pct - benchmark_return_pct
    return round(max(0.0, min(10.0, 5.0 + delta / 5.0)), 1)


# ---------------- entry point ----------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", type=int, default=52, help="Trailing weeks to simulate (default 52)")
    parser.add_argument("--universe-limit", type=int, default=120, help="Candidates to pull from advisor_universe.json (default 120)")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker override instead of the configured universe (for quick tests)")
    parser.add_argument("--top-n", type=int, default=20, help="Portfolio size each week (default 20)")
    parser.add_argument("--monthly-contribution", type=float, default=1000.0)
    parser.add_argument("--report-lag-days", type=int, default=REPORT_LAG_DAYS_DEFAULT,
                        help="Assumed days between a fiscal quarter ending and its numbers being public (default 45)")
    parser.add_argument("--benchmarks", type=str, default="SPY,QQQ,DIA,IWM")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between yfinance requests")
    parser.add_argument("--out", type=str, default=os.path.join(HERE, "backtest_historical_results.json"))
    parser.add_argument("--policy-suite", action="store_true",
                        help="Compare eight exit/trim policies with identical walk-forward entry signals")
    parser.add_argument("--spread-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--tax-bps", type=float, default=0.0,
                        help="Optional simplified realized-sale tax friction; tax-lot modeling remains provisional")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r pipeline/requirements.txt")
        sys.exit(1)

    symbols = load_universe(args.universe_limit, args.tickers)
    LOG.info(f"Fetching {len(symbols)} candidates + {args.benchmarks} ({args.weeks} weeks, "
              f"{args.report_lag_days}-day reporting lag)...")

    universe_data = {}
    for i, symbol in enumerate(symbols, 1):
        data = fetch_ticker_data(yf, symbol, args.delay)
        if data:
            universe_data[symbol] = data
        if i % 20 == 0:
            LOG.info(f"...{i}/{len(symbols)} candidates fetched ({len(universe_data)} usable)")
    LOG.info(f"Usable candidates: {len(universe_data)}/{len(symbols)}")

    benchmark_symbols = [s.strip().upper() for s in args.benchmarks.split(",") if s.strip()]
    benchmarks = {}
    for symbol in benchmark_symbols:
        data = fetch_benchmark(yf, symbol, args.delay)
        if data:
            benchmarks[symbol] = data
    if "SPY" not in benchmarks:
        LOG.error("Could not fetch SPY; aborting (it's required as the primary benchmark).")
        sys.exit(1)

    week_dates = weekly_dates(args.weeks)
    weekly_rankings = []
    for i, as_of in enumerate(week_dates, 1):
        idx = price_index(benchmarks["SPY"]["dates"], as_of)
        spy_closes_to_date = benchmarks["SPY"]["closes"][:idx + 1] if idx is not None else []
        rows = rank_week(universe_data, spy_closes_to_date, as_of, args.report_lag_days)
        weekly_rankings.append(rows)
        if i % 10 == 0 or i == len(week_dates):
            LOG.info(f"Ranked week {i}/{len(week_dates)} ({as_of.isoformat()}): "
                      f"{len(rows)} scored, top pick {rows[0]['ticker'] if rows else 'n/a'}")

    portfolio = simulate_portfolio(weekly_rankings, week_dates, args.top_n, args.monthly_contribution)
    benchmark_results = {
        symbol: simulate_benchmark_dca(data["dates"], data["closes"], week_dates, args.monthly_contribution)
        for symbol, data in benchmarks.items()
    }

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "weeks": args.weeks,
        "top_n": args.top_n,
        "monthly_contribution": args.monthly_contribution,
        "report_lag_days": args.report_lag_days,
        "universe_size_requested": len(symbols),
        "universe_size_usable": len(universe_data),
        "strategy": {
            "total_invested": portfolio["total_invested"],
            "final_value": portfolio["final_value"],
            "return_pct": portfolio["return_pct"],
        },
        "benchmarks": {
            symbol: {
                "total_invested": result["total_invested"],
                "final_value": result["final_value"],
                "return_pct": result["return_pct"],
                "score_out_of_10_vs_strategy": score_out_of_ten(result["return_pct"], portfolio["return_pct"]),
            }
            for symbol, result in benchmark_results.items()
        },
        "score_out_of_10_vs_spy": score_out_of_ten(portfolio["return_pct"], benchmark_results["SPY"]["return_pct"]),
    }

    print("\n" + "=" * 72)
    print(f"STRATEGY  invested ${portfolio['total_invested']:,.0f} -> ${portfolio['final_value']:,.0f} "
          f"({portfolio['return_pct']:+.1f}%)")
    for symbol, result in benchmark_results.items():
        print(f"{symbol:9s} invested ${result['total_invested']:,.0f} -> ${result['final_value']:,.0f} "
              f"({result['return_pct']:+.1f}%)")
    print(f"\nScore vs SPY: {summary['score_out_of_10_vs_spy']}/10 "
          "(5 = matched SPY, +/-1 per 5 points of out/under-performance)")
    print("=" * 72 + "\n")

    output = {"summary": summary, "portfolio": portfolio, "benchmarks": benchmark_results}
    if args.policy_suite:
        output["policy_comparison"] = compare_policies(
            weekly_rankings, week_dates, top_n=args.top_n,
            initial_capital=max(args.monthly_contribution * 12, 1),
            spread_bps=args.spread_bps, slippage_bps=args.slippage_bps, tax_bps=args.tax_bps,
        )
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2, default=str)
    LOG.info(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
