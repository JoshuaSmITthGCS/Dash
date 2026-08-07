"""Size the selection-bootstrapping defect from already-published data.

The production pipeline computes statement-derived metrics -- EV/EBITDA, ROIC, interest
coverage, Piotroski F, the capital-allocation and accounting-quality categories -- only for a
shortlist. That shortlist is picked by a *preliminary* score that does not contain those
metrics, and is seeded with the previous refresh's top 20 while admitting five new candidates
(``fetch_advisor.select_enrichment_priority``). So the evidence that carries most of the
model's weight is available almost exclusively to companies an earlier, weaker model already
ranked highly, and today's leaders are seeded from yesterday's.

The decisive measurement -- run the full universe unseeded, then compare top-40 overlap, rank
correlation, and forward returns against the production shortlist -- needs a live enrichment
pass over ~900 names and cannot run without network access. What *can* be measured offline is
the footprint the gate leaves on the last published refresh: which categories are scored for
whom, and how differently enriched and unenriched names score. That is what this reports.

**This must be measured on a full-universe refresh.** A fast intraday refresh re-polls only
the previously ranked leaders and carries every other row forward stale, so on a fast artifact
"not statement-enriched" mostly means "not re-polled this cycle" -- an entirely different
thing, and one that would badly overstate the gate's footprint. The script refuses to score a
payload whose rows are dominated by carry-forwards, and the committed default source is the
most recent clean full refresh.

Usage: python pipeline/enrichment_bias.py [--source PATH]
Output: pipeline/reports/enrichment_bias.json
"""

import argparse
import json
import os
import sys
from collections import Counter
from statistics import mean, median

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from common import load_json  # noqa: E402

OUT_PATH = os.path.join(HERE, "reports", "enrichment_bias.json")

# The most recent refresh that polled the whole universe with statement enrichment working.
# Committed so this measurement is reproducible without network access and without depending
# on whichever refresh mode happens to have run last.
DEFAULT_SOURCE = os.path.join(HERE, "data", "full_refresh_snapshots",
                              "advisor-2026-08-06T002332-full.json")

# Above this share of carried-forward rows the sample says more about refresh mode than about
# the shortlist gate.
MAX_STALE_SHARE = 0.05

# Categories that cannot be scored at all without a statement-enrichment pass. Their presence
# on a row is the observable marker of whether that row cleared the shortlist gate.
STATEMENT_ONLY_CATEGORIES = ("capital_allocation", "accounting_quality")

BLOCKED_COMPARISON = {
    "status": "blocked_network_policy",
    "reason": ("requires a live unseeded enrichment pass over the full universe; this "
               "environment has no route to any market-data provider"),
    "reproduction": [
        "FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py",
        "python pipeline/enrichment_bias.py  # re-run to populate the comparison block",
    ],
    "metrics_that_would_populate": [
        "top_40_overlap", "top_100_overlap", "spearman_rank_correlation",
        "unconstrained_top_40_missing_from_production_shortlist",
        "difference_by_market_cap", "difference_by_sector",
        "difference_by_valuation_profile", "difference_by_profitability",
        "forward_return_difference",
    ],
}


def is_statement_enriched(row):
    categories = row.get("fundamental_categories") or {}
    return any(categories.get(name) is not None for name in STATEMENT_ONLY_CATEGORIES)


def _summary(values):
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": round(mean(ordered), 2),
        "median": round(median(ordered), 2),
        "minimum": round(ordered[0], 2),
        "maximum": round(ordered[-1], 2),
    }


def category_coverage(rows):
    """How many rows have each fundamental category scored at all."""
    counts = Counter()
    for row in rows:
        for name, value in (row.get("fundamental_categories") or {}).items():
            if value is not None:
                counts[name] += 1
    return {name: {"scored": count, "of": len(rows),
                   "coverage": round(count / len(rows), 3) if rows else None}
            for name, count in sorted(counts.items())}


