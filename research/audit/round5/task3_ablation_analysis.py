"""Task 3: technical sleeve ablation table on the as-filed spine."""
import json
import statistics
import sys

import numpy as np
import statsmodels.api as sm

REPO = "/Users/eyerise/Documents/GitHub/Dash"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/research/audit/round3")
from item3_regression import load_factors, monthly_returns

ff = load_factors()
base = monthly_returns(f"{S}/bt_af_base.json")

VARIANTS = [
    ("as-filed full sleeve (base)", "bt_af_base.json"),
    ("drop momentum_12_1", "bt_af_drop_momentum_12_1.json"),
    ("drop risk_adjusted", "bt_af_drop_risk_adjusted.json"),
    ("drop relative_strength", "bt_af_drop_relative_strength.json"),
    ("drop drawdown_resilience", "bt_af_drop_drawdown_resilience.json"),
    ("drop volume_confirmation", "bt_af_drop_volume_confirmation.json"),
    ("drop low_beta", "bt_af_drop_low_beta.json"),
    ("drop technical_extended", "bt_af_drop_technical_extended.json"),
    ("drop RS + volume (fast pair)", "bt_af_dropfast.json"),
    ("relative_strength slowed to 63d", "bt_af_slowrs.json"),
    ("fundamentals only", "bt_af_fund.json"),
]

print(f"{'variant':34s} {'TO':>6s} {'dTO':>6s} {'CAGR':>7s} {'DD':>7s} {'CMA(t)':>13s} {'MOM(t)':>13s} {'paired dCAGR/2SE':>17s}")
for name, f in VARIANTS:
    try:
        d = json.load(open(f"{S}/{f}"))
    except FileNotFoundError:
        print(f"{name:34s} MISSING")
        continue
    p = d["portfolio"]; m = p["metrics"]
    tos = [x["turnover"] for x in p["rebalances"][1:]]
    to = statistics.mean(tos)
    rets = monthly_returns(f"{S}/{f}")
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    reg = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    diff = (rets - base).dropna()
    se2 = 2 * diff.std(ddof=1) / np.sqrt(len(diff)) * 12 * 100 if len(diff) > 2 else float("nan")
    dc = diff.mean() * 12 * 100 if len(diff) else 0.0
    base_to = 0.222
    print(f"{name:34s} {to*100:5.1f}% {(to-base_to)*100:+5.1f}% {m['cagr']*100:6.2f}% {m['maximum_drawdown']*100:6.1f}% "
          f"{reg.params['CMA']:+.2f} ({reg.tvalues['CMA']:+.1f})  {reg.params['MOM']:+.2f} ({reg.tvalues['MOM']:+.1f})  "
          f"{dc:+6.2f}/{se2:5.2f}")
