"""Task 5: the reconstructed-universe backtest.

Universe at each rebalance = the 860 survivors plus every dead-cohort name that was
live on that date (had prices and as-filed facts) and delisted later. Dead names are
scored by the identical as-filed TTM path used in Round 6 (their EDGAR facts entered
the same PIT store through the same code in ingest_dead_cohort.py), and their prices
come from the Task 3 recovery audit's cache, written into a merged cache directory that
symlinks the pinned survivor cache and never mutates it.

Universe definition, stated plainly: "filed XBRL, had a recoverable price, and
EntityPublicFloat >= $1B at the last 10-K." This is a size-proxy reconstruction, not an
index-membership series, and the findings document names it as such.

Selection runs through backtest_monthly unchanged. Returns are computed by the
locked-picks engine with delisting exits: a name whose prices end between two execution
dates exits at its last trade times (1 + delisting return), where the delisting return
is 0 for mergers (the last trade converges to deal value), the Shumway imputation for
bankruptcies and exchange-rule removals (Journal of Finance 52(1), 1997, -30% default,
-20/-40 sensitivity), and 0 with a separate count for voluntary deregistrations.

Usage: reconstruction_backtest.py run <out.json>     (build merged cache + run selection)
       reconstruction_backtest.py analyze <run.json> (returns, sensitivity, deltas)
"""
import json
import os
import sys
from bisect import bisect_left
from datetime import date, timedelta

REPO = "/Users/eyerise/Documents/GitHub/Dash"
OUT = f"{REPO}/research/audit/survivorship/data"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
MERGED = f"{OUT}/merged_cache"

FLOAT_FLOOR = 1e9


def dead_cohort():
    log = json.load(open(f"{OUT}/delisting_log.json"))
    recovery = {r["cik"]: r for r in json.load(open(f"{OUT}/price_recovery.json"))}
    floats = json.load(open(f"{OUT}/public_floats.json"))
    cohort = []
    for e in log:
        r = recovery.get(e["cik"])
        if not (e["operating_company"] and r and r["hit"]):
            continue
        if floats.get(e["cik"], 0) < FLOAT_FLOOR:
            continue
        if e["event_date"] < "2021-06-01":
            continue
        cohort.append({**e, "last_price_date": r["last_price_date"]})
    return cohort


def build_merged_cache(cohort):
    os.makedirs(MERGED, exist_ok=True)
    survivors = 0
    for f in os.listdir(f"{REPO}/pipeline/data/backtest_cache"):
        if not f.endswith(".json"):
            continue
        dst = os.path.join(MERGED, f)
        if not os.path.exists(dst):
            os.symlink(f"{REPO}/pipeline/data/backtest_cache/{f}", dst)
        survivors += 1
    added = []
    empty = {"periods": [], "rows": {}}
    for e in cohort:
        t = e["ticker"]
        src = f"{OUT}/dead_prices/{t}.json"
        if not os.path.exists(src):
            continue
        # A ticker already present in the survivor cache is a live name whose Form 25
        # was a transfer or a debt delisting. Writing through the symlink would clobber
        # the pinned cache (it did, for 16 names, before this guard: the survivorship
        # round 2 postmortem). Survivors always take precedence.
        if os.path.lexists(os.path.join(MERGED, f"{t}.json")):
            continue
        d = json.load(open(src))
        if len(d["dates"]) < 60:
            continue
        payload = {"symbol": t, "name": e["company"], "sector": None, "is_etf": False,
                   "current_shares_outstanding": None,
                   "dates": d["dates"], "closes": d["closes"], "raw_closes": d["closes"],
                   "volumes": d["volumes"],
                   "income": empty, "balance": empty, "cashflow": empty}
        json.dump(payload, open(os.path.join(MERGED, f"{t}.json"), "w"))
        added.append(t)
    return survivors, added


if sys.argv[1] == "run":
    cohort = dead_cohort()
    survivors, added = build_merged_cache(cohort)
    json.dump({"cohort": cohort, "added": added},
              open(f"{OUT}/reconstruction_cohort.json", "w"), indent=1)
    print(f"merged cache: {survivors} survivors + {len(added)} dead names "
          f"(cohort {len(cohort)}, float floor ${FLOAT_FLOOR/1e9:.0f}B)")

    out_path = sys.argv[2]
    sys.path.insert(0, f"{REPO}/pipeline")
    sys.path.insert(0, f"{REPO}/research/audit/round6")
    import backtest_historical as bh

    original_load = bh.load_universe

    def patched_load_universe(*args, **kwargs):
        symbols = original_load(*args, **kwargs)
        return list(symbols) + [t for t in added if t not in symbols]

    # asfiled_ttm_backtest executes backtest_monthly.main() at import time. Stub the
    # module during the import so only its build_snapshot patch installs, then load the
    # real one.
    import importlib
    import types
    fake = types.ModuleType("backtest_monthly")
    fake.main = lambda: None
    sys.modules["backtest_monthly"] = fake
    sys.argv = ["asfiled_ttm_backtest.py", "asfiled_q", "/dev/null"]
    import asfiled_ttm_backtest  # noqa: F401  (installs the TTM build_snapshot patch)
    del sys.modules["backtest_monthly"]
    import backtest_monthly
    importlib.reload(backtest_monthly)

    bh.load_universe = patched_load_universe
    backtest_monthly.load_universe = patched_load_universe
    sys.argv = ["backtest_monthly.py", "--cache-only", "--years", "5",
                "--cache-dir", MERGED, "--out", out_path]
    backtest_monthly.main()

