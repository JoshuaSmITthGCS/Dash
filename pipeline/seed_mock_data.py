"""
seed_mock_data.py
Generates realistic MOCK trades.json / prices.json / news.json / politicians.json
matching the exact schemas the real fetch scripts produce. Lets you run scorer.py and
rank_picks.py end-to-end WITHOUT network access (e.g. in a sandbox) to verify the engine.

In production you never run this -- the real fetch_*.py scripts write these files.
Usage:  python seed_mock_data.py   then   python scorer.py && python rank_picks.py
"""

import random
from datetime import datetime, timezone, timedelta

from common import save_json, normalize_name

random.seed(7)
TODAY = datetime.now(timezone.utc).date()


def d(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


# (politician, chamber, party, state) roster drawn from committees.json names
ROSTER = [
    ("Nancy Pelosi", "House", "D", "CA"),
    ("Michael McCaul", "House", "R", "TX"),
    ("Ro Khanna", "House", "D", "CA"),
    ("Josh Gottheimer", "House", "D", "NJ"),
    ("Dan Crenshaw", "House", "R", "TX"),
    ("Tommy Tuberville", "Senate", "R", "AL"),
    ("Markwayne Mullin", "Senate", "R", "OK"),
    ("Sheldon Whitehouse", "Senate", "D", "RI"),
    ("Marjorie Taylor Greene", "House", "R", "GA"),
    ("Rick Scott", "Senate", "R", "FL"),
]

# ticker -> realistic-ish valuation snapshot (price, sector, mcap, ps, fwd_pe, peg, growth, div)
FUND = {
    "NVDA": dict(price=178, sector="Technology", mc=4.3e12, ps=28.5, fpe=34, peg=1.2, gr=0.42, dy=0.0003),
    "LMT":  dict(price=470, sector="Industrials", mc=112e9, ps=1.7, fpe=17, peg=1.9, gr=0.06, dy=0.027),
    "RTX":  dict(price=128, sector="Industrials", mc=170e9, ps=2.1, fpe=20, peg=1.6, gr=0.08, dy=0.021),
    "COIN": dict(price=245, sector="Financials", mc=61e9, ps=9.4, fpe=38, peg=0.9, gr=0.55, dy=0.0),
    "MSTR": dict(price=380, sector="Technology", mc=95e9, ps=88.0, fpe=None, peg=None, gr=None, dy=0.0),
    "XOM":  dict(price=118, sector="Energy", mc=470e9, ps=1.3, fpe=12, peg=1.1, gr=0.04, dy=0.033),
    "NUE":  dict(price=140, sector="Materials", mc=32e9, ps=1.1, fpe=13, peg=0.8, gr=0.10, dy=0.016),
    "GEO":  dict(price=27, sector="Industrials", mc=3.6e9, ps=1.5, fpe=15, peg=0.7, gr=0.12, dy=0.0),
    "MU":   dict(price=115, sector="Technology", mc=128e9, ps=4.2, fpe=11, peg=0.5, gr=0.60, dy=0.004),
    "JPM":  dict(price=245, sector="Financials", mc=690e9, ps=3.6, fpe=13, peg=1.7, gr=0.05, dy=0.021),
    "UNH":  dict(price=520, sector="Healthcare", mc=480e9, ps=1.2, fpe=16, peg=1.3, gr=0.11, dy=0.016),
    "DJT":  dict(price=32, sector="Communication", mc=6.8e9, ps=680.0, fpe=None, peg=None, gr=None, dy=0.0),
    "AMD":  dict(price=168, sector="Technology", mc=272e9, ps=11.0, fpe=28, peg=1.4, gr=0.30, dy=0.0),
    # ETFs
    "VTI":  dict(price=295, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.013, etf=True),
    "VOO":  dict(price=545, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.013, etf=True),
    "SCHD": dict(price=28, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.036, etf=True),
    "VXUS": dict(price=68, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.031, etf=True),
    "QQQ":  dict(price=520, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.006, etf=True),
    "BND":  dict(price=73, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.038, etf=True),
    "ITA":  dict(price=155, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.010, etf=True),
    "SMH":  dict(price=270, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.004, etf=True),
    "XLE":  dict(price=92, sector="ETF", mc=0, ps=None, fpe=None, peg=None, gr=None, dy=0.032, etf=True),
}

AMOUNT_RANGES = [
    ("$1,001 - $15,000", 8000),
    ("$15,001 - $50,000", 32500),
    ("$50,001 - $100,000", 75000),
    ("$250,001 - $500,000", 375000),
    ("$500,001 - $1,000,000", 750000),
]


def make_trades():
    trades = []
    # engineered clusters: NVDA (4 buyers), RTX (3 buyers), COIN (2 buyers)
    scripted = [
        ("NVDA", ["Nancy Pelosi", "Michael McCaul", "Ro Khanna", "Josh Gottheimer"], "buy", 3),
        ("RTX",  ["Michael McCaul", "Ro Khanna", "Markwayne Mullin"], "buy", 2),
        ("LMT",  ["Michael McCaul", "Tommy Tuberville"], "buy", 4),
        ("COIN", ["Josh Gottheimer", "Nancy Pelosi"], "buy", 5),
        ("MU",   ["Michael McCaul"], "buy", 6),
        ("NUE",  ["Tommy Tuberville"], "buy", 3),
        ("GEO",  ["Marjorie Taylor Greene"], "buy", 8),
        ("XOM",  ["Sheldon Whitehouse", "Dan Crenshaw"], "buy", 10),
        ("DJT",  ["Marjorie Taylor Greene"], "buy", 12),
        ("UNH",  ["Rick Scott"], "buy", 5),
        ("AMD",  ["Nancy Pelosi"], "buy", 20),
        # selling cluster -> cooling list
        ("JPM",  ["Dan Crenshaw", "Rick Scott"], "sell", 6),
    ]
    lut = {r[0]: r for r in ROSTER}
    for ticker, pols, ttype, trade_ago in scripted:
        for pol in pols:
            chamber, party, state = lut[pol][1], lut[pol][2], lut[pol][3]
            rng = random.choice(AMOUNT_RANGES[1:]) if ticker in ("NVDA", "LMT", "RTX") else random.choice(AMOUNT_RANGES)
            filing_ago = max(0, trade_ago - random.randint(25, 40))
            trades.append({
                "politician": normalize_name(pol),
                "chamber": chamber, "party": party, "state": state,
                "ticker": ticker,
                "asset": f"{ticker} Common Stock",
                "type": ttype,
                "amount_range": rng[0], "amount_mid": rng[1],
                "trade_date": d(trade_ago),
                "filing_date": d(filing_ago),
                "filing_lag_days": trade_ago - filing_ago,
                "source": "mock",
            })
    return trades


def make_prices():
    prices = {}
    for tk, f in FUND.items():
        is_etf = f.get("etf", False)
        if is_etf:
            pb = roe = fcf_yield = debt_to_equity = current_ratio = profit_margin = revenue_growth = None
            free_cash_flow = None
        else:
            pb = round(max(0.7, min(18, (f["ps"] or 2) * random.uniform(0.7, 1.6))), 2)
            roe = round(random.uniform(0.07, 0.30), 4)
            fcf_yield = round(random.uniform(0.015, 0.085), 4)
            debt_to_equity = round(random.uniform(0.15, 1.8), 2)
            current_ratio = round(random.uniform(0.85, 2.4), 2)
            profit_margin = round(random.uniform(0.05, 0.28), 4)
            revenue_growth = round(f["gr"] if f["gr"] is not None else random.uniform(-0.08, 0.12), 4)
            free_cash_flow = round(f["mc"] * fcf_yield) if f["mc"] else None
        if tk in ("DJT", "MSTR"):
            roe, fcf_yield, profit_margin = -0.12, -0.03, -0.18
            free_cash_flow = round(f["mc"] * fcf_yield)
        prices[tk] = {
            "ticker": tk,
            "name": f"{tk}",
            "price": f["price"],
            "pct_30d": round(random.uniform(-8, 14), 2),
            "sector": f["sector"],
            "market_cap": f["mc"],
            "dividend_yield": f["dy"],
            "is_etf": is_etf,
            "price_to_sales": f["ps"],
            "price_to_book": pb,
            "forward_pe": f["fpe"],
            "trailing_pe": f["fpe"] * 1.15 if f["fpe"] else None,
            "peg": f["peg"],
            "return_on_equity": roe,
            "free_cash_flow": free_cash_flow,
            "free_cash_flow_yield": fcf_yield,
            "debt_to_equity": debt_to_equity,
            "current_ratio": current_ratio,
            "profit_margin": profit_margin,
            "revenue_growth": revenue_growth,
            "earnings_growth": f["gr"],
        }
    # engineer some momentum for short-term demo
    prices["NVDA"]["pct_30d"] = 11.4
    prices["MU"]["pct_30d"] = 9.1
    prices["COIN"]["pct_30d"] = 13.8
    prices["GEO"]["pct_30d"] = 6.2
    return prices


def make_news():
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "demo",
        "count": 3,
        "feed_health": [
            {"name": "Demo feed", "url": "", "status": "demo", "entries": 3},
        ],
        "flagged_sectors": {"semiconductors": 4, "defense": 3, "crypto": 2, "energy_oil": 1},
        "flagged_tickers": {
            "NVDA": "semiconductors", "AMD": "semiconductors", "MU": "semiconductors", "SMH": "semiconductors",
            "LMT": "defense", "RTX": "defense", "ITA": "defense",
            "COIN": "crypto", "MSTR": "crypto",
            "XOM": "energy_oil", "XLE": "energy_oil",
        },
        "items": [
            {"title": "Demo: export controls tighten chip bans", "source": "Demo feed",
             "url": "", "published": d(1), "flags": [{"sector": "semiconductors", "keyword": "export control", "tickers": ["NVDA", "AMD", "MU"]}]},
            {"title": "Demo: defense budget adds missile funding", "source": "Demo feed",
             "url": "", "published": d(2), "flags": [{"sector": "defense", "keyword": "defense budget", "tickers": ["LMT", "RTX"]}]},
            {"title": "Demo: digital asset ETF policy moves", "source": "Demo feed",
             "url": "", "published": d(2), "flags": [{"sector": "crypto", "keyword": "etf approval", "tickers": ["COIN"]}]},
        ],
    }


