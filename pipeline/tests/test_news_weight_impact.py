import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import RANKING_WEIGHTS
from news_weight_impact import build_report, compare_section, score_row


def row(ticker="AAA", fundamentals=80.0, market_behavior=60.0, article_count=0,
        news_sentiment=50.0, coverage=0.0):
    """A row shaped like advisor.json's ``research`` entries."""
    components = {"fundamentals": fundamentals, "market_behavior": market_behavior,
                  "news_sentiment": news_sentiment}
    payload = {
        "ticker": ticker,
        "components": components,
        "fundamental_detail": {"coverage": 0.9},
        "technical_detail": {"coverage": 0.8},
        "sentiment_detail": {"coverage": coverage, "article_count": article_count,
                             "news_available": article_count > 0},
        "modifiers": {"applied": {}, "total": 0.0},
    }
    payload["score"] = score_row(payload, drop_unavailable_news=False)
    return payload


class NewsWeightImpactTests(unittest.TestCase):
    def test_uncovered_name_above_neutral_scores_higher_once_news_is_dropped(self):
        uncovered = row(fundamentals=80.0, market_behavior=70.0)
        self.assertGreater(score_row(uncovered, drop_unavailable_news=True),
                           score_row(uncovered, drop_unavailable_news=False))

    def test_uncovered_name_below_neutral_scores_lower_once_news_is_dropped(self):
        """The correction is not a free uplift -- it removes a pull toward 50 in both directions."""
        uncovered = row(fundamentals=30.0, market_behavior=35.0)
        self.assertLess(score_row(uncovered, drop_unavailable_news=True),
                        score_row(uncovered, drop_unavailable_news=False))

    def test_covered_name_is_untouched(self):
        covered = row(article_count=4, news_sentiment=90.0, coverage=0.8)
        self.assertEqual(score_row(covered, drop_unavailable_news=True),
                         score_row(covered, drop_unavailable_news=False))

    def test_rows_whose_published_score_cannot_be_reproduced_are_excluded(self):
        """A delta computed from a blend we cannot reproduce is not evidence.

        The realistic case post-promotion (Round 5 Task 2, 2026-08-12): a row's stored
        score still carries the old coverage multiplier and has not been rescored yet.
        """
        stale = row()
        stale["score"] = round(stale["score"] * 0.85, 1)  # simulate the retired multiplier
        section = compare_section([stale])
        self.assertEqual(section["names"], 0)
        self.assertEqual(section["excluded_unreproducible_blend"], 1)
        self.assertEqual(section["status"], "no_row_reproduces_its_published_score")

    def test_section_summary_counts_coverage_and_rank_movement(self):
        section = compare_section([
            row("AAA", fundamentals=80.0),
            row("BBB", fundamentals=40.0),
            row("CCC", fundamentals=90.0, article_count=3, news_sentiment=95.0, coverage=0.6),
        ])
        self.assertEqual(section["names"], 3)
        self.assertEqual(section["names_with_news_coverage"], 1)
        self.assertEqual(section["names_without_news_coverage"], 2)
        self.assertEqual(section["excluded_unreproducible_blend"], 0)

    def test_report_records_the_news_weight_it_measured(self):
        report = build_report({"generated_at": "2026-08-07T00:00:00+00:00",
                               "research": [row("AAA"), row("BBB", fundamentals=55.0)]})
        self.assertEqual(report["news_weight"], RANKING_WEIGHTS["news_sentiment"])
        self.assertEqual(report["sections"]["research"]["names"], 2)


if __name__ == "__main__":
    unittest.main()
