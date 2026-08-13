"""Map CUSIPs to tickers via OpenFIGI, for the direction that's actually free to use.

OpenFIGI's mapping API accepts a CUSIP as an *input* identifier but will not return one in
a response, per its data redistribution terms - CUSIP is licensed by CGS/ABA and OpenFIGI
is not permitted to redistribute it. That is irrelevant to ``institutional_ownership.py``:
a 13F information table already gives us the CUSIP (it's the issuer identifier the filer
reported), and what we need back is the ticker, which OpenFIGI does return. CUSIP-in,
ticker-out is exactly the supported direction.

No API key is required, but the *unauthenticated tier is not simply slower - it is shaped
differently*: OpenFIGI documents a 100-job cap per request for keyed callers and a 10-job
cap for anonymous ones. Sending a keyed-size batch without a key is rejected outright, per
request, every request - which is exactly how this module spent a production run mapping
3,489 CUSIPs to nothing at all while reporting no error. Two changes keep that from
recurring:

  * the batch size and pacing follow the tier actually in use (``self.max_jobs``), so an
    anonymous run sends anonymous-sized batches rather than being refused;
  * a failed batch is recorded in ``self.errors`` and its CUSIPs land in ``self.pending``
    instead of being swallowed by a bare ``continue``. Callers publish those, so "OpenFIGI
    refused us" can never again read the same as "no CUSIP resolved".

Rate limits are enforced by pacing between requests and by retrying a 429 with backoff.
The published ceilings have moved before and are not verified from this codebase, so they
are treated as a starting point that degrades to retries rather than as ground truth.
"""

import json
import os
import time
import urllib.error
import urllib.request

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI documents a per-request job cap that depends on whether a key is presented.
# Sending the keyed size anonymously is refused, not throttled.
KEYED_MAX_JOBS_PER_REQUEST = 100
ANONYMOUS_MAX_JOBS_PER_REQUEST = 10
# Retained for callers that imported the old module-level constant.
MAX_JOBS_PER_REQUEST = KEYED_MAX_JOBS_PER_REQUEST
# Documented request ceilings: 25 per 6 seconds with a key, 25 per minute without one.
KEYED_REQUEST_DELAY_SECONDS = 0.3
ANONYMOUS_REQUEST_DELAY_SECONDS = 2.5
DEFAULT_REQUEST_DELAY_SECONDS = ANONYMOUS_REQUEST_DELAY_SECONDS
# A 429 is a pacing problem, not a permanent one, so it is retried; a 4xx that is not a 429
# is a request the server will refuse identically forever, so it is not.
MAX_ATTEMPTS_PER_BATCH = 3
RETRY_BACKOFF_SECONDS = 5.0


class OpenFigiClient:
    def __init__(self, api_key=None, request_delay=None, max_jobs=None, max_requests=None,
                 retry_backoff=None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENFIGI_API_KEY", "").strip()
        self.max_jobs = max_jobs or (KEYED_MAX_JOBS_PER_REQUEST if self.api_key
                                     else ANONYMOUS_MAX_JOBS_PER_REQUEST)
        self.request_delay = (
            (KEYED_REQUEST_DELAY_SECONDS if self.api_key else ANONYMOUS_REQUEST_DELAY_SECONDS)
            if request_delay is None else request_delay)
        # None means "no ceiling". A run that cannot finish inside its job timeout is better
        # off resolving a bounded prefix and saying what it left for next time than being
        # killed halfway with nothing written.
        self.max_requests = max_requests
        self.retry_backoff = RETRY_BACKOFF_SECONDS if retry_backoff is None else retry_backoff
        self.errors = []
        self.pending = []
        self.requests_made = 0

    @property
    def tier(self):
        return "keyed" if self.api_key else "anonymous"

    def _post(self, jobs):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        request = urllib.request.Request(
            OPENFIGI_URL, data=json.dumps(jobs).encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def _post_with_retry(self, jobs):
        """One batch's results, or ``None`` with the reason recorded in ``self.errors``.

        Retries only what retrying can fix - a 429 (pacing) or a 5xx (transient) - because
        re-sending a batch the server refuses on its shape just spends the rate budget on
        the same refusal.
        """
        for attempt in range(1, MAX_ATTEMPTS_PER_BATCH + 1):
            self.requests_made += 1
            try:
                return self._post(jobs)
            except urllib.error.HTTPError as exc:
                detail = f"HTTP {exc.code}"
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace").strip()[:200]
                except Exception:  # noqa: BLE001 - the status is the part that matters
                    pass
                if body:
                    detail = f"{detail}: {body}"
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt == MAX_ATTEMPTS_PER_BATCH:
                    self.errors.append(f"{len(jobs)}-job batch refused ({detail})")
                    return None
                time.sleep(self.retry_backoff * attempt)
            except (OSError, ValueError) as exc:
                if attempt == MAX_ATTEMPTS_PER_BATCH:
                    self.errors.append(
                        f"{len(jobs)}-job batch failed ({type(exc).__name__}: {exc})")
                    return None
                time.sleep(self.retry_backoff * attempt)
        return None

    def map_cusips(self, cusips):
        """Best-effort ``{cusip: ticker}`` for every CUSIP OpenFIGI resolves unambiguously.

        A CUSIP that OpenFIGI cannot map, or maps to more than one distinct ticker (a
        multi-class issuer, most often), is left out rather than guessed at - a wrong
        ticker silently attributes one company's institutional flows to another, which is
        a worse failure than reporting fewer resolved names.

        Order is preserved from the caller: a CUSIP list that arrives ranked by how much it
        matters gets its high-value end resolved first, which is what makes a request
        ceiling survivable. Anything not attempted - because the ceiling was reached or the
        batch was refused - is left in ``self.pending`` for the caller to publish and for
        the next run to pick up.
        """
        seen, distinct = set(), []
        for cusip in cusips:
            value = str(cusip).strip().upper()
            if value and value not in seen:
                seen.add(value)
                distinct.append(value)

        resolved = {}
        self.errors, self.pending, self.requests_made = [], [], 0
        for start in range(0, len(distinct), self.max_jobs):
            batch = distinct[start:start + self.max_jobs]
            if self.max_requests is not None and self.requests_made >= self.max_requests:
                self.pending.extend(distinct[start:])
                self.errors.append(
                    f"stopped after {self.requests_made} request(s) at the configured "
                    f"ceiling with {len(self.pending)} CUSIP(s) unattempted")
                break
            results = self._post_with_retry(
                [{"idType": "ID_CUSIP", "idValue": cusip} for cusip in batch])
            if results is None:
                self.pending.extend(batch)
            else:
                for cusip, result in zip(batch, results):
                    if not isinstance(result, dict):
                        continue
                    tickers = {row["ticker"] for row in (result.get("data") or [])
                               if isinstance(row, dict) and row.get("ticker")}
                    if len(tickers) == 1:
                        resolved[cusip] = next(iter(tickers))
            if self.request_delay and start + self.max_jobs < len(distinct):
                time.sleep(self.request_delay)
        return resolved
