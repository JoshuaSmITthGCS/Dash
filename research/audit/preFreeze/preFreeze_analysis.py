"""Single backtest row per pre-freeze challenger, Class B annotated, no ranking."""
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
base = monthly_returns(f"{S}/bt_q_base.json")

VARIANTS = [("as-filed Q base (incumbent)", "bt_q_base.json"),
            ("orthogonal (AFP value-quality)", "bt_pf_orthogonal.json"),
            ("max_screen (BCW exclusion)", "bt_pf_max_screen.json"),
            ("net_issuance (PW replaces buybacks)", "bt_pf_net_issuance.json"),
            ("parsimony (DGU 6-signal 1/N)", "bt_pf_parsimony.json"),
            ("intangible_book (AHKL/Peters-Taylor)", "bt_pf_intangible_book.json")]
print(f"{'variant':38s} {'TO':>6s} {'CAGR':>7s} {'DD':>7s} {'alpha(t)':>15s} {'HML(t)':>13s} {'RMW(t)':>13s} {'paired/2SE':>13s}")
for name, f in VARIANTS:
    try:
        d = json.load(open(f"{S}/{f}"))
    except FileNotFoundError:
        print(f"{name:38s} MISSING")
        continue
    p = d["portfolio"]; m = p["metrics"]
    to = statistics.mean(x["turnover"] for x in p["rebalances"][1:])
    rets = monthly_returns(f"{S}/{f}")
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    reg = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    dd_ = (rets - base).dropna()
    thr = 2 * dd_.std(ddof=1) / np.sqrt(len(dd_)) * 12 * 100 if len(dd_) > 2 else float("nan")
    diff = dd_.mean() * 12 * 100 if len(dd_) else 0.0
    print(f"{name:38s} {to*100:5.1f}% {m['cagr']*100:6.2f}% {m['maximum_drawdown']*100:6.1f}% "
          f"{reg.params['const']*12*100:+6.2f} ({reg.tvalues['const']:+.2f}) "
          f"{reg.params['HML']:+.2f} ({reg.tvalues['HML']:+.1f}) "
          f"{reg.params['RMW']:+.2f} ({reg.tvalues['RMW']:+.1f}) "
          f"{diff:+5.2f}/{thr:4.2f}")
