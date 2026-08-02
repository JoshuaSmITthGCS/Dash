"""Provider abstraction: one internal contract, one adapter per data source.

The problem this fixes is structural. Provider field names were reaching directly into
scoring code - ``info.get("trailingEps")``, ``overview.get("PEGRatio")``,
``recent.get("filingDate")`` - which meant adding Tiingo or EODHD, or reacting to yfinance
breaking again, would ripple through the model rather than stopping at the boundary.

The shape here is ports and adapters:

  * ``AbstractDataProvider`` is the **port** - the stable internal contract scoring code
    depends on. It is expressed in normalized dataclasses (``PriceSeries``, ``Fundamentals``,
    ``Quote``), never in a vendor's JSON keys.
  * ``YahooAdapter``, ``AlphaVantageAdapter``, ``EdgarAdapter`` are **adapters** - each maps
    one vendor's raw payload into the normalized schema and nothing else.
  * ``FakeProvider`` is the adapter tests use, so the model can be exercised end to end
    with no network at all.
  * ``build_provider`` is the factory; ``CompositeProvider`` chains adapters so a primary
    source can fail over to a secondary without any caller knowing.

Free-tier limits move constantly (Alpha Vantage's daily cap has gone 500 to 100 to 25;
Polygon rebranded; FMP moved segments and transcripts behind paid tiers), which is exactly
why the per-provider quota lives in config next to the adapter rather than in the code that
uses the data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from cache import CACHE, limiter_for, retry_with_backoff
from common import LOG

SCHEMA_VERSION = 1


# ---------------- normalized internal schema ----------------

@dataclass
class PriceSeries:
    """Adjusted daily closes and volumes for one symbol, oldest first."""
    symbol: str
    dates: list = field(default_factory=list)
    closes: list = field(default_factory=list)
    volumes: list = field(default_factory=list)
    source: str = None
    fetched_at: str = None

    def __len__(self):
        return len(self.closes)

    @property
    def last(self):
        return self.closes[-1] if self.closes else None

    def as_dict(self):
        return {"dates": self.dates, "closes": self.closes, "volumes": self.volumes}


@dataclass
class Quote:
    """Point-in-time market and descriptive fields, normalized across vendors."""
    symbol: str
    name: str = None
    sector: str = None
    industry: str = None
    price: float = None
    market_cap: float = None
    is_etf: bool = False
    currency: str = None
    exchange: str = None
    source: str = None
    fetched_at: str = None
    extras: dict = field(default_factory=dict)

    def as_dict(self):
        base = {key: value for key, value in asdict(self).items() if key != "extras"}
        return {**base, **self.extras}


@dataclass
class Fundamentals:
    """Statement-derived metrics keyed by the model's own names, never a vendor's.

    ``as_of`` carries the observation date so the point-in-time store can record when this
    view of the numbers was true, which is the only defence against restatement bias.
    """
    symbol: str
    as_of: str = None
    metrics: dict = field(default_factory=dict)
    statements: dict = field(default_factory=dict)
    source: str = None
    fetched_at: str = None

    def get(self, name, default=None):
        return self.metrics.get(name, default)

    def as_dict(self):
        return {"symbol": self.symbol, "as_of": self.as_of, "source": self.source,
                "fetched_at": self.fetched_at, **self.metrics}


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------- the port ----------------

class AbstractDataProvider(ABC):
    """The stable internal contract. Scoring code depends on this and nothing below it."""

    name = "abstract"
    #: Which capabilities this adapter actually implements, so callers can route rather
    #: than call and catch.
    capabilities = frozenset()

    @abstractmethod
    def prices(self, symbol, start=None, end=None) -> PriceSeries:
        """Daily price history for one symbol."""

    @abstractmethod
    def quote(self, symbol) -> Quote:
        """Current market and descriptive fields for one symbol."""

    def fundamentals(self, symbol, as_of=None) -> Fundamentals:
        """Statement-derived metrics. Point-in-time aware where the source allows it."""
        return Fundamentals(symbol=symbol, as_of=as_of, source=self.name, fetched_at=_now())

    def batch_prices(self, symbols, start=None, end=None):
        """Price history for many symbols. Adapters that can batch should override this."""
        return {symbol: self.prices(symbol, start, end) for symbol in symbols}

    def supports(self, capability):
        return capability in self.capabilities


# ---------------- adapters ----------------

class YahooAdapter(AbstractDataProvider):
    """yfinance. Unofficial, rate-limits unpredictably, and breaks without notice.

    Everything therefore goes through the on-disk cache and exponential backoff, and
    ``batch_prices`` uses ``yf.download`` so forty symbols cost a handful of HTTP calls
    rather than forty. This adapter is never trusted as a sole production path.
    """

    name = "yahoo"
    capabilities = frozenset({"prices", "quote", "fundamentals", "batch_prices"})

    def __init__(self, yf=None, cache=None, period="2y"):
        self._yf = yf
        self.cache = cache or CACHE
        self.period = period

    @property
    def yf(self):
        if self._yf is None:
            import yfinance  # imported lazily so the module stays importable without it
            self._yf = yfinance
        return self._yf

    def prices(self, symbol, start=None, end=None):
        period = self.period

        def produce():
            def download():
                frame = self.yf.Ticker(symbol).history(
                    period=period, auto_adjust=False).dropna(subset=["Close"])
                if frame.empty:
                    raise ValueError("empty price frame")
                return {
                    "dates": [str(index)[:10] for index in frame.index],
                    "closes": [float(value) for value in frame["Close"].tolist()],
                    "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
                }
            limiter_for(self.name).acquire()
            return retry_with_backoff(download, description=f"{symbol} prices")

        try:
            payload = self.cache.fetch("price_history", f"{symbol}:{period}", produce,
                                       source=self.name)
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: Yahoo prices unavailable ({type(exc).__name__})")
            return PriceSeries(symbol=symbol, source=self.name, fetched_at=_now())
        return PriceSeries(symbol=symbol, source=self.name, fetched_at=_now(), **payload)

    def batch_prices(self, symbols, start=None, end=None):
        """One ``yf.download`` for the whole list instead of one request per symbol.

        This is the single biggest speed win available: yfinance collapses a batch into far
        fewer HTTP calls, and fewer calls is also the most reliable way to stay under an
        undocumented rate limit.
        """
        symbols = list(symbols)
        if not symbols:
            return {}
        cached, missing = {}, []
        for symbol in symbols:
            payload = self.cache.get("price_history", f"{symbol}:{self.period}")
            if payload:
                cached[symbol] = PriceSeries(symbol=symbol, source=self.name,
                                             fetched_at=_now(), **payload)
            else:
                missing.append(symbol)
        if not missing:
            return cached

        try:
            limiter_for(self.name).acquire()
            frame = retry_with_backoff(
                lambda: self.yf.download(missing, period=self.period, auto_adjust=False,
                                         group_by="ticker", progress=False, threads=True),
                description=f"batch prices for {len(missing)} symbols")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"batch price download failed ({type(exc).__name__}); "
                     "falling back to per-symbol requests")
            for symbol in missing:
                cached[symbol] = self.prices(symbol, start, end)
            return cached

        for symbol in missing:
            payload = self.extract_symbol_frame(frame, symbol, single=len(missing) == 1)
            if payload:
                self.cache.set("price_history", f"{symbol}:{self.period}", payload,
                               source=self.name)
                cached[symbol] = PriceSeries(symbol=symbol, source=self.name,
                                             fetched_at=_now(), **payload)
            else:
                cached[symbol] = PriceSeries(symbol=symbol, source=self.name, fetched_at=_now())
        return cached

    @staticmethod
    def extract_symbol_frame(frame, symbol, single=False):
        """Pull one symbol's columns out of a multi-index ``yf.download`` frame.

        Public because the orchestrator warms the cache with its own batched download and
        needs the same unpacking; a one-symbol batch comes back without the ticker level.
        """
        try:
            section = frame if single else frame[symbol]
            section = section.dropna(subset=["Close"])
            if section.empty:
                return None
            return {
                "dates": [str(index)[:10] for index in section.index],
                "closes": [float(value) for value in section["Close"].tolist()],
                "volumes": [float(value) for value in section["Volume"].fillna(0).tolist()],
            }
        except Exception:  # noqa: BLE001 - one absent symbol must not sink the batch
            return None

    def quote(self, symbol):
        def produce():
            limiter_for(self.name).acquire()
            return self.yf.Ticker(symbol).info or {}

        try:
            info = self.cache.fetch("quote", symbol, produce, source=self.name) or {}
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: Yahoo quote unavailable ({type(exc).__name__})")
            return Quote(symbol=symbol, source=self.name, fetched_at=_now())
        return self.map_quote(symbol, info)

    @staticmethod
    def map_quote(symbol, info):
        """Vendor keys to internal names. The only place Yahoo's spelling is allowed."""
        info = info or {}
        return Quote(
            symbol=symbol,
            name=info.get("longName") or info.get("shortName") or symbol,
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice"),
            market_cap=info.get("marketCap"),
            is_etf=str(info.get("quoteType", "")).upper() == "ETF",
            currency=info.get("currency"),
            exchange=info.get("exchange"),
            source="yahoo",
            fetched_at=_now(),
            extras={
                "forward_pe": info.get("forwardPE"), "trailing_pe": info.get("trailingPE"),
                "price_to_book": info.get("priceToBook"), "peg": info.get("pegRatio"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "dividend_yield": info.get("dividendYield"), "beta": info.get("beta"),
                "short_percent_of_float": info.get("shortPercentOfFloat"),
                "nav": info.get("navPrice"), "bid": info.get("bid"), "ask": info.get("ask"),
                "aum": info.get("totalAssets"),
            },
        )


class AlphaVantageAdapter(AbstractDataProvider):
    """Alpha Vantage. Free tier is 25 requests/day and 5/minute, and has been cut repeatedly.

    Given that quota this adapter is used for enrichment of a handful of symbols, never for
    the universe sweep - which is a routing decision the caller makes by checking
    ``capabilities``, not something buried in the fetch loop.
    """

    name = "alpha_vantage"
    capabilities = frozenset({"prices", "quote", "fundamentals", "news"})

    def __init__(self, client=None, cache=None):
        self.client = client
        self.cache = cache or CACHE

    def _query(self, function, **params):
        if not self.client:
            return {}
        limiter_for(self.name).acquire()
        key = f"{function}:{sorted(params.items())}"
        try:
            return self.cache.fetch("quote", key, lambda: self.client.query(function, **params),
                                    source=self.name) or {}
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{function} unavailable ({type(exc).__name__})")
            return {}

    def prices(self, symbol, start=None, end=None):
        payload = self._query("TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
        series = payload.get("Time Series (Daily)", {})
        rows = sorted(series.items())
        return PriceSeries(
            symbol=symbol, source=self.name, fetched_at=_now(),
            dates=[day for day, values in rows if values.get("4. close")],
            closes=[float(values["4. close"]) for _, values in rows if values.get("4. close")],
            volumes=[float(values.get("5. volume") or 0) for _, values in rows
                     if values.get("4. close")],
        )

    def quote(self, symbol):
        return self.map_quote(symbol, self._query("OVERVIEW", symbol=symbol))

    @staticmethod
    def map_quote(symbol, overview):
        """OVERVIEW's SCREAMING_CASE keys to internal names."""
        overview = overview or {}

        def number(key, digits=4):
            try:
                return round(float(overview.get(key)), digits)
            except (TypeError, ValueError):
                return None

        return Quote(
            symbol=symbol, name=overview.get("Name") or symbol,
            sector=overview.get("Sector"), industry=overview.get("Industry"),
            market_cap=number("MarketCapitalization", 0),
            currency=overview.get("Currency"), exchange=overview.get("Exchange"),
            source="alpha_vantage", fetched_at=_now(),
            extras={
                "description": overview.get("Description") or "",
                "forward_pe": number("ForwardPE"), "trailing_pe": number("PERatio"),
                "peg": number("PEGRatio"), "price_to_sales": number("PriceToSalesRatioTTM"),
                "price_to_book": number("PriceToBookRatio"),
                "return_on_equity": number("ReturnOnEquityTTM"),
                "profit_margin": number("ProfitMargin"),
                "revenue_growth": number("QuarterlyRevenueGrowthYOY"),
                "earnings_growth": number("QuarterlyEarningsGrowthYOY"),
                "dividend_yield": number("DividendYield"),
            },
        )


class EdgarAdapter(AbstractDataProvider):
    """SEC EDGAR. Free, unlimited, no key, and the source of record.

    No prices or quotes - EDGAR does not publish market data - so ``capabilities`` says so
    and callers route around it rather than discovering it through an exception.
    """

    name = "sec_edgar"
    capabilities = frozenset({"fundamentals", "filings", "insider", "segments"})

    def __init__(self, client=None, cache=None):
        self.client = client
        self.cache = cache or CACHE

    @property
    def available(self):
        return bool(self.client and self.client.available)

    def prices(self, symbol, start=None, end=None):
        return PriceSeries(symbol=symbol, source=self.name, fetched_at=_now())

    def quote(self, symbol):
        return Quote(symbol=symbol, source=self.name, fetched_at=_now())

    def fundamentals(self, symbol, as_of=None):
        """XBRL company facts, filtered to values reported on or before ``as_of``.

        Unlike a quote-based provider, EDGAR can answer point-in-time honestly: every fact
        carries the date it was filed, so a genuine as-of view is reconstructable.
        """
        if not self.available:
            return Fundamentals(symbol=symbol, as_of=as_of, source=self.name, fetched_at=_now())
        try:
            payload = self.cache.fetch("sec_xbrl", f"facts:{symbol}",
                                       lambda: self.client.company_facts(symbol),
                                       source=self.name)
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: EDGAR company facts unavailable ({type(exc).__name__})")
            return Fundamentals(symbol=symbol, as_of=as_of, source=self.name, fetched_at=_now())
        return Fundamentals(symbol=symbol, as_of=as_of, source=self.name, fetched_at=_now(),
                            metrics=self.map_facts(payload, as_of=as_of))

    @staticmethod
    def map_facts(payload, as_of=None, concepts=None):
        """Latest value per XBRL concept as of a date. Vendor taxonomy stops here."""
        concepts = concepts or {
            "Assets": "total_assets", "Revenues": "revenue",
            "GrossProfit": "gross_profit", "OperatingIncomeLoss": "operating_income",
            "NetIncomeLoss": "net_income", "StockholdersEquity": "equity",
            "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
        }
        facts = ((payload or {}).get("facts") or {}).get("us-gaap") or {}
        metrics = {}
        for concept, internal in concepts.items():
            units = (facts.get(concept) or {}).get("units") or {}
            rows = units.get("USD") or []
            usable = [row for row in rows if row.get("val") is not None and row.get("filed")
                      and (as_of is None or row["filed"] <= as_of)]
            if usable:
                usable.sort(key=lambda row: (row.get("end", ""), row.get("filed", "")))
                metrics[internal] = float(usable[-1]["val"])
                metrics[f"{internal}_filed"] = usable[-1]["filed"]
        return metrics


class FakeProvider(AbstractDataProvider):
    """Deterministic in-memory provider for tests. No network, no clock, no surprises."""

    name = "fake"
    capabilities = frozenset({"prices", "quote", "fundamentals", "batch_prices"})

    def __init__(self, prices=None, quotes=None, fundamentals=None):
        self._prices = prices or {}
        self._quotes = quotes or {}
        self._fundamentals = fundamentals or {}
        self.calls = []

    def prices(self, symbol, start=None, end=None):
        self.calls.append(("prices", symbol))
        payload = self._prices.get(symbol)
        if payload is None:
            return PriceSeries(symbol=symbol, source=self.name)
        if isinstance(payload, PriceSeries):
            return payload
        return PriceSeries(symbol=symbol, source=self.name, **payload)

    def quote(self, symbol):
        self.calls.append(("quote", symbol))
        payload = self._quotes.get(symbol)
        if isinstance(payload, Quote):
            return payload
        return Quote(symbol=symbol, source=self.name, **(payload or {}))

    def fundamentals(self, symbol, as_of=None):
        self.calls.append(("fundamentals", symbol))
        return Fundamentals(symbol=symbol, as_of=as_of, source=self.name,
                            metrics=dict(self._fundamentals.get(symbol) or {}))


class CompositeProvider(AbstractDataProvider):
    """Try adapters in order, taking the first usable answer.

    Failover is a routing concern, not a scoring concern, so it lives here. Adding a
    fallback vendor becomes a change to one list rather than a conditional in every caller.
    """

    name = "composite"

    def __init__(self, providers):
        self.providers = list(providers)
        self.capabilities = frozenset().union(*(p.capabilities for p in self.providers)) \
            if self.providers else frozenset()

    def _first(self, capability, call, usable):
        for provider in self.providers:
            if not provider.supports(capability):
                continue
            result = call(provider)
            if usable(result):
                return result
        return None

    def prices(self, symbol, start=None, end=None):
        result = self._first("prices", lambda p: p.prices(symbol, start, end),
                             lambda r: r and len(r) > 0)
        return result or PriceSeries(symbol=symbol, source=self.name)

    def quote(self, symbol):
        result = self._first("quote", lambda p: p.quote(symbol),
                             lambda r: r and (r.price is not None or r.name))
        return result or Quote(symbol=symbol, source=self.name)

    def fundamentals(self, symbol, as_of=None):
        result = self._first("fundamentals", lambda p: p.fundamentals(symbol, as_of),
                             lambda r: r and r.metrics)
        return result or Fundamentals(symbol=symbol, as_of=as_of, source=self.name)

    def batch_prices(self, symbols, start=None, end=None):
        remaining, collected = list(symbols), {}
        for provider in self.providers:
            if not remaining or not provider.supports("prices"):
                continue
            batch = provider.batch_prices(remaining, start, end)
            for symbol, series in batch.items():
                if series and len(series) > 0:
                    collected[symbol] = series
            remaining = [symbol for symbol in remaining if symbol not in collected]
        for symbol in remaining:
            collected[symbol] = PriceSeries(symbol=symbol, source=self.name)
        return collected


# ---------------- factory ----------------

REGISTRY = {
    "yahoo": YahooAdapter,
    "alpha_vantage": AlphaVantageAdapter,
    "sec_edgar": EdgarAdapter,
    "fake": FakeProvider,
}


def build_provider(name, **kwargs):
    """Construct one adapter by name. Unknown names fail loudly rather than silently."""
    adapter = REGISTRY.get(name)
    if adapter is None:
        raise ValueError(f"unknown provider '{name}'; known: {sorted(REGISTRY)}")
    return adapter(**kwargs)


def build_composite(names, **kwargs_by_name):
    """Build a failover chain from an ordered list of adapter names."""
    return CompositeProvider([build_provider(name, **(kwargs_by_name.get(name) or {}))
                              for name in names])
