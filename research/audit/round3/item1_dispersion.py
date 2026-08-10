"""Item 1: band vs cross-sectional dispersion on one identical snapshot.

Uses the latest full refresh in pipeline/pit_store/2026-08-10.jsonl. Both modes'
normalized metric scores were written by the production pipeline itself
(scorer.py band functions and CrossSectionalNormalizer) on the same raw inputs,
so this compares the two normalizers with zero re-implementation drift.
"""
import json
import math
from collections import Counter, defaultdict

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
DAY = f"{REPO}/pipeline/pit_store/2026-08-10.jsonl"

settings = json.load(open(f"{REPO}/pipeline/config/settings.json"))
fcfg = settings["fundamentals"]
CAT_W = fcfg["category_weights"]
MET_W = fcfg["metric_weights"]  # category -> {metric: weight}
METRIC_CAT = {m: c for c, ws in MET_W.items() for m in ws}

rows = [json.loads(l) for l in open(DAY)]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]
print("refresh:", latest, "rows:", len(rows))

VAL_METRICS = list(MET_W["valuation"])


def collect(mode):
    per_metric = defaultdict(dict)
    for r in rows:
        t = r["ticker"]
        for m, v in (r.get("normalized_metric_scores", {}).get(mode) or {}).items():
            if isinstance(v, (int, float)):
                per_metric[m][t] = float(v)
    return per_metric


champ = collect("champion")
chall = collect("challenger")


def metric_stats(values):
    a = np.array(list(values))
    sd = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
    iqr = float(np.percentile(a, 75) - np.percentile(a, 25))
    modal = Counter(np.round(a, 1)).most_common(1)[0][1] / len(a)
    distinct = len(set(np.round(a, 1)))
    return {"n": len(a), "sd": round(sd, 1), "iqr": round(iqr, 1),
            "modal_frac": round(modal, 3), "distinct": distinct}


report = {"refresh": latest, "n_rows": len(rows), "metrics": {}}
for m in sorted(set(champ) | set(chall)):
    entry = {}
    if m in champ:
        entry["band"] = metric_stats(champ[m].values())
    if m in chall:
        entry["cs"] = metric_stats(chall[m].values())
    entry["category"] = METRIC_CAT.get(m)
    report["metrics"][m] = entry


def weighted_available(scores, weights):
    avail = [(scores[k], weights[k]) for k in weights if scores.get(k) is not None]
    if not avail:
        return None
    return sum(s * w for s, w in avail) / sum(w for _, w in avail)


def composites(mode_scores):
    """Category scores and fundamentals composite per ticker, mirroring scorer.py."""
    cats_out = defaultdict(dict)
    comp_out = {}
    tickers = set()
    for m in mode_scores:
        tickers |= set(mode_scores[m])
    for t in tickers:
        cats = {}
        for c, ws in MET_W.items():
            cats[c] = weighted_available({m: mode_scores[m].get(t) for m in ws}, ws)
        comp = weighted_available(cats, CAT_W)
        if comp is not None:
            comp_out[t] = round(comp, 1)
            for c, v in cats.items():
                if v is not None:
                    cats_out[c][t] = round(v, 1)
    return cats_out, comp_out


champ_cats, champ_comp = composites(champ)
chall_cats, chall_comp = composites(chall)

report["categories"] = {}
for c in CAT_W:
    report["categories"][c] = {
        "band": metric_stats(champ_cats[c].values()),
        "cs": metric_stats(chall_cats[c].values()),
    }

common = sorted(set(champ_comp) & set(chall_comp))
a = np.array([champ_comp[t] for t in common])
b = np.array([chall_comp[t] for t in common])
rho, p = stats.spearmanr(a, b)
report["composite"] = {
    "n_common": len(common),
    "spearman": round(float(rho), 3),
    "band": metric_stats(a),
    "cs": metric_stats(b),
}

# Effective rank dispersion: SD of percentile ranks (ties share average rank).
for name, arr in (("band", a), ("cs", b)):
    pct = stats.rankdata(arr, method="average") / len(arr) * 100
    report["composite"][name]["rank_sd"] = round(float(np.std(pct, ddof=1)), 1)

# Valuation collinearity: correlation matrix on complete cases, first eigenvalue share.
report["valuation_collinearity"] = {}
for name, source in (("band", champ), ("cs", chall)):
    tickers = set.intersection(*[set(source.get(m, {})) for m in VAL_METRICS])
    X = np.array([[source[m][t] for m in VAL_METRICS] for t in sorted(tickers)])
    C = np.corrcoef(X, rowvar=False)
    eig = np.linalg.eigvalsh(C)[::-1]
    report["valuation_collinearity"][name] = {
        "n_complete": len(tickers),
        "mean_offdiag_corr": round(float((C.sum() - len(VAL_METRICS)) /
                                         (len(VAL_METRICS) ** 2 - len(VAL_METRICS))), 3),
        "first_eig_share": round(float(eig[0] / eig.sum()), 3),
        "corr_matrix": [[round(float(x), 2) for x in row] for row in C],
        "metrics": VAL_METRICS,
    }

out = "/private/tmp/claude-501/-Users-eyerise-Documents-GitHub-Dash/2d12605e-76ba-4f6c-83bd-a90aa6a3e36a/scratchpad/item1_results.json"
json.dump(report, open(out, "w"), indent=1)

print(f"{'metric':34s} {'cat':12s} {'SD b/cs':>12s} {'IQR b/cs':>12s} {'modal b/cs':>12s} {'distinct b/cs':>14s}")
for m, e in sorted(report["metrics"].items(), key=lambda kv: (kv[1].get("category") or "z", kv[0])):
    bb, cc = e.get("band"), e.get("cs")
    if not bb or not cc:
        continue
    print(f"{m:34s} {str(e['category'])[:12]:12s} "
          f"{bb['sd']:5.1f}/{cc['sd']:5.1f} {bb['iqr']:5.1f}/{cc['iqr']:5.1f} "
          f"{bb['modal_frac']:5.3f}/{cc['modal_frac']:5.3f} {bb['distinct']:6d}/{cc['distinct']:6d}")
print()
for c, e in report["categories"].items():
    print(f"CAT {c:22s} SD {e['band']['sd']:5.1f}/{e['cs']['sd']:5.1f}  IQR {e['band']['iqr']:5.1f}/{e['cs']['iqr']:5.1f}  modal {e['band']['modal_frac']:.3f}/{e['cs']['modal_frac']:.3f}")
print()
print("composite:", json.dumps(report["composite"], indent=1))
print("valuation collinearity:",
      {k: {kk: vv for kk, vv in v.items() if kk != "corr_matrix"}
       for k, v in report["valuation_collinearity"].items()})
