"""
scorer.py
Turn normalized trades + prices + news into a ranked signal list.

Two independent scores per ticker:
  political_score (0-100)  -- from the 6-factor weight table (settings.json)
  valuation_score (0-100)  -- broad fundamental score retained under the legacy field name

The ranker (rank_picks.py) blends these differently per bucket.
Also emits a cooling list: tickers with heavy congressional selling.

Output labels are research tiers, never 'BUY':
  HIGH CONVICTION / WATCH / NEUTRAL / COOLING
"""

from collections import defaultdict
from datetime import datetime, timezone

from common import (LOG, data_mode, load_json, save_json, days_between, today_iso,
                    normalize_name, update_pipeline_status)

SETTINGS = load_json("settings.json", from_config=True) or {}
COMMITTEES = (load_json("committees.json", from_config=True) or {}).get("politicians", {})


# ---------------- political factors ----------------

def score_track_record(politician, track_index, w):
    row = track_index.get(normalize_name(politician))
    if not row:
        return 0.0
    return round(w * (row["percentile"] / 100.0), 2)


def score_committee(politician, ticker, ticker_sector, w):
    cfg = COMMITTEES.get(normalize_name(politician))
    if not cfg or not ticker_sector:
        return 0.0
    return round(w, 2) if ticker_sector in cfg.get("sectors", []) else 0.0


def score_cluster(ticker, cluster_counts, w):
    cfg = SETTINGS["cluster"]
    n = cluster_counts.get(ticker, 0)
    if n >= cfg["min_politicians_for_max"]:
        return round(w, 2)
    if n == 2:
        return round(w * 0.5, 2)
    return 0.0


def score_size(amount_mid, w):
    b = SETTINGS["trade_size_bands"]
    if amount_mid >= b["high_min"]:
        return round(w, 2)
    if amount_mid >= b["mid_max"]:
        return round(w * 0.75, 2)
    if amount_mid > b["low_max"]:
        return round(w * 0.5, 2)
    if amount_mid > 0:
        return round(w * 0.25, 2)
    return 0.0


def score_direction_recency(trade, w):
    if trade.get("type") != "buy":
        return 0.0
    r = SETTINGS["recency"]
    lag = days_between(trade.get("filing_date"), today_iso())
    if lag is None:
        return round(w * 0.5, 2)
    if lag <= r["hot_filing_days"]:
        return round(w, 2)
    if lag <= r["warm_filing_days"]:
        return round(w * 0.66, 2)
    return round(w * 0.33, 2)


def score_policy(ticker, ticker_sector, flagged_sectors, flagged_tickers, w):
    if ticker in flagged_tickers:
        return round(w, 2)
    if ticker_sector and ticker_sector in flagged_sectors:
        return round(w * 0.7, 2)
    return 0.0


# ---------------- fundamental factor ----------------

def band_score(value, bands, lower_is_better=True):
    """Map a metric to 0-100 across ordered bands. Returns None if value missing."""
    if value is None:
        return None
    if value < 0:
        return 15.0  # negative earnings / odd data -> penalize, don't zero out
    keys = list(bands.keys())
    tiers = [100, 75, 50, 25]
    for i, k in enumerate(keys):
        if value <= bands[k]:
            return float(tiers[i]) if lower_is_better else float(tiers[len(keys) - 1 - i])
    return 10.0 if lower_is_better else 100.0


def higher_is_better_score(value, bands):
    """Score decimal ratios/growth where more is generally better."""
    if value is None:
        return None
    for key, score in (("excellent_min", 100), ("good_min", 80),
                       ("fair_min", 55), ("weak_min", 30)):
        if value >= bands[key]:
            return float(score)
    return 10.0


def multiple_score(value, bands):
    """Score a positive valuation multiple while flagging unusually low P/E as possible value-trap risk."""
    if value is None:
        return None
    if value <= 0:
        return 5.0
    if bands.get("suspicious_below") and value < bands["suspicious_below"]:
        return 60.0
    if value <= bands["cheap_max"]:
        return 100.0
    if value <= bands["healthy_max"]:
        return 80.0
    if value <= bands["elevated_max"]:
        return 45.0
    return 15.0


