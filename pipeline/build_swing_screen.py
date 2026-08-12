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
from edgar_sue import ANNOUNCEMENT_ANCHOR_NOTE, announcement_age_trading_days, sue_for
from peer_groups import peer_group
from screen_inputs import (backtest_entry, latest_observations, median_dollar_volume,
                           universe_rows, with_current_price)
from swing_signals import (BASELINE_VARIANT, DECAY_HAIRCUT, DEFAULT_CONFIG, HOLDING_HORIZON,
                           SHORT_INTEREST_EVIDENCE, SWING_EVIDENCE, SWING_SUBFACTORS,
                           SWING_VARIANTS, SWING_WEIGHTS, capacity_profile, leg_coverage,
                           legs_resolved_distribution, pead_anchor_diagnostic, sector_cap_log,
                           swing_factors, swing_scores, trailing_dollar_volume)

SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "swing-v1.1.0"
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


def resolve_sue(ticker, as_of, sessions, sue_for=sue_for):
    """The row's standardized unexpected earnings, with its drift window aged in sessions.

    Reads the EDGAR point-in-time store rather than the advisor snapshot's `earnings_surprise`
    field, which is 0/839 populated and is in any case a different construct - see
    edgar_sue's module docstring. Ages the window on the ticker's own trading calendar so a
    holiday or a stale cache cannot quietly reopen a closed window.

    Spec amendment SA-2026-08-12-02: the window is aged from the earnings *release* datetime,
    which comes from Form 8-K Item 2.02 and is independent of the 10-Q filing date. A row
    whose release does not resolve gets no age, and pead_factor drops it. Nothing here
    substitutes the filing date for the missing anchor.
    """
    sue = sue_for(ticker, as_of)
    if not sue:
        return None
    return {**sue, "age_trading_days": announcement_age_trading_days(
        sue.get("release_datetime"), sessions)}


def build_rows(universe, entry_for=None, observations=None, as_of=None, sue_resolver=resolve_sue):
    """One pre-score row per ticker: its context, plus every raw swing subfactor."""
    entry_for = entry_for or backtest_entry
    observations = observations if observations is not None else latest_observations()
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
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
        sue = sue_resolver(ticker, as_of, entry.get("dates") or [])
        group_id, group_label = peer_group(row)
        rows.append({
            "ticker": ticker, "name": row.get("name"), "sector": row.get("sector"),
            "peer_group": group_id, "peer_group_label": group_label,
            "price": row.get("price") or closes[-1],
            "market_cap": row.get("market_cap") or observed.get("market_cap"),
            "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
            # The participation cap reads a trailing 20-session mean, not the 60-day median
            # the eligibility screens use. See swing_signals.trailing_dollar_volume for why
            # the two are kept apart rather than one standing in for the other.
            "adv_20d_dollar_volume": trailing_dollar_volume(closes, volumes),
            "history_sessions": len(closes),
            "structural_score": row.get("score"),
            "data_coverage": row.get("data_coverage"),
            "short_percent_of_float": row.get("short_percent_of_float") or observed.get("short_percent_of_float"),
            "days_to_cover": row.get("days_to_cover") or observed.get("days_to_cover"),
            "factors": swing_factors(row, closes=closes, volumes=volumes, sue=sue),
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
        # The zero-filled divisor superseded by spec amendment SA-2026-08-12-04, published for
        # comparison against anything computed before renormalization returned. Never ranked on.
        "composite_z_zero_filled": round(row.get("score_zero_filled", 0.0), 4),
        "coverage": row.get("coverage"),
        "legs_resolved": row.get("legs_resolved"),
        "legs_declared": row.get("legs_declared"),
        "sector_capped": bool(row.get("sector_capped")),
        "sector_trim": row.get("sector_trim"),
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
            "declared_weight": SWING_WEIGHTS[leg],
            # What the leg was actually worth on this row after renormalizing across the legs
            # that resolved. Equal to the declared weight only on a full row.
            "effective_weight": (round(SWING_WEIGHTS[leg] * (row.get("renormalization_factor") or 0), 4)
                                 if legs.get(leg) is not None else 0.0),
            "contribution": round(contributions.get(leg, 0.0), 4),
            "applied": legs.get(leg) is not None,
        } for leg in SWING_WEIGHTS},
        "dropped_legs": row.get("dropped_legs", []),
        "reversal_cost_gated": row.get("reversal_cost_gated", False),
        "short_interest": row.get("short_interest"),
        "pead_status": factors.get("pead_status"),
        "pead_detail": {key: factors.get(key) for key in
                        ("pead_basis", "pead_period_end", "pead_announced_on",
                         "pead_release_datetime", "pead_release_source",
                         "pead_release_precision", "pead_anchor_status", "pead_filed",
                         "pead_expectation_model", "pead_drift_term",
                         "pead_age_trading_days") if factors.get(key) is not None},
        "raw_factors": {key: _rounded(value) for key, value in factors.items()
                        if not key.startswith("pead_") and value is not None},
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
        "legs_resolved": legs_resolved_distribution(scored),
        "pead_anchor_diagnostic": pead_anchor_diagnostic(scored),
        "sector_concentration": {
            "cap": DEFAULT_CONFIG["sector_concentration_cap"],
            "applied": "after ranking, by trimming the lowest-scoring names in the "
                       "over-represented sector",
            "trims": sector_cap_log(scored),
            "trimmed_count": len(sector_cap_log(scored)),
        },
        "registered_variants": {key: {"id": spec["id"], "label": spec["label"],
                                      "weights": spec["weights"],
                                      "is_frozen_baseline": spec["is_frozen_baseline"]}
                                for key, spec in SWING_VARIANTS.items()},
        "published_variant": BASELINE_VARIANT,
        "pead_source": {
            "store": "pipeline/data/pit/fundamentals (EDGAR as-filed XBRL)",
            "construct": "seasonal random walk with drift, standardized by the firm's own "
                         "history of seasonal differences (Foster 1977; Foster, Olsen & "
                         "Shevlin 1984; Bernard & Thomas 1989, 1990)",
            "announcement_anchor": "earnings_release_datetime_8k_item_202",
            "announcement_anchor_store": "pipeline/data/pit/earnings_releases.jsonl "
                                         "(EDGAR Form 8-K Item 2.02)",
            "announcement_anchor_note": ANNOUNCEMENT_ANCHOR_NOTE,
            "replaces": "advisor snapshot earnings_surprise (0/839 populated, and a "
                        "four-quarter weighted average of percent surprise rather than the "
                        "most-recent standardized surprise PEAD is a claim about)",
        },
        "cost_model": capacity_profile(scored),
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
            "the McLean-Pontiff haircuts before reading them as live expectations, and read "
            "`cost_model` for what the traded book costs to turn over. A leg a row cannot fill "
            "is renormalized away and the legs that did resolve carry their declared weight, "
            "so read `coverage` and `legs_resolved` beside every score; a row resolving fewer "
            "than three of five legs is excluded from the ranking entirely. This model has no "
            "out-of-sample record: it is registered in pipeline/validation/harness_freeze.json "
            "on the prospective clock that starts 2026-09-01 and should be read as a research "
            "filter until that clock reports."),
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
