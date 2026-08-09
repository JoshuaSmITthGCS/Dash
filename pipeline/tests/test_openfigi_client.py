import contextlib
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import openfigi_client
from openfigi_client import OpenFigiClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload


class MapCusipsTests(unittest.TestCase):
    def test_a_single_unambiguous_match_is_resolved(self):
        client = OpenFigiClient(request_delay=0)
        response = json.dumps([{"data": [{"ticker": "ACME"}]}]).encode()

        with mock.patch.object(openfigi_client.urllib.request, "urlopen",
                               lambda request, timeout=None: contextlib.nullcontext(_FakeResponse(response))):
            resolved = client.map_cusips(["000000001"])

        self.assertEqual(resolved, {"000000001": "ACME"})

    def test_multiple_distinct_tickers_for_one_cusip_is_left_unresolved(self):
        # A multi-class issuer (two share classes sharing history under one CUSIP root in
        # this fake) - ambiguous, so it must not guess.
        client = OpenFigiClient(request_delay=0)
        response = json.dumps([{"data": [{"ticker": "ACME.A"}, {"ticker": "ACME.B"}]}]).encode()

        with mock.patch.object(openfigi_client.urllib.request, "urlopen",
                               lambda request, timeout=None: contextlib.nullcontext(_FakeResponse(response))):
            resolved = client.map_cusips(["000000001"])

        self.assertEqual(resolved, {})

    def test_an_unmapped_cusip_is_simply_absent(self):
        client = OpenFigiClient(request_delay=0)
        response = json.dumps([{"error": "No identifier found."}]).encode()

        with mock.patch.object(openfigi_client.urllib.request, "urlopen",
                               lambda request, timeout=None: contextlib.nullcontext(_FakeResponse(response))):
            resolved = client.map_cusips(["999999999"])

        self.assertEqual(resolved, {})

    def test_a_transport_failure_degrades_to_no_resolutions_rather_than_raising(self):
        client = OpenFigiClient(request_delay=0, retry_backoff=0)

        def broken(request, timeout=None):
            raise OSError("network unavailable")

        with mock.patch.object(openfigi_client.urllib.request, "urlopen", broken):
            resolved = client.map_cusips(["000000001"])

        self.assertEqual(resolved, {})

    def test_requests_are_batched_at_the_keyed_job_cap_when_a_key_is_configured(self):
        client = OpenFigiClient(api_key="secret-key", request_delay=0)
        cusips = [f"{i:09d}" for i in range(150)]
        seen_batch_sizes = []

        def fake_post(jobs):
            seen_batch_sizes.append(len(jobs))
            return [{"data": []} for _ in jobs]

        with mock.patch.object(client, "_post", fake_post):
            client.map_cusips(cusips)

        self.assertEqual(seen_batch_sizes, [100, 50])

    def test_an_anonymous_run_batches_at_the_smaller_anonymous_job_cap(self):
        # The failure this guards: OpenFIGI caps an anonymous request at 10 jobs, so sending
        # the keyed size of 100 without a key is refused every time. A production run mapped
        # 3,489 CUSIPs to zero tickers that way, and reported no error at all.
        client = OpenFigiClient(api_key="", request_delay=0)
        seen_batch_sizes = []

        def fake_post(jobs):
            seen_batch_sizes.append(len(jobs))
            return [{"data": []} for _ in jobs]

        with mock.patch.object(client, "_post", fake_post):
            client.map_cusips([f"{i:09d}" for i in range(25)])

        self.assertEqual(seen_batch_sizes, [10, 10, 5])

    def test_a_refused_batch_is_reported_and_its_cusips_left_pending(self):
        client = OpenFigiClient(api_key="", request_delay=0)

        def refused(request, timeout=None):
            raise urllib.error.HTTPError(
                openfigi_client.OPENFIGI_URL, 413, "Payload Too Large", {}, None)

        with mock.patch.object(openfigi_client.urllib.request, "urlopen", refused):
            resolved = client.map_cusips(["000000001", "000000002"])

        self.assertEqual(resolved, {})
        self.assertEqual(client.pending, ["000000001", "000000002"])
        self.assertEqual(len(client.errors), 1)
        self.assertIn("HTTP 413", client.errors[0])

    def test_a_rate_limited_batch_is_retried_rather_than_dropped(self):
        client = OpenFigiClient(api_key="", request_delay=0)
        attempts = {"n": 0}

        def throttled_then_ok(jobs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise urllib.error.HTTPError(
                    openfigi_client.OPENFIGI_URL, 429, "Too Many Requests", {}, None)
            return [{"data": [{"ticker": "ACME"}]} for _ in jobs]

        with mock.patch.object(openfigi_client.time, "sleep", lambda _seconds: None), \
             mock.patch.object(client, "_post", throttled_then_ok):
            resolved = client.map_cusips(["000000001"])

        self.assertEqual(resolved, {"000000001": "ACME"})
        self.assertEqual(client.errors, [])

    def test_a_request_ceiling_stops_early_and_says_what_was_not_attempted(self):
        client = OpenFigiClient(api_key="", request_delay=0, max_requests=2)

        with mock.patch.object(client, "_post", lambda jobs: [{"data": []} for _ in jobs]):
            client.map_cusips([f"{i:09d}" for i in range(50)])

        self.assertEqual(client.requests_made, 2)
        self.assertEqual(len(client.pending), 30)
        self.assertIn("unattempted", client.errors[0])

    def test_the_caller_supplied_order_is_preserved(self):
        # The caller ranks CUSIPs by how much they matter before handing them over, so that a
        # run cut short by the ceiling has still resolved the ones worth publishing.
        client = OpenFigiClient(api_key="", request_delay=0)
        seen = []

        with mock.patch.object(client, "_post",
                               lambda jobs: seen.extend(job["idValue"] for job in jobs) or
                               [{"data": []} for _ in jobs]):
            client.map_cusips(["000000009", "000000001", "000000009", "000000005"])

        self.assertEqual(seen, ["000000009", "000000001", "000000005"])

    def test_the_api_key_header_is_sent_when_configured(self):
        client = OpenFigiClient(api_key="secret-key", request_delay=0)
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return contextlib.nullcontext(_FakeResponse(b"[]"))

        with mock.patch.object(openfigi_client.urllib.request, "urlopen", fake_urlopen):
            client.map_cusips([])

        # No jobs means no request is made at all - nothing to assert on an empty CUSIP list.
        self.assertEqual(captured, {})

    def test_the_api_key_header_is_sent_on_a_real_request(self):
        client = OpenFigiClient(api_key="secret-key", request_delay=0)
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return contextlib.nullcontext(_FakeResponse(b"[{}]"))

        with mock.patch.object(openfigi_client.urllib.request, "urlopen", fake_urlopen):
            client.map_cusips(["000000001"])

        self.assertEqual(captured["headers"]["X-openfigi-apikey"], "secret-key")


if __name__ == "__main__":
    unittest.main()
