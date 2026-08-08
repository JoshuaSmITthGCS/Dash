"""Publishes the "Vertical spread" research screen.

For every ticker in the already-published advisor universe, builds a defined-risk
directional spread on the same 20-day trend bias the multi-day options screen uses: a
bull call spread (buy a higher-delta call, sell a lower-delta call, same expiration) on
an uptrending name, or a bear put spread (buy a higher-delta put, sell a lower-delta put)
on a downtrending one. Ranks candidates by risk/reward ratio, contract liquidity, and
trend strength.

Options-chain data is opt-in (ENABLE_VERTICAL_SPREAD_SCREEN=1): each ticker costs two
extra options-chain lookups (one per leg) on top of what fetch_advisor.py already pulls,
the same tradeoff build_options_screen.py's own flag makes. This is a research screen,
not a trade instruction or order-routing feature - nothing in this codebase places option
orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, liquidity_factor, realized_volatility_20d,
                            select_by_target_delta, select_expiration, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
LONG_LEG_TARGET_DELTA = 0.45
SHORT_LEG_TARGET_DELTA = 0.20
MINIMUM_HISTORY_SESSIONS = 21

WEIGHTS = {"risk_reward": .40, "liquidity": .30, "trend_strength": .30}


def build_row(entry, yf, as_of=None):
    """One candidate spread row per ticker, or None if no coherent spread qualifies."""
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

    side = "put" if (trend or 0) < 0 else "call"
    strategy_type = "bear_put_spread" if side == "put" else "bull_call_spread"
    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None
    frame = chain.puts if side == "put" else chain.calls

    long_leg = select_by_target_delta(frame, price, dte, side=side, target_delta=LONG_LEG_TARGET_DELTA)
    if long_leg is None:
        return None
    short_leg = select_by_target_delta(frame, price, dte, side=side, target_delta=SHORT_LEG_TARGET_DELTA)
    if short_leg is None:
        return None

    if side == "call":
        if short_leg["strike"] <= long_leg["strike"]:
            return None
    else:
        if short_leg["strike"] >= long_leg["strike"]:
            return None

    net_debit = long_leg["mid"] - short_leg["mid"]
    width = abs(short_leg["strike"] - long_leg["strike"])
    if net_debit <= 0 or width <= net_debit:
        return None
    max_loss = net_debit
    max_profit = width - net_debit
    risk_reward = max_profit / max_loss

    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "confidence": entry.get("confidence"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": max_loss * 100,
        "strategy_type": strategy_type,
        "long_leg": long_leg, "short_leg": short_leg,
        "metrics": {
            "net_debit": round(net_debit, 4), "width": round(width, 4),
            "max_profit": round(max_profit, 4), "max_loss": round(max_loss, 4),
            "risk_reward": round(risk_reward, 4),
        },
        "factors": {
            "risk_reward": risk_reward,
            "liquidity": min(liquidity_factor(long_leg), liquidity_factor(short_leg)),
            "trend_strength": abs(trend) if trend is not None else None,
        },
    }


def build_rows(universe, yf, as_of=None):
    return [row for row in (build_row(entry, yf, as_of) for entry in universe) if row is not None]


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
    long_leg, short_leg = row.get("long_leg") or {}, row.get("short_leg") or {}
    option_type = "put" if row.get("strategy_type") == "bear_put_spread" else "call"
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "confidence": row.get("confidence"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"), "strategy_type": row.get("strategy_type"),
        "legs": [
            {"action": "buy", "option_type": option_type, "strike": long_leg.get("strike"),
             "bid": long_leg.get("bid"), "ask": long_leg.get("ask"), "mid": long_leg.get("mid"),
             "spread_pct": long_leg.get("spread_pct"), "implied_volatility": long_leg.get("implied_volatility"),
             "open_interest": long_leg.get("open_interest"), "delta": long_leg.get("delta")},
            {"action": "sell", "option_type": option_type, "strike": short_leg.get("strike"),
             "bid": short_leg.get("bid"), "ask": short_leg.get("ask"), "mid": short_leg.get("mid"),
             "spread_pct": short_leg.get("spread_pct"), "implied_volatility": short_leg.get("implied_volatility"),
             "open_interest": short_leg.get("open_interest"), "delta": short_leg.get("delta")},
        ],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "vertical-spread-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_VERTICAL_SPREAD_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Vertical spread screen: opt-in flag not set, skipping "
                 "(set ENABLE_VERTICAL_SPREAD_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Vertical spread screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/vertical-spreads.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/vertical-spreads.json", result)
        return result

    rows = build_rows(universe, yf, as_of)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/vertical-spreads.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "vertical-spread-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "long_leg_target_delta": LONG_LEG_TARGET_DELTA,
                   "short_leg_target_delta": SHORT_LEG_TARGET_DELTA},
        "results": results,
    }
    save_json("screens/vertical-spreads.json", result)
    LOG.info(f"Vertical spread screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward simulation: opens a fresh bull-call or bear-put debit spread every
    period (direction from the trailing trend, same as build_row's own logic), settles
    it against the real historical closing price at expiry, and pools every ticker's
    trades into one aggregate performance_stats result.
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
            side = "put" if trend < 0 else "call"
            calls, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)
            frame = puts if side == "put" else calls
            long_leg = select_by_target_delta(frame, price, TARGET_DAYS_TO_EXPIRATION, side=side,
                                              target_delta=LONG_LEG_TARGET_DELTA)
            short_leg = select_by_target_delta(frame, price, TARGET_DAYS_TO_EXPIRATION, side=side,
                                               target_delta=SHORT_LEG_TARGET_DELTA)
            if long_leg is None or short_leg is None:
                continue
            if side == "call" and short_leg["strike"] <= long_leg["strike"]:
                continue
            if side == "put" and short_leg["strike"] >= long_leg["strike"]:
                continue
            net_debit = long_leg["mid"] - short_leg["mid"]
            width = abs(short_leg["strike"] - long_leg["strike"])
            fee = 2 * CONTRACT_FEE
            cost = net_debit * 100 + fee
            if net_debit <= 0 or width <= net_debit or cost <= 0:
                continue
            if side == "call":
                payoff_per_share = min(max(settle_price, long_leg["strike"]), short_leg["strike"]) - long_leg["strike"]
            else:
                payoff_per_share = long_leg["strike"] - max(min(settle_price, long_leg["strike"]), short_leg["strike"])
            pnl = payoff_per_share * 100 - cost
            period_returns.append(pnl / cost)
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Walk-forward backtest of the same bull-call/bear-put spread logic run() screens
    live, but priced with simulated (Black-Scholes) entries and settled against real
    historical closes - see the module docstring and backtest_common's for the full
    simulated-vs-real breakdown. Unlike run(), this needs no live option-chain data, so
    it has no opt-in flag and always attempts to run when called.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices.")
    if not universe:
        LOG.warn("Vertical spread backtest: no published universe to backtest, skipping")
        result = {"schema_version": "1.0.0", "model_version": "vertical-spread-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/vertical-spreads-backtest.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "vertical-spread-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/vertical-spreads-backtest.json", result)
        return result

    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "vertical-spread-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/vertical-spreads-backtest.json", result)
        return result

    result = {
        "schema_version": "1.0.0", "model_version": "vertical-spread-backtest-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "methodology": methodology, "universe_tickers": len(universe),
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "long_leg_target_delta": LONG_LEG_TARGET_DELTA,
                   "short_leg_target_delta": SHORT_LEG_TARGET_DELTA},
        "backtest": stats,
    }
    save_json("screens/vertical-spreads-backtest.json", result)
    LOG.info(f"Vertical-spread backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
