"""Publishes the earnings-only catalyst / expected-move screen to screens/catalyst.json.

catalyst_screen_signals.py holds every formula, gate and citation; this script assembles
real inputs for it. Scoped to scheduled earnings only - see that module's docstring for why
FDA/court/index/contract-award catalysts are explicitly out of scope for this screen.

Options-chain data is opt-in (ENABLE_CATALYST_SCREEN=1), same tradeoff and same convention
as build_options_screen.py's ENABLE_MULTIDAY_OPTIONS_SCREEN: each qualifying ticker costs up
to two extra option-chain requests (the expiry spanning earnings, and the one just before
it) on top of what fetch_advisor.py already pulls.

This is a Stage-0 research filter, like build_pre_breakout_screen.py, not a validated
strategy or a trade instruction - nothing in this codebase places option orders or talks to
a brokerage.
"""

import os
from datetime import date, datetime, timezone

from catalyst_screen_signals import (CATALYST_EVIDENCE, DEFAULT_CONFIG, days_between,
                                     event_isolated_expected_move_pct, gate_reasons,
                                     iv_implied_move_pct, meets_liquidity_floor,
                                     straddle_expected_move_pct)
from common import LOG, save_json
from fetch_advisor import yahoo_history
from options_common import (days_to_expiration, expiration_spans_earnings, next_earnings_date,
                            select_by_target_moneyness)
from peer_groups import peer_group
from screen_inputs import median_dollar_volume

SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "catalyst-earnings-v0.1.0"
CONFIG_VERSION = "screens-v1.0.0"
OUTPUT = "screens/catalyst.json"
MINIMUM_HISTORY_SESSIONS = 21


def _bracketing_expirations(expirations, earnings_date, as_of):
    """(pre, post) expiration strings: ``post`` is the earliest expiration that spans
    ``earnings_date``, ``pre`` is the one immediately before it in the sorted expiration
    list (None if ``post`` is the nearest expiration Yahoo lists at all - there is nothing
    shorter-dated to difference against).

    Expiration strings are ISO ``YYYY-MM-DD``, which sorts correctly as plain strings.
    """
    ordered = sorted(expirations or [])
    post_index = next((index for index, expiration in enumerate(ordered)
                       if expiration_spans_earnings(expiration, earnings_date, as_of)), None)
    if post_index is None:
        return None, None
    pre = ordered[post_index - 1] if post_index > 0 else None
    return pre, ordered[post_index]


def _atm_iv_and_mids(ticker_obj, expiration, price):
    """Averaged ATM call/put implied vol (whichever resolve and pass the liquidity floor)
    plus each side's fill mid, for one expiration - or all-None fields if the chain, or
    every ATM contract on it, is unavailable/illiquid.
    """
    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001 - a missing/broken chain must not sink the ticker
        LOG.info(f"catalyst screen: chain unavailable for {expiration} ({type(exc).__name__})")
        return None, None, None
    call = select_by_target_moneyness(chain.calls, price, 0.0)
    put = select_by_target_moneyness(chain.puts, price, 0.0)
    ivs = [contract["implied_volatility"] for contract in (call, put)
          if contract and meets_liquidity_floor(contract) and contract["implied_volatility"]]
    iv = sum(ivs) / len(ivs) if ivs else None
    call_mid = call["mid"] if call and meets_liquidity_floor(call) else None
    put_mid = put["mid"] if put and meets_liquidity_floor(put) else None
    return iv, call_mid, put_mid


