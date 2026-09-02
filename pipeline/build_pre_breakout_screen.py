"""Publishes the pre-breakout composite screen to screens/pre-breakout.json.

pre_breakout_signals.py holds every formula, weight, gate and citation; this script is the
part that assembles real inputs for it and writes the file. Like the swing and quality-value
screens, this costs no network call: every input already sits on disk from the same run --
the backtest cache's closes/volumes/statements fetch_advisor.py already warmed, the EDGAR
point-in-time fundamentals store edgar_sue.py and earnings_acceleration.py read, the
observation store the short-interest leg reads, and the insider-activity block
fetch_advisor.py already computed and published on every research/portfolio row.

This is a Stage-0 research filter, not a validated strategy. It is registered on the
prospective clock in pipeline/validation/harness_freeze.json -- see payload()'s
coverage_note. See docs/PRE-BREAKOUT-SCREEN-RESEARCH.md for the design brief this
implements, including which of the composite's legs are Tier A/B (well-evidenced) versus
Tier C (the volatility_contraction subfactor -- an unvalidated hypothesis, weighted lowest
inside its own leg, published so the prospective clock can say whether it earns its place).
"""

import json
import os
from datetime import datetime, timezone

from common import LOG, load_json, save_json
from earnings_acceleration import acceleration_for as default_acceleration_for
from edgar_sue import announcement_age_trading_days, sue_for
from fundamentals_extended import derive_margins, derive_roa_delta
from peer_groups import peer_group
from pit_store import history as pit_history
import pre_breakout_pit_store
from pre_breakout_signals import (DEFAULT_CONFIG, PRE_BREAKOUT_EVIDENCE, PRE_BREAKOUT_SUBFACTORS,
                                  PRE_BREAKOUT_WEIGHTS, STAGE_THRESHOLDS, SUBWEIGHTS_BY_LEG,
                                  leg_coverage, legs_resolved_distribution, pre_breakout_scores,
                                  short_interest_change, signed_path_smoothness,
                                  volatility_contraction_score)
from price_archive import load_series as archive_series_for
from research_screens_v2 import industry_relative_returns, momentum_factors, momentum_path_smoothness
from screen_inputs import (OBSERVATIONS, backtest_entry, latest_observations,
                           median_dollar_volume, universe_rows, with_current_price)

SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "pre-breakout-v0.1.0"
CONFIG_VERSION = "screens-v2.0.0"
OUTPUT = "screens/pre-breakout.json"
# Same ranked-head convention as the swing and quality-value screens: publish the head with
# both counts stated rather than shipping the whole ~900-name universe.
PUBLISH_LIMIT = 300


def _rounded(value, places=4):
    return round(value, places) if isinstance(value, float) else value


def _price_rows(dates, closes):
    return [{"date": day, "adjusted_close": close} for day, close in zip(dates, closes)]


def _read_observation_rows(path=None):
    """The whole observation store, read once. pit_store.history() re-reads the file on
    every call unless handed pre-read rows; reading it once here and passing the result into
    every ticker's history() call is the difference between one file read and ~900 of them.
    """
    path = path or OBSERVATIONS
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def resolve_sue(ticker, as_of, sessions, config, sue_for=sue_for):
    """This ticker's standardized unexpected earnings, or None once its drift window has
    closed. Same construction and reasoning as build_swing_screen.py's resolve_sue: dated by
    the earnings *release* datetime (Form 8-K Item 2.02), aged in trading sessions on the
    ticker's own calendar, never falling back to the filing date when the release does not
    resolve.
    """
    sue = sue_for(ticker, as_of)
    if not sue:
        return None
    age = announcement_age_trading_days(sue.get("release_datetime"), sessions)
    if age is None or age > config["sue_window_trading_days"]:
        return None
    return sue


