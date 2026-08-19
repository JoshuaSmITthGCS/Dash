import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import edgar_enrichment as ee


class _FakeLog:
    def __init__(self):
        self.warnings = []

    def warn(self, message):
        self.warnings.append(message)

    def info(self, message):
        pass

    def error(self, message):
        pass


class SilentEdgarFallbackFailureTests(unittest.TestCase):
    """A broken EDGAR PIT lookup used to disappear with zero trace: merge_edgar_fallback
    caught the exception and returned the provider's original result unchanged, giving no
    signal that the fallback itself never ran. A systemic cause (a corrupt shard, a bad
    entity-map entry) could silently disable the fallback for the whole universe."""

    def test_a_broken_edgar_lookup_is_logged_not_swallowed_silently(self):
        fake_log = _FakeLog()
        original_log = ee.LOG
        original_edgar_extended = ee.edgar_extended
        ee.LOG = fake_log
        ee.edgar_extended = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("shard read failed"))
        try:
            result = ee.merge_edgar_fallback(
                "BROKEN", {"altman_z": None}, {"market_cap": 100, "price": 10, "sector": "Technology"},
                as_of="2026-08-19")
        finally:
            ee.LOG = original_log
            ee.edgar_extended = original_edgar_extended

        # Behavior is unchanged: the provider's original result passes through untouched.
        self.assertEqual(result, {"altman_z": None})
        self.assertEqual(len(fake_log.warnings), 1)
        self.assertIn("BROKEN", fake_log.warnings[0])
        self.assertIn("RuntimeError", fake_log.warnings[0])


if __name__ == "__main__":
    unittest.main()
