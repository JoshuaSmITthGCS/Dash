import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evidence_events import (build_evidence, build_expectation_change, build_insider_events,
                             build_news_events, cluster_articles, decay_weight,
                             event_half_life, event_materiality, insider_event_score,
                             news_event_score)

_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "settings.json")
with open(_SETTINGS_PATH) as _fh:
    _SETTINGS = json.load(_fh)
CONFIG = {**_SETTINGS["news_intelligence"], **_SETTINGS["evidence_events"]}

NOW = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)


def article(title, *, days_ago=0, source="Reuters", sentiment=0.8, ticker="MU", summary=""):
    return {
        "title": title,
        "summary": summary,
        "source": source,
        "url": f"https://{source.lower().replace(' ', '')}.com/{abs(hash(title)) % 10000}",
        "published_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "ticker": ticker,
        "ticker_sentiment": [{"ticker": ticker, "ticker_sentiment_score": sentiment}],
    }


class DecayTests(unittest.TestCase):
    def test_one_half_life_halves_the_weight(self):
        self.assertAlmostEqual(decay_weight(5.0, 5.0), 0.5)
        self.assertAlmostEqual(decay_weight(10.0, 5.0), 0.25)

    def test_a_brand_new_event_is_undecayed(self):
        self.assertEqual(decay_weight(0.0, 5.0), 1.0)

    def test_an_undated_event_earns_no_recency_credit(self):
        self.assertEqual(decay_weight(None, 5.0), 0.0)

    def test_age_is_measured_in_trading_days_not_calendar_days(self):
        # A Friday event is not two half-lives old on Monday: 3 calendar days over a weekend
        # is roughly 2 trading days.
        events = build_news_events([article("Co raises FY guidance", days_ago=3)], "MU", CONFIG, now=NOW)
        self.assertAlmostEqual(events[0]["age_trading_days"], 3 / (7 / 5), places=2)


class MaterialityTests(unittest.TestCase):
    """Materiality has to outrank sentiment, or the loudest trivia wins the catalyst screen."""

    def test_a_guidance_raise_outweighs_a_more_positive_puff_piece(self):
        puff = build_news_events(
            [article("Company recognized as a great workplace", sentiment=0.95)], "MU", CONFIG, now=NOW)
        guidance = build_news_events(
            [article("Company raises FY EPS guidance by 18%", sentiment=0.75)], "MU", CONFIG, now=NOW)

        self.assertGreater(guidance[0]["strength"], puff[0]["strength"])

    def test_the_most_material_matched_type_decides_the_weight(self):
        # "CFO resigns amid SEC investigation" is management and regulatory; regulatory is
        # what moves a price.
        self.assertEqual(event_materiality(["management", "regulatory"], CONFIG),
                         CONFIG["event_materiality"]["regulatory"])

    def test_an_unclassified_headline_falls_back_to_routine_commentary(self):
        self.assertEqual(event_materiality([], CONFIG),
                         CONFIG["event_materiality"]["routine_commentary"])
        self.assertEqual(event_half_life([], CONFIG),
                         CONFIG["event_half_life_trading_days"]["routine_commentary"])

    def test_the_slowest_resolving_matched_type_sets_the_half_life(self):
        self.assertEqual(event_half_life(["earnings", "m_and_a"], CONFIG),
                         CONFIG["event_half_life_trading_days"]["m_and_a"])


