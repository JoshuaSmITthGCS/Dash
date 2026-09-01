"""Registry of foreign-domiciled/ADR tickers whose exchange share count is not directly
interchangeable with the share count on the underlying issuer's own financial statements.

Round-12 valuation audit finding: pipeline/valuation_history.py and
pipeline/backtest_historical.py both reconstruct ``market_cap = price * shares`` from a
statement-derived share count (Yahoo's "Ordinary Shares Number"/"Share Issued" balance-sheet
row). For a name like TSM, that row is the company's total *ordinary*-share count, not the
ADS-equivalent share count an ADR's USD price implies (TSM trades 1 ADS per 5 ordinary
shares) -- multiplying the ADR price by the full ordinary-share count overstates market cap,
and every multiple built on it, by roughly the ADR ratio.

This module is the single place either call site must consult before doing that
multiplication. See pipeline/config/adr_listings.json for the registry data and why every
entry currently ships with ``verified: false`` (no ratio is used with false confidence).
"""
from common import load_json

_REGISTRY = None


def _registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = (load_json("adr_listings.json", from_config=True) or {}).get("tickers", {})
    return _REGISTRY


def adr_entry(ticker):
    """The registry entry for ``ticker``, or None if it isn't a known ADR/foreign listing."""
    return _registry().get(str(ticker or "").upper())


def verified_ads_ratio(ticker):
    """Ordinary shares per one ADS for ``ticker``, only once checked against a primary
    source. Returns None when unverified -- callers must not guess a ratio.
    """
    entry = adr_entry(ticker)
    if not entry or not entry.get("verified"):
        return None
    return entry.get("adr_ratio")


def is_unreconciled_adr(ticker):
    """True when ``ticker`` is a known ADR/foreign listing with no verified share-count ratio.

    A caller about to multiply a statement-derived share count by a live price must treat
    this as "cannot reconcile -- unavailable", never fall back to using the raw ordinary-share
    count as if it were ADS-equivalent.
    """
    entry = adr_entry(ticker)
    return bool(entry and entry.get("is_adr") and not entry.get("verified"))


def ads_equivalent_shares(ticker, ordinary_shares):
    """``ordinary_shares`` converted to ADS-equivalent shares, or None if not reconcilable.

    Returns ``ordinary_shares`` unchanged for a ticker the registry doesn't know about (an
    ordinary US-domiciled listing, where the concept doesn't apply). Returns None -- not a
    best-effort guess -- for a known ADR with no verified ratio, and for a known ADR the
    caller must not silently treat as a 1:1 ordinary listing.
    """
    if ordinary_shares is None:
        return None
    entry = adr_entry(ticker)
    if not entry:
        return ordinary_shares
    ratio = verified_ads_ratio(ticker)
    if not ratio:
        return None
    return ordinary_shares / ratio
