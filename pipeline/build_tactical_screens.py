"""Publishes the two near-term screens: earnings timeliness, and the structural/tactical matrix.

Both read the same tactical factor set, so they are built together from one pass rather than
scored twice. research_screens_v2.tactical_score has always held the weights and the quadrant
logic; what was missing was anything that assembled real factors for it, which is why
earnings-timeliness.json shipped as REVISION_BACKTEST_UNAVAILABLE_FORWARD_COLLECTION_ONLY and
structural-tactical.json as TACTICAL_SNAPSHOTS_NOT_YET_AVAILABLE.

Neither reason code was wrong, and neither is discarded here. A revision *backtest* genuinely
is unavailable - the estimate store only began collecting forward, so nobody can ask what
consensus said last winter. But a screen of today's revisions never needed a backtest to be
publishable; it needed today's revisions, which the advisor snapshot has been carrying all
along in `estimate_detail`. So each row keeps FORWARD_COLLECTION_ONLY as a quality flag until
its own estimate history is deep enough to drop it, and the screen publishes.

Factors, and what fills them:

  revision agreement / magnitude   published 30-day revision breadth and EPS revision percent
  revision acceleration            the estimate snapshot store, for tickers it has collected
  dispersion trend                 the same store's high/low estimate spread, narrowing or not
  price confirmation               exact month-end 12-1 and 6-1 skip-month returns and
                                   52-week proximity from the cached daily closes
  industry breadth                 the peer group's revision breadth, leave-one-out
  tradability                      median dollar volume against realized volatility

Every factor is ranked across the cross-section before scoring, because tactical_score reads
its inputs on a 0-100 scale and treats 60 as the timely line. Factors nothing can fill stay
absent; tactical_score divides by the weight actually present, and `coverage` is published per
row so a score built from two thirds of the model is never mistaken for a complete one.
"""

import math
import os
from datetime import datetime, timezone

from common import LOG, STORE_DIR, load_json, save_json
import earnings_timeliness_pit_store
from estimate_snapshots import estimate_revision_diagnostics, snapshots_at_or_before
from peer_groups import peer_group
from research_screens_v2 import (TACTICAL_WEIGHTS, industry_relative_returns, momentum_factors,
                                 tactical_score)
from screen_inputs import (backtest_entry, cross_sectional_percentiles, latest_observations,
                           median_dollar_volume, universe_rows, with_current_price)

ESTIMATES_DIR = os.path.join(STORE_DIR, "estimates")
MINIMUM_HISTORY_SESSIONS = 253
# tactical_score renormalizes by the weight it could fill, so a row with one factor still
# produces a number. Below this share of the model, that number is an opinion about one input
# dressed as a composite - published, ranked, but not called eligible.
MINIMUM_COVERAGE = .35
# Same reasoning as the quality-value screen: the ranked head, with both counts published, in
# place of a megabyte of table.
PUBLISH_LIMIT = 300
VOLATILITY_WINDOW = 60
# The screen's own horizon. Anything scored on estimate revisions that are already a quarter
# stale is not a one-to-three-month signal.
TIMELINESS_BANDS = ((75, "accelerating expectations"), (60, "improving expectations"),
                    (40, "stable expectations"), (0, "deteriorating expectations"))


def realized_volatility(closes, window=VOLATILITY_WINDOW):
    """Annualized standard deviation of daily log returns over the trailing window."""
    series = [close for close in (closes or [])[-(window + 1):] if close and close > 0]
    if len(series) < 21:
        return None
    returns = [math.log(series[index + 1] / series[index]) for index in range(len(series) - 1)]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def estimate_diagnostics(ticker, as_of, root=None):
    """Revision acceleration and dispersion trend from this ticker's own collected snapshots.

    Returns `available=False` when the store holds too little of this ticker's history to say
    anything - which is most of the universe today, and is exactly what FORWARD_COLLECTION_ONLY
    is for.
    """
    snapshots = snapshots_at_or_before(root or ESTIMATES_DIR, ticker, as_of)
    if len(snapshots) < 2:
        return {"available": False, "revision_acceleration": None, "dispersion_trend": None}
    diagnostics = estimate_revision_diagnostics(snapshots, as_of=as_of)
    dispersions = [((snapshot.get("estimates") or {}).get("horizons") or {})
                   .get("current_year", {}).get("dispersion") for snapshot in snapshots]
    present = [value for value in dispersions if isinstance(value, (int, float))]
    # A narrowing spread between the high and low estimate is analysts converging, so the
    # factor is signed to make narrowing the positive direction.
    trend = None
    if len(present) >= 2 and present[0]:
        trend = (present[0] - present[-1]) / abs(present[0])
    return {"available": diagnostics.get("status") == "AVAILABLE",
            "revision_acceleration": diagnostics.get("revision_acceleration"),
            "dispersion_trend": trend}


