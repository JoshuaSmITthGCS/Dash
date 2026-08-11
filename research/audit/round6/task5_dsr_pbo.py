"""Task 5: retrospective deflated Sharpe ratio and probability of backtest overfitting
for the as-filed alpha estimate, at the frozen trial count.

DSR per Bailey and Lopez de Prado, Journal of Portfolio Management 40(5), 2014: the
observed Sharpe is tested against the expected maximum Sharpe of N unskilled trials,
with non-normality corrections from the observed skew and kurtosis. PBO per Bailey,
Borwein, Lopez de Prado and Zhu (Notices of the AMS 61(5), 2014) via combinatorially
symmetric cross-validation over the actual variant return matrix produced across
Rounds 3 through 5.
"""
import itertools
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import monthly_returns  # noqa: E402

VARIANTS = {
    "restated_baseline": "bt_baseline.json", "restated_cs": "bt_cs.json",
    "restated_buffer125": "bt_buffer125.json", "restated_buffer150": "bt_buffer150.json",
    "restated_buffer200": "bt_buffer.json", "restated_growth0": "bt_growth_zero.json",
    "restated_fund_only": "bt_fund_only.json", "restated_no_mods": "bt_no_mods.json",
    "af_base": "bt_af_base.json", "af_fund": "bt_af_fund.json",
    "af_stack": "bt_af_stack.json", "af_slowrs": "bt_af_slowrs.json",
    "af_drop_mom": "bt_af_drop_momentum_12_1.json",
    "af_drop_risk": "bt_af_drop_risk_adjusted.json",
    "af_drop_rs": "bt_af_drop_relative_strength.json",
    "af_drop_dd": "bt_af_drop_drawdown_resilience.json",
    "af_drop_vol": "bt_af_drop_volume_confirmation.json",
    "af_drop_beta": "bt_af_drop_low_beta.json",
    "af_drop_ext": "bt_af_drop_technical_extended.json",
    "af_dropfast": "bt_af_dropfast.json",
}

frame = {}
for name, f in VARIANTS.items():
    try:
        frame[name] = monthly_returns(f"{S}/{f}")
    except FileNotFoundError:
        pass
M = pd.DataFrame(frame).dropna()
T, N_avail = M.shape
print(f"variant return matrix: T={T} months, N={N_avail} variants (frozen trial count N=40)")

target = "af_base"
r = M[target]
sr_monthly = r.mean() / r.std(ddof=1)
sr_annual = sr_monthly * np.sqrt(12)
skew = stats.skew(r)
kurt = stats.kurtosis(r, fisher=False)
print(f"as-filed base: monthly SR {sr_monthly:.3f} (annualized {sr_annual:.2f}), "
      f"skew {skew:+.2f}, kurtosis {kurt:.2f}")

# Expected max Sharpe of N unskilled trials (monthly units), variance from actual trials.
trial_srs = M.mean() / M.std(ddof=0)
V = trial_srs.var(ddof=1)
gamma = 0.5772156649
for N in (N_avail, 40):
    sr_star = np.sqrt(V) * ((1 - gamma) * stats.norm.ppf(1 - 1 / N)
                            + gamma * stats.norm.ppf(1 - 1 / (N * np.e)))
    num = (sr_monthly - sr_star) * np.sqrt(T - 1)
    den = np.sqrt(1 - skew * sr_monthly + (kurt - 1) / 4 * sr_monthly ** 2)
    dsr = stats.norm.cdf(num / den)
    print(f"N={N}: E[max SR unskilled] {sr_star:.3f}/mo ({sr_star*np.sqrt(12):.2f} ann)  "
          f"DSR = {dsr:.3f}  (threshold 0.95)")

# PBO via CSCV: 8 blocks, C(8,4)=70 splits.
blocks = np.array_split(np.arange(T), 8)
logits = []
for train_idx in itertools.combinations(range(8), 4):
    train = np.concatenate([blocks[i] for i in train_idx])
    test = np.concatenate([blocks[i] for i in range(8) if i not in train_idx])
    is_sr = M.iloc[train].mean() / M.iloc[train].std(ddof=0)
    oos_sr = M.iloc[test].mean() / M.iloc[test].std(ddof=0)
    best = is_sr.idxmax()
    rank = (oos_sr < oos_sr[best]).sum() / (len(oos_sr) - 1)
    w = max(min(rank, 1 - 1e-9), 1e-9)
    logits.append(np.log(w / (1 - w)))
logits = np.array(logits)
pbo = (logits <= 0).mean()
print(f"PBO (CSCV, 8 blocks, 70 splits, N={N_avail} variants): {pbo:.2f}  "
      f"(mean OOS relative rank of IS winner: {stats.norm.cdf(logits.mean()):.2f} as logit-cdf)")

# HLZ hurdle.
print("\nHarvey, Liu, Zhu (RFS 29(1), 2016) hurdle: |t| > 3.0 for a new factor.")
print("as-filed alpha t = 1.93 (n=58): FAILS the t>3 hurdle and the t>2 convention.")
