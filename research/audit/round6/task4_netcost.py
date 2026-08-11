"""Task 4: every net-of-cost figure re-run under the corrected cost model.

Annualized cost drag per run and scenario, from the run's actual trades, at two AUMs
(the $100k personal-account case and $10M). Net CAGR = gross CAGR minus drag.
"""
import json
import statistics
import sys
from bisect import bisect_left

import numpy as np

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/pipeline")
from costs import IMPACT_SCENARIOS, SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER

_cache = {}
def series(t):
    if t not in _cache:
        try:
            d = json.load(open(f"{REPO}/pipeline/data/backtest_cache/{t}.json"))
            _cache[t] = (d["dates"], d["closes"], d["volumes"])
        except FileNotFoundError:
            _cache[t] = None
    return _cache[t]

def adv_vol(t, day):
    p = series(t)
    if not p:
        return None, None
    dates, closes, volumes = p
    i = min(bisect_left(dates, day), len(dates) - 1)
    lo = max(0, i - 60)
    wc = [c for c in closes[lo:i + 1] if c]
    wv = [v for v in volumes[lo:i + 1] if v]
    if len(wc) < 20 or len(wv) < 20:
        return None, None
    adv = float(np.median([c * v for c, v in zip(closes[lo:i + 1], volumes[lo:i + 1]) if c and v]))
    rets = np.diff(np.log(wc))
    return adv, float(np.std(rets, ddof=1) * np.sqrt(252))

def spread(adv):
    if adv >= 25e6: return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["liquid"]
    if adv >= 5e6: return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["thin"]
    return SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["illiquid"]

def drag(run, aum, scenario):
    params = IMPACT_SCENARIOS[scenario]
    rebs = json.load(open(run))["portfolio"]["rebalances"]
    prev, total, months = {}, 0.0, 0
    for r in rebs:
        w = {p["ticker"]: p["weight"] for p in r["picks"]}
        cost = 0.0
        for t in set(w) | set(prev):
            frac = abs(w.get(t, 0) - prev.get(t, 0))
            if frac <= 0: continue
            adv, vol = adv_vol(t, r["execution_date"])
            if not adv or not vol: continue
            part = min(1.0, frac * aum / adv)
            imp = params["impact_coefficient"] * vol * np.sqrt(part)
            cost += frac * (imp + spread(adv) / 2 * params["spread_multiplier"]) / 1e4
        total += cost; months += 1; prev = w
    return total / months * 12

RUNS = [("restated baseline", "bt_baseline.json", 0.1259),
        ("restated buffer 1.5", "bt_buffer150.json", 0.1260),
        ("as-filed annual base", "bt_af_base.json", 0.1970),
        ("as-filed stack (1.5)", "bt_af_stack.json", 0.2070)]
print(f"{'run':22s} {'AUM':>6s} {'optimistic(old)':>15s} {'base(canonical)':>15s} {'stress':>8s}   net CAGR at canonical")
for name, f, cagr in RUNS:
    for aum in (1e5, 1e7):
        ds = {s: drag(f"{S}/{f}", aum, s) for s in ("optimistic", "base", "stress")}
        print(f"{name:22s} {'$'+('100k' if aum==1e5 else '10M'):>6s} "
              f"{ds['optimistic']*1e4:13.0f}bp {ds['base']*1e4:13.0f}bp {ds['stress']*1e4:6.0f}bp   "
              f"{(cagr - ds['base'])*100:6.2f}%")
