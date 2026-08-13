"""Backfill the compact report with a daily analytics tape from committed price archives.

Normal refreshes publish this field directly from provider history. This deterministic helper
repairs an already-committed report without a network call so the browser does not keep treating
the intentionally sparse chart grid as daily observations between refreshes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "public" / "data" / "report.json"
ARCHIVE = ROOT / "pipeline" / "data" / "price_archive"
SPY = ROOT / "public" / "data" / "etf" / "SPY.json"
MAXIMUM_SESSIONS = 504


def load(path: Path):
    with path.open() as handle:
        return json.load(handle)


def write_atomic(path: Path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(temporary, path)


def archived_rows(ticker: str):
    path = ARCHIVE / f"{ticker}.json"
    if not path.exists():
        return {}
    rows = load(path).get("rows") or {}
    return {
        str(date)[:10]: float(values[0])
        for date, values in rows.items()
        if values and values[0] is not None and float(values[0]) > 0
    }


def merge_history(row, earliest_date):
    prices = archived_rows(str(row.get("ticker") or "").upper())
    history = row.get("history") or {}
    for date, close in zip(history.get("dates") or [], history.get("closes") or []):
        if date and close is not None and float(close) > 0:
            prices[str(date)[:10]] = float(close)
    dates = sorted(date for date in prices if date >= earliest_date)[-MAXIMUM_SESSIONS:]
    if len(dates) < 2:
        row.pop("analytics_history", None)
        return False
    row["analytics_history"] = {
        "dates": dates,
        "closes": [round(prices[date], 4) for date in dates],
        "frequency": "daily",
    }
    return True


def main():
    report = load(REPORT)
    spy_rows = (load(SPY).get("price_series") or {}).get("fund") or []
    spy_rows = [row for row in spy_rows if row.get("date") and row.get("adjusted_close")]
    spy_rows = spy_rows[-MAXIMUM_SESSIONS:]
    if len(spy_rows) < 2:
        raise RuntimeError("Committed SPY daily history is unavailable")
    earliest = spy_rows[0]["date"]
    report["benchmark_analytics_history"] = {
        "symbol": "SPY",
        "dates": [row["date"] for row in spy_rows],
        "closes": [round(float(row["adjusted_close"]), 4) for row in spy_rows],
        "frequency": "daily",
    }
    updated = 0
    for collection in ("research", "portfolio_coverage"):
        for row in report.get(collection) or []:
            updated += int(merge_history(row, earliest))
    write_atomic(REPORT, report)
    print(f"Published daily analytics history for {updated} report rows")


if __name__ == "__main__":
    main()
