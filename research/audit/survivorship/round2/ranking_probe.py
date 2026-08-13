"""Task 1: the fundamentals-only ranking probe. Would the score have selected names
that subsequently died?

Needs no prices. At each of the 60 rebalance dates, every dead-cohort CIK with as-filed
facts visible on that date is scored through the identical as-filed TTM statement path
(edgar_enrichment internals) and the identical band scorer, on the PRICE-FREE composite:
the five fundamental categories that need no market data (profitability, financial
health, growth, capital allocation, accounting quality), weights renormalized over the
five. Valuation and technical require prices and are excluded, stated plainly. The
excluded half is not the half whose job is avoiding deaths. The included half is.

Survivor baseline: the 851 usable cache names scored identically at the same dates, so
every dead name gets a same-day percentile in the merged cross-section.

Conditioning: time-to-death buckets and classification, with the transfer-adjusted
true-death cohort (bankruptcy or exchange-rule removal, stopped filing within 12
months) reported as the headline and mergers separately. A name whose latest visible
annual period is older than 548 days at the scoring date counts as UNSCORED-STALE, not
excluded silently, because a name that stopped filing before it died is a coverage
collapse the live pipeline gates on.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
OUT = f"{REPO}/research/audit/survivorship/data"
S = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad"
sys.path.insert(0, f"{REPO}/pipeline")

import scorer  # noqa: E402
from edgar_enrichment import (_annual_facts_as_of, _statements,  # noqa: E402
                              _ticker_to_cik, _ttm_facts_as_of)
from fundamentals_extended import derive_extended  # noqa: E402

PRICE_FREE = ("profitability", "financial_health", "growth",
              "capital_allocation", "accounting_quality")
CAT_W = {k: v for k, v in scorer.SETTINGS["fundamentals"]["category_weights"].items()
         if k in PRICE_FREE}


def statements_for(cik, as_of):
    annual = _statements(_annual_facts_as_of(cik, as_of))
    if annual is None:
        return None
    ttm, balance_now = _ttm_facts_as_of(cik, as_of)
    return annual  # annual is sufficient for the price-free blocks at probe fidelity


def price_free_score(cik, as_of, sector=None):
    """(composite, categories, latest_period) on the price-free basis, or None."""
    annual = statements_for(cik, as_of)
    if annual is None:
        return None
    periods = annual["income"]["periods"]
    if not periods:
        return None
    latest = periods[0]
    ext = derive_extended(annual=annual, info={}, market_cap=None, price=None,
                         sector=sector)
    snap = {**ext, "ticker": cik, "is_etf": False, "sector": sector}
    _total, parts = scorer.valuation_score(snap, mode="bands")
    cats = (parts or {}).get("categories") or {}
    avail = [(cats[c], CAT_W[c]) for c in PRICE_FREE if cats.get(c) is not None]
    if not avail:
        return None
    composite = sum(v * w for v, w in avail) / sum(w for _v, w in avail)
    return composite, cats, latest, ext.get("altman_z"), ext.get("interest_coverage")


# Cohorts.
log = json.load(open(f"{OUT}/delisting_log.json"))
adjusted_dead = set()
merger_cohort = set()
death_class = {}
for e in log:
    if not e["operating_company"]:
        continue
    death_class[e["cik"]] = (e["classification"], e["event_date"])
    if e["classification"] in ("bankruptcy", "exchange_rule_removal"):
        adjusted_dead.add(e["cik"])
    elif e["classification"] == "merger_acquisition":
        merger_cohort.add(e["cik"])

# Filing-continuation filter: still-filing names are transfers, not deaths.
sub_dir = f"{OUT}/submissions"


def still_filing_12m(cik, event_iso):
    path = f"{sub_dir}/{cik}.json"
    if not os.path.exists(path):
        return None
    try:
        sub = json.load(open(path))
    except (json.JSONDecodeError, TypeError):
        return None
    cutoff = (date.fromisoformat(event_iso) + timedelta(days=365)).isoformat()
    r = (sub.get("filings") or {}).get("recent") or {}
    return any(f in ("10-K", "10-Q", "20-F") and d >= cutoff
               for f, d in zip(r.get("form", []), r.get("filingDate", [])))


true_dead = {c for c in adjusted_dead
             if still_filing_12m(c, death_class[c][1]) is False}
print(f"true-death cohort (bankruptcy/removal, stopped filing): {len(true_dead)}")
print(f"merger cohort: {len(merger_cohort)}")

# Rebalance dates from the Round 6 quarterly base run.
rebs = json.load(open(f"{S}/bt_q_base.json"))["portfolio"]["rebalances"]
dates = [r["signal_date"] for r in rebs]

# Survivor CIKs.
t2c = _ticker_to_cik()
survivors = sorted({t2c[t.upper()] for t in
                    (f[:-5] for f in os.listdir(f"{REPO}/pipeline/data/backtest_cache")
                     if f.endswith(".json")) if t.upper() in t2c})

probe_ciks = sorted(true_dead | merger_cohort)
STALE_DAYS = 548

rows = []
for di, as_of in enumerate(dates):
    surv_scores = []
    for cik in survivors:
        r = price_free_score(cik, as_of)
        if r is None:
            continue
        comp, _cats, latest, _z, _ic = r
        if (date.fromisoformat(as_of) - date.fromisoformat(latest)).days > STALE_DAYS:
            continue
        surv_scores.append(comp)
    surv_arr = np.sort(np.array(surv_scores))

    for cik in probe_ciks:
        klass, edate = death_class[cik]
        if edate <= as_of:
            continue  # already dead or transferred by this date
        r = price_free_score(cik, as_of)
        if r is None:
            status = "unscored_no_facts"
            rows.append({"date": as_of, "cik": cik, "class": klass, "event": edate,
                         "status": status})
            continue
        comp, cats, latest, z, ic = r
        if (date.fromisoformat(as_of) - date.fromisoformat(latest)).days > STALE_DAYS:
            rows.append({"date": as_of, "cik": cik, "class": klass, "event": edate,
                         "status": "unscored_stale"})
            continue
        pct = float(np.searchsorted(surv_arr, comp) / max(1, len(surv_arr)) * 100)
        rows.append({"date": as_of, "cik": cik, "class": klass, "event": edate,
                     "status": "scored", "composite": round(comp, 1),
                     "pct_vs_survivors": round(pct, 1),
                     "months_to_death": round((date.fromisoformat(edate)
                                               - date.fromisoformat(as_of)).days / 30.4, 1),
                     "financial_health": cats.get("financial_health"),
                     "accounting_quality": cats.get("accounting_quality"),
                     "profitability": cats.get("profitability"),
                     "altman_z": z, "interest_coverage": ic})
    if (di + 1) % 12 == 0:
        print(f"  {di+1}/{len(dates)} dates, {len(rows)} rows")

json.dump(rows, open(f"{OUT}/ranking_probe.json", "w"))
print(f"probe rows: {len(rows)}")
