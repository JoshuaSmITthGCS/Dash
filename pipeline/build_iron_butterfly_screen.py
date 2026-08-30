"""Publishes the "Iron butterfly" options-strategy research screen.

An iron butterfly is the iron condor's close cousin: same four-leg, defined-risk,
range-bound structure (sell an inner spread, buy two further-OTM wings for protection),
except the two SHORT strikes collapse onto ONE at-the-money strike instead of being spread
apart. Collapsing the short strikes concentrates the entire short premium at a single point,
which produces a bigger net credit (and a correspondingly bigger max profit) than an iron
condor built from the same chain, but at the cost of a narrower profitable range - the
break-evens sit tighter around spot, so a smaller move in either direction erodes the whole
edge. Mechanically this file mirrors build_advanced_options_screen.py's `build_iron_condor_row`
closely enough that most of the differences are called out inline below; the one REAL
mechanical difference is strike selection - instead of `select_by_target_delta` picking two
different short strikes, both short legs must land on the SAME near-the-money strike, so this
reuses `select_contract` (per-side "tightest-spread near-the-money contract") plus
build_advanced_options_screen.py's `_contract_at_strike` strike-matching fallback, exactly the
way that file's own `build_straddle_row` already forces its two ATM legs onto one strike.

Options-chain data is opt-in (ENABLE_IRON_BUTTERFLY_SCREEN=1), the same tradeoff every other
options screen in this pipeline makes: one extra options-chain request per ticker on top of
what fetch_advisor.py already pulls. This is a research screen, not a trade instruction or
order-routing feature - nothing in this codebase places option orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

import iv_archive
from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from build_advanced_options_screen import _contract_at_strike
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expiration_spans_earnings,
                            iv_skew, liquidity_factor, next_earnings_date, probability_below,
                            put_call_oi_ratio, realized_volatility_20d, realized_vol_percentile,
                            research_universe_factors, select_by_target_delta, select_contract,
                            select_expiration, single_expiration_gex, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
# Wing convention matches build_advanced_options_screen.py's LONG_WING_TARGET_DELTA exactly -
# there is no "short wing" delta target here at all, since both short legs are pinned to the
# ATM strike by construction rather than selected by a target delta.
LONG_WING_TARGET_DELTA = 0.08
MINIMUM_HISTORY_SESSIONS = 21

# Same "calm, not directional" reasoning as build_advanced_options_screen.py's
# IRON_CONDOR_WEIGHTS comment: an iron butterfly's failure mode is an unexpected move in
# EITHER direction, arguably worse than an iron condor's, since the butterfly's profitable
# range is narrower to begin with (break-evens sit at atm_strike +/- net_credit, not at a
# pair of short strikes spread further apart) - the same size move that merely dents an iron
# condor can blow straight through a butterfly's break-evens. research_confidence is an
# unsigned quality gate (neither strategy picks a directional side). Weights themselves are a
# direct carry-over of IRON_CONDOR_WEIGHTS - same factor roles, same structure family.
IRON_BUTTERFLY_WEIGHTS = {"credit_efficiency": .34, "probability_in_range": .30, "liquidity": .21,
                          "news_sentiment": .08, "research_confidence": .07}


def fetch_chain(entry, yf, as_of=None, generated_at=None):
    """Shared per-ticker setup: history, expiration selection, and one option chain fetch.

    Deliberately the same shape as build_advanced_options_screen.py's fetch_chain (this
    screen only ever builds ONE strategy per ticker, so there's no second consumer to share
    the fetch with the way that file's iron-condor/straddle pair does, but keeping the tuple
    shape identical keeps the two files easy to read side by side).
    """
    ticker = entry.get("ticker")
    if not ticker or yf is None:
        return None
    history = yahoo_history(ticker, yf)
    closes = history["closes"]
    if len(closes) < MINIMUM_HISTORY_SESSIONS:
        return None
    price = closes[-1]
    realized = realized_volatility_20d(closes)
    trend = trend_20d(closes)

    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: options unavailable ({type(exc).__name__})")
        return None
    expiration, dte = select_expiration(expirations, MIN_DAYS_TO_EXPIRATION, MAX_DAYS_TO_EXPIRATION,
                                        TARGET_DAYS_TO_EXPIRATION, as_of)
    if expiration is None:
        return None
    earnings_date = next_earnings_date(ticker_obj, ticker, as_of)
    if expiration_spans_earnings(expiration, earnings_date, as_of):
        # Same reasoning as build_advanced_options_screen.py: an earnings-inflated premium
        # would misrepresent this as a bigger edge than it is, for a strategy whose whole
        # point is betting on calm, not a catalyst.
        LOG.info(f"{ticker}: excluded, {expiration} spans earnings on {earnings_date}")
        return None

    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None
    return (ticker, price, dte, expiration, trend, realized, chain, entry, len(closes), generated_at, as_of, closes)


def build_iron_butterfly_row(setup):
    """Sell an ATM straddle + buy OTM wings on both sides, or None if legs don't qualify.

    Strike selection mirrors build_straddle_row's ATM-matching logic (same file that already
    houses _contract_at_strike): pick each side's near-the-money contract independently via
    select_contract, and if the two land on different strikes, force one side onto the
    other's strike with the strike-matching fallback rather than accept a straddle-shaped
    mismatch. Unlike the iron condor's two DIFFERENT short strikes (short_call != short_put,
    each chosen by its own target-delta search), both short legs here must be the exact same
    contract-adjacent strike - that collapse is the entire mechanical distinction between
    this screen and the iron condor.
    """
    ticker, price, dte, expiration, trend, realized, chain, entry, history_sessions, generated_at, as_of, closes = setup

    atm_call = select_contract(chain.calls, price)
    atm_put = select_contract(chain.puts, price)
    if atm_call is None or atm_put is None:
        return None

    if atm_call["strike"] != atm_put["strike"]:
        # Same fallback build_straddle_row uses: keep whichever side is already closer to
        # spot and re-select the other side AT that strike, rather than accepting two legs
        # that don't share a strike (which would make this a broken butterfly, not one).
        call_distance = abs(atm_call["strike"] - price)
        put_distance = abs(atm_put["strike"] - price)
        if call_distance <= put_distance:
            atm_put = _contract_at_strike(chain.puts, atm_call["strike"], price)
        else:
            atm_call = _contract_at_strike(chain.calls, atm_put["strike"], price)
        if atm_call is None or atm_put is None or atm_call["strike"] != atm_put["strike"]:
            return None
    atm_strike = atm_call["strike"]

    long_call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=LONG_WING_TARGET_DELTA)
    long_put = select_by_target_delta(chain.puts, price, dte, side="put", target_delta=LONG_WING_TARGET_DELTA)
    if long_call is None or long_put is None:
        return None
    if not (long_call["strike"] > atm_strike > long_put["strike"]):
        return None

    net_credit = (atm_call["mid"] - long_call["mid"]) + (atm_put["mid"] - long_put["mid"])
    call_wing_width = long_call["strike"] - atm_strike
    put_wing_width = atm_strike - long_put["strike"]
    max_loss = max(call_wing_width, put_wing_width) - net_credit
    if net_credit <= 0 or max_loss <= 0:
        return None
    max_profit = net_credit
    breakeven_up = atm_strike + net_credit
    breakeven_down = atm_strike - net_credit

    # probability_in_range here is computed against the actual profitable BREAK-EVEN band
    # (atm_strike +/- net_credit), not against the wing strikes the way the iron condor's
    # probability_in_range is computed against its short strikes. The two structures need
    # different definitions: an iron condor is flat-max-profit across its whole
    # short-put-to-short-call range, so "finishes between the short strikes" IS "at max
    # profit". An iron butterfly's payoff is a tent, not a plateau - profit peaks exactly at
    # atm_strike and decays linearly to zero at each break-even, so "finishes between the
    # wing strikes" would overstate how often the trade is actually profitable. Break-evens
    # are the correct boundary for "probability of ANY profit"; using the wing strikes here
    # instead would silently describe a wider, rosier range than the position really has.
    prob_below_up = probability_below(price, breakeven_up, atm_call["implied_volatility"], dte)
    prob_below_down = probability_below(price, breakeven_down, atm_put["implied_volatility"], dte)
    probability_in_range = (None if prob_below_up is None or prob_below_down is None
                            else prob_below_up - prob_below_down)
    credit_efficiency = net_credit / max_loss
    skew = iv_skew(chain.calls, chain.puts, price, dte)
    pc_oi_ratio = put_call_oi_ratio(chain.calls, chain.puts)
    gex = single_expiration_gex(chain.calls, chain.puts, price, dte)
    vol_percentile = realized_vol_percentile(closes)
    research_factors = research_universe_factors(entry, generated_at, as_of, sentiment_mode="calm")

    group_id, group_label = peer_group(entry)
    return {
        "strategy": "iron_butterfly", "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": history_sessions, "structural_score": entry.get("score"), "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": max_loss * 100,
        "atm_call": atm_call, "atm_put": atm_put, "long_call": long_call, "long_put": long_put,
        "metrics": {
            "net_credit": round(net_credit, 4), "max_profit": round(max_profit, 4),
            "max_loss": round(max_loss, 4),
            "probability_in_range": round(probability_in_range, 4) if probability_in_range is not None else None,
            "breakeven_up": round(breakeven_up, 4), "breakeven_down": round(breakeven_down, 4),
            "iv_skew": skew, "put_call_oi_ratio": pc_oi_ratio, "realized_volatility_percentile": vol_percentile,
            # Read-only - see build_options_screen.py's identical comment: only
            # build_options_strategies.py's shared fetch writes to iv_archive.
            "iv_percentile": iv_archive.iv_percentile(ticker), "single_expiration_gex": gex,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "credit_efficiency": credit_efficiency,
            "probability_in_range": probability_in_range,
            "liquidity": min(liquidity_factor(atm_call), liquidity_factor(atm_put),
                            liquidity_factor(long_call), liquidity_factor(long_put)),
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    rows = []
    for entry in universe:
        setup = fetch_chain(entry, yf, as_of, generated_at)
        if setup is None:
            continue
        row = build_iron_butterfly_row(setup)
        if row is not None:
            rows.append(row)
    return rows


def score_rows(rows, config=None):
    """Winsorized z-score composite among eligible rows, ranked into a percentile.

    Identical machinery to build_advanced_options_screen.py's score_rows, just fixed to this
    screen's single weight set (that file parameterizes on `weights` because it scores two
    different strategy groups from one run; this screen only ever has the one).
    """
    config = config or {}
    fields = list(IRON_BUTTERFLY_WEIGHTS)
    standardized = {field: zscores(winsorize([(row["factors"] or {}).get(field) for row in rows]))
                    for field in fields}
    output = []
    for index, row in enumerate(rows):
        reasons = []
        if (row.get("price") or 0) < config.get("minimum_price", MINIMUM_PRICE):
            reasons.append("MINIMUM_PRICE")
        if (row.get("market_cap") or 0) < config.get("minimum_market_cap", MINIMUM_MARKET_CAP):
            reasons.append("MINIMUM_MARKET_CAP")
        if row.get("realized_volatility_20d") is None:
            reasons.append("INSUFFICIENT_HISTORY")
        contributions = {field: (standardized[field][index] or 0) * IRON_BUTTERFLY_WEIGHTS[field] for field in fields}
        score = sum(contributions.values())
        output.append({**row, "score": round(score, 4),
                       "standardized_factors": {field: standardized[field][index] for field in fields},
                       "contribution_by_factor": {field: round(value, 4) for field, value in contributions.items()},
                       "eligibility": not reasons, "reason_codes": reasons})
    eligible = sorted((row for row in output if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = round(100 * rank / max(1, len(eligible) - 1), 2)
    for row in output:
        row.setdefault("percentile", None)
    return sorted(output, key=lambda row: row["score"], reverse=True)


def to_result(rank, row):
    # Leg ordering matches build_iron_condor_row's to_result: low strike to high strike -
    # long put, short put, short call, long call. Here the two "short" legs (sell put, sell
    # call) share a strike (atm_strike) by construction.
    return {
        "rank": rank, "ticker": row["ticker"], "strategy": row["strategy"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "metrics": row.get("metrics", {}), "reason_codes": row.get("reason_codes", []),
        "legs": [
            {"action": "buy", "option_type": "put", "strike": row["long_put"].get("strike"), "mid": row["long_put"].get("mid"), "bid": row["long_put"].get("bid"), "ask": row["long_put"].get("ask"), "implied_volatility": row["long_put"].get("implied_volatility"), "open_interest": row["long_put"].get("open_interest")},
            {"action": "sell", "option_type": "put", "strike": row["atm_put"].get("strike"), "mid": row["atm_put"].get("mid"), "bid": row["atm_put"].get("bid"), "ask": row["atm_put"].get("ask"), "implied_volatility": row["atm_put"].get("implied_volatility"), "open_interest": row["atm_put"].get("open_interest")},
            {"action": "sell", "option_type": "call", "strike": row["atm_call"].get("strike"), "mid": row["atm_call"].get("mid"), "bid": row["atm_call"].get("bid"), "ask": row["atm_call"].get("ask"), "implied_volatility": row["atm_call"].get("implied_volatility"), "open_interest": row["atm_call"].get("open_interest")},
            {"action": "buy", "option_type": "call", "strike": row["long_call"].get("strike"), "mid": row["long_call"].get("mid"), "bid": row["long_call"].get("bid"), "ask": row["long_call"].get("ask"), "implied_volatility": row["long_call"].get("implied_volatility"), "open_interest": row["long_call"].get("open_interest")},
        ],
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "iron-butterfly-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_IRON_BUTTERFLY_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Iron butterfly screen: opt-in flag not set, skipping "
                 "(set ENABLE_IRON_BUTTERFLY_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Iron butterfly screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/iron-butterflies.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/iron-butterflies.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/iron-butterflies.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "iron-butterfly-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "long_wing_target_delta": LONG_WING_TARGET_DELTA},
        "results": results,
    }
    save_json("screens/iron-butterflies.json", result)
    LOG.info(f"Iron butterfly screen: {len(results)} candidates "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_iron_butterfly(universe, yf, as_of=None):
    """Walk-forward simulated backtest of the iron butterfly strategy against real settlement.

    Adapts build_advanced_options_screen.py's backtest_iron_condor payoff-clamping logic to
    the collapsed-ATM-strike case: the iron condor's piecewise payoff has FOUR pieces bounded
    by four distinct strikes (long_put < short_put < short_call < long_call); the iron
    butterfly's has only THREE, since short_put and short_call collapse into one atm_strike
    (long_put < atm_strike < long_call). Entry prices are Black-Scholes estimates (see
    backtest_common module docstring); every trade settles against the REAL historical
    closing price at expiry_index. iv is computed only from closes[:entry_index + 1] - no
    lookahead into price history past entry.
    """
    period_returns, trade_pnls = [], []
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        closes = yahoo_history(ticker, yf)["closes"]
        for entry_index, expiry_index in walk_periods(closes, TARGET_DAYS_TO_EXPIRATION):
            price, settle_price = closes[entry_index], closes[expiry_index]
            iv = realized_volatility_20d(closes[:entry_index + 1])
            if not iv or not price:
                continue
            calls, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)
            atm_call = select_contract(calls, price)
            atm_put = select_contract(puts, price)
            if atm_call is None or atm_put is None:
                continue
            if atm_call["strike"] != atm_put["strike"]:
                matched_put = _contract_at_strike(puts, atm_call["strike"], price)
                if matched_put is not None:
                    atm_put = matched_put
                else:
                    matched_call = _contract_at_strike(calls, atm_put["strike"], price)
                    if matched_call is None:
                        continue
                    atm_call = matched_call
            if atm_call["strike"] != atm_put["strike"]:
                continue
            atm_strike = atm_call["strike"]
            long_call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call", target_delta=LONG_WING_TARGET_DELTA)
            long_put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put", target_delta=LONG_WING_TARGET_DELTA)
            if long_call is None or long_put is None:
                continue
            if not (long_call["strike"] > atm_strike > long_put["strike"]):
                continue
            net_credit = (atm_call["mid"] - long_call["mid"]) + (atm_put["mid"] - long_put["mid"])
            call_width = long_call["strike"] - atm_strike
            put_width = atm_strike - long_put["strike"]
            max_loss = max(call_width, put_width) - net_credit
            fee = 4 * CONTRACT_FEE
            if net_credit <= 0 or max_loss <= 0:
                continue
            # Three-piece payoff (one fewer breakpoint than the iron condor's four): the
            # short strikes have collapsed to atm_strike, so there is no longer a
            # zero-payout PLATEAU between two different short strikes - profit peaks exactly
            # at atm_strike and decays linearly toward each wing.
            if atm_strike < settle_price <= long_call["strike"]:
                paid_out = settle_price - atm_strike
            elif settle_price > long_call["strike"]:
                paid_out = call_width
            elif long_put["strike"] <= settle_price <= atm_strike:
                paid_out = atm_strike - settle_price
            else:  # settle_price < long_put["strike"]
                paid_out = put_width
            pnl = (net_credit - paid_out) * 100 - fee
            period_returns.append(pnl / (max_loss * 100))
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Publishes a walk-forward simulated backtest (see module docstring and
    backtest_common's for the simulated-entry/real-settlement methodology). Unlike run(),
    this needs no live option-chain data - it only reads yahoo_history's cached price
    history - so it always attempts to run, with no ENABLE_IRON_BUTTERFLY_SCREEN gate.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices. The live "
                   "screen's ranking also factors in news sentiment and the ticker's broader "
                   "research-universe score/confidence; this backtest does not, since no "
                   "point-in-time history of those signals exists yet to backtest against "
                   "without look-ahead risk.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "iron-butterfly-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/iron-butterflies-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "iron-butterfly-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/iron-butterflies-backtest.json", result)
        return result
    stats = backtest_iron_butterfly(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "iron-butterfly-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/iron-butterflies-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "iron-butterfly-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION},
              "backtest": stats}
    save_json("screens/iron-butterflies-backtest.json", result)
    LOG.info(f"Iron-butterfly backtest: {stats['num_trades']} trades")
    return result


if __name__ == "__main__":
    run()
