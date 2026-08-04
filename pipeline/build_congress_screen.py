"""Weekly Congressional (STOCK Act) trade disclosure screen.

Fetches new Senate and House disclosures from Financial Modeling Prep, appends them
point-in-time (never overwritten, same convention as pit_store.py) under
pipeline/data/congress/, and publishes the trailing window with defensible,
computable flags - no invented "conflict of interest" scoring that would need data
this pipeline doesn't have (committee assignments, legislative calendars), and no
claim that any flagged trade was improper:

  LATE_FILING          disclosed more than the STOCK Act's required 45 days after the trade
  OPTIONS_TRADE         the disclosed asset is a stock option, not a plain equity position
  RARE_TRADER            this representative's only disclosed trade in the accumulated
                        history - gated behind a minimum accumulated history span so
                        week one doesn't flag every representative for lack of prior data
  CONCENTRATED_SIZE     the reported range's floor is at least $50,000
  CLUSTER_TRADE          three or more distinct representatives traded the same symbol
                        within a 14-day span
  SAME_SECTOR_REPEAT     this representative has three or more trades in the same sector
                        (looked up from the main research pipeline's own classification,
                        so it only ever covers tickers that pipeline already scores -
                        never a guessed sector) within a trailing 90 days
  BUY_SELL_FLIP          the same representative traded the same symbol in both
                        directions within 60 days
  NOVEL_TICKER            this representative's first-ever disclosed trade in this symbol

Purchases of a plain equity also get a real, factual measurement: the stock's price
change from the purchase date to the latest available close (`return_since_purchase_pct`).
That is a price fact, not a claim about why the price moved or that the trade was
improper - see CongressTrades.jsx's own disclaimer copy.

Run weekly, not daily: FMP's free tier allows 250 requests/day, and disclosures
themselves lag the actual trade by up to 45 days, so daily polling would mostly
re-fetch what a weekly run already has.
"""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from common import LOG, STORE_DIR, load_json, save_json
from congress_trades import CongressTradesClient, CongressTradesError

CONGRESS_DIR = os.path.join(STORE_DIR, "congress")
TRADES = "trades.jsonl"

PUBLISH_WINDOW_DAYS = 120
LATE_FILING_DAYS = 45
# A "rare trader" reading is only trustworthy once the store has covered enough
# calendar time to say a representative really hasn't traded, not just that this
# pipeline hasn't been running long enough to have seen them do it.
RARE_TRADER_MINIMUM_HISTORY_DAYS = 90
CONCENTRATED_SIZE_FLOOR = 50_000
CLUSTER_WINDOW_DAYS = 14
SAME_SECTOR_WINDOW_DAYS = 90
SAME_SECTOR_MINIMUM_COUNT = 3
BUY_SELL_FLIP_WINDOW_DAYS = 60


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


def parse_amount_bounds(amount):
    """The (floor, ceiling) of FMP's reported range string (e.g. "$15,001 - $50,000"
    -> (15001, 50000), "Over $50,000,000" -> (50000000, 50000000)) - STOCK Act
    disclosures only ever report a range, never an exact amount."""
    if not amount:
        return None, None
    numbers = [float(match.replace(",", "")) for match in re.findall(r"\$([\d,]+)", amount)]
    return (min(numbers), max(numbers)) if numbers else (None, None)


def _days_between(earlier, later):
    try:
        start = datetime.fromisoformat(earlier)
        end = datetime.fromisoformat(later)
    except (TypeError, ValueError):
        return None
    return (end - start).days


def _date_gap_days(a, b):
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except (TypeError, ValueError):
        return None


def _is_buy(transaction_type):
    lowered = str(transaction_type or "").lower()
    return "purchase" in lowered or "buy" in lowered


def _is_sell(transaction_type):
    lowered = str(transaction_type or "").lower()
    return "sale" in lowered or "sell" in lowered


def sector_by_ticker():
    """Real sector classification, reused as-is from the main research pipeline - only
    covers tickers inside the actively-scored stock universe. Everything else (bonds,
    municipal notes, unmatched tickers) has no sector here, and SAME_SECTOR_REPEAT
    never guesses one for them."""
    payload = load_json("advisor.json") or {}
    lookup = {}
    for row in (*payload.get("research", []), *payload.get("portfolio_coverage", [])):
        ticker, sector = row.get("ticker"), row.get("sector")
        if ticker and sector:
            lookup[ticker] = sector
    return lookup


