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

import math
import os
import statistics
from datetime import date, datetime, timezone

from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

MIN_DAYS_TO_EXPIRATION = 2
MAX_DAYS_TO_EXPIRATION = 45
TARGET_DAYS_TO_EXPIRATION = 14
ATM_TOLERANCE = 0.10
MINIMUM_OPEN_INTEREST = 50
MAXIMUM_SPREAD_PCT = 0.35
MINIMUM_HISTORY_SESSIONS = 21
MINIMUM_PRICE = 5
MINIMUM_MARKET_CAP = 300_000_000

WEIGHTS = {"iv_value": .35, "liquidity": .35, "trend_strength": .30}


def realized_volatility_20d(closes):
    if len(closes) < 21 or any(value <= 0 for value in closes[-21:]):
        return None
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
    return statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None


def trend_20d(closes):
    if len(closes) < 21 or closes[-21] <= 0:
        return None
    return closes[-1] / closes[-21] - 1


def days_to_expiration(expiration, as_of=None):
    as_of = as_of or date.today()
    try:
        expiration_date = datetime.strptime(expiration, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (expiration_date - as_of).days


def select_expiration(expirations, as_of=None):
    """Nearest expiration to TARGET_DAYS_TO_EXPIRATION inside the multi-day window."""
    candidates = []
    for expiration in expirations or []:
        dte = days_to_expiration(expiration, as_of)
        if dte is not None and MIN_DAYS_TO_EXPIRATION <= dte <= MAX_DAYS_TO_EXPIRATION:
            candidates.append((abs(dte - TARGET_DAYS_TO_EXPIRATION), expiration, dte))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0])
    _, expiration, dte = candidates[0]
    return expiration, dte


def select_contract(frame, price):
    """Tightest-spread near-the-money contract among adequately liquid rows."""
    best = None
    for _, contract in frame.iterrows():
        strike = contract.get("strike")
        bid, ask = contract.get("bid"), contract.get("ask")
        open_interest = contract.get("openInterest") or 0
        if not strike or not price or abs(strike / price - 1) > ATM_TOLERANCE:
            continue
        if not bid or not ask or bid <= 0 or ask <= 0 or ask < bid:
            continue
        if open_interest < MINIMUM_OPEN_INTEREST:
            continue
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid else None
        if spread_pct is None or spread_pct > MAXIMUM_SPREAD_PCT:
            continue
        implied_volatility = contract.get("impliedVolatility")
        candidate = {
            "strike": float(strike), "bid": float(bid), "ask": float(ask), "mid": round(mid, 4),
            "spread_pct": round(spread_pct, 4),
            "implied_volatility": float(implied_volatility) if implied_volatility else None,
            "open_interest": int(open_interest), "volume": int(contract.get("volume") or 0),
            "moneyness": round(strike / price - 1, 4),
        }
        if best is None or candidate["spread_pct"] < best["spread_pct"]:
            best = candidate
    return best


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
        "factors": {
            "iv_value": -iv_rv_ratio if iv_rv_ratio is not None else None,
            "liquidity": math.log10(max(contract["open_interest"], 1)) - contract["spread_pct"],
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

    rows = build_rows(universe, yf, as_of)
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


if __name__ == "__main__":
    run()
