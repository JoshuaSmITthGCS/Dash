"""Publishes the "quality at valuation lows" screen.

research_screens_v2 has carried this screen's formulas - `robust_value_score`,
`classify_quality_value` - and their tests since the screen was designed. What never existed
was a script to feed them real inputs, so public/data/screens/quality-value.json shipped as a
hand-written placeholder reading POINT_IN_TIME_VALUATION_HISTORY_NOT_COLLECTED. This is that
script.

The four inputs the classifier wants, and where each comes from:

  own-history cheapness   valuation_history.multiple_series - a daily multiple series rebuilt
                          from the backtest cache's closes and quarterly statements, with each
                          statement withheld until its filing deadline had passed
  peer cheapness          the published sector valuation percentile, or the cross-sectional
                          valuation category score where no peer percentile was constructed
  business quality        the published profitability, financial-health, accounting-quality
                          and capital-allocation category scores
  forward revisions       the published 30-day estimate revision magnitude and breadth,
                          ranked across the cross-section

The own-history window is only as deep as the cached statements reach. Companies below
valuation_history.MINIMUM_HISTORY_SESSIONS are still published, still ranked on peer value and
quality, and classified "insufficient historical data" with an explicit reason code - the
screen says what it knows about them rather than dropping them or pretending to a percentile
it cannot support.
"""

from datetime import datetime, timezone

from common import LOG, load_json, save_json
from peer_groups import peer_group
from research_screens_v2 import classify_quality_value, robust_value_score
from screen_inputs import (backtest_entry, cross_sectional_percentiles, latest_observations,
                           median_dollar_volume, universe_rows, with_current_price)
from valuation_history import (APPLICABILITY, MINIMUM_FUNDAMENTAL_STEPS,
                               MINIMUM_HISTORY_SESSIONS, REPORTING_LAG_DAYS, applicable_metrics,
                               multiple_series, profile_for)

QUALITY_WEIGHTS = {"profitability": .35, "financial_health": .30,
                   "accounting_quality": .20, "capital_allocation": .15}
# The whole scored cross-section is around 900 names. Publishing every one of them costs the
# better part of a megabyte over a phone connection to deliver a table nobody scrolls to the
# end of, so the file carries the ranked head and states both numbers.
PUBLISH_LIMIT = 300
# Altman below the distress zone, or a company that cannot cover its interest bill out of
# operating profit, is a value trap by the screen's own definition - not a valuation low.
DISTRESS_ALTMAN_Z = 1.8
DISTRESS_INTEREST_COVERAGE = 1.0


def quality_score(categories):
    """Weighted mean of the published quality categories, ignoring valuation and growth.

    Valuation is the other axis of this screen and must not appear on both sides of it;
    growth is a forecast, and the classifier gates on revisions for that.
    """
    present = {key: value for key, value in (categories or {}).items()
               if key in QUALITY_WEIGHTS and isinstance(value, (int, float))}
    weight = sum(QUALITY_WEIGHTS[key] for key in present)
    if not weight:
        return None
    return sum(value * QUALITY_WEIGHTS[key] for key, value in present.items()) / weight


def peer_value(row):
    """Peer cheapness on 0-100, higher is cheaper, plus which basis produced it."""
    percentile = row.get("sector_valuation_percentile")
    if isinstance(percentile, (int, float)):
        return float(percentile), "sector_valuation_percentile"
    categories = (row.get("fundamental_categories") or {})
    value = categories.get("valuation")
    if isinstance(value, (int, float)):
        return float(value), "cross_sectional_valuation_score"
    return None, None


def is_distressed(observed):
    """Distress from the point-in-time store's own solvency readings, never from cheapness."""
    altman, coverage = observed.get("altman_z"), observed.get("interest_coverage")
    if isinstance(altman, (int, float)) and altman < DISTRESS_ALTMAN_Z:
        return True
    return isinstance(coverage, (int, float)) and coverage < DISTRESS_INTEREST_COVERAGE


