"""Weekly political trade disclosure screen: Congress (House + Senate) and the executive
branch (OGE Form 278-T filers, including the President) in one pool.

Fetches new Senate, House, and executive-branch disclosures from Financial Modeling Prep
and the congress-trading-monitor mirror (the only source that carries executive-branch
rows - see congress_trades.py), appends them
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
improper - see CongressTrades.jsx's own disclaimer copy. Priced from FMP first (whatever
symbols the configured plan actually covers), falling back to the same keyless Yahoo
history every options screen in this pipeline already reads - so a purchase still gets
priced when FMP's key has no entitlement at all, not just when it happens to cover a
given symbol.

Run weekly, not daily: FMP's free tier allows 250 requests/day, and disclosures
themselves lag the actual trade by up to 45 days, so daily polling would mostly
re-fetch what a weekly run already has.
"""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from common import LOG, STORE_DIR, load_json, save_json
from congress_trades import (CongressTradesClient, CongressTradesError, SenateEfdClient,
                             StockWatcherClient)

# Imported lazily inside compute_price_performance(), not at module scope: fetch_advisor
# imports congress_signal, which imports this module for is_buy(), so a top-level import
# here would be circular.

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
# Small-cap boundary. A member's first-ever trade in a name (NOVEL_TICKER) is a much
# stronger tell when the name is a small, unfamiliar company than when it's a mega-cap
# most portfolios already hold - EXTRAORDINARY_BUY requires both, not either alone.
OBSCURE_MARKET_CAP_CEILING = 2_000_000_000

# notable_signals() display ranking - separate from congress_signal.score_congressional_
# buying's capped, buy-only, advisor-facing modifier (see that module's docstring for why
# political inputs to the research score are deliberately narrow). This ranking exists only
# to pick a top-N leaderboard for the screen page itself; it is never read by advisor_engine.
NOTABLE_SIGNAL_TOP_N = 5
# The disclosed amount (range floor) at which the size component of a signal's rank saturates
# at 1.0 - chosen so a $1M+ disclosure maxes out the size contribution rather than a handful
# of eight-figure trades dominating every slot regardless of how novel or clustered they are.
NOTABLE_SIGNAL_SIZE_REFERENCE = 1_000_000
NOTABLE_SIGNAL_FLAG_WEIGHTS = {
    "EXTRAORDINARY_BUY": 3.0,
    "CLUSTER_TRADE": 2.0,
    "NOVEL_TICKER": 1.5,
    "CONCENTRATED_SIZE": 1.0,
}


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


def is_buy(transaction_type):
    lowered = str(transaction_type or "").lower()
    return "purchase" in lowered or "buy" in lowered


def is_sell(transaction_type):
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


def market_cap_by_ticker():
    """Market cap, reused as-is from the main research pipeline - same coverage caveat
    as ``sector_by_ticker``: only tickers inside the actively-scored stock universe."""
    payload = load_json("advisor.json") or {}
    lookup = {}
    for row in (*payload.get("research", []), *payload.get("portfolio_coverage", [])):
        ticker, market_cap = row.get("ticker"), row.get("market_cap")
        if ticker and market_cap is not None:
            lookup[ticker] = market_cap
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
            row_buy, row_sell = is_buy(row.get("transaction_type")), is_sell(row.get("transaction_type"))
            if not (row_buy or row_sell):
                continue
            for other in trades:
                if other is row:
                    continue
                other_buy, other_sell = is_buy(other.get("transaction_type")), is_sell(other.get("transaction_type"))
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


def classify(trade, *, trade_counts, history_days, relational=None, market_cap_lookup=None):
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
    # A member's first-ever trade in a small, unfamiliar company - not just a large
    # dollar figure, and not just novelty in isolation (a first-ever trade in a mega-cap
    # everyone already holds is not unusual). Buys only: a rare sell of an obscure name
    # carries none of the "how would they know about this" signal a buy does.
    market_cap = (market_cap_lookup or {}).get(trade.get("symbol"))
    if ("NOVEL_TICKER" in flags and is_buy(trade.get("transaction_type"))
            and market_cap is not None and market_cap < OBSCURE_MARKET_CAP_CEILING):
        flags.append("EXTRAORDINARY_BUY")
    return {
        **trade,
        "amount_lower": amount_lower, "amount_upper": amount_upper,
        "filing_delay_days": filing_delay,
        "flags": flags,
        "rare_trader_evaluated": rare_trader_evaluated,
    }


