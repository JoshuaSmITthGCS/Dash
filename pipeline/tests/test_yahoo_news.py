import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evidence_events import build_news_events, news_event_score
from yahoo_news import (annotate_direction, fetch_company_news, headline_direction,
                        is_aggregator, new_diagnostics, normalize_article)

_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "settings.json")
with open(_SETTINGS_PATH) as _fh:
    _SETTINGS = json.load(_fh)
CONFIG = {**_SETTINGS["news_intelligence"], **_SETTINGS["evidence_events"]}

NOW = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)


def stream_item(title, *, source="Reuters", summary="", published="2026-08-08T12:00:00Z",
                url="https://reuters.com/story-1"):
    """The nested shape current yfinance returns from Yahoo's ncp stream."""
    return {
        "id": "abc123",
        "content": {
            "contentType": "STORY",
            "title": title,
            "summary": summary,
            "description": summary,
            "pubDate": published,
            "provider": {"displayName": source},
            "canonicalUrl": {"url": url},
            "clickThroughUrl": {"url": url},
        },
    }


def flat_item(title, *, source="Reuters", url="https://reuters.com/story-1", epoch=1786000000):
    """The older flat shape yfinance used to return."""
    return {"title": title, "publisher": source, "link": url, "providerPublishTime": epoch,
            "type": "STORY"}


class NormalizationTests(unittest.TestCase):
    """yfinance has served two different news shapes. Understanding only one of them loses
    the entire news leg the day the dependency moves."""

    def test_reads_the_current_nested_stream_item(self):
        article = normalize_article(stream_item("Micron raises FY guidance"), "MU")

        self.assertEqual(article["title"], "Micron raises FY guidance")
        self.assertEqual(article["source"], "Reuters")
        self.assertEqual(article["url"], "https://reuters.com/story-1")
        self.assertEqual(article["published_at"], "2026-08-08T12:00:00Z")
        self.assertEqual(article["ticker"], "MU")

    def test_reads_the_older_flat_item_and_converts_its_epoch_timestamp(self):
        article = normalize_article(flat_item("Micron raises FY guidance"), "MU")

        self.assertEqual(article["source"], "Reuters")
        self.assertTrue(article["published_at"].startswith("20"))

    def test_an_item_with_no_title_is_dropped_rather_than_published_untitled(self):
        self.assertIsNone(normalize_article({"content": {"summary": "no headline"}}, "MU"))
        self.assertIsNone(normalize_article("not a dict", "MU"))

    def test_a_missing_timestamp_degrades_to_empty_rather_than_raising(self):
        article = normalize_article({"content": {"title": "Untimed story"}}, "MU")

        self.assertEqual(article["published_at"], "")

    def test_yahoo_syndication_is_recognized_as_an_aggregator(self):
        self.assertTrue(is_aggregator({"source": "Yahoo Finance", "url": "https://finance.yahoo.com/x"}))
        self.assertFalse(is_aggregator({"source": "Reuters", "url": "https://reuters.com/x"}))


class HeadlineDirectionTests(unittest.TestCase):
    """Yahoo's feed carries no sentiment at all, so direction comes from a phrase lexicon.
    It is a keyword match, not a sentiment model, and it has to behave like one."""

    def test_a_guidance_raise_reads_strongly_positive(self):
        direction, marker = headline_direction({"title": "Micron raises FY guidance"}, CONFIG)

        self.assertGreater(direction, 0.8)
        self.assertEqual(marker, "raises fy guidance")

    def test_a_guidance_cut_reads_strongly_negative(self):
        direction, marker = headline_direction({"title": "Acme cuts full-year guidance"}, CONFIG)

        self.assertLess(direction, -0.8)
        self.assertEqual(marker, "cuts full-year guidance")

    def test_the_strongest_marker_wins_rather_than_the_sum_of_mild_ones(self):
        # Headlines are short. Summing lets incidental positives dilute one decisive negative.
        direction, marker = headline_direction(
            {"title": "Acme announces buyback and raises dividend but cuts full-year guidance"}, CONFIG)

        self.assertLess(direction, 0)
        self.assertEqual(marker, "cuts full-year guidance")

    def test_an_unmatched_headline_carries_no_direction_rather_than_a_neutral_guess(self):
        direction, marker = headline_direction(
            {"title": "Acme to present at an industry conference"}, CONFIG)

        self.assertIsNone(direction)
        self.assertIsNone(marker)

    def test_the_summary_is_searched_as_well_as_the_title(self):
        direction, _ = headline_direction(
            {"title": "Acme reports Q2", "summary": "The company cuts guidance for the year."}, CONFIG)

        self.assertLess(direction, 0)


