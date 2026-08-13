"""Task 1: reconcile published -2.57% alpha vs Round 3's +0.43%, and 64.9% vs 50.6% turnover.

The published figure comes from pipeline/p0_q1_benchmark_factor_report.py run against the
committed pipeline/backtest_monthly_results.json (generated 2026-08-03). Round 3's figure
comes from research/audit/round3/item3_regression.py against a fresh 2026-08-10 cache run.

This script bridges the gap in four controlled steps, changing one thing at a time:
  A. Reproduce the published construction exactly (value-series returns, HAC lag 3,
     geometric annualization, french.json factors) on the committed artifact.
  B. Same committed artifact, Round 3's estimator (statsmodels HAC lag 6, arithmetic
     annualization, zip factors). Isolates estimator differences.
  C. Committed artifact's locked picks re-priced gross from the price cache with Round 3's
     return construction. Isolates return-path differences (net-of-cost value series with
     cash drag vs gross locked-pick returns).
  D. Round 3's baseline run (2026-08-10 cache), same construction as C. Isolates cache state.

Turnover reconciliation: per-rebalance turnover series of the committed 2026-08-03 artifact
vs the 2026-08-10 rerun, with pick-overlap and first-divergence date.
"""
import json
import sys
from bisect import bisect_left

import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import load_factors, monthly_returns, prices, price_on_or_before  # noqa: E402

COMMITTED = f"{REPO}/pipeline/backtest_monthly_results.json"
ROUND3 = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad/bt_baseline.json"


def value_series_monthly_returns(run_path):
    """Month-end resample of the daily portfolio value series, the published construction."""
    hist = json.load(open(run_path))["portfolio"]["history"]
    s = pd.Series({h["date"]: h["value"] for h in hist})
    s.index = pd.to_datetime(s.index)
    monthly = s.resample("ME").last()
    rets = monthly.pct_change().dropna()
    rets.index = rets.index.strftime("%Y%m")
    return rets


def french_json_factors():
    d = json.load(open(f"{REPO}/public/data/factors/french.json"))
    obs = d["observations"]
    df = pd.DataFrame(obs)
    month_key = "month" if "month" in df.columns else df.columns[0]
    df["ym"] = df[month_key].str.replace("-", "")
    df = df.set_index("ym")
    ren = {"market_excess": "MktRF", "size": "SMB", "value": "HML",
           "profitability": "RMW", "investment": "CMA", "momentum": "MOM",
           "risk_free": "RF", "mkt_rf": "MktRF", "smb": "SMB", "hml": "HML",
           "rmw": "RMW", "cma": "CMA", "mom": "MOM", "rf": "RF"}
    df = df.rename(columns={c: ren[c] for c in df.columns if c in ren})
    cols = ["MktRF", "SMB", "HML", "RMW", "CMA", "RF", "MOM"]
    df = df[[c for c in cols if c in df.columns]].astype(float)
    if df.abs().max().max() > 1.5:
        df = df / 100.0
    return df


def run_regression(rets, ff, maxlags, annualization):
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    a = m.params["const"]
    ann = ((1 + a) ** 12 - 1) * 100 if annualization == "geometric" else a * 12 * 100
    return {"n": len(df), "alpha_monthly": a, "alpha_annual_pct": ann,
            "alpha_t": m.tvalues["const"],
            "betas": {f: (m.params[f], m.tvalues[f]) for f in
                      ["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]}}


def summarize(label, r):
    print(f"{label:74s} alpha {r['alpha_annual_pct']:+6.2f}%/yr  t {r['alpha_t']:+5.2f}  n {r['n']}")


ff_json = french_json_factors()
ff_zip = load_factors()
print("factor vintages: french.json ends", ff_json.index.max(), " zips end", ff_zip.index.max())
print()

# Step A: published construction on committed artifact.
vs_committed = value_series_monthly_returns(COMMITTED)
A = run_regression(vs_committed, ff_json, maxlags=3, annualization="geometric")
summarize("A. committed artifact, value-series (net, cash drag), HAC3, geometric", A)

# Step B: same returns, Round 3 estimator settings.
B = run_regression(vs_committed, ff_zip, maxlags=6, annualization="arithmetic")
summarize("B. committed artifact, value-series, HAC6, arithmetic, zip factors", B)

# Step C: committed artifact's locked picks, gross re-pricing (Round 3 construction).
lp_committed = monthly_returns(COMMITTED)
C = run_regression(lp_committed, ff_zip, maxlags=6, annualization="arithmetic")
summarize("C. committed artifact, locked-picks gross, HAC6, arithmetic", C)

# Step D: Round 3 baseline (2026-08-10 cache), locked-picks gross.
lp_new = monthly_returns(ROUND3)
D = run_regression(lp_new, ff_zip, maxlags=6, annualization="arithmetic")
summarize("D. 2026-08-10 rerun,   locked-picks gross, HAC6, arithmetic", D)

print()
print("bridge contributions to the %.2f -> %.2f swing:" % (A["alpha_annual_pct"], D["alpha_annual_pct"]))
print("  estimator (A->B):          %+.2f pp" % (B["alpha_annual_pct"] - A["alpha_annual_pct"]))
print("  return construction (B->C): %+.2f pp" % (C["alpha_annual_pct"] - B["alpha_annual_pct"]))
print("  cache state (C->D):         %+.2f pp" % (D["alpha_annual_pct"] - C["alpha_annual_pct"]))

# Month-level first divergence between the two return paths on the SAME artifact.
joint = pd.DataFrame({"value_series": vs_committed, "locked_gross": lp_committed}).dropna()
joint["diff_bps"] = (joint["locked_gross"] - joint["value_series"]) * 1e4
print("\nmonth-level |diff| between value-series and locked-gross returns, same artifact:")
print("  mean %.0f bps  median %.0f bps  max %.0f bps (month %s)" % (
    joint["diff_bps"].abs().mean(), joint["diff_bps"].abs().median(),
    joint["diff_bps"].abs().max(), joint["diff_bps"].abs().idxmax()))

# Turnover reconciliation.
def turnover_series(path):
    rebs = json.load(open(path))["portfolio"]["rebalances"]
    return {r["signal_date"]: (r["turnover"], frozenset(p["ticker"] for p in r["picks"]))
            for r in rebs}

old_t = turnover_series(COMMITTED)
new_t = turnover_series(ROUND3)
common_dates = sorted(set(old_t) & set(new_t))
first_div = None
overlaps = []
for dte in common_dates:
    ov = len(old_t[dte][1] & new_t[dte][1]) / max(1, len(old_t[dte][1]))
    overlaps.append(ov)
    if ov < 1.0 and first_div is None:
        first_div = (dte, ov)
old_mean = np.mean([v[0] for d, v in sorted(old_t.items())][1:])
new_mean = np.mean([v[0] for d, v in sorted(new_t.items())][1:])
print("\nturnover: committed 2026-08-03 artifact mean %.1f%%, 2026-08-10 rerun mean %.1f%%" % (
    old_mean * 100, new_mean * 100))
print("common rebalance dates %d, mean pick overlap %.2f, first divergence %s (overlap %.2f)" % (
    len(common_dates), np.mean(overlaps), first_div[0] if first_div else None,
    first_div[1] if first_div else 1.0))
