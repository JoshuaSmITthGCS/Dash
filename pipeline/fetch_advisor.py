"""Build the public investment-research dataset from Alpha Vantage + Yahoo fundamentals."""

import os
import time
from datetime import datetime, timezone

from advisor_engine import build_research
from alpha_vantage import AlphaVantageClient, AlphaVantageError, load_local_env
from common import LOG, save_json, update_pipeline_status
from fetch_prices import fetch_snapshot

DEFAULT_SYMBOLS = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL", "CRM", "ADBE",
    "JPM", "BAC", "GS", "V", "MA", "JNJ", "UNH", "LLY", "MRK", "ABBV",
    "WMT", "COST", "HD", "MCD", "NKE", "XOM", "CVX", "CAT", "GE", "NEE",
    "KO", "PEP", "PG", "PM", "TMO", "ABT", "DHR", "LIN", "HON", "UPS",
    "LOW", "SBUX", "DIS", "NFLX", "AMD", "QCOM", "TXN", "AMAT", "COP", "SLB",
)


def number(value, digits=4):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def daily_closes(payload):
    series = payload.get("Time Series (Daily)", {})
    rows = sorted(series.items())
    return [float(values["4. close"]) for _, values in rows if values.get("4. close")]


def yahoo_closes(symbol, yf):
    if not yf:
        return []
    try:
        history = yf.Ticker(symbol).history(period="6mo", auto_adjust=False)
        return [float(value) for value in history["Close"].dropna().tolist()]
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return []


def yahoo_snapshot(symbol, yf, attempts=2):
    if not yf:
        return None
    for attempt in range(attempts):
        snapshot = fetch_snapshot(symbol, yf, set())
        if snapshot:
            return snapshot
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return None


def overview_snapshot(symbol, overview, closes):
    market_cap = number(overview.get("MarketCapitalization"), 0)
    return {
        "ticker": symbol,
        "name": overview.get("Name") or symbol,
        "description": overview.get("Description") or "",
        "exchange": overview.get("Exchange"),
        "currency": overview.get("Currency"),
        "sector": overview.get("Sector"),
        "industry": overview.get("Industry"),
        "price": round(closes[-1], 2) if closes else None,
        "market_cap": market_cap,
        "dividend_yield": number(overview.get("DividendYield")),
        "is_etf": False,
        "price_to_sales": number(overview.get("PriceToSalesRatioTTM")),
        "price_to_book": number(overview.get("PriceToBookRatio")),
        "forward_pe": number(overview.get("ForwardPE")),
        "trailing_pe": number(overview.get("PERatio")),
        "peg": number(overview.get("PEGRatio")),
        "return_on_equity": number(overview.get("ReturnOnEquityTTM")),
        "profit_margin": number(overview.get("ProfitMargin")),
        "revenue_growth": number(overview.get("QuarterlyRevenueGrowthYOY")),
        "earnings_growth": number(overview.get("QuarterlyEarningsGrowthYOY")),
        "analyst_target_price": number(overview.get("AnalystTargetPrice"), 2),
        "week_52_high": number(overview.get("52WeekHigh"), 2),
        "week_52_low": number(overview.get("52WeekLow"), 2),
    }


def merge_snapshots(primary, fallback):
    if not fallback:
        return primary
    merged = dict(primary)
    for key, value in fallback.items():
        if merged.get(key) is None or merged.get(key) == "":
            merged[key] = value
    return merged


def compact_news(payload, symbol):
    items = []
    for row in payload.get("feed", [])[:12]:
        items.append({
            "title": row.get("title"), "url": row.get("url"), "source": row.get("source"),
            "published_at": row.get("time_published"), "summary": row.get("summary"),
            "overall_sentiment_score": number(row.get("overall_sentiment_score"), 3),
            "ticker_sentiment": [x for x in row.get("ticker_sentiment", []) if x.get("ticker") == symbol],
        })
    return items


def insider_summary(payload):
    buys = sells = 0
    for row in payload.get("data", [])[:100]:
        kind = str(row.get("acquisition_or_disposal", "")).upper()
        if kind == "A":
            buys += 1
        elif kind == "D":
            sells += 1
    return {"recent_acquisitions": buys, "recent_disposals": sells, "records_reviewed": min(100, len(payload.get("data", [])))}


def fetch_optional(client, function, **params):
    try:
        return client.query(function, **params)
    except (AlphaVantageError, OSError, ValueError) as exc:
        LOG.warn(f"{function} unavailable: {exc}")
        return {}


def macro_context(client):
    specs = {
        "treasury_10y": ("TREASURY_YIELD", {"interval": "monthly", "maturity": "10year"}),
        "federal_funds_rate": ("FEDERAL_FUNDS_RATE", {"interval": "monthly"}),
        "inflation": ("INFLATION", {}),
    }
    result = {}
    for key, (function, params) in specs.items():
        payload = fetch_optional(client, function, **params)
        first = next((row for row in payload.get("data", []) if number(row.get("value")) is not None), None)
        result[key] = {"value": number(first.get("value")) if first else None,
                       "date": first.get("date") if first else None,
                       "unit": payload.get("unit")}
    return result


