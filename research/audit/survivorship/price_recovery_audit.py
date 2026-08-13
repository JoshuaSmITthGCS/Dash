"""Task 3: measure, do not assume, which delisted tickers still serve free price history.

For every operating-company event in the delisting log with a recoverable ticker,
attempt a full daily history pull from yfinance (the stack's price provider). A hit is
a series with at least 60 trading days ending within 120 days of the event date (prices
up to, not through, delisting are sufficient: Shumway supplies the final return).
Results cache per ticker so the audit is resumable. Achieved coverage is recorded as-is
after one pass, per the brief's no-indefinite-retry rule.
"""
import json
import os
import sys
import time
from datetime import date, timedelta

REPO = "/Users/eyerise/Documents/GitHub/Dash"
OUT = f"{REPO}/research/audit/survivorship/data"
os.makedirs(f"{OUT}/dead_prices", exist_ok=True)

import yfinance as yf  # noqa: E402

log = json.load(open(f"{OUT}/delisting_log.json"))
ops = [e for e in log if e["operating_company"] and e["ticker"]]
print(f"probing {len(ops)} operating-company events with recoverable tickers")

results = []
for i, e in enumerate(ops):
    t = e["ticker"]
    path = f"{OUT}/dead_prices/{t}.json"
    if os.path.exists(path):
        d = json.load(open(path))
    else:
        d = {"ticker": t, "dates": [], "closes": [], "volumes": []}
        try:
            h = yf.Ticker(t).history(period="max", auto_adjust=True)
            if h is not None and not h.empty:
                d = {"ticker": t,
                     "dates": [x.strftime("%Y-%m-%d") for x in h.index],
                     "closes": [round(float(v), 4) for v in h["Close"]],
                     "volumes": [int(v) for v in h["Volume"]]}
        except Exception:  # noqa: BLE001
            pass
        json.dump(d, open(path, "w"))
        time.sleep(0.35)
    n = len(d["dates"])
    last = d["dates"][-1] if n else None
    ev = date.fromisoformat(e["event_date"])
    hit = bool(n >= 60 and last and abs((date.fromisoformat(last) - ev).days) <= 120)
    near_miss = bool(n >= 60 and last and (ev - date.fromisoformat(last)).days > 120)
    results.append({**e, "price_days": n, "last_price_date": last,
                    "hit": hit, "history_but_stale": near_miss})
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(ops)}")

json.dump(results, open(f"{OUT}/price_recovery.json", "w"), indent=1)

from collections import Counter, defaultdict
by_year = defaultdict(lambda: [0, 0])
by_class = defaultdict(lambda: [0, 0])
for r in results:
    y = r["event_date"][:4]
    by_year[y][1] += 1
    by_class[r["classification"]][1] += 1
    if r["hit"]:
        by_year[y][0] += 1
        by_class[r["classification"]][0] += 1
print("\nhit rate by delisting year:")
for y in sorted(by_year):
    h, n = by_year[y]
    print(f"  {y}: {h}/{n} ({h/n*100:.0f}%)")
print("hit rate by classification:")
for c in sorted(by_class):
    h, n = by_class[c]
    print(f"  {c:28s}: {h}/{n} ({h/n*100:.0f}%)")
print("overall:", sum(r["hit"] for r in results), "/", len(results))
