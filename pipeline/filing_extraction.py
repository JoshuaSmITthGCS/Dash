"""Operating-KPI extraction from 8-K earnings-release exhibits and 10-Q/10-K MD&A.

Same-store sales, net interest margin, ARPU, and the like are not standardized XBRL facts --
the SEC's own guidance treats "same-store sales calculated from GAAP revenues" as an MD&A
disclosure, not a tagged financial-statement line, and issuers report each of these in
whatever table or prose format their earnings-release template uses. This module locates the
right exhibit, flattens its HTML into lines a company actually wrote (one per table row or
paragraph), and searches those lines for a small, deliberately narrow registry of
well-templated metrics.

**This is a first-pass, low-confidence layer, not a general-purpose filing parser.** It has
not been validated against a single live SEC EDGAR fetch: this module was written in a
sandboxed session whose outbound network policy blocks sec.gov (data.sec.gov returned a
proxy-level 403), so every test here runs against synthetic fixtures built from the *known*
structure of real earnings-release exhibits, not a fetched document. Confirm against real
filings before trusting its output in production -- see ``KPI_PATTERNS`` and
``pipeline/tests/test_filing_extraction.py`` for exactly what was and was not exercised.

Deliberately narrow scope: same-store/comparable sales (retail, restaurants), net interest
margin and efficiency ratio (banks), and ARPU/postpaid churn (telecom) -- the sub-industries
the source research (docs/... KPI-layer research) itself calls most template-consistent, not
all nine remaining GICS sectors. Extending coverage means adding registry entries and, before
trusting them, checking real filings.
"""

import re

from bs4 import BeautifulSoup


