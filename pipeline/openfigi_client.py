"""Map CUSIPs to tickers via OpenFIGI, for the direction that's actually free to use.

OpenFIGI's mapping API accepts a CUSIP as an *input* identifier but will not return one in
a response, per its data redistribution terms - CUSIP is licensed by CGS/ABA and OpenFIGI
is not permitted to redistribute it. That is irrelevant to ``institutional_ownership.py``:
a 13F information table already gives us the CUSIP (it's the issuer identifier the filer
reported), and what we need back is the ticker, which OpenFIGI does return. CUSIP-in,
ticker-out is exactly the supported direction.

No API key is required, at a lower, documented rate limit than the keyed tier; set
``OPENFIGI_API_KEY`` to use a key if one is available. Because this module has never run
against the live endpoint from this codebase (no network access existed while it was
written - see TODO.md), the batch size and pacing below are deliberately conservative
reads of OpenFIGI's public documentation rather than values tuned against observed
behavior. Confirm both against OpenFIGI's current docs before relying on this at scale.
"""

import json
import os
import time
import urllib.request

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI documents a 100-job cap per mapping request regardless of key tier.
MAX_JOBS_PER_REQUEST = 100
# Conservative pacing for the unauthenticated tier. Confirm against current OpenFIGI docs
# before raising - the exact published ceiling has moved before and is not verified here.
DEFAULT_REQUEST_DELAY_SECONDS = 2.5


class OpenFigiClient:
    def __init__(self, api_key=None, request_delay=None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENFIGI_API_KEY", "").strip()
        self.request_delay = (DEFAULT_REQUEST_DELAY_SECONDS if request_delay is None
                              else request_delay)

    def _post(self, jobs):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        request = urllib.request.Request(
            OPENFIGI_URL, data=json.dumps(jobs).encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def map_cusips(self, cusips):
        """Best-effort ``{cusip: ticker}`` for every CUSIP OpenFIGI resolves unambiguously.

        A CUSIP that OpenFIGI cannot map, or maps to more than one distinct ticker (a
        multi-class issuer, most often), is left out rather than guessed at - a wrong
        ticker silently attributes one company's institutional flows to another, which is
        a worse failure than reporting fewer resolved names.
        """
        distinct = sorted({str(cusip).strip().upper() for cusip in cusips if cusip})
        resolved = {}
        for start in range(0, len(distinct), MAX_JOBS_PER_REQUEST):
            batch = distinct[start:start + MAX_JOBS_PER_REQUEST]
            jobs = [{"idType": "ID_CUSIP", "idValue": cusip} for cusip in batch]
            try:
                results = self._post(jobs)
            except (OSError, ValueError):
                continue
            for cusip, result in zip(batch, results):
                tickers = {row["ticker"] for row in (result.get("data") or [])
                          if row.get("ticker")}
                if len(tickers) == 1:
                    resolved[cusip] = next(iter(tickers))
            if self.request_delay and start + MAX_JOBS_PER_REQUEST < len(distinct):
                time.sleep(self.request_delay)
        return resolved
