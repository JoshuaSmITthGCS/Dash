"""Rank an ETF watchlist on the metrics that actually apply to a diversified fund:
performance, risk-adjusted return, total cost of ownership, liquidity, and structure.
A single stock's fundamentals ratios (PEG, P/S, ROE...) don't translate to a basket of
holdings, so ETFs are scored and ranked independently of the stock research pipeline.

Two things changed here relative to the first version, both of them corrections rather
than additions:

**Peer-group ranking.** Every metric used to be percentile-ranked against the whole
40-fund batch, which meant a Treasury fund's Sharpe was ranked against a semiconductor
fund's Sharpe and a sector fund's return against a broad index's. Those comparisons have
no meaning - the resulting "rank" mostly measured which asset class happened to have a
good three years. Funds are now ranked inside their own peer group (broad equity, sector,
thematic, fixed income, commodity, crypto...), and composite scores are only comparable
within a group.

**Cost is more than the expense ratio.** The expense ratio is what the issuer charges;
what an owner actually loses is the tracking difference against the fund's own index plus
whatever premium to NAV they paid on the way in. Both are free: tracking difference from
the return series, premium/discount and the median 30-day spread from the issuer's
legally mandated Rule 6c-11 disclosure (see ``etf_disclosure``).

Every fund is still also compared against just buying the S&P 500 (SPY) or the Dow (DIA) -
both are themselves part of the scored universe, so the comparison is apples-to-apples.
"""

import os
from datetime import datetime, timezone

from cache import CACHE, parallel_map, retry_with_backoff
from common import LOG, load_json, save_json, update_pipeline_status
from etf_disclosure import (effective_spread_pct, fetch_disclosure, from_quote,
                            total_cost_of_ownership)
from risk_metrics import (beta_vs_benchmark, daily_returns, max_drawdown, period_return,
                          sharpe_ratio, sortino_ratio, tracking_difference, tracking_error)

UNIVERSE = load_json("universe.json", from_config=True) or {}
ETFS = UNIVERSE.get("etfs", {})
SP500_TICKER = "SPY"
DOW_TICKER = "DIA"

# Trading-day windows for the performance and vs-benchmark comparisons.
WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756}

# Which peer group each configured category belongs to. Cross-group score comparisons are
# suppressed in the output; a bond fund outranking a growth fund would be an artifact of
# the batch, not a finding. Overridable from config so a new asset class is a config edit.
DEFAULT_PEER_GROUPS = {
    "broad_market": "equity_broad",
    "growth": "equity_broad",
    "value": "equity_broad",
    "dividend": "equity_income",
    "small_cap": "equity_broad",
    "international": "equity_international",
    "sector": "equity_sector",
    "thematic": "equity_thematic",
    "bonds": "fixed_income",
    "commodity": "commodity",
    "crypto": "crypto",
}
# Below this many funds a percentile is noise, so the group falls back to the full batch
# and the row is flagged so the UI can say the ranking is cross-asset-class.
MIN_PEER_GROUP_SIZE = 4

# Analyst ratings (Morningstar/CFRA) require a paid feed. The structural stand-in below is
# free and more informative than brand alone: issuer reputation, fund age, and asset base
# are all observable, and leverage/synthetic replication are structural risks a brand score
# cannot express.
ISSUER_QUALITY = {
    "Vanguard": 100, "iShares": 98, "State Street": 95, "Schwab": 92,
    "Invesco": 85, "JPMorgan": 85, "VanEck": 75, "ARK": 55,
}

DEFAULT_SCORE_WEIGHTS = {"performance": 0.28, "risk": 0.27, "cost": 0.17,
                         "liquidity": 0.16, "quality": 0.12}


def score_weights():
    configured = (UNIVERSE.get("etf_scoring", {}) or {}).get("weights")
    return {**DEFAULT_SCORE_WEIGHTS, **(configured or {})}


def peer_groups():
    configured = (UNIVERSE.get("etf_scoring", {}) or {}).get("peer_groups")
    return {**DEFAULT_PEER_GROUPS, **(configured or {})}


SCORE_WEIGHTS = score_weights()


