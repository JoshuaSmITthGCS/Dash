"""Item 3: FF5 + momentum time-series regression of backtest portfolio returns.

Reconstructs clean monthly returns from each run's locked rebalance picks and the
price cache (no contribution cash flows), then regresses excess returns on
Mkt-RF, SMB, HML, RMW, CMA, MOM (Kenneth R. French Data Library, local zips).
Newey-West (HAC, 6 lags) standard errors.
"""
import io
import json
import sys
import zipfile
from bisect import bisect_left
from datetime import date

import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO = "/Users/eyerise/Documents/GitHub/Dash"
CACHE = f"{REPO}/pipeline/data/backtest_cache"


def load_factors():
    z = zipfile.ZipFile(f"{REPO}/pipeline/data/factors/fama_french_5_monthly.zip")
    raw = z.read(z.namelist()[0]).decode("latin1")
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(",Mkt-RF"))
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if len(parts) == 7 and parts[0].isdigit() and len(parts[0]) == 6:
            rows.append([parts[0]] + [float(x) for x in parts[1:]])
        else:
            break
    ff = pd.DataFrame(rows, columns=["ym", "MktRF", "SMB", "HML", "RMW", "CMA", "RF"]).set_index("ym")

    z2 = zipfile.ZipFile(f"{REPO}/pipeline/data/factors/momentum_monthly.zip")
    raw2 = z2.read(z2.namelist()[0]).decode("latin1")
    lines2 = raw2.splitlines()
    start2 = next(i for i, l in enumerate(lines2) if l.strip().startswith("Mom") or l.strip().startswith(",Mom"))
    rows2 = []
    for l in lines2[start2 + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 6:
            rows2.append([parts[0], float(parts[1])])
        elif rows2:
            break
    mom = pd.DataFrame(rows2, columns=["ym", "MOM"]).set_index("ym")
    return ff.join(mom, how="inner") / 100.0


_price_cache = {}


def prices(ticker):
    if ticker not in _price_cache:
        try:
            d = json.load(open(f"{CACHE}/{ticker}.json"))
            _price_cache[ticker] = (d["dates"], d["closes"])
        except FileNotFoundError:
            _price_cache[ticker] = None
    return _price_cache[ticker]


def price_on_or_before(ticker, day):
    p = prices(ticker)
    if not p:
        return None
    dates, closes = p
    i = bisect_left(dates, day)
    if i == len(dates) or dates[i] != day:
        i -= 1
    if i < 0:
        return None
    return closes[i]


def monthly_returns(run):
    rebs = json.load(open(run))["portfolio"]["rebalances"]
    out = {}
    for a, b in zip(rebs, rebs[1:]):
        r = 0.0
        wsum = 0.0
        for p in a["picks"]:
            p0 = price_on_or_before(p["ticker"], a["execution_date"])
            p1 = price_on_or_before(p["ticker"], b["execution_date"])
            if p0 and p1:
                r += p["weight"] * (p1 / p0 - 1)
                wsum += p["weight"]
        if wsum > 0.5:
            ym = a["execution_date"][:7].replace("-", "")
            out[ym] = r / wsum
    return pd.Series(out)


def regress(name, run, ff):
    rets = monthly_returns(run)
    df = ff.join(rets.rename("port"), how="inner").dropna()
    y = df["port"] - df["RF"]
    X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    print(f"== {name} (n={len(df)} months) ==")
    print("annualized alpha: %.2f%%  (t=%.2f)" % (model.params["const"] * 12 * 100, model.tvalues["const"]))
    for f in ["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]:
        print("  %-6s beta %+.3f  se %.3f  t %+0.2f" % (
            f, model.params[f], model.bse[f], model.tvalues[f]))
    print("  R2 %.3f" % model.rsquared)
    return model


if __name__ == "__main__":
    ff = load_factors()
    print("factor months:", ff.index.min(), "to", ff.index.max())
    for name, path in [(a, b) for a, b in zip(sys.argv[1::2], sys.argv[2::2])]:
        regress(name, path, ff)
        print()
