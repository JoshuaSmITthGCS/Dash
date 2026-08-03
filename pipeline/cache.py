"""On-disk caching, per-provider rate limiting, and bounded parallel fetching.

Three problems this solves, in the order they bite:

  1. Every rerun re-downloaded price history that had not changed. A parquet-style
     on-disk cache keyed by (namespace, key) makes a rerun nearly free and insulates
     the pipeline from Alpha Vantage's 25-request/day free cap and Yahoo's 429s.
  2. Providers rate-limit on different clocks (Alpha Vantage 5/min, SEC 10/sec,
     Polygon 5/min). One global sleep is either too slow or a ban; a per-provider
     token bucket is neither.
  3. Fetches are independent, so they should overlap - but only up to the limit the
     provider actually permits. ``parallel_map`` pairs a bounded thread pool with the
     provider's own limiter so concurrency never outruns the quota.

Every cached entry records the time it was fetched and the source that produced it,
which is what makes the staleness reporting in ``pit_store`` possible at all.
"""

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone

from common import LOG, STORE_DIR, load_json

CACHE_DIR = os.path.join(STORE_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Requests per minute each provider tolerates on its free tier. Overridable from
# config/settings.json so a paid upgrade is a config edit, not a code change.
DEFAULT_RATE_LIMITS = {
    "alpha_vantage": 5,
    # SEC fair access allows 10 requests/second. Sitting exactly on a published ceiling
    # leaves no room for clock jitter or a retry the limiter never saw, and the penalty for
    # crossing it is a block rather than a warning, so this runs at 9/s instead.
    "sec_edgar": 540,
    # Yahoo publishes no rate limit, so this is our own conservative guess rather than a
    # documented ceiling. 4/s clears a ~900-name universe in a few minutes of pacing where
    # 2/s took nearly eight, and stays far below the rates that draw 429s in practice.
    # Every call is cached and retried with backoff, so the cost of guessing slightly high
    # is a retry, not a lost run. Lower it if YFRateLimitError starts appearing in the logs.
    "yahoo": 240,
    "fred": 120,
    "marketaux": 60,
    "polygon": 5,
    "default": 60,
}

# How long a cached namespace stays usable before it must be refetched, in seconds.
DEFAULT_TTLS = {
    "price_history": 6 * 3600,
    "quote": 900,
    "statements": 7 * 24 * 3600,
    "sec_submissions": 24 * 3600,
    "sec_document": 30 * 24 * 3600,   # a filed document never changes
    "sec_xbrl": 24 * 3600,
    "etf_disclosure": 24 * 3600,
    "etf_full_history": 20 * 3600,  # a "max" pull is expensive; only the latest session changes daily
    "news": 1800,
    "default": 3600,
}


def _settings():
    return load_json("settings.json", from_config=True) or {}


def rate_limits():
    configured = (_settings().get("providers", {}) or {}).get("rate_limits_per_minute", {})
    return {**DEFAULT_RATE_LIMITS, **configured}


def cache_ttls():
    configured = (_settings().get("providers", {}) or {}).get("cache_ttl_seconds", {})
    return {**DEFAULT_TTLS, **configured}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- rate limiting ----------------

class RateLimiter:
    """Token bucket sized in requests per minute. Thread-safe and monotonic-clock based."""

    def __init__(self, per_minute):
        self.per_minute = max(1, int(per_minute))
        self.interval = 60.0 / self.per_minute
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self):
        """Block until this caller owns the next request slot. Returns seconds waited."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self.interval
            wait = start - now
        if wait > 0:
            time.sleep(wait)
        return wait


_LIMITERS = {}
_LIMITERS_LOCK = threading.Lock()


def limiter_for(provider):
    """One shared limiter per provider name, created on first use."""
    with _LIMITERS_LOCK:
        if provider not in _LIMITERS:
            limits = rate_limits()
            _LIMITERS[provider] = RateLimiter(limits.get(provider, limits["default"]))
        return _LIMITERS[provider]


def reset_limiters():
    """Drop cached limiters so a settings change takes effect. Used by tests."""
    with _LIMITERS_LOCK:
        _LIMITERS.clear()


# ---------------- on-disk cache ----------------

def _slug(key):
    """Filesystem-safe, collision-resistant filename for an arbitrary cache key."""
    text = key if isinstance(key, str) else json.dumps(key, sort_keys=True, default=str)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    readable = "".join(character if character.isalnum() or character in "-._" else "-"
                       for character in text)[:60]
    return f"{readable}.{digest}.json"


class DiskCache:
    """JSON-on-disk cache with per-namespace TTLs and fetch-time provenance.

    Entries are never silently trusted past their TTL: ``get`` returns None once an
    entry expires, but the expired payload stays on disk so ``get(allow_stale=True)``
    can still serve it when a provider is down. Serving known-stale data beats
    serving nothing, as long as the caller is told which it got.
    """

    def __init__(self, root=CACHE_DIR, ttls=None, enabled=None):
        self.root = root
        self.ttls = ttls or cache_ttls()
        if enabled is None:
            enabled = os.getenv("PIPELINE_CACHE_DISABLE", "").lower() not in {"1", "true", "yes"}
        self.enabled = enabled
        self.hits = self.misses = self.stale_hits = 0
        self._lock = threading.Lock()

    def ttl(self, namespace):
        return self.ttls.get(namespace, self.ttls.get("default", 3600))

    def path(self, namespace, key):
        directory = os.path.join(self.root, namespace)
        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, _slug(key))

    def read_entry(self, namespace, key):
        """The raw envelope (value + provenance), regardless of age. None when absent."""
        path = self.path(namespace, key)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def age_seconds(self, entry):
        try:
            fetched = datetime.fromisoformat(entry["fetched_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - fetched).total_seconds()

    def get(self, namespace, key, allow_stale=False):
        """Cached value, or None on a miss or an expiry the caller did not opt out of."""
        if not self.enabled:
            return None
        entry = self.read_entry(namespace, key)
        if entry is None:
            with self._lock:
                self.misses += 1
            return None
        age = self.age_seconds(entry)
        fresh = age is not None and age <= self.ttl(namespace)
        if fresh:
            with self._lock:
                self.hits += 1
            return entry.get("value")
        if allow_stale:
            with self._lock:
                self.stale_hits += 1
            return entry.get("value")
        with self._lock:
            self.misses += 1
        return None

    def set(self, namespace, key, value, source=None):
        """Store a value with its fetch time and source. Written atomically."""
        if not self.enabled:
            return value
        envelope = {"fetched_at": now_iso(), "source": source, "namespace": namespace,
                    "key": key if isinstance(key, str) else json.dumps(key, sort_keys=True, default=str),
                    "value": value}
        path = self.path(namespace, key)
        temporary = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
        try:
            with open(temporary, "w") as handle:
                json.dump(envelope, handle, default=str)
            os.replace(temporary, path)
        except OSError as exc:
            LOG.warn(f"cache write failed for {namespace}/{key}: {type(exc).__name__}")
            if os.path.exists(temporary):
                os.unlink(temporary)
        return value

    def fetch(self, namespace, key, producer, source=None, allow_stale_on_error=True):
        """Return the cached value, or call ``producer()`` and cache what it returns.

        A producer that raises falls back to an expired entry when one exists. That is
        the difference between a degraded refresh and a blank dashboard.
        """
        cached = self.get(namespace, key)
        if cached is not None:
            return cached
        try:
            value = producer()
        except Exception as exc:  # noqa: BLE001 - provider failures must not sink the run
            if allow_stale_on_error:
                stale = self.get(namespace, key, allow_stale=True)
                if stale is not None:
                    LOG.warn(f"{namespace}/{key}: {type(exc).__name__}; serving cached copy")
                    return stale
            raise
        if value is not None:
            self.set(namespace, key, value, source=source)
        return value

    def stats(self):
        total = self.hits + self.misses + self.stale_hits
        return {"hits": self.hits, "misses": self.misses, "stale_hits": self.stale_hits,
                "hit_rate": round(self.hits / total, 3) if total else None}

    def purge(self, namespace=None, older_than_seconds=None):
        """Delete cache entries. Used by the cleanup path and by tests."""
        namespaces = [namespace] if namespace else (
            os.listdir(self.root) if os.path.isdir(self.root) else [])
        removed = 0
        for name in namespaces:
            directory = os.path.join(self.root, name)
            if not os.path.isdir(directory):
                continue
            for filename in os.listdir(directory):
                path = os.path.join(directory, filename)
                if older_than_seconds is not None:
                    try:
                        with open(path) as handle:
                            age = self.age_seconds(json.load(handle))
                    except (OSError, ValueError):
                        age = None
                    if age is not None and age <= older_than_seconds:
                        continue
                try:
                    os.unlink(path)
                    removed += 1
                except OSError:
                    pass
        return removed


CACHE = DiskCache()


# ---------------- rate-limited, cached HTTP ----------------

def cached_json(url, *, provider="default", namespace=None, params=None, headers=None,
                cache=None, retries=3, backoff=2.0, timeout=30):
    """GET JSON through the provider's rate limiter and the on-disk cache."""
    from common import http_get_json  # imported here to keep cache.py import-light

    cache = cache or CACHE
    namespace = namespace or provider
    key = json.dumps({"url": url, "params": params or {}}, sort_keys=True)

    def produce():
        limiter_for(provider).acquire()
        payload = http_get_json(url, params=params, headers=headers,
                                retries=retries, backoff=backoff, timeout=timeout)
        if payload is None:
            raise OSError(f"no payload from {url}")
        return payload

    try:
        return cache.fetch(namespace, key, produce, source=provider)
    except OSError:
        return None


