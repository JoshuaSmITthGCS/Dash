"""Task 2: quantify the transfer contamination in the delisting log.

Two independent checks, both deterministic, both from data already on disk:

1. Price continuation (priced subsample, n=146 recovered tickers): trading more than
   120 days past the Form 25 event means transfer or rename, not death.
2. Filing continuation (all 5,120 operating companies, from the cached submissions
   JSON): a transferred issuer keeps filing periodic reports, a dead one stops. Events
   less than 12 (24) months before the submissions snapshot are right-censored and
   reported as such, never counted either way.
"""
import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

REPO = "/Users/eyerise/Documents/GitHub/Dash"
OUT = f"{REPO}/research/audit/survivorship/data"
SNAPSHOT_DATE = date(2026, 8, 11)

log = json.load(open(f"{OUT}/delisting_log.json"))
ops = [e for e in log if e["operating_company"]]

# Check 1: price continuation on the priced subsample.
recovery = json.load(open(f"{OUT}/price_recovery.json"))
priced = [r for r in recovery if r["price_days"] >= 60 and r["last_price_date"]]
cont = Counter()
tot = Counter()
for r in priced:
    ev = date.fromisoformat(r["event_date"])
    last = date.fromisoformat(r["last_price_date"])
    tot[r["classification"]] += 1
    if (last - ev).days > 120:
        cont[r["classification"]] += 1
n_cont = sum(cont.values())
n_tot = sum(tot.values())
print(f"1. price continuation (priced subsample, n={n_tot}):")
print(f"   trading >120d past event: {n_cont}/{n_tot} ({n_cont/max(1,n_tot)*100:.0f}%) -> transfers/renames")
for c in sorted(tot):
    print(f"   {c:28s}: {cont[c]}/{tot[c]} ({cont[c]/max(1,tot[c])*100:.0f}%)")

# Check 2: filing continuation for all 5,120.
def filings_after(cik, cutoff_iso):
    path = f"{OUT}/submissions/{cik}.json"
    if not os.path.exists(path):
        return None
    try:
        sub = json.load(open(path))
    except (json.JSONDecodeError, TypeError):
        return None
    r = (sub.get("filings") or {}).get("recent") or {}
    for form, filed in zip(r.get("form", []), r.get("filingDate", [])):
        if form in ("10-K", "10-Q", "20-F", "10-K/A", "10-Q/A") and filed >= cutoff_iso:
            return True
    return False


results = {12: Counter(), 24: Counter()}
censored = {12: 0, 24: 0}
assessed = {12: Counter(), 24: Counter()}
for e in ops:
    ev = date.fromisoformat(e["event_date"])
    for months in (12, 24):
        cutoff = ev + timedelta(days=months * 30)
        if cutoff > SNAPSHOT_DATE:
            censored[months] += 1
            continue
        still = filings_after(e["cik"], cutoff.isoformat())
        if still is None:
            continue
        assessed[months][e["classification"]] += 1
        if still:
            results[months][e["classification"]] += 1

print(f"\n2. filing continuation (n={len(ops)} operating companies, snapshot {SNAPSHOT_DATE}):")
for months in (12, 24):
    n_a = sum(assessed[months].values())
    n_s = sum(results[months].values())
    print(f"   still filing periodic reports {months}m after the event: "
          f"{n_s}/{n_a} ({n_s/max(1,n_a)*100:.0f}%), right-censored {censored[months]}")
    for c in sorted(assessed[months]):
        a, s = assessed[months][c], results[months][c]
        print(f"     {c:28s}: {s}/{a} ({s/max(1,a)*100:.0f}%) still filing -> NOT dead")

# Transfer-adjusted death table at the 12-month horizon.
print("\n3. transfer-adjusted classification (12m filing-continuation basis, measured):")
adjusted = {}
for c in sorted(assessed[12]):
    a, s = assessed[12][c], results[12][c]
    dead_rate = 1 - s / max(1, a)
    total_class = sum(1 for e in ops if e["classification"] == c)
    adjusted[c] = {"raw": total_class, "assessed": a, "still_filing": s,
                   "dead_rate_measured": round(dead_rate, 3),
                   "adjusted_deaths": round(total_class * dead_rate)}
    print(f"   {c:28s} raw {total_class:5d}  measured-dead rate {dead_rate:.2f}  "
          f"adjusted deaths ~{adjusted[c]['adjusted_deaths']}")
json.dump(adjusted, open(f"{OUT}/transfer_adjusted.json", "w"), indent=1)