def notable_signals(rows, *, top_n=NOTABLE_SIGNAL_TOP_N, as_of=None):
    """A curated "most worth noticing" leaderboard over already-classified rows -
    display-only, never fed into advisor_engine or any published score.

    Unlike congress_signal.score_congressional_buying (capped, buy-only, breadth x
    freshness, and the one deliberate exception to this pipeline's "no political inputs"
    rule), this ranks BUYS AND SELLS together by disclosed size, novelty (NOVEL_TICKER /
    EXTRAORDINARY_BUY), and cross-filer clustering (CLUSTER_TRADE), scaled by the same
    freshness decay congress_signal already uses - so a large, unusual, or multiply-
    disclosed trade from *last week* outranks an even larger one from four months ago.

    Deduped to one row per ticker (the highest-ranked disclosure for that symbol) so a
    single prolific filer's repeated trades in one name can't fill every slot.
    """
    from insider_signal import decay  # local import: same lazy pattern as compute_price_performance

    as_of_date = as_of or date.today()
    best_by_ticker = {}
    for row in rows:
        symbol = row.get("symbol")
        transaction_type = row.get("transaction_type")
        direction = "BUY" if is_buy(transaction_type) else "SELL" if is_sell(transaction_type) else None
        if not (symbol and direction):
            continue
        when = row.get("disclosure_date") or row.get("transaction_date")
        try:
            days_since = (as_of_date - date.fromisoformat(when)).days if when else None
        except ValueError:
            days_since = None
        freshness = decay(days_since)
        if freshness <= 0:
            continue

        flags = row.get("flags") or []
        flag_bonus = sum(NOTABLE_SIGNAL_FLAG_WEIGHTS.get(flag, 0.0) for flag in flags)
        amount_lower = row.get("amount_lower") or 0
        size_component = min(1.0, amount_lower / NOTABLE_SIGNAL_SIZE_REFERENCE)
        rank_score = round((size_component + flag_bonus) * freshness, 4)
        if rank_score <= 0:
            continue

        candidate = {
            "ticker": symbol,
            "direction": direction,
            "representative": row.get("representative"),
            "chamber": row.get("chamber"),
            "office": row.get("office"),
            "agency": row.get("agency"),
            "amount_lower": row.get("amount_lower"),
            "amount_upper": row.get("amount_upper"),
            "transaction_date": row.get("transaction_date"),
            "disclosure_date": row.get("disclosure_date"),
            "flags": flags,
            "rank_score": rank_score,
        }
        existing = best_by_ticker.get(symbol)
        if existing is None or rank_score > existing["rank_score"]:
            best_by_ticker[symbol] = candidate

    ranked = sorted(best_by_ticker.values(), key=lambda row: (-row["rank_score"], row["ticker"]))[:top_n]
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    return ranked


def is_equity_purchase(row):
    """A plain stock buy - excludes options (already their own flag) and bonds/munis,
    which have no meaningful daily price series to measure against.

    Executive-branch (OGE 278-T) rows never carry an ``asset_type`` at all - it is null on
    every row the congress-trading-monitor mirror has served so far, confirmed against a
    live pull covering ~2,957 executive-branch rows, none with asset_type set. The
    "stock"-substring check below would silently zero out every executive equity purchase,
    so those rows fall back to a resolved ``symbol`` as the equity signal instead: in that
    same pull, every row with a ticker was a real large-cap equity and every bond/muni row
    had no ticker at all, so presence of a ticker is a reliable (if less precise than
    asset_type) stand-in for this source specifically.
    """
    if not (row.get("symbol") and is_buy(row.get("transaction_type"))):
        return False
    if row.get("chamber") == "executive":
        return True
    asset_type = str(row.get("asset_type") or "").lower()
    return "stock" in asset_type and "option" not in asset_type


