"""Publishes the "Advanced strategies" options research screen.

For every ticker in the already-published advisor universe, pulls a single option chain
(one expiration inside a 15-45 day window) and derives candidates for TWO distinct
strategies from that one fetch: an iron condor (sell a call spread + sell a put spread,
a range-bound income idea) and a straddle (buy a call and a put at the same near-the-money
strike, a cheap-volatility big-move bet). Each strategy is scored and ranked independently
within its own group - a condor candidate never competes against a straddle candidate for
rank - and the published results carry a "strategy" tag so a shared frontend component can
split them back out.

Both strategies share the same 15-45 day-to-expiration window for simplicity. That is a
real simplification for the straddle side: traders who actually run straddles typically time
them around a known catalyst (earnings, an FDA decision, etc.) so the position's expected
move lines up with a specific event. This pipeline has no earnings-calendar or other
catalyst-date source wired into this script, so the straddle candidates published here are
best read as "cheap relative-volatility ideas" (an implied/realized volatility ratio below
1, i.e. options pricing in less movement than the stock has recently delivered) rather than
catalyst-timed trades. Stating that plainly here rather than dressing the output up as
earnings-play picks.

Options-chain data is opt-in (ENABLE_ADVANCED_OPTIONS_SCREEN=1), the same tradeoff every
other options screen in this pipeline makes: one extra options-chain request per ticker on
top of what fetch_advisor.py already pulls. This is a research screen, not a trade
instruction or order-routing feature - nothing in this codebase places option orders or
talks to a brokerage.
"""

import os
import statistics
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, contract_liquidity, expiration_spans_earnings,
                            liquidity_factor, next_earnings_date, probability_below, realized_volatility_20d,
                            research_universe_factors, select_by_target_delta, select_contract,
                            select_expiration, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
SHORT_WING_TARGET_DELTA = 0.18
LONG_WING_TARGET_DELTA = 0.08
MINIMUM_HISTORY_SESSIONS = 21

# Iron condor wants calm, not a direction - "calm" mode (-|average|*coverage) penalizes
# controversy in either direction, since the strategy's failure mode is an unexpected big
# move either way. Straddle wants the opposite of calm - "attention" mode rewards news
# volume (a live-catalyst proxy) regardless of polarity, since the strategy doesn't care
# which way price moves. research_confidence is an unsigned quality gate for both (neither
# strategy picks a directional side). Existing factors shrunk proportionally.
IRON_CONDOR_WEIGHTS = {"credit_efficiency": .34, "probability_in_range": .30, "liquidity": .21,
                       "news_sentiment": .08, "research_confidence": .07}
# straddle's iv_value trimmed further (was .30): same single-name-VRP-is-weaker-than-index
# reasoning as build_options_screen.py's and build_protective_put_screen.py's identical
# trims (Driessen, Maenhout & Vilkov 2009). liquidity picked up the difference.
STRADDLE_WEIGHTS = {"iv_value": .25, "probability_of_profit": .31, "liquidity": .31,
                    "news_sentiment": .08, "research_confidence": .05}