class ClusteringTests(unittest.TestCase):
    """Seven rewrites of one Reuters story are one catalyst, not seven."""

    def test_syndicated_retellings_collapse_into_one_event(self):
        headline = "Micron raises fiscal year guidance"
        articles = [
            article(headline, source=name, days_ago=0)
            for name in ("Reuters", "MarketWatch", "Benzinga", "Motley Fool", "InvestorPlace")
        ]

        events = build_news_events(articles, "MU", CONFIG, now=NOW)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["article_count"], 5)
        self.assertEqual(events[0]["distinct_sources"], 5)

    def test_the_cluster_keeps_the_earliest_timestamp_when_the_news_reached_the_market(self):
        articles = [
            article("Micron raises fiscal year guidance", source="Benzinga", days_ago=1),
            article("Micron raises fiscal year guidance", source="Reuters", days_ago=2),
        ]

        [event] = build_news_events(articles, "MU", CONFIG, now=NOW)

        self.assertEqual(event["published_at"], (NOW - timedelta(days=2)).isoformat())

    def test_the_cluster_reports_the_best_source_not_the_first_one_seen(self):
        articles = [
            article("Micron raises fiscal year guidance", source="Benzinga", days_ago=2),
            article("Micron raises fiscal year guidance", source="Reuters", days_ago=1),
        ]

        [event] = build_news_events(articles, "MU", CONFIG, now=NOW)

        self.assertEqual(event["source_quality_tier"], "established_press")

    def test_unrelated_stories_stay_separate_events(self):
        articles = [
            article("Micron raises fiscal year guidance"),
            article("Micron names new chief operating officer"),
        ]

        self.assertEqual(len(build_news_events(articles, "MU", CONFIG, now=NOW)), 2)

    def test_the_same_headline_months_apart_is_two_events_not_one(self):
        articles = [
            article("Micron reports quarterly results", days_ago=0),
            article("Micron reports quarterly results", days_ago=95),
        ]

        self.assertEqual(len(cluster_articles(
            [{**a, "_published": datetime.fromisoformat(a["published_at"])} for a in articles],
            CONFIG)), 2)

    def test_coverage_volume_cannot_outrank_materiality(self):
        # Twelve rewrites of a workplace award must not beat one guidance raise.
        puff = [article("Company recognized as a great workplace", source=f"Blog{i}", sentiment=0.95)
                for i in range(12)]
        guidance = [article("Company raises FY EPS guidance by 18%", sentiment=0.75)]

        puff_score, _ = news_event_score(build_news_events(puff, "MU", CONFIG, now=NOW), CONFIG)
        guidance_score, _ = news_event_score(build_news_events(guidance, "MU", CONFIG, now=NOW), CONFIG)

        self.assertGreater(guidance_score, puff_score)


class NewsScoreTests(unittest.TestCase):
    def test_a_fresh_material_event_dominates_a_stale_trivial_one(self):
        events = build_news_events([
            article("Company raises FY EPS guidance by 18%", days_ago=0, sentiment=0.9),
            article("Company publishes routine market commentary", days_ago=35, sentiment=-0.9),
        ], "MU", CONFIG, now=NOW)
        score, detail = news_event_score(events, CONFIG)

        self.assertGreater(score, 60)
        self.assertIn("guidance", detail["dominant_event_types"])

    def test_no_directional_coverage_returns_none_rather_than_a_neutral_fifty(self):
        # "We have nothing" and "we checked and it is neutral" are different claims, and the
        # second one is what made hundreds of uncovered names look reviewed.
        score, detail = news_event_score([], CONFIG)

        self.assertIsNone(score)
        self.assertFalse(detail["available"])

    def test_a_fully_decayed_event_stops_carrying_the_score(self):
        events = build_news_events(
            [article("Company publishes routine commentary", days_ago=400)], "MU", CONFIG, now=NOW)

        self.assertLess(events[0]["recency_weight"], 1e-6)


