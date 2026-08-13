"""Task 1: category-vs-B/M exposure before and after orthogonalization, section 3.3 format."""
import json
import sys

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")
import scorer
from edgar_enrichment import edgar_extended

rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

CAT_W = scorer.SETTINGS["fundamentals"]["category_weights"]
ORTHO = ("profitability", "growth", "financial_health")
cats_all, bm_all, cov_all = {}, {}, {}
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
    snap = {**raw, "ticker": r["ticker"], "is_etf": False}
    _s, parts = scorer.valuation_score(snap, mode="bands")
    pb = raw.get("price_to_book")
    if not parts or not isinstance(pb, (int, float)) or pb <= 0:
        continue
    t = r["ticker"]
    cats_all[t] = dict(parts.get("categories") or {})
    bm_all[t] = 1.0 / pb
    cov_all[t] = parts.get("coverage", 0.0)

tickers = sorted(cats_all)
bm = np.array([bm_all[t] for t in tickers])
lbm = np.log(bm)

def spear(vals):
    pairs = [(v, b) for v, b in vals if v is not None]
    a = np.array(pairs)
    rho, p = stats.spearmanr(a[:, 0], a[:, 1])
    return rho, p, len(a)

adjusted = {t: dict(cats_all[t]) for t in tickers}
for cat in ORTHO:
    idx = [i for i, t in enumerate(tickers) if cats_all[t].get(cat) is not None]
    y = np.array([cats_all[tickers[i]][cat] for i in idx], dtype=float)
    X = np.column_stack([np.ones(len(idx)), lbm[idx]])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    adj = np.clip(resid * (y.std(ddof=1) / max(resid.std(ddof=1), 1e-9)) + y.mean(), 0, 100)
    for j, i in enumerate(idx):
        adjusted[tickers[i]][cat] = float(adj[j])

def composite(cats_by_t):
    out = {}
    for t in tickers:
        avail = [(cats_by_t[t][c], CAT_W[c]) for c in CAT_W
                 if cats_by_t[t].get(c) is not None]
        if avail:
            raw = sum(v * w for v, w in avail) / sum(w for _v, w in avail)
            out[t] = raw * (0.65 + 0.35 * cov_all[t])
    return out

print(f"{'category':22s} {'weight':>6s} {'before rho':>16s} {'after rho':>16s}")
for c in ("valuation", "profitability", "growth", "financial_health",
          "capital_allocation", "accounting_quality"):
    b = spear([(cats_all[t].get(c), bm_all[t]) for t in tickers])
    a = spear([(adjusted[t].get(c), bm_all[t]) for t in tickers])
    print(f"{c:22s} {CAT_W[c]:6.2f} {b[0]:+7.3f} (n {b[2]:4d}) {a[0]:+7.3f} (n {a[2]:4d})")
cb = composite(cats_all)
ca = composite(adjusted)
b = spear([(cb.get(t), bm_all[t]) for t in tickers])
a = spear([(ca.get(t), bm_all[t]) for t in tickers])
print(f"{'composite':22s} {'':6s} {b[0]:+7.3f} (n {b[2]:4d}) {a[0]:+7.3f} (n {a[2]:4d})")
rho_pa = stats.spearmanr([cb[t] for t in tickers if t in cb and t in ca],
                          [ca[t] for t in tickers if t in cb and t in ca])[0]
print(f"rank correlation before vs after composite: {rho_pa:.3f}")

# EBITDA/EV diagnostic only.
ee = {t: None for t in tickers}
for r in rows:
    t = r["ticker"]
    if t in ee:
        v = (r.get("raw_metric_inputs") or {}).get("ev_to_ebitda")
        ee[t] = 1.0 / v if isinstance(v, (int, float)) and v > 0 else None
d = spear([(ca.get(t), ee[t]) for t in tickers if ee[t] is not None])
print(f"diagnostic: after-composite vs EBITDA/EV: {d[0]:+.3f} (n {d[2]})")
