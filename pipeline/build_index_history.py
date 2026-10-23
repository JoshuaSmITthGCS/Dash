"""Publish the market-index close history behind the Portfolio > Performance returns table.

Runs after the US close (see .github/workflows/refresh-index-returns.yml) so the table's
"as of" date is always the session that just ended. It is deliberately separate from
build_etf_comparisons.py: that script rebuilds ~125 multi-megabyte ETF contracts, while this
one fetches eight symbols and writes one compact file.

Every series is the provider's split- and distribution-adjusted close, so period returns read
as total returns. Each index is an investable ETF proxy, not the index itself, and the
published `index` field says which index it stands in for.
"""

from datetime import datetime, timezone

from build_etf_comparisons import _fetch_rows
from cache import CACHE
from common import LOG, save_json

# ~11 years of sessions: enough for a 10-year window plus the prior period-end close.
INDEX_OBSERVATIONS = 2800
CALENDAR_SYMBOL = "SPY"

INDEX_PROXIES = (
    {"symbol": "SPY", "label": "S&P 500® Index", "index": "S&P 500"},
    {"symbol": "VTI", "label": "U.S. Total Stock Market", "index": "CRSP U.S. Total Market"},
    {"symbol": "DIA", "label": "Dow Jones Industrial Average", "index": "Dow Jones Industrial Average"},
    {"symbol": "QQQ", "label": "Nasdaq-100", "index": "Nasdaq-100"},
    {"symbol": "ACWX", "label": "MSCI ACWI ex USA", "index": "MSCI ACWI ex USA"},
    {"symbol": "AGG", "label": "U.S. Aggregate Bond", "index": "Bloomberg U.S. Aggregate Bond"},
    {"symbol": "MUB", "label": "Municipal Bond", "index": "ICE AMT-Free National Municipal"},
    {"symbol": "BIL", "label": "3-Month Treasury Bill", "index": "Bloomberg 1-3 Month T-Bill"},
)


def build_index_history_payload(rows_by_symbol, generated_at=None, observations=INDEX_OBSERVATIONS):
    """Align every proxy to the calendar symbol's sessions; a missing close is null, never filled."""
    calendar_rows = rows_by_symbol.get(CALENDAR_SYMBOL) or []
    dates = [row["date"] for row in calendar_rows if row.get("date")][-observations:]
    if len(dates) < 2:
        return None
    symbols = {}
    for proxy in INDEX_PROXIES:
        rows = rows_by_symbol.get(proxy["symbol"]) or []
        closes_by_date = {row["date"]: row["adjusted_close"] for row in rows
                          if row.get("date") and row.get("adjusted_close") is not None}
        closes = [round(closes_by_date[date], 4) if date in closes_by_date else None for date in dates]
        if sum(value is not None for value in closes) < 2:
            continue
        symbols[proxy["symbol"]] = {"label": proxy["label"], "index": proxy["index"], "closes": closes}
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "as_of": dates[-1],
        "return_basis": "provider_adjusted_close_total_return_compatible",
        "dates": dates,
        "symbols": symbols,
    }


def publish_index_history():
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance missing; cannot build the index history")
        return None
    rows_by_symbol = {}
    for proxy in INDEX_PROXIES:
        try:
            rows_by_symbol[proxy["symbol"]] = _fetch_rows(proxy["symbol"], yf, "max", CACHE)
        except Exception as error:  # one dead proxy must not blank the whole table
            LOG.warning(f"index history fetch failed for {proxy['symbol']}: {error}")
    payload = build_index_history_payload(rows_by_symbol)
    if payload is None:
        LOG.error(f"no {CALENDAR_SYMBOL} calendar history; keeping the previous index-history.json")
        return None
    save_json("index-history.json", payload)
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if publish_index_history() is not None else 1)
