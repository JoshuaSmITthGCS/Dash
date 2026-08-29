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

Covers same-store/comparable sales (retail, restaurants), net interest margin and efficiency
ratio (banks), ARPU/postpaid churn (telecom), AUM/net-flows/fee-rate (capital markets and
asset managers), same-store NOI/occupancy/leasing spread (REITs), book-to-bill and backlog
(aerospace & defense, semiconductors), net revenue retention (SaaS), capacity utilization
(semiconductors, chemicals/metals/paper, independent power producers), rate-base growth and
allowed ROE (regulated utilities), and capacity factor (independent power producers) -- see
``KPI_PATTERNS`` for the full registry and ``filing_extraction_group`` for how a company is
routed to its subset. Extending coverage further means adding registry entries and, before
trusting them, checking real filings.
"""

import re

from bs4 import BeautifulSoup


# Confirmed against a real filing (Citigroup 8-K Exhibit 99.x, 2026-08-28 live-extraction run):
# SEC filers pad earnings-release tables with spacer cells containing only a zero-width space
# (U+200B) -- invisible, but not whitespace by Python's definition, so str.strip() leaves it
# alone and it survives as a "non-empty" cell: the real evidence line for a matched
# efficiency_ratio reading was
#   "Efficiency Ratio (...) | ​ | 57.4% | ​ | 58.1% | ​ | 62.7% | ​ | (70) bps | ​ | (530) bps"
# Every one of those spacer cells burns characters out of the label-to-value search window
# below for no informational reason.
_INVISIBLE_FORMATTING_CHARS = "​‌‍﻿"


def _clean_cell_text(text):
    return text.translate({ord(char): None for char in _INVISIBLE_FORMATTING_CHARS})


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
        cells = [_clean_cell_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
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


# A real matched line (see _clean_cell_text's docstring above) put the value 52 characters
# after its label, even after stripping spacer cells -- multi-column comparison tables (this
# quarter | prior quarter | prior year, sometimes with a units/footnote cell between each)
# routinely spend that much space before the first number. The original 60/40-character
# budgets were tight enough that a slightly longer label parenthetical or one extra column
# would have missed a real, present value. Widened once, from that evidence, not tuned per
# metric -- there still isn't enough live data to justify anything more surgical.
_LABEL_TO_VALUE_CHARS = 110
_LABEL_TO_RATIO_CHARS = 70


class _LabelValuePattern:
    """A compiled label+value regex that also exposes its label-only half.

    ``extract_kpis`` only ever calls ``.search()``, so this is a drop-in replacement for a
    bare compiled pattern everywhere that matters -- but ``near_miss_samples`` below can also
    reach ``.label_pattern`` to tell "this label never appears in the filing" apart from "the
    label appears, but no value-shaped text follows it the regex recognizes", which is the
    difference between a metric this filer simply doesn't disclose and one whose pattern
    needs fixing. A bare ``re.Pattern`` can't carry that second regex as an attribute (it has
    no ``__dict__``), hence the wrapper.
    """

    def __init__(self, value_pattern, label_pattern):
        self.value_pattern = value_pattern
        self.label_pattern = label_pattern

    def search(self, line):
        return self.value_pattern.search(line)


def _percent_after(label_pattern):
    """A label, then the first signed percentage within range of it."""
    return _LabelValuePattern(
        re.compile(label_pattern + rf".{{0,{_LABEL_TO_VALUE_CHARS}}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%",
                  re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _percent_value(match):
    return round(float(match.group(1)) / 100, 4)


def _bps_or_percent_after(label_pattern):
    """A label, then a percentage (margin/ratio levels are usually reported as a level, not
    a change) within range."""
    return _LabelValuePattern(
        re.compile(label_pattern + rf".{{0,{_LABEL_TO_VALUE_CHARS}}}?(\d{{1,3}}(?:\.\d+)?)\s*%",
                  re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _dollar_after(label_pattern):
    return _LabelValuePattern(
        re.compile(label_pattern + rf".{{0,{_LABEL_TO_VALUE_CHARS}}}?\$\s?(\d{{1,4}}(?:\.\d+)?)",
                  re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _dollar_value(match):
    return round(float(match.group(1)), 2)


# AUM, backlog, and similar figures are reported at a magnitude ("$1.2 trillion", "$450.3
# billion") rather than in raw dollars -- a bare number with no scale is meaningless for these.
_SCALE_MULTIPLIERS = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}


def _dollar_with_scale_after(label_pattern):
    return _LabelValuePattern(
        re.compile(
            label_pattern + rf".{{0,{_LABEL_TO_VALUE_CHARS}}}?\$\s?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*"
            r"(trillion|billion|million|thousand)?", re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _dollar_scaled_value(match):
    amount = float(match.group(1).replace(",", ""))
    scale = (match.group(2) or "").lower()
    return round(amount * _SCALE_MULTIPLIERS.get(scale, 1), 2)


def _ratio_after(label_pattern):
    """A label, then a bare or 'Nx'-style ratio (book-to-bill, coverage, ...)."""
    return _LabelValuePattern(
        re.compile(label_pattern + rf".{{0,{_LABEL_TO_RATIO_CHARS}}}?(\d{{1,2}}(?:\.\d+)?)\s*x?\b",
                  re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _ratio_value(match):
    return round(float(match.group(1)), 3)


def _bps_after(label_pattern):
    """A label, then a basis-point figure (fee rates are usually quoted this way, not as %)."""
    return _LabelValuePattern(
        re.compile(label_pattern + rf".{{0,{_LABEL_TO_VALUE_CHARS}}}?(\d{{1,4}}(?:\.\d+)?)\s*(?:bps|basis\s+points)",
                  re.IGNORECASE),
        re.compile(label_pattern, re.IGNORECASE))


def _bps_value(match):
    return round(float(match.group(1)) / 10000, 6)


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
    # ---- Capital markets / asset managers ----
    "assets_under_management": {
        "profiles": ("capital_markets",),
        "pattern": _dollar_with_scale_after(r"(?:assets\s+under\s+management|\bAUM\b)"),
        "parse": _dollar_scaled_value,
        "unit": "usd",
        "label": "Assets under management",
    },
    "net_flows_organic_growth": {
        "profiles": ("capital_markets",),
        "pattern": _percent_after(r"organic\s+(?:asset\s+)?growth(?:\s+rate)?"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Net flows / organic growth rate",
    },
    "fee_rate_bps": {
        "profiles": ("capital_markets",),
        "pattern": _bps_after(r"(?:(?:effective\s+)?fee\s+rate|revenue\s+yield)"),
        "parse": _bps_value,
        "unit": "decimal",
        "label": "Fee rate / revenue yield",
    },
    # ---- REITs ----
    "same_store_noi_growth": {
        "profiles": ("reit",),
        "pattern": _percent_after(r"same[\s-]?(?:store|property)\s+NOI"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Same-store / same-property NOI growth",
    },
    "occupancy_rate": {
        "profiles": ("reit",),
        "pattern": _bps_or_percent_after(r"occupancy(?:\s+rate|\s+was|\s+of)?"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Occupancy rate",
    },
    "leasing_spread": {
        "profiles": ("reit",),
        "pattern": _percent_after(r"leasing\s+spread"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Leasing spread",
    },
    # ---- Aerospace & defense / industrials / semiconductors ----
    "book_to_bill_ratio": {
        "profiles": ("aerospace_defense", "semiconductor"),
        "pattern": _ratio_after(r"book[\s-]to[\s-]bill(?:\s+ratio)?(?:\s+of)?"),
        "parse": _ratio_value,
        "unit": "multiple",
        "label": "Book-to-bill ratio",
    },
    "backlog_value": {
        "profiles": ("aerospace_defense",),
        "pattern": _dollar_with_scale_after(r"backlog(?:\s+of|\s+was|\s+totaled)?"),
        "parse": _dollar_scaled_value,
        "unit": "usd",
        "label": "Backlog",
    },
    # ---- SaaS ----
    "net_revenue_retention": {
        "profiles": ("saas",),
        "pattern": _bps_or_percent_after(r"net\s+(?:dollar[\s-]based\s+|revenue[\s-]based\s+)?retention(?:\s+rate)?"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Net revenue retention",
    },
    # ---- Semiconductors / chemicals / metals / paper / IPPs (shared) ----
    "capacity_utilization": {
        "profiles": ("semiconductor", "commodity_producer", "independent_power_producer"),
        "pattern": _bps_or_percent_after(r"(?:capacity\s+utilization|utilization\s+rate)"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Capacity utilization",
    },
    # ---- Regulated utilities ----
    "rate_base_growth": {
        "profiles": ("utility",),
        "pattern": _percent_after(r"rate\s+base\s+growth"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Rate base growth",
    },
    "allowed_roe": {
        "profiles": ("utility",),
        "pattern": _bps_or_percent_after(r"(?:allowed|authorized)\s+(?:return\s+on\s+equity|ROE)"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Allowed / authorized return on equity",
    },
    # ---- Independent power producers ----
    "capacity_factor": {
        "profiles": ("independent_power_producer",),
        "pattern": _bps_or_percent_after(r"capacity\s+factor"),
        "parse": _percent_value,
        "unit": "decimal",
        "label": "Capacity factor",
    },
}


def filing_extraction_group(snapshot):
    """Which KPI subset a company should be tried against, for filing extraction only.

    Deliberately independent of ``canonical_metrics.classify_profile``: that function drives
    live-score suppression/replacement and touching it to add routing-only groups (capital
    markets, aerospace/defense, SaaS, IPP) would risk the scored composite for a purpose that
    has nothing to do with scoring. This is sector/industry substring matching against the
    same snapshot fields, kept local to this module, used only to pick a metric subset.
    """
    snapshot = snapshot or {}
    sector = str(snapshot.get("sector") or "").lower()
    industry = str(snapshot.get("industry") or "").lower()
    text = f"{sector} {industry}"
    if "bank" in industry:
        return "bank"
    if "reit" in text or "real estate investment trust" in text:
        return "reit"
    if any(term in industry for term in
           ("asset management", "capital markets", "financial data", "exchange")):
        return "capital_markets"
    if any(term in industry for term in ("aerospace", "defense")):
        return "aerospace_defense"
    if "semiconductor" in text:
        return "semiconductor"
    if "independent power" in industry or "power producers" in industry:
        return "independent_power_producer"
    if "utilit" in sector:
        return "utility"
    if any(term in text for term in
           ("chemical", "paper", "packaging", "steel", "aluminum", "copper", "metals",
            "oil", "gas", "mining", "gold", "coal")):
        return "commodity_producer"
    if any(term in industry for term in
           ("software", "internet content", "information technology services")):
        return "saas"
    return "general"


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


def near_miss_samples(lines, metric_ids, *, limit_per_metric=1):
    """For each of these (still-unresolved) metrics, up to ``limit_per_metric`` lines where
    the label matched real filing text but no value-shaped match followed close enough.

    This is the diagnostic this module has needed since its first live run: a resolution
    count alone can't say whether a metric is absent from the filing (this filer just doesn't
    disclose it) or present but phrased in a way the value regex doesn't recognize (the
    pattern needs fixing). Every prior fix to this file could only be made from the one metric
    that happened to resolve; every other pattern's near-total miss rate was otherwise
    unexplained. Returns ``{metric_id: [line, ...]}`` -- never a value, and a metric already
    resolved should not be passed in here at all (the caller filters that).
    """
    samples = {}
    for metric_id in metric_ids:
        spec = KPI_PATTERNS.get(metric_id)
        label_pattern = getattr(spec.get("pattern") if spec else None, "label_pattern", None)
        if label_pattern is None:
            continue
        found = []
        for line in lines:
            if label_pattern.search(line):
                found.append(line)
                if len(found) >= limit_per_metric:
                    break
        if found:
            samples[metric_id] = found
    return samples


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


def extract_operating_kpis_for_ticker(client, ticker, metric_ids, *, forms=("8-K",), limit=4,
                                      near_miss_sink=None):
    """Fetch this ticker's most recent qualifying exhibits and extract the requested metrics.

    Stops at the first exhibit that resolves every requested metric; otherwise merges across
    exhibits (a metric found in an earlier, more recent filing is never overwritten by a
    later, older one). Returns ``(results, filings_attempted)`` so a caller can report
    extraction coverage -- how many filings were readable, not just what was found in them.

    ``near_miss_sink``, if given a dict, is populated in place with ``{metric_id: [line, ...]}``
    for metrics whose label matched somewhere but never resolved a value -- see
    ``near_miss_samples``. Left ``None`` by default so existing callers see no behavior change;
    this only exists as an optional diagnostic channel, never returned positionally, so it
    can't change this function's return arity for anyone not asking for it.
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
            pending = [metric for metric in metric_ids if metric not in results]
            found = extract_kpis(lines, pending)
            for metric_id, reading in found.items():
                results[metric_id] = {**reading, "filed": filing.get("filed"),
                                      "form": filing.get("form")}
                if near_miss_sink is not None:
                    near_miss_sink.pop(metric_id, None)
            if near_miss_sink is not None:
                still_pending = [metric for metric in pending if metric not in found]
                for metric_id, lines_hit in near_miss_samples(lines, still_pending).items():
                    bucket = near_miss_sink.setdefault(metric_id, [])
                    for line in lines_hit:
                        if line not in bucket:
                            bucket.append(line)
        if len(results) == len(metric_ids):
            break
    return results, filings_attempted


