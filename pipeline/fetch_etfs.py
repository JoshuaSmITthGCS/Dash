"""Rank a 40-fund ETF watchlist against itself on the metrics that actually apply to a
diversified fund: performance, risk-adjusted return, cost, liquidity, and issuer quality.
A single stock's fundamentals ratios (PEG, P/S, ROE...) don't translate to a basket of
holdings, so ETFs are scored and ranked independently of the stock research pipeline.

Every fund is also compared against just buying the S&P 500 (SPY) or the Dow (DIA) —
both are themselves part of the scored universe, so the comparison is apples-to-apples.
"""

from math import sqrt
from datetime import datetime, timezone

from advisor_engine import max_drawdown
from common import LOG, load_json, save_json, update_pipeline_status

UNIVERSE = load_json("universe.json", from_config=True) or {}
ETFS = UNIVERSE.get("etfs", {})
SP500_TICKER = "SPY"
DOW_TICKER = "DIA"

# Trading-day windows for the performance and vs-benchmark comparisons.
WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756}

# Analyst ratings (Morningstar/CFRA) require a paid feed; issuer reputation is the free
# proxy used for the "quality" bucket instead. Unlisted issuers default to a middling 60.
ISSUER_QUALITY = {
    "Vanguard": 100, "iShares": 98, "State Street": 95, "Schwab": 92,
    "Invesco": 85, "JPMorgan": 85, "VanEck": 75, "ARK": 55,
}

SCORE_WEIGHTS = {"performance": 0.35, "risk": 0.25, "cost": 0.15, "liquidity": 0.15, "quality": 0.10}


