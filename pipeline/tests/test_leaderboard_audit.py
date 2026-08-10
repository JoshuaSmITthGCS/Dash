"""The leaderboard audit: does the published ranking order companies, or order data volume?

This is the one measurement in `research/` that rests on no backtest, so it survives whatever
turns out to be true about valuation or survivorship. That makes it worth guarding: its failure
mode is not an exception but a reassuring verdict on a leaderboard that is in fact stratified
by which companies received a data pull.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "research"))

from audit_leaderboard import audit  # noqa: E402


def company(ticker, score, *, enriched=True):
    categories = {"valuation": 80.0, "profitability": 80.0,
                  "financial_health": 80.0, "growth": 80.0}
    if enriched:
        categories.update({"capital_allocation": 80.0, "accounting_quality": 80.0})
    return {"ticker": ticker, "score": score, "is_etf": False,
            "fundamental_categories": categories}


def artifact(*, enriched_high=True):
    """Forty enriched companies and eighty thin ones, with the enriched scoring higher."""
    research = [company(f"E{index}", 90 - index, enriched=True) for index in range(40)]
    screen = [company(f"T{index}", (40 if enriched_high else 95) - index * 0.1, enriched=False)
              for index in range(80)]
    return {"research": research, "screen_universe": screen,
            "enrichment_selection": {"previous_top": [f"E{index}" for index in range(20)],
                                     "challengers": ["X1"], "priority_count": 21}}


def test_a_leaderboard_stratified_by_data_volume_is_called_out():
    report = audit(artifact())
    assert report["concentration"]["top_40"]["from_enriched_cohort"] == 40
    assert report["best_rank_without_enrichment"] == 41
    assert "not comparable" in report["verdict"]
    assert "thinner evidence base" in report["verdict"]


def test_the_self_reinforcing_loop_is_named_when_priority_comes_from_the_ranking():
    report = audit(artifact())
    assert report["enrichment_loop"]["priority_source"] == "previous_top"
    assert report["enrichment_loop"]["top_carried_over_from_previous"] == 1.0
    assert "already had it" in report["verdict"]


def test_a_leaderboard_that_is_not_stratified_passes():
    """Thin companies topping the ranking means the score is not tracking data volume."""
    report = audit(artifact(enriched_high=False))
    assert report["concentration"]["top_40"]["from_enriched_cohort"] < 40
    assert "No disproportionate concentration" in report["verdict"]


def test_the_score_gap_between_cohorts_is_measured_not_assumed():
    report = audit(artifact())
    gap = report["lighter_cohort_score_gap"]
    assert gap["without"]["count"] == 80
    assert gap["with_enrichment_categories"]["count"] == 0


def test_an_empty_artifact_reports_an_error_rather_than_a_clean_bill():
    assert "error" in audit({"research": [], "screen_universe": []})