def compute_price_performance(rows, client=None, yf=None):
    """One price-history request per distinct symbol among this window's equity
    purchases (not per trade), then each trade's own entry/latest/return computed
    locally against that shared series.

    Tries FMP first when a client is available - it can price a symbol in one call from
    an exact date - then falls back to Yahoo for anything FMP didn't cover (no key, an
    unentitled plan, or a per-symbol miss), using the same ``yahoo_history`` every options
    screen in this pipeline reads. Yahoo's ``period="2y"`` window is filtered locally to
    the purchase date same as FMP's response, so which source answered is invisible to the
    caller except through ``price_source`` on the result.
    """
    from fetch_advisor import yahoo_history  # local import: see the module-level note above

    buys = [row for row in rows if is_equity_purchase(row)]
    earliest_by_symbol = {}
    for row in buys:
        symbol, when = row["symbol"], row["transaction_date"]
        if symbol not in earliest_by_symbol or when < earliest_by_symbol[symbol]:
            earliest_by_symbol[symbol] = when

    histories, sources = {}, {}
    for symbol, earliest_date in earliest_by_symbol.items():
        history = None
        if client is not None:
            try:
                history = client.price_history(symbol, from_date=earliest_date)
            except CongressTradesError as exc:
                LOG.warn(f"Congress trades: FMP price history unavailable for {symbol} ({exc})")
            if history:
                sources[symbol] = "fmp"
        if not history and yf is not None:
            fetched = yahoo_history(symbol, yf)
            points = [{"date": day, "close": close} for day, close in
                      zip(fetched.get("dates") or [], fetched.get("closes") or [])
                      if day and close is not None and day >= earliest_date]
            if points:
                history = points
                sources[symbol] = "yahoo"
        if history:
            histories[symbol] = history

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
                "price_source": sources.get(row["symbol"]),
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
    market_cap_lookup = market_cap_by_ticker()
    window = [row for row in rows if (row.get("disclosure_date") or "") >= cutoff]
    classified = [classify(row, trade_counts=trade_counts, history_days=history_days,
                          relational=relational, market_cap_lookup=market_cap_lookup)
                 for row in window]
    classified.sort(key=lambda row: row.get("disclosure_date") or "", reverse=True)
    return classified, history_days


def collect(fmp_factory=CongressTradesClient, mirror_factory=StockWatcherClient,
            efd_factory=SenateEfdClient):
    """Every disclosure any available source will give up, recording why anything that failed did.

    A failed fetch used to be logged and then forgotten, so a run where the provider refused
    every request published exactly what a genuinely quiet week publishes: zero disclosures
    under a "success" status, which the page reads out as "no disclosures collected yet". The
    two are not the same thing and the difference is the whole story, so the failures come back
    with the rows and end up in the published payload.

    Two independent sources rather than one, because neither is dependable alone. FMP answers
    the Congressional endpoints with HTTP 402 unless the key's plan covers them - a billing
    boundary no retry gets past - while the public house/senate mirrors need no key at all.
    They are attempted independently and pooled rather than tried in priority order, since
    they do not cover the same rows: FMP returns a recent page, the mirrors carry full
    history. ``append_new_trades`` already keys on the disclosure identity, so a row arriving
    from both is recorded once.

    Returns ``(fmp_client, rows, failures, counts)``. ``fmp_client`` is None when no key is
    configured - it is the only source that can price a purchase, so the caller needs to know
    whether the performance column is reachable. ``counts`` carries how many usable rows each
    source produced, so a mirror that silently changes its column names reads as zero from
    that source rather than as a quiet Congress.
    """
    rows, failures, counts = [], [], {}

    fmp_client = None
    try:
        fmp_client = fmp_factory()
    except CongressTradesError as exc:
        # Not fatal any more: the keyless mirrors are a complete source of disclosures on
        # their own, so a missing or unentitled key costs the price-performance column
        # rather than the screen.
        failures.append(f"fmp-client: {exc}")
        LOG.warn(f"Congress trades: FMP unavailable ({exc})")

    if fmp_client is not None:
        for name, fetch in (("fmp-senate", fmp_client.senate_latest),
                            ("fmp-house", fmp_client.house_latest)):
            try:
                fetched = fetch()
            except CongressTradesError as exc:
                failures.append(f"{name}: {exc}")
                LOG.warn(f"Congress trades fetch failed ({name}: {exc})")
                continue
            rows.extend(fetched)
            counts[name] = len(fetched)

    mirror_client = mirror_factory()
    sources = [("mirror-senate", mirror_client.senate_latest),
               ("mirror-house", mirror_client.house_latest),
               # The only source anywhere in this module that covers executive-branch (OGE
               # 278-T) filers - the President included - since FMP and the Senate eFD system
               # are Congress-only. See congress_trades.py's StockWatcherClient docstring.
               ("mirror-executive", mirror_client.executive_latest)]
    if efd_factory is not None:
        # The Senate's own system, added after both original stock-watcher mirrors were
        # withdrawn and started answering 403 to everything. Senate only - the House Clerk's
        # own site has no equivalent structured search - but mirror-house now reaches House
        # disclosures too via congress-trading-monitor's default HOUSE_DATASET (see
        # congress_trades.py), so this and mirror-house together are meant to close the gap
        # this comment used to describe as permanent, not just narrow it.
        sources.insert(0, ("senate-efd",
                           lambda: efd_factory().fetch(since_days=PUBLISH_WINDOW_DAYS)))

    for name, fetch in sources:
        try:
            fetched, seen = fetch()
        # Broad on purpose: these sources are HTML and third-party JSON, so a shape change
        # raises whatever the parser raises. One source failing has to cost that source's
        # coverage and be reported, never take down a run the other sources could publish.
        except Exception as exc:  # noqa: BLE001
            reason = exc if isinstance(exc, CongressTradesError) else f"{type(exc).__name__}: {exc}"
            failures.append(f"{name}: {reason}")
            LOG.warn(f"Congress trades fetch failed ({name}: {reason})")
            continue
        rows.extend(fetched)
        counts[name] = len(fetched)
        if seen and not fetched:
            # Rows arrived and none survived normalization: the dataset is reachable but no
            # longer shaped the way this reads it. A different problem from an unreachable
            # source, and one that has to be said out loud rather than averaged into a total.
            failures.append(f"{name}: read {seen} row(s), none usable - the dataset's "
                            "columns may have changed")
    return fmp_client, rows, failures, counts


