"""Build the public investment-research dataset from Alpha Vantage + Yahoo fundamentals."""

import math
import os
import re
import statistics
import time
from datetime import datetime, timezone

from advisor_engine import RANKING_WEIGHTS, build_research
from alpha_vantage import AlphaVantageClient, AlphaVantageError, load_local_env
from cache import CACHE, limiter_for, parallel_map, retry_with_backoff
from canonical_metrics import Observation
from providers import YahooAdapter
from common import LOG, load_json, save_json, update_pipeline_status
from fetch_prices import fetch_snapshot
from fundamentals_extended import derive_extended, earnings_surprise_rows, extended_inputs
from insider_signal import summarize as summarize_insiders
import pit_store
from fred import FredClient, FredError, fetch_regime
from market_history import (BASIS, chart_grid, hypothetical_vs_benchmark, sector_percentiles,
                            series_payload)
from peer_groups import canonical_percentiles
from observability import diagnostics_payload, run_manifest
from marketaux import (MarketauxClient, MarketauxError, advisor_articles,
                       advisor_articles_for_symbols)
from scorer import SETTINGS, valuation_score
from sec_edgar import SecEdgarClient
from theme_signals import EdgarThemeSignals
from themes import build_theme_screen, empty_screen, load_themes

UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}
DEFAULT_SYMBOLS = tuple(UNIVERSE.get("symbols", ()))
PUBLISH_LIMIT = int(UNIVERSE.get("publish_limit", 20))
MIN_ALPHA_PRIMARY_RELEVANCE = 0.8
# How many shortlisted companies get the multi-request financial-statement treatment.
EXTENDED_LIMIT = int(UNIVERSE.get("extended_limit", PUBLISH_LIMIT * 3))
PORTFOLIO_SYMBOLS = tuple(UNIVERSE.get("portfolio_symbols", ()))
INCUMBENT_ENRICH_LIMIT = 20
CHALLENGER_ENRICH_LIMIT = 5
NEWS_DISCOVERY_LIMIT = 75

# The unpublished remainder of the universe rides along so the value and momentum screens
# can scan more than the leaderboard. It carries only the fields those screens actually
# read - the full technical block is roughly three times the size, and at a universe of
# several hundred names that difference is most of the payload the browser downloads.
# Keep this in sync with src/lib/researchScreens.js.
SCREEN_TECHNICAL_FIELDS = (
    "return_5d", "return_20d", "momentum_12_1", "momentum_12_1_pct", "risk_adjusted",
    "relative_strength", "relative_strength_20d", "volume_confirmation",
    "pct_above_52w_low",
)


def resolve_refresh_symbols(
    requested_symbols,
    configured_portfolio,
    portfolio_override="",
    previous_portfolio=(),
):
    """Include every valid current holding in Yahoo fetches and portfolio coverage."""
    dynamic_portfolio = portfolio_override.split(",") if portfolio_override else ()

    def valid_symbols(values):
        normalized = []
        for value in values:
            symbol = str(value or "").strip().upper()
            if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
                normalized.append(symbol)
        return normalized

    portfolio_symbols = tuple(dict.fromkeys(
        (
            *valid_symbols(configured_portfolio),
            *valid_symbols(previous_portfolio),
            *valid_symbols(dynamic_portfolio),
        )
    ))
    symbols = tuple(dict.fromkeys(
        (*valid_symbols(requested_symbols), *portfolio_symbols)
    ))
    return symbols, portfolio_symbols


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


def yahoo_history(symbol, yf, period="2y", ticker_obj=None, cache=None):
    """Dates, closes, and volumes. Two years so max drawdown and 52-week context are real.

    Served from the on-disk cache when a recent copy exists, which is what makes a rerun
    cheap and keeps the universe sweep off Yahoo's undocumented rate limiter.
    """
    if not yf:
        return dict(EMPTY_HISTORY)
    cache = cache or CACHE

    def produce():
        source = ticker_obj or yf.Ticker(symbol)
        frame = source.history(period=period, auto_adjust=False).dropna(subset=["Close"])
        if frame.empty:
            raise ValueError("empty price frame")
        return {
            "dates": [str(index)[:10] for index in frame.index],
            "closes": [float(value) for value in frame["Close"].tolist()],
            "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
        }

    try:
        return cache.fetch("price_history", f"{symbol}:{period}", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return dict(EMPTY_HISTORY)


def prefetch_histories(symbols, yf, period="2y", cache=None):
    """Warm the price cache for the whole universe in a handful of HTTP calls.

    ``yf.download`` batches many symbols into far fewer requests than one Ticker call each,
    which is both the biggest speed win available and the most reliable way to stay under a
    rate limit nobody publishes. Anything the batch misses falls back to a per-symbol fetch
    at the normal call site, so a partial batch degrades rather than fails.
    """
    if not yf or not symbols:
        return 0
    cache = cache or CACHE
    missing = [symbol for symbol in symbols
               if cache.get("price_history", f"{symbol}:{period}") is None]
    if not missing:
        LOG.info(f"Price history: all {len(symbols)} symbols served from cache")
        return 0
    warmed = 0
    batch_size = int(os.getenv("YAHOO_BATCH_SIZE", "60"))
    for start in range(0, len(missing), batch_size):
        chunk = missing[start:start + batch_size]
        try:
            frame = retry_with_backoff(
                lambda chunk=chunk: yf.download(chunk, period=period, auto_adjust=False,
                                                group_by="ticker", progress=False, threads=True),
                description=f"batch history for {len(chunk)} symbols")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"batch history failed ({type(exc).__name__}); "
                     "per-symbol fetches will cover this chunk")
            continue
        for symbol in chunk:
            payload = YahooAdapter.extract_symbol_frame(frame, symbol, single=len(chunk) == 1)
            if payload:
                cache.set("price_history", f"{symbol}:{period}", payload, source="yahoo")
                warmed += 1
    LOG.info(f"Price history: warmed {warmed}/{len(missing)} uncached symbols in batches")
    return warmed


