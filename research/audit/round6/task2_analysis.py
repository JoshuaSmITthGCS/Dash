"""Tasks 1c and 2: three-way cadence table, quarterly ablations, post-spine DSR."""
import itertools
import json
import statistics
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import load_factors, monthly_returns

ff = load_factors()

def metrics(f):
    d = json.load(open(f"{S}/{f}"))
    p = d["portfolio"]; m = p["metrics"]
    tos = [x["turnover"] for x in p["rebalances"][1:]]
    return statistics.mean(tos), m["cagr"], m["maximum_drawdown"], m.get("annualized_volatility")

def regress(f, maxlags=6):
    rets = monthly_returns(f"{S}/{f}")
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    return m, len(df), rets

print("== three-way cadence table ==")
for name, f in [("restated TTM quarterly (R4 baseline)", "bt_baseline.json"),
                ("as-filed TTM quarterly (corrected spine)", "bt_q_base.json"),
                ("as-filed annual (corrected store)", "bt_af2_base.json"),
                ("as-filed annual (R5, pre-correction)", "bt_af_base.json")]:
    to, cagr, dd, vol = metrics(f)
    m, n, _ = regress(f)
    print(f"{name:42s} TO {to*100:5.1f}%  CAGR {cagr*100:6.2f}%  DD {dd*100:6.1f}%  "
          f"alpha {m.params['const']*12*100:+6.2f}%/yr (t {m.tvalues['const']:+.2f}, n {n})  "
          f"RMW {m.params['RMW']:+.2f}({m.tvalues['RMW']:+.1f}) MOM {m.params['MOM']:+.2f}({m.tvalues['MOM']:+.1f})")

base_rets = monthly_returns(f"{S}/bt_q_base.json")
rr = monthly_returns(f"{S}/bt_baseline.json")
d = (base_rets - rr).dropna()
se2 = 2 * d.std(ddof=1) / np.sqrt(len(d)) * 12 * 100
print(f"\nrestatement-bias isolate (as-filed Q minus restated Q): {d.mean()*12*100:+.2f}pp, 2SE {se2:.2f}pp, n {len(d)}")

# pick overlap
def picks(f):
    return {r["signal_date"]: {p["ticker"] for p in r["picks"]}
            for r in json.load(open(f"{S}/{f}"))["portfolio"]["rebalances"]}
pq, pr = picks("bt_q_base.json"), picks("bt_baseline.json")
common = sorted(set(pq) & set(pr))
ov = [len(pq[d0] & pr[d0]) / max(1, len(pr[d0])) for d0 in common]
print(f"cadence-constant pick overlap vs restated: mean {np.mean(ov):.2f}")

print("\n== quarterly-spine ablations (vs as-filed Q base) ==")
VAR = [("q base (full sleeve)", "bt_q_base.json"),
       ("q fundamentals only", "bt_q_fund.json"),
       ("q stack (buffer 1.5)", "bt_q_stack.json"),
       ("drop momentum_12_1", "bt_q_drop_momentum_12_1.json"),
       ("drop risk_adjusted", "bt_q_drop_risk_adjusted.json"),
       ("drop drawdown_resilience", "bt_q_drop_drawdown_resilience.json"),
       ("drop volume_confirmation", "bt_q_drop_volume_confirmation.json"),
       ("drop low_beta", "bt_q_drop_low_beta.json"),
       ("drop technical_extended", "bt_q_drop_technical_extended.json"),
       ("valuation 2-metric EV block", "bt_q_val2.json"),
       ("valuation single EV/EBITDA", "bt_q_val1.json")]
