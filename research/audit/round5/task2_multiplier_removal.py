"""Task 2: measure the multiplier removal alone, unbundled from imputation.

Variant under test: production champion (bands, within-block renormalization intact,
same modifiers) with the two completeness multipliers removed. Compared against
production and against the Round 4 fixed-feature challenger on the identical
EDGAR-augmented snapshot, so the three points isolate: multipliers alone, then
imputation on top.

Also runs Task 6.1 (residual-correlation mechanism) and Task 6.2 (characteristic
battery on the augmented snapshot) since all three need the same augmented scoring pass.
"""
import json
import math
import sys
from bisect import bisect_left
from collections import defaultdict

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")

import scorer  # noqa: E402
from edgar_enrichment import edgar_extended  # noqa: E402
from scorer import CrossSectionalNormalizer  # noqa: E402

rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

settings = scorer.SETTINGS["fundamentals"]


def wcov(detail):
    answered = total = 0.0
    for cat, ws in settings["metric_weights"].items():
        cw = settings["category_weights"].get(cat, 0)
        for m, w in ws.items():
            share = cw * w
            total += share
            if detail.get(m) is not None:
                answered += share
    return answered / total if total else 0.0


snaps, keep = [], []
for r in rows:
    raw = dict(r.get("raw_metric_inputs") or {})
    if r["scores"]["champion"] is None or raw.get("sector") == "ETF":
        continue
    fb = edgar_extended(r["ticker"], as_of="2026-08-10", market_cap=raw.get("market_cap"),
                        price=raw.get("price"), sector=raw.get("sector"))
    if fb:
        for k, v in fb.items():
            if k in ("statement_source", "statement_periods", "piotroski_tests"):
                continue
            if raw.get(k) is None and v is not None:
                raw[k] = v
    snaps.append({**raw, "ticker": r["ticker"], "is_etf": False})
    keep.append(r)

nz = CrossSectionalNormalizer(snaps)
prod, nomult, ff = {}, {}, {}
covs, sectors, ff_detail = {}, {}, {}
for snap in snaps:
    t = snap["ticker"]
    p_score, p_parts = scorer.valuation_score(snap, mode="bands")
    f_score, f_parts = scorer.valuation_score(snap, mode="fixed_feature", normalizer=nz)
    if p_score is None or f_score is None:
        continue
    prod[t] = p_score                       # bands with 0.65+0.35*coverage
    nomult[t] = p_parts.get("raw_score")    # bands, multiplier removed, renorm intact
    ff[t] = f_score
    covs[t] = wcov({m: p_parts.get(m) for ws in settings["metric_weights"].values() for m in ws})
    sectors[t] = snap.get("sector")
    ff_detail[t] = f_parts

tickers = sorted(prod)
p = np.array([prod[t] for t in tickers])
nm = np.array([nomult[t] for t in tickers])
f = np.array([ff[t] for t in tickers])
c = np.array([covs[t] for t in tickers])
print("n=%d  mean coverage %.2f" % (len(tickers), c.mean()))
print("\nSpearman(coverage, fundamentals score):")
for name, arr in (("production (bands, both multipliers)", p),
                  ("multiplier removal alone (renorm intact)", nm),
                  ("fixed_feature (imputation, no multipliers)", f)):
    rho, pv = stats.spearmanr(c, arr)
    print(f"  {name:44s} rho {rho:+.3f}  p {pv:.1e}")

pr, nr = stats.rankdata(-p), stats.rankdata(-nm)
shift = pr - nr
print("\nmultiplier removal vs production: rank corr %.3f  mean |shift| %.1f  >25: %d  >50: %d" % (
    stats.spearmanr(p, nm)[0], np.abs(shift).mean(),
    (np.abs(shift) > 25).sum(), (np.abs(shift) > 50).sum()))

fin = [i for i, t in enumerate(tickers) if sectors[t] in ("Financial Services", "Financials")]
oth = [i for i in range(len(tickers)) if i not in fin]
for name, arr in (("production", p), ("multiplier removal", nm)):
    u = stats.mannwhitneyu(arr[fin], arr[oth])
    print(f"{name}: financials {arr[fin].mean():.1f} vs rest {arr[oth].mean():.1f} "
          f"(gap {arr[fin].mean()-arr[oth].mean():+.1f}, p {u[1]:.3f})")

# ---- Task 6.1: residual-correlation mechanism under fixed_feature ----
imputed_w = np.array([ff_detail[t].get("imputed_weight_fraction", 0.0) for t in tickers])
complete = imputed_w <= 0.02
print("\nTask 6.1 residual mechanism: complete-case names (imputed weight <= 0.02): %d" % complete.sum())
if complete.sum() > 30:
    rho_cc = stats.spearmanr(c[complete], f[complete])
    print("  Spearman(coverage, fixed_feature) complete cases only: %+.3f (p %.2f, n %d)" % (
        rho_cc[0], rho_cc[1], complete.sum()))
rho_dilution = stats.spearmanr(imputed_w, np.abs(f - 50))
print("  Spearman(imputed weight, |score - 50|): %+.3f (p %.1e) "
      "(negative = imputation shrinks scores toward neutral, the dilution mechanism)" % (
          rho_dilution[0], rho_dilution[1]))

# ---- Task 6.2: characteristic battery on the augmented snapshot ----
def mom_12_1(ticker, asof="2026-08-10"):
    try:
        d = json.load(open(f"{REPO}/pipeline/data/backtest_cache/{ticker}.json"))
    except FileNotFoundError:
        return None
    dates, closes = d["dates"], d["closes"]
    i = min(bisect_left(dates, asof), len(dates) - 1)
    if i < 252 or not closes[i - 21] or not closes[i - 252]:
        return None
    return closes[i - 21] / closes[i - 252] - 1


by_snap = {s["ticker"]: s for s in snaps}
print("\nTask 6.2 characteristic battery, EDGAR-augmented snapshot, production score:")
chars = {
    "log_mcap": lambda s: math.log(s["market_cap"]) if isinstance(s.get("market_cap"), (int, float)) and s["market_cap"] > 0 else None,
    "book_to_market": lambda s: 1.0 / s["price_to_book"] if isinstance(s.get("price_to_book"), (int, float)) and s["price_to_book"] > 0 else None,
    "gross_prof_assets": lambda s: s.get("gross_profits_to_assets"),
    "profit_margin": lambda s: s.get("profit_margin"),
    "asset_growth": lambda s: s.get("asset_growth"),
    "mom_12_1": lambda s: mom_12_1(s["ticker"]),
}
for name, fn in chars.items():
    xs, ys = [], []
    for t in tickers:
        v = fn(by_snap[t])
        if isinstance(v, (int, float)) and not math.isnan(v):
            xs.append(v)
            ys.append(prod[t])
    rho, pv = stats.spearmanr(ys, xs)
    print(f"  {name:20s} rho {rho:+.3f}  p {pv:.1e}  n {len(xs)}")