def price_history(symbol, yf, ticker_obj=None):
    try:
        source = ticker_obj or yf.Ticker(symbol)
        frame = source.history(period="3y", auto_adjust=False).dropna(subset=["Close"])
        return {
            "closes": [float(value) for value in frame["Close"].tolist()],
            "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return {"closes": [], "volumes": []}


def etf_snapshot(ticker, yf, ticker_obj=None):
    try:
        tk = ticker_obj or yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: Yahoo snapshot unavailable ({type(exc).__name__})")
        return {}
    return {
        "price": info.get("regularMarketPrice") or info.get("navPrice"),
        "aum": info.get("totalAssets"),
        "bid": info.get("bid"),
        "ask": info.get("ask"),
    }


def period_return(closes, days):
    if len(closes) <= days or not closes[-days - 1]:
        return None
    return round((closes[-1] / closes[-days - 1] - 1) * 100, 2)


def daily_returns(closes):
    return [(b / a) - 1 for a, b in zip(closes[:-1], closes[1:]) if a]


def sharpe_ratio(rets):
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / len(rets)
    std = sqrt(variance)
    return round((mean / std) * sqrt(252), 2) if std else None


def sortino_ratio(rets):
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    downside = [min(0.0, r) for r in rets]
    downside_std = sqrt(sum(d * d for d in downside) / len(downside))
    return round((mean / downside_std) * sqrt(252), 2) if downside_std else None


def beta_vs_benchmark(rets, benchmark_rets):
    n = min(len(rets), len(benchmark_rets))
    if n < 20:
        return None
    a, b = rets[-n:], benchmark_rets[-n:]
    mean_a, mean_b = sum(a) / n, sum(b) / n
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / n
    variance_b = sum((y - mean_b) ** 2 for y in b) / n
    return round(covariance / variance_b, 2) if variance_b else None


def percentile_scores(values, higher_is_better=True):
    """Map a batch of possibly-missing raw values onto 0-100 so unlike metrics (a return
    percentage, an expense ratio, an AUM in dollars) can be combined into one score.
    A fund missing a metric stays neutral rather than being punished for lacking it.
    """
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    scores = [50.0] * len(values)
    if len(present) < 2:
        return scores
    ordered = sorted(present, key=lambda pair: pair[1])
    n = len(ordered)
    for rank, (i, _) in enumerate(ordered):
        pct = 100 * rank / (n - 1)
        scores[i] = pct if higher_is_better else 100 - pct
    return scores


def _average(values):
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else 50.0


def build_etf_row(ticker, meta, snapshot, closes, volumes, benchmark_daily_returns):
    rets = daily_returns(closes)
    avg_volume = sum(volumes[-30:]) / len(volumes[-30:]) if len(volumes) >= 5 else None
    price = closes[-1] if closes else snapshot.get("price")
    bid, ask = snapshot.get("bid"), snapshot.get("ask")
    spread_pct = None
    if bid and ask and ask >= bid > 0:
        mid = (bid + ask) / 2
        spread_pct = round((ask - bid) / mid * 100, 3) if mid else None

    return {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "category": meta.get("category", "etf"),
        "sector": meta.get("category", "etf").replace("_", " ").title(),
        "confidence": 1.0,
        "issuer": meta.get("issuer", "Other"),
        "expense_ratio": meta.get("expense_ratio"),
        "price": round(price, 2) if price else None,
        "aum": snapshot.get("aum"),
        "avg_dollar_volume": round(avg_volume * price, 0) if avg_volume and price else None,
        "bid_ask_spread_pct": spread_pct,
        "returns": {label: period_return(closes, days) for label, days in WINDOWS.items()},
        "max_drawdown": max_drawdown(closes),
        "sharpe_ratio": sharpe_ratio(rets),
        "sortino_ratio": sortino_ratio(rets),
        "beta": beta_vs_benchmark(rets, benchmark_daily_returns),
    }


def score_etf_universe(rows, sp500_ticker=SP500_TICKER, dow_ticker=DOW_TICKER):
    """Rank the batch against itself: normalize every metric to a 0-100 percentile within
    this group, blend into the five weighted buckets, then diff each fund's own returns
    against the S&P 500 and Dow rows already sitting in the same batch."""
    window_labels = list(WINDOWS.keys())
    window_percentiles = {
        label: percentile_scores([row["returns"][label] for row in rows], higher_is_better=True)
        for label in window_labels
    }
    risk_percentiles = {
        "sharpe_ratio": percentile_scores([row["sharpe_ratio"] for row in rows], higher_is_better=True),
        "sortino_ratio": percentile_scores([row["sortino_ratio"] for row in rows], higher_is_better=True),
        "max_drawdown": percentile_scores([row["max_drawdown"] for row in rows], higher_is_better=True),
    }
    cost_percentiles = percentile_scores([row["expense_ratio"] for row in rows], higher_is_better=False)
    liquidity_percentiles = {
        "aum": percentile_scores([row["aum"] for row in rows], higher_is_better=True),
        "avg_dollar_volume": percentile_scores([row["avg_dollar_volume"] for row in rows], higher_is_better=True),
        "bid_ask_spread_pct": percentile_scores([row["bid_ask_spread_pct"] for row in rows], higher_is_better=False),
    }

    sp500_returns = next((row["returns"] for row in rows if row["ticker"] == sp500_ticker), None)
    dow_returns = next((row["returns"] for row in rows if row["ticker"] == dow_ticker), None)

    scored = []
    for idx, row in enumerate(rows):
        performance = _average([
            window_percentiles[label][idx] for label in window_labels if row["returns"][label] is not None
        ])
        risk = _average([
            risk_percentiles[key][idx] for key in ("sharpe_ratio", "sortino_ratio", "max_drawdown")
            if row[key] is not None
        ])
        cost = cost_percentiles[idx] if row["expense_ratio"] is not None else 50.0
        liquidity = _average([
            liquidity_percentiles[key][idx] for key in ("aum", "avg_dollar_volume", "bid_ask_spread_pct")
            if row[key] is not None
        ])
        quality = ISSUER_QUALITY.get(row["issuer"], 60)
        buckets = {"performance": performance, "risk": risk, "cost": cost,
                   "liquidity": liquidity, "quality": quality}
        overall = round(sum(buckets[bucket] * weight for bucket, weight in SCORE_WEIGHTS.items()), 1)

        vs_benchmarks = {}
        for label in window_labels:
            etf_ret = row["returns"][label]
            sp_ret = sp500_returns[label] if sp500_returns else None
            dow_ret = dow_returns[label] if dow_returns else None
            vs_benchmarks[f"sp500_{label}"] = (
                round(etf_ret - sp_ret, 2) if etf_ret is not None and sp_ret is not None else None
            )
            vs_benchmarks[f"dow_{label}"] = (
                round(etf_ret - dow_ret, 2) if etf_ret is not None and dow_ret is not None else None
            )

        scored.append({
            **row,
            "scores": {**buckets, "overall": overall},
            "vs_benchmarks": vs_benchmarks,
        })

    scored.sort(key=lambda item: item["scores"]["overall"], reverse=True)
    for rank, row in enumerate(scored):
        row["overall_rank"] = rank + 1
    return scored


def build_etfs():
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r requirements.txt")
        return None

    tickers = list(ETFS.keys())
    histories = {ticker: price_history(ticker, yf) for ticker in tickers}
    benchmark_daily = daily_returns(histories.get(SP500_TICKER, {"closes": []})["closes"])

    raw_rows = []
    for ticker in tickers:
        history = histories[ticker]
        if len(history["closes"]) < 30:
            LOG.warn(f"{ticker}: not enough price history for ETF metrics")
            continue
        snapshot = etf_snapshot(ticker, yf)
        raw_rows.append(build_etf_row(ticker, ETFS[ticker], snapshot, history["closes"], history["volumes"], benchmark_daily))

    have_benchmarks = {SP500_TICKER, DOW_TICKER}.issubset({row["ticker"] for row in raw_rows})
    if not have_benchmarks:
        message = "S&P 500 (SPY) and/or Dow (DIA) benchmark rows missing; cannot score the watchlist against them"
        LOG.error(message)
        update_pipeline_status("etfs", status="error", source="Yahoo Finance", message=message)
        return None

    scored = score_etf_universe(raw_rows)
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "benchmarks": {"sp500": SP500_TICKER, "dow": DOW_TICKER},
        "count": len(scored),
        "etfs": scored,
    }
    minimum = max(1, len(tickers) // 2)
    if len(scored) < minimum:
        message = f"Only {len(scored)}/{len(tickers)} ETF snapshots fetched"
        LOG.error(f"{message}; refusing to replace etfs.json")
        update_pipeline_status("etfs", status="error", source="Yahoo Finance", message=message)
        return None

    save_json("etfs.json", payload)
    update_pipeline_status("etfs", status="healthy", source="Yahoo Finance",
                           details={"requested": len(tickers), "received": len(scored)})
    LOG.info(f"Wrote etfs.json with {len(scored)} ETFs")
    return payload


def main():
    return 0 if build_etfs() is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
