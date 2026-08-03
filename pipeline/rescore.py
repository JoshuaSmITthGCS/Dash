"""Re-score the last published data, with no network calls at all.

fetch_advisor.py's fetch -> enrich -> score pipeline is the slow part (rate-limited Yahoo/
Alpha Vantage/SEC requests, up to the workflow's 90-minute budget). A change to scoring
logic alone - like giving statement-derived metrics canonical observation lineage - doesn't
need any of that re-fetched: every value it needs is already sitting on each row in the
last published advisor.json, computed by the last real fetch.

This backfills the canonical Observation records those already-fetched values were missing
(the same gap fundamentals_extended.extended_observations/canonical_metrics.yahoo_observations
now fill going forward, for data fetched *before* that fix existed), then re-runs
migrate_advisor_v2's scoring pass over every row. Finishes in well under a second.

Usage: python pipeline/rescore.py
"""

from canonical_metrics import Observation
from common import load_json, save_json
from fundamentals_extended import extended_observations
from migrate_advisor_v2 import migrate
from observability import diagnostics_payload

# The handful of quote-derived metrics canonical_metrics.yahoo_observations backfills going
# forward. There's no raw provider payload left to recompute them from here, but the value
# already on the row is the real, already-fetched number - just missing its lineage.
YAHOO_INFO_BACKFILL = {
    "debt_to_equity": "multiple",
    "return_on_equity": "decimal",
    "profit_margin": "decimal",
    "price_to_sales": "multiple",
    "free_cash_flow_yield": "decimal",
}


def backfill_row_observations(row):
    fetched_at = row.get("data_fetched_at")
    observations = dict(row.get("observations") or {})
    for metric_id, rows in extended_observations(row, fetched_at=fetched_at).items():
        observations.setdefault(metric_id, []).extend(rows)
    for metric_id, unit in YAHOO_INFO_BACKFILL.items():
        if metric_id in observations or row.get(metric_id) is None:
            continue
        observations[metric_id] = [Observation(
            value=row[metric_id], unit=unit, source="yahoo", source_field=f"backfilled:{metric_id}",
            observed_at=fetched_at, fetched_at=fetched_at, is_ttm=True,
            quality_flags=["backfilled_from_legacy_snapshot"],
        ).to_dict()]
    row["observations"] = observations
    return row


def main():
    payload = load_json("advisor.json")
    if not payload:
        raise SystemExit("advisor.json is missing - run fetch_advisor.py at least once first")
    rescored = 0
    for collection in (payload.get("research", []), payload.get("portfolio_coverage", [])):
        for row in collection:
            if row.get("ticker"):
                backfill_row_observations(row)
                rescored += 1
    migrated = migrate(payload)
    save_json("advisor.json", migrated)
    save_json("diagnostics.json", diagnostics_payload(migrated))
    print(f"Rescored {rescored} rows with no network calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