def build_rows(universe, observations, entry_for=backtest_entry):
    """One row per ticker with its own-history cheapness computed where history allows."""
    rows = []
    for row in universe:
        ticker = row.get("ticker")
        if not ticker or row.get("is_etf"):
            continue
        observed = observations.get(ticker) or {}
        entry = with_current_price(entry_for(ticker) or {}, row.get("price"),
                                   row.get("last_polled_at")) or {}
        margin = row.get("profit_margin")
        profile = profile_for({**row, "profit_margin": observed.get("profit_margin")
                               if margin is None else margin})
        series = multiple_series(entry) if entry else {}
        applicable = applicable_metrics(profile, series)
        own_history, per_metric = robust_value_score(
            {name: series[name] for name in applicable}, applicable) if applicable else (None, {})
        sessions = max((series[name]["sessions"] for name in applicable), default=0)
        peer_score, peer_basis = peer_value(row)
        group_id, group_label = peer_group(row)
        closes, volumes = entry.get("closes") or [], entry.get("volumes") or []
        rows.append({
            "ticker": ticker, "sector": row.get("sector"),
            "peer_group": group_id, "peer_group_label": group_label, "business_profile": profile,
            "market_cap": row.get("market_cap") or observed.get("market_cap"),
            "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
            "structural_score": row.get("score"),
            "data_coverage": ((row.get("score_variants") or {}).get("champion") or {}).get("data_coverage"),
            "own_history_score": own_history, "own_history_sessions": sessions,
            "own_history_steps": max((series[name]["fundamental_steps"] for name in applicable),
                                     default=0),
            "own_history_start": min((series[name]["start"] for name in applicable), default=None),
            "applicable_metrics": applicable,
            "metric_percentiles": {name: (None if value is None else round(value, 2))
                                   for name, value in per_metric.items()},
            "peer_value_score": peer_score, "peer_value_basis": peer_basis,
            "quality_score": quality_score(row.get("fundamental_categories")),
            "distressed": is_distressed(observed),
            "revision_magnitude_raw": (row.get("estimate_detail") or {}).get("eps_revision_30d_pct"),
            "revision_breadth_raw": (row.get("estimate_detail") or {}).get("revision_breadth_30d"),
        })
    return rows


def attach_revision_percentiles(rows):
    """Rank the two revision readings across the cross-section onto the 0-100 the gate expects.

    `classify_quality_value` treats a revision score at or below 20 as deterioration, i.e. the
    bottom fifth of the market - a percentile, not a raw growth rate, so it has to be ranked
    here rather than passed through.
    """
    magnitude = cross_sectional_percentiles([row["revision_magnitude_raw"] for row in rows])
    breadth = cross_sectional_percentiles([row["revision_breadth_raw"] for row in rows])
    for row, magnitude_value, breadth_value in zip(rows, magnitude, breadth):
        row["revision_current_year"] = magnitude_value
        row["revision_next_year"] = breadth_value
    return rows


def classify_rows(rows):
    for row in rows:
        classification, reasons = classify_quality_value(
            row["own_history_score"], row["peer_value_score"], row["quality_score"],
            revision_current_year=row["revision_current_year"],
            revision_next_year=row["revision_next_year"],
            revision_acceleration=None,
            distressed=row["distressed"],
            minimum_history=row["own_history_sessions"] >= MINIMUM_HISTORY_SESSIONS)
        row["classification"] = classification
        row["reason_codes"] = reasons
    return rows


def composite_percentiles(rows):
    """Rank by own-history cheapness when it exists, peer cheapness otherwise.

    Both are already 0-100 cheapness readings, so a company with a real own-history window and
    one still accumulating stay comparable; `own_history_sessions` on the row says which is
    which rather than leaving the two silently blended.
    """
    basis = [row["own_history_score"] if row["own_history_score"] is not None
             else row["peer_value_score"] for row in rows]
    for row, percentile in zip(rows, cross_sectional_percentiles(basis)):
        row["percentile"] = percentile
    return rows


def to_result(rank, row):
    return {
        "rank": rank, "ticker": row["ticker"], "sector": row.get("sector"),
        "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "business_profile": row.get("business_profile"),
        "classification": row["classification"],
        "percentile": None if row.get("percentile") is None else round(row["percentile"], 2),
        "structural_score": row.get("structural_score"),
        # This screen scores the durable axis only. The tactical column stays empty here on
        # purpose; earnings-timeliness and the matrix are where the near-term axis is scored.
        "tactical_score": None,
        "data_coverage": row.get("data_coverage"),
        "market_cap": row.get("market_cap"),
        "median_dollar_volume_60d": row.get("median_dollar_volume_60d"),
        "own_history_score": None if row["own_history_score"] is None else round(row["own_history_score"], 2),
        "own_history_sessions": row["own_history_sessions"],
        "own_history_steps": row.get("own_history_steps"),
        "own_history_start": row.get("own_history_start"),
        "peer_value_score": None if row["peer_value_score"] is None else round(row["peer_value_score"], 2),
        "peer_value_basis": row.get("peer_value_basis"),
        "quality_score": None if row["quality_score"] is None else round(row["quality_score"], 2),
        # Which multiples were used is `business_profile` plus the published weight table;
        # what they said is here, per metric, on the same cheapness scale as the composite.
        "metric_percentiles": row.get("metric_percentiles"),
        "distressed": row["distressed"],
        "eligibility": row["own_history_sessions"] >= MINIMUM_HISTORY_SESSIONS,
        "current_membership": False,
        "reason_codes": row["reason_codes"],
    }


