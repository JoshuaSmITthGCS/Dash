"""Task 3: measure the fixed-feature imputation challenger against production.

Builds real snapshots from the pinned pit refresh's raw inputs (EDGAR-augmented, so the
comparison runs at restored coverage), fits the production CrossSectionalNormalizer on
them, and scores every name three ways:

  production      band champion + within-block renormalization + two coverage multipliers
  fixed_feature   same intended weight vector for every name, neutral imputation,
                  no completeness multiplier (scorer.valuation_score mode="fixed_feature")
  ff + shrink     fixed_feature then one neutral-target shrink (constant-50 prior and
                  sector-mean prior variants)

Reported: Spearman(coverage, score) per mode, rank correlation to production, rank-shift
distribution, ten most-affected names, financials-vs-rest gap.
"""
import json
import sys
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

snaps = []
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

nz = CrossSectionalNormalizer(snaps)
prod, ff, covs, sectors = {}, {}, {}, {}
ff_detail = {}
for snap in snaps:
    t = snap["ticker"]
    p_score, p_parts = scorer.valuation_score(snap, mode="bands")
    f_score, f_parts = scorer.valuation_score(snap, mode="fixed_feature", normalizer=nz)
    if p_score is None or f_score is None:
        continue
    prod[t], ff[t] = p_score, f_score
    covs[t] = f_parts.get("coverage", 0.0)
    sectors[t] = snap.get("sector")
    ff_detail[t] = f_parts

tickers = sorted(prod)
p = np.array([prod[t] for t in tickers])
f = np.array([ff[t] for t in tickers])
c = np.array([covs[t] for t in tickers])
print("n scored:", len(tickers), " mean observed-weight coverage %.2f" % c.mean())

# Shrinkage variants on the fixed-feature score.
univ_mean = f.mean()
sector_means = defaultdict(list)
for t in tickers:
    sector_means[sectors[t]].append(ff[t])
sector_means = {s: np.mean(v) for s, v in sector_means.items() if len(v) >= 8}
shrunk50 = np.array([50 + c[i] * (f[i] - 50) for i in range(len(tickers))])
shrunk_sector = np.array([
    (sector_means.get(sectors[t], univ_mean)) + c[i] * (f[i] - sector_means.get(sectors[t], univ_mean))
    for i, t in enumerate(tickers)])

print("\nSpearman(observed-weight coverage, score):")
for name, arr in (("production (bands + 2 multipliers)", p),
                  ("fixed_feature, no shrink", f),
                  ("fixed_feature + shrink to 50", shrunk50),
                  ("fixed_feature + shrink to sector mean", shrunk_sector)):
    rho, pv = stats.spearmanr(c, arr)
    print(f"  {name:40s} rho {rho:+.3f}  p {pv:.1e}")

rho_pf = stats.spearmanr(p, f)[0]
print("\nrank correlation production vs fixed_feature: %.3f" % rho_pf)
pr = stats.rankdata(-p)
fr = stats.rankdata(-f)
shift = pr - fr
print("rank shifts: mean |shift| %.1f  >25: %d  >50: %d  max %d" % (
    np.abs(shift).mean(), (np.abs(shift) > 25).sum(), (np.abs(shift) > 50).sum(),
    int(np.abs(shift).max())))

print("\nten names the redesign moves most (production rank -> fixed-feature rank):")
order = np.argsort(-np.abs(shift))[:10]
for i in order:
    t = tickers[i]
    d = ff_detail[t]
    print(f"  {t:6s} {int(pr[i]):4d} -> {int(fr[i]):4d}  cov {covs[t]:.2f}  "
          f"imputed_w {d.get('imputed_weight_fraction'):.2f}  {sectors[t]}")

fin = [i for i, t in enumerate(tickers) if sectors[t] in ("Financial Services", "Financials")]
oth = [i for i in range(len(tickers)) if i not in fin]
for name, arr in (("production", p), ("fixed_feature", f), ("ff+sector-shrink", shrunk_sector)):
    u = stats.mannwhitneyu(arr[fin], arr[oth])
    print(f"\n{name}: financials mean {arr[fin].mean():.1f} vs others {arr[oth].mean():.1f} "
          f"(gap {arr[fin].mean()-arr[oth].mean():+.1f}, Mann-Whitney p {u[1]:.3f})")
