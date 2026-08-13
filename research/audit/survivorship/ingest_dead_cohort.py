"""Task 2: ingest EDGAR facts for the dead cohort into the existing PIT store.

The entity map filters to current tickers (pipeline/data/pit/entity_map.json, built from
SEC's company_tickers.json, which drops deregistered issuers), which is why the store
holds only surviving CIKs. This job fetches companyfacts for every operating-company CIK
in the delisting log, extracts observations through the SAME fixed tag-union path
(edgar_facts.company_observations) and writes through the SAME idempotent
amendment-preserving store (pit_fundamentals_store.ShardedStore), so every PIT test that
holds for survivors holds for the dead cohort by construction. EntityPublicFloat (dei
taxonomy) is captured per CIK as the size proxy for universe reconstruction.
"""
import json
import os
import sys
import time
import urllib.request

try:
    import requests
    _SESSION = requests.Session()
except ImportError:
    _SESSION = None

REPO = "/Users/eyerise/Documents/GitHub/Dash"
OUT = f"{REPO}/research/audit/survivorship/data"
sys.path.insert(0, f"{REPO}/pipeline")

from edgar_facts import company_observations  # noqa: E402
from pit_fundamentals_store import ShardedStore, compact  # noqa: E402

UA = {"User-Agent": "ValueSignal research jbmsmusic05@gmail.com"}
STORE = ShardedStore(f"{REPO}/pipeline/data/pit/fundamentals")
os.makedirs(f"{OUT}/companyfacts", exist_ok=True)

log = json.load(open(f"{OUT}/delisting_log.json"))
ops = [e for e in log if e["operating_company"]]
ciks = sorted({e["cik"] for e in ops})
print(f"dead cohort: {len(ciks)} operating-company CIKs")

rows, floats, fetched, missing = [], {}, 0, 0
start = time.time()
from concurrent.futures import ThreadPoolExecutor
import threading
_lock = threading.Lock()

def process(cik):
    global fetched, missing
    path = f"{OUT}/companyfacts/{cik}.json"
    if os.path.exists(path):
        try:
            facts = json.load(open(path))
        except json.JSONDecodeError:
            facts = None
    else:
        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            if _SESSION is not None:
                resp = _SESSION.get(url, headers=UA, timeout=30)
                resp.raise_for_status()
                data = resp.content
            else:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
            open(path, "wb").write(data)
            facts = json.loads(data)
            time.sleep(0.06)
        except Exception:  # noqa: BLE001
            with _lock:
                missing += 1
            open(path, "w").write("null")
            return
    if not facts:
        with _lock:
            missing += 1
        return
    observations, _meta = company_observations(facts, cik=cik)
    pf = (((facts.get("facts") or {}).get("dei") or {})
          .get("EntityPublicFloat") or {}).get("units", {}).get("USD", [])
    with _lock:
        fetched += 1
        rows.extend(compact(row) for row in observations)
        if pf:
            floats[cik] = max((entry.get("val") or 0) for entry in pf)
        if fetched % 250 == 0:
            print(f"  fetched={fetched} missing={missing} rows={len(rows)} "
                  f"{time.time()-start:.0f}s")

with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(process, ciks))

written = STORE.write(rows)
json.dump(floats, open(f"{OUT}/public_floats.json", "w"))
print(f"done: fetched {fetched}, no-facts {missing}, observations {len(rows)}, "
      f"new rows written {written}")
print(f"EntityPublicFloat recovered for {len(floats)} CIKs, "
      f">=$1B: {sum(1 for v in floats.values() if v >= 1e9)}")