def payload(rows, generated_at):
    with_history = [row for row in rows if row["own_history_sessions"] >= MINIMUM_HISTORY_SESSIONS]
    # Companies the screen can actually answer its own question about come first. Below them
    # sit the ones still ranked on peer value alone, so the two bases are never interleaved
    # into a single league table that hides which is which.
    ranked = sorted(rows, key=lambda row: (
        row["own_history_sessions"] < MINIMUM_HISTORY_SESSIONS,
        row.get("percentile") is None,
        -(row.get("percentile") or 0), -(row.get("quality_score") or 0), row["ticker"]))
    return {
        "schema_version": "1.0.0", "model_version": "quality-value-v2.0.0",
        "config_version": "screens-v2.0.0", "generated_at": generated_at,
        "status": "success" if rows else "unavailable",
        **({} if rows else {"reason_code": "NO_SCORED_UNIVERSE"}),
        "own_history": {
            "source": "reconstructed_from_cached_statements_and_closes",
            "minimum_sessions": MINIMUM_HISTORY_SESSIONS,
            "minimum_fundamental_steps": MINIMUM_FUNDAMENTAL_STEPS,
            "reporting_lag_days": REPORTING_LAG_DAYS,
            "tickers_with_history": len(with_history),
            "deepest_sessions": max((row["own_history_sessions"] for row in rows), default=0),
            "earliest_start": min((row["own_history_start"] for row in with_history
                                   if row.get("own_history_start")), default=None),
        },
        "quality_weights": QUALITY_WEIGHTS,
        "metric_weights_by_profile": APPLICABILITY,
        "universe_scored": len(rows), "publish_limit": PUBLISH_LIMIT,
        "coverage_note": coverage_note(rows, with_history),
        "results": [to_result(rank + 1, row) for rank, row in enumerate(ranked[:PUBLISH_LIMIT])],
    }


def coverage_note(rows, with_history):
    """One sentence stating the window actually measured, so the screen cannot overclaim."""
    if not with_history:
        return (f"No company yet has {MINIMUM_HISTORY_SESSIONS} sessions of reconstructed "
                "valuation history; every row is ranked on peer cheapness alone. The file "
                f"carries the top {PUBLISH_LIMIT} of {len(rows)} scored companies.")
    deepest = max(row["own_history_sessions"] for row in with_history)
    start = min((row["own_history_start"] for row in with_history if row.get("own_history_start")),
                default="an unrecorded date")
    return (f"Own-history cheapness is measured over each company's reconstructed multiple "
            f"series - at most {deepest} sessions, starting {start}, priced against statements "
            f"only from {REPORTING_LAG_DAYS} days after each period ended. "
            f"{len(with_history)} of {len(rows)} companies clear the "
            f"{MINIMUM_HISTORY_SESSIONS}-session minimum; the rest are ranked on peer "
            f"cheapness and quality until their own record is deep enough. The file carries "
            f"the top {PUBLISH_LIMIT} of {len(rows)} scored companies.")


def run():
    advisor = load_json("advisor.json") or {}
    universe = universe_rows(advisor)
    if not universe:
        LOG.warn("Quality-value screen: no published universe to score, skipping")
        return None
    rows = classify_rows(attach_revision_percentiles(
        build_rows(universe, latest_observations())))
    composite_percentiles(rows)
    result = payload(rows, datetime.now(timezone.utc).isoformat())
    save_json("screens/quality-value.json", result)
    LOG.info(f"Quality-value screen: scored {result['universe_scored']} tickers "
             f"({result['own_history']['tickers_with_history']} with own-history depth), "
             f"published {len(result['results'])}")
    return result


if __name__ == "__main__":
    run()
