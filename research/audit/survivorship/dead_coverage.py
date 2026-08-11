"""Dead-cohort as-filed coverage by year, against the survivor table from Round 6."""
import json
import sys
from collections import Counter

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")
import edgar_enrichment
from edgar_enrichment import _annual_facts_as_of
edgar_enrichment._shard_rows.cache_clear()

log = json.load(open(f"{REPO}/research/audit/survivorship/data/delisting_log.json"))
ops = [e for e in log if e["operating_company"]]
ciks = sorted({e["cik"] for e in ops})
CORE = ["revenue", "net_income", "assets", "equity", "operating_cash_flow",
        "retained_earnings"]
print(f"dead cohort coverage by year (n={len(ciks)} operating CIKs):")
print("year  " + "  ".join(f"{c[:10]:>10s}" for c in CORE))
for year in (2011, 2014, 2017, 2020, 2023):
    counts = Counter()
    with_any = 0
    for cik in ciks:
        seen = {c for c, _pe in _annual_facts_as_of(cik, f"{year}-01-01")}
        if seen:
            with_any += 1
        for c in CORE:
            if c in seen:
                counts[c] += 1
    print(f"{year}  " + "  ".join(f"{counts[c]/len(ciks):10.2f}" for c in CORE)
          + f"   any-fact: {with_any/len(ciks):.2f}")
