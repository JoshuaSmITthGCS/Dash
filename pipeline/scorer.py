"""
scorer.py
Turn normalized trades + prices + news into a ranked signal list.

Two independent scores per ticker:
  political_score (0-100)  -- from the 6-factor weight table (settings.json)
  valuation_score (0-100)  -- from P/S, Forward P/E, PEG   (the added screen)

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


# ---------------- valuation factor (added) ----------------

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


def valuation_score(snap):
    """Blend P/S, Forward P/E, PEG into 0-100. ETFs get a neutral pass (metrics N/A)."""
    if not snap or snap.get("is_etf"):
        return None, {}
    v = SETTINGS["valuation"]
    peg = band_score(snap.get("peg"), v["peg"])
    fpe = band_score(snap.get("forward_pe"), v["forward_pe"])
    ps = band_score(snap.get("price_to_sales"), v["price_to_sales"])

    parts, weights = [], []
    if peg is not None: parts.append(peg); weights.append(0.45)
    if fpe is not None: parts.append(fpe); weights.append(0.35)
    if ps is not None:  parts.append(ps); weights.append(0.20)
    if not parts:
        return None, {"peg": None, "forward_pe": None, "price_to_sales": None}
    total = sum(p * w for p, w in zip(parts, weights)) / sum(weights)
    return round(total, 1), {"peg": peg, "forward_pe": fpe, "price_to_sales": ps}


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
                # valuation
                "valuation_score": val_score,
                "valuation_parts": val_parts,
                "peg": snap.get("peg"),
                "forward_pe": snap.get("forward_pe"),
                "price_to_sales": snap.get("price_to_sales"),
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
