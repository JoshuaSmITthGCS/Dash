"""Capability-specific provider contracts for canonical observations.

Providers may implement more than one protocol, but callers depend on the smallest
capability they need.  This prevents an estimate outage from being confused with a
price outage and keeps field definitions explicit.
"""

from typing import Protocol


class PriceProvider(Protocol):
    def prices(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class FundamentalsProvider(Protocol):
    def fundamentals(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class EstimateProvider(Protocol):
    def estimates(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class FilingProvider(Protocol):
    def filings(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class InsiderProvider(Protocol):
    def insider_transactions(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class NewsProvider(Protocol):
    def news(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class MacroProvider(Protocol):
    def macro(self, series_ids: list[str], as_of: str | None = None) -> list[dict]: ...


class ETFMetadataProvider(Protocol):
    def etf_metadata(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class ETFNavProvider(Protocol):
    def etf_nav(self, symbol: str, as_of: str | None = None) -> list[dict]: ...


class ETFBenchmarkProvider(Protocol):
    def etf_benchmark(self, symbol: str, as_of: str | None = None) -> list[dict]: ...
