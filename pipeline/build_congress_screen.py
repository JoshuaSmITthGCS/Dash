"""Weekly Congressional (STOCK Act) trade disclosure screen.

Fetches new Senate and House disclosures from Financial Modeling Prep, appends them
point-in-time (never overwritten, same convention as pit_store.py) under
pipeline/data/congress/, and publishes the trailing window with a few defensible,
computable flags - no invented "conflict of interest" scoring that would need data
this pipeline doesn't have (committee assignments, legislative calendars):

  LATE_FILING     disclosed more than the STOCK Act's required 45 days after the trade
  OPTIONS_TRADE   the disclosed asset is a stock option, not a plain equity position
  RARE_TRADER     this representative's only disclosed trade in the accumulated window -
                  gated behind a minimum accumulated history span so week one doesn't
                  flag every single representative as "rare" for lack of prior data

Run weekly, not daily: FMP's free tier allows 250 requests/day, and disclosures
themselves lag the actual trade by up to 45 days, so daily polling would mostly
re-fetch what a weekly run already has.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

from common import LOG, STORE_DIR, save_json
from congress_trades import CongressTradesClient, CongressTradesError

CONGRESS_DIR = os.path.join(STORE_DIR, "congress")
TRADES = "trades.jsonl"

PUBLISH_WINDOW_DAYS = 120
LATE_FILING_DAYS = 45
# A "rare trader" reading is only trustworthy once the store has covered enough
# calendar time to say a representative really hasn't traded, not just that this
# pipeline hasn't been running long enough to have seen them do it.
RARE_TRADER_MINIMUM_HISTORY_DAYS = 90


def _path():
    os.makedirs(CONGRESS_DIR, exist_ok=True)
    return os.path.join(CONGRESS_DIR, TRADES)


def _trade_key(trade):
    return (trade.get("chamber"), trade.get("representative"), trade.get("symbol"),
            trade.get("transaction_date"), trade.get("transaction_type"), trade.get("amount"))


def _read_all():
    path = _path()
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def append_new_trades(trades, *, collected_at=None):
    """Appends trades not already recorded, keyed on the disclosure's own identifying
    fields (not FMP's link, which isn't guaranteed present or stable)."""
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    existing_keys = {_trade_key(row) for row in _read_all()}
    fresh = [trade for trade in trades if _trade_key(trade) not in existing_keys]
    if not fresh:
        return 0
    with open(_path(), "a") as handle:
        for trade in fresh:
            handle.write(json.dumps({**trade, "collected_at": collected_at}, default=str, sort_keys=True) + "\n")
    return len(fresh)


def parse_amount_upper(amount):
    """The upper bound of FMP's reported range string (e.g. "$15,001 - $50,000" -> 50000,
    "Over $50,000,000" -> 50000000), a sortable proxy for size - STOCK Act disclosures
    only ever report a range, never an exact amount."""
    if not amount:
        return None
    numbers = [float(match.replace(",", "")) for match in re.findall(r"\$([\d,]+)", amount)]
    return max(numbers) if numbers else None


def _days_between(earlier, later):
    try:
        start = datetime.fromisoformat(earlier)
        end = datetime.fromisoformat(later)
    except (TypeError, ValueError):
        return None
    return (end - start).days


def classify(trade, *, trade_counts, history_days):
    flags = []
    filing_delay = _days_between(trade.get("transaction_date"), trade.get("disclosure_date"))
    if filing_delay is not None and filing_delay > LATE_FILING_DAYS:
        flags.append("LATE_FILING")
    if "option" in str(trade.get("asset_type") or "").lower():
        flags.append("OPTIONS_TRADE")
    rare_trader_evaluated = history_days >= RARE_TRADER_MINIMUM_HISTORY_DAYS
    if rare_trader_evaluated and trade_counts.get(trade.get("representative"), 0) <= 1:
        flags.append("RARE_TRADER")
    return {
        **trade,
        "amount_upper": parse_amount_upper(trade.get("amount")),
        "filing_delay_days": filing_delay,
        "flags": flags,
        "rare_trader_evaluated": rare_trader_evaluated,
    }


def build_results(rows, *, as_of=None):
    as_of = as_of or datetime.now(timezone.utc)
    cutoff = (as_of - timedelta(days=PUBLISH_WINDOW_DAYS)).date().isoformat()
    dates = [row.get("disclosure_date") or row.get("transaction_date") for row in rows
            if row.get("disclosure_date") or row.get("transaction_date")]
    history_days = 0
    if dates:
        earliest = min(dates)
        try:
            history_days = (as_of.date() - datetime.fromisoformat(earliest).date()).days
        except ValueError:
            history_days = 0

    trade_counts = {}
    for row in rows:
        representative = row.get("representative")
        if representative:
            trade_counts[representative] = trade_counts.get(representative, 0) + 1

    window = [row for row in rows if (row.get("disclosure_date") or "") >= cutoff]
    classified = [classify(row, trade_counts=trade_counts, history_days=history_days) for row in window]
    classified.sort(key=lambda row: row.get("disclosure_date") or "", reverse=True)
    return classified, history_days


def run():
    try:
        client = CongressTradesClient()
    except CongressTradesError as exc:
        LOG.warn(f"Congress trades collection skipped: {exc}")
        return None

    fetched = []
    for fetch in (client.senate_latest, client.house_latest):
        try:
            fetched.extend(fetch())
        except CongressTradesError as exc:
            LOG.warn(f"Congress trades fetch failed ({type(exc).__name__}: {exc})")

    added = append_new_trades(fetched)
    LOG.info(f"Congress trades: +{added} new disclosure(s) recorded")

    generated_at = datetime.now(timezone.utc)
    results, history_days = build_results(_read_all(), as_of=generated_at)
    payload = {
        "schema_version": "1.0.0", "model_version": "congress-trades-v1.0.0",
        "generated_at": generated_at.isoformat(), "status": "success",
        "publish_window_days": PUBLISH_WINDOW_DAYS, "history_days": history_days,
        "late_filing_threshold_days": LATE_FILING_DAYS,
        "rare_trader_minimum_history_days": RARE_TRADER_MINIMUM_HISTORY_DAYS,
        "results": results,
    }
    save_json("screens/congress-trades.json", payload)
    LOG.info(f"Congress trades screen: {len(results)} disclosure(s) published, {history_days}d of history")
    return payload


if __name__ == "__main__":
    run()