for name, f in VAR:
    try:
        to, cagr, dd, _ = metrics(f)
    except FileNotFoundError:
        print(f"{name:28s} MISSING"); continue
    rets = monthly_returns(f"{S}/{f}")
    dd_ = (rets - base_rets).dropna()
    thr = 2 * dd_.std(ddof=1) / np.sqrt(len(dd_)) * 12 * 100 if len(dd_) > 2 else float("nan")
    diff = dd_.mean() * 12 * 100
    m, n, _ = regress(f)
    print(f"{name:28s} TO {to*100:5.1f}%  CAGR {cagr*100:6.2f}%  DD {dd*100:6.1f}%  "
          f"CMA {m.params['CMA']:+.2f}({m.tvalues['CMA']:+.1f})  "
          f"paired {diff:+5.2f}/{thr:4.2f} {'SIGNAL' if abs(diff)>thr else 'noise'}")

# DSR/PBO recompute including the corrected-spine runs.
frame = {}
ALL = {**dict(("r5_"+k, v) for k, v in {
    "af_base": "bt_af_base.json", "af_fund": "bt_af_fund.json", "af_stack": "bt_af_stack.json",
    "drop_mom": "bt_af_drop_momentum_12_1.json", "drop_risk": "bt_af_drop_risk_adjusted.json",
    "drop_dd": "bt_af_drop_drawdown_resilience.json", "drop_vol": "bt_af_drop_volume_confirmation.json",
    "drop_beta": "bt_af_drop_low_beta.json", "drop_ext": "bt_af_drop_technical_extended.json",
    "dropfast": "bt_af_dropfast.json"}.items()),
    "restated": "bt_baseline.json", "restated_cs": "bt_cs.json",
    "restated_b125": "bt_buffer125.json", "restated_b150": "bt_buffer150.json",
    "restated_b200": "bt_buffer.json", "restated_g0": "bt_growth_zero.json",
    "restated_fund": "bt_fund_only.json", "restated_nm": "bt_no_mods.json",
    "q_base": "bt_q_base.json", "q_fund": "bt_q_fund.json", "q_stack": "bt_q_stack.json",
    "q_dmom": "bt_q_drop_momentum_12_1.json", "q_drisk": "bt_q_drop_risk_adjusted.json",
    "q_ddd": "bt_q_drop_drawdown_resilience.json", "q_dvol": "bt_q_drop_volume_confirmation.json",
    "q_dbeta": "bt_q_drop_low_beta.json", "q_dext": "bt_q_drop_technical_extended.json",
    "q_val2": "bt_q_val2.json", "q_val1": "bt_q_val1.json",
    "af2_base": "bt_af2_base.json"}
for k, v in ALL.items():
    try:
        frame[k] = monthly_returns(f"{S}/{v}")
    except FileNotFoundError:
        pass
M = pd.DataFrame(frame).dropna()
T, N = M.shape
r = M["q_base"]
sr = r.mean() / r.std(ddof=1)
skew, kurt = stats.skew(r), stats.kurtosis(r, fisher=False)
srs = M.mean() / M.std(ddof=0)
V = srs.var(ddof=1)
g = 0.5772156649
for NN in (N, 40):
    sr_star = np.sqrt(V) * ((1 - g) * stats.norm.ppf(1 - 1 / NN) + g * stats.norm.ppf(1 - 1 / (NN * np.e)))
    num = (sr - sr_star) * np.sqrt(T - 1)
    den = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    print(f"\nDSR of as-filed-quarterly base at N={NN} (T={T}, {N} series): {stats.norm.cdf(num/den):.3f}")
blocks = np.array_split(np.arange(T), 8)
logits = []
for tr in itertools.combinations(range(8), 4):
    train = np.concatenate([blocks[i] for i in tr])
    test = np.concatenate([blocks[i] for i in range(8) if i not in tr])
    is_sr = M.iloc[train].mean() / M.iloc[train].std(ddof=0)
    oos_sr = M.iloc[test].mean() / M.iloc[test].std(ddof=0)
    best = is_sr.idxmax()
    w = (oos_sr < oos_sr[best]).sum() / (len(oos_sr) - 1)
    w = max(min(w, 1 - 1e-9), 1e-9)
    logits.append(np.log(w / (1 - w)))
print(f"PBO over the full {N}-variant family: {np.mean(np.array(logits) <= 0):.2f}")
