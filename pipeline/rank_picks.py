"""
rank_picks.py
Blend political_score + valuation_score + context into three research buckets and
print a ranked list. Writes picks.json for the dashboard's Picks page.

Buckets:
  SHORT TERM   -> catalyst/momentum driven. Weights the political signal + recent price move.
                  Valuation matters least; a hot policy catalyst can run regardless of PEG.
  LONG TERM    -> quality at a fair price. Weights broad fundamentals + political signal.
  RETIREMENT   -> broad/low-maintenance. ETFs and large-cap stability first. Political signal
     / BROAD      barely matters; this bucket is about diversification and cost.

NOTHING here is a buy instruction. Labels are research tiers. Congressional data lags 30-45 days.
"""

from datetime import datetime, timezone

from common import LOG, data_mode, load_json, save_json, update_pipeline_status

SETTINGS = load_json("settings.json", from_config=True) or {}
UNIVERSE = load_json("universe.json", from_config=True) or {}
BW = SETTINGS["bucket_weights"]
LIMITS = SETTINGS["bucket_limits"]


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def momentum_score(pct_30d):
    """Recent price move -> 0-100. Rewards positive momentum, caps runaway spikes."""
    if pct_30d is None:
        return 50.0
    return clamp(50 + pct_30d * 2.5)


ETF_CATEGORY = {tk: meta.get("category") for tk, meta in UNIVERSE.get("etfs", {}).items()}
# Diversification value of each ETF type for a retirement/broad sleeve.
CATEGORY_STABILITY = {
    "broad_market": 95, "international": 85, "dividend": 88, "bonds": 82,
    "growth": 72, "sector": 55, "crypto": 25,
}


def stability_score(sig):
    """
    Retirement/broad is about diversification + low maintenance, so a total-market
    fund should out-anchor any single stock. ETFs score on their category; single
    stocks earn stability only through large-cap size + dividend + non-frothy valuation.
    """
    if sig.get("is_etf"):
        cat = ETF_CATEGORY.get(sig["ticker"], "sector")
        base = CATEGORY_STABILITY.get(cat, 60)
        er = sig.get("expense_ratio")
        if er is not None and er <= 0.10:  # cheap fund bonus
            base += 3
        return clamp(base)
    # single stock
    s = 30.0
    mc = sig.get("market_cap") or 0
    if mc > 200e9: s += 28
    elif mc > 50e9: s += 18
    elif mc > 10e9: s += 8
    dy = sig.get("dividend_yield") or 0
    if dy > 0.03: s += 16
    elif dy > 0.02: s += 10
    ps = sig.get("price_to_sales")
    if ps is not None and ps > 15: s -= 15  # frothy, not retirement-appropriate
    return clamp(s, hi=72.0)  # a single stock never out-anchors a diversified fund


def quality_score(sig):
    """Profitability and growth quality used in the long-term blend."""
    categories = sig.get("fundamental_categories") or {}
    available = [categories.get(k) for k in ("profitability", "growth") if categories.get(k) is not None]
    if available:
        return round(sum(available) / len(available), 1)
    return 50.0


def val_or(sig, default=50.0):
    v = sig.get("valuation_score")
    return v if v is not None else default


def composite(sig, bucket):
    w = BW[bucket]
    pol = sig.get("political_score", 0)
    val = val_or(sig)
    if bucket == "short_term":
        extra = momentum_score(sig.get("pct_30d")) * w["momentum"]
        return round(pol * w["signal"] + val * w["valuation"] + extra, 1)
    if bucket == "long_term":
        extra = quality_score(sig) * w["quality"]
        return round(pol * w["signal"] + val * w["valuation"] + extra, 1)
    # retirement
    extra = stability_score(sig) * w["stability"]
    return round(pol * w["signal"] + val * w["valuation"] + extra, 1)


def tier(score):
    lb = SETTINGS["labels"]
    if score >= lb["high_conviction_min"]:
        return "HIGH CONVICTION"
    if score >= lb["watch_min"]:
        return "WATCH"
    if score >= lb["neutral_min"]:
        return "NEUTRAL"
    return "LOW"


def enrich(sig, bucket, score):
    return {
        "ticker": sig["ticker"],
        "name": sig.get("name"),
        "sector": sig.get("sector"),
        "is_etf": sig.get("is_etf", False),
        "bucket_score": score,
        "tier": tier(score),
        "political_score": sig.get("political_score"),
        "valuation_score": sig.get("valuation_score"),
        "fundamental_categories": sig.get("fundamental_categories", {}),
        "fundamental_coverage": sig.get("fundamental_coverage"),
        "peg": sig.get("peg"),
        "forward_pe": sig.get("forward_pe"),
        "price_to_sales": sig.get("price_to_sales"),
        "price_to_book": sig.get("price_to_book"),
        "return_on_equity": sig.get("return_on_equity"),
        "free_cash_flow_yield": sig.get("free_cash_flow_yield"),
        "debt_to_equity": sig.get("debt_to_equity"),
        "current_ratio": sig.get("current_ratio"),
        "profit_margin": sig.get("profit_margin"),
        "revenue_growth": sig.get("revenue_growth"),
        "earnings_growth": sig.get("earnings_growth"),
        "pct_30d": sig.get("pct_30d"),
        "dividend_yield": sig.get("dividend_yield"),
        "price": sig.get("price"),
        "cluster_size": sig.get("cluster_size"),
        "filing_lag_days": sig.get("filing_lag_days"),
        "why": reason(sig, bucket),
    }


