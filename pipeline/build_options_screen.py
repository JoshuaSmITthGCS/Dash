"""Publishes the "Best multi-day options" research screen.

For every ticker in the already-published advisor universe, pulls the nearest option
expiration inside a multi-day window (2-45 days out - excludes 0DTE/1DTE plays at one
end and LEAPS at the other), picks the most liquid near-the-money contract on the side
(call above a falling 20-day trend gets a put bias, calls otherwise) implied by recent
price trend, and ranks tickers by implied/realized volatility value, contract liquidity,
and trend strength.

Options-chain data is opt-in (ENABLE_MULTIDAY_OPTIONS_SCREEN=1): each ticker costs an
extra options-chain request on top of what fetch_advisor.py already pulls, the same
tradeoff fetch_advisor.py's own ENABLE_OPTIONS_VOLATILITY flag makes. This is a research
screen, not a trade instruction or order-routing feature - nothing in this codebase
places option orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expiration_spans_earnings, liquidity_factor,
                            next_earnings_date, realized_volatility_20d, research_universe_factors,
                            select_contract, trend_20d)
from options_common import select_expiration as _select_expiration
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 1
MAX_DAYS_TO_EXPIRATION = 14
TARGET_DAYS_TO_EXPIRATION = 7
MINIMUM_HISTORY_SESSIONS = 21

# news_sentiment/research_confidence are sign-aligned with the chosen side (call=+1,
# put=-1) via research_universe_factors' "signed" mode: this is a directional bet, so
# sentiment/research agreeing with that direction is a conviction-confirmation signal,
# not an independent one. Existing factors were shrunk proportionally (not just appended)
# to make room, so the composite still sums to 1.0.
#
# iv_value trimmed further (was .30) than a pure "make room for the new factors" split
# would give it: Driessen, Maenhout & Vilkov (2009, JF) found the variance risk premium
# that makes index-level short-vol reliable is largely a correlation-risk premium, and
# that individual-stock variance risk was NOT reliably priced in their sample - the
# IV-vs-RV signal this factor is built on is weaker and noisier for a single name than it
# is for an index. liquidity picked up the difference, since it's a harder signal to
# arbitrage away than a volatility mispricing.
WEIGHTS = {"iv_value": .25, "liquidity": .35, "trend_strength": .25,
          "news_sentiment": .08, "research_confidence": .07}


def select_expiration(expirations, as_of=None):
    """Nearest expiration to TARGET_DAYS_TO_EXPIRATION inside this screen's window."""
    return _select_expiration(expirations, MIN_DAYS_TO_EXPIRATION, MAX_DAYS_TO_EXPIRATION,
                              TARGET_DAYS_TO_EXPIRATION, as_of)


def build_row(entry, yf, as_of=None, generated_at=None):
    """One candidate row per ticker, or None if it doesn't clear a qualifying contract."""
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
    expiration, dte = select_expiration(expirations, as_of)
    if expiration is None:
        return None
    earnings_date = next_earnings_date(ticker_obj, ticker, as_of)
    if expiration_spans_earnings(expiration, earnings_date, as_of):
        LOG.info(f"{ticker}: excluded, {expiration} spans earnings on {earnings_date}")
        return None

    option_type = "put" if (trend or 0) < 0 else "call"
    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None
    contract = select_contract(chain.puts if option_type == "put" else chain.calls, price)
    if contract is None:
        return None

    iv_rv_ratio = (contract["implied_volatility"] / realized
                   if contract["implied_volatility"] and realized else None)
    direction = -1 if option_type == "put" else 1
    research_factors = research_universe_factors(entry, generated_at, as_of, direction=direction,
                                                  sentiment_mode="signed")
    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "confidence": entry.get("confidence"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "option_type": option_type, "expiration": expiration, "days_to_expiration": dte,
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
    contract = row.get("contract") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "confidence": row.get("confidence"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "option_type": row.get("option_type"), "expiration": row.get("expiration"),
        "days_to_expiration": row.get("days_to_expiration"),
        "strike": contract.get("strike"), "bid": contract.get("bid"), "ask": contract.get("ask"),
        "mid": contract.get("mid"), "spread_pct": contract.get("spread_pct"),
        "implied_volatility": contract.get("implied_volatility"),
        "realized_volatility_20d": row.get("realized_volatility_20d"),
        "implied_realized_vol_ratio": row.get("implied_realized_vol_ratio"),
        "open_interest": contract.get("open_interest"), "volume": contract.get("volume"),
        "moneyness": contract.get("moneyness"),
        "news_sentiment": round(row["news_sentiment"], 4) if row.get("news_sentiment") is not None else None,
        "research_confidence": round(row["research_confidence"], 4) if row.get("research_confidence") is not None else None,
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "multiday-options-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_MULTIDAY_OPTIONS_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Multi-day options screen: opt-in flag not set, skipping "
                 "(set ENABLE_MULTIDAY_OPTIONS_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Multi-day options screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/options.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/options.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/options.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "multiday-options-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION},
        "results": results,
    }
    save_json("screens/options.json", result)
    LOG.info(f"Multi-day options screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward backtest, pooling every ticker's trades into one aggregate result.

    Simulated entry (Black-Scholes priced off trailing realized vol), real settlement
    (actual historical closing price at expiry) - see this module's and backtest_common's
    docstrings for the full rationale. Buys the near-the-money contract on the side
    (call/put) implied by point-in-time trend, matching what the live screen recommends.
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
            option_type = "put" if trend < 0 else "call"
            calls, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)
            contract = select_contract(puts if option_type == "put" else calls, price)
            if contract is None:
                continue
            cost = contract["mid"] * 100 + CONTRACT_FEE
            if cost <= 0:
                continue
            intrinsic = (max(0, settle_price - contract["strike"]) if option_type == "call"
                        else max(0, contract["strike"] - settle_price))
            pnl = intrinsic * 100 - cost
            period_returns.append(pnl / cost)
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION, trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Walk-forward backtest of the multi-day options screen's strategy against the
    already-published advisor universe. See this module's top-of-file and
    backtest_common's docstrings for why this is simulated-entry/real-settlement and why
    it needs no live option-chain call.
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
        result = {"schema_version": "1.0.0", "model_version": "multiday-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/options-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "multiday-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/options-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "multiday-options-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/options-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "multiday-options-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION},
              "backtest": stats}
    save_json("screens/options-backtest.json", result)
    LOG.info(f"Multi-day options backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
