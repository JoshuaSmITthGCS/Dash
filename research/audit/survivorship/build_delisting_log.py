"""Task 1: the delisting event log, from EDGAR's own filing indexes. Free and authoritative.

Stage 1: quarterly form indexes (edgar/full-index/{year}/{qtr}/form.idx) for 2020Q1
through 2026Q3. One request per quarter, cached to disk, SEC fair-access UA and pacing.
Rows kept: Form 25, 25-NSE (removal from listing) and Form 15 family (termination of
registration).

Stage 2: per-CIK submissions JSON (data.sec.gov/submissions) for every candidate CIK,
cached. Supplies the classification signals: 8-K item 1.03 (bankruptcy) or 2.01
(completed acquisition) near the event, the filer's last 10-K/10-Q (operating-company
test), recoverable tickers, and EntityPublicFloat comes later from companyfacts.

Classification, in priority order:
  bankruptcy            8-K with item 1.03 within 365 days before the event
  merger_acquisition    8-K with item 2.01 within 180 days around the event, or DEFM14A/
                        S-4 within 365 days before
  voluntary_dereg       Form 15 family with no Form 25, or Form 25 filed by the issuer
                        with none of the above
  exchange_rule_removal Form 25-NSE (exchange-initiated) with none of the above. This is
                        the performance-related bucket for the Shumway treatment.
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
os.makedirs(f"{OUT}/form_index", exist_ok=True)
os.makedirs(f"{OUT}/submissions", exist_ok=True)
UA = {"User-Agent": "ValueSignal research jbmsmusic05@gmail.com"}

KEEP_FORMS = {"25", "25-NSE", "25-NSE/A", "25/A",
              "15-12B", "15-12G", "15-15D", "15", "15/A", "15-12B/A", "15-12G/A"}


def get(url, timeout=30):
    if _SESSION is not None:
        resp = _SESSION.get(url, headers=UA, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def form_index(year, qtr):
    path = f"{OUT}/form_index/{year}Q{qtr}.idx"
    if not os.path.exists(path):
        data = get(f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/form.idx")
        open(path, "wb").write(data)
        time.sleep(0.15)
    return open(path, encoding="latin1").read().splitlines()


events = []
quarters = [(y, q) for y in range(2020, 2027) for q in range(1, 5)
            if not (y == 2026 and q > 3)]
for year, qtr in quarters:
    try:
        lines = form_index(year, qtr)
    except Exception as exc:  # noqa: BLE001
        print(f"{year}Q{qtr}: index unavailable ({exc})")
        continue
    started = False
    for line in lines:
        if line.startswith("Form Type"):
            started = True
            continue
        if not started or not line.strip() or line.startswith("---"):
            continue
        head_tail = line.rsplit(None, 3)
        if len(head_tail) != 4:
            continue
        head, cik, filed, _filename = head_tail
        if not (cik.isdigit() and len(filed) == 10 and filed[4] == "-"):
            continue
        form = head.split(None, 1)[0]
        if form not in KEEP_FORMS:
            continue
        company = head.split(None, 1)[1].strip() if " " in head else ""
        events.append({"form": form, "company": company, "cik": cik.zfill(10),
                       "date": filed})
print(f"index rows kept: {len(events)} across {len(quarters)} quarters")

ciks = sorted({e["cik"] for e in events})
print(f"distinct candidate CIKs: {len(ciks)}")


def submissions(cik):
    path = f"{OUT}/submissions/{cik}.json"
    if os.path.exists(path):
        return json.load(open(path))
    try:
        data = get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    except Exception:  # noqa: BLE001
        return None
    open(path, "wb").write(data)
    time.sleep(0.06)
    return json.loads(data)


def recent_frame(sub):
    r = (sub.get("filings") or {}).get("recent") or {}
    return list(zip(r.get("form", []), r.get("filingDate", []),
                    r.get("items", [""] * len(r.get("form", [])))))


log = []
start = time.time()
for i, cik in enumerate(ciks):
    sub = submissions(cik)
    if sub is None:
        continue
    frame = recent_frame(sub)
    forms_dates = [(f, d) for f, d, _ in frame]
    cik_events = sorted((e for e in events if e["cik"] == cik), key=lambda e: e["date"])
    event = cik_events[-1]
    edate = event["date"]

    def within(form_prefixes, lo_days, hi_days, item=None):
        from datetime import date as D
        e = D.fromisoformat(edate)
        for f, d, items in frame:
            if not any(f.startswith(p) for p in form_prefixes):
                continue
            try:
                delta = (D.fromisoformat(d) - e).days
            except ValueError:
                continue
            if lo_days <= delta <= hi_days:
                if item is None or item in (items or ""):
                    return True
        return False

    has_25 = any(e["form"].startswith("25") for e in cik_events)
    has_25nse = any(e["form"].startswith("25-NSE") for e in cik_events)
    last_periodic = max((d for f, d in forms_dates if f in ("10-K", "10-Q", "20-F")),
                       default=None)
    operating = last_periodic is not None and last_periodic >= "2019-01-01"

    if within(("8-K",), -365, 30, item="1.03"):
        klass = "bankruptcy"
    elif within(("8-K",), -180, 180, item="2.01") or within(("DEFM14A", "S-4"), -365, 30):
        klass = "merger_acquisition"
    elif has_25nse:
        klass = "exchange_rule_removal"
    elif has_25:
        klass = "voluntary_or_unclassified_25"
    else:
        klass = "voluntary_dereg"

    tickers = sub.get("tickers") or []
    log.append({"cik": cik, "company": event["company"], "event_date": edate,
                "form": event["form"], "classification": klass,
                "ticker": tickers[0] if tickers else None,
                "all_tickers": tickers,
                "last_periodic_filing": last_periodic,
                "operating_company": operating,
                "exchange": (sub.get("exchanges") or [None])[0]})
    if (i + 1) % 250 == 0:
        print(f"  {i+1}/{len(ciks)} classified, {time.time()-start:.0f}s")

json.dump(log, open(f"{OUT}/delisting_log.json", "w"), indent=1)

from collections import Counter
ops = [e for e in log if e["operating_company"]]
print(f"\nlog entries: {len(log)}  operating companies (10-K/Q/20-F since 2019): {len(ops)}")
print("classification (operating cohort):", dict(Counter(e["classification"] for e in ops)))
print("with recoverable ticker:", sum(1 for e in ops if e["ticker"]), "/", len(ops))
print("date range:", min(e["event_date"] for e in log), "to", max(e["event_date"] for e in log))