def cluster_trade_keys(rows):
    """Trade keys where 3+ distinct representatives traded the same symbol within a
    14-day span of this specific trade - so every trade in a busy stretch is flagged,
    not just whichever one happened to be third chronologically."""
    by_symbol = {}
    for row in rows:
        if row.get("symbol") and row.get("transaction_date"):
            by_symbol.setdefault(row["symbol"], []).append(row)
    flagged = set()
    for trades in by_symbol.values():
        for row in trades:
            distinct_reps = set()
            for other in trades:
                gap = _date_gap_days(row["transaction_date"], other["transaction_date"])
                if other.get("representative") and gap is not None and gap <= CLUSTER_WINDOW_DAYS:
                    distinct_reps.add(other["representative"])
            if len(distinct_reps) >= 3:
                flagged.add(_trade_key(row))
    return flagged


def same_sector_repeat_keys(rows, sector_lookup):
    """Trade keys for a representative with 3+ trades in the same known sector within
    90 days of this trade."""
    by_rep_sector = {}
    for row in rows:
        sector = sector_lookup.get(row.get("symbol"))
        if row.get("representative") and sector and row.get("transaction_date"):
            by_rep_sector.setdefault((row["representative"], sector), []).append(row)
    flagged = set()
    for trades in by_rep_sector.values():
        for row in trades:
            nearby = 0
            for other in trades:
                gap = _date_gap_days(row["transaction_date"], other["transaction_date"])
                if gap is not None and gap <= SAME_SECTOR_WINDOW_DAYS:
                    nearby += 1
            if nearby >= SAME_SECTOR_MINIMUM_COUNT:
                flagged.add(_trade_key(row))
    return flagged


def buy_sell_flip_keys(rows):
    """Trade keys where the same representative traded the same symbol in both
    directions within 60 days - a round trip, not a simple hold."""
    by_rep_symbol = {}
    for row in rows:
        if row.get("representative") and row.get("symbol") and row.get("transaction_date"):
            by_rep_symbol.setdefault((row["representative"], row["symbol"]), []).append(row)
    flagged = set()
    for trades in by_rep_symbol.values():
        for row in trades:
            row_buy, row_sell = _is_buy(row.get("transaction_type")), _is_sell(row.get("transaction_type"))
            if not (row_buy or row_sell):
                continue
            for other in trades:
                if other is row:
                    continue
                other_buy, other_sell = _is_buy(other.get("transaction_type")), _is_sell(other.get("transaction_type"))
                opposite = (row_buy and other_sell) or (row_sell and other_buy)
                gap = _date_gap_days(row["transaction_date"], other["transaction_date"])
                if opposite and gap is not None and gap <= BUY_SELL_FLIP_WINDOW_DAYS:
                    flagged.add(_trade_key(row))
                    break
    return flagged


def novel_ticker_keys(rows):
    """Trade keys that are a representative's earliest disclosed trade in that symbol
    across the full accumulated history."""
    earliest = {}
    for row in rows:
        rep, symbol, when = row.get("representative"), row.get("symbol"), row.get("transaction_date")
        if not (rep and symbol and when):
            continue
        key = (rep, symbol)
        if key not in earliest or when < earliest[key][0]:
            earliest[key] = (when, row)
    return {_trade_key(row) for _when, row in earliest.values()}


def relational_flags(rows):
    """All cross-row flags computed once over the FULL accumulated history, keyed by
    trade identity, so a match outside the published window (e.g. a trade from a year
    ago) is still seen - a member's "novel ticker" trade five months ago must not look
    novel again just because it fell out of the publish window."""
    sector_lookup = sector_by_ticker()
    by_key = {}
    for label, keys in (
        ("CLUSTER_TRADE", cluster_trade_keys(rows)),
        ("SAME_SECTOR_REPEAT", same_sector_repeat_keys(rows, sector_lookup)),
        ("BUY_SELL_FLIP", buy_sell_flip_keys(rows)),
        ("NOVEL_TICKER", novel_ticker_keys(rows)),
    ):
        for key in keys:
            by_key.setdefault(key, []).append(label)
    return by_key