def peer_group_for(meta):
    """Peer group for one fund: explicit config wins, category mapping otherwise."""
    explicit = (meta or {}).get("peer_group")
    if explicit:
        return explicit
    return peer_groups().get((meta or {}).get("category", ""), "other")


# ---------------- fetching ----------------

def price_history(symbol, yf, ticker_obj=None, cache=None):
    """Three years of closes and volumes, served from the on-disk cache when fresh."""
    cache = cache or CACHE

    def produce():
        def download():
            source = ticker_obj or yf.Ticker(symbol)
            frame = source.history(period="3y", auto_adjust=False).dropna(subset=["Close"])
            if frame.empty:
                raise ValueError("empty price frame")
            return {
                "closes": [float(value) for value in frame["Close"].tolist()],
                "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
            }
        return retry_with_backoff(download, description=f"{symbol} price history")

    try:
        return cache.fetch("price_history", f"{symbol}:3y", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return {"closes": [], "volumes": []}


def etf_snapshot(ticker, yf, ticker_obj=None, cache=None):
    """Quote-level fields, including the NAV needed for the premium/discount fallback."""
    cache = cache or CACHE

    def produce():
        tk = ticker_obj or yf.Ticker(ticker)
        info = tk.info or {}
        return {
            "price": info.get("regularMarketPrice") or info.get("navPrice"),
            "nav": info.get("navPrice"),
            "aum": info.get("totalAssets"),
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "inception": info.get("fundInceptionDate"),
        }

    try:
        return cache.fetch("quote", f"etf:{ticker}", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: Yahoo snapshot unavailable ({type(exc).__name__})")
        return {}


# Re-exported so existing importers and tests keep working after the risk math moved into
# risk_metrics, where the stock model can share exactly the same implementations.
__all__ = ["beta_vs_benchmark", "build_etf_row", "build_etfs", "daily_returns",
           "peer_group_for", "percentile_scores", "period_return", "score_etf_universe",
           "sharpe_ratio", "sortino_ratio"]


def percentile_scores(values, higher_is_better=True):
    """Map a batch of possibly-missing raw values onto 0-100 so unlike metrics (a return
    percentage, an expense ratio, an AUM in dollars) can be combined into one score.
    A fund missing a metric stays neutral rather than being punished for lacking it.

    Equal values share a percentile. Without that, four funds with identical expense ratios
    would be spread across 0, 33, 67, and 100 purely by their position in the input list -
    a ranking that looks decisive and means nothing.
    """
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    scores = [50.0] * len(values)
    if len(present) < 2:
        return scores
    ordered = sorted(present, key=lambda pair: pair[1])
    n = len(ordered)
    position = 0
    while position < n:
        end = position
        while end + 1 < n and ordered[end + 1][1] == ordered[position][1]:
            end += 1
        shared_rank = (position + end) / 2
        pct = 100 * shared_rank / (n - 1)
        for index, _ in ordered[position:end + 1]:
            scores[index] = pct if higher_is_better else 100 - pct
        position = end + 1
    return scores


def _average(values):
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else 50.0


def structural_quality(row, meta):
    """Issuer reputation adjusted by observable structure, not brand alone.

    Fund age and asset base both proxy for survival odds and creation/redemption health;
    leverage and synthetic replication are genuine structural risks that a strong brand
    does not offset. All four are free and more informative than the issuer name by itself.
    """
    base = ISSUER_QUALITY.get(row.get("issuer"), 60)
    aum = row.get("aum")
    if aum is not None:
        if aum >= 5e9:
            base += 6
        elif aum < 2.5e8:
            base -= 10
    if (meta or {}).get("leveraged") or (meta or {}).get("inverse"):
        base -= 25
    if (meta or {}).get("replication") == "synthetic":
        base -= 10
    if (meta or {}).get("securities_lending") == "aggressive":
        base -= 5
    return round(max(0.0, min(100.0, base)), 1)


def build_etf_row(ticker, meta, snapshot, closes, volumes, benchmark_daily_returns,
                  index_closes=None, disclosure=None):
    """One fund's raw, un-ranked metrics. Pure: everything is derived from its arguments."""
    rets = daily_returns(closes)
    avg_volume = sum(volumes[-30:]) / len(volumes[-30:]) if len(volumes) >= 5 else None
    price = closes[-1] if closes else snapshot.get("price")
    # With no issuer disclosure supplied, derive what the quote payload can support: a
    # one-moment spread and a NAV-based premium/discount, both labelled as the fallback.
    disclosure = disclosure if disclosure is not None else from_quote(snapshot)
    spread, spread_source = effective_spread_pct(disclosure)

    returns = {label: period_return(closes, days) for label, days in WINDOWS.items()}
    index_returns, tracking = {}, {}
    if index_closes:
        index_returns = {label: period_return(index_closes, days) for label, days in WINDOWS.items()}
        tracking = {label: tracking_difference(returns[label], index_returns[label])
                    for label in WINDOWS}
    expense_ratio = meta.get("expense_ratio")
    annual_tracking = tracking.get("1y")
    premium = disclosure.get("premium_discount_pct")

    row = {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "category": meta.get("category", "etf"),
        "peer_group": peer_group_for(meta),
        "sector": meta.get("category", "etf").replace("_", " ").title(),
        "confidence": 1.0,
        "issuer": meta.get("issuer", "Other"),
        "expense_ratio": expense_ratio,
        "price": round(price, 2) if price else None,
        "aum": snapshot.get("aum"),
        "avg_dollar_volume": round(avg_volume * price, 0) if avg_volume and price else None,
        "bid_ask_spread_pct": spread,
        "bid_ask_spread_source": spread_source,
        "nav": disclosure.get("nav"),
        "premium_discount_pct": premium,
        "premium_discount_source": disclosure.get("source"),
        "returns": returns,
        "index_symbol": meta.get("index_proxy"),
        "index_returns": index_returns or None,
        "tracking_difference": tracking or None,
        "tracking_difference_1y": annual_tracking,
        "tracking_error_pct": (tracking_error(rets, daily_returns(index_closes))
                               if index_closes else None),
        "total_cost_of_ownership_pct": total_cost_of_ownership(expense_ratio, annual_tracking, premium),
        "max_drawdown": max_drawdown(closes),
        "sharpe_ratio": sharpe_ratio(rets),
        "sortino_ratio": sortino_ratio(rets),
        "beta": beta_vs_benchmark(rets, benchmark_daily_returns),
    }
    row["quality_score"] = structural_quality(row, meta)
    return row


# ---------------- scoring ----------------

RISK_KEYS = ("sortino_ratio", "sharpe_ratio", "max_drawdown", "beta")
# Sharpe and Sortino overlap heavily. Sortino leads because downside deviation is the risk
# an owner is actually trying to avoid; Sharpe is kept as a secondary cross-check. Beta
# enters because it is the core systematic-risk measure and the betting-against-beta
# literature (Frazzini & Pedersen 2014) says it is priced.
RISK_SUBWEIGHTS = {"sortino_ratio": 0.38, "sharpe_ratio": 0.20, "max_drawdown": 0.24, "beta": 0.18}
COST_KEYS = ("expense_ratio", "tracking_difference_1y", "premium_discount_pct")
COST_SUBWEIGHTS = {"expense_ratio": 0.40, "tracking_difference_1y": 0.40,
                   "premium_discount_pct": 0.20}
LIQUIDITY_KEYS = ("aum", "avg_dollar_volume", "bid_ask_spread_pct")


def _weighted(values, weights):
    """Weighted mean over whichever components are present."""
    present = [(values[key], weights[key]) for key in weights if values.get(key) is not None]
    if not present:
        return 50.0
    return round(sum(value * weight for value, weight in present)
                 / sum(weight for _, weight in present), 1)


def rank_within(rows, indices, key, higher_is_better=True, transform=None):
    """Percentile-rank one metric across a subset of rows, returning {row_index: score}."""
    values = []
    for index in indices:
        value = rows[index].get(key)
        values.append(transform(value) if transform and value is not None else value)
    scores = percentile_scores(values, higher_is_better=higher_is_better)
    return {index: scores[position] for position, index in enumerate(indices)}


def group_indices(rows):
    """Row indices bucketed by peer group, with under-populated groups pooled.

    A group with fewer than ``MIN_PEER_GROUP_SIZE`` members cannot produce a meaningful
    percentile, so its members are ranked against the whole batch instead - and marked
    ``cross_asset_class`` so the caller never presents that rank as a like-for-like one.
    """
    buckets = {}
    for index, row in enumerate(rows):
        buckets.setdefault(row.get("peer_group", "other"), []).append(index)
    resolved, pooled = {}, []
    for group, indices in buckets.items():
        if len(indices) >= MIN_PEER_GROUP_SIZE:
            resolved[group] = indices
        else:
            pooled.extend(indices)
    if pooled:
        resolved["_pooled"] = pooled
    return resolved


def score_etf_universe(rows, sp500_ticker=SP500_TICKER, dow_ticker=DOW_TICKER):
    """Rank each fund inside its own peer group, then blend the five weighted buckets.

    Percentiles are computed per group, so a fund's ``overall`` score answers "how does
    this compare to funds doing the same job" - the only version of the question that has
    an answer. Cross-group ordering is preserved in the output purely for display and
    labelled as such via ``peer_rank``.
    """
    window_labels = list(WINDOWS.keys())
    grouped = group_indices(rows)
    weights = score_weights()

    performance, risk, cost, liquidity = {}, {}, {}, {}
    group_of = {}
    for group, indices in grouped.items():
        for index in indices:
            group_of[index] = group
        # Returns live in a nested dict, so they are ranked here rather than via rank_within.
        window_ranks = {}
        for label in window_labels:
            values = [rows[index]["returns"][label] for index in indices]
            scores = percentile_scores(values, higher_is_better=True)
            window_ranks[label] = {index: scores[position] for position, index in enumerate(indices)}
        risk_ranks = {
            "sortino_ratio": rank_within(rows, indices, "sortino_ratio", True),
            "sharpe_ratio": rank_within(rows, indices, "sharpe_ratio", True),
            "max_drawdown": rank_within(rows, indices, "max_drawdown", True),
            # Low beta scores well: the betting-against-beta result says high-beta assets
            # have not paid for the systematic risk they carry.
            "beta": rank_within(rows, indices, "beta", False),
        }
        cost_ranks = {
            "expense_ratio": rank_within(rows, indices, "expense_ratio", False),
            # A fund ahead of its index is genuinely better than one behind it, so this
            # ranks the signed difference rather than its absolute size.
            "tracking_difference_1y": rank_within(rows, indices, "tracking_difference_1y", True),
            # Paying a premium is a cost either way, so the absolute deviation is ranked.
            "premium_discount_pct": rank_within(rows, indices, "premium_discount_pct", False,
                                                transform=abs),
        }
        liquidity_ranks = {
            "aum": rank_within(rows, indices, "aum", True),
            "avg_dollar_volume": rank_within(rows, indices, "avg_dollar_volume", True),
            "bid_ask_spread_pct": rank_within(rows, indices, "bid_ask_spread_pct", False),
        }
        for index in indices:
            row = rows[index]
            performance[index] = _average([
                window_ranks[label][index] for label in window_labels
                if row["returns"][label] is not None
            ])
            risk[index] = _weighted(
                {key: risk_ranks[key][index] if row.get(key) is not None else None
                 for key in RISK_KEYS}, RISK_SUBWEIGHTS)
            cost[index] = _weighted(
                {key: cost_ranks[key][index] if row.get(key) is not None else None
                 for key in COST_KEYS}, COST_SUBWEIGHTS)
            liquidity[index] = _average([
                liquidity_ranks[key][index] for key in LIQUIDITY_KEYS
                if row.get(key) is not None
            ])

    sp500_returns = next((row["returns"] for row in rows if row["ticker"] == sp500_ticker), None)
    dow_returns = next((row["returns"] for row in rows if row["ticker"] == dow_ticker), None)

    scored = []
    for index, row in enumerate(rows):
        buckets = {"performance": performance[index], "risk": risk[index], "cost": cost[index],
                   "liquidity": liquidity[index], "quality": row["quality_score"]}
        overall = round(sum(buckets[bucket] * weight for bucket, weight in weights.items()), 1)

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
            "ranked_against": group_of[index],
            "cross_asset_class_rank": group_of[index] == "_pooled",
            "vs_benchmarks": vs_benchmarks,
        })

    scored.sort(key=lambda item: item["scores"]["overall"], reverse=True)
    for rank, row in enumerate(scored):
        row["overall_rank"] = rank + 1
    # The rank that actually means something: position inside the peer group.
    by_group = {}
    for row in scored:
        by_group.setdefault(row["ranked_against"], []).append(row)
    for group, members in by_group.items():
        for rank, row in enumerate(members):
            row["peer_rank"] = rank + 1
            row["peer_group_size"] = len(members)
    return scored