def fetch_chain(entry, yf, as_of=None, generated_at=None):
    """Shared per-ticker setup: history, expiration selection, and one option chain fetch.

    Returns (ticker, price, dte, expiration, trend, realized, chain, entry, history_sessions,
    generated_at), or None if the ticker doesn't clear a qualifying history/expiration/chain.
    The extra trailing history_sessions/generated_at elements (beyond the base
    ticker/price/.../entry tuple both strategy builders unpack) are what let each strategy's
    row carry the session count and the advisor.json snapshot timestamp (for the
    news_sentiment/research_confidence staleness discount) without re-fetching either a
    second time per strategy.
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
        # Applies to both strategies this screen builds - the straddle side is explicitly
        # documented as a "cheap-volatility idea, not a catalyst-timed one" (see module
        # docstring), so an earnings-inflated straddle candidate would misrepresent itself
        # exactly as much as an earnings-inflated iron condor would.
        LOG.info(f"{ticker}: excluded, {expiration} spans earnings on {earnings_date}")
        return None

    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None
    return (ticker, price, dte, expiration, trend, realized, chain, entry, len(closes), generated_at, as_of)


def build_iron_condor_row(setup):
    """Sell a call spread + sell a put spread around price, or None if legs don't qualify."""
    ticker, price, dte, expiration, trend, realized, chain, entry, history_sessions, generated_at, as_of = setup

    short_call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=SHORT_WING_TARGET_DELTA)
    long_call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=LONG_WING_TARGET_DELTA)
    short_put = select_by_target_delta(chain.puts, price, dte, side="put", target_delta=SHORT_WING_TARGET_DELTA)
    long_put = select_by_target_delta(chain.puts, price, dte, side="put", target_delta=LONG_WING_TARGET_DELTA)
    if any(leg is None for leg in (short_call, long_call, short_put, long_put)):
        return None

    if not (long_call["strike"] > short_call["strike"] > price > short_put["strike"] > long_put["strike"]):
        return None

    net_credit = (short_call["mid"] - long_call["mid"]) + (short_put["mid"] - long_put["mid"])
    call_wing_width = long_call["strike"] - short_call["strike"]
    put_wing_width = short_put["strike"] - long_put["strike"]
    max_loss = max(call_wing_width, put_wing_width) - net_credit
    if net_credit <= 0 or max_loss <= 0:
        return None
    max_profit = net_credit

    prob_below_short_call = probability_below(price, short_call["strike"], short_call["implied_volatility"], dte)
    prob_below_short_put = probability_below(price, short_put["strike"], short_put["implied_volatility"], dte)
    probability_in_range = (None if prob_below_short_call is None or prob_below_short_put is None
                            else prob_below_short_call - prob_below_short_put)
    credit_efficiency = net_credit / max_loss
    research_factors = research_universe_factors(entry, generated_at, as_of, sentiment_mode="calm")

    group_id, group_label = peer_group(entry)
    return {
        "strategy": "iron_condor", "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": history_sessions, "structural_score": entry.get("score"), "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": max_loss * 100,
        "short_call": short_call, "long_call": long_call, "short_put": short_put, "long_put": long_put,
        "metrics": {
            "net_credit": round(net_credit, 4), "max_profit": round(max_profit, 4),
            "max_loss": round(max_loss, 4),
            "probability_in_range": round(probability_in_range, 4) if probability_in_range is not None else None,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "credit_efficiency": credit_efficiency,
            "probability_in_range": probability_in_range,
            "liquidity": min(liquidity_factor(short_call), liquidity_factor(long_call),
                            liquidity_factor(short_put), liquidity_factor(long_put)),
            **research_factors,
        },
    }


def _contract_at_strike(frame, strike, price):
    """First liquid contract in `frame` whose strike matches exactly, or None."""
    for _, contract in frame.iterrows():
        if contract.get("strike") == strike:
            return contract_liquidity(contract, price)
    return None


