"""A1 — measure and land the news-availability fix on the committed champion data.

``fetch_advisor.py`` needs live Yahoo/Alpha Vantage/marketaux access to re-run from scratch,
which this environment's network policy blocks. But the A1 fix (news_intelligence.py
returning ``None``/``news_available: False`` instead of a fabricated neutral 50.0 when no
news cleared the coverage window) only changes one input to a handful of already-tested pure
functions -- ``blend_research_components``, ``stance_for``, ``action_for``. Every input those
functions need is already sitting on each published row from the last real fetch, so the fix
can be measured and applied to the committed ``advisor.json`` without any network call, the
same principle ``rescore.py`` uses for the v2 shadow layer.

What gets recomputed, and why each is safe to trust from stored fields alone:
  * ``raw_score`` / ``base_score`` / ``confidence`` / ``score`` -- pure functions of
    ``components``, coverage (read from ``fundamental_detail``/``technical_detail``/
    ``sentiment_detail``), and ``modifiers.total`` (already computed and capped).
  * ``stance`` -- pure function of the new score and confidence.
  * ``recommendation`` -- ``action_for`` takes ``fundamental_detail``, ``technical_detail``,
    ``sentiment_detail`` verbatim, plus an ``extended`` dict it only ``.get()``s from; the row
    itself is a superset of the extended fields ``build_research`` originally merged in, so
    passing the row itself reproduces the same lookups.

What is deliberately left untouched, and why:
  * ``strengths`` / ``risks`` -- ``build_evidence`` never reads the news component at all.
  * ``recommendation_v2`` / ``analysis_v2`` -- shadow-only fields (see advisor_engine.py's own
    comment: "legacy recommendation remains the production field"); recomputing them needs
    portfolio/position context this script has no reason to fabricate.

Every row's *current* score and recommendation are reproduced exactly from its own stored
fields before the fix is applied (see ``pipeline/tests/test_news_fix_impact.py``), which is
the check that this reconstruction is faithful rather than approximate.
"""

import json
import os

from advisor_engine import action_for, blend_research_components, clamp, stance_for
from common import load_json, save_json

REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "news_fix_score_delta.json")


def _coverage(row):
    return {
        "fundamentals": (row.get("fundamental_detail") or {}).get("coverage", 0.0),
        "market_behavior": (row.get("technical_detail") or {}).get("coverage", 0.0),
        "news_sentiment": (row.get("sentiment_detail") or {}).get("coverage", 0.0),
    }


def _news_was_unavailable(row):
    """Reconstructs weighted_sentiment's own condition (``not articles or total_weight <= 0``)
    from the coverage it already published: coverage is exactly article_count divided by a
    positive constant, so coverage <= 0 iff there was zero cleared coverage.
    """
    return ((row.get("sentiment_detail") or {}).get("coverage") or 0) <= 0


def reconstruct_score(row):
    """Recompute raw_score/base_score/confidence/score exactly as build_research does under
    the A1 fix (news_sentiment excluded, not neutral, when coverage is zero), from fields
    already on the row.
    """
    components = dict(row.get("components") or {})
    coverage = _coverage(row)
    unavailable = _news_was_unavailable(row)
    if unavailable:
        components["news_sentiment"] = None
    blend = blend_research_components(components, coverage)
    total = (row.get("modifiers") or {}).get("total", 0.0)
    score = round(clamp(blend["base_score"] + total), 1)
    return {
        "raw_score": blend["raw_score"], "base_score": blend["base_score"],
        "confidence": blend["confidence"], "score": score,
        "components": components, "news_available": not unavailable,
    }


def recompute_row(row):
    """Return ``(before, after)`` score/stance/recommendation, both reconstructed the same
    way, differing only in whether a row with zero news coverage is scored neutral (before,
    the behavior the row was actually published under) or excluded (after, the A1 fix). A
    row with real news coverage is identical in both, since only the zero-coverage case
    changes under the fix.
    """
    components_pre = dict(row.get("components") or {})
    if _news_was_unavailable(row):
        components_pre["news_sentiment"] = 50.0  # the neutral_score constant this fix removed
    coverage = _coverage(row)
    total = (row.get("modifiers") or {}).get("total", 0.0)
    blend_pre = blend_research_components(components_pre, coverage)
    before = {
        "raw_score": blend_pre["raw_score"], "base_score": blend_pre["base_score"],
        "confidence": blend_pre["confidence"],
        "score": round(clamp(blend_pre["base_score"] + total), 1),
        "components": components_pre, "news_available": not _news_was_unavailable(row),
    }
    after = reconstruct_score(row)

    for state in (before, after):
        state["stance"] = stance_for(state["score"], state["confidence"])
        state["recommendation"] = action_for(
            state["score"], state["stance"], row.get("fundamental_detail") or {},
            row.get("technical_detail") or {}, row, row.get("sentiment_detail") or {},
        )
    return before, after