def build_row(entry, yf, as_of=None, config=None):
    """One candidate row per ticker, or None if it isn't within the catalyst window at all
    (cheap to check before paying for any option-chain request) - tickers that reach a
    chain fetch but fail a gate afterward are still returned, carrying their reason codes,
    matching pre_breakout_signals' "account for the whole universe it was given" contract.
    """
    config = config or DEFAULT_CONFIG
    ticker = entry.get("ticker")
    if not ticker or yf is None:
        return None
    as_of_date = as_of or date.today()

    try:
        ticker_obj = yf.Ticker(ticker)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: catalyst screen ticker unavailable ({type(exc).__name__})")
        return None

    earnings_date = next_earnings_date(ticker_obj, ticker, as_of_date)
    days_to_earnings = days_between(as_of_date, earnings_date)
    if (days_to_earnings is None
            or not (config["minimum_days_to_earnings"] <= days_to_earnings <= config["maximum_days_to_earnings"])):
        return None  # outside the window entirely - not worth an option-chain request

    history = yahoo_history(ticker, yf, ticker_obj=ticker_obj)
    closes, volumes = history["closes"], history["volumes"]
    if len(closes) < MINIMUM_HISTORY_SESSIONS:
        return None
    price = entry.get("price") or closes[-1]

    try:
        expirations = ticker_obj.options
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: options unavailable ({type(exc).__name__})")
        expirations = []
    pre_expiration, post_expiration = _bracketing_expirations(expirations, earnings_date, as_of_date)

    post_iv = post_call_mid = post_put_mid = pre_iv = None
    if post_expiration:
        post_iv, post_call_mid, post_put_mid = _atm_iv_and_mids(ticker_obj, post_expiration, price)
    if pre_expiration:
        pre_iv, _pre_call_mid, _pre_put_mid = _atm_iv_and_mids(ticker_obj, pre_expiration, price)

    post_dte = days_to_expiration(post_expiration, as_of_date) if post_expiration else None
    pre_dte = days_to_expiration(pre_expiration, as_of_date) if pre_expiration else None

    expected_move = event_isolated_expected_move_pct(pre_iv, pre_dte, post_iv, post_dte)
    group_id, group_label = peer_group(entry)
    row = {
        "ticker": ticker, "name": entry.get("name"), "sector": entry.get("sector"),
        "peer_group": group_id, "peer_group_label": group_label,
        "price": price, "market_cap": entry.get("market_cap"),
        "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
        "structural_score": entry.get("score"), "data_coverage": entry.get("data_coverage"),
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "days_to_earnings": days_to_earnings,
        "date_confidence_note": (
            "Yahoo's earnings calendar carries no confirmed-vs-estimated flag the way "
            "institutional providers (Wall Street Horizon, FactSet) do - see "
            "options_common.next_earnings_date's own docstring. Treat this date as the best "
            "available, not as confirmed."
        ),
        "pre_expiration": pre_expiration, "pre_days_to_expiration": pre_dte,
        "post_expiration": post_expiration, "post_days_to_expiration": post_dte,
        "expected_move_pct": round(expected_move, 3) if expected_move is not None else None,
        # Context only, never scored - see catalyst_screen_signals module docstring.
        "unisolated_iv_move_pct": (round(iv_implied_move_pct(post_iv, post_dte), 3)
                                   if post_iv is not None and post_dte else None),
        "straddle_move_pct": (round(straddle_expected_move_pct(post_call_mid, post_put_mid, price), 3)
                              if post_call_mid is not None and post_put_mid is not None else None),
        "post_atm_implied_volatility": round(post_iv, 4) if post_iv is not None else None,
        "pre_atm_implied_volatility": round(pre_iv, 4) if pre_iv is not None else None,
    }
    row["reason_codes"] = gate_reasons(row, config)
    row["eligibility"] = not row["reason_codes"]
    return row


def build_rows(universe, yf, as_of=None, config=None):
    return [row for row in (build_row(entry, yf, as_of, config) for entry in universe) if row is not None]


def to_result(row):
    return {key: value for key, value in row.items()}


def unavailable(reason_code, generated_at):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code,
        "evidence": CATALYST_EVIDENCE, "window": DEFAULT_CONFIG, "results": [],
    }


def payload(results, generated_at, config):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at, "status": "success",
        "scope_note": (
            "Earnings-only by design - see catalyst_screen_signals.py's module docstring "
            "for why FDA/PDUFA, court rulings, index reconstitution, and government-contract "
            "awards are out of scope for this screen rather than missing from it."
        ),
        "evidence": CATALYST_EVIDENCE,
        "window": config,
        "eligible_count": sum(1 for row in results if row["eligibility"]),
        "scored_count": len(results),
        "results": sorted(results, key=lambda row: (not row["eligibility"], row["days_to_earnings"])),
    }


def run(as_of=None):
    if os.getenv("ENABLE_CATALYST_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Catalyst screen: opt-in flag not set, skipping (set ENABLE_CATALYST_SCREEN=1)")
        return None
    from common import load_json
    payload_in = load_json("advisor.json") or {}
    universe = [*payload_in.get("research", []), *payload_in.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Catalyst screen: no published universe to scan, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json(OUTPUT, result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json(OUTPUT, result)
        return result

    rows = build_rows(universe, yf, as_of)
    results = [to_result(row) for row in rows]
    result = payload(results, generated_at, DEFAULT_CONFIG)
    save_json(OUTPUT, result)
    LOG.info(f"Catalyst screen: {len(results)} tickers in the earnings window "
             f"({result['eligible_count']} eligible)")
    return result


if __name__ == "__main__":
    run()