def classify(trade, *, trade_counts, history_days, relational=None):
    flags = list((relational or {}).get(_trade_key(trade), []))
    filing_delay = _days_between(trade.get("transaction_date"), trade.get("disclosure_date"))
    if filing_delay is not None and filing_delay > LATE_FILING_DAYS:
        flags.append("LATE_FILING")
    if "option" in str(trade.get("asset_type") or "").lower():
        flags.append("OPTIONS_TRADE")
    rare_trader_evaluated = history_days >= RARE_TRADER_MINIMUM_HISTORY_DAYS
    if rare_trader_evaluated and trade_counts.get(trade.get("representative"), 0) <= 1:
        flags.append("RARE_TRADER")
    amount_lower, amount_upper = parse_amount_bounds(trade.get("amount"))
    if amount_lower is not None and amount_lower >= CONCENTRATED_SIZE_FLOOR:
        flags.append("CONCENTRATED_SIZE")
    return {
        **trade,
        "amount_lower": amount_lower, "amount_upper": amount_upper,
        "filing_delay_days": filing_delay,
        "flags": flags,
        "rare_trader_evaluated": rare_trader_evaluated,
    }


def is_equity_purchase(row):
    """A plain stock buy - excludes options (already their own flag) and bonds/munis,
    which have no meaningful daily price series to measure against."""
    asset_type = str(row.get("asset_type") or "").lower()
    return bool(row.get("symbol")) and _is_buy(row.get("transaction_type")) \
        and "stock" in asset_type and "option" not in asset_type


def compute_price_performance(rows, client):
    """One price-history request per distinct symbol among this window's equity
    purchases (not per trade), then each trade's own entry/latest/return computed
    locally against that shared series."""
    buys = [row for row in rows if is_equity_purchase(row)]
    earliest_by_symbol = {}
    for row in buys:
        symbol, when = row["symbol"], row["transaction_date"]
        if symbol not in earliest_by_symbol or when < earliest_by_symbol[symbol]:
            earliest_by_symbol[symbol] = when

    histories = {}
    for symbol, earliest_date in earliest_by_symbol.items():
        try:
            histories[symbol] = client.price_history(symbol, from_date=earliest_date)
        except CongressTradesError as exc:
            LOG.warn(f"Congress trades: price history unavailable for {symbol} ({exc})")

    performance = {}
    for row in buys:
        history = histories.get(row["symbol"])
        if not history:
            continue
        entry = next((point["close"] for point in history if point["date"] >= row["transaction_date"]), None)
        latest = history[-1]["close"]
        if entry and latest:
            performance[_trade_key(row)] = {
                "price_at_purchase": entry, "price_latest": latest,
                "price_as_of": history[-1]["date"],
                "return_since_purchase_pct": round((latest / entry - 1) * 100, 2),
            }
    return performance


def summary_stats(rows):
    """Filings are estimated as one per (representative, disclosure_date) pair - FMP's
    per-trade rows don't carry a filing/document ID, and a single PTR commonly bundles
    several line-item trades disclosed the same day."""
    trades = len(rows)
    filings = len({(row.get("representative"), row.get("disclosure_date")) for row in rows
                  if row.get("representative") and row.get("disclosure_date")})
    volume_upper = sum(row.get("amount_upper") or 0 for row in rows)
    politicians = len({row.get("representative") for row in rows if row.get("representative")})
    issuers = len({row.get("symbol") or row.get("asset_description") for row in rows
                  if row.get("symbol") or row.get("asset_description")})
    return {"trades": trades, "filings_estimated": filings, "volume_upper": volume_upper,
            "politicians": politicians, "issuers": issuers}


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

    relational = relational_flags(rows)
    window = [row for row in rows if (row.get("disclosure_date") or "") >= cutoff]
    classified = [classify(row, trade_counts=trade_counts, history_days=history_days, relational=relational)
                 for row in window]
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

    performance = compute_price_performance(results, client)
    for row in results:
        row.update(performance.get(_trade_key(row), {}))

    payload = {
        "schema_version": "1.0.0", "model_version": "congress-trades-v1.1.0",
        "generated_at": generated_at.isoformat(), "status": "success",
        "publish_window_days": PUBLISH_WINDOW_DAYS, "history_days": history_days,
        "late_filing_threshold_days": LATE_FILING_DAYS,
        "rare_trader_minimum_history_days": RARE_TRADER_MINIMUM_HISTORY_DAYS,
        "concentrated_size_floor": CONCENTRATED_SIZE_FLOOR,
        "summary": summary_stats(results),
        "results": results,
    }
    save_json("screens/congress-trades.json", payload)
    LOG.info(f"Congress trades screen: {len(results)} disclosure(s) published, {history_days}d of history")
    return payload


if __name__ == "__main__":
    run()
