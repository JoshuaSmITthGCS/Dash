"""Publishes the "Cash-secured put" research screen.

For every ticker in the already-published advisor universe, sells an out-of-the-money put
collateralized with cash (a "cash-secured put") near a 30-delta strike on a monthly-income
expiration window (15-45 days out), and ranks tickers by annualized yield on the collateral,
probability the put expires worthless (premium kept, no assignment), and contract liquidity.
This is the classic "sell puts on stocks you wouldn't mind owning at a discount" income idea.

Options-chain data is opt-in (ENABLE_CASH_SECURED_PUT_SCREEN=1): each ticker costs an extra
options-chain request on top of what fetch_advisor.py already pulls, the same tradeoff
fetch_advisor.py's own ENABLE_OPTIONS_VOLATILITY flag makes. This is a research screen, not a
trade instruction or order-routing feature - nothing in this codebase places option orders,
posts collateral, or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

from backtest_common import CONTRACT_FEE, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, liquidity_factor, probability_above,
                            realized_volatility_20d, select_by_target_delta, select_expiration,
                            trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 30
TARGET_DELTA = 0.30
MINIMUM_HISTORY_SESSIONS = 21

WEIGHTS = {"annualized_yield": .40, "probability_otm": .30, "liquidity": .30}


def build_row(entry, yf, as_of=None):
    """One candidate row per ticker, or None if it doesn't clear a qualifying contract."""
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

    try:
        chain = ticker_obj.option_chain(expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None
    put = select_by_target_delta(chain.puts, price, dte, side="put", target_delta=TARGET_DELTA)
    if put is None:
        return None

    premium = put["mid"]
    collateral = put["strike"] * 100
    effective_cost_basis = put["strike"] - premium
    annualized_yield = (premium / put["strike"]) * (365 / dte)
    probability_otm = (probability_above(price, put["strike"], put["implied_volatility"], dte)
                       if put["implied_volatility"] is not None else None)
    probability_assigned = None if probability_otm is None else (1 - probability_otm)

    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "confidence": entry.get("confidence"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        "expiration": expiration, "days_to_expiration": dte,
        "capital_required": collateral,
        "put": put,
        "metrics": {
            "premium": round(premium, 4), "collateral": round(collateral, 2),
            "effective_cost_basis": round(effective_cost_basis, 4),
            "annualized_yield": round(annualized_yield, 4),
            "probability_otm": round(probability_otm, 4) if probability_otm is not None else None,
            "probability_assigned": round(probability_assigned, 4) if probability_assigned is not None else None,
        },
        "factors": {
            "annualized_yield": annualized_yield,
            "probability_otm": probability_otm,
            "liquidity": liquidity_factor(put),
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
    put = row.get("put") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "confidence": row.get("confidence"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "legs": [{"action": "sell", "option_type": "put", "strike": put.get("strike"),
                  "bid": put.get("bid"), "ask": put.get("ask"), "mid": put.get("mid"),
                  "spread_pct": put.get("spread_pct"), "implied_volatility": put.get("implied_volatility"),
                  "open_interest": put.get("open_interest"), "delta": put.get("delta")}],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "cash-secured-put-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_CASH_SECURED_PUT_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("Cash-secured put screen: opt-in flag not set, skipping "
                 "(set ENABLE_CASH_SECURED_PUT_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("Cash-secured put screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/cash-secured-puts.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/cash-secured-puts.json", result)
        return result

    rows = build_rows(universe, yf, as_of)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/cash-secured-puts.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "cash-secured-put-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                   "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                   "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION,
                   "target_delta": TARGET_DELTA},
        "results": results,
    }
    save_json("screens/cash-secured-puts.json", result)
    LOG.info(f"Cash-secured put screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Walk-forward simulation of continuously rolling a cash-secured put across every ticker
    in `universe`, pooling all tickers' trades into one aggregate result. See backtest_common
    for the no-lookahead pricing/settlement mechanics.
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
            _, puts = synthetic_chain(price, iv, TARGET_DAYS_TO_EXPIRATION)
            put = select_by_target_delta(puts, price, TARGET_DAYS_TO_EXPIRATION, side="put",
                                         target_delta=TARGET_DELTA)
            if put is None:
                continue
            strike = put["strike"]
            premium_per_share = put["mid"]
            fee_per_share = CONTRACT_FEE / 100
            # Collect the premium yield on the collateral every period; if assigned
            # (settle_price below strike), additionally mark the loss down to settle_price -
            # min(0, ...) is 0 when settle_price >= strike (no assignment, no extra loss).
            period_return = ((premium_per_share - fee_per_share) / strike
                             + min(0, (settle_price - strike) / strike))
            period_returns.append(period_return)
            trade_pnls.append(period_return * strike * 100)
    return performance_stats(period_returns, periods_per_year=365 / TARGET_DAYS_TO_EXPIRATION,
                             trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Walk-forward backtest of the cash-secured-put strategy. Needs no live option-chain
    data (only cached price history), so unlike run() this always attempts to execute -
    there's no ENABLE_CASH_SECURED_PUT_SCREEN gate to check.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("Simulated: option entry prices are Black-Scholes estimates using trailing "
                   "realized volatility as the implied-volatility input, not quoted historical "
                   "prices. Real historical bid/ask spreads, open interest, and fill quality are "
                   "not modeled. Trade settlement uses real historical closing prices.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "cash-secured-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/cash-secured-puts-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "cash-secured-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/cash-secured-puts-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "cash-secured-put-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/cash-secured-puts-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "cash-secured-put-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"min_days_to_expiration": MIN_DAYS_TO_EXPIRATION,
                         "max_days_to_expiration": MAX_DAYS_TO_EXPIRATION,
                         "target_days_to_expiration": TARGET_DAYS_TO_EXPIRATION, "target_delta": TARGET_DELTA},
              "backtest": stats}
    save_json("screens/cash-secured-puts-backtest.json", result)
    LOG.info(f"Cash-secured-put backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
