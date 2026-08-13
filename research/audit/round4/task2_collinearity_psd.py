"""Task 2: validity of Round 3's collinearity statistics.

Tests both pairwise-complete valuation correlation matrices for positive
semi-definiteness, reports the per-cell sample matrix, and re-runs the measurement on
complete cases and on a neutral-imputed matrix. Pinned to pit refresh
advisor-2026-08-10T17:22:04 (file sha256 54f86b3e9bf861a4...).
"""
import json
from collections import defaultdict

import numpy as np

REPO = "/Users/eyerise/Documents/GitHub/Dash"
rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

VAL = ["ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "forward_pe", "peg",
       "sales_multiple", "price_to_book", "price_to_tangible_book"]


def collect(mode):
    per = defaultdict(dict)
    for r in rows:
        for m in VAL:
            v = (r.get("normalized_metric_scores", {}).get(mode) or {}).get(m)
            if isinstance(v, (int, float)):
                per[m][r["ticker"]] = float(v)
    return per


def eig_stats(C):
    eig = np.linalg.eigvalsh(C)
    return eig.min(), eig.max() / eig.sum() if eig.sum() > 0 else float("nan")


for mode in ("champion", "challenger"):
    src = collect(mode)
    n = len(VAL)
    C = np.eye(n)
    N = np.zeros((n, n), int)
    for i in range(n):
        for j in range(i + 1, n):
            common = set(src[VAL[i]]) & set(src[VAL[j]])
            N[i, j] = N[j, i] = len(common)
            if len(common) > 10:
                a = np.array([src[VAL[i]][t] for t in common])
                b = np.array([src[VAL[j]][t] for t in common])
                C[i, j] = C[j, i] = np.corrcoef(a, b)[0, 1]
    mn, share = eig_stats(C)
    print(f"== {mode} pairwise-complete ==")
    print("per-cell N matrix (upper triangle):")
    for i in range(n):
        print(" ", VAL[i][:12].ljust(13), " ".join(f"{N[i,j]:4d}" for j in range(n)))
    print(f"min eigenvalue {mn:+.4f}  ->  PSD: {mn >= -1e-10}")
    print(f"first-eig share (INVALID if not PSD): {share:.3f}")

    # Complete cases, 8 metrics.
    tick8 = set.intersection(*[set(src[m]) for m in VAL])
    if len(tick8) >= 10:
        X = np.array([[src[m][t] for m in VAL] for t in sorted(tick8)])
        C8 = np.corrcoef(X, rowvar=False)
        mn8, share8 = eig_stats(C8)
        print(f"complete-case 8-metric: n={len(tick8)}  min eig {mn8:+.4f}  first-eig share {share8:.3f}")

    # Neutral-imputed matrix: missing -> 50, all 880 names. This measures the
    # correlation structure the imputation challenger would actually score on.
    tickers = sorted({t for m in VAL for t in src[m]})
    Xi = np.array([[src[m].get(t, 50.0) for m in VAL] for t in tickers])
    Ci = np.corrcoef(Xi, rowvar=False)
    mni, sharei = eig_stats(Ci)
    print(f"neutral-imputed: n={len(tickers)}  min eig {mni:+.4f}  first-eig share {sharei:.3f}")
    off = Ci[np.triu_indices(n, 1)]
    print(f"neutral-imputed mean offdiag {off.mean():.3f}")
    print()
