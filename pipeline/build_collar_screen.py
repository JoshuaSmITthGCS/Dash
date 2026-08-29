"""Publishes the "Collar" research screen.

For every ticker in the already-published advisor universe, builds a defined-risk collar:
long the underlying stock, a protective put purchased 5-10% below spot, and a covered call
sold around 30 delta, both legs sharing the same expiration. Ranks candidates by how close
to zero-cost the collar is (net premium paid or collected, as a fraction of spot) and how
wide the resulting floor-to-cap range is - a wider range for near-zero cost is a better
collar, since it leaves more room for the stock to move before either leg caps the outcome.

Options-chain data is opt-in (ENABLE_COLLAR_SCREEN=1): each ticker costs two extra
options-chain lookups (a put leg and a call leg) on top of what fetch_advisor.py already
pulls, the same tradeoff the other options-strategy screens make. This is a research
screen, not a trade instruction or order-routing feature - nothing in this codebase places
option orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expiration_spans_earnings, iv_skew, liquidity_factor,
                            next_earnings_date, put_call_oi_ratio, realized_volatility_20d, realized_vol_percentile,
                            research_universe_factors, select_by_target_delta, select_by_target_moneyness,
                            select_expiration, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
TARGET_MONEYNESS_PUT = -0.075
MONEYNESS_TOLERANCE = 0.03
TARGET_DELTA_CALL = 0.30
MINIMUM_HISTORY_SESSIONS = 21

# news_sentiment uses "inverse" mode (same reasoning as the covered-call leg this collar
# also sells: don't cap upside into a hot catalyst). research_confidence is a quality gate.
# Existing factors shrunk proportionally to still sum to 1.0.
WEIGHTS = {"cost_efficiency": .35, "range_width": .26, "liquidity": .26,
          "news_sentiment": .05, "research_confidence": .08}


def build_row(entry, yf, as_of=None, generated_at=None):
    """One candidate collar row per ticker, or None if it doesn't clear a qualifying pair."""
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

    put = select_by_target_moneyness(chain.puts, price, TARGET_MONEYNESS_PUT, MONEYNESS_TOLERANCE)
    if put is None:
        return None
    call = select_by_target_delta(chain.calls, price, dte, side="call", target_delta=TARGET_DELTA_CALL)
    if call is None:
        return None
    if call["strike"] <= put["strike"]:
        return None

    skew = iv_skew(chain.calls, chain.puts, price, dte)
    pc_oi_ratio = put_call_oi_ratio(chain.calls, chain.puts)
    vol_percentile = realized_vol_percentile(closes)
    net_cost = put["mid"] - call["mid"]
    net_cost_pct = net_cost / price
    floor_price = put["strike"]
    cap_price = call["strike"]
    range_width_pct = (cap_price - floor_price) / price
    max_loss_pct = ((price - floor_price) + net_cost) / price
    max_gain_pct = ((cap_price - price) - net_cost) / price
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
        "capital_required": price * 100 + max(net_cost, 0) * 100,
        "put": put, "call": call,
        "metrics": {
            "net_cost": round(net_cost, 4), "net_cost_pct": round(net_cost_pct, 4),
            "floor_price": floor_price, "cap_price": cap_price,
            "range_width_pct": round(range_width_pct, 4),
            "max_loss_pct": round(max_loss_pct, 4), "max_gain_pct": round(max_gain_pct, 4),
            "iv_skew": skew, "put_call_oi_ratio": pc_oi_ratio, "realized_volatility_percentile": vol_percentile,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "cost_efficiency": -abs(net_cost_pct),
            "range_width": range_width_pct,
            "liquidity": min(liquidity_factor(put), liquidity_factor(call)),
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
    put, call = row.get("put") or {}, row.get("call") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "legs": [
            {"action": "buy", "option_type": "put", "strike": put.get("strike"),
             "bid": put.get("bid"), "ask": put.get("ask"), "mid": put.get("mid"),
             "spread_pct": put.get("spread_pct"), "implied_volatility": put.get("implied_volatility"),
             "open_interest": put.get("open_interest")},
            {"action": "sell", "option_type": "call", "strike": call.get("strike"),
             "bid": call.get("bid"), "ask": call.get("ask"), "mid": call.get("mid"),
             "spread_pct": call.get("spread_pct"), "implied_volatility": call.get("implied_volatility"),
             "open_interest": call.get("open_interest"), "delta": call.get("delta")},
        ],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "collar-v1.1.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_COLLAR_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Collar screen: opt-in flag not set, skipping (set ENABLE_COLLAR_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Collar screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/collars.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/collars.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/collars.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "collar-v1.1.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "target_moneyness_put": TARGET_MONEYNESS_PUT,
                   "target_delta_call": TARGET_DELTA_CALL},
        "results": results,
    }
    save_json("screens/collars.json", result)
    LOG.info(f"Collar screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward simulation of continuously holding a rolling collar, pooled across
    every ticker in `universe` into one aggregate result.

    Each period buys a fresh protective put and sells a fresh covered call, both priced
    with Black-Scholes off trailing realized volatility computed ONLY from price history
    up to and including the entry date (no lookahead) - then settles against the REAL
    historical closing price at expiry, clamped between the put floor and the call cap.
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
            put = select_by_target_moneyness(puts, price, TARGET_MONEYNESS_PUT, MONEYNESS_TOLERANCE)
            call = select_by_target_delta(calls, price, TARGET_DAYS_TO_EXPIRATION, side="call",
                                          target_delta=TARGET_DELTA_CALL)
            if put is None or call is None or call["strike"] <= put["strike"]:
                continue
            net_cost_per_share = put["mid"] - call["mid"]
            fee_per_share = 2 * CONTRACT_FEE / 100
            floor, cap = put["strike"], call["strike"]
            # min(max(settle_price, floor), cap) clamps the payoff between the put floor and
            # the call cap - the whole point of a collar.
            clamped = min(max(settle_price, floor), cap)
            period_return = (clamped - price) / price - (net_cost_per_share + fee_per_share) / price
            period_returns.append(period_return)
            trade_pnls.append(period_return * price * 100)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION,
                             trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Publishes the walk-forward collar backtest. Always runs when called - unlike the
    live screen's run(), there's no ENABLE_COLLAR_SCREEN gate, since this needs no live
    option-chain network call at all (see backtest_common's module docstring).
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
        result = {"schema_version": "1.0.0", "model_version": "collar-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/collars-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "collar-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/collars-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "collar-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/collars-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "collar-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                         "target_moneyness_put": TARGET_MONEYNESS_PUT, "target_delta_call": TARGET_DELTA_CALL},
              "backtest": stats}
    save_json("screens/collars-backtest.json", result)
    LOG.info(f"Collar backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
