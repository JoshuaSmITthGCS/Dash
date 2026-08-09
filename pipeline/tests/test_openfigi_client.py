import contextlib
import json
import os
import sys
import unittest
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
        client = OpenFigiClient(request_delay=0)

        def broken(request, timeout=None):
            raise OSError("network unavailable")

        with mock.patch.object(openfigi_client.urllib.request, "urlopen", broken):
            resolved = client.map_cusips(["000000001"])

        self.assertEqual(resolved, {})

    def test_requests_are_batched_at_the_documented_job_cap(self):
        client = OpenFigiClient(request_delay=0)
        cusips = [f"{i:09d}" for i in range(150)]
        seen_batch_sizes = []

        def fake_post(jobs):
            seen_batch_sizes.append(len(jobs))
            return [{"data": []} for _ in jobs]

        with mock.patch.object(client, "_post", fake_post):
            client.map_cusips(cusips)

        self.assertEqual(seen_batch_sizes, [100, 50])

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
