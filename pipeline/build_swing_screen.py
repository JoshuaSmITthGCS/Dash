"""Publishes the swing-horizon screen (2 trading days to 8 weeks) to screens/swing.json.

swing_signals.py holds every formula, weight, gate and citation; this script is the part
that assembles real inputs for it and writes the file. Like the other research screens it
costs no network call: the price and volume series come from the on-disk backtest cache that
fetch_advisor.py already maintains, and the revision, surprise and short-interest inputs come
from the advisor snapshot published moments earlier in the same run.

What lands in the file beyond the ranked rows: the declared weights, the citation and
published (gross, pre-decay) effect size behind each leg, the McLean-Pontiff decay haircut,
the eligibility thresholds actually applied, and per-leg coverage across the universe. A leg
that resolved on 4% of the cross-section produces a very different screen from one that
resolved on 90%, and the page has to be able to say which it is showing.
"""

from datetime import datetime, timezone

from common import LOG, load_json, save_json
from peer_groups import peer_group
from screen_inputs import (backtest_entry, latest_observations, median_dollar_volume,
                           universe_rows, with_current_price)
from swing_signals import (DECAY_HAIRCUT, DEFAULT_CONFIG, HOLDING_HORIZON,
                           SHORT_INTEREST_EVIDENCE, SWING_EVIDENCE, SWING_SUBFACTORS,
                           SWING_WEIGHTS, leg_coverage, swing_factors, swing_scores)

SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "swing-v1.0.0"
CONFIG_VERSION = "screens-v2.0.0"
OUTPUT = "screens/swing.json"
# Same ranked-head convention as the quality-value and tactical screens: publish the head
# with both counts stated rather than shipping a megabyte of table to a phone.
PUBLISH_LIMIT = 300


def publishable(scored):
    """The head, plus every name the short-interest screen suppressed out of it.

    A negative screen that silently deletes its hits is indistinguishable from a screen that
    never fired. A name scoring in the head and removed for carrying 14% of its float short
    is a *result* - arguably the most actionable one on the page - so it is published with
    its reason attached and its eligibility false, rather than dropped off the bottom.
    Rows excluded for price, size, liquidity, history or thin coverage are ordinary universe
    misses and stay counted-but-unpublished.
    """
    keep = [row for row in scored
            if row.get("eligibility") or (row.get("short_interest") or {}).get("suppressed")]
    return sorted(keep, key=lambda row: row["score"], reverse=True)[:PUBLISH_LIMIT]


def build_rows(universe, entry_for=None, observations=None):
    """One pre-score row per ticker: its context, plus every raw swing subfactor."""
    entry_for = entry_for or backtest_entry
    observations = observations if observations is not None else latest_observations()
    rows = []
    for row in universe:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        observed = observations.get(ticker) or {}
        # Dividend-adjusted closes: every factor here is a return or a ratio of returns, and
        # an unadjusted series reads each ex-dividend date as a real decline.
        entry = with_current_price(entry_for(ticker) or {}, row.get("price"),
                                   row.get("last_polled_at")) or {}
        closes, volumes = entry.get("closes") or [], entry.get("volumes") or []
        if not closes:
            continue
        group_id, group_label = peer_group(row)
        rows.append({
            "ticker": ticker, "name": row.get("name"), "sector": row.get("sector"),
            "peer_group": group_id, "peer_group_label": group_label,
            "price": row.get("price") or closes[-1],
            "market_cap": row.get("market_cap") or observed.get("market_cap"),
            "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
            "history_sessions": len(closes),
            "structural_score": row.get("score"),
            "data_coverage": row.get("data_coverage"),
            "short_percent_of_float": row.get("short_percent_of_float") or observed.get("short_percent_of_float"),
            "days_to_cover": row.get("days_to_cover") or observed.get("days_to_cover"),
            "factors": swing_factors(row, closes=closes, volumes=volumes),
        })
    return rows


def previous_members(screen):
    return {row["ticker"]: True for row in (screen or {}).get("results", [])
            if row.get("current_membership") and row.get("ticker")}


def _rounded(value, places=4):
    return round(value, places) if isinstance(value, float) else value


