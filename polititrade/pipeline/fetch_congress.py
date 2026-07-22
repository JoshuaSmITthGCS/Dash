"""
fetch_congress.py
Pull congressional trades, normalize them, merge an append-only historical store,
and publish a recent view to trades.json.

Source: Bargo Congress API (House + Senate, derived from official STOCK Act filings)

Normalized schema per record:
{ politician, chamber, party, state, ticker, asset, type, amount_range,
  amount_mid, trade_date, filing_date, filing_lag_days, source }
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

from common import (
    DATA_DIR, LOG, load_store_json,
    http_get_json, save_json, days_between, today_iso, normalize_name,
    update_pipeline_status,
)

BARGO_URL = "https://www.bargo.ai/free-apis/congress/v1/trades"
BARGO_HEALTH_URL = "https://www.bargo.ai/free-apis/congress/v1/health"

LOOKBACK_DAYS = 90
HISTORY_FETCH_DAYS = int(os.getenv("CONGRESS_HISTORY_DAYS", "400"))
BARGO_API_KEY = os.getenv("BARGO_API_KEY", "").strip()
PAGE_SIZE = 250 if BARGO_API_KEY else 100
MAX_PAGES = int(os.getenv("CONGRESS_MAX_PAGES", "100"))
MIN_SOURCE_RECORDS = int(os.getenv("CONGRESS_MIN_RECORDS", "10"))
HISTORY_FILE = "trades_history.json"


def parse_amount_range(raw):
    """Return (label, midpoint) from a disclosed dollar range string."""
    if not raw:
        return ("unknown", 0)
    label = str(raw).strip()
    digits = [int(x.replace(",", "")) for x in _find_numbers(label)]
    if len(digits) >= 2:
        return (label, (digits[0] + digits[1]) // 2)
    if len(digits) == 1:
        return (label, digits[0])
    return (label, 0)


def _find_numbers(text):
    import re
    return re.findall(r"[\d,]{3,}", text)


def norm_type(raw):
    r = (raw or "").lower()
    if "purchase" in r or r == "buy":
        return "buy"
    if "sale" in r or "sold" in r or r == "sell":
        return "sell"
    if "exchange" in r:
        return "exchange"
    return r or "unknown"


def normalize_bargo(rec):
    trade_date = rec.get("transaction_date") or rec.get("trade_date")
    filing_date = rec.get("disclosure_date") or rec.get("filing_date")
    amount_label = rec.get("amount_range") or "unknown"
    low, high = rec.get("amount_low"), rec.get("amount_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        amount_mid = int((low + high) / 2)
    else:
        amount_label, amount_mid = parse_amount_range(amount_label)
    return {
        "politician": normalize_name(rec.get("member", "").removeprefix("Hon. ")),
        "chamber": str(rec.get("chamber", "unknown")).title(),
        "party": rec.get("party", "unknown"),
        "state": rec.get("state", ""),
        "ticker": (rec.get("ticker") or "").upper().strip(),
        "asset": rec.get("asset", ""),
        "type": norm_type(rec.get("type") or rec.get("transaction_type")),
        "amount_range": amount_label,
        "amount_mid": amount_mid,
        "trade_date": trade_date,
        "filing_date": filing_date,
        "filing_lag_days": days_between(trade_date, filing_date),
        "source": "bargo_official_filings",
        "source_url": rec.get("filing_portal", ""),
    }


def within_lookback(rec):
    td = rec.get("trade_date")
    if not td:
        return False
    lag = days_between(td, today_iso())
    return lag is not None and 0 <= lag <= LOOKBACK_DAYS


def dedupe(records):
    seen = set()
    out = []
    for r in records:
        key = trade_key(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def trade_key(r):
    return (r.get("politician"), r.get("ticker"), r.get("trade_date"),
            r.get("filing_date"), r.get("type"), r.get("amount_mid"))


def fetch():
    fetch_days = HISTORY_FETCH_DAYS if BARGO_API_KEY else LOOKBACK_DAYS
    start = (date.today() - timedelta(days=fetch_days)).isoformat()
    records = []
    page_limit = MAX_PAGES if BARGO_API_KEY else 1
    for page in range(page_limit):
        data = http_get_json(BARGO_URL, params={
            "from": start, "to": today_iso(), "limit": PAGE_SIZE, "page": page,
        }, headers={"X-API-Key": BARGO_API_KEY} if BARGO_API_KEY else None)
        if not data:
            raise RuntimeError(f"Bargo page {page} failed")
        rows = data.get("trades", [])
        records.extend(normalize_bargo(r) for r in rows)
        if len(rows) < PAGE_SIZE:
            break
    else:
        if not BARGO_API_KEY:
            LOG.warn("Anonymous Bargo mode fetched one incremental page; set BARGO_API_KEY for historical backfill")
        elif rows and len(rows) >= PAGE_SIZE:
            raise RuntimeError(f"Bargo pagination exceeded safety limit ({MAX_PAGES} pages)")

    records = [r for r in records if r["ticker"] and r["trade_date"]]
    records = dedupe(records)
    if len(records) < MIN_SOURCE_RECORDS:
        raise RuntimeError(f"Bargo returned only {len(records)} valid records")
    LOG.info(f"Bargo: {len(records)} normalized records since {start}")
    return records


def merge_history(fetched):
    previous = load_store_json(HISTORY_FILE) or {}
    prior_rows = previous.get("trades", []) if previous.get("data_mode") != "demo" else []
    merged = {trade_key(r): r for r in prior_rows}
    for row in fetched:
        merged[trade_key(row)] = row
    rows = sorted(merged.values(), key=lambda r: (r.get("filing_date") or "", r.get("trade_date") or ""), reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "source": "Bargo Congress API / official STOCK Act filing portals",
        "count": len(rows),
        "trades": rows,
    }
    save_json(HISTORY_FILE, payload, to_store=True)
    return payload


def main():
    try:
        health = http_get_json(BARGO_HEALTH_URL, retries=2)
        history = merge_history(fetch())
    except RuntimeError as exc:
        LOG.error(f"Congress source rejected: {exc}. Keeping previous trades.json.")
        update_pipeline_status("congress", status="error", source="Bargo Congress API", message=str(exc))
        sys.exit(1)
    records = [r for r in history["trades"] if within_lookback(r)]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "source": "Bargo Congress API / official STOCK Act filing portals",
        "source_latest_disclosure": (health or {}).get("latest_disclosure"),
        "lookback_days": LOOKBACK_DAYS,
        "history_count": history["count"],
        "history_oldest_trade_date": min((r["trade_date"] for r in history["trades"] if r.get("trade_date")), default=None),
        "count": len(records),
        "trades": records,
    }
    save_json("trades.json", payload)
    update_pipeline_status("congress", status="healthy", source="Bargo Congress API",
                           details={"recent_records": len(records), "history_records": history["count"],
                                    "source_latest_disclosure": (health or {}).get("latest_disclosure")})
    update_pipeline_status("demo_seed", status="healthy", source="production guard",
                           message="Live congressional data replaced demo fixtures")
    LOG.info(f"Wrote trades.json with {len(records)} trades")


if __name__ == "__main__":
    main()
