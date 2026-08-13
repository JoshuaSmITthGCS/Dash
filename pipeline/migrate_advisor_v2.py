"""Re-derive every computed block on a published advisor payload, with no network calls.

Two jobs, and the second one used to be silently skipped.

**Migration.** Bring an older payload up to the schema this build publishes. Field renames
live here, not only in the frontend's read-time migration, because the pipeline can also
*write* an upgraded payload (``pipeline/rescore.py``, the workflow's ``rescore-only`` mode).

**Re-derivation.** Everything downstream of the raw provider values -- the v2 analysis, the
shadow recommendation, peer context, the composite score -- is a pure function of inputs
already sitting on each row. After a scoring change those blocks are stale, and rebuilding
them is the entire point of a rescore.

The guards here used to read ``if not row.get("analysis_v2")``, so a row that already had
one kept its old, pre-change values while ``schema_version`` was stamped with the new
number. A payload that claims a contract it does not satisfy is worse than an old payload:
the frontend's read-time migration chain skips a version it thinks it is already at, so the
stale rows reach components expecting the new shape. ``assert_contract`` below makes that
combination fail loudly instead.

Rows carrying their raw metric inputs (``research``, ``portfolio_coverage``) are fully
rescored. Lightweight ``screen_universe`` rows do not carry those inputs -- see
``fetch_advisor._screen_row`` -- so they receive the mechanical field renames and are marked
``rescored: false`` rather than being passed off as recomputed.
"""

from advisor_engine import (apply_modifiers, blend_research_components, build_evidence,
                            action_for, stance_for)
from common import load_json, save_json
from observability import diagnostics_payload, run_manifest
from peer_groups import canonical_percentiles
from recommendation_policy_v2 import build_recommendation_v2
from scorer import valuation_score
from scoring_v2 import MODEL_VERSION, build_v2_analysis

# Scalars renamed in schema 6. The published name was a completeness ratio described as
# confidence; see research/audit/CURRENT_MODEL_AUDIT.md section 4.
RENAMED_ROW_FIELDS = {"confidence": "data_coverage", "confidence_detail": "data_coverage_detail"}

# Peer fields schema 6 removed outright. A continuous percentile over a composite of
# discrete band scores was never a supportable number, so there is nothing to translate it
# into -- see peer_groups.py.
REMOVED_PEER_FIELDS = ("value", "display_value")


def rename_row_fields(row):
    """Apply the schema-6 scalar renames in place, dropping the retired names."""
    for old, new in RENAMED_ROW_FIELDS.items():
        if old in row:
            value = row.pop(old)
            row.setdefault(new, value)
    detail = row.get("data_coverage_detail")
    if isinstance(detail, dict) and "confidence" in detail:
        detail["data_coverage"] = detail.pop("confidence")
    recommendation = row.get("recommendation")
    if isinstance(recommendation, dict) and "confidence" in recommendation:
        recommendation.setdefault("agreement_strength", recommendation.pop("confidence"))
    for variant in (row.get("score_variants") or {}).values():
        if isinstance(variant, dict) and "confidence" in variant:
            variant.setdefault("data_coverage", variant.pop("confidence"))
    percentile = row.get("valuation_percentile")
    if isinstance(percentile, dict):
        for field in REMOVED_PEER_FIELDS:
            percentile.pop(field, None)
    return row


def rescore_row(row, peer_context):
    """Recompute every derived block on one fully-detailed row.

    Returns the row unchanged apart from the derived fields. Anything that cannot be
    recomputed from what the row carries is left alone rather than guessed at.
    """
    row["valuation_percentile"] = peer_context
    row["sector_valuation_percentile"] = (peer_context or {}).get("ordinal")
    fundamental, fundamental_detail = valuation_score(row)
    if fundamental is None:
        # No raw metric inputs on this row, so the composite cannot be recomputed. Keep the
        # published score rather than overwriting it with a score derived from nothing --
        # zeroing a row because its inputs were projected away is worse than leaving it
        # stale, and `rescored` says which it is. The v2 blocks are still rebuilt: they
        # derive from the legacy category detail the row does carry.
        row["rescored"] = False
        _rebuild_v2(row, row.get("fundamental_detail") or {})
        return row
    # Champion formula promoted 2026-08-12 (Round 5 Task 2): the fundamentals component
    # is pre-multiplier, and the blend below carries no coverage multiplier either - see
    # advisor_engine.blend_research_components' docstring. build_research and rescore_row
    # must stay in lockstep or a rescore-only refresh silently regresses the fix.
    raw_fundamental = fundamental_detail.get("raw_score", fundamental)
    components = {**(row.get("components") or {}), "fundamentals": raw_fundamental}
    coverage = {
        "fundamentals": fundamental_detail.get("coverage", 0.0),
        "market_behavior": (row.get("technical_detail") or {}).get("coverage", 0.0),
        "news_sentiment": (row.get("sentiment_detail") or {}).get("coverage", 0.0),
    }
    blended = blend_research_components(components, coverage, apply_coverage_multiplier=False)
    score, modifiers = apply_modifiers(
        blended["base_score"], row, row,
        sector_percentile=row["sector_valuation_percentile"],
        insider_activity=row.get("insider_activity"),
        institutional_ownership=row.get("institutional_ownership"),
        congressional_activity=row.get("congressional_activity"),
        concentration_risk=row.get("concentration_risk"),
    )
    categories = fundamental_detail.get("categories", {})
    stance = stance_for(score, blended["data_coverage"])
    strengths, risks = build_evidence(categories, row.get("technical_detail") or {}, row)
    row.update({
        "score": score, "base_score": blended["base_score"], "raw_score": blended["raw_score"],
        "data_coverage": blended["data_coverage"], "stance": stance,
        "components": components, "fundamental_categories": categories,
        "fundamental_detail": fundamental_detail, "modifiers": modifiers,
        "strengths": strengths, "risks": risks,
        "recommendation": action_for(score, stance, fundamental_detail,
                                     row.get("technical_detail") or {}, row,
                                     row.get("sentiment_detail") or {}),
        "rescored": True,
    })
    _rebuild_v2(row, fundamental_detail)
    return row