class InsiderHorizonTests(unittest.TestCase):
    """Insider evidence decays far more slowly than news - that is the whole point of
    modelling evidence per event rather than per category."""

    ACTIVITY = {
        "available": True,
        "buy_cluster": {"insider_count": 3, "total_value": 2_000_000,
                        "days_since_latest": 20, "pattern_confidence": 0.9},
        "sell_cluster": {"insider_count": 0},
    }

    def test_a_three_week_old_purchase_still_carries_weight_on_the_catalyst_horizon(self):
        [event] = build_insider_events(self.ACTIVITY, CONFIG, horizon="catalyst")

        self.assertGreater(event["recency_weight"], 0.5)

    def test_the_long_term_horizon_decays_the_same_purchase_more_slowly_still(self):
        [catalyst] = build_insider_events(self.ACTIVITY, CONFIG, horizon="catalyst")
        [long_term] = build_insider_events(self.ACTIVITY, CONFIG, horizon="long_term")

        self.assertGreater(long_term["recency_weight"], catalyst["recency_weight"])

    def test_an_insider_purchase_outlives_a_news_item_of_the_same_age(self):
        [insider] = build_insider_events(self.ACTIVITY, CONFIG, horizon="catalyst")
        [news] = build_news_events(
            [article("Company publishes routine commentary", days_ago=20)], "MU", CONFIG, now=NOW)

        self.assertGreater(insider["recency_weight"], news["recency_weight"])

    def test_selling_is_discounted_against_buying_of_identical_size_and_freshness(self):
        selling = {
            "available": True,
            "buy_cluster": {"insider_count": 0},
            "sell_cluster": {"insider_count": 3, "total_value": 2_000_000,
                             "days_since_latest": 20, "pattern_confidence": 0.9},
        }
        [buy] = build_insider_events(self.ACTIVITY, CONFIG, horizon="catalyst")
        [sell] = build_insider_events(selling, CONFIG, horizon="catalyst")

        self.assertGreater(abs(buy["strength"]), abs(sell["strength"]))

    def test_an_unavailable_form4_layer_produces_no_events_and_no_score(self):
        self.assertEqual(build_insider_events({"available": False}, CONFIG, horizon="catalyst"), [])
        score, detail = insider_event_score([], CONFIG)
        self.assertIsNone(score)
        self.assertFalse(detail["available"])


class ExpectationChangeTests(unittest.TestCase):
    def test_rising_estimates_and_upgrades_score_above_neutral(self):
        score, detail = build_expectation_change({"estimate_detail": {
            "revision_breadth_30d": 0.75, "eps_revision_30d_pct": 0.12,
            "net_upgrades_90d": 6, "target_change_30d_pct": 24.0,
        }}, CONFIG)

        self.assertGreater(score, 70)
        self.assertEqual(detail["inputs_resolved"], 4)

    def test_falling_estimates_score_below_neutral(self):
        score, _ = build_expectation_change({"estimate_detail": {
            "revision_breadth_30d": -0.8, "eps_revision_30d_pct": -0.15,
        }}, CONFIG)

        self.assertLess(score, 40)

    def test_weights_renormalize_over_whatever_actually_resolved(self):
        score, detail = build_expectation_change(
            {"estimate_detail": {"revision_breadth_30d": 1.0}}, CONFIG)

        self.assertEqual(detail["inputs_resolved"], 1)
        self.assertEqual(score, 100.0)

    def test_no_revision_history_returns_none_rather_than_neutral(self):
        score, detail = build_expectation_change({"estimate_detail": {}}, CONFIG)

        self.assertIsNone(score)
        self.assertFalse(detail["available"])


class EvidenceBlockTests(unittest.TestCase):
    def test_the_published_block_carries_both_insider_horizons(self):
        row = {
            "ticker": "MU",
            "insider_activity": InsiderHorizonTests.ACTIVITY,
            "estimate_detail": {"revision_breadth_30d": 0.5},
        }

        evidence = build_evidence(row, [article("Micron raises fiscal year guidance")], CONFIG, now=NOW)

        self.assertGreater(evidence["news_score"], 50)
        self.assertGreater(evidence["insider_score_long_term"], evidence["insider_score"])
        self.assertTrue(evidence["expectation_detail"]["available"])

    def test_a_company_with_no_evidence_at_all_scores_nothing_rather_than_neutral(self):
        evidence = build_evidence({"ticker": "QUIET"}, [], CONFIG, now=NOW)

        self.assertIsNone(evidence["news_score"])
        self.assertIsNone(evidence["insider_score"])
        self.assertIsNone(evidence["expectation_score"])

    def test_the_published_event_list_is_bounded(self):
        articles = [article(f"Micron unrelated story number {i}", days_ago=i % 5) for i in range(40)]

        evidence = build_evidence({"ticker": "MU"}, articles, CONFIG, now=NOW)

        self.assertLessEqual(len(evidence["news_events"]), CONFIG["published_event_limit"])


if __name__ == "__main__":
    unittest.main()
