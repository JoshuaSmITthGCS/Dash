"""Is the published leaderboard ranking companies, or ranking how much data they received?

Every other measurement in ``research/`` rests on a nine-year backtest and inherits its
caveats. This one does not. It is arithmetic on the artifact the site publishes, so it holds
whatever turns out to be true about valuation, momentum or survivorship, and it decides what
the bucket planner allocates money to today.

The question is answerable because two of the six scoring categories -- ``capital_allocation``
and ``accounting_quality``, 20% of the score between them -- depend on statement enrichment,
and enrichment reaches a minority of the universe. If the enriched minority occupies the top of
the ranking, then the ranking is reporting data availability wearing the clothes of company
quality, and no amount of correctness in the scoring underneath changes that.

Run it after every publish. It needs no network, no point-in-time store, and no backtest.
"""

import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rank_statistics import spearman  # noqa: E402

# The categories that only resolve once a company has had its financial statements pulled.
ENRICHMENT_ONLY = ("capital_allocation", "accounting_quality")

# Above this share, the top of the leaderboard is drawn from the enriched minority far out of
# proportion to its size, and the ranking is not comparing like with like.
CONCENTRATION_ALARM = 0.9


def _category(row, name):
    return (row.get("fundamental_categories") or {}).get(name)


def _enriched(row):
    return all(_category(row, name) is not None for name in ENRICHMENT_ONLY)


def audit(artifact):
    """Concentration, cohort separation and loop persistence, from a published advisor.json."""
    published = [row for row in artifact.get("research") or [] if not row.get("is_etf")]
    published_tickers = {row["ticker"] for row in published}
    lighter = [row for row in artifact.get("screen_universe") or []
               if not row.get("is_etf") and row["ticker"] not in published_tickers]
    everyone = published + lighter
    if not everyone:
        return {"error": "no non-ETF rows in the artifact"}

    ranked = sorted(everyone, key=lambda row: -(row.get("score") or 0))
    enriched = [row for row in everyone if _enriched(row)]
    enriched_share = len(enriched) / len(everyone)

    concentration = {}
    for depth in (8, 20, 40, 100):
        head = ranked[:depth]
        concentration[f"top_{depth}"] = {
            "from_enriched_cohort": sum(1 for row in head if _enriched(row)),
            "from_fully_published": sum(1 for row in head if row["ticker"] in published_tickers),
            "of": len(head),
        }

    unenriched_best = next((index + 1 for index, row in enumerate(ranked) if not _enriched(row)),
                           None)

    with_both = [row["score"] for row in lighter if _enriched(row) and row.get("score") is not None]
    without = [row["score"] for row in lighter
               if not _enriched(row) and row.get("score") is not None]

    selection = artifact.get("enrichment_selection") or {}
    previous_top = set(selection.get("previous_top") or [])
    challengers = set(selection.get("challengers") or [])
    current_top = [row["ticker"] for row in ranked[:max(len(previous_top), 20)]]

    # Enrichment priority keyed on the previous ranking is a closed loop: the data that lifts a
    # score is handed to whoever already scored. Persistence measures how closed it still is.
    persistence = (sum(1 for ticker in current_top if ticker in previous_top) / len(current_top)
                   if current_top else None)

    return {
        "generated_at": artifact.get("generated_at"),
        "model_version": artifact.get("model_version"),
        "universe": len(everyone),
        "fully_published": len(published),
        "enriched_cohort": len(enriched),
        "enriched_share": round(enriched_share, 4),
        "concentration": concentration,
        "best_rank_without_enrichment": unenriched_best,
        "lighter_cohort_score_gap": {
            "with_enrichment_categories": {
                "count": len(with_both),
                "median": statistics.median(with_both) if with_both else None},
            "without": {
                "count": len(without),
                "median": statistics.median(without) if without else None},
            "median_points": (statistics.median(with_both) - statistics.median(without)
                              if with_both and without else None),
        },
        "category_medians": {
            name: {
                "published": _median_category(published, name),
                "lighter": _median_category(lighter, name),
            } for name in ("valuation", "profitability", "financial_health", "growth",
                           *ENRICHMENT_ONLY)
        },
        "coverage_versus_score": _coverage_correlation(everyone),
        "enrichment_loop": {
            "priority_source": "previous_top" if previous_top else None,
            "priority_count": selection.get("priority_count"),
            "challengers_rotated_in": len(challengers),
            "top_carried_over_from_previous": persistence,
            "challengers_reaching_the_top": sum(1 for ticker in current_top
                                                if ticker in challengers),
        },
        "verdict": _verdict(concentration, enriched_share, persistence),
    }


def _median_category(rows, name):
    values = [_category(row, name) for row in rows if _category(row, name) is not None]
    return {"resolved": len(values), "of": len(rows),
            "median": round(statistics.median(values), 1) if values else None}


def _coverage_correlation(rows):
    """Rank correlation between how much resolved and how well a company scored.

    A high value is the finding in one number: the leaderboard is ordering evidence volume.
    """
    pairs = [(sum(1 for name in ("valuation", "profitability", "financial_health", "growth",
                                 *ENRICHMENT_ONLY) if _category(row, name) is not None),
              row.get("score"))
             for row in rows if row.get("score") is not None]
    if len(pairs) < 30:
        return None
    return round(spearman([count for count, _ in pairs], [score for _, score in pairs]), 4)


def _verdict(concentration, enriched_share, persistence):
    top40 = concentration.get("top_40") or {}
    resolved, of = top40.get("from_enriched_cohort", 0), top40.get("of", 0) or 1
    if resolved / of >= CONCENTRATION_ALARM and enriched_share < 0.5:
        return ("The top of the leaderboard is drawn almost entirely from the minority of "
                "companies that received statement enrichment. Rows scored on a thinner "
                "evidence base are not comparable to it and should not share one ordered list."
                + (" Enrichment priority is keyed on the previous ranking, so the cohort that "
                   "gets the data is largely the cohort that already had it."
                   if persistence and persistence >= 0.6 else ""))
    return "No disproportionate concentration of the leaderboard in the enriched cohort."


def main(argv=None):
    path = (argv or sys.argv[1:] or [os.path.join(ROOT, "public", "data", "advisor.json")])[0]
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    print(json.dumps(audit(artifact), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
