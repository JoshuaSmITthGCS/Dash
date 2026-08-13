"""Task 1c: post-re-ingest coverage by year, Altman Z scored coverage, store stats."""
import glob
import json
import sys
from collections import Counter

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")
from edgar_enrichment import _annual_facts_as_of, _ticker_to_cik, edgar_extended
import edgar_enrichment
edgar_enrichment._shard_rows.cache_clear()

n = re_rows = 0
for f in glob.glob(f"{REPO}/pipeline/data/pit/fundamentals/*.jsonl"):
    for line in open(f):
        n += 1
        if '"retained_earnings"' in line:
            re_rows += 1
print(f"store rows {n} (pre-ingest 1,448,995), retained_earnings rows {re_rows}")

t2c = _ticker_to_cik()
import os
mapped = [t for t in (f[:-5] for f in os.listdir(f"{REPO}/pipeline/data/backtest_cache")
                      if f.endswith(".json")) if t.upper() in t2c]
CORE = ["revenue", "net_income", "operating_income", "assets", "equity",
        "operating_cash_flow", "capital_expenditure", "depreciation_amortization",
        "retained_earnings"]
print("\ncoverage by year, share of %d mapped names (post tag-union re-ingest):" % len(mapped))
print("year  " + "  ".join(f"{c[:10]:>10s}" for c in CORE))
for year in range(2011, 2027, 3):
    counts = Counter()
    for t in mapped:
        seen = {c for c, _pe in _annual_facts_as_of(t2c[t.upper()], f"{year}-01-01")}
        for c in CORE:
            if c in seen:
                counts[c] += 1
    print(f"{year}  " + "  ".join(f"{counts[c]/len(mapped):10.2f}" for c in CORE))

# Altman Z scored coverage on the pinned snapshot with re-ingested fallback.
rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]
have = 0
tot = 0
for r in rows:
    raw = dict(r.get("raw_metric_inputs") or {})
    if r["scores"]["champion"] is None or raw.get("sector") == "ETF":
        continue
    tot += 1
    fb = edgar_extended(r["ticker"], as_of="2026-08-10", market_cap=raw.get("market_cap"),
                        price=raw.get("price"), sector=raw.get("sector"))
    v = raw.get("altman_z")
    if v is None and fb:
        v = fb.get("altman_z")
    if isinstance(v, (int, float)):
        have += 1
print(f"\nAltman Z resolvable post-ingest: {have}/{tot} ({have/tot*100:.0f}%)  "
      "(Round 5 cap was 66%)")