def run():
    load_local_env()
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in os.getenv("ADVISOR_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",") if s.strip()))
    alpha_limit = max(0, min(5, int(os.getenv("ALPHA_ENRICH_LIMIT", "5"))))
    requested_enrichment = tuple(s.strip().upper() for s in os.getenv("ALPHA_ENRICH_SYMBOLS", "").split(",") if s.strip())
    enrichment_order = requested_enrichment or symbols
    eligible_enrichment = tuple(symbol for symbol in enrichment_order if symbol in symbols)
    alpha_symbols = set(eligible_enrichment[:alpha_limit])
    client = AlphaVantageClient()
    delay = float(os.getenv("ALPHA_VANTAGE_CALL_DELAY", "0"))
    try:
        import yfinance as yf
    except ImportError:
        yf = None

    benchmark_payload = fetch_optional(client, "TIME_SERIES_DAILY", symbol="SPY", outputsize="compact")
    benchmark = daily_closes(benchmark_payload) or yahoo_closes("SPY", yf)
    research, all_news = [], []
    alpha_failures, research_failures = [], []
    for symbol in symbols:
        try:
            fallback = yahoo_snapshot(symbol, yf)
            closes = yahoo_closes(symbol, yf)
            overview = daily = news_payload = insiders = {}
            if symbol in alpha_symbols:
                overview = fetch_optional(client, "OVERVIEW", symbol=symbol)
                time.sleep(delay)
                daily = fetch_optional(client, "TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
                time.sleep(delay)
                news_payload = fetch_optional(client, "NEWS_SENTIMENT", tickers=symbol, sort="LATEST", limit="12")
                time.sleep(delay)
                insiders = fetch_optional(client, "INSIDER_TRANSACTIONS", symbol=symbol)
                alpha_closes = daily_closes(daily)
                if alpha_closes:
                    closes = alpha_closes
                if not overview or not daily:
                    alpha_failures.append(symbol)
            news = compact_news(news_payload, symbol)
            all_news.extend({**item, "ticker": symbol} for item in news)
            primary = overview_snapshot(symbol, overview, closes) if overview else {"ticker": symbol}
            snapshot = merge_snapshots(primary, fallback)
            if not snapshot.get("name") or len(closes) < 21:
                raise ValueError("insufficient company snapshot or price history")
            if len(closes) >= 21:
                snapshot["pct_30d"] = round((closes[-1] / closes[-21] - 1) * 100, 2)
            row = build_research(symbol, snapshot, closes, benchmark, news)
            row["insider_activity"] = insider_summary(insiders)
            row["alpha_enriched"] = symbol in alpha_symbols and bool(overview)
            research.append(row)
            LOG.info(f"Advisor research complete for {symbol}")
        except Exception as exc:  # keep other symbols useful
            research_failures.append(symbol)
            LOG.error(f"{symbol}: advisor fetch failed ({type(exc).__name__}: {exc})")
        time.sleep(delay)

    if not research:
        update_pipeline_status("advisor", status="error", source="Alpha Vantage + Yahoo Finance",
                               message="No research records were produced")
        return None
    research.sort(key=lambda row: row["score"], reverse=True)
    ranked = research[:20]
    market_status = fetch_optional(client, "MARKET_STATUS")
    macro = macro_context(client)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1, "generated_at": generated_at, "data_mode": "live",
        "count": len(ranked), "universe_count": len(symbols), "universe": list(symbols), "benchmark": "SPY",
        "methodology": {
            "weights": {"fundamentals": 0.60, "market_behavior": 0.25, "news_sentiment": 0.15},
            "fundamental_weights": {"valuation": 0.40, "profitability": 0.25, "financial_health": 0.20, "growth": 0.15},
            "principle": "Fundamentals lead. Price behavior and news modify confidence; they do not replace business quality.",
        },
        "market": {"status": market_status.get("markets", []), "macro": macro},
        "research": ranked,
        "news": sorted(all_news, key=lambda item: item.get("published_at") or "", reverse=True)[:30],
        "source_status": {
            "alpha_vantage": {"status": "healthy" if not alpha_failures else "degraded", "failed_symbols": alpha_failures,
                              "enriched_symbols": sorted(alpha_symbols), "quota_strategy": "up to five symbols per refresh"},
            "yahoo_fundamentals": {"status": "degraded" if research_failures else ("healthy" if yf else "unavailable"),
                                   "failed_symbols": research_failures},
        },
        "disclaimer": "General research, not individualized investment advice. Verify filings, estimates, valuation context, and suitability before acting.",
    }
    save_json("advisor.json", payload)
    all_failures = sorted(set(alpha_failures + research_failures))
    update_pipeline_status("advisor", status="healthy" if not all_failures else "degraded",
                           source="Alpha Vantage + Yahoo Finance",
                           details={"universe": len(symbols), "scored": len(research), "ranked": len(ranked), "failed": all_failures})
    LOG.info(f"Wrote advisor.json with the top {len(ranked)} of {len(research)} scored companies")
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
