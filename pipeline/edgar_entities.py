"""Canonical entity resolution: ticker -> CIK, with ambiguity as an error (Phase 2.1).

Everything in this repository is keyed by ticker. Tickers are not identifiers: they are
leased, reassigned, and reused across exchanges. ``THG`` is the audit's own example -- on the
NYSE it is The Hanover Insurance Group (CIK 0000944695); the same three letters were THG plc,
the UK e-commerce company, on the LSE. A store keyed by ticker silently merges the two the
moment both appear.

CIK does not have that problem. It is assigned once by the SEC, never reused, and survives
ticker changes, mergers and re-listings. This module makes it the primary key for everything
the point-in-time store writes.

Three rules:

1. **Fail loudly on ambiguity.** An unmapped or ambiguous ticker raises rather than falling
   back to a best guess. A wrong CIK does not produce an error downstream, it produces a
   confident history of the wrong company.
2. **Share classes are not collisions.** GOOG and GOOGL share CIK 0001652044 legitimately;
   they are one filer with two classes. Two *CIKs* claiming one ticker is the real defect.
3. **The map is cached with its fetch date.** SEC reassigns tickers, so a resolution is only
   true as of when the map was pulled, and the point-in-time store records that.
"""

import json
import os
import re
from datetime import datetime, timezone

from common import LOG, STORE_DIR

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
CACHE_PATH = os.path.join(STORE_DIR, "pit", "entity_map.json")


class EntityResolutionError(ValueError):
    """A ticker could not be resolved to exactly one CIK."""


def normalize_ticker(value):
    """SEC writes class suffixes with a hyphen where providers often use a dot."""
    ticker = str(value or "").strip().upper()
    return ticker.replace(".", "-") if ticker else ""


class EntityResolver:
    """Ticker -> CIK over a snapshot of SEC's company_tickers.json.

    Construct with an explicit ``rows`` payload in tests; in production ``from_client``
    fetches and caches it.
    """

    def __init__(self, rows, fetched_at=None, source="sec_company_tickers"):
        self.fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        self.source = source
        self._by_ticker = {}
        self._names = {}
        for row in rows or []:
            ticker = normalize_ticker(row.get("ticker"))
            cik = str(row.get("cik_str") or row.get("cik") or "").strip()
            if not ticker or not cik:
                continue
            cik = cik.zfill(10)
            self._by_ticker.setdefault(ticker, set()).add(cik)
            self._names.setdefault(cik, row.get("title") or row.get("name"))

    @classmethod
    def from_client(cls, client, *, cache_path=CACHE_PATH, max_age_days=7):
        """Load from the on-disk snapshot when fresh, else refetch and rewrite it.

        The snapshot is what makes a backfill reproducible: a rerun weeks later resolves
        every ticker exactly as the original run did, rather than against a map SEC has since
        changed underneath it.
        """
        cached = _read_cache(cache_path)
        if cached and not _older_than(cached.get("fetched_at"), max_age_days):
            return cls(cached.get("rows") or [], fetched_at=cached.get("fetched_at"))
        payload = client.ticker_map_rows()
        fetched_at = datetime.now(timezone.utc).isoformat()
        _write_cache(cache_path, {"fetched_at": fetched_at, "rows": payload})
        return cls(payload, fetched_at=fetched_at)

    def resolve(self, ticker):
        """The one CIK for this ticker. Raises rather than guessing."""
        normalized = normalize_ticker(ticker)
        if not normalized or not TICKER_PATTERN.match(normalized):
            raise EntityResolutionError(f"{ticker!r} is not a well-formed ticker")
        matches = self._by_ticker.get(normalized)
        if not matches:
            raise EntityResolutionError(
                f"{normalized} is not in SEC's company_tickers map (fetched "
                f"{self.fetched_at[:10]}). It may be a foreign listing, an ETF, or delisted; "
                "no CIK means no point-in-time filing history.")
        if len(matches) > 1:
            raise EntityResolutionError(
                f"{normalized} maps to {len(matches)} CIKs ({', '.join(sorted(matches))}) -- "
                "ambiguous. Resolve it explicitly before any history is keyed on it; a "
                "best guess here produces a confident history of the wrong company.")
        return next(iter(matches))

    def try_resolve(self, ticker):
        """``(cik, None)`` or ``(None, reason)``. For bulk passes that must not abort."""
        try:
            return self.resolve(ticker), None
        except EntityResolutionError as error:
            return None, str(error)

    def entity_name(self, cik):
        return self._names.get(str(cik).zfill(10))

    def provenance(self):
        return {"entity_map_source": self.source, "entity_map_fetched_at": self.fetched_at}

    def audit(self, tickers):
        """Resolution report for a universe: resolved, unmapped, ambiguous, shared CIKs.

        ``shared_cik`` is reported but is not an error -- share classes of one filer share a
        CIK by design. It is surfaced because two tickers resolving to one company means a
        universe holds the same issuer twice, which matters for any equal-weight test.
        """
        resolved, unresolved = {}, {}
        for ticker in tickers:
            cik, reason = self.try_resolve(ticker)
            if cik:
                resolved[normalize_ticker(ticker)] = cik
            else:
                unresolved[normalize_ticker(ticker)] = reason
        by_cik = {}
        for ticker, cik in resolved.items():
            by_cik.setdefault(cik, []).append(ticker)
        shared = {cik: sorted(names) for cik, names in by_cik.items() if len(names) > 1}
        return {
            "requested": len(list(tickers)),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "resolved_map": resolved,
            "unresolved_reasons": unresolved,
            "shared_cik": shared,
            "ambiguous_tickers": sorted(
                ticker for ticker, reason in unresolved.items() if "ambiguous" in reason),
            **self.provenance(),
        }


def _read_cache(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        LOG.warn(f"entity map cache at {path} is unreadable; refetching")
        return None


def _write_cache(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, path)
    except OSError as error:
        LOG.warn(f"could not cache the entity map ({type(error).__name__}: {error})")


def _older_than(stamp, days):
    if not stamp:
        return True
    try:
        fetched = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).days >= days
