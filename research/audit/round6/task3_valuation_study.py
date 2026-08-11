"""Task 3: where does the valuation block's value exposure go?

Three questions, all on the pinned refresh with EDGAR-augmented raw metrics:
1. Which of the eight valuation metrics individually carry value exposure (rank
   correlation with book-to-market, trailing earnings yield, and EBITDA/EV)?
2. Does the category score preserve or destroy the exposure its constituents carry,
   under band mode and under fixed-feature imputation?
3. How much of the fixed-feature attenuation is the imputation-shrinkage mechanism
   Round 5 characterized (dilution proportional to imputed weight)?

Value proxies are computed from raw inputs, sector-demeaned variants included, so the
exposure question is separated from sector composition.
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

# Value proxies per name.
def proxies(s):
    out = {}
    pb = s.get("price_to_book")
    out["book_to_market"] = 1.0 / pb if isinstance(pb, (int, float)) and pb > 0 else None
    pe = s.get("trailing_pe") or s.get("forward_pe")
    out["earnings_yield"] = 1.0 / pe if isinstance(pe, (int, float)) and pe > 0 else None
    ee = s.get("ev_to_ebitda")
    out["ebitda_to_ev"] = 1.0 / ee if isinstance(ee, (int, float)) and ee > 0 else None
    return out


VAL_METRICS = ["ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "forward_pe", "peg",
               "price_to_sales", "price_to_book", "price_to_tangible_book"]
PROXIES = ["book_to_market", "earnings_yield", "ebitda_to_ev"]

px = {s["ticker"]: proxies(s) for s in snaps}
sector_of = {s["ticker"]: s.get("sector") for s in snaps}


def spear(pairs):
    a = np.array(pairs)
    if len(a) < 30:
        return None, None, len(a)
    rho, p = stats.spearmanr(a[:, 0], a[:, 1])
    return rho, p, len(a)


print("1. Raw metric vs value proxy, Spearman (negative for a multiple means cheap "
      "names score as cheap, which IS value exposure):")
print(f"{'metric':24s} " + " ".join(f"{p:>26s}" for p in PROXIES))
for m in VAL_METRICS:
    line = f"{m:24s} "
    for pr in PROXIES:
        pairs = [(s.get(m), px[s['ticker']][pr]) for s in snaps
                 if isinstance(s.get(m), (int, float)) and s.get(m) > 0
                 and px[s["ticker"]][pr] is not None]
        rho, p, n = spear(pairs)
        line += f"  {rho:+.2f} (p {p:.0e}, n {n:4d})" if rho is not None else f"  {'n<30':>22s}"
    print(line)

# 2. Category score vs proxies under both modes.
nz = CrossSectionalNormalizer(snaps)
cat_band, cat_ff, ff_imputed_val = {}, {}, {}
for s in snaps:
    t = s["ticker"]
    _b, bp = scorer.valuation_score(s, mode="bands")
    _f, fp = scorer.valuation_score(s, mode="fixed_feature", normalizer=nz)
    if bp:
        cat_band[t] = (bp.get("categories") or {}).get("valuation")
    if fp:
        cat_ff[t] = (fp.get("categories") or {}).get("valuation")
        norm = fp.get("normalization") or {}
        val_metrics_reg = list(scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"])
        imputed = [m for m in fp.get("imputed_metrics", []) if m in val_metrics_reg]
        weights = scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"]
        ff_imputed_val[t] = sum(weights.get(m, 0) for m in imputed) / max(sum(weights.values()), 1e-9)

print("\n2. Valuation CATEGORY score vs value proxies:")
for label, cat in (("band mode", cat_band), ("fixed_feature", cat_ff)):
    line = f"{label:24s} "
    for pr in PROXIES:
        pairs = [(cat[t], px[t][pr]) for t in cat
                 if cat[t] is not None and px[t][pr] is not None]
        rho, p, n = spear(pairs)
        line += f"  {rho:+.2f} (p {p:.0e}, n {n:4d})" if rho is not None else "  n<30"
    print(line)

# Sector-demeaned category exposure (band mode), to separate composition from tilt.
by_sector = defaultdict(list)
for t, v in cat_band.items():
    if v is not None and px[t]["book_to_market"] is not None:
        by_sector[sector_of[t]].append(t)
pairs = []
for sec, ts in by_sector.items():
    if len(ts) < 8:
        continue
    cvals = np.array([cat_band[t] for t in ts])
    bvals = np.array([px[t]["book_to_market"] for t in ts])
    pairs += list(zip(stats.rankdata(cvals) / len(ts), stats.rankdata(bvals) / len(ts)))
rho, p, n = spear(pairs)
print(f"band category vs B/M, sector-demeaned ranks: {rho:+.2f} (p {p:.0e}, n {n})")

# 3. Attenuation mechanism: fixed-feature category exposure on low-imputation names.
for cut, label in ((0.10, "imputed val weight <= 10%"), (0.5, "imputed <= 50%"), (1.1, "all")):
    pairs = [(cat_ff[t], px[t]["book_to_market"]) for t in cat_ff
             if cat_ff[t] is not None and px[t]["book_to_market"] is not None
             and ff_imputed_val.get(t, 1) <= cut]
    rho, p, n = spear(pairs)
    if rho is not None:
        print(f"fixed_feature category vs B/M, {label:28s}: {rho:+.2f} (p {p:.0e}, n {n})")

# Challenger blocks, scored cross-sectionally, sector scope where peers allow.
print("\n4. Challenger blocks (cross-sectional percentile, sector-conditional):")
for label, weights in (("two-metric EV block (EBITDA 60/FCF 40)",
                        {"ev_to_ebitda": 0.6, "ev_to_fcf": 0.4}),
                       ("single-metric EV/EBITDA", {"ev_to_ebitda": 1.0}),
                       ("eight-metric incumbent",
                        scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"])):
    block = {}
    for s in snaps:
        t = s["ticker"]
        num = den = 0.0
        for m, w in weights.items():
            sc, _d = nz.score(m, s.get(m), s.get("sector"), t)
            if sc is not None:
                num += sc * w
                den += w
        if den > 0:
            block[t] = num / den
    line = f"{label:40s} "
    for pr in PROXIES:
        pairs = [(block[t], px[t][pr]) for t in block if px[t][pr] is not None]
        rho, p, n = spear(pairs)
        line += f"  {rho:+.2f} (n {n:4d})" if rho is not None else "  n<30"
    print(line)