def weighted_available(scores, weights):
    available = [(scores[k], weights[k]) for k in weights if scores.get(k) is not None]
    if not available:
        return None
    return sum(score * weight for score, weight in available) / sum(weight for _, weight in available)


def valuation_score(snap):
    """Score valuation, profitability, solvency, cash generation, and growth.

    ETFs remain unscored because corporate accounting ratios are not comparable to fund holdings.
    Missing values are reweighted, then the final score is confidence-adjusted for data coverage.
    """
    if not snap or snap.get("is_etf"):
        return None, {}
    cfg = SETTINGS["fundamentals"]
    sector = snap.get("sector") or "default"
    is_financial = sector in ("Financial Services", "Financials")
    pe_bands = cfg["forward_pe_by_sector"].get(sector, cfg["forward_pe_by_sector"]["default"])
    ps_bands = cfg["price_to_sales_by_sector"].get(sector, cfg["price_to_sales_by_sector"]["default"])

    metrics = {
        "peg": band_score(snap.get("peg"), cfg["peg"]),
        "forward_pe": multiple_score(snap.get("forward_pe"), pe_bands),
        "price_to_sales": multiple_score(snap.get("price_to_sales"), ps_bands),
        "price_to_book": band_score(snap.get("price_to_book"), cfg["price_to_book"]),
        "return_on_equity": higher_is_better_score(snap.get("return_on_equity"), cfg["return_on_equity"]),
        "free_cash_flow_yield": higher_is_better_score(snap.get("free_cash_flow_yield"), cfg["free_cash_flow_yield"]),
        "profit_margin": higher_is_better_score(snap.get("profit_margin"), cfg["profit_margin"]),
        # Bank balance sheets are structurally leveraged; these industrial-company cutoffs do not apply.
        "debt_to_equity": None if is_financial else band_score(snap.get("debt_to_equity"), cfg["debt_to_equity"]),
        "current_ratio": None if is_financial else higher_is_better_score(snap.get("current_ratio"), cfg["current_ratio"]),
        "revenue_growth": higher_is_better_score(snap.get("revenue_growth"), cfg["revenue_growth"]),
        "earnings_growth": higher_is_better_score(snap.get("earnings_growth"), cfg["earnings_growth"]),
    }
    categories = {}
    for category, weights in cfg["metric_weights"].items():
        value = weighted_available(metrics, weights)
        categories[category] = round(value, 1) if value is not None else None
    raw = weighted_available(categories, cfg["category_weights"])
    if raw is None:
        return None, {**metrics, "categories": categories, "coverage": 0.0}
    coverage = sum(value is not None for value in metrics.values()) / len(metrics)
    confidence_multiplier = 0.65 + (0.35 * coverage)
    total = round(raw * confidence_multiplier, 1)
    return total, {**metrics, "categories": categories, "coverage": round(coverage, 2),
                   "raw_score": round(raw, 1), "sector": sector}


# ---------------- assembly ----------------

def ticker_sector_lookup(prices, policy):
    """Best-effort ticker -> policy sector (for committee + policy scoring)."""
    lut = {}
    for sector, cfg in policy.get("sectors", {}).items():
        for tk in cfg.get("tickers", []):
            lut.setdefault(tk, sector)
    return lut


def label_for(score):
    lb = SETTINGS["labels"]
    if score >= lb["high_conviction_min"]:
        return "HIGH CONVICTION"
    if score >= lb["watch_min"]:
        return "WATCH"
    if score >= lb["neutral_min"]:
        return "NEUTRAL"
    return "LOW"


