import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cache as cache_module
import providers
from providers import (AlphaVantageAdapter, CompositeProvider, EdgarAdapter, FakeProvider,
                       PriceSeries, Quote, YahooAdapter, build_provider)


class DiskCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cache-test-")
        self.cache = cache_module.DiskCache(root=self.directory,
                                            ttls={"default": 3600, "quick": 0})

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_value_survives_a_round_trip(self):
        self.cache.set("prices", "AAA", {"closes": [1, 2, 3]}, source="test")
        self.assertEqual(self.cache.get("prices", "AAA"), {"closes": [1, 2, 3]})

    def test_a_miss_returns_nothing(self):
        self.assertIsNone(self.cache.get("prices", "MISSING"))

    def test_fetch_calls_the_producer_only_once(self):
        calls = []

        def produce():
            calls.append(1)
            return {"value": 42}

        self.cache.fetch("prices", "AAA", produce)
        self.cache.fetch("prices", "AAA", produce)
        self.assertEqual(len(calls), 1)

    def test_an_expired_entry_is_a_miss_but_still_on_disk(self):
        self.cache.set("quick", "AAA", {"value": 1})
        self.assertIsNone(self.cache.get("quick", "AAA"))
        self.assertEqual(self.cache.get("quick", "AAA", allow_stale=True), {"value": 1})

    def test_a_failing_producer_falls_back_to_the_stale_copy(self):
        # A degraded refresh beats a blank dashboard, as long as the caller can tell.
        self.cache.set("quick", "AAA", {"value": "old"})

        def failing():
            raise OSError("provider down")

        self.assertEqual(self.cache.fetch("quick", "AAA", failing), {"value": "old"})

    def test_a_failing_producer_with_no_cached_copy_raises(self):
        with self.assertRaises(OSError):
            self.cache.fetch("prices", "NEW", lambda: (_ for _ in ()).throw(OSError("down")))

    def test_provenance_is_recorded_with_every_entry(self):
        self.cache.set("prices", "AAA", {"value": 1}, source="yahoo")
        entry = self.cache.read_entry("prices", "AAA")
        self.assertEqual(entry["source"], "yahoo")
        self.assertIn("fetched_at", entry)

    def test_keys_that_differ_only_in_punctuation_do_not_collide(self):
        self.cache.set("prices", "A/B", {"value": 1})
        self.cache.set("prices", "A:B", {"value": 2})
        self.assertEqual(self.cache.get("prices", "A/B"), {"value": 1})
        self.assertEqual(self.cache.get("prices", "A:B"), {"value": 2})

    def test_disabling_the_cache_makes_every_read_a_miss(self):
        disabled = cache_module.DiskCache(root=self.directory, enabled=False)
        disabled.set("prices", "AAA", {"value": 1})
        self.assertIsNone(disabled.get("prices", "AAA"))

    def test_stats_track_hits_and_misses(self):
        self.cache.set("prices", "AAA", {"value": 1})
        self.cache.get("prices", "AAA")
        self.cache.get("prices", "BBB")
        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)


class RateLimiterTests(unittest.TestCase):
    def test_the_limiter_spaces_requests(self):
        limiter = cache_module.RateLimiter(per_minute=600)  # 100ms apart
        start = time.monotonic()
        for _ in range(3):
            limiter.acquire()
        self.assertGreaterEqual(time.monotonic() - start, 0.15)

    def test_the_limiter_is_thread_safe(self):
        limiter = cache_module.RateLimiter(per_minute=6000)
        seen = []

        def worker():
            limiter.acquire()
            seen.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(seen), 8)

    def test_each_provider_gets_its_own_limiter(self):
        cache_module.reset_limiters()
        self.assertIsNot(cache_module.limiter_for("sec_edgar"),
                         cache_module.limiter_for("alpha_vantage"))

    def test_configured_limits_include_the_known_providers(self):
        limits = cache_module.rate_limits()
        # SEC fair access is 10 requests/second; Alpha Vantage's free tier is 5/minute.
        self.assertGreater(limits["sec_edgar"], limits["alpha_vantage"])
        self.assertIn("default", limits)


class ParallelMapTests(unittest.TestCase):
    def test_results_come_back_in_input_order(self):
        self.assertEqual(cache_module.parallel_map(lambda n: n * 2, [1, 2, 3, 4],
                                                   max_workers=3),
                         [2, 4, 6, 8])

    def test_one_failure_does_not_abort_the_batch(self):
        def flaky(value):
            if value == 2:
                raise ValueError("boom")
            return value

        self.assertEqual(cache_module.parallel_map(flaky, [1, 2, 3], max_workers=2),
                         [1, None, 3])

    def test_an_error_handler_can_supply_a_fallback(self):
        def flaky(value):
            raise ValueError("boom")

        self.assertEqual(
            cache_module.parallel_map(flaky, [1, 2], max_workers=2,
                                      on_error=lambda item, exc: f"failed:{item}"),
            ["failed:1", "failed:2"])

    def test_an_empty_batch_is_a_no_op(self):
        self.assertEqual(cache_module.parallel_map(lambda n: n, []), [])


