"""Measure what removing the inert news weight does to published scores.

Before this change, ``news_intelligence.weighted_sentiment`` returned the neutral score
(50.0) at coverage 0.0 whenever no article cleared the entity/recency filters. Because
``advisor_engine.blend_research_components`` renormalizes only over components that are not
None, a hard 50.0 stayed *in* the denominator: every uncovered name was blended 4% toward 50
regardless of its fundamentals. That moved the level of every score without ordering any two
companies differently -- an apparently active component doing nothing.

This script quantifies the correction against the last published refresh, with no network
access. It recomputes the champion blend from the components already stored on each row, once
with the neutral fill and once with news dropped from the denominator, and reports the score
and rank deltas.

It reuses ``advisor_engine.blend_research_components`` rather than reimplementing the blend,
so the measurement cannot drift from production behaviour.

Usage: python pipeline/news_weight_impact.py
Output: pipeline/reports/news_availability_impact.json
"""

import json
import os
import sys
from statistics import mean

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from advisor_engine import RANKING_WEIGHTS, blend_research_components  # noqa: E402
from common import load_json  # noqa: E402

OUT_PATH = os.path.join(HERE, "reports", "news_availability_impact.json")
SECTIONS = ("research", "screen_universe")


def _has_real_coverage(row):
    """True when at least one article survived the entity/recency/confidence filters."""
    detail = row.get("sentiment_detail") or {}
    if "news_available" in detail:
        return bool(detail["news_available"])
    # Rows published before the flag existed: article_count is the same evidence.
    return int(detail.get("article_count") or 0) > 0


def _modifier_points(row):
    modifiers = row.get("modifiers") or {}
    total = modifiers.get("total")
    return float(total) if isinstance(total, (int, float)) else 0.0


def _coverage(row):
    return {
        "fundamentals": (row.get("fundamental_detail") or {}).get("coverage") or 0.0,
        "market_behavior": (row.get("technical_detail") or {}).get("coverage") or 0.0,
        "news_sentiment": (row.get("sentiment_detail") or {}).get("coverage") or 0.0,
    }


def score_row(row, *, drop_unavailable_news):
    components = dict(row.get("components") or {})
    if drop_unavailable_news and not _has_real_coverage(row):
        components["news_sentiment"] = None
    blended = blend_research_components(components, _coverage(row),
                                        modifier_points=_modifier_points(row))
    return blended["score"]


# The reconstruction must reproduce the published score before its delta means anything.
# Rows that carry components but not the per-component ``coverage`` blocks (screen_universe
# publishes a trimmed row shape) cannot reproduce the confidence multiplier, so their
# recomputed "before" score is not the score that shipped. Those rows are excluded and
# counted rather than silently averaged in.
RECONSTRUCTION_TOLERANCE = 0.15


def compare_section(rows):
    scored, unreproducible = [], []
    for row in rows:
        ticker = row.get("ticker")
        components = row.get("components") or {}
        published = row.get("score")
        if not ticker or components.get("fundamentals") is None:
            continue
        before = score_row(row, drop_unavailable_news=False)
        if not isinstance(published, (int, float)) or abs(before - published) > RECONSTRUCTION_TOLERANCE:
            unreproducible.append(ticker)
            continue
        after = score_row(row, drop_unavailable_news=True)
        scored.append({
            "ticker": ticker,
            "news_available": _has_real_coverage(row),
            "score_before": before,
            "score_after": after,
            "delta": round(after - before, 2),
        })
    if not scored:
        return {
            "names": 0,
            "excluded_unreproducible_blend": len(unreproducible),
            "status": "no_row_reproduces_its_published_score",
            "reason": ("rows in this section do not publish the per-component coverage blocks "
                       "the champion's confidence multiplier is computed from"),
        }

    before_rank = {row["ticker"]: index for index, row in
                   enumerate(sorted(scored, key=lambda item: -item["score_before"]))}
    after_rank = {row["ticker"]: index for index, row in
                  enumerate(sorted(scored, key=lambda item: -item["score_after"]))}
    for row in scored:
        row["rank_before"] = before_rank[row["ticker"]] + 1
        row["rank_after"] = after_rank[row["ticker"]] + 1
        row["rank_delta"] = row["rank_before"] - row["rank_after"]

    deltas = [row["delta"] for row in scored]
    moved = [row for row in scored if row["rank_delta"] != 0]
    return {
        "names": len(scored),
        "excluded_unreproducible_blend": len(unreproducible),
        "names_with_news_coverage": sum(row["news_available"] for row in scored),
        "names_without_news_coverage": sum(not row["news_available"] for row in scored),
        "score_delta": {
            "mean": round(mean(deltas), 3),
            "minimum": round(min(deltas), 3),
            "maximum": round(max(deltas), 3),
        },
        "names_changing_rank_position": len(moved),
        "largest_rank_moves": sorted(
            ({k: row[k] for k in ("ticker", "delta", "rank_before", "rank_after", "rank_delta")}
             for row in scored),
            key=lambda item: -abs(item["rank_delta"]),
        )[:10],
        "largest_score_moves": sorted(
            ({k: row[k] for k in ("ticker", "score_before", "score_after", "delta")}
             for row in scored),
            key=lambda item: -abs(item["delta"]),
        )[:10],
    }


def build_report(payload=None):
    payload = payload if payload is not None else (load_json("advisor.json") or {})
    sections = {}
    for name in SECTIONS:
        result = compare_section(payload.get(name) or [])
        if result:
            sections[name] = result
    return {
        "schema_version": 1,
        "generated_at": payload.get("generated_at"),
        "source": "public/data/advisor.json",
        "change": ("weighted_sentiment returns None instead of the neutral score when no "
                   "article clears the entity/recency/confidence filters, so the blend drops "
                   "the news weight from the denominator instead of filling it with 50.0"),
        "news_weight": RANKING_WEIGHTS["news_sentiment"],
        "interpretation": (
            "A uniform neutral fill is close to an affine transform of the remaining blend, so "
            "it barely reorders names -- which is exactly why it was inert. What it did do was "
            "compress every score toward 50, which matters for score levels, stance bands, and "
            "any future calibration that attaches meaning to a score value."
        ),
        "sections": sections,
    }


def main():
    report = build_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    for name, section in report["sections"].items():
        if not section["names"]:
            print(f"{name}: skipped -- {section['status']} "
                  f"({section['excluded_unreproducible_blend']} rows)")
            continue
        delta = section["score_delta"]
        print(f"{name}: n={section['names']} "
              f"covered={section['names_with_news_coverage']} "
              f"mean delta {delta['mean']:+.2f} (min {delta['minimum']:+.2f}, "
              f"max {delta['maximum']:+.2f}), "
              f"{section['names_changing_rank_position']} names change rank position")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