# ---------------- assembly ----------------

def index_proxy_symbols(etfs):
    """Every distinct index-proxy ticker the config references."""
    return sorted({meta.get("index_proxy") for meta in etfs.values() if meta.get("index_proxy")})


def build_etfs():
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r requirements.txt")
        return None

    tickers = list(ETFS.keys())
    proxies = [symbol for symbol in index_proxy_symbols(ETFS) if symbol not in tickers]
    max_workers = int(os.getenv("ETF_FETCH_WORKERS", "4"))
    fetch_symbols = tickers + proxies
    fetched = parallel_map(lambda symbol: (symbol, price_history(symbol, yf)),
                           fetch_symbols, provider="yahoo", max_workers=max_workers)
    histories = {symbol: history for symbol, history in fetched if symbol}
    benchmark_daily = daily_returns(histories.get(SP500_TICKER, {"closes": []})["closes"])

    snapshots = dict(parallel_map(lambda symbol: (symbol, etf_snapshot(symbol, yf)),
                                  tickers, provider="yahoo", max_workers=max_workers))

    raw_rows = []
    for ticker in tickers:
        history = histories.get(ticker) or {"closes": [], "volumes": []}
        if len(history["closes"]) < 30:
            LOG.warn(f"{ticker}: not enough price history for ETF metrics")
            continue
        snapshot = snapshots.get(ticker) or {}
        meta = ETFS[ticker]
        disclosure = fetch_disclosure(ticker, meta, snapshot=snapshot)
        index_closes = (histories.get(meta.get("index_proxy")) or {}).get("closes")
        raw_rows.append(build_etf_row(ticker, meta, snapshot, history["closes"],
                                      history["volumes"], benchmark_daily,
                                      index_closes=index_closes, disclosure=disclosure))

    have_benchmarks = {SP500_TICKER, DOW_TICKER}.issubset({row["ticker"] for row in raw_rows})
    if not have_benchmarks:
        message = "S&P 500 (SPY) and/or Dow (DIA) benchmark rows missing; cannot score the watchlist against them"
        LOG.error(message)
        update_pipeline_status("etfs", status="error", source="Yahoo Finance", message=message)
        return None

    scored = score_etf_universe(raw_rows)
    disclosed = sum(1 for row in scored if row.get("bid_ask_spread_source") == "rule_6c11_median_30d")
    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "benchmarks": {"sp500": SP500_TICKER, "dow": DOW_TICKER},
        "count": len(scored),
        "score_weights": score_weights(),
        "peer_groups": sorted({row["ranked_against"] for row in scored}),
        "methodology": {
            "ranking": "Percentiles are computed within each peer group, not across the whole "
                       "batch. Comparing a bond fund's Sharpe to an equity fund's produces a "
                       "number, not a finding.",
            "cost": "Expense ratio, tracking difference against the fund's own index proxy, and "
                    "NAV premium/discount. The expense ratio alone is not the cost of ownership.",
            "disclosure": "Premium/discount and median 30-day bid-ask spread come from issuer "
                          "Rule 6c-11 disclosures where configured, and from quote NAV otherwise.",
        },
        "disclosure_coverage": {"rule_6c11": disclosed, "total": len(scored)},
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
                           details={"requested": len(tickers), "received": len(scored),
                                    "rule_6c11_disclosures": disclosed,
                                    "cache": CACHE.stats()})
    LOG.info(f"Wrote etfs.json with {len(scored)} ETFs across "
             f"{len(payload['peer_groups'])} peer groups")
    return payload


def main():
    return 0 if build_etfs() is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
