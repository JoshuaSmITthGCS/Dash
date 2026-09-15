"""Eviction-based top-10 tracking and mark-to-market P&L for the options screens that
actually refresh live in production: ``options.json``, ``covered-calls.json``,
``cash-secured-puts.json`` and ``short-term-trades.json`` - all published by
``build_options_strategies.py``. The other four options build scripts
(``build_protective_put_screen.py``, ``build_collar_screen.py``,
``build_vertical_spread_screen.py``, ``build_advanced_options_screen.py``) are each gated
behind an ``ENABLE_*`` flag this pipeline does not currently set in
``.github/workflows/refresh-advisor.yml``, so they never get a live daily refresh and are not
wired in here - a "date predicted" on one of them would reflect a stale, manually-produced
snapshot rather than a real market date, which is a different and worse thing to publish than
simply not having the feature yet.

Unlike swing_pit_store's permanent record, an entry here is dropped the moment a position
falls out of its screen's top 10 - "how has this position done since it entered the CURRENT
top 10", not an all-time first-sighting record. Same rule as momentum_pit_store.py and
growth_track_record.py.

Marking a still-open position reuses options_common's own Black-Scholes pricer
(call_price/put_price) with the ticker's OWN fresh spot price and realized volatility from
this same run - the same construction the walk-forward backtests already use to price a leg
with no live option-chain call (see options_common.py's module docstring on why r=0 and why
IV here is a realized-vol proxy, not a market-quoted one - a mark computed this way is a
model mark, not a quote-derived one). Once a position's own expiration date has passed, there
is no time value left to model, so it is settled on intrinsic value at today's spot instead.

A covered call's capital is the cost of owning the 100 shares behind it, so its P&L includes
the stock's own move, not just the short call leg - a cash-secured put's capital is cash
collateral, which does not itself gain or lose value, so its P&L is the put leg alone.
"""

import json
import os

from options_common import call_price, days_to_expiration, put_price

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "options_track_record")
FIRST_SEEN_FILENAME = "top10.json"

# One published file per sub-screen; "options" (buy) carries no capital_required field, so
# it is computed here as premium x100 - see capital_required_for.
SUB_SCREENS = ("options", "covered_calls", "cash_secured_puts", "short_term_trades")

# Only covered_calls and a short-term "sell_call" pick assume the position is collateralized
# by owning 100 shares of the underlying - a cash-secured put's collateral is cash, which
# does not move, and a bought option's cost is the premium alone.
STOCK_COLLATERALIZED = {"covered_calls"}


def legs_for(sub_screen, row):
    """This row's option leg(s) in one canonical shape - ``[{action, option_type, strike,
    premium}]`` - plus whether the strategy implicitly includes a long-100-shares leg
    (covered call's collateral). Returns ``([], False)`` for a row this module does not
    recognize rather than raising, so a malformed or renamed row is simply never tracked.
    """
    if sub_screen == "options":
        return ([{"action": "buy", "option_type": row.get("option_type"),
                 "strike": row.get("strike"), "premium": row.get("mid")}], False)
    if sub_screen in ("covered_calls", "cash_secured_puts", "short_term_trades"):
        legs = [{"action": leg.get("action"), "option_type": leg.get("option_type"),
                "strike": leg.get("strike"), "premium": leg.get("mid")}
               for leg in (row.get("legs") or [])]
        stock_leg = sub_screen in STOCK_COLLATERALIZED or (
            sub_screen == "short_term_trades" and row.get("strategy") == "sell_call")
        return legs, stock_leg
    return [], False


def capital_required_for(sub_screen, row):
    """``options.json`` never publishes capital_required (its position IS the premium paid);
    every other sub-screen already publishes it."""
    if sub_screen == "options":
        mid = row.get("mid")
        return round(mid * 100, 2) if mid else None
    return row.get("capital_required")


def _leg_mark_or_settle(leg, spot_now, iv_now, dte_now):
    """One leg's per-share value today: a Black-Scholes mark while time remains, intrinsic
    value once the expiration date has passed - there is nothing left to model past it.
    """
    option_type = leg.get("option_type")
    strike = leg.get("strike")
    if strike is None or option_type not in ("call", "put"):
        return None
    if dte_now is not None and dte_now > 0:
        if not iv_now:
            return None
        pricer = call_price if option_type == "call" else put_price
        return pricer(spot_now, strike, iv_now, dte_now)
    return (max(0.0, spot_now - strike) if option_type == "call"
           else max(0.0, strike - spot_now))


