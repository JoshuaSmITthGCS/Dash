"""Publishes the "Jade lizard" research screen.

A jade lizard combines two pieces sold on the SAME underlying, SAME expiration: an
out-of-the-money short put (identical in shape to the cash-secured put screen's own
put leg) plus a short call credit spread (short a call, buy a further-OTM call, same
convention build_vertical_spread_screen.py uses for its call-spread leg). The position
is only published as a jade lizard when it is structured so the TOTAL net credit
collected across all three legs is at least as large as the call spread's width.

That inequality is what eliminates upside risk entirely, and it's worth spelling out
why. If the stock rallies through both call strikes at expiration, the call spread
itself loses (width - credit-allocated-to-that-spread) - but the put side expires
worthless in that scenario, so every dollar of credit collected (put premium included)
is available to absorb that call-spread loss. When net_credit >= call_spread_width, the
credit alone covers the worst-case call-spread loss, so there is no dollar amount a
rally can cost - the max loss on the upside is <= 0, i.e. never actually a loss. A
candidate that collects a total credit smaller than the call spread's width does NOT
have this property (a big enough rally still costs money) and is therefore not a
genuine jade lizard - see the net_credit < call_spread_width gate in build_row below,
which mirrors build_advanced_options_screen.build_iron_condor_row returning None when
its own structural requirement fails.

With upside eliminated, the only risk that remains is downside - and it is IDENTICAL in
shape to build_cash_secured_put_screen.py's own risk: assignment on the short put below
its strike, uncapped down to zero. This screen deliberately mirrors that screen's
economics (effective_cost_basis, expected_value_pct, suggested_position_pct, "signed"
sentiment mode) almost verbatim, because the downside-risk analysis is the same problem.

Options-chain data is opt-in (ENABLE_JADE_LIZARD_SCREEN=1): each ticker costs one extra
options-chain request on top of what fetch_advisor.py already pulls, the same tradeoff
every other options screen in this pipeline makes. This is a research screen, not a
trade instruction or order-routing feature - nothing in this codebase places option
orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

import iv_archive
from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expected_value_pct, expiration_spans_earnings,
                            iv_skew, liquidity_factor, next_earnings_date, probability_above, put_call_oi_ratio,
                            realized_volatility_20d, realized_vol_percentile, research_universe_factors,
                            select_by_target_delta, select_expiration, single_expiration_gex,
                            suggested_position_pct, transaction_cost_pct, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
PUT_TARGET_DELTA = 0.30
SHORT_CALL_TARGET_DELTA = 0.18
LONG_CALL_TARGET_DELTA = 0.08
MINIMUM_HISTORY_SESSIONS = 21

# news_sentiment uses research_universe_factors' "signed" mode (direction=1): calm/positive
# sentiment is rewarded, since strong NEGATIVE sentiment argues against selling a put into
# a name with active bad news (the falling-knife problem) - the exact same reasoning
# build_cash_secured_put_screen.py's identical comment gives, because the downside risk
# here IS a naked put's downside risk; the no-upside-risk call spread wrapped around it
# doesn't change what the position is exposed to on the way down. research_confidence is a
# quality gate (only sell puts on names worth owning). Existing factors shrunk
# proportionally to still sum to 1.0.
#
# Ranks on expected_value_pct, not raw annualized_yield - see build_cash_secured_put_screen's
# identical rationale. annualized_yield/probability_otm stay published in `metrics` as
# display-only, clearly risk-neutral, figures.
WEIGHTS = {"expected_value_pct": .33, "probability_otm": .25, "liquidity": .25,
          "news_sentiment": .07, "research_confidence": .10}


def build_row(entry, yf, as_of=None, generated_at=None):
    """One candidate jade lizard row per ticker, or None if no genuine jade lizard (net
    credit >= call spread width) can be built from the current chain.
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
        LOG.info(f"{ticker}: excluded, {expiration} spans earnings on {earnings_date}")
        return None

    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None

    put = select_by_target_delta(chain.puts, price, dte, side="put", target_delta=PUT_TARGET_DELTA)
    short_call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=SHORT_CALL_TARGET_DELTA)
    long_call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=LONG_CALL_TARGET_DELTA)
    if put is None or short_call is None or long_call is None:
        return None

    # The short call must sit above spot and the long call further above still - a jade
    # lizard's call side is a bear-call-spread-shaped credit spread, not just any two calls.
    if not (long_call["strike"] > short_call["strike"] > price):
        return None

    call_spread_width = long_call["strike"] - short_call["strike"]
    net_credit = put["mid"] + short_call["mid"] - long_call["mid"]
    if net_credit <= 0:
        return None
    # THE defining jade lizard constraint - see module docstring for the full reasoning.
    # A candidate that clears every other gate but fails this one is a naked put plus a
    # call spread that still carries real upside risk, not a jade lizard, and must not be
    # published as one.
    if net_credit < call_spread_width:
        return None

    skew = iv_skew(chain.calls, chain.puts, price, dte)
    pc_oi_ratio = put_call_oi_ratio(chain.calls, chain.puts)
    # Read-only - see build_options_screen.py's identical comment: only
    # build_options_strategies.py's shared fetch writes to iv_archive.
    gex = single_expiration_gex(chain.calls, chain.puts, price, dte)
    vol_percentile = realized_vol_percentile(closes)

    collateral = put["strike"] * 100  # same convention as a cash-secured put: what a
    # retail account is required to post against the short put. Stated simplification: a
    # real broker may recognize the defined-risk call spread and net some margin relief
    # against it (a jade lizard's max loss is on the put side alone, not put-collateral
    # PLUS call-spread-width), but this pipeline doesn't model broker-specific margin
    # rules, so it publishes the conservative cash-secured-put-equivalent figure, same as
    # every other screen in this pipeline states its own capital_required simplification.
    effective_cost_basis = put["strike"] - net_credit
    annualized_yield = (net_credit / put["strike"]) * (365 / dte)
    # Probability the put finishes OTM (full credit kept). Stated simplification: this
    # assumes the calls also finish OTM/worthless, the common case for a jade lizard
    # structured this far out-of-the-money on the call side - it does not separately model
    # the (much smaller, and by construction loss-free per the net_credit >= width gate
    # above) probability of the calls finishing in the money. Mirrors expected_value_pct's
    # own docstring in stating a simplification plainly rather than leaving it implicit.
    probability_otm = (probability_above(price, put["strike"], put["implied_volatility"], dte)
                       if put["implied_volatility"] is not None else None)
    # Three legs trade, so three legs' worth of execution cost - unlike a single-leg
    # cash-secured put, this sums the modeled cost across all three contracts.
    cost_pct = (transaction_cost_pct(put, put["strike"]) + transaction_cost_pct(short_call, price)
               + transaction_cost_pct(long_call, price))
    # If OTM (favorable, no assignment): keep the full net credit's yield. If assigned:
    # the mark-to-market outcome if the stock simply sits at today's price rather than
    # dropping further from here - the same "flat from here" simplification
    # build_cash_secured_put_screen's EV treatment uses for its own unfavorable-outcome
    # return (adapted here to net_credit/effective_cost_basis).
    favorable_return = net_credit / put["strike"]
    unfavorable_return = (price - effective_cost_basis) / put["strike"]
    expected_value = expected_value_pct(probability_otm, favorable_return, unfavorable_return, cost_pct)
    position_pct = suggested_position_pct(probability_otm, favorable_return, unfavorable_return)
    research_factors = research_universe_factors(entry, generated_at, as_of, direction=1, sentiment_mode="signed")

    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": collateral,
        "put": put, "short_call": short_call, "long_call": long_call,
        "metrics": {
            "net_credit": round(net_credit, 4), "collateral": round(collateral, 2),
            "effective_cost_basis": round(effective_cost_basis, 4),
            "annualized_yield": round(annualized_yield, 4),
            "expected_value_pct": round(expected_value, 4) if expected_value is not None else None,
            "probability_otm": round(probability_otm, 4) if probability_otm is not None else None,
            "call_spread_width": round(call_spread_width, 4),
            "suggested_position_pct": round(position_pct, 4) if position_pct is not None else None,
            "iv_skew": skew, "put_call_oi_ratio": pc_oi_ratio, "realized_volatility_percentile": vol_percentile,
            "iv_percentile": iv_archive.iv_percentile(ticker), "single_expiration_gex": gex,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "expected_value_pct": expected_value,
            "probability_otm": probability_otm,
            "liquidity": min(liquidity_factor(put), liquidity_factor(short_call), liquidity_factor(long_call)),
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    return [row for row in (build_row(entry, yf, as_of, generated_at) for entry in universe) if row is not None]


def score_rows(rows, config=None):
    """Winsorized z-score composite among eligible rows, ranked into a percentile."""
    config = config or {}
    fields = list(WEIGHTS)
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
        contributions = {field: (standardized[field][index] or 0) * WEIGHTS[field] for field in fields}
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
    put, short_call, long_call = row.get("put") or {}, row.get("short_call") or {}, row.get("long_call") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "legs": [
            {"action": "sell", "option_type": "put", "strike": put.get("strike"),
             "bid": put.get("bid"), "ask": put.get("ask"), "mid": put.get("mid"),
             "spread_pct": put.get("spread_pct"), "implied_volatility": put.get("implied_volatility"),
             "open_interest": put.get("open_interest"), "delta": put.get("delta")},
            {"action": "sell", "option_type": "call", "strike": short_call.get("strike"),
             "bid": short_call.get("bid"), "ask": short_call.get("ask"), "mid": short_call.get("mid"),
             "spread_pct": short_call.get("spread_pct"), "implied_volatility": short_call.get("implied_volatility"),
             "open_interest": short_call.get("open_interest"), "delta": short_call.get("delta")},
            {"action": "buy", "option_type": "call", "strike": long_call.get("strike"),
             "bid": long_call.get("bid"), "ask": long_call.get("ask"), "mid": long_call.get("mid"),
             "spread_pct": long_call.get("spread_pct"), "implied_volatility": long_call.get("implied_volatility"),
             "open_interest": long_call.get("open_interest"), "delta": long_call.get("delta")},
        ],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "jade-lizard-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_JADE_LIZARD_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Jade lizard screen: opt-in flag not set, skipping "
                 "(set ENABLE_JADE_LIZARD_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Jade lizard screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/jade-lizards.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/jade-lizards.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/jade-lizards.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "jade-lizard-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "put_target_delta": PUT_TARGET_DELTA,
                   "short_call_target_delta": SHORT_CALL_TARGET_DELTA,
                   "long_call_target_delta": LONG_CALL_TARGET_DELTA},
        "results": results,
    }
    save_json("screens/jade-lizards.json", result)
    LOG.info(f"Jade lizard screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward simulation of continuously rolling a jade lizard across every ticker in
    `universe`, pooling all tickers' trades into one aggregate result. See backtest_common
    for the no-lookahead pricing/settlement mechanics. Only trades whose synthetic legs
    actually clear the net_credit >= call_spread_width constraint are counted - a period
    that can't form a genuine jade lizard from the synthetic chain is skipped, same as
    build_row returning None live.
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
            put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put",
                                         target_delta=PUT_TARGET_DELTA)
            short_call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call",
                                                target_delta=SHORT_CALL_TARGET_DELTA)
            long_call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call",
                                               target_delta=LONG_CALL_TARGET_DELTA)
            if put is None or short_call is None or long_call is None:
                continue
            if not (long_call["strike"] > short_call["strike"] > price):
                continue
            call_spread_width = long_call["strike"] - short_call["strike"]
            net_credit = put["mid"] + short_call["mid"] - long_call["mid"]
            fee = 3 * CONTRACT_FEE
            if net_credit <= 0 or net_credit < call_spread_width:
                continue
            strike = put["strike"]
            # Downside: identical settlement shape to a cash-secured put - the call spread
            # never contributes a loss at settlement here because the constraint above
            # already ruled out any candidate where it could (see module docstring).
            # min(0, ...) is 0 when settle_price >= strike (put finishes OTM, no assignment).
            period_return = ((net_credit - fee / 100) / strike + min(0, (settle_price - strike) / strike))
            period_returns.append(period_return)
            trade_pnls.append(period_return * strike * 100)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION,
                             trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Walk-forward backtest of the jade lizard strategy. Needs no live option-chain data
    (only cached price history), so unlike run() this always attempts to execute - there's
    no ENABLE_JADE_LIZARD_SCREEN gate to check.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices. Only "
                   "periods whose synthetic legs actually clear the net_credit >= "
                   "call_spread_width constraint are counted as trades - see module docstring "
                   "for why that constraint is what makes a jade lizard's upside loss-free. "
                   "The live screen's ranking also factors in news sentiment and the ticker's "
                   "broader research-universe score/confidence; this backtest does not, since "
                   "no point-in-time history of those signals exists yet to backtest against "
                   "without look-ahead risk.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "jade-lizard-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/jade-lizards-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "jade-lizard-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/jade-lizards-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "jade-lizard-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/jade-lizards-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "jade-lizard-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                         "put_target_delta": PUT_TARGET_DELTA,
                         "short_call_target_delta": SHORT_CALL_TARGET_DELTA,
                         "long_call_target_delta": LONG_CALL_TARGET_DELTA},
              "backtest": stats}
    save_json("screens/jade-lizards-backtest.json", result)
    LOG.info(f"Jade lizard backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
