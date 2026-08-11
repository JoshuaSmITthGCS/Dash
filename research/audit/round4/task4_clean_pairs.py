"""Task 4: daily band vs cross-sectional turnover restricted to clean refresh pairs.

Stability rule, stated before measurement:
  universe churn      |A xor B| / |A union B| < 0.02
  coverage stability  |mean fundamentals coverage delta| < 0.02

Coverage is the weighted_coverage recomputation over champion metric scores used in
Round 3 item 4. Fewer than five clean pairs means the daily direction claim is
withdrawn, per the Round 4 brief, and the monthly backtest comparison stands as the
only admissible evidence.
"""
import json
from collections import defaultdict

import numpy as np

REPO = "/Users/eyerise/Documents/GitHub/Dash"
DAYS = ["2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10"]

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


def load_day(day):
    rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/{day}.jsonl")]
    latest = max(r["refresh_id"] for r in rows)
    return {r["ticker"]: r for r in rows if r["refresh_id"] == latest}


def topdecile_turnover(sa, sb):
    common = [t for t in sa if t in sb and sa[t] is not None and sb[t] is not None]
    n = max(1, len(common) // 10)
    ta = set(sorted(common, key=lambda t: (-sa[t], t))[:n])
    tb = set(sorted(common, key=lambda t: (-sb[t], t))[:n])
    return 1 - len(ta & tb) / n


snaps = {d: load_day(d) for d in DAYS}
cov = {d: np.mean([weighted_coverage(r["normalized_metric_scores"]["champion"])
                   for r in snaps[d].values()]) for d in DAYS}

print("pair            universe_churn  coverage_delta  clean?  champ_TO  chall_TO")
clean = []
for a, b in zip(DAYS, DAYS[1:]):
    A, B = set(snaps[a]), set(snaps[b])
    churn = len(A ^ B) / len(A | B)
    cdelta = abs(cov[b] - cov[a])
    ok = churn < 0.02 and cdelta < 0.02
    champ = topdecile_turnover({t: r["scores"]["champion"] for t, r in snaps[a].items()},
                               {t: r["scores"]["champion"] for t, r in snaps[b].items()})
    chall = topdecile_turnover({t: r["scores"]["challenger"] for t, r in snaps[a].items()},
                               {t: r["scores"]["challenger"] for t, r in snaps[b].items()})
    print(f"{a}->{b}  {churn:14.3f}  {cdelta:14.3f}  {str(ok):6s}  {champ:.3f}    {chall:.3f}")
    if ok:
        clean.append((champ, chall))

print(f"\nclean pairs: {len(clean)} of 5 (rule requires >=5 for a daily direction claim)")
if clean:
    print("clean-pair means: champion %.3f  challenger %.3f" % (
        np.mean([c[0] for c in clean]), np.mean([c[1] for c in clean])))
print("daily coverage means:", {d: round(cov[d], 3) for d in DAYS})