def build_delta_report(payload):
    collections = {
        "research": payload.get("research") or [],
        "screen_universe": payload.get("screen_universe") or [],
        "portfolio_coverage": payload.get("portfolio_coverage") or [],
    }
    report_rows = {}
    summary = {}
    for label, rows in collections.items():
        deltas = []
        for row in rows:
            ticker = row.get("ticker")
            if not ticker or "components" not in row:
                continue
            before, after = recompute_row(row)
            deltas.append({
                "ticker": ticker, "score_before": before["score"], "score_after": after["score"],
                "score_delta": round(after["score"] - before["score"], 2),
                "stance_before": before["stance"], "stance_after": after["stance"],
                "action_before": before["recommendation"]["action"],
                "action_after": after["recommendation"]["action"],
                "news_available": after["news_available"],
            })
        report_rows[label] = deltas
        changed = [row for row in deltas if row["score_delta"] != 0]
        summary[label] = {
            "rows": len(deltas),
            "rows_with_no_news_coverage": sum(1 for row in deltas if not row["news_available"]),
            "rows_changed": len(changed),
            "mean_delta": round(sum(row["score_delta"] for row in changed) / len(changed), 3) if changed else 0.0,
            "max_delta": max((row["score_delta"] for row in changed), default=0.0),
            "stance_changes": sum(1 for row in deltas if row["stance_before"] != row["stance_after"]),
            "action_changes": sum(1 for row in deltas if row["action_before"] != row["action_after"]),
        }
    if report_rows["research"]:
        before_rank = [row["ticker"] for row in
                      sorted(report_rows["research"], key=lambda row: -row["score_before"])]
        after_rank = [row["ticker"] for row in
                     sorted(report_rows["research"], key=lambda row: -row["score_after"])]
        summary["research"]["rank_position_changes"] = sum(
            1 for ticker in before_rank if before_rank.index(ticker) != after_rank.index(ticker)
        )
    return {
        "method": (
            "raw_score/base_score/confidence/score reconstructed via "
            "advisor_engine.blend_research_components from each row's own stored components, "
            "coverage, and modifiers.total; stance via stance_for; recommendation via "
            "action_for. strengths/risks/recommendation_v2/analysis_v2 are unaffected by the "
            "news component and were not recomputed. No network calls."
        ),
        "summary": summary,
        "changed_rows": {
            label: sorted((row for row in rows if row["score_delta"] != 0),
                          key=lambda row: -abs(row["score_delta"]))
            for label, rows in report_rows.items()
        },
    }


def apply_news_fix(payload):
    """Mutate research/screen_universe/portfolio_coverage rows in place to the corrected
    (post-fix) score/stance/recommendation/components, landing A1 on the champion.
    """
    touched = 0
    for collection in ("research", "screen_universe", "portfolio_coverage"):
        for row in payload.get(collection) or []:
            if "components" not in row or not row.get("ticker"):
                continue
            _, after = recompute_row(row)
            row["raw_score"] = after["raw_score"]
            row["base_score"] = after["base_score"]
            row["confidence"] = after["confidence"]
            row["score"] = after["score"]
            row["stance"] = after["stance"]
            row["recommendation"] = after["recommendation"]
            row["components"] = after["components"]
            row["news_available"] = after["news_available"]
            if isinstance(row.get("sentiment_detail"), dict):
                row["sentiment_detail"]["news_available"] = after["news_available"]
            touched += 1
    if payload.get("research"):
        payload["research"].sort(key=lambda row: row.get("score") or 0, reverse=True)
    return touched


def main():
    payload = load_json("advisor.json")
    if not payload:
        raise SystemExit("advisor.json is missing - run fetch_advisor.py at least once first")
    report = build_delta_report(payload)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    temporary = f"{REPORT_PATH}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, REPORT_PATH)
    touched = apply_news_fix(payload)
    save_json("advisor.json", payload)
    research_summary = report["summary"]["research"]
    print(f"Wrote {REPORT_PATH}")
    print(f"research: {research_summary['rows_changed']}/{research_summary['rows']} changed, "
          f"mean delta {research_summary['mean_delta']:+.2f}, max {research_summary['max_delta']:+.2f}, "
          f"{research_summary.get('rank_position_changes', 0)} rank position changes")
    print(f"Applied corrected score/stance/recommendation to {touched} rows in advisor.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