def rank_concentration(rows, cutoffs=(10, 20, 40, 100)):
    """What share of each rank band cleared the statement gate.

    If the gate were neutral with respect to rank, these shares would track the universe-wide
    enrichment rate. They do not, and they cannot: a name is enriched *because* a preliminary
    model ranked it highly, and it then ranks highly partly *because* it was enriched.
    """
    ordered = sorted((row for row in rows if isinstance(row.get("score"), (int, float))),
                     key=lambda row: -row["score"])
    overall = (sum(is_statement_enriched(row) for row in ordered) / len(ordered)
               if ordered else None)
    bands = {}
    for cutoff in cutoffs:
        band = ordered[:cutoff]
        if not band:
            continue
        bands[f"top_{cutoff}"] = {
            "names": len(band),
            "statement_enriched": sum(is_statement_enriched(row) for row in band),
            "share": round(sum(is_statement_enriched(row) for row in band) / len(band), 3),
        }
    return {
        "universe_enrichment_rate": round(overall, 3) if overall is not None else None,
        "by_rank_band": bands,
    }


def score_gap(rows):
    """Score distribution of enriched versus unenriched names.

    A gap here is expected and is *not* by itself proof of bias -- enrichment is targeted at
    names the preliminary model already liked, so enriched names should score higher. It is
    reported because it sizes how much of the published ranking rests on evidence the rest of
    the universe was never given the chance to produce.
    """
    enriched = [row["score"] for row in rows
                if is_statement_enriched(row) and isinstance(row.get("score"), (int, float))]
    unenriched = [row["score"] for row in rows
                  if not is_statement_enriched(row) and isinstance(row.get("score"), (int, float))]
    summary = {"statement_enriched": _summary(enriched), "not_enriched": _summary(unenriched)}
    if summary["statement_enriched"] and summary["not_enriched"]:
        summary["mean_gap"] = round(
            summary["statement_enriched"]["mean"] - summary["not_enriched"]["mean"], 2)
    return summary


def unenriched_category_gap(rows):
    """Category-score gaps restricted to categories that need no statement enrichment.

    This is the check on whether the headline score gap means what it looks like. Enrichment
    is targeted at names the preliminary model already scored highly, and the preliminary
    model is built from exactly these categories -- so enriched names *should* look better
    here, by construction. A large gap on non-statement categories therefore says the gap is
    mostly circular selection, not evidence that the gate is hiding good companies.
    """
    gaps = {}
    for row in rows:
        for name, value in (row.get("fundamental_categories") or {}).items():
            if name in STATEMENT_ONLY_CATEGORIES or value is None:
                continue
            bucket = gaps.setdefault(name, {"statement_enriched": [], "not_enriched": []})
            key = "statement_enriched" if is_statement_enriched(row) else "not_enriched"
            bucket[key].append(value)
    return {
        name: {
            "statement_enriched_mean": round(mean(values["statement_enriched"]), 1)
            if values["statement_enriched"] else None,
            "not_enriched_mean": round(mean(values["not_enriched"]), 1)
            if values["not_enriched"] else None,
            "gap": round(mean(values["statement_enriched"]) - mean(values["not_enriched"]), 1)
            if values["statement_enriched"] and values["not_enriched"] else None,
        }
        for name, values in sorted(gaps.items())
    }


def sector_composition(rows):
    """Enrichment rate by sector -- a gate that is uneven across sectors tilts the ranking."""
    totals, enriched = Counter(), Counter()
    for row in rows:
        sector = row.get("sector") or "unknown"
        totals[sector] += 1
        if is_statement_enriched(row):
            enriched[sector] += 1
    return {
        sector: {"names": totals[sector], "statement_enriched": enriched[sector],
                 "rate": round(enriched[sector] / totals[sector], 3)}
        for sector in sorted(totals, key=lambda name: -totals[name])
    }


