"""Task 1 analysis: rank distributions, conditioning, component discrimination."""
import json
from collections import defaultdict

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
rows = json.load(open(f"{REPO}/research/audit/survivorship/data/ranking_probe.json"))

scored = [r for r in rows if r.get("status") == "scored"]
unscored = [r for r in rows if r.get("status") != "scored"]
print(f"total name-date rows {len(rows)}: scored {len(scored)}, "
      f"unscored {len(unscored)} ({len(unscored)/len(rows)*100:.0f}%)")

by_year_unscored = defaultdict(lambda: [0, 0])
for r in rows:
    y = r["date"][:4]
    by_year_unscored[y][1] += 1
    if r.get("status") != "scored":
        by_year_unscored[y][0] += 1
print("unscored fraction by rebalance year (stale or missing facts = the "
      "coverage-collapse signal):")
for y in sorted(by_year_unscored):
    u, n = by_year_unscored[y]
    print(f"  {y}: {u}/{n} ({u/n*100:.0f}%)")

TRUE_DEATH = ("bankruptcy", "exchange_rule_removal")
dead_rows = [r for r in scored if r["class"] in TRUE_DEATH]
merger_rows = [r for r in scored if r["class"] == "merger_acquisition"]
print(f"\nscored rows: true-death classes {len(dead_rows)}, mergers {len(merger_rows)}")
print(f"distinct true-death names scored at least once: "
      f"{len({r['cik'] for r in dead_rows})}")

def dist(rows_, label):
    p = np.array([r["pct_vs_survivors"] for r in rows_])
    if len(p) == 0:
        print(f"  {label}: empty")
        return
    print(f"  {label:34s} n {len(p):6d}  median pct {np.median(p):5.1f}  "
          f"p75 {np.percentile(p,75):5.1f}  top-decile share {np.mean(p>=90)*100:4.1f}%  "
          f"top-quintile {np.mean(p>=80)*100:4.1f}%  "
          f"selection-proxy (top 2.3%) {np.mean(p>=97.7)*100:4.2f}%")

print("\nwhere dying names ranked vs survivors (price-free composite percentile):")
dist(dead_rows, "true deaths (bankruptcy+removal)")
dist([r for r in dead_rows if r["class"] == "bankruptcy"], "  bankruptcies only")
dist(merger_rows, "mergers (separate event class)")

print("\nconditioned on time to death (true-death classes):")
for lo, hi, label in ((0, 6, "<6 months"), (6, 12, "6-12 months"),
                      (12, 24, "12-24 months"), (24, 999, ">24 months")):
    dist([r for r in dead_rows if lo <= r["months_to_death"] < hi], label)

print("\ncomponent discrimination, true deaths vs survivor median (AUC = probability a "
      "random dying name scores BELOW a random survivor, higher = better screen):")
surv_pct = {}


def auc_against_uniform(values_pct):
    """Dead names' percentiles vs survivors are already relative ranks: AUC = 1 - mean/100."""
    p = np.array(values_pct, dtype=float)
    return 1 - p.mean() / 100

for comp in ("financial_health", "accounting_quality", "profitability"):
    vals = [r[comp] for r in dead_rows if r.get(comp) is not None]
    med = np.median(vals)
    print(f"  {comp:22s} dying median {med:5.1f} (n {len(vals)})")
alive_z = [r["altman_z"] for r in merger_rows if r.get("altman_z") is not None]
dead_z = [r["altman_z"] for r in dead_rows if r.get("altman_z") is not None]
if dead_z and alive_z:
    u = stats.mannwhitneyu(dead_z, alive_z, alternative="less")
    print(f"  altman_z raw: dying median {np.median(dead_z):.2f} vs merger cohort "
          f"median {np.median(alive_z):.2f} (Mann-Whitney one-sided p {u[1]:.1e}, "
          f"n {len(dead_z)}/{len(alive_z)})")
comp_pct = [r["pct_vs_survivors"] for r in dead_rows]
print(f"  composite AUC vs survivors: {auc_against_uniform(comp_pct):.3f} "
      f"(0.5 = no discrimination)")
imminent = [r["pct_vs_survivors"] for r in dead_rows if r["months_to_death"] < 12]
print(f"  composite AUC, deaths within 12 months: {auc_against_uniform(imminent):.3f} "
      f"(n {len(imminent)})")
