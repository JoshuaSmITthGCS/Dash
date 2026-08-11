"""Task 4: capacity estimate. At what AUM does modeled market impact consume the edge?

Uses the as-filed construction-stack run's actual trades (buffer 1.5, top 20). For every
rebalance, the traded dollars per name at a hypothetical AUM are pushed through the
existing square-root impact model (pipeline/costs.py, base scenario): impact_bps =
15 * annualized_vol * sqrt(participation), participation = trade dollars / 60-day median
daily dollar volume, one-day execution assumed, both legs charged. The spread and fee
terms are charged at the model's liquidity-tiered proxy. The proxy caveat stands: no
provider serves real spreads, so the spread floor is labeled, and this capacity curve is
a statement about the impact term, which dominates at scale.
"""
import json
import sys
from bisect import bisect_left

import numpy as np

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/pipeline")
from costs import IMPACT_SCENARIOS, SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER  # noqa: E402

run = json.load(open(f"{S}/bt_af_stack.json"))
rebs = run["portfolio"]["rebalances"]

_cache = {}


def series(ticker):
    if ticker not in _cache:
        try:
            d = json.load(open(f"{REPO}/pipeline/data/backtest_cache/{ticker}.json"))
            _cache[ticker] = (d["dates"], d["closes"], d["volumes"])
        except FileNotFoundError:
            _cache[ticker] = None
    return _cache[ticker]


def adv_and_vol(ticker, day):
    p = series(ticker)
    if not p:
        return None, None
    dates, closes, volumes = p
    i = min(bisect_left(dates, day), len(dates) - 1)
    lo = max(0, i - 60)
    window_close = [c for c in closes[lo:i + 1] if c]
    window_vol = [v for v in volumes[lo:i + 1] if v]
    if len(window_close) < 20 or len(window_vol) < 20:
        return None, None
    dollar = float(np.median([c * v for c, v in zip(closes[lo:i + 1], volumes[lo:i + 1])
                              if c and v]))
    rets = np.diff(np.log(window_close))
    vol = float(np.std(rets, ddof=1) * np.sqrt(252))
    return dollar, vol


def spread_bps(adv):
    if adv >= 25_000_000:
        return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["liquid"]
    if adv >= 5_000_000:
        return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["thin"]
    return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["illiquid"]


coef = IMPACT_SCENARIOS["base"]["impact_coefficient"]

# Reconstruct per-name trade fractions per rebalance from consecutive pick weights.
prev = {}
monthly_cost_frac = []  # cost as fraction of AUM at AUM=1 (impact scales, spread does not)


def month_cost(aum):
    global prev
    prev = {}
    total = 0.0
    months = 0
    for r in rebs:
        w = {p["ticker"]: p["weight"] for p in r["picks"]}
        traded = {t: abs(w.get(t, 0) - prev.get(t, 0)) for t in set(w) | set(prev)}
        cost = 0.0
        for t, frac in traded.items():
            if frac <= 0:
                continue
            adv, vol = adv_and_vol(t, r["execution_date"])
            if not adv or not vol:
                continue
            trade_dollars = frac * aum
            participation = min(1.0, trade_dollars / adv)
            impact = coef * vol * np.sqrt(participation)
            half_spread = spread_bps(adv) / 2
            cost += frac * (impact + half_spread) / 1e4
        total += cost
        months += 1
        prev = w
    return total / months * 12  # annualized cost as fraction of AUM


print("annualized modeled cost (base scenario, one-day execution) by AUM, as-filed stack "
      "(top 20, buffer 1.5, mean one-way turnover %.1f%%/mo):" %
      (np.mean([x["turnover"] for x in rebs[1:]]) * 100))
for aum in (1e6, 1e7, 5e7, 1e8, 2.5e8, 5e8, 1e9, 2e9):
    c = month_cost(aum)
    print(f"  AUM ${aum/1e6:7.0f}M  cost {c*1e4:7.0f} bps/yr")

# Crossing points.
lo_target = [50, 100, 200]
for target in lo_target:
    lo_aum, hi_aum = 1e6, 5e9
    for _ in range(40):
        mid = (lo_aum * hi_aum) ** 0.5
        if month_cost(mid) * 1e4 > target:
            hi_aum = mid
        else:
            lo_aum = mid
    print(f"cost crosses {target} bps/yr at AUM ~ ${hi_aum/1e6:,.0f}M")