# ---------------- bounded parallelism ----------------

def parallel_map(function, items, *, provider="default", max_workers=None, on_error=None):
    """Run ``function`` over ``items`` concurrently without outrunning the provider quota.

    Worker count defaults to the provider's per-minute allowance capped at 8 - enough to
    overlap network latency, never enough to turn a rate limit into a ban. Results come
    back in input order; a failing item yields whatever ``on_error`` returns (None by
    default) rather than aborting the batch.
    """
    items = list(items)
    if not items:
        return []
    if max_workers is None:
        limits = rate_limits()
        allowance = limits.get(provider, limits["default"])
        max_workers = max(1, min(8, allowance // 2 or 1))
    if max_workers == 1:
        results = []
        for item in items:
            try:
                results.append(function(item))
            except Exception as exc:  # noqa: BLE001
                LOG.warn(f"{provider}: {item} failed ({type(exc).__name__}: {exc})")
                results.append(on_error(item, exc) if on_error else None)
        return results

    from concurrent.futures import ThreadPoolExecutor

    def guarded(item):
        try:
            return function(item)
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{provider}: {item} failed ({type(exc).__name__}: {exc})")
            return on_error(item, exc) if on_error else None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(guarded, items))


def retry_with_backoff(function, *, attempts=4, base_delay=2.0, retry_on=(Exception,),
                       description="request"):
    """Exponential backoff at 2s, 4s, 8s, 16s. Yahoo's limits are undocumented and move."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return function()
        except retry_on as exc:  # noqa: PERF203 - the retry is the point
            last = exc
            if attempt == attempts:
                break
            delay = base_delay ** attempt
            LOG.warn(f"{description}: {type(exc).__name__} (attempt {attempt}/{attempts}), "
                     f"retrying in {delay:.0f}s")
            time.sleep(delay)
    raise last
