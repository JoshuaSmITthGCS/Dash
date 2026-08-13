"""Item 4: coverage comparability. Does the model rank data availability?

Fundamentals coverage is recomputed per name from the published champion metric scores
using the exact weighted_coverage() weighting (scorer.py:496-512). Suppression sets are
not stored in pit rows, so financial-profile names have coverage understated here; the
sector split below shows that effect explicitly instead of hiding it.
"""
import json
import math
import numpy as np
from scipy import stats
from collections import defaultdict

REPO = "/Users/eyerise/Documents/GitHub/Dash"
rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

settings = json.load(open(f"{REPO}/pipeline/config/settings.json"))
fcfg = settings["fundamentals"]
CAT_W, MET_W = fcfg["category_weights"], fcfg["metric_weights"]

def weighted_coverage(metrics):
    answered = total = 0.0
    for cat, ws in MET_W.items():
        cw = CAT_W.get(cat, 0)
        for m, w in ws.items():
            share = cw * w
            total += share
            if metrics.get(m) is not None:
                answered += share
    return answered / total if total else 0.0

recs = []
for r in rows:
    ch = r["normalized_metric_scores"]["champion"]
    raw = r.get("raw_metric_inputs") or {}
    s = r["scores"]["champion"]
    if s is None:
        continue
    recs.append({
        "ticker": r["ticker"], "score": s,
        "fcov": weighted_coverage(ch),
        "dcov": (r.get("confidence") or r["data_coverage"])["champion"],
        "mcap": raw.get("market_cap"), "sector": raw.get("sector"),
    })

fcov = np.array([x["fcov"] for x in recs])
score = np.array([x["score"] for x in recs])
print("n:", len(recs))
print("fundamentals coverage deciles:",
      [round(v, 2) for v in np.percentile(fcov, range(10, 100, 10))])
print("min %.2f max %.2f mean %.2f" % (fcov.min(), fcov.max(), fcov.mean()))

rho, p = stats.spearmanr(fcov, score)
pr = stats.pearsonr(fcov, score)
print("spearman(coverage, final champion score) = %.3f (p=%.1e)   pearson = %.3f" % (rho, p, pr[0]))

# combined multiplicative coverage penalty: (0.65+0.35*fcov) * (0.8+0.2*dcov)
dcov = np.array([x["dcov"] for x in recs])
mult = (0.65 + 0.35 * fcov) * (0.8 + 0.2 * dcov)
print("combined coverage multiplier on fundamentals evidence: min %.2f p10 %.2f median %.2f p90 %.2f max %.2f" % (
    mult.min(), *np.percentile(mult, [10, 50, 90]), mult.max()))
print("max/min score ratio purely from coverage: %.2f" % (mult.max() / mult.min()))

mc = np.array([x["mcap"] if isinstance(x["mcap"], (int, float)) else np.nan for x in recs])
mask = ~np.isnan(mc)
rho_mc = stats.spearmanr(fcov[mask], np.log(mc[mask]))
print("spearman(coverage, log market cap) = %.3f (p=%.1e), n=%d" % (rho_mc[0], rho_mc[1], mask.sum()))

rho_sc = stats.spearmanr(np.log(mc[mask]), score[mask])
print("spearman(log mcap, score) = %.3f" % rho_sc[0])

print("\ncoverage and score by sector:")
by_sector = defaultdict(list)
for x in recs:
    by_sector[x["sector"] or "?"].append(x)
fin_scores, other_scores = [], []
for sec, grp in sorted(by_sector.items(), key=lambda kv: -len(kv[1])):
    if len(grp) < 5:
        continue
    f = np.array([g["fcov"] for g in grp]); s = np.array([g["score"] for g in grp])
    print(f"  {sec:24s} n={len(grp):3d}  cov mean {f.mean():.2f}  score mean {s.mean():5.1f} median {np.median(s):5.1f}")
    (fin_scores if sec in ("Financial Services", "Financials") else other_scores).extend(s)
fin, oth = np.array(fin_scores), np.array(other_scores)
t = stats.mannwhitneyu(fin, oth)
print("\nFinancials: n=%d mean %.1f median %.1f  vs others: n=%d mean %.1f median %.1f  (Mann-Whitney p=%.3f)" % (
    len(fin), fin.mean(), np.median(fin), len(oth), oth.mean(), np.median(oth), t[1]))

# forward return vs coverage: check whether any pit rows have realized horizons
realized = 0
for day in ["2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10"]:
    for line in open(f"{REPO}/pipeline/pit_store/{day}.jsonl"):
        if '"forward_return' in line or '"realized' in line:
            realized += 1
            break
print("\npit rows with realized forward returns:", realized)
