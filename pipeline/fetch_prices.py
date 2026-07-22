"""
fetch_prices.py
For every ticker appearing in the last 90 days of trades + the policy/ETF watchlist:
  - daily close, 30d % move (momentum)
  - VALUATION METRICS: price/sales, forward P/E, PEG   <-- the added screen
  - sector, market cap, name, dividend yield
Also computes each politician's rolling track record (90d fwd return vs SPY) -- cached weekly.

Writes:
  prices.json       (per-ticker snapshot + valuation)
  politicians.json  (track-record leaderboard, refreshed weekly)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

from common import (DATA_DIR, LOG, data_mode, load_json, load_store_json, save_json,
                    normalize_name, update_pipeline_status)

TRACK_RECORD_CACHE = os.path.join(DATA_DIR, "politicians.json")
TRACK_REFRESH_DAYS = 7


def collect_tickers():
    tickers = set()
    trades = load_json("trades.json") or {}
    for t in trades.get("trades", []):
        if t.get("ticker"):
            tickers.add(t["ticker"].upper())

    policy = load_json("policy_map.json", from_config=True) or {}
    for sec in policy.get("sectors", {}).values():
        tickers.update(sec.get("tickers", []))

    universe = load_json("universe.json", from_config=True) or {}
    tickers.update(universe.get("etfs", {}).keys())
    tickers.update(universe.get("retirement_core", []))

    tickers.discard("")
    return sorted(tickers)


def safe(info, *keys):
    for k in keys:
        v = info.get(k)
        if v is not None and v == v:  # not NaN
            return v
    return None


def fetch_snapshot(ticker, yf, etf_ids):
    """Return price plus valuation, profitability, balance-sheet, cash, and growth metrics."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        hist = tk.history(period="35d")
    except Exception as e:  # noqa: BLE001
        LOG.warn(f"{ticker}: fetch failed ({type(e).__name__})")
        return None

    price = safe(info, "currentPrice", "regularMarketPrice")
    if price is None and len(hist):
        price = float(hist["Close"].iloc[-1])

    pct_30d = None
    if len(hist) >= 2:
        first, last = float(hist["Close"].iloc[0]), float(hist["Close"].iloc[-1])
        if first:
            pct_30d = round((last - first) / first * 100, 2)

    is_etf = ticker in etf_ids or (info.get("quoteType") == "ETF")
    market_cap = safe(info, "marketCap")
    free_cash_flow = safe(info, "freeCashflow")
    debt_to_equity_percent = _round(safe(info, "debtToEquity"))

    snap = {
        "ticker": ticker,
        "name": safe(info, "shortName", "longName") or ticker,
        "price": round(price, 2) if price else None,
        "pct_30d": pct_30d,
        "sector": safe(info, "sector") or ("ETF" if is_etf else None),
        "market_cap": market_cap,
        "dividend_yield": safe(info, "dividendYield"),
        "is_etf": is_etf,
        # ----- valuation metrics -----
        "price_to_sales": _round(safe(info, "priceToSalesTrailing12Months")),
        "price_to_book": _round(safe(info, "priceToBook")),
        "forward_pe": _round(safe(info, "forwardPE")),
        "trailing_pe": _round(safe(info, "trailingPE")),
        "peg": _round(safe(info, "trailingPegRatio", "pegRatio")),
        # Yahoo reports debtToEquity as a percentage (e.g. 80 means 0.8x).
        "debt_to_equity": _round(debt_to_equity_percent / 100) if debt_to_equity_percent is not None else None,
        "current_ratio": _round(safe(info, "currentRatio")),
        "return_on_equity": _round(safe(info, "returnOnEquity"), 4),
        "profit_margin": _round(safe(info, "profitMargins"), 4),
        "free_cash_flow": _round(free_cash_flow, 0),
        "free_cash_flow_yield": _round(free_cash_flow / market_cap, 4) if free_cash_flow is not None and market_cap else None,
        "revenue_growth": _round(safe(info, "revenueGrowth"), 4),
        "earnings_growth": _round(safe(info, "earningsGrowth")),
    }
    return snap