elif sys.argv[1] == "analyze":
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    sys.path.insert(0, f"{REPO}/research/audit/round3")
    from item3_regression import load_factors

    run_path = sys.argv[2]
    cohort = json.load(open(f"{OUT}/reconstruction_cohort.json"))
    dead = {e["ticker"]: e for e in cohort["cohort"]}
    CLASS_RET = {"merger_acquisition": 0.0, "voluntary_or_unclassified_25": 0.0,
                 "voluntary_dereg": 0.0}

    _pc = {}

    def prices(t):
        if t not in _pc:
            for base in (MERGED,):
                p = os.path.join(base, f"{t}.json")
                if os.path.exists(p):
                    d = json.load(open(p))
                    _pc[t] = (d["dates"], d.get("closes"))
                    break
            else:
                _pc[t] = None
        return _pc[t]

    def price_on_or_before(t, day):
        p = prices(t)
        if not p:
            return None, None
        dates, closes = p
        i = bisect_left(dates, day)
        if i == len(dates) or dates[i] != day:
            i -= 1
        if i < 0:
            return None, None
        return closes[i], dates[i]

    rebs = json.load(open(run_path))["portfolio"]["rebalances"]

    def monthly_returns(imp):
        out = {}
        stats_c = {"dead_held_months": 0, "delist_exits": 0, "exit_by_class": {}}
        for a, b in zip(rebs, rebs[1:]):
            r = wsum = 0.0
            for p in a["picks"]:
                t = p["ticker"]
                p0, _ = price_on_or_before(t, a["execution_date"])
                p1, d1 = price_on_or_before(t, b["execution_date"])
                if not p0:
                    continue
                if t in dead:
                    stats_c["dead_held_months"] += 1
                e = dead.get(t)
                if (e and d1 and d1 < b["execution_date"]
                        and e["last_price_date"] <= b["execution_date"]
                        and d1 >= e["last_price_date"]):
                    klass = e["classification"]
                    dret = CLASS_RET.get(klass, imp)
                    p1 = p1 * (1 + dret)
                    stats_c["delist_exits"] += 1
                    stats_c["exit_by_class"][klass] = stats_c["exit_by_class"].get(klass, 0) + 1
                if p1:
                    r += p["weight"] * (p1 / p0 - 1)
                    wsum += p["weight"]
            if wsum > 0.5:
                out[a["execution_date"][:7].replace("-", "")] = r / wsum
        return pd.Series(out), stats_c

    ff = load_factors()

    def full_stats(rets):
        df = ff.join(rets.rename("port"), how="inner").dropna()
        y = df["port"] - df["RF"]
        X = sm.add_constant(df[["MktRF", "SMB", "HML", "RMW", "CMA", "MOM"]])
        m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
        years = len(rets) / 12
        cagr = (1 + rets).prod() ** (1 / years) - 1
        sharpe = rets.mean() / rets.std(ddof=1) * np.sqrt(12)
        curve = (1 + rets).cumprod()
        dd = (curve / curve.cummax() - 1).min()
        return cagr, sharpe, dd, m.params["const"] * 12 * 100, m.tvalues["const"], len(df)

    # Deterministic counts first.
    dead_picked = sorted({p["ticker"] for r0 in rebs for p in r0["picks"]
                          if p["ticker"] in dead})
    print(f"deterministic: dead names ever selected: {len(dead_picked)}: {dead_picked}")

    from item3_regression import monthly_returns as survivor_returns
    base = survivor_returns(f"{S}/bt_q_base.json")
    for imp in (-0.20, -0.30, -0.40):
        rets, sc = monthly_returns(imp)
        cagr, sharpe, dd, alpha, at, n = full_stats(rets)
        line = (f"imp {imp:+.0%}: CAGR {cagr*100:6.2f}%  Sharpe {sharpe:.2f}  "
                f"DD {dd*100:6.1f}%  alpha {alpha:+6.2f}%/yr (t {at:+.2f}, n {n})")
        if imp == -0.30:
            d = (rets - base).dropna()
            se2 = 2 * d.std(ddof=1) / np.sqrt(len(d)) * 12 * 100
            line += (f"  | vs survivor-only: paired {d.mean()*12*100:+.2f}pp, "
                     f"MDE {se2:.2f}pp, n {len(d)}  dead-held months {sc['dead_held_months']}"
                     f"  delist exits {sc['delist_exits']} {sc['exit_by_class']}")
        print(line)

    # Pick overlap and the single number.
    surv = {r0["signal_date"]: {p["ticker"] for p in r0["picks"]}
            for r0 in json.load(open(f"{S}/bt_q_base.json"))["portfolio"]["rebalances"]}
    rec = {r0["signal_date"]: {p["ticker"] for p in r0["picks"]} for r0 in rebs}
    common = sorted(set(surv) & set(rec))
    ov = [len(surv[d0] & rec[d0]) / max(1, len(surv[d0])) for d0 in common]
    displaced = sum(len(rec[d0] - surv[d0]) for d0 in common)
    phantom = sum(len(surv[d0] - rec[d0]) for d0 in common)
    print(f"pick overlap vs survivor-only: mean {np.mean(ov):.2f} over {len(common)} rebalances")
    print(f"THE NUMBER: position-months the survivor-only backtest held that the "
          f"reconstructed universe replaces: {phantom}. Position-months a real investor "
          f"could have held that the survivor-only run never offered: {displaced}.")
