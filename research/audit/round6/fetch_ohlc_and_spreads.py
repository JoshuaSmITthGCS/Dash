"""Task 4: unblock spread measurement. Fetch daily OHLC into a NEW cache directory
(pipeline/data/ohlc_cache, never mutating the pinned backtest_cache), then estimate
effective spreads with the Corwin-Schultz high-low estimator (Journal of Finance 67(2),
2012) and compare against the labeled liquidity-tier proxy.

Usage: fetch_ohlc_and_spreads.py [n_tickers]
Default 120 names sampled across liquidity tiers, enough to fit the proxy. The full-universe
backfill is the same command with 860.
"""
import json
import math
import os
import random
import sys
import time

import numpy as np

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")
OHLC_DIR = f"{REPO}/pipeline/data/ohlc_cache"
os.makedirs(OHLC_DIR, exist_ok=True)

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 120

import yfinance as yf  # noqa: E402

cache_tickers = sorted(f[:-5] for f in os.listdir(f"{REPO}/pipeline/data/backtest_cache")
                       if f.endswith(".json"))
random.Random(11).shuffle(cache_tickers)
tickers = cache_tickers[:limit]

fetched = 0
for t in tickers:
    out = os.path.join(OHLC_DIR, f"{t}.json")
    if os.path.exists(out):
        fetched += 1
        continue
    try:
        h = yf.Ticker(t).history(period="1y", auto_adjust=False)
        if h is None or h.empty:
            continue
        json.dump({"ticker": t,
                   "dates": [d.strftime("%Y-%m-%d") for d in h.index],
                   "high": [round(float(x), 4) for x in h["High"]],
                   "low": [round(float(x), 4) for x in h["Low"]],
                   "close": [round(float(x), 4) for x in h["Close"]],
                   "volume": [int(x) for x in h["Volume"]]},
                  open(out, "w"))
        fetched += 1
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.4)
print(f"OHLC cached for {fetched}/{len(tickers)} sampled tickers")


def corwin_schultz(high, low):
    """Two-day high-low spread estimator, negative estimates floored at zero per CS."""
    spreads = []
    for i in range(1, len(high)):
        if not all(v and v > 0 for v in (high[i], low[i], high[i - 1], low[i - 1])):
            continue
        beta = (math.log(high[i] / low[i]) ** 2
                + math.log(high[i - 1] / low[i - 1]) ** 2)
        h2, l2 = max(high[i], high[i - 1]), min(low[i], low[i - 1])
        gamma = math.log(h2 / l2) ** 2
        alpha = ((math.sqrt(2 * beta) - math.sqrt(beta)) / (3 - 2 * math.sqrt(2))
                 - math.sqrt(gamma / (3 - 2 * math.sqrt(2))))
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        spreads.append(max(s, 0.0))
    return float(np.mean(spreads)) * 1e4 if spreads else None  # bps


from costs import SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER, liquidity_tier  # noqa: E402

rows = []
for f in os.listdir(OHLC_DIR):
    d = json.load(open(os.path.join(OHLC_DIR, f)))
    cs = corwin_schultz(d["high"], d["low"])
    if cs is None:
        continue
    dollar = float(np.median([c * v for c, v in zip(d["close"], d["volume"]) if c and v]))
    rows.append((d["ticker"], liquidity_tier(dollar), cs))

by_tier = {}
for _t, tier, cs in rows:
    by_tier.setdefault(tier, []).append(cs)
print("\nCorwin-Schultz estimated FULL spread (bps) vs labeled proxy, by liquidity tier:")
for tier in ("liquid", "thin", "illiquid"):
    vals = by_tier.get(tier, [])
    if not vals:
        print(f"  {tier:9s} n=0")
        continue
    print(f"  {tier:9s} n={len(vals):3d}  median {np.median(vals):6.1f}  "
          f"p25 {np.percentile(vals,25):6.1f}  p75 {np.percentile(vals,75):6.1f}  "
          f"labeled proxy {SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER[tier]:5.1f}")
