"""Rank-turnover and score-stability diagnostics over the scored PIT store.

Built to answer one question honestly: when the published ranking reshuffles between
refreshes, is that from real changes in the underlying businesses, or from noise -- a metric
flickering null <-> present, or a normalization-regime discontinuity? See
docs/BASELINE-2026-08-06.md for why this exists: the published score spread was 6.1 points
across 40 names, so ordinary refresh noise was large relative to signal.

Reads the append-only refresh log (pipeline/pit_store/YYYY-MM-DD.jsonl, one immutable row per
(refresh, ticker), written by validation/ic_harness.append_refresh and never rewritten), not
the raw fundamentals PIT store (pipeline/data/pit/) -- that one tracks provider values, this
one tracks scored output.

Findings against the real committed store (2026-08-06, model 3.2.0): three healthy
same-day transitions show top-40 turnover of 5-12.5% with 0.7-3.7% of shared tickers seeing
an availability-driven metric change. The transition into the run diagnosed in
docs/BASELINE-2026-08-06.md (the statement_enriched_count=0 incident) shows top-40 turnover
jump to 52.5% with 43.6% of shared tickers affected -- a 10-60x spike exactly where the
enrichment bug hit, confirming availability-driven churn as the dominant cause rather than
genuine business change. That bug is fixed at its source in yahoo_extended()
(pipeline/fetch_advisor.py); this diagnostic exists to make a repeat visible immediately
instead of requiring another multi-day investigation.

A universal minimum-coverage floor for ranking eligibility was considered as an additional
defense-in-depth measure and deliberately not added here: fundamental_detail.coverage mixes
the core metrics every company gets with the extended statement metrics only a budget-limited
enrichment shortlist (~20-40 names) ever receives by design (see enrich() in
fetch_advisor.py), so a blanket floor would conflate "legitimately never enriched, by
design" with "enrichment attempted and failed" and could systematically demote the very
names the two-tier design intends to include. That needs the full sleeve eligibility
framework (Phase 6) to do correctly, not a rushed blanket cutoff here.

Usage: python pipeline/stability_report.py
"""

import glob
import json
import os
import statistics
from collections import defaultdict

from common import LOG

PIT_STORE_DIR = os.path.join(os.path.dirname(__file__), "pit_store")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "stability.json")


def load_refresh_rows(pit_dir=None, require_prefix="advisor-"):
    """Every row from every dated jsonl file, as {refresh_id: [rows]}.

    Only ``refresh_id``s matching the real production pattern
    (``f"advisor-{generated_at}"``, see fetch_advisor.py) are included by default. The
    committed store also carries a handful of non-standard ids (e.g.
    ``initial-2026-08-04T...``, ``phase3-complete-2026-08-05``) left over from an earlier
    dev/test session -- their rows carry model_version 3.0.0 against a current 3.2.0 and
    would silently corrupt turnover comparisons if treated as real refreshes. Pass
    ``require_prefix=None`` to include everything anyway.
    """
    pit_dir = pit_dir or PIT_STORE_DIR
    by_refresh, excluded = defaultdict(list), set()
    for path in sorted(glob.glob(os.path.join(pit_dir, "*.jsonl"))):
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                refresh_id = row["refresh_id"]
                if require_prefix and not refresh_id.startswith(require_prefix):
                    excluded.add(refresh_id)
                    continue
                by_refresh[refresh_id].append(row)
    if excluded:
        LOG.warn(f"stability_report: excluded {len(excluded)} non-standard refresh_id(s) "
                 f"from pipeline/pit_store/ ({sorted(excluded)})")
    return by_refresh


def _ranked_tickers(rows, variant, top_n, published_only=True):
    """Tickers sorted by descending score for one variant. Published rows only by default --
    a screen-only tail row is not part of what a user perceives as "the ranking".
    """
    candidates = [
        row for row in rows
        if (row.get("scores") or {}).get(variant) is not None
        and (not published_only or row.get("published_research"))
    ]
    candidates.sort(key=lambda row: row["scores"][variant], reverse=True)
    return [row["ticker"] for row in candidates[:top_n]]


def rank_turnover(previous_tickers, current_tickers):
    """Fraction of the previous top-N no longer in the current top-N."""
    previous_set, current_set = set(previous_tickers), set(current_tickers)
    if not previous_set:
        return None
    departed = previous_set - current_set
    return round(len(departed) / len(previous_set), 3)


def _metric_scores(row, variant):
    return (row.get("normalized_metric_scores") or {}).get(variant) or {}


