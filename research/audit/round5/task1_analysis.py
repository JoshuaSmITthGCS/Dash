"""Task 1 analysis: restated vs as-filed delta, sample diagnostics, coverage by year.

The headline CAGR difference is interrogated, not celebrated: the as-filed path scores
annual 10-K statements only and drops names without us-gaap EDGAR facts, so the
eligible universe and update frequency both differ from the restated path. Every
mechanical difference is quantified here before the delta table is read as a
restatement-bias measurement.
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import load_factors, monthly_returns  # noqa: E402

restated = json.load(open(f"{S}/bt_baseline.json"))
asfiled = json.load(open(f"{S}/bt_af_base.json"))

# Pick divergence per rebalance.
r_picks = {r["signal_date"]: {p["ticker"] for p in r["picks"]}
           for r in restated["portfolio"]["rebalances"]}
a_picks = {r["signal_date"]: {p["ticker"] for p in r["picks"]}
           for r in asfiled["portfolio"]["rebalances"]}
common_dates = sorted(set(r_picks) & set(a_picks))
overlaps = [len(r_picks[d] & a_picks[d]) / max(1, len(r_picks[d])) for d in common_dates]
print("rebalances compared: %d  mean pick overlap %.2f  (fraction of picks that change: %.2f)" % (
    len(common_dates), np.mean(overlaps), 1 - np.mean(overlaps)))

# Regressions, aligned months, Round 4 step-D estimator.
ff = load_factors()


def regress(path):
    rets = monthly_returns(path)
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return m, len(df), rets


m_r, n_r, rets_r = regress(f"{S}/bt_baseline.json")
m_a, n_a, rets_a = regress(f"{S}/bt_af_base.json")
m_f, n_f, _ = regress(f"{S}/bt_af_fund.json")
for name, m, n in (("restated", m_r, n_r), ("as-filed", m_a, n_a),
                   ("as-filed fund-only", m_f, n_f)):
    print(f"{name:20s} alpha {m.params['const']*12*100:+.2f}%/yr (t {m.tvalues['const']:+.2f}, n {n})  "
          + "  ".join(f"{f} {m.params[f]:+.2f} (t {m.tvalues[f]:+.1f})"
                      for f in ["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]))

# Paired noise standard from task6_noise_standard, applied to the headline delta.
d = (rets_a - rets_r).dropna()
se = d.std(ddof=1) / np.sqrt(len(d))
print("paired as-filed minus restated: ann diff %+.2f pp, 2SE threshold %.2f pp, n %d -> %s" % (
    d.mean() * 12 * 100, 2 * se * 12 * 100, len(d),
    "SIGNAL" if abs(d.mean() * 12 * 100) > 2 * se * 12 * 100 else "noise"))

# Eligible-universe diagnostics: how many names each run could rank. The artifact does
# not store per-month eligibles, so approximate by unique tickers ever picked plus
# scoring reach: count cache tickers with any EDGAR annual facts.
sys.path.insert(0, f"{REPO}/pipeline")
from edgar_enrichment import _annual_facts_as_of, _ticker_to_cik  # noqa: E402
import os
cache_tickers = [f[:-5] for f in os.listdir(f"{REPO}/pipeline/data/backtest_cache")
                 if f.endswith(".json")]
t2c = _ticker_to_cik()
mapped = [t for t in cache_tickers if t.upper() in t2c]
with_facts = 0
for t in mapped:
    facts = _annual_facts_as_of(t2c[t.upper()], "2026-08-10")
    if any(c == "revenue" for c, _pe in facts):
        with_facts += 1
print("cache tickers %d, CIK-mapped %d, with EDGAR annual revenue facts %d" % (
    len(cache_tickers), len(mapped), with_facts))

# As-filed coverage by year: fraction of mapped names whose latest visible annual
# statement (on Jan 1 of each year) includes each core concept.
CORE = ["revenue", "net_income", "operating_income", "assets", "equity",
        "operating_cash_flow", "capital_expenditure", "depreciation_amortization",
        "retained_earnings"]
print("\nas-filed coverage by year (share of %d mapped names with the concept visible on Jan 1):" % len(mapped))
print("year  " + "  ".join(f"{c[:10]:>10s}" for c in CORE))
for year in range(2011, 2027, 3):
    as_of = f"{year}-01-01"
    counts = Counter()
    for t in mapped:
        facts = _annual_facts_as_of(t2c[t.upper()], as_of)
        seen = {c for c, _pe in facts}
        for c in CORE:
            if c in seen:
                counts[c] += 1
    print(f"{year}  " + "  ".join(f"{counts[c]/len(mapped):10.2f}" for c in CORE))