def make_politicians():
    # mock track records -> percentile drives track_record factor
    lb = [
        {"politician": normalize_name("Nancy Pelosi"), "n_buys_scored": 22, "avg_90d_alpha": 14.3},
        {"politician": normalize_name("Michael McCaul"), "n_buys_scored": 18, "avg_90d_alpha": 9.7},
        {"politician": normalize_name("Ro Khanna"), "n_buys_scored": 15, "avg_90d_alpha": 6.1},
        {"politician": normalize_name("Josh Gottheimer"), "n_buys_scored": 12, "avg_90d_alpha": 4.4},
        {"politician": normalize_name("Markwayne Mullin"), "n_buys_scored": 9, "avg_90d_alpha": 2.0},
        {"politician": normalize_name("Tommy Tuberville"), "n_buys_scored": 20, "avg_90d_alpha": 1.2},
        {"politician": normalize_name("Dan Crenshaw"), "n_buys_scored": 8, "avg_90d_alpha": -0.5},
        {"politician": normalize_name("Rick Scott"), "n_buys_scored": 7, "avg_90d_alpha": -1.8},
        {"politician": normalize_name("Sheldon Whitehouse"), "n_buys_scored": 6, "avg_90d_alpha": -3.0},
        {"politician": normalize_name("Marjorie Taylor Greene"), "n_buys_scored": 10, "avg_90d_alpha": -4.2},
    ]
    n = len(lb)
    for i, row in enumerate(lb):
        row["percentile"] = round(100 * (n - i) / n, 1)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "data_mode": "demo",
            "count": n, "leaderboard": lb}


def main():
    trades = make_trades()
    save_json("trades.json", {"generated_at": datetime.now(timezone.utc).isoformat(),
                              "data_mode": "demo", "source": "generated demo fixtures",
                              "lookback_days": 90, "history_count": len(trades),
                              "count": len(trades), "trades": trades})
    save_json("prices.json", {"generated_at": datetime.now(timezone.utc).isoformat(),
                              "data_mode": "demo", "count": len(FUND), "prices": make_prices()})
    save_json("news.json", make_news())
    save_json("politicians.json", make_politicians())
    now = datetime.now(timezone.utc).isoformat()
    save_json("status.json", {
        "generated_at": now,
        "status": "degraded",
        "stages": {
            "demo_seed": {
                "status": "degraded", "checked_at": now,
                "source": "generated demo fixtures",
                "message": "Demo data is active; live deployment is blocked",
            },
        },
    })
    print("Mock data written: trades.json, prices.json, news.json, politicians.json")


if __name__ == "__main__":
    main()