def reason(sig, bucket):
    bits = []
    if sig.get("cluster_size", 0) >= 3:
        bits.append(f"{sig['cluster_size']} members buying")
    elif sig.get("cluster_size", 0) == 2:
        bits.append("2 members buying")
    peg = sig.get("peg")
    if bucket in ("long_term",) and peg is not None and 0 < peg <= 1.5:
        bits.append(f"PEG {peg}")
    roe = sig.get("return_on_equity")
    if bucket == "long_term" and roe is not None and roe >= 0.15:
        bits.append(f"ROE {roe*100:.0f}%")
    if bucket == "short_term" and sig.get("pct_30d") is not None:
        bits.append(f"{sig['pct_30d']:+.1f}% 30d")
    if bucket == "retirement" and sig.get("is_etf"):
        bits.append("diversified ETF")
    dy = sig.get("dividend_yield")
    if bucket == "retirement" and dy:
        bits.append(f"{dy*100:.1f}% yield")
    return ", ".join(bits) or "signal present"


def add_retirement_core(signals_by_ticker, prices):
    """Seed retirement bucket with diversified core ETFs even without congressional activity."""
    core = []
    for tk in UNIVERSE.get("retirement_core", []):
        snap = prices.get(tk, {})
        etf_meta = UNIVERSE.get("etfs", {}).get(tk, {})
        core.append({
            "ticker": tk,
            "name": snap.get("name") or etf_meta.get("name", tk),
            "sector": etf_meta.get("category", "ETF"),
            "is_etf": True,
            "political_score": signals_by_ticker.get(tk, {}).get("political_score", 0),
            "valuation_score": None,
            "peg": None, "forward_pe": None, "price_to_sales": None, "price_to_book": None,
            "return_on_equity": None, "free_cash_flow_yield": None,
            "debt_to_equity": None, "current_ratio": None,
            "profit_margin": None, "revenue_growth": None, "earnings_growth": None,
            "fundamental_categories": {}, "fundamental_coverage": None,
            "pct_30d": snap.get("pct_30d"),
            "dividend_yield": snap.get("dividend_yield"),
            "price": snap.get("price"),
            "market_cap": snap.get("market_cap"),
            "cluster_size": 0,
            "filing_lag_days": None,
            "expense_ratio": etf_meta.get("expense_ratio"),
        })
    return core


def build():
    sig_payload = load_json("signals.json") or {}
    signals = sig_payload.get("signals", [])
    price_payload = load_json("prices.json") or {}
    prices = price_payload.get("prices", {})
    by_ticker = {s["ticker"]: s for s in signals}

    # SHORT: signal-driven, needs a real political signal to qualify
    short_pool = [s for s in signals if s.get("political_score", 0) >= 30]
    short = sorted(
        (enrich(s, "short_term", composite(s, "short_term")) for s in short_pool),
        key=lambda x: x["bucket_score"], reverse=True
    )[:LIMITS["short_term"]]

    # LONG: needs a valuation reading + decent signal
    long_pool = [s for s in signals if s.get("valuation_score") is not None and s.get("political_score", 0) >= 20]
    long = sorted(
        (enrich(s, "long_term", composite(s, "long_term")) for s in long_pool),
        key=lambda x: x["bucket_score"], reverse=True
    )[:LIMITS["long_term"]]

    # RETIREMENT: core ETFs + any ETF/large-cap that showed congressional interest
    retire_pool = add_retirement_core(by_ticker, prices)
    seen = {r["ticker"] for r in retire_pool}
    for s in signals:
        if (s.get("is_etf") or (s.get("market_cap") or 0) > 50e9) and s["ticker"] not in seen:
            retire_pool.append(s)
            seen.add(s["ticker"])
    retire = sorted(
        (enrich(s, "retirement", composite(s, "retirement")) for s in retire_pool),
        key=lambda x: x["bucket_score"], reverse=True
    )[:LIMITS["retirement"]]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": data_mode(sig_payload, price_payload),
        "disclaimer": "Research candidates only. Not financial advice. Congressional disclosures lag 30-45 days.",
        "buckets": {
            "short_term": short,
            "long_term": long,
            "retirement": retire,
        },
    }
    save_json("picks.json", payload)
    update_pipeline_status("ranking", status="healthy", source="local ranking engine",
                           details={k: len(v) for k, v in payload["buckets"].items()})
    return payload


def print_bucket(title, rows):
    print(f"\n{'='*72}\n {title}\n{'='*72}")
    if not rows:
        print("  (no qualifying candidates in current data)")
        return
    print(f"  {'#':<3}{'TICKER':<8}{'TIER':<17}{'SCORE':<7}{'PEG':<7}{'FwdPE':<8}{'P/S':<7}{'WHY'}")
    print(f"  {'-'*100}")
    for i, r in enumerate(rows, 1):
        peg = f"{r['peg']}" if r.get("peg") is not None else "-"
        fpe = f"{r['forward_pe']}" if r.get("forward_pe") is not None else "-"
        ps = f"{r['price_to_sales']}" if r.get("price_to_sales") is not None else "-"
        print(f"  {i:<3}{r['ticker']:<8}{r['tier']:<17}{r['bucket_score']:<7}{peg:<7}{fpe:<8}{ps:<7}{r['why']}")


def main():
    payload = build()
    b = payload["buckets"]
    print_bucket("SHORT TERM  (catalyst / momentum -- research candidates)", b["short_term"])
    print_bucket("LONG TERM   (quality at a fair price -- research candidates)", b["long_term"])
    print_bucket("RETIREMENT / BROAD  (diversified, low-maintenance)", b["retirement"])
    print(f"\n  {payload['disclaimer']}\n")
    LOG.info("Wrote picks.json")


if __name__ == "__main__":
    main()
