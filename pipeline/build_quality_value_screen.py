"""Publishes the quality-value research screen from prospectively collected valuations.

Like the tactical sleeve, the scoring contract already existed in ``research_screens_v2``
(``robust_value_score`` and ``classify_quality_value``) and the shadow report already listed
the sleeve; the builder that connects them did not, so the published file stayed pinned to a
hand-written ``POINT_IN_TIME_VALUATION_HISTORY_NOT_COLLECTED`` placeholder.

That reason code was true when it was written and is not any more: ``pit_store`` has been
appending observed valuations since the store opened. It is deliberately not true in reverse
either - Yahoo serves restated multiples with no as-reported history, so "cheap against its
own history" can only ever be answered from observations this pipeline recorded itself.
Until a ticker has ``minimum_history_observations`` of them, it is published with an explicit
``INSUFFICIENT_HISTORICAL_DATA`` flag and held ineligible rather than scored against a
history too short to mean anything.
"""

from datetime import datetime, timezone

import pit_store
from canonical_metrics import applicability_for
from common import LOG, load_json, save_json
from peer_groups import peer_group
from research_screens_v2 import classify_quality_value, historical_percentile, robust_value_score

# ``lower_is_cheaper`` is the direction that makes a metric a bargain, not its sign. A
# falling multiple is cheap; a falling free-cash-flow yield is not.
VALUATION_METRICS = {
    "forward_pe": True,
    "ev_to_ebitda": True,
    "ev_to_sales": True,
    "price_to_book": True,
    "free_cash_flow_yield": False,
}
HISTORY_YEARS = 3
DISTRESS_ALTMAN_Z = 1.8


def _quality_score(entry):
    structural = (entry.get("analysis_v2") or {}).get("structural") or {}
    components = entry.get("components") or {}
    for value in (structural.get("effective_score"), components.get("fundamentals"),
                  entry.get("score")):
        if value is not None:
            return float(value)
    return None


def _applicability(entry):
    profile = (entry.get("analysis_v2") or {}).get("applicability_profile") or "general"
    return {metric: 0 if applicability_for(metric, profile)["status"] == "suppressed" else 1
            for metric in VALUATION_METRICS}


def build_metrics(entry, histories):
    """``{metric: {history, current, lower_is_cheaper}}`` for one ticker."""
    stored = histories.get(str(entry.get("ticker") or "").upper()) or {}
    metrics = {}
    for metric, lower_is_cheaper in VALUATION_METRICS.items():
        current = entry.get(metric)
        history = [row["value"] for row in stored.get(metric) or []]
        if current is None and not history:
            continue
        metrics[metric] = {"history": history, "current": current,
                           "lower_is_cheaper": lower_is_cheaper}
    return metrics


def observation_depth(metrics, applicability):
    """Longest applicable own-history run, which is what the minimum actually gates on."""
    lengths = [len(item["history"]) for metric, item in metrics.items()
               if applicability.get(metric, 0)]
    return max(lengths) if lengths else 0


def peer_value_scores(rows):
    """Cheapness against same-profile peers today, blended across applicable metrics."""
    by_group = {}
    for row in rows:
        by_group.setdefault(row["peer_group"][0], []).append(row)
    scores = {}
    for members in by_group.values():
        for row in members:
            percentiles = []
            for metric, lower_is_cheaper in VALUATION_METRICS.items():
                if not row["applicability"].get(metric, 0):
                    continue
                current = (row["metrics"].get(metric) or {}).get("current")
                peers = [value for other in members
                         if (value := (other["metrics"].get(metric) or {}).get("current")) is not None]
                # One company is not a peer group; a lone member would score its own
                # 100th percentile against itself.
                if current is None or len(peers) < 2:
                    continue
                percentile = historical_percentile(peers, current, lower_is_cheaper)
                if percentile is not None:
                    percentiles.append(percentile)
            scores[row["ticker"]] = (round(sum(percentiles) / len(percentiles), 4)
                                     if percentiles else None)
    return scores


def collect(universe, histories):
    """One row per ticker. ``research`` and ``portfolio_coverage`` overlap, and a company
    listed in both is one company -- scoring it twice would give it two entries competing
    for the same sleeve.
    """
    rows, seen = [], set()
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker or ticker in seen:
            continue
        metrics = build_metrics(entry, histories)
        if not metrics:
            continue
        seen.add(ticker)
        rows.append({
            "ticker": ticker, "metrics": metrics, "applicability": _applicability(entry),
            "peer_group": peer_group(entry), "quality_score": _quality_score(entry),
            "confidence": entry.get("confidence"),
            "altman_z": entry.get("altman_z"),
            "estimate_detail": entry.get("estimate_detail") or {},
        })
    return rows


