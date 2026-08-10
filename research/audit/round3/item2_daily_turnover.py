"""Item 2 (daily-frequency portion): turnover across consecutive pit_store refreshes.

Uses the last refresh of each day. Turnover here is top-decile name turnover:
1 - |top_t intersect top_t+1| / N, on the tickers common to both days so universe
membership churn cannot masquerade as signal churn. Membership churn is reported
separately. Band-flicker is measured per metric: champion normalized score changed
while the raw input moved less than 1 percent in relative terms.
"""
import json
import numpy as np
from collections import defaultdict

REPO = "/Users/eyerise/Documents/GitHub/Dash"
DAYS = ["2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10"]

settings = json.load(open(f"{REPO}/pipeline/config/settings.json"))
fcfg = settings["fundamentals"]
CAT_W, MET_W = fcfg["category_weights"], fcfg["metric_weights"]


def load_day(day):
    rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/{day}.jsonl")]
    latest = max(r["refresh_id"] for r in rows)
    return {r["ticker"]: r for r in rows if r["refresh_id"] == latest}


def weighted_available(scores, weights):
    avail = [(scores[k], weights[k]) for k in weights if scores.get(k) is not None]
    if not avail:
        return None
    return sum(s * w for s, w in avail) / sum(w for _, w in avail)


def fundamentals_composite(row, mode):
    ms = row["normalized_metric_scores"][mode]
    cats = {c: weighted_available({m: ms.get(m) for m in ws}, ws) for c, ws in MET_W.items()}
    return weighted_available(cats, CAT_W)


def topdecile_turnover(scores_prev, scores_next):
    common = [t for t in scores_prev if t in scores_next
              and scores_prev[t] is not None and scores_next[t] is not None]
    n = max(1, len(common) // 10)
    top_prev = set(sorted(common, key=lambda t: (-scores_prev[t], t))[:n])
    top_next = set(sorted(common, key=lambda t: (-scores_next[t], t))[:n])
    return 1 - len(top_prev & top_next) / n, len(common), n


snapshots = {d: load_day(d) for d in DAYS}
variants = {
    "full champion (published score)": lambda r: r["scores"]["champion"],
    "full challenger (published score)": lambda r: r["scores"]["challenger"],
    "fundamentals only, band mode": lambda r: fundamentals_composite(r, "champion"),
    "fundamentals only, cross-sectional": lambda r: fundamentals_composite(r, "challenger"),
}

print("top-decile daily turnover by variant (common tickers only):")
results = defaultdict(list)
for a, b in zip(DAYS, DAYS[1:]):
    ra, rb = snapshots[a], snapshots[b]
    line = f"  {a}->{b}"
    for name, fn in variants.items():
        sa = {t: fn(r) for t, r in ra.items()}
        sb = {t: fn(r) for t, r in rb.items()}
        to, ncommon, n = topdecile_turnover(sa, sb)
        results[name].append(to)
        line += f"  {name.split(' ')[0][:4]}:{to:.2f}"
    common = len(set(ra) & set(rb))
    union = len(set(ra) | set(rb))
    print(line + f"   common {common} union {union} (membership churn {1-common/union:.2f})")

print("\nmean daily top-decile turnover:")
for name, vals in results.items():
    print(f"  {name:38s} {np.mean(vals):.3f}")

# band flicker: champion metric score changed while raw moved < 1%
flicker = defaultdict(int)
changed = defaultdict(int)
raw_moved = defaultdict(int)
for a, b in zip(DAYS, DAYS[1:]):
    ra, rb = snapshots[a], snapshots[b]
    for t in set(ra) & set(rb):
        ma, mb = ra[t]["normalized_metric_scores"]["champion"], rb[t]["normalized_metric_scores"]["champion"]
        wa, wb = ra[t].get("raw_metric_inputs") or {}, rb[t].get("raw_metric_inputs") or {}
        for m in mb:
            va, vb = ma.get(m), mb.get(m)
            if va is None or vb is None or va == vb:
                continue
            changed[m] += 1
            xa, xb = wa.get(m), wb.get(m)
            if isinstance(xa, (int, float)) and isinstance(xb, (int, float)) and xa != 0:
                if abs(xb - xa) / abs(xa) < 0.01:
                    flicker[m] += 1
                else:
                    raw_moved[m] += 1

total_changed = sum(changed.values())
total_flicker = sum(flicker.values())
print(f"\nchampion metric-score changes across {len(DAYS)-1} day-pairs: {total_changed}")
print(f"of which raw input moved <1%% (pure band flicker): {total_flicker} ({total_flicker/max(1,total_changed)*100:.0f}%)")
print("top flickering metrics:")
for m, k in sorted(flicker.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {m:32s} flicker {k:4d} of {changed[m]:4d} changes")

# challenger comparison: same flicker definition on cross-sectional scores.
# A cs score changes whenever the universe distribution moves, so 'changed' is near-universal;
# report how many cs changes exceed 5 points with raw moved <1% (rank-relevant churn).
cs_big = cs_all = 0
for a, b in zip(DAYS, DAYS[1:]):
    ra, rb = snapshots[a], snapshots[b]
    for t in set(ra) & set(rb):
        ma, mb = ra[t]["normalized_metric_scores"]["challenger"], rb[t]["normalized_metric_scores"]["challenger"]
        wa, wb = ra[t].get("raw_metric_inputs") or {}, rb[t].get("raw_metric_inputs") or {}
        for m in mb:
            va, vb = ma.get(m), mb.get(m)
            if va is None or vb is None:
                continue
            xa, xb = wa.get(m), wb.get(m)
            if isinstance(xa, (int, float)) and isinstance(xb, (int, float)) and xa != 0 and abs(xb - xa) / abs(xa) < 0.01:
                cs_all += 1
                if abs(vb - va) > 5:
                    cs_big += 1
print(f"\ncross-sectional: raw-stable observations {cs_all}, of which score moved >5 points: {cs_big} ({cs_big/max(1,cs_all)*100:.1f}%)")
