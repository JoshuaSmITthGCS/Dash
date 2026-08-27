"""Fetch and cache the actual text of an 8-K Item 2.02 earnings-release exhibit.

``pipeline/collect_earnings_releases.py`` already crawls the EDGAR submissions API for every
Item 2.02 8-K in the universe -- accession, form, item codes, filing dates -- and writes it to
``pipeline/data/pit/earnings_releases.jsonl``. It deliberately stops at metadata: its own
docstring says "No page scraping", and ``pipeline/edgar_filing_signals.py`` documents the same
boundary for the whole pipeline -- 8-K signals come from SEC's own Item taxonomy, "never the
filing's actual prose". That boundary is exactly what this module crosses, on purpose, for one
reason: same-store/comparable sales, ARPU, and the rest of the sector operating KPIs a research
brief asks for genuinely do not exist anywhere in structured SEC XBRL (unlike FFO or bank NIM,
see fundamentals_extended.derive_reit_ffo/derive_bank_metrics) -- they live only in the earnings
release itself, Exhibit 99.x of an Item 2.02 8-K.

This module fetches that one exhibit's text, using the same rate-limited SecEdgarClient and the
same accession numbers ``collect_earnings_releases.py`` already found -- no new discovery, no
new crawl, just one more document per accession, read once and cached forever (an accession's
filed content never changes). What it deliberately does NOT do is decide what any of that text
means: extraction (pipeline/operating_kpis.py) is a separate, narrow, pattern-matching module
that returns ``None`` rather than guess, and this module's own job stops at handing over
plain text.

IMPORTANT: unlike the rest of this pipeline's data sources, text extracted through this path has
not been validated against a broad, live sample of real filings -- the environment this module
was written in has no network access to SEC EDGAR to check a single real exhibit's HTML against
the picker/parser below. See docs/LIMITATIONS.md. Nothing here is wired into the live scoring
snapshot (pipeline/fetch_advisor.py) for that reason; pipeline/collect_operating_kpis.py is a
standalone collector to run and validate coverage against first.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser

from common import LOG

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "data", "pit", "filing_text_cache")

# Exhibit 99.1 is, near-universally, the earnings press release on an Item 2.02 8-K; a
# supplemental slide deck or data tables sometimes ride along as 99.2/99.3. Tried in this
# order and the first match wins -- a filer's own naming convention varies (`ex991.htm`,
# `ex-99_1.htm`, `tm2412345d1_ex99-1.htm`, `brhc10abcde_ex99-1.htm`), but "99" followed by an
# optional separator and "1" is consistent across the ones this was written against known
# real-world examples of, and a bare "ex99" catch-all is the fallback for a filer that omits
# the sub-number entirely.
_EXHIBIT_PATTERNS = (
    re.compile(r"ex-?99[._x-]?1\b", re.IGNORECASE),
    re.compile(r"ex-?99\b", re.IGNORECASE),
)


class _VisibleTextExtractor(HTMLParser):
    """Minimal HTML-to-text: drop script/style contents, keep everything else's text."""

    _SKIPPED_TAGS = ("script", "style")

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.chunks.append(data)


def html_to_text(html):
    """Plain text from a filing's raw HTML, whitespace-normalized. Never raises."""
    parser = _VisibleTextExtractor()
    try:
        parser.feed(html or "")
    except Exception:  # noqa: BLE001 - malformed markup must not sink the whole document
        pass
    return re.sub(r"[ \t\r\f\v]+", " ", " ".join(parser.chunks)).strip()


def pick_exhibit_document(document_names):
    """The earnings-release exhibit's filename from a filing's directory listing, or ``None``.

    Returns ``None`` -- never a guess -- when nothing in the listing looks like an Exhibit 99.
    """
    for pattern in _EXHIBIT_PATTERNS:
        for name in document_names or ():
            if pattern.search(name):
                return name
    return None


def _cache_path(cik, accession):
    return os.path.join(CACHE_DIR, str(cik).zfill(10), f"{str(accession).replace('-', '')}.txt")


def earnings_release_text(client, cik, accession, *, use_cache=True):
    """Plain text of one Item 2.02 8-K's earnings-release exhibit, or ``None``.

    Cached to disk by accession: a filed accession's content is immutable, so a cache hit
    never needs revalidation and a re-run never re-fetches it. Returns ``None`` (not raises)
    when the exhibit can't be identified in the filing's directory listing or can't be
    fetched -- one unreadable filing must not sink a caller iterating many.
    """
    cache_file = _cache_path(cik, accession)
    if use_cache and os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as handle:
            return handle.read()
    try:
        document_names = client.filing_index(cik, accession)
        document = pick_exhibit_document(document_names)
        if not document:
            return None
        html = client.filing_document(cik, accession, document)
    except Exception as error:  # noqa: BLE001 - one filing is not the run
        LOG.warn(f"filing_text: could not fetch exhibit for CIK {cik} accession {accession}: "
                 f"{type(error).__name__}")
        return None
    text = html_to_text(html)
    if use_cache:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as handle:
            handle.write(text)
    return text