def run():
    trade_payload = load_json("trades.json") or {}
    price_payload = load_json("prices.json") or {}
    trades = trade_payload.get("trades", [])
    prices = price_payload.get("prices", {})
    news = load_json("news.json") or {}
    track = (load_json("politicians.json") or {}).get("leaderboard", [])
    policy = load_json("policy_map.json", from_config=True) or {}

    track_index = {normalize_name(r["politician"]): r for r in track}
    sector_lut = ticker_sector_lookup(prices, policy)
    flagged_sectors = news.get("flagged_sectors", {})
    flagged_tickers = news.get("flagged_tickers", {})
    w = SETTINGS["signal_weights"]
    cluster_cfg = SETTINGS["cluster"]

    # cluster counts: distinct politicians buying same ticker within window
    buyers = defaultdict(set)
    sellers = defaultdict(set)
    for t in trades:
        lag = days_between(t.get("trade_date"), today_iso())
        if lag is None or lag > cluster_cfg["window_days"]:
            continue
        if t.get("type") == "buy":
            buyers[t["ticker"]].add(normalize_name(t["politician"]))
        elif t.get("type") == "sell":
            sellers[t["ticker"]].add(normalize_name(t["politician"]))
    cluster_counts = {tk: len(p) for tk, p in buyers.items()}

    # aggregate per ticker: take the strongest supporting buy
    best = {}
    for t in trades:
        if t.get("type") != "buy" or not t.get("ticker"):
            continue
        tk = t["ticker"]
        sec = sector_lut.get(tk)
        breakdown = {
            "track_record": score_track_record(t["politician"], track_index, w["track_record"]),
            "committee_relevance": score_committee(t["politician"], tk, sec, w["committee_relevance"]),
            "cluster_detection": score_cluster(tk, cluster_counts, w["cluster_detection"]),
            "trade_size": score_size(t.get("amount_mid", 0), w["trade_size"]),
            "direction_recency": score_direction_recency(t, w["direction_recency"]),
            "policy_catalyst": score_policy(tk, sec, flagged_sectors, flagged_tickers, w["policy_catalyst"]),
        }
        political = round(sum(breakdown.values()), 1)
        if tk not in best or political > best[tk]["political_score"]:
            snap = prices.get(tk, {})
            val_score, val_parts = valuation_score(snap)
            best[tk] = {
                "ticker": tk,
                "name": snap.get("name", tk),
                "sector": snap.get("sector") or sec,
                "is_etf": snap.get("is_etf", False),
                "political_score": political,
                "breakdown": breakdown,
                "cluster_size": cluster_counts.get(tk, 0),
                "top_buyer": t["politician"],
                "filing_lag_days": t.get("filing_lag_days"),
                "amount_range": t.get("amount_range"),
                # broad fundamentals (legacy valuation_score name kept for data compatibility)
                "valuation_score": val_score,
                "valuation_parts": val_parts,
                "fundamental_categories": val_parts.get("categories", {}),
                "fundamental_coverage": val_parts.get("coverage", 0.0),
                "peg": snap.get("peg"),
                "forward_pe": snap.get("forward_pe"),
                "price_to_sales": snap.get("price_to_sales"),
                "price_to_book": snap.get("price_to_book"),
                "return_on_equity": snap.get("return_on_equity"),
                "free_cash_flow": snap.get("free_cash_flow"),
                "free_cash_flow_yield": snap.get("free_cash_flow_yield"),
                "debt_to_equity": snap.get("debt_to_equity"),
                "current_ratio": snap.get("current_ratio"),
                "profit_margin": snap.get("profit_margin"),
                "revenue_growth": snap.get("revenue_growth"),
                "earnings_growth": snap.get("earnings_growth"),
                "pct_30d": snap.get("pct_30d"),
                "dividend_yield": snap.get("dividend_yield"),
                "market_cap": snap.get("market_cap"),
                "price": snap.get("price"),
                "label": label_for(political),
            }

    signals = sorted(best.values(), key=lambda x: x["political_score"], reverse=True)

    # cooling list: heavy selling clusters
    cooling = []
    for tk, pols in sellers.items():
        if len(pols) >= 2:
            snap = prices.get(tk, {})
            cooling.append({
                "ticker": tk,
                "name": snap.get("name", tk),
                "sellers": len(pols),
                "sector": snap.get("sector"),
                "pct_30d": snap.get("pct_30d"),
                "label": "COOLING",
            })
    cooling.sort(key=lambda x: x["sellers"], reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": data_mode(trade_payload, price_payload, news),
        "count": len(signals),
        "hot_sectors": flagged_sectors,
        "signals": signals,
        "cooling": cooling,
    }
    save_json("signals.json", payload)
    update_pipeline_status("scoring", status="healthy", source="local scoring engine",
                           details={"signals": len(signals), "cooling": len(cooling)})
    LOG.info(f"Wrote signals.json: {len(signals)} signals, {len(cooling)} cooling")
    return payload


if __name__ == "__main__":
    run()
