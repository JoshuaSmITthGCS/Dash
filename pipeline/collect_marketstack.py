"""Collects premarket/intraday-capable price data for the top-100 published tickers.

Two runs a day cover this: end-of-day (off hours, backfills the session that just
closed) and pre-open (forward, captures whatever premarket quote Marketstack has
ahead of the next session) - see .github/workflows/marketstack-premarket.yml. Each
run is exactly one batched API request for up to 100 symbols, so two runs a day
stays near 40-46 calls a month, well inside a 100-calls/month plan.

Every collected row is appended point-in-time (never overwritten) under
pipeline/data/marketstack/, the same append-only convention as pit_store.py, so
early_session_research.py can report real freshness instead of a guess.
"""

from datetime import datetime, timezone

from common import LOG, STORE_DIR, load_json
from marketstack import MarketstackClient, MarketstackError, MarketstackPlanRestricted

import json
import os

MARKETSTACK_DIR = os.path.join(STORE_DIR, "marketstack")
COLLECTED = "collected.jsonl"


def top_symbols(payload, limit=100):
    """Same "top by score" ordering fetch_advisor.py's fast-refresh path uses -
    advisor.json's research list is already rank-sorted, so this is just a slice."""
    payload = payload or {}
    ranked = [row.get("ticker") for row in payload.get("research", []) if row.get("ticker")]
    tail = [row.get("ticker") for row in payload.get("portfolio_coverage", [])
            if row.get("ticker") and row.get("ticker") not in ranked]
    return (ranked + tail)[:limit]


def _append(rows):
    if not rows:
        return 0
    os.makedirs(MARKETSTACK_DIR, exist_ok=True)
    path = os.path.join(MARKETSTACK_DIR, COLLECTED)
    with open(path, "a") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
    return len(rows)


def collect(symbols, client=None, observed_at=None):
    """Fetches intraday bars for the given symbols, falling back to end-of-day data
    if intraday isn't available on the configured plan. Returns a summary dict;
    never raises for a plan restriction, only for missing configuration."""
    client = client or MarketstackClient()
    observed_at = observed_at if isinstance(observed_at, str) else (observed_at or datetime.now(timezone.utc)).isoformat()
    mode, rows = "intraday", []
    try:
        rows = client.intraday(symbols)
    except MarketstackPlanRestricted as exc:
        LOG.warn(f"Marketstack intraday unavailable on this plan ({exc}); falling back to EOD latest")
        mode = "eod_latest"
        rows = client.eod_latest(symbols)

    written = _append([{"observed_at": observed_at, "mode": mode, **row} for row in rows])
    LOG.info(f"Marketstack collection: {written} row(s) via {mode} for {len(symbols)} requested symbols")
    return {"mode": mode, "requested": len(symbols), "collected": written, "observed_at": observed_at}


def _closing_value(row):
    """Marketstack's EOD and intraday endpoints don't share one confirmed field name for
    a bar's close, so this tries every plausible one rather than assuming a schema that
    was never exercised against a live key from this environment (network access to
    Marketstack is blocked here - see the collect_marketstack module docstring)."""
    for field in ("close", "last", "price"):
        value = row.get(field)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def daily_closes():
    """One closing price per (ticker, calendar day), oldest first, built from every
    collected row. Two collections a day can both land on the same calendar day (the
    pre-open run and, once available, the after-close run); the later one - by
    observed_at - wins, since it reflects more of that session."""
    path = os.path.join(MARKETSTACK_DIR, COLLECTED)
    if not os.path.exists(path):
        return {}
    latest_by_ticker_day = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            ticker = str(row.get("symbol") or "").upper()
            close = _closing_value(row)
            observed_at = row.get("observed_at") or ""
            day = str(row.get("date") or observed_at)[:10]
            if not ticker or close is None or not day:
                continue
            key = (ticker, day)
            existing = latest_by_ticker_day.get(key)
            if existing is None or observed_at >= existing[0]:
                latest_by_ticker_day[key] = (observed_at, close)

    by_ticker = {}
    for (ticker, day), (_, close) in latest_by_ticker_day.items():
        by_ticker.setdefault(ticker, {})[day] = close

    result = {}
    for ticker, days in by_ticker.items():
        dates = sorted(days)
        result[ticker] = {"dates": dates, "closes": [days[day] for day in dates]}
    return result


def depth():
    """How much premarket/intraday history exists, for the capability report to cite."""
    path = os.path.join(MARKETSTACK_DIR, COLLECTED)
    if not os.path.exists(path):
        return {"rows": 0, "modes": [], "last_observed": None}
    modes, last_observed = set(), None
    rows = 0
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows += 1
            if row.get("mode"):
                modes.add(row["mode"])
            observed = row.get("observed_at")
            if observed and (last_observed is None or observed > last_observed):
                last_observed = observed
    return {"rows": rows, "modes": sorted(modes), "last_observed": last_observed}


def run():
    try:
        client = MarketstackClient()
    except MarketstackError as exc:
        LOG.warn(f"Marketstack collection skipped: {exc}")
        return None
    payload = load_json("advisor.json")
    symbols = top_symbols(payload)
    if not symbols:
        LOG.warn("Marketstack collection skipped: no published universe to select the top 100 from")
        return None
    return collect(symbols, client=client)


if __name__ == "__main__":
    run()
