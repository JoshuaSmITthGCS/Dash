"""Publishes the "buy" (multi-day options), "sell call" (covered call), and "sell put"
(cash-secured put) research screens, plus a combined "Short-term trades" screen, from ONE
shared option-chain fetch per ticker.

build_options_screen.py, build_covered_call_screen.py, and build_cash_secured_put_screen.py
each independently fetch their own option chain per ticker for live data. Since all three
now share the same 1-14-day expiration window (see each module's own top-of-file docstring),
that was three redundant option-chain requests for the same ticker on the same day. This
script fetches ONCE per ticker and derives all three screens' picks from it, replacing what
those three files' own run() functions publish for live/scheduled data - their
build_row/score_rows/to_result logic is mirrored here rather than imported, since a shared
fetch feeding three different selections doesn't fit their own fetch-then-select shape, but
each module's WEIGHTS and to_result() ARE imported and reused directly so the published
schema for options.json/covered-calls.json/cash-secured-puts.json is unchanged - the
frontend needs no changes for those three files. Each module's own run()/run_backtest()
stay in place and are still directly testable/runnable standalone; run() just isn't what the
scheduled workflow calls for live data anymore (see .github/workflows/refresh-advisor.yml).

The Short-term trades screen picks, for each ticker, whichever of the three mechanisms (buy
a call, buy a put, sell a covered call, sell a cash-secured put) ranks highest by percentile
within its own mechanism's cross-sectional population - one idea per ticker, not a
duplicate list. "Multi-day"/"short-term" here means 1 day to 2 weeks (MIN/MAX/TARGET below),
not the wider window this codebase used earlier - see git history if that's confusing.

Options-chain data is opt-in (ENABLE_MULTIDAY_OPTIONS_SCREEN=1), the same flag
build_options_screen.py's own run() used - kept as the single gate since this script is the
combined replacement for that live fetch, not an additional one.
"""

import os
from datetime import datetime, timezone

import build_cash_secured_put_screen as sell_put_screen
import build_covered_call_screen as sell_call_screen
import build_options_screen as buy_screen
from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
import options_pit_store
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expected_value_pct, expiration_spans_earnings,
                            liquidity_factor, next_earnings_date, probability_above, realized_volatility_20d,
                            research_universe_factors, select_by_target_delta, select_contract,
                            select_expiration, suggested_position_pct, transaction_cost_pct, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 1
MAX_DAYS_TO_EXPIRATION = 14
TARGET_DAYS_TO_EXPIRATION = 7
TARGET_DELTA = 0.30
MINIMUM_HISTORY_SESSIONS = 21

