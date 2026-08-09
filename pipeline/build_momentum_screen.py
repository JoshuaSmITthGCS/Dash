"""Publishes the Momentum research screen from the same 2-year Yahoo price history
fetch_advisor.py already fetched and cached this run.

research_screens_v2.py supplies every scoring formula (exact month-end skip-month
returns, cross-sectional z-scoring, correlation-capped composite, hysteresis-based
membership) and already has its own test suite. What was missing was real per-ticker
price series and a script to feed them through it and write the published file - this
is that script. It costs no additional network calls: yahoo_history() reads the
on-disk cache fetch_advisor.py just warmed for the same symbols.
"""

from datetime import datetime, timezone

from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from peer_groups import peer_group
from research_screens_v2 import industry_relative_returns, momentum_factors, momentum_scores

MINIMUM_HISTORY_SESSIONS = 253


def median_dollar_volume(closes, volumes, window=60):
    if not closes or not volumes or len(closes) != len(volumes):
        return None
    paired = list(zip(closes[-window:], volumes[-window:]))
    if not paired:
        return None
    dollar = sorted(close * volume for close, volume in paired)
    mid = len(dollar) // 2
    return dollar[mid] if len(dollar) % 2 else (dollar[mid - 1] + dollar[mid]) / 2


def build_rows(universe, yf):
    """One row per ticker with real month-end price factors, or skipped if history is too thin."""
    rows = []
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        history = yahoo_history(ticker, yf)
        dates, closes, volumes = history["dates"], history["closes"], history["volumes"]
        if len(closes) < 21:
            continue
        prices = [{"date": day, "adjusted_close": close} for day, close in zip(dates, closes)]
        factors = momentum_factors(prices, as_of=dates[-1] if dates else None)
        if factors is None:
            continue
        group_id, group_label = peer_group(entry)
        rows.append({
            "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
            "price": closes[-1], "market_cap": entry.get("market_cap"),
            "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
            "history_sessions": len(closes), "sector": entry.get("sector"),
            "structural_score": entry.get("score"), "data_coverage": entry.get("data_coverage"),
            # industry_relative_returns() (below) reads momentum_12_1 off the row directly,
            # not from factors - a different row shape than momentum_scores() expects.
            "momentum_12_1": factors.get("momentum_12_1"),
            "factors": factors,
        })
    peer_returns = industry_relative_returns(rows)
    for row in rows:
        relative = (peer_returns.get(row["ticker"]) or {}).get("industry_relative_momentum")
        if relative is not None:
            row["factors"]["industry_relative_momentum"] = relative
    return rows


def previous_members(screen):
    return {row["ticker"]: True for row in (screen or {}).get("results", [])
            if row.get("current_membership") and row.get("ticker")}


def to_result(rank, row):
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": round(row["percentile"], 2) if row.get("percentile") is not None else None,
        # Fundamentals composite already published for this ticker today, reused as-is
        # so the shared screen table has a like-for-like quality reference beside momentum.
        "structural_score": row.get("structural_score"),
        "tactical_score": None,
        "data_coverage": row.get("data_coverage"),
        "current_membership": bool(row.get("current_membership")),
        "reason_codes": row.get("reason_codes", []),
    }


def run():
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    if not universe:
        LOG.warn("Momentum screen: no published universe to score, skipping")
        return None
    try:
        import yfinance as yf
    except ImportError:
        yf = None

    rows = build_rows(universe, yf)
    generated_at = datetime.now(timezone.utc).isoformat()
    if not rows:
        result = {
            "schema_version": "1.0.0", "model_version": "momentum-v2.0.0",
            "config_version": "screens-v2.0.0", "generated_at": generated_at,
            "status": "unavailable", "reason_code": "INSUFFICIENT_PRICE_HISTORY", "results": [],
        }
        save_json("screens/momentum.json", result)
        return result

    scored = momentum_scores(rows, current_members=previous_members(load_json("screens/momentum.json")),
                             config={"minimum_history_sessions": MINIMUM_HISTORY_SESSIONS})
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "momentum-v2.0.0",
        "config_version": "screens-v2.0.0", "generated_at": generated_at,
        "status": "success", "results": results,
    }
    save_json("screens/momentum.json", result)
    LOG.info(f"Momentum screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


if __name__ == "__main__":
    run()