def decompose_score_delta(previous_row, current_row, variant):
    """For one ticker present in both refreshes, split metric-level movement into "a
    metric's value genuinely changed" versus "a metric flipped between missing and
    present". The second is a data-availability artifact, not new evidence about the
    company -- exactly the failure mode fixed in yahoo_extended() (see
    docs/BASELINE-2026-08-06.md).
    """
    previous_metrics, current_metrics = _metric_scores(previous_row, variant), _metric_scores(current_row, variant)
    value_changes, availability_changes = [], []
    for metric in sorted(set(previous_metrics) | set(current_metrics)):
        before, after = previous_metrics.get(metric), current_metrics.get(metric)
        if (before is None) != (after is None):
            availability_changes.append(metric)
        elif before is not None and after is not None and before != after:
            value_changes.append(metric)
    previous_score = (previous_row.get("scores") or {}).get(variant)
    current_score = (current_row.get("scores") or {}).get(variant)
    previous_confidence = (previous_row.get("confidence") or {}).get(variant)
    current_confidence = (current_row.get("confidence") or {}).get(variant)
    return {
        "metrics_with_value_change": value_changes,
        "metrics_with_availability_change": availability_changes,
        "score_delta": (round(current_score - previous_score, 2)
                        if previous_score is not None and current_score is not None else None),
        "confidence_delta": (round(current_confidence - previous_confidence, 3)
                             if previous_confidence is not None and current_confidence is not None else None),
    }


def compute_stability_report(pit_dir=None, top_ns=(40, 100), variant="champion"):
    """Rank turnover and score-delta decomposition across every consecutive pair of
    refreshes actually stored, for one score variant.
    """
    by_refresh = load_refresh_rows(pit_dir)
    refresh_ids = sorted(by_refresh, key=lambda refresh_id: refresh_id.split("advisor-", 1)[-1])
    if len(refresh_ids) < 2:
        return {
            "status": "insufficient_history",
            "refreshes_observed": len(refresh_ids),
            "note": "Rank-turnover diagnostics need at least two refreshes in "
                    "pipeline/pit_store/ to compare; fewer are available.",
        }

    transitions = []
    for previous_id, current_id in zip(refresh_ids, refresh_ids[1:]):
        previous_rows = {row["ticker"]: row for row in by_refresh[previous_id]}
        current_rows = {row["ticker"]: row for row in by_refresh[current_id]}
        shared = sorted(set(previous_rows) & set(current_rows))

        turnover_by_depth = {
            f"top_{top_n}": rank_turnover(
                _ranked_tickers(by_refresh[previous_id], variant, top_n),
                _ranked_tickers(by_refresh[current_id], variant, top_n),
            )
            for top_n in top_ns
        }

        decompositions = [
            {"ticker": ticker, **decompose_score_delta(previous_rows[ticker], current_rows[ticker], variant)}
            for ticker in shared
        ]
        availability_driven = [d for d in decompositions if d["metrics_with_availability_change"]]
        score_deltas = [d["score_delta"] for d in decompositions if d["score_delta"] is not None]
        confidence_deltas = [d["confidence_delta"] for d in decompositions if d["confidence_delta"] is not None]

        transitions.append({
            "previous_refresh": previous_id,
            "current_refresh": current_id,
            "shared_tickers": len(shared),
            "rank_turnover": turnover_by_depth,
            "tickers_with_availability_driven_change": len(availability_driven),
            "tickers_with_availability_driven_change_pct": (
                round(len(availability_driven) / len(decompositions), 3) if decompositions else None
            ),
            "mean_abs_score_delta": round(statistics.mean(abs(d) for d in score_deltas), 2) if score_deltas else None,
            "mean_abs_confidence_delta": (
                round(statistics.mean(abs(d) for d in confidence_deltas), 3) if confidence_deltas else None
            ),
            "largest_availability_driven_movers": sorted(
                availability_driven, key=lambda d: abs(d["score_delta"] or 0), reverse=True,
            )[:10],
        })

    return {
        "status": "ok",
        "variant": variant,
        "refreshes_observed": len(refresh_ids),
        "transitions": transitions,
        # Both left explicitly unresolved rather than estimated: the scored PIT log records
        # each ticker's own normalized scores, not the peer set or normalization scope it was
        # ranked against at that refresh, so neither signal is recoverable from this log as
        # currently shaped without inventing one.
        "peer_group_recomposition": {
            "status": "not_computed",
            "reason": "Peer-group membership per refresh is not captured at write time.",
        },
        "normalization_regime_flip": {
            "status": "not_computed",
            "reason": "Whether a sector crossed sector_minimum_count between refreshes is "
                      "not recoverable from this log as currently shaped.",
        },
    }


def write_stability_report(path=REPORT_PATH):
    report = compute_stability_report()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report


def main():
    report = write_stability_report()
    if report["status"] == "ok":
        latest = report["transitions"][-1]
        LOG.info(
            f"Stability report: {report['refreshes_observed']} refreshes, latest top_40 "
            f"turnover={latest['rank_turnover'].get('top_40')}, "
            f"{latest['tickers_with_availability_driven_change_pct']} of shared tickers had "
            "an availability-driven metric change"
        )
    else:
        LOG.info(f"Stability report: {report['note']}")
    return report


if __name__ == "__main__":
    main()