def _rebuild_v2(row, fundamental_detail):
    """Rebuild the versioned analysis and shadow recommendation from current code.

    Unconditional. These blocks are pure functions of inputs already on the row, so a
    surviving copy from before a scoring change is stale by definition -- keeping it is what
    let a payload be stamped schema 6 while carrying schema 5 values.
    """
    row["analysis_v2"] = build_v2_analysis(row, fundamental_detail)
    row["recommendation_v2"] = build_recommendation_v2(
        row["ticker"], row["analysis_v2"],
        technical=row.get("technical_detail"), sentiment=row.get("sentiment_detail"),
        extended=row,
    )


def assert_contract(payload, schema_version):
    """Fail if the payload does not satisfy the schema it is about to claim.

    A payload stamped with a version it does not match is worse than an unmigrated one: the
    frontend's migration chain skips a version it believes it is already at, so stale rows
    reach components written for the new shape.
    """
    problems = []
    for name in ("research", "portfolio_coverage", "screen_universe"):
        for index, row in enumerate(payload.get(name) or []):
            where = f"{name}.{index} ({row.get('ticker')})"
            for retired in RENAMED_ROW_FIELDS:
                if retired in row:
                    problems.append(f"{where}: retired field '{retired}' survived migration")
            percentile = row.get("valuation_percentile")
            if isinstance(percentile, dict):
                for field in REMOVED_PEER_FIELDS:
                    if percentile.get(field) is not None:
                        problems.append(f"{where}: retired peer field '{field}' survived migration")
    if problems:
        raise ValueError(
            f"payload does not satisfy schema {schema_version}: " + "; ".join(problems[:5])
            + (f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""))


def migrate(payload):
    if not payload:
        raise ValueError("advisor payload is missing")
    output = dict(payload)
    detailed = [*output.get("research", []), *output.get("portfolio_coverage", [])]
    unique_rows = {}
    for row in detailed:
        if row.get("ticker"):
            unique_rows.setdefault(row["ticker"], row)
    peer_rows = [{**row, "categories": valuation_score(row)[1].get("categories", {})}
                 for row in unique_rows.values()]
    peers = canonical_percentiles(peer_rows,
                                  constructed_at=str(output.get("generated_at", ""))[:10] or None)
    for collection in (output.get("research", []), output.get("portfolio_coverage", [])):
        for row in collection:
            if not row.get("ticker"):
                continue
            rename_row_fields(row)
            rescore_row(row, peers.get(row["ticker"]))
    # Lightweight rows do not carry the raw metric inputs a rescore needs. They get the
    # mechanical renames and say plainly that they were not recomputed.
    for row in output.get("screen_universe", []) or []:
        rename_row_fields(row)
        row["rescored"] = False

    # Rescoring reorders the leaderboard by definition. Leaving the old order in place
    # publishes a list whose first row is not its highest score, which validate_data rejects
    # and which every consumer reads as a ranking.
    output["research"] = sorted(output.get("research", []),
                                key=lambda row: row.get("score") or 0, reverse=True)

    from scorer import SETTINGS
    schema_version = SETTINGS["model"]["advisor_schema_version"]
    output["model_version"] = SETTINGS["model"]["semantic_version"]
    output.setdefault("methodology", {})["canonical_layer"] = {
        "model_version": MODEL_VERSION,
        "migration": "every derived block re-computed; raw provider values untouched",
    }
    assert_contract(output, schema_version)
    output["schema_version"] = schema_version
    rejected = (output.get("run_manifest") or {}).get("rejected_at_each_step") or {"migration": 0}
    output["run_manifest"] = run_manifest(output, rejected)
    return output


def main():
    payload = migrate(load_json("advisor.json"))
    save_json("advisor.json", payload)
    save_json("diagnostics.json", diagnostics_payload(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
