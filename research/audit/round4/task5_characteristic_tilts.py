"""Task 5: cross-sectional characteristic tilts of the champion score, plus the
minimum detectable effect of the 58-month factor regression.

Characteristic proxies, from pit raw inputs and the price cache:
  size                log market cap
  book-to-market      1 / price_to_book
  operating prof.     gross_profits_to_assets (proxy), profit_margin (proxy)
  investment          asset_growth (the CMA characteristic)
  prior 12-1 return   computed from backtest_cache adjusted closes as of the refresh date

Every statistic reports n. Pinned to pit refresh advisor-2026-08-10T17:22:04.
"""
import json
import math
from bisect import bisect_left

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]


def mom_12_1(ticker, asof="2026-08-10"):
    try:
        d = json.load(open(f"{REPO}/pipeline/data/backtest_cache/{ticker}.json"))
    except FileNotFoundError:
        return None
    dates, closes = d["dates"], d["closes"]
    i = bisect_left(dates, asof)
    i = min(i, len(dates) - 1)
    if i < 252:
        return None
    p_t21, p_t252 = closes[i - 21], closes[i - 252]
    if not p_t21 or not p_t252:
        return None
    return p_t21 / p_t252 - 1


chars = {"log_mcap": [], "book_to_market": [], "gross_prof_assets": [],
         "profit_margin": [], "asset_growth": [], "mom_12_1": []}
scores = {k: [] for k in chars}
for r in rows:
    s = r["scores"]["champion"]
    raw = r.get("raw_metric_inputs") or {}
    if s is None:
        continue
    pairs = {
        "log_mcap": math.log(raw["market_cap"]) if isinstance(raw.get("market_cap"), (int, float)) and raw["market_cap"] > 0 else None,
        "book_to_market": 1.0 / raw["price_to_book"] if isinstance(raw.get("price_to_book"), (int, float)) and raw["price_to_book"] > 0 else None,
        "gross_prof_assets": raw.get("gross_profits_to_assets"),
        "profit_margin": raw.get("profit_margin"),
        "asset_growth": raw.get("asset_growth"),
        "mom_12_1": mom_12_1(r["ticker"]),
    }
    for k, v in pairs.items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            chars[k].append(v)
            scores[k].append(s)

print("champion score vs raw characteristic, Spearman (pinned snapshot):")
for k in chars:
    a, b = np.array(scores[k]), np.array(chars[k])
    rho, p = stats.spearmanr(a, b)
    print(f"  {k:20s} rho {rho:+.3f}  p {p:.1e}  n {len(a)}")

# MDE of the 58-month regression given the observed HAC standard errors.
print("\nminimum detectable loading, 58 months, two-sided 5%:")
for name, se in [("CMA (full model)", 0.300), ("HML", 0.193), ("RMW", 0.205),
                 ("CMA (fund-only)", 0.146)]:
    print(f"  {name:18s} se {se:.3f}  detectable at 50% power {1.96*se:.2f}  at 80% power {2.80*se:.2f}")