def _round(v, n=2):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def build_prices():
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r requirements.txt")
        return None

    universe = load_json("universe.json", from_config=True) or {}
    etf_ids = set(universe.get("etfs", {}).keys())

    tickers = collect_tickers()
    LOG.info(f"Fetching prices + valuation for {len(tickers)} tickers")

    prices = {}
    for i, t in enumerate(tickers, 1):
        snap = fetch_snapshot(t, yf, etf_ids)
        if snap:
            prices[t] = snap
        if i % 25 == 0:
            LOG.info(f"  ...{i}/{len(tickers)}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": data_mode(load_json("trades.json") or {}),
        "count": len(prices),
        "prices": prices,
    }
    minimum = max(1, len(tickers) // 2)
    if len(prices) < minimum:
        message = f"Only {len(prices)}/{len(tickers)} price snapshots fetched"
        LOG.error(f"{message}; refusing to replace prices.json")
        update_pipeline_status("prices", status="error", source="Yahoo Finance", message=message)
        return None
    save_json("prices.json", payload)
    update_pipeline_status("prices", status="healthy", source="Yahoo Finance",
                           details={"requested": len(tickers), "received": len(prices)})
    LOG.info(f"Wrote prices.json with {len(prices)} tickers")
    return payload


# ---------- Politician track record ----------

def needs_track_refresh():
    cache = load_json("politicians.json")
    if not cache:
        return True
    history = load_store_json("trades_history.json") or load_json("trades.json") or {}
    if cache.get("data_mode") != data_mode(history):
        return True
    gen = cache.get("generated_at")
    if not gen:
        return True
    try:
        last = datetime.fromisoformat(gen)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last > timedelta(days=TRACK_REFRESH_DAYS)


def build_track_record():
    """
    For each politician's historical BUYS, compute 90-day forward return vs SPY.
    Expensive -> cached weekly. Uses trades.json history.
    """
    if not needs_track_refresh():
        LOG.info("Track record cache fresh (<7d). Skipping.")
        return

    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance missing; cannot build track record.")
        return

    trades = load_store_json("trades_history.json") or load_json("trades.json") or {}
    buys_by_pol = {}
    for t in trades.get("trades", []):
        if t.get("type") == "buy" and t.get("ticker") and t.get("trade_date"):
            buys_by_pol.setdefault(normalize_name(t["politician"]), []).append(t)

    # Pre-fetch SPY baseline once
    try:
        spy = yf.Ticker("SPY").history(period="2y")["Close"]
    except Exception:  # noqa: BLE001
        spy = None

    leaderboard = []
    for pol, buys in buys_by_pol.items():
        returns = []
        for b in buys:
            r = _fwd_return_vs_spy(b["ticker"], b["trade_date"], yf, spy)
            if r is not None:
                returns.append(r)
        if returns:
            avg = round(sum(returns) / len(returns), 2)
            leaderboard.append({
                "politician": pol,
                "n_buys_scored": len(returns),
                "avg_90d_alpha": avg,  # excess return vs SPY, percentage points
            })

    leaderboard.sort(key=lambda x: x["avg_90d_alpha"], reverse=True)
    # decile ranking for the scorer
    n = len(leaderboard)
    for i, row in enumerate(leaderboard):
        row["percentile"] = round(100 * (n - i) / n, 1) if n else 0

    save_json("politicians.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": data_mode(trades),
        "history_count": len(trades.get("trades", [])),
        "count": len(leaderboard),
        "leaderboard": leaderboard,
    })
    LOG.info(f"Wrote politicians.json with {len(leaderboard)} scored politicians")
    update_pipeline_status("track_record", status="healthy", source="historical trade store + Yahoo Finance",
                           details={"history_records": len(trades.get("trades", [])),
                                    "politicians_scored": len(leaderboard)})


def _fwd_return_vs_spy(ticker, trade_date, yf, spy):
    try:
        start = datetime.strptime(str(trade_date)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    end = start + timedelta(days=95)
    if end > datetime.now():
        return None  # not enough forward window yet
    try:
        hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"),
                                         end=end.strftime("%Y-%m-%d"))["Close"]
        if len(hist) < 2:
            return None
        stock_ret = (float(hist.iloc[-1]) - float(hist.iloc[0])) / float(hist.iloc[0]) * 100
    except Exception:  # noqa: BLE001
        return None

    spy_ret = 0.0
    if spy is not None:
        window = spy[(spy.index >= start.strftime("%Y-%m-%d")) & (spy.index <= end.strftime("%Y-%m-%d"))]
        if len(window) >= 2:
            spy_ret = (float(window.iloc[-1]) - float(window.iloc[0])) / float(window.iloc[0]) * 100
    return round(stock_ret - spy_ret, 2)


def main():
    if build_prices() is None:
        return 1
    build_track_record()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
