"""Item 5: production coverage-pull vs v2 neutral-target shrinkage on identical inputs.

Production (advisor_engine.py:846-867): base = raw * (0.8 + 0.2 * coverage)
v2 form   (advisor_engine.py:870-895):  base = 50 + strength * (raw - 50), strength = coverage

Reconstructs raw from published rows: base = score - modifier_total (valid while the
final score is unclamped), raw = base / (0.8 + 0.2 * coverage). Both transforms are then
applied to the same raw and coverage, modifiers excluded from both, and rankings compared.
"""
import json
import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

recs = []
for r in rows:
    s = r["scores"]["champion"]
    c = (r.get("confidence") or r["data_coverage"])["champion"]
    mods = r["modifiers"]["champion"]
    m = mods.get("total")
    if m is None:
        m = sum((mods.get("applied") or {}).values())
    if s is None or c is None:
        continue
    base = s - m
    if base <= 0 or base >= 100 or s <= 0 or s >= 100:
        continue  # clamped rows cannot be inverted exactly
    raw = base / (0.8 + 0.2 * c)
    prod = raw * (0.8 + 0.2 * c)          # equals base by construction
    v2 = 50 + c * (raw - 50)
    recs.append({"ticker": r["ticker"], "raw": raw, "conf": c,
                 "prod": prod, "v2": v2,
                 "sector": (r.get("raw_metric_inputs") or {}).get("sector")})

n = len(recs)
prod_rank = stats.rankdata([-x["prod"] for x in recs], method="average")
v2_rank = stats.rankdata([-x["v2"] for x in recs], method="average")
raw_rank = stats.rankdata([-x["raw"] for x in recs], method="average")
for x, pr, vr, rr in zip(recs, prod_rank, v2_rank, raw_rank):
    x["prod_rank"], x["v2_rank"], x["raw_rank"] = pr, vr, rr
    x["shift"] = pr - vr  # positive: production ranks it WORSE than v2 would

shifts = np.array([x["shift"] for x in recs])
conf = np.array([x["conf"] for x in recs])
raws = np.array([x["raw"] for x in recs])

print("n usable rows:", n, "of", len(rows))
print("confidence: min %.2f p10 %.2f median %.2f p90 %.2f max %.2f" % (
    conf.min(), *np.percentile(conf, [10, 50, 90]), conf.max()))
print("rank shift (prod_rank - v2_rank): mean %.1f sd %.1f  |shift| p50 %.1f p90 %.1f max %.1f" % (
    shifts.mean(), shifts.std(), *np.percentile(np.abs(shifts), [50, 90]), np.abs(shifts).max()))
print("names moving >10 ranks: %d (%.1f%%)  >25 ranks: %d  >50 ranks: %d" % (
    (np.abs(shifts) > 10).sum(), (np.abs(shifts) > 10).mean() * 100,
    (np.abs(shifts) > 25).sum(), (np.abs(shifts) > 50).sum()))
print("spearman(prod, v2): %.4f" % stats.spearmanr([x["prod"] for x in recs], [x["v2"] for x in recs])[0])
print("spearman(conf, prod_rank): %.3f   spearman(conf, v2_rank): %.3f   spearman(conf, raw_rank): %.3f" % (
    stats.spearmanr(conf, prod_rank)[0], stats.spearmanr(conf, v2_rank)[0],
    stats.spearmanr(conf, raw_rank)[0]))

# The directional-bias test: among ABOVE-neutral names (raw > 50), production penalizes
# low confidence. Among BELOW-neutral names, production REWARDS low confidence (a bad
# stock with thin data outranks the same stock with full data under prod, and the
# reverse under v2).
hi = [x for x in recs if x["raw"] > 50]
lo = [x for x in recs if x["raw"] <= 50]
for name, grp in (("raw>50", hi), ("raw<=50", lo)):
    g_conf = np.array([x["conf"] for x in grp])
    g_shift = np.array([x["shift"] for x in grp])
    print(f"{name}: n={len(grp)}  corr(conf, shift)={stats.spearmanr(g_conf, g_shift)[0]:.3f}  "
          f"mean shift low-conf tercile {g_shift[g_conf <= np.percentile(g_conf, 33)].mean():+.1f}  "
          f"high-conf tercile {g_shift[g_conf >= np.percentile(g_conf, 67)].mean():+.1f}")

print("\nTen names production penalizes most vs v2 (high raw, thin data):")
worst = sorted(recs, key=lambda x: -x["shift"])[:10]
for x in worst:
    print(f"  {x['ticker']:6s} raw {x['raw']:5.1f} conf {x['conf']:.2f} "
          f"prod_rank {x['prod_rank']:5.0f} v2_rank {x['v2_rank']:5.0f} shift {x['shift']:+5.0f}  {x['sector']}")
print("\nTen names production rewards most vs v2 (low raw, thin data):")
best = sorted(recs, key=lambda x: x["shift"])[:10]
for x in best:
    print(f"  {x['ticker']:6s} raw {x['raw']:5.1f} conf {x['conf']:.2f} "
          f"prod_rank {x['prod_rank']:5.0f} v2_rank {x['v2_rank']:5.0f} shift {x['shift']:+5.0f}  {x['sector']}")