def yahoo_snapshot(symbol, yf, ticker_obj=None, attempts=2, cache=None):
    """Quote-derived snapshot for one company, served from cache when it is fresh."""
    if not yf:
        return None
    cache = cache or CACHE
    cached = cache.get("quote", f"snapshot:{symbol}")
    if cached:
        return cached
    for attempt in range(attempts):
        snapshot = fetch_snapshot(symbol, yf, set(), ticker_obj)
        if snapshot:
            return cache.set("quote", f"snapshot:{symbol}", snapshot, source="yahoo")
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return None


def prefetch_snapshots(symbols, yf, cache=None):
    """Warm the quote cache in parallel so the sequential collect loop mostly reads memory.

    Quotes cannot be batched the way price history can - each one is its own request - so
    the lever here is concurrency rather than batching. The pool is bounded and paced by the
    Yahoo rate limiter, which is what makes a universe of several hundred names finish
    inside the workflow's timeout instead of crawling through them one at a time.
    """
    if not yf or not symbols:
        return 0
    cache = cache or CACHE
    missing = [symbol for symbol in symbols
               if cache.get("quote", f"snapshot:{symbol}") is None]
    if not missing:
        LOG.info(f"Quotes: all {len(symbols)} symbols served from cache")
        return 0

    def fetch_one(symbol):
        limiter_for("yahoo").acquire()
        snapshot = fetch_snapshot(symbol, yf, set())
        if snapshot:
            cache.set("quote", f"snapshot:{symbol}", snapshot, source="yahoo")
            return 1
        return 0

    workers = int(os.getenv("YAHOO_QUOTE_WORKERS", "6"))
    warmed = sum(result or 0 for result in
                 parallel_map(fetch_one, missing, provider="yahoo", max_workers=workers))
    LOG.info(f"Quotes: warmed {warmed}/{len(missing)} uncached symbols")
    return warmed


# Earnings surprises come from a scraped page, one request per symbol, on an endpoint that
# is noticeably flakier than the statement bundle. Opt-in for the same reason option chains
# are: a per-symbol extra request has to earn its place. The first production run scored
# 0/40 companies on it, so leaving it on by default would spend ~110 requests to populate a
# metric that never resolves. The weight stays in config - missing values reweight - so
# enabling it later needs no other change.
EARNINGS_SURPRISE_ENABLED = os.getenv("ENABLE_EARNINGS_SURPRISE", "").lower() in {"1", "true", "yes"}
EARNINGS_SURPRISE_STATS = {"requested": 0, "resolved": 0, "failed": 0}