def build_rows(universe, as_of, entry_for=backtest_entry, estimates_root=None, observations=None):
    """One row per ticker carrying raw (un-ranked) tactical factors and its context."""
    observations = observations if observations is not None else latest_observations()
    rows = []
    for row in universe:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        observed = observations.get(ticker) or {}
        entry = with_current_price(entry_for(ticker) or {}, row.get("price"),
                                   row.get("last_polled_at")) or {}
        # Dividend-adjusted closes here: these factors are returns, and an unadjusted series
        # would read every ex-dividend date as a real drop in the stock.
        dates, closes = entry.get("dates") or [], entry.get("closes") or []
        prices = [{"date": day, "adjusted_close": close} for day, close in zip(dates, closes)]
        factors = momentum_factors(prices, as_of=dates[-1] if dates else None) or {}
        estimate = row.get("estimate_detail") or {}
        diagnostics = estimate_diagnostics(ticker, as_of, root=estimates_root)
        group_id, group_label = peer_group(row)
        volatility = realized_volatility(closes)
        rows.append({
            "ticker": ticker, "sector": row.get("sector"),
            "peer_group": group_id, "peer_group_label": group_label,
            "structural_score": row.get("score"),
            "structural_data_coverage": ((row.get("score_variants") or {}).get("champion") or {}).get("data_coverage"),
            "price": row.get("price") or (closes[-1] if closes else None),
            "market_cap": row.get("market_cap") or observed.get("market_cap"),
            "median_dollar_volume_60d": median_dollar_volume(closes, entry.get("volumes") or []),
            "realized_volatility": volatility,
            "history_sessions": len(closes),
            "snapshot_available": diagnostics["available"],
            "momentum_12_1": factors.get("momentum_12_1"),
            "raw": {
                "revision_agreement": estimate.get("revision_breadth_30d"),
                "revision_magnitude": estimate.get("eps_revision_30d_pct"),
                "revision_acceleration": diagnostics["revision_acceleration"],
                "dispersion_trend": diagnostics["dispersion_trend"],
                "momentum_12_1": factors.get("momentum_12_1"),
                "momentum_6_1": factors.get("momentum_6_1"),
                "high_52w_proximity": factors.get("high_52w_proximity"),
            },
        })
    return rows


def attach_industry_factors(rows):
    """Peer-group aggregates: relative momentum, and the group's own revision breadth.

    Both are computed leave-one-out - a company is never part of the benchmark it is being
    measured against, or a lone name in a thin group would score neutral by construction.
    """
    relative = industry_relative_returns(rows)
    for row in rows:
        row["raw"]["industry_relative_momentum"] = (relative.get(row["ticker"]) or {}).get(
            "industry_relative_momentum")

    by_group = {}
    for row in rows:
        value = row["raw"]["revision_agreement"]
        if value is not None:
            by_group.setdefault(row["peer_group"], []).append((row["ticker"], float(value)))
    for row in rows:
        peers = [value for ticker, value in by_group.get(row["peer_group"], [])
                 if ticker != row["ticker"]]
        row["raw"]["industry_revision_breadth"] = sum(peers) / len(peers) if peers else None
    return rows


