"""Structural guards on the EDGAR client.

A second ``company_facts`` defined 200 lines below an earlier one silently shadowed it.
Python takes the last definition, so the point-in-time backfill passed a CIK into a method
expecting a ticker, the lookup missed, and it returned an empty dict -- which read as a
successful fetch. Twenty-five companies reported "ok" with zero facts, and no unit test
caught it because the tests used a stub client. These are the guards that would have.
"""

import ast
import os
import sys
import unittest
from collections import Counter

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from sec_edgar import SecEdgarClient


def duplicate_methods(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        names = Counter(child.name for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)))
        repeated = sorted(name for name, count in names.items() if count > 1)
        if repeated:
            found[node.name] = repeated
    return found


class NoShadowedMethodsTest(unittest.TestCase):
    def test_no_class_in_the_pipeline_defines_a_method_twice(self):
        offenders = {}
        for root, _, files in os.walk(PIPELINE_DIR):
            if "tests" in root or "__pycache__" in root:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                for klass, methods in duplicate_methods(path).items():
                    offenders[f"{os.path.relpath(path, PIPELINE_DIR)}:{klass}"] = methods
        self.assertEqual(offenders, {},
                         "a later definition silently replaces the earlier one")

    def test_the_detector_actually_detects(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
            handle.write("class A:\n    def f(self): pass\n    def f(self): pass\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        self.assertEqual(duplicate_methods(path), {"A": ["f"]})


class ClientSurfaceTest(unittest.TestCase):
    """The two fact accessors take different keys and must stay distinguishable."""

    def test_both_accessors_exist_and_are_distinct(self):
        self.assertTrue(callable(SecEdgarClient.company_facts_by_cik))
        self.assertTrue(callable(SecEdgarClient.company_facts))
        self.assertIsNot(SecEdgarClient.company_facts_by_cik, SecEdgarClient.company_facts)

    def test_the_cik_accessor_zero_pads_and_hits_the_companyfacts_endpoint(self):
        seen = {}

        class Recording(SecEdgarClient):
            def _get(self, url, as_json=False, **kwargs):
                seen["url"] = url
                return {"facts": {}}

        Recording(user_agent="test test@example.com").company_facts_by_cik(320193)
        self.assertEqual(
            seen["url"], "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")

    def test_the_ticker_accessor_delegates_rather_than_duplicating_the_url(self):
        calls = []

        class Recording(SecEdgarClient):
            def ticker_map(self):
                return {"AAPL": "0000320193"}

            def company_facts_by_cik(self, cik):
                calls.append(cik)
                return {"facts": {}}

        Recording(user_agent="test test@example.com").company_facts("AAPL")
        self.assertEqual(calls, ["0000320193"])


if __name__ == "__main__":
    unittest.main()