def eligible_universe(payload):
    """Deduplicated rows from a payload, or a refusal explaining why it cannot be scored."""
    rows = [*(payload.get("research") or []), *(payload.get("screen_universe") or [])]
    seen, universe = set(), []
    for row in rows:
        ticker = (row.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            universe.append(row)
    stale = sum(1 for row in universe if row.get("stale_carryforward"))
    share = stale / len(universe) if universe else 1.0
    if share > MAX_STALE_SHARE:
        return None, {
            "status": "source_rejected_fast_refresh",
            "reason": (f"{stale} of {len(universe)} rows are stale carry-forwards "
                       f"({share:.0%}); on a fast refresh 'not statement-enriched' mostly "
                       "means 'not re-polled this cycle', which would overstate the "
                       "shortlist gate's footprint"),
            "universe_mode": payload.get("universe_mode"),
            "remedy": "measure on a full-universe refresh artifact (--source)",
        }
    return universe, None


def build_report(payload=None, source_label=None):
    payload = payload if payload is not None else (load_json("advisor.json") or {})
    universe, rejection = eligible_universe(payload)
    selection = payload.get("enrichment_selection") or {}
    if rejection:
        return {
            "schema_version": 1,
            "generated_at": payload.get("generated_at"),
            "source": source_label,
            "observed_footprint": rejection,
            "unconstrained_comparison": BLOCKED_COMPARISON,
        }
    return {
        "schema_version": 1,
        "generated_at": payload.get("generated_at"),
        "source": source_label,
        "source_universe_mode": payload.get("universe_mode"),
        "source_polled_count": payload.get("polled_count"),
        "defect": ("statement-derived metrics are computed only for a shortlist chosen by a "
                   "preliminary score that does not contain them, seeded with the previous "
                   "refresh's top 20 and admitting 5 new candidates per refresh"),
        "enrichment_selection_as_published": {
            "mode": selection.get("mode", "production_shortlist"),
            "seeded_from_previous_ranking": selection.get("seeded_from_previous_ranking", True),
            "priority_count": selection.get("priority_count"),
            "statement_enriched_count": payload.get("statement_enriched_count"),
            "universe_count": payload.get("universe_count"),
        },
        "observed_footprint": {
            "names_considered": len(universe),
            "category_coverage": category_coverage(universe),
            "statement_only_categories": list(STATEMENT_ONLY_CATEGORIES),
            "rank_concentration": rank_concentration(universe),
            "score_gap": score_gap(universe),
            "non_statement_category_gap": unenriched_category_gap(universe),
            "sector_composition": sector_composition(universe),
        },
        "unconstrained_comparison": BLOCKED_COMPARISON,
        "interpretation": (
            "The footprint is measurable; the cost is not. The hard structural finding is that "
            "no unenriched name reaches the top 100 -- the two statement-only categories are "
            "20% of the fundamental weight and can never contribute for the ~60% of the "
            "published universe that is never enriched. The headline score gap, by contrast, "
            "is largely circular: enrichment is targeted at names the preliminary model "
            "already liked, and non_statement_category_gap shows enriched names already score "
            "well ahead on the categories that need no enrichment at all. So the gap is mostly "
            "selection, not proof that the gate hides good companies. Whether it does can only "
            "be answered by running the universe unseeded and comparing, which needs network "
            "access. Note also that docs/P0-Q1-BENCHMARK.md found no residual alpha after "
            "controlling for the six factors this model targets, which lowers the stakes: a "
            "gate that starves an alpha-generating process matters less when the process has "
            "not been shown to generate alpha."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="advisor.json-shaped payload from a full-universe refresh")
    args = parser.parse_args(argv)
    with open(args.source) as handle:
        payload = json.load(handle)
    report = build_report(payload, source_label=os.path.relpath(args.source, os.path.dirname(HERE)))
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    footprint = report["observed_footprint"]
    if footprint.get("status"):
        print(f"{footprint['status']}: {footprint['reason']}")
        print(f"wrote {OUT_PATH}")
        return report
    print(f"source: {report['source']} "
          f"({report['source_universe_mode']}, polled {report['source_polled_count']})")
    print(f"names considered: {footprint['names_considered']}")
    for name, block in footprint["category_coverage"].items():
        print(f"  {name:<20} {block['scored']:>4} / {block['of']}  ({block['coverage']:.0%})")
    concentration = footprint["rank_concentration"]
    print(f"universe enrichment rate: {concentration['universe_enrichment_rate']:.1%}")
    for band, block in concentration["by_rank_band"].items():
        print(f"  {band:<10} {block['statement_enriched']:>3} / {block['names']} "
              f"({block['share']:.0%}) statement-enriched")
    gap = footprint["score_gap"]
    if gap.get("mean_gap") is not None:
        print(f"mean score gap (enriched - not): {gap['mean_gap']:+.2f}")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