def build_rows(universe, entry_for=None, observations=None, observation_rows=None, as_of=None,
               archive_for=None, acceleration_for=default_acceleration_for, sue_resolver=resolve_sue,
               config=None):
    """One pre-score row per ticker: gates, observed solvency fields, and every raw subfactor
    pre_breakout_signals.py's composite needs.

    Two passes, same reason build_swing_screen.py's build_rows is two passes: industry-
    relative momentum is a leave-one-out peer benchmark and cannot be computed until every
    row's own momentum_12_1 has been read.

    ``observations`` is the {ticker: values} map from screen_inputs.latest_observations() --
    today's latest reading, used for the distress gate and as a market-cap fallback, matching
    build_swing_screen.py's own use of the same store for the same purpose. ``observation_rows``
    is the separate, raw, unaggregated observation history short_interest_change needs (see
    _read_observation_rows) -- distinct from ``observations`` because that leg needs more than
    just the latest value.
    """
    entry_for = entry_for or backtest_entry
    archive_for = archive_for or archive_series_for
    config = config or DEFAULT_CONFIG
    observation_rows = observation_rows if observation_rows is not None else _read_observation_rows()
    observed_latest = observations if observations is not None else latest_observations()
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()

    prepared = []
    for row in universe:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        entry = with_current_price(entry_for(ticker) or {}, row.get("price"),
                                   row.get("last_polled_at")) or {}
        dates, closes = entry.get("dates") or [], entry.get("closes") or []
        volumes = entry.get("volumes") or []
        if not closes or not dates:
            continue
        prepared.append((row, ticker, entry, dates, closes, volumes))

    rows = []
    for row, ticker, entry, dates, closes, volumes in prepared:
        prices = _price_rows(dates, closes)
        momentum = momentum_factors(prices, as_of=as_of)
        if momentum is None:
            continue
        income, balance = entry.get("income"), entry.get("balance")
        margins = derive_margins(income) if income else {}
        roa_delta = derive_roa_delta(income, balance) if income and balance else None
        earnings_accel = (acceleration_for(ticker, as_of) or {}).get("acceleration")
        revenue_accel = (acceleration_for(ticker, as_of, concept="revenue") or {}).get("acceleration")
        sue = sue_resolver(ticker, as_of, dates, config)
        smoothness = momentum_path_smoothness(prices, as_of=as_of)
        signed_smoothness = signed_path_smoothness(smoothness, momentum.get("momentum_12_1"))
        archive = archive_for(ticker) or {}
        contraction = volatility_contraction_score(closes, archive.get("highs"), archive.get("lows"))
        si_history = pit_history(ticker, "short_percent_of_float", rows=observation_rows)
        si_change = short_interest_change(si_history, as_of)
        observed = observed_latest.get(ticker) or {}
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
            # industry_relative_returns() reads momentum_12_1 off the row directly, not from
            # raw_factors -- filled into raw_factors below, after the peer pass.
            "momentum_12_1": momentum.get("momentum_12_1"),
            "observed": {"altman_z": observed.get("altman_z"),
                        "interest_coverage": observed.get("interest_coverage")},
            "raw_factors": {
                "earnings_acceleration": earnings_accel,
                "revenue_acceleration": revenue_accel,
                "roa_delta": roa_delta,
                "margin_turn": margins.get("operating_margin_trend"),
                "standardized_unexpected_earnings": (sue or {}).get("sue"),
                "momentum_12_1": momentum.get("momentum_12_1"),
                "path_smoothness": signed_smoothness,
                "industry_relative_momentum": None,
                "volatility_contraction": contraction,
                "insider_cluster_score": (row.get("insider_activity") or {}).get("score_points"),
                "short_interest_change": si_change,
            },
        })

    peer_returns = industry_relative_returns(rows)
    for row in rows:
        relative = (peer_returns.get(row["ticker"]) or {}).get("industry_relative_momentum")
        row["raw_factors"]["industry_relative_momentum"] = relative
    return rows


def previous_members(screen):
    return {row["ticker"]: True for row in (screen or {}).get("results", [])
            if row.get("current_membership") and row.get("ticker")}


def to_result(rank, row):
    return {
        "rank": rank, "ticker": row["ticker"], "name": row.get("name"), "sector": row.get("sector"),
        "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "eligibility": row["eligibility"],
        "current_membership": bool(row.get("current_membership")),
        "percentile": round(row["percentile"], 2) if row.get("percentile") is not None else None,
        "composite_z": _rounded(row.get("score")),
        # Coiling (about to move, not yet) vs. breaking_out/extended (already moving) --
        # see pre_breakout_signals.classify_stage. Read by ResearchScreen.jsx's shared table
        # the same way build_quality_value_screen.py's own "classification" field already is.
        "classification": row.get("classification"),
        "coverage": row.get("coverage"),
        "legs_resolved": row.get("legs_resolved"),
        "legs_declared": row.get("legs_declared"),
        "renormalization_factor": row.get("renormalization_factor"),
        # Same keys the shared screen table reads on every other screen (momentum.json,
        # swing.json), so a row here is legible beside them without special-casing.
        "structural_score": row.get("structural_score"),
        "tactical_score": None,
        "data_coverage": row.get("data_coverage"),
        "market_cap": row.get("market_cap"),
        "price": _rounded(row.get("price"), 2),
        "median_dollar_volume_60d": _rounded(row.get("median_dollar_volume_60d"), 0),
        "sub_scores": row.get("sub_scores"),
        "raw_factors": {key: _rounded(value) for key, value in (row.get("raw_factors") or {}).items()
                        if value is not None},
        "reason_codes": row.get("reason_codes", []),
    }


