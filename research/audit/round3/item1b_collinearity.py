import json
import numpy as np
from collections import defaultdict

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

for mode in ("champion", "challenger"):
    src = collect(mode)
    n = len(VAL)
    C = np.eye(n)
    Ns = np.zeros((n, n), int)
    for i in range(n):
        for j in range(i + 1, n):
            common = set(src[VAL[i]]) & set(src[VAL[j]])
            Ns[i, j] = Ns[j, i] = len(common)
            if len(common) > 10:
                a = np.array([src[VAL[i]][t] for t in common])
                b = np.array([src[VAL[j]][t] for t in common])
                C[i, j] = C[j, i] = np.corrcoef(a, b)[0, 1]
    eig = np.linalg.eigvalsh(C)[::-1]
    eig = np.clip(eig, 0, None)
    print(f"== {mode} (pairwise complete) ==")
    print("coverage per metric:", {m: len(src[m]) for m in VAL})
    print("min/median pair N:", Ns[np.triu_indices(n,1)].min(), int(np.median(Ns[np.triu_indices(n,1)])))
    off = C[np.triu_indices(n, 1)]
    print("mean offdiag corr:", round(float(off.mean()), 3),
          " first eig share:", round(float(eig[0] / eig.sum()), 3))
    hdr = "          " + " ".join(f"{m[:7]:>7s}" for m in VAL)
    print(hdr)
    for i, m in enumerate(VAL):
        print(f"{m[:9]:9s} " + " ".join(f"{C[i,j]:7.2f}" for j in range(n)))
    # core-5 complete case (drop ptb, peg, keep high-coverage): 
    core = ["ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "forward_pe", "sales_multiple"]
    tick = set.intersection(*[set(src[m]) for m in core])
    X = np.array([[src[m][t] for m in core] for t in sorted(tick)])
    Cc = np.corrcoef(X, rowvar=False)
    e = np.linalg.eigvalsh(Cc)[::-1]
    print(f"core-5 complete case n={len(tick)}: mean offdiag "
          f"{float((Cc.sum()-5)/20):.3f}, first eig share {float(e[0]/e.sum()):.3f}")
    print()