def collect_operating_kpi_signals(client, tickers, *, metrics_by_profile, profile_for_ticker,
                                  limit_per_ticker=4, near_miss_limit_per_metric=1):
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

    The returned diagnostics dict also carries ``"near_misses"``: up to
    ``near_miss_limit_per_metric`` real evidence lines per metric where the label matched but
    no value resolved, the first time each metric hits that cap across the whole batch (a
    metric already at its cap is skipped for every later ticker, so this stays cheap across a
    ~900-name universe). This is what makes the next pattern fix evidence-based rather than a
    guess: a resolution count alone can't distinguish "this filer doesn't disclose it" from
    "the pattern doesn't recognize how this filer phrases it."
    """
    if not getattr(client, "available", True):
        return {}, {"attempted": 0, "resolved_tickers": 0, "near_misses": {}}
    results_by_ticker = {}
    filings_attempted_total = 0
    near_misses = {}
    for ticker in tickers:
        profile = profile_for_ticker(ticker)
        metric_ids = metrics_by_profile.get(profile, metrics_by_profile.get("general", []))
        if not metric_ids:
            continue
        needs_near_miss = any(len(near_misses.get(metric_id, [])) < near_miss_limit_per_metric
                              for metric_id in metric_ids)
        near_miss_sink = {} if needs_near_miss else None
        try:
            readings, attempted = extract_operating_kpis_for_ticker(
                client, ticker, metric_ids, limit=limit_per_ticker, near_miss_sink=near_miss_sink)
        except Exception:  # noqa: BLE001 - one ticker's EDGAR failure must not sink the batch
            continue
        filings_attempted_total += attempted
        if readings:
            results_by_ticker[ticker] = {
                metric_id: {**reading, "unaudited": True} for metric_id, reading in readings.items()
            }
        if near_miss_sink:
            for metric_id, lines_hit in near_miss_sink.items():
                bucket = near_misses.setdefault(metric_id, [])
                for line in lines_hit:
                    if len(bucket) >= near_miss_limit_per_metric:
                        break
                    bucket.append({"ticker": ticker, "evidence_line": line})
    return results_by_ticker, {"attempted": filings_attempted_total,
                               "resolved_tickers": len(results_by_ticker),
                               "near_misses": near_misses}


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