def score_universe(rows, minimum_observations, weights):
    peers = peer_value_scores(rows)
    scored = []
    for row in rows:
        own_history_score, raw = robust_value_score(row["metrics"], row["applicability"])
        depth = observation_depth(row["metrics"], row["applicability"])
        sufficient = depth >= minimum_observations
        peer_score = peers.get(row["ticker"])
        detail = row["estimate_detail"]
        distressed = (row["altman_z"] is not None
                      and float(row["altman_z"]) < DISTRESS_ALTMAN_Z)
        classification, reasons = classify_quality_value(
            own_history_score, peer_score, row["quality_score"],
            revision_current_year=detail.get("eps_revision_30d_pct"),
            revision_next_year=detail.get("revision_breadth_30d"),
            revision_acceleration=detail.get("net_upgrades_90d"),
            distressed=distressed, minimum_history=sufficient,
        )
        parts = {"own_history_weight": own_history_score, "peer_value_weight": peer_score,
                 "quality_weight": row["quality_score"]}
        available = {key: value for key, value in parts.items() if value is not None}
        total_weight = sum(weights.get(key, 0) for key in available)
        composite = (round(sum(weights.get(key, 0) * value
                               for key, value in available.items()) / total_weight, 4)
                     if total_weight else None)
        scored.append({
            "ticker": row["ticker"], "peer_group": row["peer_group"][1],
            "quality_value_score": composite, "own_history_score": own_history_score,
            "peer_value_score": peer_score, "quality_score": row["quality_score"],
            "classification": classification, "reason_codes": reasons,
            "observations": depth, "minimum_observations": minimum_observations,
            "confidence": row["confidence"], "metric_percentiles": raw,
            "eligibility": sufficient and classification == "actionable value",
        })
    return sorted(scored, key=lambda row: (row["quality_value_score"] is not None,
                                           row["quality_value_score"] or 0), reverse=True)


def to_result(rank, row):
    return {"rank": rank, **row}


def run():
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    models = load_json("research_models.json", from_config=True) or {}
    config = models.get("quality_value") or {}
    minimum_observations = config.get("minimum_history_observations", 12)
    weights = {"own_history_weight": config.get("own_history_weight", 0.5),
               "peer_value_weight": config.get("peer_value_weight", 0.15),
               "quality_weight": config.get("quality_weight", 0.35)}
    header = {
        "schema_version": "1.0.0",
        "model_version": config.get("model_version", "quality-value-v2.0.0"),
        "config_version": models.get("config_version", "screens-v2.0.0"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_history_observations": minimum_observations,
    }
    if not universe:
        LOG.warn("Quality-value screen: no published universe to score, skipping")
        result = {**header, "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE",
                  "results": []}
        save_json("screens/quality-value.json", result)
        return result

    histories = pit_store.valuation_histories(
        years=HISTORY_YEARS, days_per_year=365, metrics=tuple(VALUATION_METRICS))
    rows = collect(universe, histories)
    scored = score_universe(rows, minimum_observations, weights)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    eligible = sum(1 for row in results if row["eligibility"])
    deepest = max((row["observations"] for row in results), default=0)
    if not results:
        result = {**header, "status": "unavailable",
                  "reason_code": "POINT_IN_TIME_VALUATION_HISTORY_NOT_COLLECTED", "results": []}
    elif deepest < minimum_observations:
        # Collection is running and the screen is scored; the own-history percentiles the
        # sleeve is built on are simply not seasoned yet. Reporting the depth reached makes
        # the wait a countdown instead of an indefinite placeholder.
        result = {**header, "status": "unavailable",
                  "reason_code": "POINT_IN_TIME_VALUATION_HISTORY_TOO_SHORT",
                  "observations_collected": deepest, "results": results}
    else:
        result = {**header, "status": "success", "observations_collected": deepest,
                  "results": results}
    save_json("screens/quality-value.json", result)
    LOG.info(f"Quality-value screen: scored {len(results)} tickers ({eligible} eligible, "
             f"deepest own history {deepest}/{minimum_observations} observations)")
    return result


if __name__ == "__main__":
    run()
