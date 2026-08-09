"""Publishes the structural + tactical research screen.

``research_screens_v2.tactical_score()`` has always held the scoring contract, and the
shadow report has always listed the sleeve. What never existed was a script to feed the
published universe through it, so ``screens/structural-tactical.json`` sat frozen at a
hand-written ``TACTICAL_SNAPSHOTS_NOT_YET_AVAILABLE`` placeholder and the sleeve reported
"awaiting first eligible portfolio" indefinitely - not because no portfolio qualified, but
because nothing was ever asked to build one.

Every factor is expressed as a cross-sectional percentile of the published universe, which
is what makes a weighted blend of revision breadth, surprise, and momentum commensurable at
all. Missing factors are left absent rather than defaulted: ``tactical_score()`` renormalizes
over the weight it actually has, and a neutral 50 stand-in would be a fabricated observation
pulling every score toward the middle.
"""

from datetime import datetime, timezone

from build_momentum_screen import build_rows
from common import LOG, load_json, save_json
from peer_groups import peer_group
from research_screens_v2 import tactical_score

MINIMUM_COVERAGE = 0.5


def percentile_ranks(values_by_ticker):
    """Cross-sectional percentile (0-100) per ticker, averaging ties."""
    present = {ticker: float(value) for ticker, value in values_by_ticker.items() if value is not None}
    if not present:
        return {}
    ordered = sorted(present.values())
    ranks = {}
    for ticker, value in present.items():
        below = sum(1 for other in ordered if other < value)
        equal = sum(1 for other in ordered if other == value)
        ranks[ticker] = round((below + equal / 2) / len(ordered) * 100, 4)
    return ranks


def _estimate_factors(row):
    detail = row.get("estimate_detail") or {}
    return {
        "revision_magnitude": detail.get("eps_revision_30d_pct", row.get("eps_revision_30d_pct")),
        "revision_agreement": detail.get("revision_breadth_30d", row.get("revision_breadth_30d")),
        "revision_acceleration": detail.get("net_upgrades_90d", row.get("net_upgrades_90d")),
        "fresh_estimate_delta": detail.get("target_change_30d_pct"),
        "eps_surprise": row.get("earnings_surprise"),
    }


def _risk_tradability(row):
    """Tradability rises with liquidity and falls with beta; either input alone will do."""
    volume, beta = row.get("average_dollar_volume"), row.get("beta")
    if volume is None and beta is None:
        return None
    return {"volume": volume, "beta": None if beta is None else -abs(float(beta))}


def collect_factors(universe, momentum_rows):
    """Raw per-ticker factor values, before any cross-sectional ranking."""
    momentum_by_ticker = {row["ticker"]: row for row in momentum_rows}
    collected = {}
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        analysis = entry.get("analysis_v2") or {}
        factors = _estimate_factors(entry)
        momentum = (momentum_by_ticker.get(ticker) or {}).get("factors") or {}
        for key in ("momentum_12_1", "momentum_6_1", "high_52w_proximity",
                    "industry_relative_momentum"):
            factors[key] = momentum.get(key)
        collected[ticker] = {
            "factors": factors,
            "risk": _risk_tradability(entry),
            "peer_group": peer_group(entry),
            "structural_score": (analysis.get("structural") or {}).get("effective_score",
                                                                       entry.get("score")),
            "confidence": entry.get("confidence"),
            # The revision backtest needs a stored estimate history to replay against.
            # Until one exists the score still publishes; it is flagged, not withheld.
            "snapshot_available": bool((entry.get("estimate_detail") or {}).get("revision_period")),
        }
    return collected


def _industry_revision_breadth(collected):
    """Peer-group mean revision breadth, assigned back to every member of that group."""
    by_group = {}
    for ticker, row in collected.items():
        breadth = row["factors"].get("revision_agreement")
        if breadth is not None:
            by_group.setdefault(row["peer_group"][0], []).append(float(breadth))
    means = {group: sum(values) / len(values) for group, values in by_group.items()}
    return {ticker: means.get(row["peer_group"][0]) for ticker, row in collected.items()}


def score_universe(collected):
    """Percentile-rank every factor across the universe, then blend by declared weights."""
    keys = {key for row in collected.values() for key in row["factors"]}
    ranked = {key: percentile_ranks({ticker: row["factors"].get(key)
                                     for ticker, row in collected.items()}) for key in keys}
    ranked["industry_revision_breadth"] = percentile_ranks(_industry_revision_breadth(collected))
    volume = percentile_ranks({ticker: (row["risk"] or {}).get("volume")
                               for ticker, row in collected.items()})
    beta = percentile_ranks({ticker: (row["risk"] or {}).get("beta")
                             for ticker, row in collected.items()})
    ranked["risk_tradability"] = {
        ticker: round(sum(parts) / len(parts), 4)
        for ticker in collected
        if (parts := [value for value in (volume.get(ticker), beta.get(ticker)) if value is not None])
    }

    scored = []
    for ticker, row in collected.items():
        factors = {key: values[ticker] for key, values in ranked.items() if ticker in values}
        result = tactical_score(factors, row["structural_score"], row["snapshot_available"])
        scored.append({"ticker": ticker, **result, "confidence": row["confidence"],
                       "peer_group": row["peer_group"][1], "factor_count": len(factors)})
    return sorted(scored, key=lambda row: (row["tactical_score"] is not None,
                                           row["tactical_score"] or 0), reverse=True)


def to_result(rank, row):
    eligible = row["tactical_score"] is not None and row["coverage"] >= MINIMUM_COVERAGE
    reasons = list(row["quality_flags"])
    if row["tactical_score"] is None:
        reasons.append("NO_TACTICAL_FACTORS_AVAILABLE")
    elif row["coverage"] < MINIMUM_COVERAGE:
        reasons.append("INSUFFICIENT_FACTOR_COVERAGE")
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": eligible,
        "peer_group": row["peer_group"],
        "tactical_score": row["tactical_score"],
        "structural_score": row["structural_score"],
        "classification": row["classification"],
        "coverage": row["coverage"],
        "confidence": row["confidence"],
        "reason_codes": reasons,
    }


def run():
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    models = load_json("research_models.json", from_config=True) or {}
    header = {
        "schema_version": "1.0.0",
        "model_version": (models.get("tactical") or {}).get("model_version", "tactical-v1.0.0"),
        "config_version": models.get("config_version", "screens-v2.0.0"),
        "generated_at": generated_at,
    }
    if not universe:
        LOG.warn("Structural + tactical screen: no published universe to score, skipping")
        result = {**header, "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE",
                  "results": []}
        save_json("screens/structural-tactical.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    collected = collect_factors(universe, build_rows(universe, yf))
    scored = score_universe(collected)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    eligible = sum(1 for row in results if row["eligibility"])
    if not eligible:
        result = {**header, "status": "unavailable",
                  "reason_code": "NO_TICKER_MEETS_TACTICAL_FACTOR_COVERAGE", "results": results}
        save_json("screens/structural-tactical.json", result)
        return result
    result = {**header, "status": "success", "results": results}
    save_json("screens/structural-tactical.json", result)
    LOG.info(f"Structural + tactical screen: scored {len(results)} tickers ({eligible} eligible)")
    return result


if __name__ == "__main__":
    run()
