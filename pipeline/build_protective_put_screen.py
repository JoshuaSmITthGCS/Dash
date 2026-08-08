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

from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, liquidity_factor, realized_volatility_20d,
                            select_by_target_moneyness, select_expiration, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 15
MAX_DAYS_TO_EXPIRATION = 60
TARGET_DAYS_TO_EXPIRATION = 30
TARGET_MONEYNESS = -0.075
MONEYNESS_TOLERANCE = 0.03
MINIMUM_HISTORY_SESSIONS = 21

WEIGHTS = {"iv_value": .40, "cost_efficiency": .30, "liquidity": .30}


def build_row(entry, yf, as_of=None):
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
    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "confidence": entry.get("confidence"),
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
        },
        "factors": {
            "iv_value": -iv_rv_ratio if iv_rv_ratio is not None else None,
            "cost_efficiency": -cost_pct,
            "liquidity": liquidity_factor(put),
        },
    }


def build_rows(universe, yf, as_of=None):
    return [row for row in (build_row(entry, yf, as_of) for entry in universe) if row is not None]


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
        "structural_score": row.get("structural_score"), "confidence": row.get("confidence"),
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

    rows = build_rows(universe, yf, as_of)
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


if __name__ == "__main__":
    run()