def publishable(scored):
    return sorted((row for row in scored if row.get("eligibility")),
                 key=lambda row: row["score"], reverse=True)[:PUBLISH_LIMIT]


def payload(results, scored, generated_at, config):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at,
        "status": "success",
        "weights": PRE_BREAKOUT_WEIGHTS,
        "subfactor_weights": SUBWEIGHTS_BY_LEG,
        "subfactors": {leg: [name for name, _negate in subfactors]
                       for leg, subfactors in PRE_BREAKOUT_SUBFACTORS.items()},
        "evidence": PRE_BREAKOUT_EVIDENCE,
        "thresholds": config,
        "stage_thresholds": STAGE_THRESHOLDS,
        "stage_note": (
            "`classification` (coiling / breaking_out / extended / unclassified) is a "
            "derived read of two already-scored subfactors (momentum_12_1, "
            "volatility_contraction), published so a reader can tell whether a row's score "
            "came from a name that hasn't moved yet versus one already in motion -- the "
            "composite score alone cannot distinguish the two. It is not a fourth leg: it "
            "does not feed the composite and carries no weight of its own. See "
            "pre_breakout_signals.classify_stage."
        ),
        "leg_coverage": leg_coverage(scored),
        "legs_resolved": legs_resolved_distribution(scored, config),
        "scored_count": len(scored),
        "eligible_count": sum(1 for row in scored if row["eligibility"]),
        "published_count": len(results),
        "coverage_note": (
            "Cross-sectional ranks over the scored universe, recomputed every refresh. Each "
            "of the 3 named legs (fundamental_inflection, momentum_rs, flow_sentiment) is "
            "itself a weighted blend of subfactors, renormalized over whichever subfactors "
            "resolved on a row; the composite is then the equal-weighted blend of whichever "
            "legs resolved. A row resolving fewer than "
            f"{config['minimum_legs_resolved']} of 3 legs is excluded from the ranking "
            "entirely -- read `coverage` and `legs_resolved` beside every score. This model "
            "has no out-of-sample record: it is registered in "
            "pipeline/validation/harness_freeze.json (additional_models, pre-breakout-v0.1.0) "
            "on a prospective clock and should be read as a research filter until that clock "
            "reports. The momentum_rs leg's volatility_contraction subfactor is Tier C / "
            "weakest-evidence per docs/PRE-BREAKOUT-SCREEN-RESEARCH.md -- weighted lowest "
            "inside its own leg (see pre_breakout_signals.MOMENTUM_RS_SUBWEIGHTS) and the "
            "first candidate the clock is expected to drop or reweight."
        ),
        "results": results,
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "config_version": CONFIG_VERSION, "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code,
        "weights": PRE_BREAKOUT_WEIGHTS, "evidence": PRE_BREAKOUT_EVIDENCE, "results": [],
    }


def run():
    generated_at = datetime.now(timezone.utc).isoformat()
    universe = universe_rows()
    if not universe:
        LOG.warn("Pre-breakout screen: no scored universe to rank, skipping")
        return None

    config = DEFAULT_CONFIG
    rows = build_rows(universe, config=config)
    if not rows:
        result = unavailable("INSUFFICIENT_PRICE_HISTORY", generated_at)
        save_json(OUTPUT, result)
        return result

    existing = load_json(OUTPUT)
    scored = pre_breakout_scores(rows, current_members=previous_members(existing), config=config)
    results = [to_result(rank + 1, row) for rank, row in enumerate(publishable(scored))]
    result = payload(results, scored, generated_at, config)
    save_json(OUTPUT, result)
    # Point-in-time capture of the composite and its subfactors, for future rank-IC and
    # per-metric attribution validation - starts recording today, never reconstructs
    # history. See pre_breakout_pit_store.py and validation/pre_breakout_ic.py.
    try:
        pre_breakout_pit_store.append_snapshot(results)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"pre_breakout_pit_store snapshot failed ({type(exc).__name__}): {exc}")
    LOG.info(f"Pre-breakout screen: scored {len(scored)} tickers "
             f"({result['eligible_count']} eligible), published {len(results)}")
    return result


if __name__ == "__main__":
    run()