WINDOW = {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION, "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
          "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION, "target_delta": TARGET_DELTA}

FILE_MODEL_VERSIONS = {
    "screens/options.json": "multiday-options-v1.0.0",
    "screens/covered-calls.json": "covered-call-v1.0.0",
    "screens/cash-secured-puts.json": "cash-secured-put-v1.0.0",
    "screens/short-term-trades.json": "short-term-trades-v1.0.0",
}


def fetch_chain(entry, yf, as_of=None, generated_at=None):
    """One shared per-ticker fetch: history, trend/realized vol, one expiration, one chain."""
    ticker = entry.get("ticker")
    if not ticker or yf is None:
        return None
    history = yahoo_history(ticker, yf)
    closes = history["closes"]
    if len(closes) < MINIMUM_HISTORY_SESSIONS:
        return None
    price = closes[-1]
    trend = trend_20d(closes)
    realized = realized_volatility_20d(closes)
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
    return {"ticker": ticker, "entry": entry, "price": price, "trend": trend, "realized": realized,
            "expiration": expiration, "dte": dte, "calls": chain.calls, "puts": chain.puts,
            "history_sessions": len(closes), "generated_at": generated_at, "as_of": as_of}


def build_buy_row(setup):
    """Mirrors build_options_screen.build_row's post-fetch logic - keep in sync if that changes."""
    price, trend, realized = setup["price"], setup["trend"], setup["realized"]
    option_type = "put" if (trend or 0) < 0 else "call"
    contract = select_contract(setup["puts"] if option_type == "put" else setup["calls"], price)
    if contract is None:
        return None
    iv_rv_ratio = (contract["implied_volatility"] / realized
                   if contract["implied_volatility"] and realized else None)
    entry = setup["entry"]
    direction = -1 if option_type == "put" else 1
    research_factors = research_universe_factors(entry, setup["generated_at"], setup["as_of"],
                                                  direction=direction, sentiment_mode="signed")
    group_id, group_label = peer_group(entry)
    return {
        "ticker": setup["ticker"], "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": setup["history_sessions"], "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "option_type": option_type, "expiration": setup["expiration"], "days_to_expiration": setup["dte"],
        "implied_realized_vol_ratio": round(iv_rv_ratio, 4) if iv_rv_ratio is not None else None,
        "contract": contract,
        "news_sentiment": research_factors["news_sentiment"], "research_confidence": research_factors["research_confidence"],
        "factors": {
            "iv_value": -iv_rv_ratio if iv_rv_ratio is not None else None,
            "liquidity": liquidity_factor(contract),
            "trend_strength": abs(trend) if trend is not None else None,
            **research_factors,
        },
    }


def build_sell_call_row(setup):
    """Mirrors build_covered_call_screen.build_row's post-fetch logic - keep in sync if that changes."""
    price, realized, trend = setup["price"], setup["realized"], setup["trend"]
    call = select_by_target_delta(setup["calls"], price, setup["dte"], side="call", target_delta=TARGET_DELTA)
    if call is None:
        return None
    premium = call["mid"]
    breakeven = price - premium
    max_return_if_assigned_pct = ((call["strike"] - price) + premium) / price
    annualized_yield = (premium / price) * (365 / setup["dte"])
    probability_assigned = call.get("delta")
    downside_cushion_pct = premium / price
    cost_pct = transaction_cost_pct(call, price)
    expected_value = expected_value_pct(probability_assigned, max_return_if_assigned_pct,
                                        downside_cushion_pct, cost_pct)
    position_pct = suggested_position_pct(probability_assigned, max_return_if_assigned_pct, downside_cushion_pct)
    entry = setup["entry"]
    research_factors = research_universe_factors(entry, setup["generated_at"], setup["as_of"],
                                                  direction=1, sentiment_mode="inverse")
    group_id, group_label = peer_group(entry)
    return {
        "ticker": setup["ticker"], "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": setup["history_sessions"], "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": setup["expiration"], "days_to_expiration": setup["dte"],
        "capital_required": price * 100,
        "call": call,
        "metrics": {
            "premium": round(premium, 4), "breakeven": round(breakeven, 4),
            "annualized_yield": round(annualized_yield, 4),
            "expected_value_pct": round(expected_value, 4) if expected_value is not None else None,
            "max_return_if_assigned_pct": round(max_return_if_assigned_pct, 4),
            "probability_assigned": round(probability_assigned, 4) if probability_assigned is not None else None,
            "downside_cushion_pct": round(downside_cushion_pct, 4),
            "suggested_position_pct": round(position_pct, 4) if position_pct is not None else None,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "expected_value_pct": expected_value,
            "liquidity": liquidity_factor(call),
            "cushion": downside_cushion_pct,
            **research_factors,
        },
    }


def build_sell_put_row(setup):
    """Mirrors build_cash_secured_put_screen.build_row's post-fetch logic - keep in sync if that changes."""
    price, realized, trend = setup["price"], setup["realized"], setup["trend"]
    put = select_by_target_delta(setup["puts"], price, setup["dte"], side="put", target_delta=TARGET_DELTA)
    if put is None:
        return None
    strike = put["strike"]
    premium = put["mid"]
    collateral = strike * 100
    effective_cost_basis = strike - premium
    annualized_yield = (premium / strike) * (365 / setup["dte"])
    probability_otm = probability_above(price, strike, put["implied_volatility"], setup["dte"])
    probability_assigned = None if probability_otm is None else (1 - probability_otm)
    cost_pct = transaction_cost_pct(put, strike)
    favorable_return = premium / strike
    unfavorable_return = (price - effective_cost_basis) / strike
    expected_value = expected_value_pct(probability_otm, favorable_return, unfavorable_return, cost_pct)
    position_pct = suggested_position_pct(probability_otm, favorable_return, unfavorable_return)
    entry = setup["entry"]
    research_factors = research_universe_factors(entry, setup["generated_at"], setup["as_of"],
                                                  direction=1, sentiment_mode="signed")
    group_id, group_label = peer_group(entry)
    return {
        "ticker": setup["ticker"], "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": setup["history_sessions"], "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": setup["expiration"], "days_to_expiration": setup["dte"],
        "capital_required": collateral,
        "put": put,
        "metrics": {
            "premium": round(premium, 4), "collateral": round(collateral, 2),
            "effective_cost_basis": round(effective_cost_basis, 4),
            "annualized_yield": round(annualized_yield, 4),
            "expected_value_pct": round(expected_value, 4) if expected_value is not None else None,
            "probability_otm": round(probability_otm, 4) if probability_otm is not None else None,
            "probability_assigned": round(probability_assigned, 4) if probability_assigned is not None else None,
            "suggested_position_pct": round(position_pct, 4) if position_pct is not None else None,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "expected_value_pct": expected_value,
            "probability_otm": probability_otm,
            "liquidity": liquidity_factor(put),
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    """One shared fetch per ticker, fanned out to all three mechanisms."""
    buy_rows, sell_call_rows, sell_put_rows = [], [], []
    for entry in universe:
        setup = fetch_chain(entry, yf, as_of, generated_at)
        if setup is None:
            continue
        buy_row = build_buy_row(setup)
        if buy_row is not None:
            buy_rows.append(buy_row)
        sell_call_row = build_sell_call_row(setup)
        if sell_call_row is not None:
            sell_call_rows.append(sell_call_row)
        sell_put_row = build_sell_put_row(setup)
        if sell_put_row is not None:
            sell_put_rows.append(sell_put_row)
    return {"buy": buy_rows, "sell_call": sell_call_rows, "sell_put": sell_put_rows}


def score_group(rows, weights, config=None):
    """Same winsorize/zscore/eligibility/percentile pattern every screen in this codebase
    uses, parameterized by weights so one function serves all three mechanism groups.
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


def select_best_per_ticker(scored_buy, scored_sell_call, scored_sell_put):
    """For each ticker, keep whichever ELIGIBLE mechanism has the highest percentile within
    its own mechanism's cross-sectional population - one row per ticker, tagged by strategy.
    Percentile (not raw score) is the comparable unit across mechanisms: each mechanism's
    score is a z-score composite standardized against its OWN population, so raw scores
    aren't directly comparable across mechanisms, but "rank among this mechanism's own
    eligible candidates today" is.
    """
    candidates = {}
    for strategy, rows in (("buy", scored_buy), ("sell_call", scored_sell_call), ("sell_put", scored_sell_put)):
        for row in rows:
            if not row["eligibility"] or row.get("percentile") is None:
                continue
            ticker = row["ticker"]
            best = candidates.get(ticker)
            if best is None or row["percentile"] > best[1]["percentile"]:
                candidates[ticker] = (strategy, row)
    return sorted(candidates.values(), key=lambda item: item[1]["percentile"], reverse=True)


def to_result_short_term(rank, strategy, row):
    """Unified legs+metrics envelope (matches the shape src/pages/StrategyScreen.jsx already
    consumes for the other strategy screens) regardless of which mechanism won this ticker.
    """
    if strategy == "buy":
        contract = row.get("contract") or {}
        leg = {"action": "buy", "option_type": row["option_type"], "strike": contract.get("strike"),
               "bid": contract.get("bid"), "ask": contract.get("ask"), "mid": contract.get("mid"),
               "spread_pct": contract.get("spread_pct"), "implied_volatility": contract.get("implied_volatility"),
               "open_interest": contract.get("open_interest")}
        metrics = {
            "implied_volatility": contract.get("implied_volatility"),
            "realized_volatility_20d": row.get("realized_volatility_20d"),
            "implied_realized_vol_ratio": row.get("implied_realized_vol_ratio"),
            "moneyness": contract.get("moneyness"),
            "news_sentiment": round(row["news_sentiment"], 4) if row.get("news_sentiment") is not None else None,
            "research_confidence": round(row["research_confidence"], 4) if row.get("research_confidence") is not None else None,
        }
        capital_required = round((contract.get("mid") or 0) * 100, 2)
        strategy_tag = f"buy_{row['option_type']}"
    elif strategy == "sell_call":
        call = row.get("call") or {}
        leg = {"action": "sell", "option_type": "call", "strike": call.get("strike"),
               "bid": call.get("bid"), "ask": call.get("ask"), "mid": call.get("mid"),
               "spread_pct": call.get("spread_pct"), "implied_volatility": call.get("implied_volatility"),
               "open_interest": call.get("open_interest"), "delta": call.get("delta")}
        metrics = row.get("metrics", {})
        capital_required = row.get("capital_required")
        strategy_tag = "sell_call"
    else:
        put = row.get("put") or {}
        leg = {"action": "sell", "option_type": "put", "strike": put.get("strike"),
               "bid": put.get("bid"), "ask": put.get("ask"), "mid": put.get("mid"),
               "spread_pct": put.get("spread_pct"), "implied_volatility": put.get("implied_volatility"),
               "open_interest": put.get("open_interest"), "delta": put.get("delta")}
        metrics = row.get("metrics", {})
        capital_required = row.get("capital_required")
        strategy_tag = "sell_put"
    return {
        "rank": rank, "ticker": row["ticker"], "strategy": strategy_tag, "eligibility": True,
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": capital_required,
        "legs": [leg], "metrics": metrics, "reason_codes": row.get("reason_codes", []),
    }


def unavailable(model_version, reason_code, generated_at):
    return {"schema_version": "1.0.0", "model_version": model_version, "config_version": "screens-v1.0.0",
            "generated_at": generated_at, "status": "unavailable", "reason_code": reason_code, "results": []}


def run(as_of=None):
    if os.getenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Options strategies: opt-in flag not set, skipping (set ENABLE_MULTIDAY_OPTIONS_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Options strategies: no published universe to score, skipping")
        for name, model_version in FILE_MODEL_VERSIONS.items():
            save_json(name, unavailable(model_version, "NO_PUBLISHED_UNIVERSE", generated_at))
        return None
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        for name, model_version in FILE_MODEL_VERSIONS.items():
            save_json(name, unavailable(model_version, "YFINANCE_UNAVAILABLE", generated_at))
        return None

    grouped = build_rows(universe, yf, as_of, snapshot_generated_at)
    scored_buy = score_group(grouped["buy"], buy_screen.WEIGHTS)
    scored_sell_call = score_group(grouped["sell_call"], sell_call_screen.WEIGHTS)
    scored_sell_put = score_group(grouped["sell_put"], sell_put_screen.WEIGHTS)

    buy_results = [buy_screen.to_result(rank + 1, row) for rank, row in enumerate(scored_buy)]
    sell_call_results = [sell_call_screen.to_result(rank + 1, row) for rank, row in enumerate(scored_sell_call)]
    sell_put_results = [sell_put_screen.to_result(rank + 1, row) for rank, row in enumerate(scored_sell_put)]

    save_json("screens/options.json", {
        "schema_version": "1.0.0", "model_version": FILE_MODEL_VERSIONS["screens/options.json"],
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION, "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION},
        "results": buy_results,
    })
    save_json("screens/covered-calls.json", {
        "schema_version": "1.0.0", "model_version": FILE_MODEL_VERSIONS["screens/covered-calls.json"],
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": WINDOW, "results": sell_call_results,
    })
    save_json("screens/cash-secured-puts.json", {
        "schema_version": "1.0.0", "model_version": FILE_MODEL_VERSIONS["screens/cash-secured-puts.json"],
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": WINDOW, "results": sell_put_results,
    })

    best = select_best_per_ticker(scored_buy, scored_sell_call, scored_sell_put)
    short_term_results = [to_result_short_term(rank + 1, strategy, row) for rank, (strategy, row) in enumerate(best)]
    short_term_payload = {
        "schema_version": "1.0.0", "model_version": FILE_MODEL_VERSIONS["screens/short-term-trades.json"],
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "success" if short_term_results else "unavailable",
        "window": WINDOW, "results": short_term_results,
    }
    if not short_term_results:
        short_term_payload["reason_code"] = "NO_QUALIFYING_CONTRACTS"
    save_json("screens/short-term-trades.json", short_term_payload)

    # Point-in-time capture of what was actually recommended, for future realized-payoff
    # validation - starts recording today, never reconstructs history. See
    # options_pit_store.py and validation/options_ic.py.
    try:
        options_pit_store.append_snapshot(short_term_results)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"options_pit_store snapshot failed ({type(exc).__name__}): {exc}")

    LOG.info(f"Options strategies (one chain fetch/ticker): buy {len(buy_results)}, "
             f"sell_call {len(sell_call_results)}, sell_put {len(sell_put_results)}, "
             f"short-term-trades {len(short_term_results)}")
    return {"options": buy_results, "covered_calls": sell_call_results,
            "cash_secured_puts": sell_put_results, "short_term_trades": short_term_results}


def backtest_universe(universe, yf, as_of=None):
    """Combined walk-forward backtest for the short-term-trades screen: at each historical
    period, prices ALL THREE mechanisms off ONE synthetic chain and pools every mechanism's
    period return into one aggregate result - approximating "this screen's opportunity set
    over time" rather than faithfully replaying the live screen's per-ticker best-mechanism
    selection, which would need the whole universe's cross-sectional scores at every
    historical date to reproduce exactly. Stated here rather than silently approximated.
    """
    period_returns, trade_pnls = [], []
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        closes = yahoo_history(ticker, yf)["closes"]
        for entry_index, expiry_index in walk_periods(closes, TARGET_DAYS_TO_EXPIRATION):
            price, settle_price = closes[entry_index], closes[expiry_index]
            history_slice = closes[:entry_index + 1]
            iv = realized_volatility_20d(history_slice)
            trend = trend_20d(history_slice)
            if not iv or not price or trend is None:
                continue
            calls, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)

            option_type = "put" if trend < 0 else "call"
            contract = select_contract(puts if option_type == "put" else calls, price)
            if contract is not None:
                cost = contract["mid"] * 100 + CONTRACT_FEE
                if cost > 0:
                    intrinsic = (max(0, settle_price - contract["strike"]) if option_type == "call"
                                else max(0, contract["strike"] - settle_price))
                    pnl = intrinsic * 100 - cost
                    period_returns.append(pnl / cost)
                    trade_pnls.append(pnl)

            call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call",
                                          target_delta=TARGET_DELTA)
            if call is not None:
                fee_per_share = CONTRACT_FEE / 100
                period_return = ((min(settle_price, call["strike"]) - price) / price
                                 + (call["mid"] - fee_per_share) / price)
                period_returns.append(period_return)
                trade_pnls.append(period_return * price * 100)

            put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put",
                                         target_delta=TARGET_DELTA)
            if put is not None:
                strike = put["strike"]
                fee_per_share = CONTRACT_FEE / 100
                period_return = ((put["mid"] - fee_per_share) / strike
                                 + min(0, (settle_price - strike) / strike))
                period_returns.append(period_return)
                trade_pnls.append(period_return * strike * 100)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices. This "
                   "combined backtest pools all three mechanisms' (buy, sell call, sell put) "
                   "period returns together as an approximation of the screen's opportunity set "
                   "over time - it does not replay the live screen's exact per-ticker "
                   "best-mechanism selection at each historical date. The live screen's "
                   "ranking also factors in news sentiment and the ticker's broader "
                   "research-universe score/confidence; this backtest does not, since no "
                   "point-in-time history of those signals exists yet to backtest against "
                   "without look-ahead risk.")
    model_version = "short-term-trades-backtest-v1.0.0"
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": model_version, "config_version": "screens-v1.0.0",
                  "generated_at": generated_at, "status": "unavailable",
                  "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/short-term-trades-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": model_version, "config_version": "screens-v1.0.0",
                  "generated_at": generated_at, "status": "unavailable",
                  "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/short-term-trades-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": model_version, "config_version": "screens-v1.0.0",
                  "generated_at": generated_at, "status": "unavailable",
                  "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/short-term-trades-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": model_version, "config_version": "screens-v1.0.0",
              "generated_at": generated_at, "status": "success", "methodology": methodology,
              "universe_tickers": len(universe), "window": WINDOW, "backtest": stats}
    save_json("screens/short-term-trades-backtest.json", result)
    LOG.info(f"Short-term trades backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