def publication_status(results, stored, failures):
    """Say which of the three "no rows" situations this is, or that there are rows.

    With more than one source, "there are rows" splits in two: every source answered, or some
    did and the rest failed. The second still publishes real disclosures - it just publishes
    fewer than it should, which the page has to be able to say.
    """
    if results:
        return ("partial", "SOME_SOURCES_UNAVAILABLE") if failures else ("success", None)
    if failures:
        return "unavailable", "CONGRESS_DISCLOSURE_FEED_UNAVAILABLE"
    if not stored:
        return "unavailable", "NO_DISCLOSURES_COLLECTED_YET"
    return "unavailable", "NO_DISCLOSURES_IN_PUBLISH_WINDOW"


def run():
    # Passed explicitly rather than relying on collect()'s defaults: a default argument is
    # bound at import, so a test (or any caller) swapping the module-level client would be
    # silently ignored and reach the real provider instead.
    fmp_client, fetched, failures, source_counts = collect(
        CongressTradesClient, StockWatcherClient, SenateEfdClient)
    stored_before = _read_all()
    if not fetched and not stored_before:
        # Nothing reachable and nothing ever collected is what a local or offline environment
        # looks like, not a finding about Congress - and publishing an empty screen from one
        # would overwrite whatever the last real run left behind. Once history exists, a run
        # that collects nothing does publish, so a genuine feed outage is still reported.
        LOG.warn("Congress trades collection skipped: no source returned rows and nothing is "
                 f"stored yet ({'; '.join(failures) or 'no failures reported'})")
        return None
    added = append_new_trades(fetched) if fetched else 0
    LOG.info(f"Congress trades: +{added} new disclosure(s) recorded")

    generated_at = datetime.now(timezone.utc)
    stored = _read_all()
    results, history_days = build_results(stored, as_of=generated_at)

    # Price history costs one request per symbol, so it is only worth asking for when there
    # is something to measure. FMP is tried first when a key is configured; yfinance - the
    # same keyless Yahoo client every options screen in this pipeline uses - covers whatever
    # FMP didn't, so a run with no entitled FMP key still gets "since purchase" figures
    # rather than losing the column entirely.
    yf = None
    try:
        import yfinance as yf
    except ImportError:
        LOG.warn("Congress trades: yfinance not installed - Yahoo price fallback unavailable")
    performance = (compute_price_performance(results, fmp_client, yf=yf)
                   if results and (fmp_client or yf) else {})
    for row in results:
        row.update(performance.get(_trade_key(row), {}))

    status, reason_code = publication_status(results, stored, failures)
    payload = {
        "schema_version": "1.2.0", "model_version": "congress-trades-v1.3.0",
        "generated_at": generated_at.isoformat(), "status": status,
        **({"reason_code": reason_code} if reason_code else {}),
        "publish_window_days": PUBLISH_WINDOW_DAYS, "history_days": history_days,
        "late_filing_threshold_days": LATE_FILING_DAYS,
        "rare_trader_minimum_history_days": RARE_TRADER_MINIMUM_HISTORY_DAYS,
        "concentrated_size_floor": CONCENTRATED_SIZE_FLOOR,
        "collection": {"disclosures_fetched": len(fetched), "new_disclosures": added,
                       "disclosures_stored": len(stored), "failures": failures,
                       "source_counts": source_counts},
        "summary": summary_stats(results),
        "signals": notable_signals(results, as_of=generated_at.date()),
        "results": results,
    }
    save_json("screens/congress-trades.json", payload)
    LOG.info(f"Congress trades screen: {len(results)} disclosure(s) published ({status}), "
             f"{history_days}d of history")
    return payload


if __name__ == "__main__":
    run()
