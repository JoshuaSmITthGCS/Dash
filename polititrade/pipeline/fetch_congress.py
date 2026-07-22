"""
fetch_congress.py
Pull recent congressional trades, normalize to one schema, dedupe, write trades.json.

Primary source:  Lambda Finance API (House + Senate, normalized)
Backup source:   Senate Stock Watcher S3 JSON (Senate only)
Dead source:     House Stock Watcher S3 (403s since early 2026) -- do not add.

Normalized schema per record:
{ politician, chamber, party, state, ticker, asset, type, amount_range,
  amount_mid, trade_date, filing_date, filing_lag_days, source }
"""

import json
import os
import sys
from datetime import datetime, timezone

from common import (
    DATA_DIR, LOG,
    http_get_json, load_json, save_json, days_between, today_iso, normalize_name
)

LAMBDA_URL = "https://api.lambda.finance/api/congressional/recent"  # dev account / free tier
SENATE_BACKUP_URL = "https://senate-stock-watcher-data.s3.amazonaws.com/aggregate/all_transactions.json"

LOOKBACK_DAYS = 90


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


def normalize_lambda(rec):
    trade_date = rec.get("transaction_date") or rec.get("trade_date")
    filing_date = rec.get("disclosure_date") or rec.get("filing_date")
    amount_label, amount_mid = parse_amount_range(rec.get("amount"))
    return {
        "politician": normalize_name(rec.get("representative") or rec.get("senator") or rec.get("name", "")),
        "chamber": rec.get("chamber", "unknown"),
        "party": rec.get("party", "unknown"),
        "state": rec.get("state", ""),
        "ticker": (rec.get("ticker") or "").upper().strip(),
        "asset": rec.get("asset_description") or rec.get("asset", ""),
        "type": norm_type(rec.get("type") or rec.get("transaction_type")),
        "amount_range": amount_label,
        "amount_mid": amount_mid,
        "trade_date": trade_date,
        "filing_date": filing_date,
        "filing_lag_days": days_between(trade_date, filing_date),
        "source": "lambda",
    }


def normalize_senate(rec):
    trade_date = rec.get("transaction_date")
    filing_date = rec.get("disclosure_date")
    amount_label, amount_mid = parse_amount_range(rec.get("amount"))
    return {
        "politician": normalize_name(rec.get("senator", "")),
        "chamber": "Senate",
        "party": rec.get("party", "unknown"),
        "state": rec.get("state", ""),
        "ticker": (rec.get("ticker") or "").upper().strip(),
        "asset": rec.get("asset_description", ""),
        "type": norm_type(rec.get("type")),
        "amount_range": amount_label,
        "amount_mid": amount_mid,
        "trade_date": trade_date,
        "filing_date": filing_date,
        "filing_lag_days": days_between(trade_date, filing_date),
        "source": "senate_stock_watcher",
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
        key = (r["politician"], r["ticker"], r["trade_date"], r["amount_mid"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def fetch():
    records = []

    # Primary: Lambda Finance
    data = http_get_json(LAMBDA_URL, params={"days": LOOKBACK_DAYS})
    if data:
        rows = data if isinstance(data, list) else data.get("data", [])
        records = [normalize_lambda(r) for r in rows]
        LOG.info(f"Lambda Finance: {len(records)} records")

    # Backup: Senate Stock Watcher (only if primary failed or looks empty)
    if len(records) < 10:
        LOG.warn("Primary source thin/failed -- falling back to Senate Stock Watcher")
        data = http_get_json(SENATE_BACKUP_URL)
        if data:
            rows = data if isinstance(data, list) else data.get("transactions", [])
            records = [normalize_senate(r) for r in rows]
            LOG.info(f"Senate Stock Watcher: {len(records)} records")

    records = [r for r in records if r["ticker"] and within_lookback(r)]
    records = dedupe(records)
    records.sort(key=lambda r: (r.get("filing_date") or ""), reverse=True)
    return records


def main():
    records = fetch()
    if not records:
        LOG.error("No congressional records fetched. Keeping previous trades.json if present.")
        if os.path.exists(os.path.join(DATA_DIR, "trades.json")):
            sys.exit(0)
        records = []
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "count": len(records),
        "trades": records,
    }
    save_json("trades.json", payload)
    LOG.info(f"Wrote trades.json with {len(records)} trades")


if __name__ == "__main__":
    main()