def to_result(rank, row):
    factors = row.get("factors") or {}
    legs = row.get("leg_scores") or {}
    contributions = row.get("leg_contributions") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "name": row.get("name"),
        "sector": row.get("sector"),
        "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "eligibility": row["eligibility"],
        "current_membership": bool(row.get("current_membership")),
        "percentile": round(row["percentile"], 2) if row.get("percentile") is not None else None,
        "composite_z": round(row["score"], 4),
        "coverage": row.get("coverage"),
        # Same key the shared screen table reads on every other screen, so a row here is
        # legible beside a momentum or quality-value row without special casing.
        "structural_score": row.get("structural_score"),
        "tactical_score": None,
        "data_coverage": row.get("data_coverage"),
        "market_cap": row.get("market_cap"),
        "price": _rounded(row.get("price"), 2),
        "median_dollar_volume_60d": _rounded(row.get("median_dollar_volume_60d"), 0),
        "legs": {leg: {
            "z": None if legs.get(leg) is None else round(legs[leg], 4),
            "weight": SWING_WEIGHTS[leg],
            "contribution": round(contributions.get(leg, 0.0), 4),
            "applied": legs.get(leg) is not None,
        } for leg in SWING_WEIGHTS},
        "dropped_legs": row.get("dropped_legs", []),
        "reversal_cost_gated": row.get("reversal_cost_gated", False),
        "short_interest": row.get("short_interest"),
        "pead_status": factors.get("pead_status"),
        "raw_factors": {key: _rounded(value) for key, value in factors.items()
                        if key != "pead_status" and value is not None},
        "reason_codes": row.get("reason_codes", []),
    }


def payload(results, scored, generated_at):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at,
        "status": "success",
        "horizon": HOLDING_HORIZON,
        "weights": SWING_WEIGHTS,
        "subfactors": {leg: [name for name, _ in subfactors]
                       for leg, subfactors in SWING_SUBFACTORS.items()},
        "evidence": SWING_EVIDENCE,
        "negative_screen": SHORT_INTEREST_EVIDENCE,
        "decay_haircut": DECAY_HAIRCUT,
        "thresholds": DEFAULT_CONFIG,
        "leg_coverage": leg_coverage(scored),
        "scored_count": len(scored),
        "eligible_count": sum(1 for row in scored if row["eligibility"]),
        "suppressed_count": sum(1 for row in scored
                                if (row.get("short_interest") or {}).get("suppressed")),
        "published_count": len(results),
        "published_suppressed_count": sum(1 for row in results
                                          if (row.get("short_interest") or {}).get("suppressed")),
        "coverage_note": (
            "Cross-sectional ranks over the scored universe, recomputed every refresh. Effect "
            "sizes quoted per leg are the published gross, pre-cost, pre-decay figures; apply "
            "the McLean-Pontiff haircuts before reading them as live expectations. Legs a row "
            "cannot fill are dropped and the remaining weights renormalized, so read `coverage` "
            "beside every score."),
        "results": results,
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code,
        "horizon": HOLDING_HORIZON, "weights": SWING_WEIGHTS, "evidence": SWING_EVIDENCE,
        "negative_screen": SHORT_INTEREST_EVIDENCE, "decay_haircut": DECAY_HAIRCUT,
        "results": [],
    }


def run():
    generated_at = datetime.now(timezone.utc).isoformat()
    universe = universe_rows()
    if not universe:
        LOG.warn("Swing screen: no scored universe to rank, skipping")
        return None

    rows = build_rows(universe)
    if not rows:
        result = unavailable("INSUFFICIENT_PRICE_HISTORY", generated_at)
        save_json(OUTPUT, result)
        return result

    scored = swing_scores(rows, current_members=previous_members(load_json(OUTPUT)))
    results = [to_result(rank + 1, row) for rank, row in enumerate(publishable(scored))]
    result = payload(results, scored, generated_at)
    save_json(OUTPUT, result)
    LOG.info(f"Swing screen: scored {len(scored)} tickers "
             f"({result['eligible_count']} eligible, {result['suppressed_count']} suppressed on "
             f"short interest), published {len(results)}")
    return result


if __name__ == "__main__":
    run()
