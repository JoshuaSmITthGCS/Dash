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


def lower_is_better_score(value, bands):
    """Score a metric where less is better and negative readings are genuinely good.

    Unlike band_score this never penalizes a negative value, so net cash (negative net
    debt) or a cash-backed negative accrual scores as the strength it actually is.
    """
    if value is None:
        return None
    for key, score in (("excellent_max", 100), ("good_max", 80),
                       ("fair_max", 55), ("poor_max", 30)):
        if value <= bands[key]:
            return float(score)
    return 10.0


def range_score(value, bands):
    """Score a metric where both extremes are bad - under-investment and empire-building alike."""
    if value is None:
        return None
    if bands["ideal_min"] <= value <= bands["ideal_max"]:
        return 100.0
    if bands["acceptable_min"] <= value <= bands["acceptable_max"]:
        return 65.0
    return 25.0


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


# Metrics whose accounting cutoffs are meaningless for banks and insurers. They are skipped
# for those sectors and excluded from coverage rather than counted as missing evidence.
FINANCIAL_EXEMPT = ("price_to_book", "debt_to_equity", "current_ratio", "net_debt_to_ebitda",
                    "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "sales_multiple",
                    "capex_to_depreciation", "inventory_days_trend", "altman_z",
                    "gross_profits_to_assets")

# Price-to-tangible-book is a bank and insurer metric. For an asset-light software company
# whose value is people and code, tangible book is close to an accounting accident, and
# ranking on it is noise dressed as discipline. It is scored only where it means something.
TANGIBLE_BOOK_SECTORS = ("Financial Services", "Financials", "Financial", "Real Estate",
                         "Utilities", "Energy", "Basic Materials", "Materials", "Industrials")


def altman_score(value, variant, cfg):
    """Score an Altman Z against the bands for the variant it was computed under.

    Passing a Z'' through the original model's cutoffs (or the reverse) is the single
    easiest way to mislabel a healthy company as distressed, because the two models put
    their distress thresholds in different places on different scales.
    """
    bands = cfg.get("altman_z", {})
    if value is None or not variant:
        return None
    variant_bands = bands.get(variant)
    if not variant_bands:
        return None
    return higher_is_better_score(value, variant_bands)


def sales_multiple_score(snap, cfg):
    """Score sales valuation, preferring EV/Sales and falling back to P/S.

    EV/Sales is the better measure - it includes debt, so a levered company cannot look
    cheap simply by borrowing - but it needs the balance sheet, which only the enriched
    shortlist has. P/S comes free from the quote payload and covers everyone else.
    Returns ``(score, basis)`` so the output can say which input answered.
    """
    sector = snap.get("sector") or "default"
    enterprise = snap.get("ev_to_sales")
    if enterprise is not None:
        bands = cfg["ev_to_sales_by_sector"].get(sector, cfg["ev_to_sales_by_sector"]["default"])
        return multiple_score(enterprise, bands), "ev_to_sales"
    bands = cfg["price_to_sales_by_sector"].get(sector, cfg["price_to_sales_by_sector"]["default"])
    return multiple_score(snap.get("price_to_sales"), bands), "price_to_sales"


def weighted_coverage(metrics, cfg, exempt=()):
    """Fraction of the total metric weight that was actually answered.

    Weight-aware so a missing minor input barely moves confidence while a missing
    headline input moves it a lot. Sector-exempt metrics leave the denominator entirely.
    """
    answered = total = 0.0
    for category, weights in cfg["metric_weights"].items():
        category_weight = cfg["category_weights"].get(category, 0)
        for metric, weight in weights.items():
            if metric in exempt:
                continue
            share = category_weight * weight
            total += share
            if metrics.get(metric) is not None:
                answered += share
    return answered / total if total else 0.0