def attach_tradability(rows):
    """Liquidity against volatility, as a single 0-100 factor.

    A name can be timely and still be untradeable. Averaging the two ranks says "big enough to
    get in and out of, calm enough that the entry price means something" without either one
    dominating on its own units.
    """
    liquidity = cross_sectional_percentiles([row["median_dollar_volume_60d"] for row in rows])
    calm = cross_sectional_percentiles([None if row["realized_volatility"] is None
                                        else -row["realized_volatility"] for row in rows])
    for row, liquid, quiet in zip(rows, liquidity, calm):
        present = [value for value in (liquid, quiet) if value is not None]
        row["raw"]["risk_tradability"] = sum(present) / len(present) if present else None
    return rows


def rank_factors(rows):
    """Turn every raw factor into a cross-sectional 0-100 rank.

    Deliberately not winsorized first. Clipping the tails protects a z-score from one absurd
    input, but a rank is already immune to that - and clipping before ranking would collapse
    the strongest revisions in the market into a tie at the top, which is the one part of the
    distribution a timeliness screen exists to order.
    """
    names = sorted({name for row in rows for name in row["raw"]})
    ranked = {name: cross_sectional_percentiles([row["raw"].get(name) for row in rows])
              for name in names}
    for index, row in enumerate(rows):
        row["factors"] = {name: ranked[name][index] for name in names
                          if ranked[name][index] is not None}
    return rows


def score_rows(rows):
    for row in rows:
        scored = tactical_score(row["factors"], structural_score=row["structural_score"],
                                snapshot_available=row["snapshot_available"])
        row.update(scored)
        row["reason_codes"] = list(scored["quality_flags"])
        if row["history_sessions"] < MINIMUM_HISTORY_SESSIONS:
            row["reason_codes"].append("INSUFFICIENT_PRICE_HISTORY")
        if (row.get("coverage") or 0) < MINIMUM_COVERAGE:
            row["reason_codes"].append("LOW_FACTOR_COVERAGE")
    return rows


def timeliness_label(score):
    if score is None:
        return "not scored"
    return next(label for floor, label in TIMELINESS_BANDS if score >= floor)


def _base_result(rank, row, classification):
    return {
        "rank": rank, "ticker": row["ticker"], "sector": row.get("sector"),
        "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "classification": classification,
        "structural_score": row.get("structural_score"),
        "tactical_score": row.get("tactical_score"),
        "price": row.get("price"),
        # Coverage is the share of the model's weight the row's factors actually filled. It is
        # published as confidence because that is exactly what it is: how much of the score is
        # measurement rather than absence.
        "data_coverage": row.get("coverage"),
        "coverage": row.get("coverage"),
        "market_cap": row.get("market_cap"),
        "median_dollar_volume_60d": row.get("median_dollar_volume_60d"),
        # Each factor's rank. Its contribution is this times the published weight table, so
        # publishing both would be the same number twice on every row of a 300-row file.
        "factors": {name: round(value, 2) for name, value in (row.get("factors") or {}).items()},
        "eligibility": row.get("tactical_score") is not None
                       and row["history_sessions"] >= MINIMUM_HISTORY_SESSIONS
                       and (row.get("coverage") or 0) >= MINIMUM_COVERAGE,
        "current_membership": False,
        "reason_codes": row.get("reason_codes", []),
    }