def html_to_lines(html):
    """Flatten one filing document into lines: one per table row, one per paragraph/heading.

    A naive ``get_text()`` collapses a whole table into one run of words with no row
    boundaries, so "Net interest margin" and its value can end up separated by every other
    line-item on the page. Walking row/paragraph elements directly keeps a label and its
    value on the same line, which is what every regex below depends on.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    lines = []
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        cells = [cell for cell in cells if cell]
        if cells:
            lines.append(" | ".join(cells))
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
        # Skip a paragraph that is itself inside a table cell -- already captured above as
        # part of its row, and emitting it again would duplicate every table-cell paragraph.
        if tag.find_parent("td") or tag.find_parent("th"):
            continue
        text = tag.get_text(" ", strip=True)
        if text:
            lines.append(text)
    return lines


def _percent_after(label_pattern):
    """A label, then the first signed percentage within ~60 characters of it."""
    return re.compile(label_pattern + r".{0,60}?([+-]?\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)


def _percent_value(match):
    return round(float(match.group(1)) / 100, 4)


def _bps_or_percent_after(label_pattern):
    """A label, then a percentage (margin/ratio levels are usually reported as a level, not
    a change) within range."""
    return re.compile(label_pattern + r".{0,60}?(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)


def _dollar_after(label_pattern):
    return re.compile(label_pattern + r".{0,60}?\$\s?(\d{1,4}(?:\.\d+)?)", re.IGNORECASE)


def _dollar_value(match):
    return round(float(match.group(1)), 2)


# Canonical metric -> (applicable business profiles, compiled pattern, value parser,
# human label). Kept intentionally small; see this file's module docstring for why.
KPI_PATTERNS = {
    "same_store_sales_growth": {
        "profiles": ("general",),  # retail/restaurant sub-industries are text-classified,
                                    # not a distinct applicability profile today
        "pattern": _percent_after(
            r"(?:same[\s-]?store|comparable[\s-]?store|comparable(?:\s+restaurant)?)\s+sales"
            r"(?:\s+growth|\s+increased|\s+decreased|\s+grew|\s+rose|\s+fell)?"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Same-store / comparable sales growth",
    },
    "net_interest_margin": {
        "profiles": ("bank",),
        "pattern": _bps_or_percent_after(r"net\s+interest\s+margin"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Net interest margin",
    },
    "efficiency_ratio": {
        "profiles": ("bank",),
        "pattern": _bps_or_percent_after(r"efficiency\s+ratio"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Efficiency ratio",
    },
    "average_revenue_per_user": {
        "profiles": ("general",),
        "pattern": _dollar_after(
            r"(?:postpaid\s+)?(?:average\s+revenue\s+per\s+(?:user|account)|ARPU|ARPA)"),
        "parse": _dollar_value,
        "unit": "usd",
        "label": "Average revenue per user/account",
    },
    "postpaid_churn": {
        "profiles": ("general",),
        "pattern": _bps_or_percent_after(r"postpaid\s+(?:phone\s+)?churn"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Postpaid churn",
    },
}


def extract_kpis(lines, metric_ids):
    """First match per requested metric, with the evidence line for auditability.

    Returns ``{metric_id: {"value": ..., "unit": ..., "evidence_line": ...}}`` -- a metric
    with no match in ``lines`` is simply absent from the result, never a guessed value.
    """
    results = {}
    for metric_id in metric_ids:
        spec = KPI_PATTERNS.get(metric_id)
        if spec is None:
            continue
        for line in lines:
            match = spec["pattern"].search(line)
            if not match:
                continue
            try:
                value = spec["parse"](match)
            except (TypeError, ValueError):
                continue
            results[metric_id] = {"value": value, "unit": spec["unit"], "evidence_line": line}
            break
    return results


# Exhibits carrying the earnings-release financial tables and MD&A-style commentary this
# module reads. EDGAR gives every filer a free hand in exhibit naming, so this matches by
# filename pattern rather than a fixed convention -- the same problem filing_index()'s own
# docstring describes for locating a 13F's InfoTable.
EXHIBIT_NAME_PATTERN = re.compile(r"ex-?99", re.IGNORECASE)


def find_exhibit_documents(client, ticker, *, forms=("8-K",), limit=4):
    """Recent filings of the given form(s) for ``ticker``, each paired with its Exhibit 99.x
    document name(s) found in the filing's own directory listing.

    Returns a list of ``{**filing, "documents": [name, ...]}``; ``documents`` is empty for a
    filing whose directory listing carries no exhibit-99-like file (e.g. an 8-K that only
    disclosed an unrelated item and filed no earnings-release exhibit at all).
    """
    filings = client.recent_forms(ticker, forms, limit=limit)
    enriched = []
    for filing in filings:
        try:
            names = client.filing_index(filing["cik"], filing["accession"])
        except Exception:  # noqa: BLE001 - one unreadable filing must not sink the batch
            names = []
        enriched.append({**filing, "documents": [name for name in names
                                                 if EXHIBIT_NAME_PATTERN.search(name)]})
    return enriched


def extract_operating_kpis_for_ticker(client, ticker, metric_ids, *, forms=("8-K",), limit=4):
    """Fetch this ticker's most recent qualifying exhibits and extract the requested metrics.

    Stops at the first exhibit that resolves every requested metric; otherwise merges across
    exhibits (a metric found in an earlier, more recent filing is never overwritten by a
    later, older one). Returns ``(results, filings_attempted)`` so a caller can report
    extraction coverage -- how many filings were readable, not just what was found in them.
    """
    results = {}
    filings_attempted = 0
    for filing in find_exhibit_documents(client, ticker, forms=forms, limit=limit):
        for document in filing["documents"]:
            filings_attempted += 1
            try:
                html = client.filing_document(filing["cik"], filing["accession"], document)
            except Exception:  # noqa: BLE001 - an unreadable exhibit must not sink the batch
                continue
            lines = html_to_lines(html)
            found = extract_kpis(lines, [metric for metric in metric_ids if metric not in results])
            for metric_id, reading in found.items():
                results[metric_id] = {**reading, "filed": filing.get("filed"),
                                      "form": filing.get("form")}
        if len(results) == len(metric_ids):
            break
    return results, filings_attempted


def collect_operating_kpi_signals(client, tickers, *, metrics_by_profile, profile_for_ticker,
                                  limit_per_ticker=4):
    """Extracted operating KPIs for a batch of tickers, keyed by ticker.

    ``profile_for_ticker(ticker)`` resolves each ticker's applicability profile (see
    ``canonical_metrics.classify_profile``); ``metrics_by_profile`` maps a profile name to
    the metric ids worth attempting for it (a bank gets NIM/efficiency ratio; every other
    profile falls back to ``metrics_by_profile["general"]``, since this pipeline does not yet
    distinguish retail/restaurant/telecom as their own profiles). A ticker whose client is
    unavailable, or that resolves nothing, is simply absent from the result -- never a guess.

    Every reading is tagged ``"unaudited": True``: these are self-reported, non-GAAP,
    filer-defined figures pulled from prose/tables, not a GAAP-tagged fact, following this
    module's own recommendation to flag non-standardized metrics rather than present them
    with the same confidence as an XBRL-sourced one.
    """
    if not getattr(client, "available", True):
        return {}, {"attempted": 0, "resolved_tickers": 0}
    results_by_ticker = {}
    filings_attempted_total = 0
    for ticker in tickers:
        profile = profile_for_ticker(ticker)
        metric_ids = metrics_by_profile.get(profile, metrics_by_profile.get("general", []))
        if not metric_ids:
            continue
        try:
            readings, attempted = extract_operating_kpis_for_ticker(
                client, ticker, metric_ids, limit=limit_per_ticker)
        except Exception:  # noqa: BLE001 - one ticker's EDGAR failure must not sink the batch
            continue
        filings_attempted_total += attempted
        if readings:
            results_by_ticker[ticker] = {
                metric_id: {**reading, "unaudited": True} for metric_id, reading in readings.items()
            }
    return results_by_ticker, {"attempted": filings_attempted_total,
                               "resolved_tickers": len(results_by_ticker)}


def summarize_extraction_coverage(results_by_ticker, metric_ids):
    """Per-metric resolution rate across a batch -- the >80%-of-universe gate the source
    research recommends before a KPI is trusted enough to publish or score on.

    This is the coverage-measurement machinery, not a coverage *run*: it takes whatever
    ``results_by_ticker`` a caller already assembled (e.g. a batch fetched in CI, where
    network access to SEC EDGAR is unrestricted) and reports resolution rates from it. No
    live-universe run has been performed from this module -- see the module docstring.
    """
    total = len(results_by_ticker) or 1
    return {
        metric_id: round(sum(1 for reading in results_by_ticker.values()
                             if metric_id in reading) / total, 4)
        for metric_id in metric_ids
    }
