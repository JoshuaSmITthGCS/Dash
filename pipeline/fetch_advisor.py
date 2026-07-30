"""Build the public investment-research dataset from Alpha Vantage + Yahoo fundamentals."""

import os
import time
from datetime import datetime, timezone

from advisor_engine import RANKING_WEIGHTS, build_research
from alpha_vantage import AlphaVantageClient, AlphaVantageError, load_local_env
from common import LOG, load_json, save_json, update_pipeline_status
from fetch_prices import fetch_snapshot
from fundamentals_extended import derive_extended, extended_inputs
from market_history import (BASIS, hypothetical_vs_benchmark, sector_percentiles,
                            series_payload, weekly_grid)
from scorer import SETTINGS, valuation_score

UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}
DEFAULT_SYMBOLS = tuple(UNIVERSE.get("symbols", ()))
PUBLISH_LIMIT = int(UNIVERSE.get("publish_limit", 20))
# How many shortlisted companies get the multi-request financial-statement treatment.
EXTENDED_LIMIT = int(UNIVERSE.get("extended_limit", PUBLISH_LIMIT * 3))


def number(value, digits=4):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def daily_history(payload):
    series = payload.get("Time Series (Daily)", {})
    rows = sorted(series.items())
    dates = [day for day, values in rows if values.get("4. close")]
    closes = [float(values["4. close"]) for _, values in rows if values.get("4. close")]
    volumes = [float(values.get("5. volume") or 0) for _, values in rows if values.get("4. close")]
    return {"dates": dates, "closes": closes, "volumes": volumes}


EMPTY_HISTORY = {"dates": [], "closes": [], "volumes": []}