def coverage_note(scored):
    """State how much of the tactical model these scores were actually built from."""
    if not scored:
        return "No tactical factor could be filled for any company in the published universe."
    coverages = sorted(row["coverage"] for row in scored)
    median = coverages[len(coverages) // 2]
    return (f"Tactical scores use the {round(median * 100)}% of the model's weight that today's "
            "inputs fill (revisions, price confirmation, industry breadth, tradability), "
            "renormalized. Revision acceleration, dispersion trend and the earnings-surprise "
            "factors stay absent until this pipeline's own forward collection is deep enough, "
            "which is what the FORWARD_COLLECTION_ONLY flag on each row means. The file "
            f"carries the top {PUBLISH_LIMIT} of {len(scored)} scored companies.")


def timeliness_payload(rows, generated_at):
    scored = [row for row in rows if row.get("tactical_score") is not None]
    ranked = sorted(scored, key=lambda row: (-row["tactical_score"], row["ticker"]))
    percentiles = cross_sectional_percentiles([row["tactical_score"] for row in ranked])
    results = []
    for rank, (row, percentile) in enumerate(zip(ranked[:PUBLISH_LIMIT], percentiles)):
        result = _base_result(rank + 1, row, timeliness_label(row["tactical_score"]))
        result["percentile"] = None if percentile is None else round(percentile, 2)
        results.append(result)
    return {
        "schema_version": "1.0.0", "model_version": "tactical-v1.0.0",
        "config_version": "screens-v2.0.0", "generated_at": generated_at,
        "status": "success" if results else "unavailable",
        **({} if results else {"reason_code": "NO_TACTICAL_FACTORS_AVAILABLE"}),
        "factor_weights": TACTICAL_WEIGHTS,
        "universe_scored": len(scored), "publish_limit": PUBLISH_LIMIT,
        "revision_history": {
            "collection": "FORWARD_COLLECTION_ONLY",
            "tickers_with_estimate_history": sum(1 for row in rows if row["snapshot_available"]),
            "note": ("Revision acceleration and dispersion trend need this pipeline's own "
                     "collected estimate snapshots; no provider sells the back history, so "
                     "they fill in per ticker as the store accumulates."),
        },
        "coverage_note": coverage_note(scored),
        "results": results,
    }


def matrix_payload(rows, generated_at):
    """The two-axis screen: only rows that actually have both axes belong on it."""
    scored = [row for row in rows if row.get("tactical_score") is not None
              and row.get("structural_score") is not None]
    ranked = sorted(scored, key=lambda row: (-(row["structural_score"] + row["tactical_score"]),
                                             row["ticker"]))
    percentiles = cross_sectional_percentiles(
        [row["structural_score"] + row["tactical_score"] for row in ranked])
    results = []
    for rank, (row, percentile) in enumerate(zip(ranked[:PUBLISH_LIMIT], percentiles)):
        result = _base_result(rank + 1, row, row["classification"])
        result["percentile"] = None if percentile is None else round(percentile, 2)
        results.append(result)
    # Counted over everything scored, not just the published head - the quadrant split is a
    # statement about the cross-section, and truncating it would make "avoid" look rare.
    quadrants = {}
    for row in scored:
        quadrants[row["classification"]] = quadrants.get(row["classification"], 0) + 1
    return {
        "schema_version": "1.0.0", "model_version": "matrix-v1.0.0",
        "config_version": "screens-v2.0.0", "generated_at": generated_at,
        "status": "success" if results else "unavailable",
        **({} if results else {"reason_code": "NO_TWO_AXIS_COVERAGE"}),
        "factor_weights": TACTICAL_WEIGHTS,
        "universe_scored": len(scored), "publish_limit": PUBLISH_LIMIT,
        "quadrants": quadrants,
        "coverage_note": coverage_note(scored),
        "results": results,
    }


def run():
    advisor = load_json("advisor.json") or {}
    universe = universe_rows(advisor)
    if not universe:
        LOG.warn("Tactical screens: no published universe to score, skipping")
        return None
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = score_rows(rank_factors(attach_tradability(attach_industry_factors(
        build_rows(universe, generated_at)))))
    timeliness, matrix = timeliness_payload(rows, generated_at), matrix_payload(rows, generated_at)
    save_json("screens/earnings-timeliness.json", timeliness)
    save_json("screens/structural-tactical.json", matrix)
    # Point-in-time capture of the tactical composite and its factor ranks, for future
    # rank-IC and per-metric attribution validation - starts recording today, never
    # reconstructs history. See earnings_timeliness_pit_store.py and
    # validation/earnings_timeliness_ic.py.
    try:
        earnings_timeliness_pit_store.append_snapshot(timeliness["results"])
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"earnings_timeliness_pit_store snapshot failed ({type(exc).__name__}): {exc}")
    LOG.info(f"Earnings-timeliness screen: scored {timeliness['universe_scored']}, published "
             f"{len(timeliness['results'])}; matrix screen: scored {matrix['universe_scored']} "
             f"with both axes {matrix['quadrants']}, published {len(matrix['results'])}")
    return {"earnings_timeliness": timeliness, "structural_tactical": matrix}


if __name__ == "__main__":
    run()
