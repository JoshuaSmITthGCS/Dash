"""Non-destructive v1 -> v2 advisor JSON migration using checked-in observations."""

from common import load_json, save_json
from observability import diagnostics_payload, run_manifest
from peer_groups import canonical_percentiles
from recommendation_policy_v2 import build_recommendation_v2
from scoring_v2 import build_v2_analysis


def migrate(payload):
    if not payload:
        raise ValueError("advisor payload is missing")
    output = dict(payload)
    all_rows = [*output.get("research", []), *output.get("portfolio_coverage", [])]
    unique_rows = {}
    for row in all_rows:
        if row.get("ticker"):
            unique_rows.setdefault(row["ticker"], row)
    peer_rows = [{**row, "categories": row.get("fundamental_categories", {})} for row in unique_rows.values()]
    peers = canonical_percentiles(peer_rows, constructed_at=str(output.get("generated_at", ""))[:10] or None)
    seen = set()
    for collection in (output.get("research", []), output.get("portfolio_coverage", [])):
        for row in collection:
            if not row.get("ticker"):
                continue
            row["analysis_v2"] = build_v2_analysis(row, row.get("fundamental_detail", {}))
            row["recommendation_v2"] = build_recommendation_v2(
                row["ticker"], row["analysis_v2"],
                technical=row.get("technical_detail"), sentiment=row.get("sentiment_detail"),
                extended=row,
                generated_at=output.get("generated_at"),
            )
            row["valuation_percentile"] = peers.get(row["ticker"])
            canonical_percentile = (peers.get(row["ticker"]) or {}).get("value")
            row["sector_valuation_percentile"] = canonical_percentile
            if row.get("modifiers", {}).get("notes") is not None:
                notes = [note for note in row["modifiers"]["notes"] if not note.startswith("Valuation ")]
                if canonical_percentile is not None:
                    notes.insert(0, f"Valuation cheaper than {canonical_percentile:.0f}% of its canonical peers")
                row["modifiers"]["notes"] = notes
            seen.add(row["ticker"])
    output["schema_version"] = 2
    output.setdefault("methodology", {})["canonical_layer"] = {
        "model_version": "structural-timeliness-2.0.0",
        "migration": "legacy fields retained; v2 decisions are independently versioned",
    }
    output["run_manifest"] = run_manifest(output, {"migration": 0})
    return output


def main():
    payload = migrate(load_json("advisor.json"))
    save_json("advisor.json", payload)
    save_json("diagnostics.json", diagnostics_payload(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
