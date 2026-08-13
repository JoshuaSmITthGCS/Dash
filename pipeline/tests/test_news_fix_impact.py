import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import build_research
from news_fix_impact import apply_news_fix, build_delta_report, recompute_row


def _row_with_no_news():
    snap = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18}
    closes = [100 + index * 0.2 for index in range(300)]
    return build_research("TEST", snap, closes, closes, [])


def _row_with_news():
    # Timestamped near "now" (no `now` override on build_research/sentiment_score) so the
    # article stays inside the default coverage window regardless of when the test runs.
    from datetime import datetime, timedelta, timezone
    published_at = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y%m%dT%H%M%S")
    snap = {"ticker": "TEST2", "name": "Test Co 2", "sector": "Technology", "is_etf": False,
            "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18}
    closes = [100 + index * 0.2 for index in range(300)]
    news = [{
        "ticker": "TEST2", "source": "reuters.com", "url": "https://reuters.com/story",
        "title": "Test Co 2 beats expectations", "published_at": published_at,
        "ticker_sentiment": [{"ticker": "TEST2", "ticker_sentiment_score": 0.4, "relevance_score": 0.9}],
    }]
    return build_research("TEST2", snap, closes, closes, news)


class ReconstructionFidelityTests(unittest.TestCase):
    """The reconstruction must reproduce a row's *actual current* published score and
    recommendation before it can be trusted to compute a corrected one -- this is the same
    row already built entirely under the new (fixed) code, so `recompute_row`'s `after`
    state must exactly match what's already on the row, and `before` must reproduce the
    pre-fix neutral-scoring behavior for the no-coverage case specifically.
    """

    def test_after_state_matches_the_rows_own_published_score_when_news_is_unavailable(self):
        row = _row_with_no_news()
        self.assertFalse(row["news_available"])
        before, after = recompute_row(row)
        self.assertEqual(after["score"], row["score"])
        self.assertEqual(after["stance"], row["stance"])
        self.assertEqual(after["recommendation"]["action"], row["recommendation"]["action"])

    def test_before_state_reproduces_the_neutral_scoring_the_fix_removed(self):
        row = _row_with_no_news()
        before, after = recompute_row(row)
        self.assertEqual(before["components"]["news_sentiment"], 50.0)
        # Neutral news pulls the blend toward 50 relative to excluding it entirely; the
        # direction of the delta depends on whether the row scores above or below 50
        # elsewhere, but the two states must differ whenever coverage is genuinely zero.
        self.assertNotEqual(before["score"], after["score"])

    def test_rows_with_real_news_coverage_are_identical_before_and_after(self):
        row = _row_with_news()
        self.assertTrue(row["news_available"])
        before, after = recompute_row(row)
        self.assertEqual(before["score"], after["score"])
        self.assertEqual(before["components"]["news_sentiment"], after["components"]["news_sentiment"])


class DeltaReportTests(unittest.TestCase):
    def test_report_flags_rows_without_news_coverage_and_sums_deltas(self):
        payload = {"research": [_row_with_no_news(), _row_with_news()], "screen_universe": [], "portfolio_coverage": []}
        report = build_delta_report(payload)
        summary = report["summary"]["research"]
        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["rows_with_no_news_coverage"], 1)
        self.assertEqual(summary["rows_changed"], 1)

    def test_never_fabricates_a_mean_delta_when_nothing_changed(self):
        payload = {"research": [_row_with_news()], "screen_universe": [], "portfolio_coverage": []}
        report = build_delta_report(payload)
        self.assertEqual(report["summary"]["research"]["mean_delta"], 0.0)


class ApplyFixTests(unittest.TestCase):
    def test_apply_news_fix_is_idempotent_on_an_already_fixed_row(self):
        # A row built under the already-fixed code is the "after" state applied to a row
        # still carrying legacy (pre-fix) values would produce - applying the fix a second
        # time must be a no-op, proving apply_news_fix reconstructs rather than double-counts.
        row = _row_with_no_news()
        original_score = row["score"]
        payload = {"research": [row], "screen_universe": [], "portfolio_coverage": []}
        touched = apply_news_fix(payload)
        self.assertEqual(touched, 1)
        self.assertIsNone(payload["research"][0]["components"]["news_sentiment"])
        self.assertFalse(payload["research"][0]["news_available"])
        self.assertEqual(payload["research"][0]["score"], original_score)

    def test_apply_news_fix_corrects_a_row_still_carrying_the_pre_fix_neutral_score(self):
        # A hand-built row simulating legacy production data: components.news_sentiment
        # published at the old neutral 50.0 constant, with score/base_score/raw_score
        # computed under the pre-fix formula that included it - and zero cleared coverage,
        # which is what should have triggered exclusion under the fix.
        row = {
            "ticker": "LEGACY", "sector": "Technology",
            "components": {"fundamentals": 80.0, "market_behavior": 60.0, "news_sentiment": 50.0},
            "fundamental_detail": {"coverage": 1.0}, "technical_detail": {"coverage": 1.0},
            "sentiment_detail": {"coverage": 0.0, "average": None, "article_count": 0},
            "modifiers": {"total": 0.0},
        }
        from advisor_engine import blend_research_components
        pre_fix_blend = blend_research_components(
            row["components"],
            {"fundamentals": 1.0, "market_behavior": 1.0, "news_sentiment": 0.0},
        )
        row["score"] = pre_fix_blend["score"]
        stale_score = row["score"]

        payload = {"research": [row], "screen_universe": [], "portfolio_coverage": []}
        apply_news_fix(payload)
        fixed = payload["research"][0]

        self.assertIsNone(fixed["components"]["news_sentiment"])
        self.assertNotEqual(fixed["score"], stale_score)

    def test_apply_news_fix_resorts_research_by_new_score(self):
        low = _row_with_no_news()
        low["ticker"] = "LOW"
        high = _row_with_news()
        high["ticker"] = "HIGH"
        high["score"] = 10.0  # force an artificially low stored score, pre-resort
        payload = {"research": [high, low], "screen_universe": [], "portfolio_coverage": []}
        apply_news_fix(payload)
        scores = [row["score"] for row in payload["research"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