def position_pnl(position, spot_now, iv_now, as_of=None):
    """Total dollar P&L (per 100-share contract multiplier) of every leg in ``position``,
    marked or settled at ``spot_now``, plus the stock leg's own move when the strategy is
    collateralized by owning the underlying. ``None`` if any leg cannot be priced - a partial
    mark is worse than an honest "unavailable" here, since summing an unresolved leg as zero
    would understate risk on the largest, least liquid names most.
    """
    if spot_now is None:
        return None
    dte_now = days_to_expiration(position.get("expiration"), as_of)
    total = 0.0
    for leg in position.get("legs") or []:
        mark = _leg_mark_or_settle(leg, spot_now, iv_now, dte_now)
        if mark is None or leg.get("premium") is None:
            return None
        sign = 1 if leg.get("action") == "buy" else -1
        total += sign * (mark - leg["premium"]) * 100
    if position.get("stock_leg"):
        entry_price = position.get("entry_underlying_price")
        if entry_price is None:
            return None
        total += (spot_now - entry_price) * 100
    return total


def track_record_for(position, spot_now, iv_now, as_of=None):
    """This position's track record: when it entered the current top 10, and its P&L since -
    in dollars and as a percent of the capital the position actually required. ``None``
    P&L fields mean the position could not be priced (e.g. no fresh realized-vol reading this
    run), not that it is worthless.

    Even on the day a position enters, its P&L is not guaranteed to read exactly zero: the
    entry premium is a real quoted mid from the option chain, but every mark after entry -
    including one taken minutes later - is a Black-Scholes estimate off realized volatility,
    not a re-quote of the same contract (see this module's own docstring, and
    options_common.py's, on why). Realized volatility is not the market's own implied
    volatility, so the two can and typically do disagree even with the underlying unchanged -
    a small day-one gap is that basis difference, not a sign the position already moved.
    """
    if not position:
        return {"date_predicted": None, "pnl_dollars": None, "pnl_pct_of_capital": None}
    pnl = position_pnl(position, spot_now, iv_now, as_of=as_of)
    capital = position.get("capital_required")
    return {
        "date_predicted": position.get("date_predicted"),
        "pnl_dollars": round(pnl, 2) if pnl is not None else None,
        "pnl_pct_of_capital": (round(pnl / capital * 100, 2)
                               if pnl is not None and capital else None),
    }


def _store_path(store_dir=None):
    return os.path.join(store_dir or STORE_DIR, FIRST_SEEN_FILENAME)


def load_first_seen(store_dir=None):
    """``{sub_screen: {ticker: position}}`` for every position currently in that
    sub-screen's top 10 - see ``update_first_seen`` for what a stored ``position`` holds.
    """
    path = _store_path(store_dir)
    if not os.path.exists(path):
        return {sub: {} for sub in SUB_SCREENS}
    with open(path) as handle:
        raw = json.load(handle)
    return {sub: raw.get(sub) or {} for sub in SUB_SCREENS}


def update_first_seen(results_by_sub_screen, *, recorded_at_date, store_dir=None, top_n=10):
    """Eviction-based top-10 membership per sub-screen: keeps a position while its ticker's
    rank stays <= ``top_n`` in that sub-screen (rank moving around within the top 10 is fine
    and never resets it), removes it the moment the ticker falls outside ``top_n`` - the
    position's full terms (legs, strikes, entry premiums, expiration, capital required) are
    snapshotted once, on entry, so it can be marked correctly for as long as it stays tracked
    even as the published row's own numbers move with the market. Re-entering later starts a
    fresh clock rather than resuming the old one.

    ``results_by_sub_screen`` is ``{sub_screen: published_rows}`` for whichever of
    ``SUB_SCREENS`` this call has fresh results for.
    """
    existing = load_first_seen(store_dir)
    changed = False
    for sub, results in (results_by_sub_screen or {}).items():
        current = {}
        for row in results or []:
            ticker, rank = row.get("ticker"), row.get("rank")
            price, expiration = row.get("price"), row.get("expiration")
            if not ticker or rank is None or rank > top_n or not price or not expiration:
                continue
            legs, stock_leg = legs_for(sub, row)
            if not legs or any(leg.get("strike") is None or leg.get("premium") is None
                               for leg in legs):
                continue
            current[ticker] = {
                "date_predicted": recorded_at_date,
                "entry_underlying_price": price,
                "expiration": expiration,
                "capital_required": capital_required_for(sub, row),
                "legs": legs,
                "stock_leg": stock_leg,
            }
        bucket = existing.setdefault(sub, {})
        for ticker in [*bucket]:
            if ticker not in current:
                del bucket[ticker]
                changed = True
        for ticker, position in current.items():
            if ticker not in bucket:
                bucket[ticker] = position
                changed = True
    if changed:
        store_dir = store_dir or STORE_DIR
        os.makedirs(store_dir, exist_ok=True)
        with open(_store_path(store_dir), "w") as handle:
            json.dump(existing, handle, sort_keys=True, indent=2)
    return existing
