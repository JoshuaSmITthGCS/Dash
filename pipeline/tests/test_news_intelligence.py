import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_intelligence import annotate_article, classify_event_type
from scorer import SETTINGS

CONFIG = SETTINGS["news_intelligence"]


class ClassifyEventTypeTests(unittest.TestCase):
    def test_classifies_an_earnings_headline(self):
        item = {"title": "Acme Corp reports Q2 results, beats on EPS", "summary": ""}
        self.assertIn("earnings", classify_event_type(item, CONFIG))

    def test_classifies_an_analyst_revision_headline(self):
        item = {"title": "Bank of America upgrades Acme Corp, raises price target", "summary": ""}
        self.assertIn("analyst_revision", classify_event_type(item, CONFIG))

    def test_classifies_a_political_disclosure_headline(self):
        item = {"title": "Senator files periodic transaction report on Acme Corp stock", "summary": ""}
        self.assertIn("political_disclosure", classify_event_type(item, CONFIG))

    def test_a_headline_can_belong_to_more_than_one_category(self):
        item = {"title": "Acme Corp CFO resigns amid SEC investigation", "summary": ""}
        result = classify_event_type(item, CONFIG)
        self.assertIn("management", result)
        self.assertIn("regulatory", result)

    def test_routine_commentary_with_no_event_marker_returns_empty_not_a_default(self):
        item = {"title": "Why investors are watching the tech sector this week", "summary": ""}
        self.assertEqual(classify_event_type(item, CONFIG), [])

    def test_matches_against_summary_as_well_as_title(self):
        item = {"title": "Acme Corp update", "summary": "The company announced a new product launch today."}
        self.assertIn("product", classify_event_type(item, CONFIG))


class AnnotateArticleTests(unittest.TestCase):
    def test_annotated_articles_carry_event_types(self):
        item = {"title": "Acme Corp reports quarterly results", "source": "reuters.com", "url": ""}
        annotated = annotate_article(item, CONFIG)
        self.assertIn("event_types", annotated)
        self.assertIn("earnings", annotated["event_types"])

    def test_existing_fields_are_unchanged(self):
        item = {"title": "Acme Corp reports quarterly results", "source": "reuters.com", "url": ""}
        annotated = annotate_article(item, CONFIG)
        self.assertIn("content_type", annotated)
        self.assertIn("source_quality_tier", annotated)
        self.assertIn("source_quality_weight", annotated)


if __name__ == "__main__":
    unittest.main()
