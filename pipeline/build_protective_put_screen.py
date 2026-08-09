"""Publishes the "Protective put" (portfolio hedge) research screen.

For every ticker in the already-published advisor universe, finds a put roughly 5-10%
below spot to use as portfolio insurance against an existing (or hypothetical) long
position, and ranks tickers by which hedge is cheapest relative to how much real
volatility the stock actually has - cheap insurance on a genuinely risky name is worth
more than the same-priced insurance on a quiet one.

Options-chain data is opt-in (ENABLE_PROTECTIVE_PUT_SCREEN=1): each ticker costs an extra
options-chain request on top of what fetch_advisor.py already pulls, the same tradeoff
fetch_advisor.py's own ENABLE_OPTIONS_VOLATILITY flag makes. This is a research screen,
not a trade instruction or order-routing feature - nothing in this codebase places option
orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expiration_spans_earnings, liquidity_factor,
                            next_earnings_date, realized_volatility_20d, research_universe_factors,
                            select_by_target_moneyness, select_expiration, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 60
TARGET_DAYS_TO_EXPIRATION = 30
TARGET_MONEYNESS = -0.075
MONEYNESS_TOLERANCE = 0.03
MINIMUM_HISTORY_SESSIONS = 21

# news_sentiment uses "inverse" mode: a bearish tilt modestly raises the case for owning
# insurance, kept smallest of any screen since it's the factor most likely to overlap with
# iv_value (both reflect market-implied risk). research_confidence is a quality gate -
# "worth protecting". Existing factors shrunk proportionally to still sum to 1.0.
#
# iv_value trimmed further (was .35): the single-name IV-vs-RV signal it's built on is
# weaker and noisier than the same signal at the index level (Driessen, Maenhout & Vilkov
# 2009 - individual variance risk was not reliably priced in their sample). liquidity
# picked up the difference.
WEIGHTS = {"iv_value": .28, "cost_efficiency": .26, "liquidity": .33,
          "news_sentiment": .05, "research_confidence": .08}


def build_row(entry, yf, as_of=None, generated_at=None):
    """One candidate hedge row per ticker, or None if it doesn't clear a qualifying put."""
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
    put = select_by_target_moneyness(chain.puts, price, TARGET_MONEYNESS, MONEYNESS_TOLERANCE)
    if put is None:
        return None

    cost = put["mid"]
    cost_pct = cost / price
    max_loss_with_hedge_pct = ((price - put["strike"]) + cost) / price
    iv_rv_ratio = (put["implied_volatility"] / realized
                   if put["implied_volatility"] and realized else None)
    research_factors = research_universe_factors(entry, generated_at, as_of, direction=1, sentiment_mode="inverse")
    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": price * 100 + cost * 100,
        "put": put,
        "implied_realized_vol_ratio": round(iv_rv_ratio, 4) if iv_rv_ratio is not None else None,
        "metrics": {
            "cost": round(cost, 4), "cost_pct": round(cost_pct, 4),
            "floor_price": put["strike"],
            "max_loss_with_hedge_pct": round(max_loss_with_hedge_pct, 4),
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "iv_value": -iv_rv_ratio if iv_rv_ratio is not None else None,
            "cost_efficiency": -cost_pct,
            "liquidity": liquidity_factor(put),
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    return [row for row in (build_row(entry, yf, as_of, generated_at) for entry in universe) if row is not None]


def score_rows(rows, config=None):
    """Winsorized z-score composite among eligible rows, ranked into a percentile.

    The score is "cheapest/best-value hedge" - lower cost relative to risk is better,
    which is why the factors above are negated - but the resulting composite is still
    ranked descending same as the other screens (higher composite = better candidate).
    """
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
    put = row.get("put") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "implied_realized_vol_ratio": row.get("implied_realized_vol_ratio"),
        "legs": [{"action": "buy", "option_type": "put", "strike": put.get("strike"),
                  "bid": put.get("bid"), "ask": put.get("ask"), "mid": put.get("mid"),
                  "spread_pct": put.get("spread_pct"), "implied_volatility": put.get("implied_volatility"),
                  "open_interest": put.get("open_interest")}],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "protective-put-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_PROTECTIVE_PUT_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Protective put screen: opt-in flag not set, skipping "
                 "(set ENABLE_PROTECTIVE_PUT_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Protective put screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/protective-puts.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/protective-puts.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/protective-puts.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "protective-put-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "target_moneyness": TARGET_MONEYNESS},
        "results": results,
    }
    save_json("screens/protective-puts.json", result)
    LOG.info(f"Protective put screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward simulate continuously holding shares and buying a fresh protective put
    every period, pooling ALL tickers' trades into two aggregate results: the hedged
    strategy (primary "backtest") and the same price paths held unhedged (the "baseline"),
    so the published result can show the hedge's real cost/benefit - "compute cost of
    hedge vs. potential decline" per this feature's design.

    No lookahead: at each period's entry index, realized_volatility_20d only sees price
    history up to and including the entry date. The only forward-looking input is the
    real historical closing price at the expiry index, used to settle the trade.
    """
    hedged_returns, unhedged_returns, trade_pnls = [], [], []
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
            _, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)
            put = select_by_target_moneyness(puts, price, TARGET_MONEYNESS, MONEYNESS_TOLERANCE)
            if put is None:
                continue
            cost_per_share = put["mid"]
            fee_per_share = CONTRACT_FEE / 100
            # max(settle_price, strike) floors the value at the strike (the whole point of
            # the hedge) while passing settle_price through unchanged when it's above the floor.
            hedged_return = (max(settle_price, put["strike"]) - price) / price - (cost_per_share + fee_per_share) / price
            unhedged_return = (settle_price - price) / price
            hedged_returns.append(hedged_return)
            unhedged_returns.append(unhedged_return)
            trade_pnls.append(hedged_return * price * 100)
    periods_per_year = 365 / TARGET_DAYS_TO_EXPIRATION
    hedged_stats = performance_stats(hedged_returns, periods_per_year, trade_pnls=trade_pnls)
    unhedged_stats = performance_stats(unhedged_returns, periods_per_year)
    return hedged_stats, unhedged_stats


def run_backtest(as_of=None):
    """Mirrors run()'s universe-loading/yfinance-import shape, but with no opt-in flag
    check - the backtest needs no live option-chain data (it only re-reads already-cached
    price history), so it should always attempt to run when called.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices. The "
                   "'baseline' block is the same tickers held unhedged over the same periods, "
                   "for comparison. The live screen's ranking also factors in news sentiment "
                   "and the ticker's broader research-universe score/confidence; this backtest "
                   "does not, since no point-in-time history of those signals exists yet to "
                   "backtest against without look-ahead risk.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "protective-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/protective-puts-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "protective-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/protective-puts-backtest.json", result)
        return result
    hedged_stats, unhedged_stats = backtest_universe(universe, yf, as_of)
    if hedged_stats is None:
        result = {"schema_version": "1.0.0", "model_version": "protective-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/protective-puts-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "protective-put-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION, "target_moneyness": TARGET_MONEYNESS},
              "backtest": hedged_stats, "baseline": unhedged_stats}
    save_json("screens/protective-puts-backtest.json", result)
    LOG.info(f"Protective-put backtest: {hedged_stats['num_trades']} trades, "
             f"{hedged_stats['annualized_return']*100:.1f}% annualized (hedged) vs "
             f"{unhedged_stats['annualized_return']*100:.1f}% (unhedged baseline)")
    return result


if __name__ == "__main__":
    run()
