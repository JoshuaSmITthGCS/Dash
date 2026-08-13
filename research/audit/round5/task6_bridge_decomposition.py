"""Task 6.3 and 6.4: decompose the +1.97pp return-construction bucket of the Round 4
alpha bridge, and align the C-step sample to 58 months.

Components separated:
  explicit transaction costs   per-rebalance "cost" recorded in the committed artifact
  cash drag + compounding + missing-price handling + price-cache drift
                               the remainder, jointly, with the missing-price piece
                               bounded by the artifact's own count (12 days)

The 2026-08-03 price cache was overwritten in place, so the locked picks can only be
re-priced on today's cache. Price-cache drift therefore cannot be separated from the
cash-drag and missing-price pieces with data that still exists. That blocker is stated
in the findings rather than estimated around.
"""
import json
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/research/audit/round3")
sys.path.insert(0, f"{REPO}/research/audit/round4")
from item3_regression import load_factors, monthly_returns  # noqa: E402
from task1_alpha_reconciliation import (run_regression,  # noqa: E402
                                        value_series_monthly_returns)

COMMITTED = f"{REPO}/pipeline/backtest_monthly_results.json"
artifact = json.load(open(COMMITTED))
rebs = artifact["portfolio"]["rebalances"]

# Explicit cost drag per month, from the artifact's own records.
costs = {r["execution_date"][:7].replace("-", ""): r["cost"] / r["portfolio_value"]
         for r in rebs if r.get("portfolio_value")}
annual_cost_drag = 12 * np.mean(list(costs.values()))
print("explicit cost drag from artifact records: %.2f pp/yr (mean %.1f bps/month, n=%d)" % (
    annual_cost_drag * 100, np.mean(list(costs.values())) * 1e4, len(costs)))

ff = load_factors()
vs = value_series_monthly_returns(COMMITTED)
lp = monthly_returns(COMMITTED)

# Task 6.4: align samples. The locked-pick series includes 2021-09, the value-series
# resample drops it as the pct_change seed. Regress both on the identical month set.
common = sorted(set(vs.index) & set(lp.index) & set(ff.index))
vs_a, lp_a = vs[common], lp[common]
print("aligned sample: %d months (%s to %s)" % (len(common), common[0], common[-1]))

A = run_regression(vs_a, ff, maxlags=6, annualization="arithmetic")
C = run_regression(lp_a, ff, maxlags=6, annualization="arithmetic")
lp_net = lp_a - lp_a.index.map(lambda ym: costs.get(ym, 0.0))
C_net = run_regression(pd.Series(lp_net, index=lp_a.index), ff, maxlags=6,
                       annualization="arithmetic")

print("value-series (net, cash drag, old-cache prices):  alpha %+.2f%% (t %+.2f)" % (
    A["alpha_annual_pct"], A["alpha_t"]))
print("locked gross (today-cache prices):               alpha %+.2f%% (t %+.2f)" % (
    C["alpha_annual_pct"], C["alpha_t"]))
print("locked net of recorded costs:                    alpha %+.2f%% (t %+.2f)" % (
    C_net["alpha_annual_pct"], C_net["alpha_t"]))
gap = C["alpha_annual_pct"] - A["alpha_annual_pct"]
cost_part = C["alpha_annual_pct"] - C_net["alpha_annual_pct"]
print("\nconstruction bucket on aligned months: %+.2f pp total" % gap)
print("  explicit costs:                        %+.2f pp" % cost_part)
print("  cash drag + compounding + missing-price handling + price-cache drift (joint): %+.2f pp" % (
    gap - cost_part))
print("  missing-holding-price days recorded in artifact: %d" %
      artifact["portfolio"]["metrics"].get("missing_holding_price_days", -1))