def build_straddle_row(setup):
    """Buy a call + put at the same near-the-money strike, or None if legs don't qualify."""
    ticker, price, dte, expiration, trend, realized, chain, entry, history_sessions, generated_at, as_of = setup

    call = select_contract(chain.calls, price)
    put = select_contract(chain.puts, price)
    if call is None or put is None:
        return None

    if call["strike"] != put["strike"]:
        call_distance = abs(call["strike"] - price)
        put_distance = abs(put["strike"] - price)
        if call_distance <= put_distance:
            put = _contract_at_strike(chain.puts, call["strike"], price)
        else:
            call = _contract_at_strike(chain.calls, put["strike"], price)
        if call is None or put is None or call["strike"] != put["strike"]:
            return None

    cost = call["mid"] + put["mid"]
    if cost <= 0:
        return None
    strike = call["strike"]
    breakeven_up = strike + cost
    breakeven_down = strike - cost
    required_move_pct = cost / price

    iv_values = [v for v in (call["implied_volatility"], put["implied_volatility"]) if v is not None]
    iv_avg = statistics.mean(iv_values) if iv_values else None
    iv_rv_ratio = iv_avg / realized if iv_avg and realized else None

    prob_below_up = probability_below(price, breakeven_up, iv_avg, dte) if iv_avg else None
    prob_below_down = probability_below(price, breakeven_down, iv_avg, dte) if iv_avg else None
    probability_of_profit = (None if prob_below_up is None or prob_below_down is None
                             else 1 - (prob_below_up - prob_below_down))
    research_factors = research_universe_factors(entry, generated_at, as_of, sentiment_mode="attention")

    group_id, group_label = peer_group(entry)
    return {
        "strategy": "straddle", "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": history_sessions, "structural_score": entry.get("score"), "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": cost * 100,
        "call": call, "put": put,
        "implied_realized_vol_ratio": round(iv_rv_ratio, 4) if iv_rv_ratio is not None else None,
        "metrics": {
            "cost": round(cost, 4), "breakeven_up": round(breakeven_up, 4), "breakeven_down": round(breakeven_down, 4),
            "required_move_pct": round(required_move_pct, 4),
            "probability_of_profit": round(probability_of_profit, 4) if probability_of_profit is not None else None,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "iv_value": -iv_rv_ratio if iv_rv_ratio is not None else None,
            "probability_of_profit": probability_of_profit,
            "liquidity": min(liquidity_factor(call), liquidity_factor(put)),
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    """Returns (condor_rows, straddle_rows); a ticker can land in either, both, or neither."""
    condor_rows, straddle_rows = [], []
    for entry in universe:
        setup = fetch_chain(entry, yf, as_of, generated_at)
        if setup is None:
            continue
        condor_row = build_iron_condor_row(setup)
        if condor_row is not None:
            condor_rows.append(condor_row)
        straddle_row = build_straddle_row(setup)
        if straddle_row is not None:
            straddle_rows.append(straddle_row)
    return condor_rows, straddle_rows


def score_rows(rows, weights, config=None):
    """Winsorized z-score composite among eligible rows, ranked into a percentile.

    Parameterized by `weights` (rather than a module-level constant like
    build_options_screen.score_rows) since the iron-condor and straddle groups score on
    different factor sets but otherwise share this exact scoring machinery.
    """
    config = config or {}
    fields = list(weights)
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
        contributions = {field: (standardized[field][index] or 0) * weights[field] for field in fields}
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
    base = {
        "rank": rank, "ticker": row["ticker"], "strategy": row["strategy"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "metrics": row.get("metrics", {}), "reason_codes": row.get("reason_codes", []),
    }
    if row["strategy"] == "iron_condor":
        base["legs"] = [
            {"action": "buy", "option_type": "put", "strike": row["long_put"].get("strike"), "mid": row["long_put"].get("mid"), "bid": row["long_put"].get("bid"), "ask": row["long_put"].get("ask"), "implied_volatility": row["long_put"].get("implied_volatility"), "open_interest": row["long_put"].get("open_interest")},
            {"action": "sell", "option_type": "put", "strike": row["short_put"].get("strike"), "mid": row["short_put"].get("mid"), "bid": row["short_put"].get("bid"), "ask": row["short_put"].get("ask"), "implied_volatility": row["short_put"].get("implied_volatility"), "open_interest": row["short_put"].get("open_interest")},
            {"action": "sell", "option_type": "call", "strike": row["short_call"].get("strike"), "mid": row["short_call"].get("mid"), "bid": row["short_call"].get("bid"), "ask": row["short_call"].get("ask"), "implied_volatility": row["short_call"].get("implied_volatility"), "open_interest": row["short_call"].get("open_interest")},
            {"action": "buy", "option_type": "call", "strike": row["long_call"].get("strike"), "mid": row["long_call"].get("mid"), "bid": row["long_call"].get("bid"), "ask": row["long_call"].get("ask"), "implied_volatility": row["long_call"].get("implied_volatility"), "open_interest": row["long_call"].get("open_interest")},
        ]
    else:
        base["implied_realized_vol_ratio"] = row.get("implied_realized_vol_ratio")
        base["legs"] = [
            {"action": "buy", "option_type": "call", "strike": row["call"].get("strike"), "mid": row["call"].get("mid"), "bid": row["call"].get("bid"), "ask": row["call"].get("ask"), "implied_volatility": row["call"].get("implied_volatility"), "open_interest": row["call"].get("open_interest")},
            {"action": "buy", "option_type": "put", "strike": row["put"].get("strike"), "mid": row["put"].get("mid"), "bid": row["put"].get("bid"), "ask": row["put"].get("ask"), "implied_volatility": row["put"].get("implied_volatility"), "open_interest": row["put"].get("open_interest")},
        ]
    return base


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "advanced-options-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_ADVANCED_OPTIONS_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Advanced strategies screen: opt-in flag not set, skipping "
                 "(set ENABLE_ADVANCED_OPTIONS_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Advanced strategies screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/advanced-strategies.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/advanced-strategies.json", result)
        return result

    condor_rows, straddle_rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not condor_rows and not straddle_rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/advanced-strategies.json", result)
        return result

    scored_condors = score_rows(condor_rows, IRON_CONDOR_WEIGHTS)
    scored_straddles = score_rows(straddle_rows, STRADDLE_WEIGHTS)
    results = ([to_result(rank + 1, row) for rank, row in enumerate(scored_condors)]
              + [to_result(rank + 1, row) for rank, row in enumerate(scored_straddles)])
    result = {
        "schema_version": "1.0.0", "model_version": "advanced-options-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "short_wing_target_delta": SHORT_WING_TARGET_DELTA,
                   "long_wing_target_delta": LONG_WING_TARGET_DELTA},
        "results": results,
    }
    save_json("screens/advanced-strategies.json", result)
    LOG.info(f"Advanced strategies screen: {len(scored_condors)} iron condor candidates "
             f"({sum(1 for row in scored_condors if row['eligibility'])} eligible), "
             f"{len(scored_straddles)} straddle candidates "
             f"({sum(1 for row in scored_straddles if row['eligibility'])} eligible)")
    return result


def backtest_iron_condor(universe, yf, as_of=None):
    """Walk-forward simulated backtest of the iron condor strategy against real settlement.

    Entry prices are Black-Scholes estimates (see backtest_common module docstring); every
    trade settles against the REAL historical closing price at expiry_index. iv is computed
    only from closes[:entry_index + 1] - no lookahead into price history past entry.
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
            short_call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call", target_delta=SHORT_WING_TARGET_DELTA)
            long_call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call", target_delta=LONG_WING_TARGET_DELTA)
            short_put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put", target_delta=SHORT_WING_TARGET_DELTA)
            long_put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put", target_delta=LONG_WING_TARGET_DELTA)
            if None in (short_call, long_call, short_put, long_put):
                continue
            if not (long_call["strike"] > short_call["strike"] > price > short_put["strike"] > long_put["strike"]):
                continue
            net_credit = (short_call["mid"] - long_call["mid"]) + (short_put["mid"] - long_put["mid"])
            call_width = long_call["strike"] - short_call["strike"]
            put_width = short_put["strike"] - long_put["strike"]
            max_loss = max(call_width, put_width) - net_credit
            fee = 4 * CONTRACT_FEE
            if net_credit <= 0 or max_loss <= 0:
                continue
            if short_put["strike"] <= settle_price <= short_call["strike"]:
                paid_out = 0
            elif short_call["strike"] < settle_price <= long_call["strike"]:
                paid_out = settle_price - short_call["strike"]
            elif settle_price > long_call["strike"]:
                paid_out = call_width
            elif long_put["strike"] <= settle_price < short_put["strike"]:
                paid_out = short_put["strike"] - settle_price
            else:  # settle_price < long_put["strike"]
                paid_out = put_width
            pnl = (net_credit - paid_out) * 100 - fee
            period_returns.append(pnl / (max_loss * 100))
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def backtest_straddle(universe, yf, as_of=None):
    """Walk-forward simulated backtest of the straddle strategy against real settlement.

    Mirrors build_straddle_row's strike-matching fallback via _contract_at_strike. Entry
    prices are Black-Scholes estimates; trades settle against the REAL historical closing
    price at expiry_index. iv is computed only from closes[:entry_index + 1].
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
            call = select_contract(calls, price)
            put = select_contract(puts, price)
            if call is None or put is None:
                continue
            if call["strike"] != put["strike"]:
                matched_put = _contract_at_strike(puts, call["strike"], price)
                if matched_put is not None:
                    put = matched_put
                else:
                    matched_call = _contract_at_strike(calls, put["strike"], price)
                    if matched_call is None:
                        continue
                    call = matched_call
            if call["strike"] != put["strike"]:
                continue
            strike = call["strike"]
            cost = (call["mid"] + put["mid"]) * 100 + 2 * CONTRACT_FEE
            if cost <= 0:
                continue
            payoff = abs(settle_price - strike) * 100
            pnl = payoff - cost
            period_returns.append(pnl / cost)
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Publishes a walk-forward simulated backtest for BOTH strategies (see module docstring
    and backtest_common's for the simulated-entry/real-settlement methodology). Unlike run(),
    this needs no live option-chain data - it only reads yahoo_history's cached price
    history - so it always attempts to run, with no ENABLE_ADVANCED_OPTIONS_SCREEN gate.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices. The "
                   "straddle backtest has no earnings-calendar awareness, same as the live screen. "
                   "The live screen's ranking also factors in news sentiment and the ticker's "
                   "broader research-universe score/confidence; this backtest does not, since no "
                   "point-in-time history of those signals exists yet to backtest against "
                   "without look-ahead risk.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "advanced-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/advanced-strategies-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "advanced-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/advanced-strategies-backtest.json", result)
        return result
    condor_stats = backtest_iron_condor(universe, yf, as_of)
    straddle_stats = backtest_straddle(universe, yf, as_of)
    if condor_stats is None and straddle_stats is None:
        result = {"schema_version": "1.0.0", "model_version": "advanced-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/advanced-strategies-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "advanced-options-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION},
              "backtest": {"iron_condor": condor_stats, "straddle": straddle_stats}}
    save_json("screens/advanced-strategies-backtest.json", result)
    LOG.info(f"Advanced-strategies backtest: condor {condor_stats['num_trades'] if condor_stats else 0} trades, "
             f"straddle {straddle_stats['num_trades'] if straddle_stats else 0} trades")
    return result


if __name__ == "__main__":
    run()
