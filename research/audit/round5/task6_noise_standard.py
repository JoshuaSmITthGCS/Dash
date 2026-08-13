"""Task 6.5: one noise standard for variant CAGR comparisons.

Standard adopted: a variant's CAGR difference from baseline is noise unless
|mean monthly paired return difference| > 2 * SE(paired difference). Paired, because
variants share most holdings, so the difference series is far less volatile than either
series alone. Applied identically to every variant.
"""
import sys
import numpy as np
import pandas as pd

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import monthly_returns

S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
base = monthly_returns(f"{S}/bt_baseline.json")
for name, path in [("cross_sectional", f"{S}/bt_cs.json"),
                   ("buffer_1.25", f"{S}/bt_buffer125.json"),
                   ("buffer_1.5", f"{S}/bt_buffer150.json"),
                   ("buffer_2.0", f"{S}/bt_buffer.json"),
                   ("growth_zeroed", f"{S}/bt_growth_zero.json"),
                   ("fundamentals_only", f"{S}/bt_fund_only.json")]:
    v = monthly_returns(path)
    d = (v - base).dropna()
    se = d.std(ddof=1) / np.sqrt(len(d))
    ann = d.mean() * 12 * 100
    thr = 2 * se * 12 * 100
    verdict = "SIGNAL" if abs(ann) > thr else "noise"
    print(f"{name:18s} paired ann diff {ann:+6.2f}pp  2SE threshold {thr:5.2f}pp  n {len(d)}  -> {verdict}")
