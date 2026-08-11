"""Task 1: ingest RetainedEarningsAccumulatedDeficit into the EDGAR PIT store.

Round 4 left Altman Z capped at 66% coverage because retained earnings was not among the
29 ingested concepts. The gap is not structural: it is a standard us-gaap tag. This
fetches the companyconcept series for every mapped CIK at the SEC fair-access pace and
merges rows into the sharded store through the same idempotent, amendment-preserving
write path as the original backfill.
"""
import json
import sys
import time
import urllib.request

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")

from edgar_enrichment import _ticker_to_cik  # noqa: E402
from pit_fundamentals_store import ShardedStore  # noqa: E402

STORE = ShardedStore(f"{REPO}/pipeline/data/pit/fundamentals")
UA = {"User-Agent": "ValueSignal research jbmsmusic05@gmail.com"}
URL = ("https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/"
       "RetainedEarningsAccumulatedDeficit.json")

ciks = sorted(set(_ticker_to_cik().values()))
print(f"{len(ciks)} CIKs")
rows, fetched, missing = [], 0, 0
start = time.time()
for i, cik in enumerate(ciks):
    url = URL.format(cik=cik)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
    except Exception:  # noqa: BLE001 - a filer without the tag 404s, skip it
        missing += 1
        continue
    fetched += 1
    for unit, entries in (payload.get("units") or {}).items():
        if unit != "USD":
            continue
        for entry in entries:
            form = entry.get("form") or ""
            if not form.startswith(("10-K", "10-Q", "20-F", "40-F")):
                continue
            rows.append({
                "cik": cik, "concept": "retained_earnings", "unit": "USD",
                "period_start": None, "period_end": entry.get("end"),
                "filed": entry.get("filed"), "value": entry.get("val"),
                "accession": entry.get("accn"), "form": form,
                "fiscal_year": entry.get("fy"), "fiscal_period": entry.get("fp"),
            })
    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(ciks)} fetched={fetched} missing={missing} "
              f"rows={len(rows)} elapsed={time.time()-start:.0f}s")
    time.sleep(0.12)  # 9 requests/second ceiling, run at ~8/s

written = STORE.write(rows)
print(f"done: fetched {fetched}, no-tag {missing}, rows collected {len(rows)}, "
      f"new rows written {written}, {time.time()-start:.0f}s")