class DirectionAnnotationTests(unittest.TestCase):
    def test_provider_sentiment_is_never_overwritten_by_the_lexicon(self):
        # A model over the article body outranks a keyword match on its title.
        scored = {"title": "Acme cuts full-year guidance", "ticker": "ACME",
                  "ticker_sentiment": [{"ticker": "ACME", "ticker_sentiment_score": 0.4}]}

        [annotated] = annotate_direction([scored], CONFIG)

        self.assertNotIn("headline_direction", annotated)

    def test_an_article_with_no_provider_score_gets_the_derived_one(self):
        [annotated] = annotate_direction([{"title": "Acme raises guidance"}], CONFIG)

        self.assertGreater(annotated["headline_direction"], 0)
        self.assertEqual(annotated["headline_direction_marker"], "raises guidance")


class EventIntegrationTests(unittest.TestCase):
    """The whole point of wiring this up: the catalyst model had no universe to score."""

    def test_a_yahoo_article_now_produces_a_scorable_event(self):
        articles = annotate_direction(
            [normalize_article(stream_item("Micron raises FY guidance"), "MU")], CONFIG)

        events = build_news_events(articles, "MU", CONFIG, now=NOW)
        score, detail = news_event_score(events, CONFIG)

        self.assertGreater(score, 60)
        self.assertTrue(detail["available"])
        self.assertEqual(events[0]["direction_source"], "headline_lexicon")

    def test_the_published_event_says_the_direction_came_from_a_keyword_match(self):
        articles = annotate_direction(
            [normalize_article(stream_item("Micron raises FY guidance"), "MU")], CONFIG)

        _, detail = news_event_score(build_news_events(articles, "MU", CONFIG, now=NOW), CONFIG)

        self.assertEqual(detail["lexicon_scored_events"], 1)
        self.assertEqual(detail["provider_scored_events"], 0)

    def test_coverage_with_no_readable_direction_is_recorded_but_scores_nothing(self):
        articles = annotate_direction(
            [normalize_article(stream_item("Micron to present at a conference"), "MU")], CONFIG)

        events = build_news_events(articles, "MU", CONFIG, now=NOW)
        score, detail = news_event_score(events, CONFIG)

        self.assertEqual(len(events), 1)          # the coverage is real
        self.assertIsNone(events[0]["strength"])  # but it says nothing directional
        self.assertIsNone(score)
        self.assertFalse(detail["available"])

    def test_a_provider_reading_wins_the_event_over_a_yahoo_copy_of_the_same_story(self):
        # Averaging the two would dilute a measured sentiment with a keyword guess.
        headline = "Micron raises FY guidance"
        provider_copy = {
            "title": headline, "source": "Marketaux", "url": "https://marketaux.com/a",
            "published_at": "2026-08-08T12:00:00Z", "ticker": "MU",
            "ticker_sentiment": [{"ticker": "MU", "ticker_sentiment_score": 0.2}],
        }
        yahoo_copy = normalize_article(stream_item(headline), "MU")

        events = build_news_events(annotate_direction([provider_copy, yahoo_copy], CONFIG),
                                   "MU", CONFIG, now=NOW)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction_source"], "provider_entity")
        self.assertAlmostEqual(events[0]["direction"], 0.2, places=3)

    def test_a_guidance_cut_produces_the_negative_event_the_reversal_gate_looks_for(self):
        articles = annotate_direction(
            [normalize_article(stream_item("Acme cuts full-year guidance"), "ACME")], CONFIG)

        events = build_news_events(articles, "ACME", CONFIG, now=NOW)
        score, detail = news_event_score(events, CONFIG)

        self.assertLess(score, 20)
        self.assertIn("guidance", detail["dominant_event_types"])