def valuation_score(snap):
    """Score valuation, profitability, solvency, growth, capital allocation, and accounting quality.

    ETFs remain unscored because corporate accounting ratios are not comparable to fund holdings.
    Missing values are reweighted, then the final score is confidence-adjusted for data coverage.
    """
    if not snap or snap.get("is_etf"):
        return None, {}
    cfg = SETTINGS["fundamentals"]
    sector = snap.get("sector") or "default"
    is_financial = sector in ("Financial Services", "Financials")
    pe_bands = cfg["forward_pe_by_sector"].get(sector, cfg["forward_pe_by_sector"]["default"])
    sales_score, sales_basis = sales_multiple_score(snap, cfg)
    altman_variant = snap.get("altman_z_variant")

    metrics = {
        # PEG survives as a minor growth-adjusted sanity check only. It ignores the time
        # value of money, risk, and cost of capital, and its support as a return predictor
        # is thin, so it no longer carries the largest weight in the bucket.
        "peg": band_score(snap.get("peg"), cfg["peg"]),
        "forward_pe": multiple_score(snap.get("forward_pe"), pe_bands),
        "sales_multiple": None if is_financial else sales_score,
        # Goodwill makes reported book value meaningless for banks; tangible book replaces it there.
        "price_to_book": None if is_financial else band_score(snap.get("price_to_book"), cfg["price_to_book"]),
        "price_to_tangible_book": (band_score(snap.get("price_to_tangible_book"), cfg["price_to_tangible_book"])
                                   if sector in TANGIBLE_BOOK_SECTORS else None),
        "ev_to_ebitda": None if is_financial else multiple_score(snap.get("ev_to_ebitda"), cfg["ev_to_ebitda"]),
        "ev_to_ebit": None if is_financial else multiple_score(snap.get("ev_to_ebit"), cfg["ev_to_ebit"]),
        "ev_to_fcf": None if is_financial else multiple_score(snap.get("ev_to_fcf"), cfg["ev_to_fcf"]),
        "return_on_equity": higher_is_better_score(snap.get("return_on_equity"), cfg["return_on_equity"]),
        # ROIC is the one ROE should have been: leverage cannot inflate it.
        "return_on_invested_capital": higher_is_better_score(snap.get("return_on_invested_capital"),
                                                             cfg["return_on_invested_capital"]),
        # Gross profits over assets - the cleanest profitability signal in the literature,
        # measured above the line where accounting discretion does its work.
        "gross_profits_to_assets": None if is_financial else higher_is_better_score(
            snap.get("gross_profits_to_assets"), cfg["gross_profits_to_assets"]),
        "cash_conversion": higher_is_better_score(snap.get("cash_conversion"), cfg["cash_conversion"]),
        "free_cash_flow_yield": higher_is_better_score(snap.get("free_cash_flow_yield"), cfg["free_cash_flow_yield"]),
        "profit_margin": higher_is_better_score(snap.get("profit_margin"), cfg["profit_margin"]),
        # Bank balance sheets are structurally leveraged; these industrial-company cutoffs do not apply.
        "debt_to_equity": None if is_financial else band_score(snap.get("debt_to_equity"), cfg["debt_to_equity"]),
        "current_ratio": None if is_financial else higher_is_better_score(snap.get("current_ratio"), cfg["current_ratio"]),
        "interest_coverage": higher_is_better_score(snap.get("interest_coverage"), cfg["interest_coverage"]),
        "net_debt_to_ebitda": None if is_financial else lower_is_better_score(snap.get("net_debt_to_ebitda"),
                                                                             cfg["net_debt_to_ebitda"]),
        "altman_z": None if is_financial else altman_score(snap.get("altman_z"), altman_variant, cfg),
        "revenue_growth": higher_is_better_score(snap.get("revenue_growth"), cfg["revenue_growth"]),
        "earnings_growth": higher_is_better_score(snap.get("earnings_growth"), cfg["earnings_growth"]),
        "fcf_growth_3y": higher_is_better_score(snap.get("fcf_growth_3y"), cfg["fcf_growth_3y"]),
        "operating_margin_trend": higher_is_better_score(snap.get("operating_margin_trend"),
                                                         cfg["operating_margin_trend"]),
        # Fundamental momentum: beating expectations, not merely growing.
        "earnings_surprise": higher_is_better_score(snap.get("earnings_surprise"), cfg["earnings_surprise"]),
        "net_buyback_yield": higher_is_better_score(snap.get("net_buyback_yield"), cfg["net_buyback_yield"]),
        "stock_comp_to_revenue": lower_is_better_score(snap.get("stock_comp_to_revenue"), cfg["stock_comp_to_revenue"]),
        "capex_to_depreciation": range_score(snap.get("capex_to_depreciation"), cfg["capex_to_depreciation"]),
        # The investment factor: aggressive balance-sheet expansion predicts weak returns,
        # and shrinking the asset base is not a virtue either, so both tails are penalized.
        "asset_growth": range_score(snap.get("asset_growth"), cfg["asset_growth"]),
        # Earnings that never become cash are a classic warning, but the anomaly has decayed
        # sharply in US data since 2002, so this is now a minor input rather than the bucket.
        "accruals_ratio": lower_is_better_score(snap.get("accruals_ratio"), cfg["accruals_ratio"]),
        "piotroski_f": higher_is_better_score(snap.get("piotroski_f"), cfg["piotroski_f"]),
        "days_sales_outstanding_trend": lower_is_better_score(snap.get("days_sales_outstanding_trend"),
                                                              cfg["days_sales_outstanding_trend"]),
        "inventory_days_trend": lower_is_better_score(snap.get("inventory_days_trend"), cfg["inventory_days_trend"]),
    }
    categories = {}
    for category, weights in cfg["metric_weights"].items():
        value = weighted_available(metrics, weights)
        categories[category] = round(value, 1) if value is not None else None
    raw = weighted_available(categories, cfg["category_weights"])
    if raw is None:
        return None, {**metrics, "categories": categories, "coverage": 0.0}
    exempt = list(FINANCIAL_EXEMPT) if is_financial else []
    if sector not in TANGIBLE_BOOK_SECTORS:
        exempt.append("price_to_tangible_book")
    coverage = weighted_coverage(metrics, cfg, tuple(exempt))
    confidence_multiplier = 0.65 + (0.35 * coverage)
    total = round(raw * confidence_multiplier, 1)
    return total, {**metrics, "categories": categories, "coverage": round(coverage, 2),
                   "raw_score": round(raw, 1), "sector": sector,
                   "sales_multiple_basis": sales_basis if sales_score is not None else None,
                   "altman_z_variant": altman_variant}


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
