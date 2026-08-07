"""Measure the A3 enrichment-selection defect against the committed universe.

``fetch_advisor.py::select_enrichment_priority`` seeds statement enrichment (EV/EBITDA,
ROIC, interest coverage, Piotroski F -- the ``capital_allocation``/``accounting_quality``
fundamental categories) from the prior refresh's top 20 plus 5 challengers. Every other name
in the screen universe is scored on a strict subset of fundamentals. This module quantifies
that gap from data already committed to ``public/data/advisor.json`` -- no network calls.

Two things this can measure offline, and one it cannot:
  * coverage: how many names in each collection actually carry statement-derived categories.
  * the enriched/non-enriched split: how those two populations differ in score, and what
    can (and cannot) be said about sector and market-cap composition from published fields.
  * NOT measurable here: whether the full universe, enriched on equal footing, would surface
    different top-40 names (overlap / Spearman / forward-return comparison). That needs
    ``FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py`` against live data, which
    this environment's network policy blocks -- recorded as ``status: blocked_network_policy``
    with its exact reproduction command, never fabricated.
"""

import json
import os
import statistics
from datetime import datetime, timezone

from common import load_json

REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "enrichment_bias.json")
STATEMENT_CATEGORIES = ("capital_allocation", "accounting_quality")


def _rows(payload):
    return [*(payload.get("research") or []), *(payload.get("screen_universe") or [])]


def is_statement_enriched(row):
    """A row is statement-enriched when the metrics that only exist after ``enrich()`` runs
    (capital_allocation, accounting_quality) are actually populated -- not merely present as
    a key, since ``fundamental_categories`` always has every key with a possibly-None value.
    """
    categories = row.get("fundamental_categories") or {}
    return all(categories.get(category) is not None for category in STATEMENT_CATEGORIES)


def category_coverage(rows, collection_label):
    categories = sorted({
        category
        for row in rows
        for category in (row.get("fundamental_categories") or {})
    })
    total = len(rows)
    return {
        "collection": collection_label,
        "total_rows": total,
        "categories": {
            category: {
                "scored": sum(1 for row in rows if (row.get("fundamental_categories") or {}).get(category) is not None),
                "total": total,
            }
            for category in categories
        },
    }


def _score_stats(rows):
    values = [row["score"] for row in rows if isinstance(row.get("score"), (int, float))]
    if not values:
        return {"n": 0, "mean": None, "median": None, "stdev": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "stdev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
    }


def _sector_distribution(rows):
    counts = {}
    for row in rows:
        sector = row.get("sector") or "Unknown"
        counts[sector] = counts.get(sector, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def enriched_vs_non_enriched(rows):
    enriched = [row for row in rows if is_statement_enriched(row)]
    non_enriched = [row for row in rows if not is_statement_enriched(row)]
    market_cap_available = sum(1 for row in rows if isinstance(row.get("market_cap"), (int, float)))
    return {
        "enriched_count": len(enriched),
        "non_enriched_count": len(non_enriched),
        "score": {
            "enriched": _score_stats(enriched),
            "non_enriched": _score_stats(non_enriched),
        },
        "sector_distribution": {
            "enriched": _sector_distribution(enriched),
            "non_enriched": _sector_distribution(non_enriched),
        },
        "market_cap_comparison": {
            "status": "not_measurable" if market_cap_available <= len(enriched) else "measurable",
            "rows_with_market_cap": market_cap_available,
            "note": (
                "market_cap is populated only on published research rows in this dataset -- "
                "the screen universe (where the non-enriched population lives) does not carry "
                "it, so an enriched-vs-non-enriched market-cap comparison cannot be computed "
                "from committed data without fabricating values for the missing side."
                if market_cap_available <= len(enriched) else
                "market_cap available for both populations; see the score/sector legs above for method."
            ),
        },
        "interpretation": (
            "This is a correlation, not yet a causal estimate: select_enrichment_priority "
            "chooses its enrichment targets partly from the same preliminary fundamentals "
            "score being compared here, so part of this gap is selection-on-the-outcome, not "
            "proof that enrichment itself lifts scores. Separating the two requires scoring "
            "the full universe with and without statement enrichment on equal footing -- "
            "the blocked full-universe comparison below."
        ),
    }


def build_enrichment_bias_report(payload, generated_at=None):
    research = payload.get("research") or []
    screen = payload.get("screen_universe") or []
    all_rows = _rows(payload)
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "method": "Computed entirely from public/data/advisor.json as committed -- no network calls.",
        "coverage_by_collection": {
            "research": category_coverage(research, "research"),
            "screen_universe": category_coverage(screen, "screen_universe"),
        },
        "enriched_vs_non_enriched": enriched_vs_non_enriched(all_rows),
        "full_universe_comparison": {
            "status": "blocked_network_policy",
            "measures": [
                "top_40_overlap_pct: full-universe-enriched top 40 vs the current production top 40",
                "spearman: rank correlation between full-universe-enriched score and production score",
                "forward_return_delta: realized forward return of full-universe-only discoveries vs the production top 40",
            ],
            "reproduction_command": "FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py",
            "reason": "Requires live Yahoo/SEC statement data for the full screen universe (374 names); this environment's network egress is blocked for every provider fetch_advisor.py uses.",
        },
    }


def write_enrichment_bias_report(payload, generated_at=None, path=REPORT_PATH):
    report = build_enrichment_bias_report(payload, generated_at)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report


def main():
    payload = load_json("advisor.json")
    if not payload:
        raise SystemExit("advisor.json is missing - run fetch_advisor.py at least once first")
    report = write_enrichment_bias_report(payload)
    coverage = report["coverage_by_collection"]["screen_universe"]["categories"].get("capital_allocation", {})
    split = report["enriched_vs_non_enriched"]
    print(f"Wrote {REPORT_PATH}")
    print(f"screen_universe capital_allocation coverage: {coverage.get('scored')}/{coverage.get('total')}")
    print(f"enriched score mean={split['score']['enriched']['mean']} "
          f"(n={split['score']['enriched']['n']}) vs non-enriched "
          f"mean={split['score']['non_enriched']['mean']} (n={split['score']['non_enriched']['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