class _FakeTicker:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def get_news(self, count=10, tab="news"):
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FetchTests(unittest.TestCase):
    def test_fetches_normalizes_and_annotates_in_one_call(self):
        ticker = _FakeTicker([stream_item("Micron raises FY guidance"),
                              stream_item("Micron opens a new office", url="https://reuters.com/2")])

        articles = fetch_company_news("MU", ticker, CONFIG)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["provider_feed"], "yahoo_news")
        self.assertGreater(articles[0]["headline_direction"], 0)

    def test_a_dark_feed_degrades_this_company_rather_than_the_run(self):
        articles = fetch_company_news("MU", _FakeTicker(RuntimeError("Yahoo is down")), CONFIG)

        self.assertEqual(articles, [])

    def test_no_ticker_object_means_no_request_and_no_error(self):
        self.assertEqual(fetch_company_news("MU", None, CONFIG), [])

    def test_repeated_requests_inside_the_ttl_are_served_from_cache(self):
        # A fast refresh polls the same leaders every few minutes; re-requesting identical
        # headlines each time is wasted quota against a provider with no contract.
        class _Cache:
            def __init__(self):
                self.store = {}

            def fetch(self, namespace, key, producer, source=None):
                if key not in self.store:
                    self.store[key] = producer()
                return self.store[key]

        ticker = _FakeTicker([stream_item("Micron raises FY guidance")])
        cache = _Cache()

        fetch_company_news("MU", ticker, CONFIG, cache=cache)
        fetch_company_news("MU", ticker, CONFIG, cache=cache)

        self.assertEqual(ticker.calls, 1)


class ShapeChangeVisibilityTests(unittest.TestCase):
    """yfinance passes Yahoo's stream items through untouched, so this parses an undocumented
    third-party shape. If it changes, every item fails to normalize - and that has to surface
    as "received items and could read none" rather than as "no news happened", which is the
    exact failure mode the Form 4 layer had."""

    def test_items_received_and_items_read_are_counted_separately(self):
        diagnostics = new_diagnostics()
        ticker = _FakeTicker([stream_item("Micron raises FY guidance"),
                              stream_item("Second story", url="https://reuters.com/2")])

        fetch_company_news("MU", ticker, CONFIG, diagnostics=diagnostics)

        self.assertEqual(diagnostics["items_received"], 2)
        self.assertEqual(diagnostics["items_normalized"], 2)
        self.assertEqual(diagnostics["symbols_with_news"], 1)

    def test_an_unrecognized_payload_shape_records_received_but_unreadable(self):
        diagnostics = new_diagnostics()
        # What a Yahoo field rename looks like from here: items arrive, none can be read.
        ticker = _FakeTicker([{"unexpected": {"headline": "Micron raises FY guidance"}}])

        articles = fetch_company_news("MU", ticker, CONFIG, diagnostics=diagnostics)

        self.assertEqual(articles, [])
        self.assertEqual(diagnostics["items_received"], 1)
        self.assertEqual(diagnostics["items_normalized"], 0)
        self.assertEqual(diagnostics["symbols_with_news"], 0)

    def test_a_cache_hit_does_not_consume_a_yahoo_rate_limit_slot(self):
        # One request per polled symbol against a provider that publishes no rate limit and
        # is already paced at 4/s; charging the limiter for cache hits too would throttle the
        # run for traffic that never left the machine.
        from cache import limiter_for

        class _CountingLimiter:
            def __init__(self):
                self.acquired = 0

            def acquire(self):
                self.acquired += 1
                return 0.0

        class _Cache:
            def __init__(self):
                self.store = {}

            def fetch(self, namespace, key, producer, source=None):
                if key not in self.store:
                    self.store[key] = producer()
                return self.store[key]

        limiter = _CountingLimiter()
        cache = _Cache()
        ticker = _FakeTicker([stream_item("Micron raises FY guidance")])
        with mock.patch.object(sys.modules["cache"], "limiter_for", lambda name: limiter):
            fetch_company_news("MU", ticker, CONFIG, cache=cache)
            fetch_company_news("MU", ticker, CONFIG, cache=cache)

        self.assertEqual(limiter.acquired, 1)
        self.assertEqual(ticker.calls, 1)
        self.assertIsNotNone(limiter_for)  # the real helper is what production resolves

    def test_a_failing_feed_is_counted_apart_from_an_unreadable_one(self):
        # Different problems with different fixes: one is an outage, the other is a defect
        # in this parser.
        diagnostics = new_diagnostics()

        fetch_company_news("MU", _FakeTicker(RuntimeError("down")), CONFIG, diagnostics=diagnostics)

        self.assertEqual(diagnostics["feed_failures"], 1)
        self.assertEqual(diagnostics["items_received"], 0)


if __name__ == "__main__":
    unittest.main()