class BackoffTests(unittest.TestCase):
    def test_it_retries_then_succeeds(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise OSError("429")
            return "ok"

        self.assertEqual(cache_module.retry_with_backoff(flaky, attempts=3, base_delay=1.0),
                         "ok")
        self.assertEqual(len(attempts), 2)

    def test_it_re_raises_after_exhausting_attempts(self):
        with self.assertRaises(OSError):
            cache_module.retry_with_backoff(
                lambda: (_ for _ in ()).throw(OSError("429")), attempts=2, base_delay=1.0)


class ProviderContractTests(unittest.TestCase):
    def test_the_fake_provider_satisfies_the_port(self):
        provider = FakeProvider(
            prices={"AAA": {"dates": ["2026-01-01"], "closes": [10.0], "volumes": [100.0]}},
            quotes={"AAA": {"name": "Alpha", "price": 10.0}},
            fundamentals={"AAA": {"return_on_invested_capital": 0.2}})
        self.assertEqual(provider.prices("AAA").last, 10.0)
        self.assertEqual(provider.quote("AAA").name, "Alpha")
        self.assertEqual(provider.fundamentals("AAA").get("return_on_invested_capital"), 0.2)

    def test_an_unknown_symbol_yields_an_empty_series_not_an_error(self):
        provider = FakeProvider()
        self.assertEqual(len(provider.prices("NOPE")), 0)

    def test_the_factory_rejects_unknown_providers(self):
        with self.assertRaises(ValueError):
            build_provider("bloomberg")
        self.assertIsInstance(build_provider("fake"), FakeProvider)

    def test_capabilities_describe_what_an_adapter_can_answer(self):
        # EDGAR has no market data, so callers route around it rather than calling and
        # catching.
        self.assertFalse(EdgarAdapter().supports("prices"))
        self.assertTrue(EdgarAdapter().supports("fundamentals"))
        self.assertTrue(YahooAdapter().supports("batch_prices"))


class AdapterMappingTests(unittest.TestCase):
    def test_yahoo_keys_are_mapped_to_internal_names(self):
        quote = YahooAdapter.map_quote("AAA", {
            "longName": "Alpha Inc", "sector": "Technology", "currentPrice": 42.0,
            "marketCap": 1e9, "quoteType": "EQUITY", "forwardPE": 18.0,
        })
        self.assertEqual(quote.name, "Alpha Inc")
        self.assertEqual(quote.price, 42.0)
        self.assertFalse(quote.is_etf)
        self.assertEqual(quote.as_dict()["forward_pe"], 18.0)

    def test_alpha_vantage_screaming_case_is_mapped_too(self):
        quote = AlphaVantageAdapter.map_quote("AAA", {
            "Name": "Alpha Inc", "Sector": "Technology",
            "MarketCapitalization": "1000000000", "PEGRatio": "1.2",
        })
        self.assertEqual(quote.name, "Alpha Inc")
        self.assertEqual(quote.as_dict()["peg"], 1.2)

    def test_unparseable_vendor_numbers_become_none(self):
        quote = AlphaVantageAdapter.map_quote("AAA", {"Name": "Alpha", "PEGRatio": "None"})
        self.assertIsNone(quote.as_dict()["peg"])

    def test_an_etf_is_recognized_from_the_quote_type(self):
        self.assertTrue(YahooAdapter.map_quote("SPY", {"quoteType": "ETF"}).is_etf)

    def test_edgar_facts_respect_the_as_of_date(self):
        payload = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [
            {"val": 100, "end": "2025-12-31", "filed": "2026-02-01"},
            {"val": 200, "end": "2026-06-30", "filed": "2026-08-01"},
        ]}}}}}
        # A fact filed in August cannot inform a March decision.
        early = EdgarAdapter.map_facts(payload, as_of="2026-03-01")
        late = EdgarAdapter.map_facts(payload, as_of="2026-09-01")
        self.assertEqual(early["total_assets"], 100)
        self.assertEqual(late["total_assets"], 200)


class CompositeProviderTests(unittest.TestCase):
    def test_it_falls_through_to_the_next_adapter(self):
        empty = FakeProvider()
        stocked = FakeProvider(prices={"AAA": {"dates": ["2026-01-01"], "closes": [5.0],
                                               "volumes": [1.0]}})
        composite = CompositeProvider([empty, stocked])
        self.assertEqual(composite.prices("AAA").last, 5.0)

    def test_the_first_usable_answer_wins(self):
        primary = FakeProvider(prices={"AAA": {"dates": ["2026-01-01"], "closes": [1.0],
                                               "volumes": [1.0]}})
        secondary = FakeProvider(prices={"AAA": {"dates": ["2026-01-01"], "closes": [9.0],
                                                 "volumes": [1.0]}})
        self.assertEqual(CompositeProvider([primary, secondary]).prices("AAA").last, 1.0)

    def test_all_adapters_failing_yields_an_empty_result_not_an_exception(self):
        composite = CompositeProvider([FakeProvider(), FakeProvider()])
        self.assertEqual(len(composite.prices("AAA")), 0)
        self.assertIsInstance(composite.quote("AAA"), Quote)

    def test_batch_prices_covers_every_requested_symbol(self):
        first = FakeProvider(prices={"AAA": {"dates": ["d"], "closes": [1.0], "volumes": [1.0]}})
        second = FakeProvider(prices={"BBB": {"dates": ["d"], "closes": [2.0], "volumes": [1.0]}})
        batch = CompositeProvider([first, second]).batch_prices(["AAA", "BBB", "CCC"])
        self.assertEqual(batch["AAA"].last, 1.0)
        self.assertEqual(batch["BBB"].last, 2.0)
        self.assertEqual(len(batch["CCC"]), 0)


if __name__ == "__main__":
    unittest.main()