def yahoo_history(symbol, yf, period="2y", ticker_obj=None):
    """Dates, closes, and volumes. Two years so max drawdown and 52-week context are real."""
    if not yf:
        return dict(EMPTY_HISTORY)
    try:
        source = ticker_obj or yf.Ticker(symbol)
        frame = source.history(period=period, auto_adjust=False).dropna(subset=["Close"])
        return {
            "dates": [str(index)[:10] for index in frame.index],
            "closes": [float(value) for value in frame["Close"].tolist()],
            "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return dict(EMPTY_HISTORY)


def yahoo_snapshot(symbol, yf, ticker_obj=None, attempts=2):
    if not yf:
        return None
    for attempt in range(attempts):
        snapshot = fetch_snapshot(symbol, yf, set(), ticker_obj)
        if snapshot:
            return snapshot
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return None


def yahoo_extended(symbol, ticker_obj, snapshot, history):
    """Statement-derived quality, capital-allocation, and accounting metrics for one company."""
    if ticker_obj is None:
        return {}
    try:
        inputs = extended_inputs(ticker_obj)
        info = ticker_obj.info or {}
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: extended fundamentals unavailable ({type(exc).__name__})")
        return {}
    return derive_extended(
        annual=inputs["annual"], quarterly=inputs["quarterly"], info=info,
        market_cap=snapshot.get("market_cap"), price=snapshot.get("price"),
        sector=snapshot.get("sector"), closes=history["closes"], volumes=history["volumes"],
    )


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


def collect(symbol, client, yf, alpha_symbols, delay):
    """The cheap first pass: quote snapshot, two years of prices, and any Alpha Vantage extras.

    Financial statements are deliberately left out here. They cost several requests per
    company, so they are fetched later for shortlisted names only.
    """
    ticker_obj = yf.Ticker(symbol) if yf else None
    fallback = yahoo_snapshot(symbol, yf, ticker_obj)
    history = yahoo_history(symbol, yf, ticker_obj=ticker_obj)
    overview = daily = news_payload = insiders = {}
    alpha_failed = False
    if symbol in alpha_symbols:
        overview = fetch_optional(client, "OVERVIEW", symbol=symbol)
        time.sleep(delay)
        daily = fetch_optional(client, "TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
        time.sleep(delay)
        news_payload = fetch_optional(client, "NEWS_SENTIMENT", tickers=symbol, sort="LATEST", limit="12")
        time.sleep(delay)
        insiders = fetch_optional(client, "INSIDER_TRANSACTIONS", symbol=symbol)
        alpha_history = daily_history(daily)
        # Alpha Vantage only returns 100 sessions; Yahoo's two years wins whenever it exists.
        if alpha_history["closes"] and len(alpha_history["closes"]) > len(history["closes"]):
            history = alpha_history
        alpha_failed = not overview or not daily

    news = compact_news(news_payload, symbol)
    primary = overview_snapshot(symbol, overview, history["closes"]) if overview else {"ticker": symbol}
    snapshot = merge_snapshots(primary, fallback)
    if not snapshot.get("name") or len(history["closes"]) < 21:
        raise ValueError("insufficient company snapshot or price history")
    closes = history["closes"]
    snapshot["pct_30d"] = round((closes[-1] / closes[-21] - 1) * 100, 2)
    return {
        "symbol": symbol, "snapshot": snapshot, "extended": {}, "ticker_obj": ticker_obj,
        "history": history, "news": news,
        "insider_activity": insider_summary(insiders),
        "alpha_enriched": symbol in alpha_symbols and bool(overview),
        "alpha_failed": alpha_failed,
    }


def enrich(contexts, limit, delay):
    """Pull financial statements for the shortlist and fold the derived metrics into each snapshot.

    Shortlisting is done on core fundamentals alone, which every candidate has in equal
    measure, so nothing is ranked down merely for being outside the statement budget.
    """
    ranked = sorted(contexts, key=lambda context: valuation_score(context["snapshot"])[0] or 0,
                    reverse=True)
    enriched = 0
    for context in ranked[:limit]:
        extended = yahoo_extended(context["symbol"], context["ticker_obj"],
                                  context["snapshot"], context["history"])
        if extended:
            context["extended"] = extended
            context["snapshot"] = {**context["snapshot"], **extended}
            enriched += 1
        time.sleep(delay)
    LOG.info(f"Extended statement metrics derived for {enriched}/{min(limit, len(contexts))} shortlisted companies")
    return enriched


def attach_history(row, context, grid, benchmark_growth):
    """Weekly series plus the equal-dollar comparison against the S&P 500."""
    history = context["history"]
    payload = series_payload(history["dates"], history["closes"], grid)
    if not payload:
        return
    row["history"] = {"dates": grid, **payload}
    row["hypothetical"] = hypothetical_vs_benchmark(payload["growth"], benchmark_growth)


def run():
    load_local_env()
    configured = os.getenv("ADVISOR_SYMBOLS")
    requested_symbols = configured.split(",") if configured else DEFAULT_SYMBOLS
    symbols = tuple(dict.fromkeys(str(s).strip().upper() for s in requested_symbols if str(s).strip()))
    publish_limit = max(1, int(os.getenv("ADVISOR_PUBLISH_LIMIT", PUBLISH_LIMIT)))
    extended_limit = max(publish_limit, int(os.getenv("ADVISOR_EXTENDED_LIMIT", EXTENDED_LIMIT)))
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
    benchmark = daily_history(benchmark_payload)
    yahoo_benchmark = yahoo_history("SPY", yf)
    if len(yahoo_benchmark["closes"]) > len(benchmark["closes"]):
        benchmark = yahoo_benchmark

    contexts, all_news = [], []
    alpha_failures, research_failures = [], []
    for symbol in symbols:
        try:
            context = collect(symbol, client, yf, alpha_symbols, delay)
            contexts.append(context)
            all_news.extend({**item, "ticker": symbol} for item in context["news"])
            if context["alpha_failed"]:
                alpha_failures.append(symbol)
            LOG.info(f"Advisor research collected for {symbol}")
        except Exception as exc:  # keep other symbols useful
            research_failures.append(symbol)
            LOG.error(f"{symbol}: advisor fetch failed ({type(exc).__name__}: {exc})")
        time.sleep(delay)

    if not contexts:
        update_pipeline_status("advisor", status="error", source="Alpha Vantage + Yahoo Finance",
                               message="No research records were produced")
        return None

    enriched_count = enrich(contexts, extended_limit, delay)

    # Valuation is scored once up front so 'cheap for its sector' can be measured against peers
    # before the final score is assembled.
    percentiles = sector_percentiles([
        {"ticker": context["symbol"], "sector": context["snapshot"].get("sector"),
         "categories": valuation_score(context["snapshot"])[1].get("categories", {})}
        for context in contexts
    ])

    research = []
    for context in contexts:
        row = build_research(
            context["symbol"], context["snapshot"], context["history"]["closes"], benchmark["closes"],
            context["news"], volumes=context["history"]["volumes"], extended=context["extended"],
            sector_percentile=percentiles.get(context["symbol"]),
        )
        row["insider_activity"] = context["insider_activity"]
        row["alpha_enriched"] = context["alpha_enriched"]
        research.append(row)

    research.sort(key=lambda row: row["score"], reverse=True)
    ranked = research[:publish_limit]

    grid = weekly_grid(benchmark["dates"])
    benchmark_series = series_payload(benchmark["dates"], benchmark["closes"], grid)
    benchmark_growth = (benchmark_series or {}).get("growth")
    contexts_by_symbol = {context["symbol"]: context for context in contexts}
    for row in ranked:
        attach_history(row, contexts_by_symbol[row["ticker"]], grid, benchmark_growth)

    market_status = fetch_optional(client, "MARKET_STATUS")
    macro = macro_context(client)
    generated_at = datetime.now(timezone.utc).isoformat()
    fundamentals_cfg = SETTINGS["fundamentals"]
    payload = {
        "schema_version": 1, "generated_at": generated_at, "data_mode": "live",
        "count": len(ranked), "universe_count": len(symbols), "universe": list(symbols),
        "publish_limit": publish_limit, "statement_enriched_count": enriched_count, "benchmark": "SPY",
        "methodology": {
            "weights": RANKING_WEIGHTS,
            "fundamental_weights": fundamentals_cfg["category_weights"],
            "metric_weights": fundamentals_cfg["metric_weights"],
            "modifiers": SETTINGS.get("modifiers", {}),
            "principle": "Fundamentals lead. Price behavior and news modify confidence; they do not replace business quality.",
        },
        "market": {"status": market_status.get("markets", []), "macro": macro},
        "benchmark_history": {"symbol": "SPY", "dates": grid, **(benchmark_series or {})},
        "hypothetical_basis": BASIS,
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
