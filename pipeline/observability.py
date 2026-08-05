"""Run manifests and ticker-level reproducibility artifacts."""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

from canonical_metrics import APPLICABILITY, BUSINESS_PROFILES, METRIC_REGISTRY, RECONCILIATION
from common import load_json


def _hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _commit_hash():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.dirname(__file__)),
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_manifest(payload, rejected=None):
    rows = payload.get("research", [])
    scores = [row.get("analysis_v2", {}).get("structural", {}).get("effective_score") for row in rows]
    scores = [score for score in scores if isinstance(score, (int, float))]
    conflicts = sum(len(row.get("analysis_v2", {}).get("structural", {}).get("provider_conflicts", [])) for row in rows)
    stale = sum(len(row.get("analysis_v2", {}).get("structural", {}).get("stale_metrics", [])) for row in rows)
    generated_at = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    settings = load_json("settings.json", from_config=True) or {}
    model_version = (settings.get("model") or {}).get("semantic_version", "0.0.0")
    return {
        "run_id": f"advisor-{generated_at.replace(':', '').replace('+00:00', 'Z')}",
        "generated_at": generated_at,
        "data_cutoff": generated_at,
        "code_commit_hash": _commit_hash(),
        "config_hash": _hash(settings),
        "schema_version": payload.get("schema_version"),
        "model_version": model_version,
        "universe_version": _hash(payload.get("universe", []))[:16],
        "provider_status": payload.get("source_status", {}),
        "cache": {"hits": None, "misses": None, "quality_flags": ["cache_counters_not_instrumented"]},
        "stale_field_count": stale,
        "provider_conflict_count": conflicts,
        "score_distribution": {
            "count": len(scores),
            "minimum": min(scores) if scores else None,
            "maximum": max(scores) if scores else None,
            "mean": round(sum(scores) / len(scores), 2) if scores else None,
        },
        "rejected_at_each_step": rejected or {},
    }


def diagnostics_payload(payload):
    rows = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    tickers = {}
    for row in rows:
        ticker = row.get("ticker")
        if not ticker or ticker in tickers:
            continue
        analysis = row.get("analysis_v2", {})
        tickers[ticker] = {
            "ticker": ticker,
            "applicability_profile": analysis.get("applicability_profile"),
            "raw_observations": row.get("observations", {}),
            "normalized_observations": row.get("observations", {}),
            "metric_applicability": analysis.get("metric_status", {}),
            "scoring_contributions": analysis.get("structural", {}),
            "modifiers": row.get("modifiers", {}),
            "confidence": {
                "structural": analysis.get("structural", {}).get("confidence"),
                "timeliness": analysis.get("timeliness", {}).get("confidence"),
            },
            "peer_ranking": row.get("valuation_percentile"),
            "final_classification": analysis.get("company_classification"),
            "position_action": analysis.get("position_action"),
            "warnings": sorted(set(
                analysis.get("structural", {}).get("missing_metrics", [])
                + analysis.get("structural", {}).get("provider_conflicts", [])
            )),
        }
    return {
        "schema_version": 1,
        "generated_at": payload.get("generated_at"),
        "run_id": payload.get("run_manifest", {}).get("run_id"),
        "tickers": tickers,
    }