def fetch_earnings_surprises(symbol, ticker_obj, cache=None):
    """Cached, opt-in earnings-surprise history with visible failures."""
    if not EARNINGS_SURPRISE_ENABLED or ticker_obj is None:
        return []
    cache = cache or CACHE
    EARNINGS_SURPRISE_STATS["requested"] += 1

    def produce():
        failures = []
        rows = earnings_surprise_rows(ticker_obj, on_error=failures.append)
        if failures:
            raise failures[0]
        return rows

    try:
        rows = cache.fetch("statements", f"earnings_surprise:{symbol}", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        EARNINGS_SURPRISE_STATS["failed"] += 1
        LOG.warn(f"{symbol}: earnings surprise history unavailable ({type(exc).__name__})")
        return []
    if rows:
        EARNINGS_SURPRISE_STATS["resolved"] += 1
    return rows or []


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
    result = derive_extended(
        annual=inputs["annual"], quarterly=inputs["quarterly"], info=info,
        market_cap=snapshot.get("market_cap"), price=snapshot.get("price"),
        sector=snapshot.get("sector"), closes=history["closes"], volumes=history["volumes"],
        earnings_surprises=fetch_earnings_surprises(symbol, ticker_obj),
    )
    if os.getenv("ENABLE_OPTIONS_VOLATILITY", "").lower() in {"1", "true", "yes"}:
        result.update(yahoo_options_volatility(ticker_obj, snapshot.get("price"), history["closes"]))
    return result


def yahoo_options_volatility(ticker_obj, price, closes):
    """Near-the-money implied volatility against 20-session realized volatility.

    Options data is opt-in because each symbol adds an option-chain request. Median IV
    across calls and puts within 10% of spot is more robust than trusting one contract.
    """
    realized = None
    if len(closes) >= 21 and all(value > 0 for value in closes[-21:]):
        returns = [math.log(closes[index] / closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
        realized = statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    try:
        expirations = ticker_obj.options
        if not expirations or not price:
            return {"implied_volatility": None, "realized_volatility_20d": number(realized)}
        chain = ticker_obj.option_chain(expirations[0])
        values = []
        for frame in (chain.calls, chain.puts):
            for _, contract in frame.iterrows():
                strike, iv = contract.get("strike"), contract.get("impliedVolatility")
                if strike and iv and abs(strike / price - 1) <= 0.10 and 0 < iv < 5:
                    values.append(float(iv))
        implied = statistics.median(values) if values else None
        return {
            "implied_volatility": number(implied),
            "realized_volatility_20d": number(realized),
            "implied_realized_vol_ratio": number(implied / realized) if implied and realized else None,
            "options_expiration_sampled": expirations[0],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"options volatility unavailable ({type(exc).__name__})")
        return {"implied_volatility": None, "realized_volatility_20d": number(realized)}


def overview_snapshot(symbol, overview, closes):
    market_cap = number(overview.get("MarketCapitalization"), 0)
    fetched_at = datetime.now(timezone.utc).isoformat()
    observation_specs = {
        "market_cap": ("MarketCapitalization", "usd", False, False),
        "forward_pe": ("ForwardPE", "multiple", False, True),
        "provider_peg": ("PEGRatio", "multiple", False, False),
        "price_to_book": ("PriceToBookRatio", "multiple", False, False),
        "trailing_revenue_growth": ("QuarterlyRevenueGrowthYOY", "decimal", False, False),
        "quarterly_eps_growth": ("QuarterlyEarningsGrowthYOY", "decimal", False, False),
    }
    observations = {}
    for metric_id, (field, unit, is_ttm, is_forward) in observation_specs.items():
        value = number(overview.get(field))
        if value is None:
            continue
        flags = [] if metric_id == "market_cap" else ["provider_period_not_supplied"]
        if metric_id == "provider_peg":
            flags.append("unknown_growth_definition_and_horizon")
        if metric_id in ("trailing_revenue_growth", "quarterly_eps_growth"):
            flags.append("quarterly_not_ttm")
        observations[metric_id] = [Observation(
            value=value, unit=unit, source="alpha_vantage", source_field=field,
            observed_at=fetched_at, fetched_at=fetched_at, is_ttm=is_ttm,
            is_forward=is_forward, quality_flags=flags,
        ).to_dict()]
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
        "observations": observations,
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
    observations = {}
    for source in (primary.get("observations", {}), fallback.get("observations", {})):
        for metric_id, rows in source.items():
            observations.setdefault(metric_id, []).extend(rows)
    if observations:
        merged["observations"] = observations
    return merged


def compact_news(payload, symbol):
    """Keep only articles whose primary Alpha Vantage entity is unambiguous.

    NEWS_SENTIMENT may return an article because the requested company is mentioned
    incidentally. The highest-relevance entity is the article's ticker; requiring a
    strong primary score keeps broad market stories from being assigned arbitrarily.
    """
    items = []
    for row in payload.get("feed", [])[:12]:
        entities = []
        for entity in row.get("ticker_sentiment", []):
            try:
                relevance = float(entity.get("relevance_score"))
            except (TypeError, ValueError):
                continue
            ticker = str(entity.get("ticker") or "").strip().upper()
            if ticker:
                entities.append((relevance, ticker, entity))
        if not entities:
            continue
        relevance, primary_ticker, primary_entity = max(entities, key=lambda item: item[0])
        if relevance < MIN_ALPHA_PRIMARY_RELEVANCE:
            continue
        primary_entity = {**primary_entity, "ticker": primary_ticker}
        items.append({
            "title": row.get("title"), "url": row.get("url"), "source": row.get("source"),
            "published_at": row.get("time_published"), "summary": row.get("summary"),
            "overall_sentiment_score": number(row.get("overall_sentiment_score"), 3),
            "ticker_sentiment": [primary_entity],
            "ticker": primary_ticker,
        })
    return items


def latest_unique_news(items, limit=30):
    """Newest article per URL, preserving the primary ticker assigned by its adapter."""
    result = []
    seen = set()
    ordered = sorted(items, key=lambda item: item.get("published_at") or "", reverse=True)
    for item in ordered:
        url = item.get("url")
        identity = url or (item.get("title"), item.get("ticker"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
        if len(result) == limit:
            break
    return result


def fetch_discovery_news(client, symbols, limit=NEWS_DISCOVERY_LIMIT):
    """Fetch one broader company-news batch for strong candidates beyond the leaders."""
    if not client:
        return []
    selected = tuple(dict.fromkeys(symbols))[:limit]
    if not selected:
        return []
    payload = client.news(
        symbols=",".join(selected),
        filter_entities="true",
        language="en",
        group_similar="true",
        limit=limit,
    )
    return advisor_articles_for_symbols(payload, selected)


def curate_candidate_news(items, research_context, limit=70, discovery_slots=25):
    """Reserve room for broader candidates so leader coverage cannot crowd them out."""
    annotated = [
        {**item, **research_context.get(item.get("ticker"), {})}
        for item in latest_unique_news(items, limit=max(limit * 3, limit))
    ]
    leaders = [item for item in annotated if item.get("published_research")]
    discovery = [item for item in annotated if not item.get("published_research")]
    selected_discovery = discovery[:min(discovery_slots, limit)]
    selected_leaders = leaders[:limit - len(selected_discovery)]
    remaining = limit - len(selected_leaders) - len(selected_discovery)
    if remaining:
        selected_discovery.extend(discovery[len(selected_discovery):len(selected_discovery) + remaining])
    return [*selected_leaders, *selected_discovery]


def insider_summary(payload):
    buys = sells = 0
    for row in payload.get("data", [])[:100]:
        kind = str(row.get("acquisition_or_disposal", "")).upper()
        if kind == "A":
            buys += 1
        elif kind == "D":
            sells += 1
    return {"recent_acquisitions": buys, "recent_disposals": sells, "records_reviewed": min(100, len(payload.get("data", [])))}


def collect_insider_signals(sec, symbols, *, lookback_days=1100, cache=None):
    """Score Form 4 activity for a shortlist, before the final ranking rather than after.

    This used to run at the very end, purely as display, which meant the single
    best-supported unused signal in the dataset could not influence a single score. It now
    runs ahead of scoring so ``insider_modifier`` can act on it. Results are cached for a
    day - Form 4 filings are not intraday data - and the whole thing is skipped silently
    when ``SEC_USER_AGENT`` is unset, since SEC fair-access policy requires it.
    """
    if not sec.available or not symbols:
        return {}, []
    cache = cache or CACHE
    failures = []

    def collect_one(symbol):
        def produce():
            transactions, _ = sec.form4_transactions(symbol, lookback_days=lookback_days)
            return transactions
        try:
            transactions = cache.fetch("sec_submissions", f"form4:{symbol}:{lookback_days}",
                                       produce, source="sec_edgar")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: SEC Form 4 unavailable ({type(exc).__name__})")
            return symbol, None
        return symbol, summarize_insiders(transactions or [])

    # SEC fair access allows 10 requests/second, so a small pool is safely inside the limit
    # while still overlapping the latency of dozens of filing downloads.
    results = parallel_map(collect_one, list(symbols), provider="sec_edgar", max_workers=4)
    signals = {}
    for entry in results:
        if not entry:
            continue
        symbol, summary = entry
        if summary is None:
            failures.append(symbol)
        else:
            signals[symbol] = summary
    return signals, failures


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


def collect(symbol, client, yf, alpha_symbols, delay, marketaux_client=None):
    """The cheap first pass: quote snapshot, two years of prices, and any Alpha Vantage extras.

    Financial statements are deliberately left out here. They cost several requests per
    company, so they are fetched later for shortlisted names only.
    """
    ticker_obj = yf.Ticker(symbol) if yf else None
    fallback = yahoo_snapshot(symbol, yf, ticker_obj)
    history = yahoo_history(symbol, yf, ticker_obj=ticker_obj)
    overview = daily = news_payload = insiders = {}
    news = []
    marketaux_failed = False
    alpha_failed = False
    if symbol in alpha_symbols:
        overview = fetch_optional(client, "OVERVIEW", symbol=symbol)
        time.sleep(delay)
        daily = fetch_optional(client, "TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
        time.sleep(delay)
        if marketaux_client:
            try:
                marketaux_payload = marketaux_client.news(
                    symbols=symbol, filter_entities="true", language="en",
                    group_similar="true", limit=10,
                )
                news = advisor_articles(marketaux_payload, symbol)
            except (MarketauxError, OSError, ValueError) as exc:
                marketaux_failed = True
                LOG.warn(f"{symbol}: Marketaux news unavailable ({type(exc).__name__}: {exc})")
        if not marketaux_client or marketaux_failed:
            news_payload = fetch_optional(client, "NEWS_SENTIMENT", tickers=symbol, sort="LATEST", limit="12")
            news = compact_news(news_payload, symbol)
            time.sleep(delay)
        insiders = fetch_optional(client, "INSIDER_TRANSACTIONS", symbol=symbol)
        alpha_history = daily_history(daily)
        # Alpha Vantage only returns 100 sessions; Yahoo's two years wins whenever it exists.
        if alpha_history["closes"] and len(alpha_history["closes"]) > len(history["closes"]):
            history = alpha_history
        alpha_failed = not overview or not daily

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
        "marketaux_enriched": symbol in alpha_symbols and bool(marketaux_client) and not marketaux_failed,
        "marketaux_failed": marketaux_failed,
    }


def enrich(contexts, limit, delay, priority=()):
    """Pull financial statements for the shortlist and fold the derived metrics into each snapshot.

    Shortlisting is done on core fundamentals alone, which every candidate has in equal
    measure, so nothing is ranked down merely for being outside the statement budget.
    """
    ranked_by_score = sorted(contexts, key=lambda context: valuation_score(context["snapshot"])[0] or 0,
                             reverse=True)
    by_symbol = {context["symbol"]: context for context in contexts}
    ranked = [by_symbol[symbol] for symbol in priority if symbol in by_symbol]
    ranked.extend(context for context in ranked_by_score if context["symbol"] not in set(priority))
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


def build_theme_layer(sec, rows):
    """Score the structural-trend screen, or explain why it could not run.

    Kept out of the score by design: a forward-looking thematic bet blended into the
    fundamentals score would make that score impossible to interpret. This emits an
    independent ``theme_screen`` block the UI renders beside the other screens.
    """
    if os.getenv("THEMES_DISABLE", "").lower() in {"1", "true", "yes"}:
        return empty_screen("disabled via THEMES_DISABLE")
    themes = load_themes()
    if not themes:
        return empty_screen("no active theme definitions in pipeline/themes/")
    provider = EdgarThemeSignals(sec)
    if not provider.available:
        return empty_screen("SEC_USER_AGENT is required by SEC fair-access policy; "
                            "theme signals come from EDGAR filings")
    screen = build_theme_screen(themes, rows, provider)
    LOG.info(f"Theme screen: {len(screen['themes'])} theme(s), "
             f"{sum(theme['count'] for theme in screen['themes'])} scored exposures")
    return screen


def previous_ranked_symbols(limit=INCUMBENT_ENRICH_LIMIT):
    """Return the prior published leaders so their deep coverage persists across refreshes."""
    payload = load_json("advisor.json") or {}
    return tuple(
        row["ticker"].upper()
        for row in payload.get("research", [])[:limit]
        if row.get("ticker")
    )


def select_enrichment_priority(previous_top, preliminary_symbols, available, portfolio_symbols=()):
    """Choose prior leaders, five best outsiders, then any explicit portfolio coverage."""
    incumbents = tuple(
        symbol for symbol in previous_top
        if symbol in available
    )[:INCUMBENT_ENRICH_LIMIT]
    if not incumbents:
        incumbents = tuple(preliminary_symbols[:INCUMBENT_ENRICH_LIMIT])
    incumbent_set = set(incumbents)
    challengers = tuple(
        symbol for symbol in preliminary_symbols
        if symbol not in incumbent_set
    )[:CHALLENGER_ENRICH_LIMIT]
    priority = tuple(dict.fromkeys((*incumbents, *challengers, *portfolio_symbols)))
    return incumbents, challengers, priority


def build_portfolio_coverage(research, portfolio_symbols, previous=()):
    """Keep configured holdings visible even when a quote provider drops a symbol."""
    research_by_ticker = {row["ticker"]: row for row in research}
    previous_by_ticker = {
        row.get("ticker", "").upper(): row
        for row in previous
        if row.get("ticker")
    }
    coverage = []
    for symbol in portfolio_symbols:
        if symbol in research_by_ticker:
            coverage.append(research_by_ticker[symbol])
        elif symbol in previous_by_ticker:
            coverage.append({
                **previous_by_ticker[symbol],
                "coverage_status": "stale_provider_unavailable",
            })
        else:
            coverage.append({
                "ticker": symbol,
                "name": symbol,
                "price": None,
                "coverage_status": "provider_unavailable",
            })
    return coverage


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
    previous_payload = load_json("advisor.json") or {}
    previous_coverage = previous_payload.get("portfolio_coverage", [])
    previous_portfolio = tuple(
        row.get("ticker", "")
        for row in previous_coverage
        if row.get("ticker")
    )
    configured = os.getenv("ADVISOR_SYMBOLS")
    requested_symbols = configured.split(",") if configured else DEFAULT_SYMBOLS
    symbols, portfolio_symbols = resolve_refresh_symbols(
        requested_symbols,
        PORTFOLIO_SYMBOLS,
        os.getenv("ADVISOR_PORTFOLIO_SYMBOLS", ""),
        previous_portfolio,
    )
    publish_limit = max(1, int(os.getenv("ADVISOR_PUBLISH_LIMIT", PUBLISH_LIMIT)))
    extended_limit = max(publish_limit, int(os.getenv("ADVISOR_EXTENDED_LIMIT", EXTENDED_LIMIT)))
    alpha_enabled = os.getenv("ALPHA_DISABLE", "").lower() not in {"1", "true", "yes"}
    alpha_limit = max(0, min(5, int(os.getenv("ALPHA_ENRICH_LIMIT", "5")))) if alpha_enabled else 0
    previous_top = previous_ranked_symbols()
    requested_enrichment = tuple(s.strip().upper() for s in os.getenv("ALPHA_ENRICH_SYMBOLS", "").split(",") if s.strip())
    enrichment_order = requested_enrichment or previous_top or symbols
    eligible_enrichment = tuple(symbol for symbol in enrichment_order if symbol in symbols)
    alpha_symbols = set(eligible_enrichment[:alpha_limit])
    client = AlphaVantageClient() if alpha_enabled else None
    try:
        marketaux_client = MarketauxClient()
    except MarketauxError:
        marketaux_client = None
    delay = float(os.getenv("ALPHA_VANTAGE_CALL_DELAY", "0"))
    try:
        import yfinance as yf
    except ImportError:
        yf = None

    benchmark_payload = (
        fetch_optional(client, "TIME_SERIES_DAILY", symbol="SPY", outputsize="compact")
        if client else {}
    )
    # One batched download for the whole universe before the per-symbol loop starts, so the
    # loop mostly reads cache instead of making a few hundred separate HTTP calls.
    prefetch_histories(("SPY", *symbols), yf)
    prefetch_snapshots(symbols, yf)
    benchmark = daily_history(benchmark_payload)
    yahoo_benchmark = yahoo_history("SPY", yf)
    if len(yahoo_benchmark["closes"]) > len(benchmark["closes"]):
        benchmark = yahoo_benchmark

    contexts, all_news = [], []
    alpha_failures, marketaux_failures, research_failures = [], [], []
    for symbol in symbols:
        try:
            context = collect(symbol, client, yf, alpha_symbols, delay, marketaux_client)
            contexts.append(context)
            all_news.extend(context["news"])
            if context["alpha_failed"]:
                alpha_failures.append(symbol)
            if context["marketaux_failed"]:
                marketaux_failures.append(symbol)
            LOG.info(f"Advisor research collected for {symbol}")
        except Exception as exc:  # keep other symbols useful
            research_failures.append(symbol)
            LOG.error(f"{symbol}: advisor fetch failed ({type(exc).__name__}: {exc})")
        time.sleep(delay)

    if not contexts:
        update_pipeline_status("advisor", status="error", source="Alpha Vantage + Yahoo Finance",
                               message="No research records were produced")
        return None

    fred_regime = None
    fred_failure = None
    try:
        fred_regime = fetch_regime(FredClient())
        if fred_regime.get("failed_series"):
            fred_failure = f"Unavailable series: {', '.join(fred_regime['failed_series'])}"
    except FredError as exc:
        fred_failure = str(exc)
        LOG.warn(f"FRED macro regime unavailable ({exc})")

    # Establish the five closest challengers from the inexpensive first-pass score.
    # Then statements are pulled for those names and the prior top 20 before final scoring.
    preliminary_peer_diagnostics = canonical_percentiles([
        {**context["snapshot"], "ticker": context["symbol"],
         "categories": valuation_score(context["snapshot"])[1].get("categories", {})}
        for context in contexts
    ])
    preliminary = []
    for context in contexts:
        row = build_research(
            context["symbol"], context["snapshot"], context["history"]["closes"], benchmark["closes"],
            context["news"], volumes=context["history"]["volumes"], extended={},
            sector_percentile=(preliminary_peer_diagnostics.get(context["symbol"]) or {}).get("value"),
            macro_regime=fred_regime,
        )
        preliminary.append(row)
    preliminary.sort(key=lambda row: row["score"], reverse=True)

    available = {context["symbol"] for context in contexts}
    preliminary_symbols = tuple(row["ticker"] for row in preliminary)
    discovery_limit = max(0, min(
        NEWS_DISCOVERY_LIMIT,
        int(os.getenv("ADVISOR_NEWS_DISCOVERY_LIMIT", str(NEWS_DISCOVERY_LIMIT))),
    ))
    try:
        discovery_news = fetch_discovery_news(
            marketaux_client, preliminary_symbols, discovery_limit
        )
    except (MarketauxError, OSError, ValueError) as exc:
        discovery_news = []
        LOG.warn(f"Broader candidate news unavailable ({type(exc).__name__}: {exc})")
    discovery_by_ticker = {}
    for item in discovery_news:
        discovery_by_ticker.setdefault(item["ticker"], []).append(item)
    for context in contexts:
        additions = discovery_by_ticker.get(context["symbol"], [])
        if additions:
            context["news"] = latest_unique_news([*context["news"], *additions], limit=12)
    all_news.extend(discovery_news)

    incumbents, challengers, statement_priority = select_enrichment_priority(
        previous_top, preliminary_symbols, available, portfolio_symbols
    )
    enriched_count = enrich(contexts, extended_limit, delay, statement_priority)

    # Valuation is scored once up front so 'cheap for its sector' can be measured against peers
    # before the final score is assembled.
    peer_diagnostics = canonical_percentiles([
        {**context["snapshot"], "ticker": context["symbol"],
         "categories": valuation_score(context["snapshot"])[1].get("categories", {})}
        for context in contexts
    ])

    # SEC Form 4 is the free source-of-record for genuine open-market insider trades. It is
    # collected here, ahead of scoring, so opportunistic cluster buying can actually move a
    # score - previously it was fetched after ranking and could only ever be displayed.
    sec = SecEdgarClient()
    sec_limit = max(0, int(os.getenv("SEC_FORM4_LIMIT", str(publish_limit))))
    insider_candidates = tuple(dict.fromkeys(
        (*preliminary_symbols[:sec_limit], *portfolio_symbols)
    )) if sec.available else ()
    insider_signals, sec_failures = collect_insider_signals(sec, insider_candidates)

    research = []
    for context in contexts:
        symbol = context["symbol"]
        row = build_research(
            symbol, context["snapshot"], context["history"]["closes"], benchmark["closes"],
            context["news"], volumes=context["history"]["volumes"], extended=context["extended"],
            sector_percentile=(peer_diagnostics.get(context["symbol"]) or {}).get("value"),
            macro_regime=fred_regime,
            insider_activity=insider_signals.get(symbol),
        )
        # The Form 4 record when we have one; the Alpha Vantage count as a display-only
        # fallback when we do not.
        row["insider_activity"] = insider_signals.get(symbol) or context["insider_activity"]
        row["alpha_enriched"] = context["alpha_enriched"]
        row["valuation_percentile"] = peer_diagnostics.get(context["symbol"])
        research.append(row)

    research.sort(key=lambda row: row["score"], reverse=True)
    ranked = research[:publish_limit]
    ranked_tickers = {row["ticker"] for row in ranked}
    # The momentum and 52-week-low screens rank on price behavior, not the fundamentals-led
    # composite score, so a strong screen candidate can rank outside the published leaderboard.
    # technical_detail and fundamental_categories are populated for the whole scored universe
    # (see technical_factors' closes-based 52-week fallback above), so publish a lightweight,
    # history-free slice of the rest of the universe for those screens to scan.
    screen_universe = [
        {
            "ticker": row["ticker"], "name": row["name"], "sector": row.get("sector"),
            "price": row.get("price"), "score": row["score"], "stance": row["stance"],
            "components": row["components"], "fundamental_categories": row["fundamental_categories"],
            "technical_detail": {key: row["technical_detail"].get(key)
                                 for key in SCREEN_TECHNICAL_FIELDS
                                 if row["technical_detail"].get(key) is not None},
        }
        for row in research[publish_limit:]
    ]
    # Publish every configured holding explicitly. A provider can temporarily stop resolving
    # a symbol (for example, an expired structured product); omitting that row made the UI look
    # as if the user's holding itself had disappeared. A stale prior row is preferable, and a
    # price-less placeholder still lets the portfolio use its brokerage snapshot.
    portfolio_coverage = build_portfolio_coverage(
        research, portfolio_symbols, previous_coverage
    )
    research_context = {
        row["ticker"]: {
            "research_score": row["score"],
            "research_stance": row["stance"],
            "research_rank": index + 1,
            "published_research": index < publish_limit,
        }
        for index, row in enumerate(research)
    }
    published_news = curate_candidate_news(all_news, research_context)

    # Append this run's observations to the point-in-time store. It only becomes valuable
    # with time depth, so it starts accumulating now, well before any backtest needs it -
    # there is no way to reconstruct it retroactively from a provider that only serves today.
    # The trend-exposure layer runs as its own screen, deliberately outside the score. It
    # is scored on the published leaders plus every configured holding, because the SEC
    # requests are per-company and the whole universe would be wasteful for a screen most
    # names will not clear anyway.
    theme_candidates = [*ranked, *(
        row for row in research
        if row["ticker"] in set(portfolio_symbols) and row["ticker"] not in ranked_tickers)]
    theme_screen = build_theme_layer(sec, theme_candidates)

    # Rows carry the raw metric values merged from their snapshot, which is what a later
    # backtest needs - the derived 0-100 scores can always be recomputed from them.
    pit_summary = pit_store.append_snapshot(research, source="advisor_refresh")
    pit_store.record_universe(symbols, source="advisor_refresh")
    pit_depth = pit_store.depth()

    grid = chart_grid(benchmark["dates"])
    benchmark_series = series_payload(benchmark["dates"], benchmark["closes"], grid)
    benchmark_growth = (benchmark_series or {}).get("growth")
    contexts_by_symbol = {context["symbol"]: context for context in contexts}
    for row in ranked:
        attach_history(row, contexts_by_symbol[row["ticker"]], grid, benchmark_growth)
    for row in portfolio_coverage:
        context = contexts_by_symbol.get(row["ticker"])
        if row["ticker"] not in ranked_tickers and context:
            attach_history(row, context, grid, benchmark_growth)

    market_status = fetch_optional(client, "MARKET_STATUS") if client else {}
    macro = macro_context(client) if client else {}
    generated_at = datetime.now(timezone.utc).isoformat()
    fundamentals_cfg = SETTINGS["fundamentals"]
    for row in research:
        row.setdefault("data_fetched_at", generated_at)
    payload = {
        # Bumped to 2: market-behavior detail keys changed (12-1 momentum and real
        # risk-adjusted ratios replaced the invented trend/risk fields), and theme exposure
        # plus data-freshness blocks were added. All additive except the technical rename,
        # which the frontend migration in src/lib/schemaMigrations.js maps for v1 readers.
        "schema_version": 2, "generated_at": generated_at, "data_mode": "live",
        "count": len(ranked), "universe_count": len(symbols), "universe": list(symbols),
        "publish_limit": publish_limit, "statement_enriched_count": enriched_count, "benchmark": "SPY",
        "enrichment_selection": {
            "previous_top": list(incumbents),
            "challengers": list(challengers),
            "priority_count": len(incumbents) + len(challengers),
        },
        "methodology": {
            "weights": RANKING_WEIGHTS,
            "fundamental_weights": fundamentals_cfg["category_weights"],
            "metric_weights": fundamentals_cfg["metric_weights"],
            "market_behavior_weights": SETTINGS.get("market_behavior", {}).get("weights", {}),
            "modifiers": SETTINGS.get("modifiers", {}),
            "principle": "Fundamentals lead. Price behavior and news modify confidence; they do not replace business quality.",
            "evidence": {
                "valuation": "EV/EBITDA and EV/EBIT carry the valuation bucket (Loughran & Wellman's "
                             "enterprise-multiple factor; Gray & Vogel's multiples comparison). PEG is a "
                             "minor sanity check because it ignores the time value of money, risk, and "
                             "cost of capital.",
                "profitability": "Gross profits-to-assets added per Novy-Marx (JFE 2013), which finds it "
                                 "roughly as predictive as book-to-market and complementary to it.",
                "accounting_quality": "Accruals down-weighted and Piotroski raised: the accruals anomaly "
                                      "has decayed in US data since 2002 while the F-score still validates.",
                "market_behavior": "12-1 momentum (Jegadeesh & Titman 1993) plus Sharpe/Sortino and a "
                                   "low-beta reward (Frazzini & Pedersen 2014), using the same functions "
                                   "as the ETF model.",
                "news_sentiment": "Weighted as a 4% tilt over a 7-day window; daily headline sentiment "
                                  "largely mean-reverts (Tetlock 2007).",
                "insider_activity": "Form 4 trades split routine vs opportunistic per Cohen, Malloy & "
                                    "Pomorski (JF 2012); only opportunistic cluster activity scores.",
                "caveat": "Published factor premia are historical in-sample estimates. They indicate which "
                          "signals have mattered, not what any of them will return next.",
            },
        },
        "market": {"status": market_status.get("markets", []), "macro": {**macro, "regime": fred_regime}},
        "benchmark_history": {"symbol": "SPY", "dates": grid, **(benchmark_series or {})},
        "hypothetical_basis": BASIS,
        "research": ranked,
        "screen_universe": screen_universe,
        "theme_screen": theme_screen,
        "portfolio_coverage": portfolio_coverage,
        "news": published_news,
        "data_freshness": pit_store.freshness_report(research),
        "point_in_time_store": {
            **pit_depth, "appended": pit_summary,
            "note": "Timestamped observations accumulate from each run so future backtests "
                    "can score on what was actually known at the time. Yahoo serves restated "
                    "fundamentals only, so this history cannot be rebuilt retroactively.",
        },
        "cache": CACHE.stats(),
        "capability_status": {
            "form4_insider_transactions": {
                "status": "available" if sec.available else "configuration_required",
                "source": "SEC EDGAR",
                "scored_symbols": len(insider_signals),
                "note": "Open-market purchase/sale codes only, split routine vs opportunistic "
                        "and scored as a bounded decaying modifier; set SEC_USER_AGENT.",
            },
            "implied_vs_realized_volatility": {
                "status": "available" if os.getenv("ENABLE_OPTIONS_VOLATILITY", "").lower() in {"1", "true", "yes"} else "opt_in",
                "source": "Yahoo option chains + calculated price returns",
                "note": "Set ENABLE_OPTIONS_VOLATILITY=1; options requests are intentionally opt-in.",
            },
            "earnings_surprise_momentum": {
                "status": "available" if EARNINGS_SURPRISE_ENABLED else "opt_in",
                "source": "Yahoo earnings calendar (scraped, one request per symbol)",
                **EARNINGS_SURPRISE_STATS,
                "note": "Set ENABLE_EARNINGS_SURPRISE=1. Off by default: the first production "
                        "run resolved it for 0 of 40 published companies, so it spent a "
                        "request per symbol for nothing. Its growth-bucket weight stays in "
                        "config and reweights away while unavailable.",
            },
            "analyst_revision_trends": {"status": "provider_required", "note": "Point-in-time estimate history is not supplied by current providers."},
            "guidance_beat_miss_history": {"status": "provider_required", "note": "Needs normalized company guidance and contemporaneous consensus snapshots."},
            "backlog_growth": {"status": "filing_parser_required", "note": "Backlog is non-GAAP and must be extracted company-by-company from filings."},
            "institutional_13f_changes": {"status": "mapping_required", "source": "SEC EDGAR", "note": "Filings are free; reliable CUSIP-to-ticker mapping is not."},
            "fx_exposure": {"status": "filing_parser_required", "source": "SEC 10-K/10-Q", "note": "Needs filing-text extraction and issuer-specific normalization."},
        },
        "source_status": {
            "alpha_vantage": {"status": "disabled_for_intraday_refresh" if not client else
                              ("healthy" if not alpha_failures else "degraded"), "failed_symbols": alpha_failures,
                              "enriched_symbols": sorted(alpha_symbols), "quota_strategy": "up to five symbols per refresh"},
            "marketaux": {
                "status": "unavailable" if not marketaux_client else ("degraded" if marketaux_failures else "healthy"),
                "failed_symbols": marketaux_failures,
                "enriched_symbols": sorted(alpha_symbols) if marketaux_client else [],
                "note": "Set MARKETAUX_API_TOKEN to enable entity-level company news sentiment"
                        if not marketaux_client else "Entity-level sentiment for the Alpha-enriched shortlist",
            },
            "fred": {
                "status": "unavailable" if not fred_regime else ("degraded" if fred_failure else "healthy"),
                "failed_series": fred_regime.get("failed_series", []) if fred_regime else [],
                "note": fred_failure or "Six high-value series condensed into a bounded sector-sensitive regime modifier",
            },
            "yahoo_fundamentals": {"status": "degraded" if research_failures else ("healthy" if yf else "unavailable"),
                                   "failed_symbols": research_failures},
            "sec_form4": {
                "status": "unavailable" if not sec.available else ("degraded" if sec_failures else "healthy"),
                "failed_symbols": sec_failures,
                "scored_symbols": len(insider_signals),
                "note": "Set SEC_USER_AGENT to enable free source-of-record insider transactions" if not sec.available else
                        "Open-market Form 4 codes P/S only; routine calendar trades score zero, "
                        "opportunistic cluster activity is a bounded decaying modifier",
            },
        },
        "disclaimer": "General research, not individualized investment advice. Verify filings, estimates, valuation context, and suitability before acting.",
    }
    payload["run_manifest"] = run_manifest(payload, {
        "provider_collection": len(research_failures),
        "statement_enrichment": max(0, len(contexts) - enriched_count),
        "publication_limit": max(0, len(research) - len(ranked)),
    })
    save_json("advisor.json", payload)
    save_json("diagnostics.json", diagnostics_payload(payload))
    all_failures = sorted(set(alpha_failures + marketaux_failures + research_failures))
    update_pipeline_status("advisor", status="healthy" if not all_failures else "degraded",
                           source="Alpha Vantage + Yahoo Finance + Marketaux",
                           details={"universe": len(symbols), "scored": len(research), "ranked": len(ranked), "failed": all_failures})
    LOG.info(f"Wrote advisor.json with the top {len(ranked)} of {len(research)} scored companies")
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
