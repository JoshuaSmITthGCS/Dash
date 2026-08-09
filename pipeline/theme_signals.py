"""Compute theme-exposure signals from free SEC EDGAR data.

Split deliberately from ``themes.py``: the scoring there is pure and unit-tested, while
everything network-shaped lives here behind one callable. That callable is what
``build_theme_screen`` takes, so tests inject a dictionary and production injects EDGAR.

All six signal families come from sources that cost nothing:

  * **segment_revenue_share** - ASC 280 segment reporting via the XBRL ``companyconcept``
    API. Caveat worth stating plainly: ASC 280 lets management define its own segments, so
    granularity is wildly inconsistent between filers. A company may or may not break out
    the segment a theme cares about, and there is no fixing that from outside. This is why
    ``min_signals_required`` exists - segment data alone is never allowed to carry a theme.
  * **filing_keyword_density_trend** - how much of a company's own 10-K Item 1 language is
    about the theme, and whether that share is rising. A company reorganizing its own
    self-description around a trend is doing something more informative than a price move.
  * **transcript_theme_salience** - the same measurement on earnings-call transcripts, which
    many filers attach to an 8-K, making them free on EDGAR.
  * **customer_concentration_to_spenders** - ASC 280 requires naming customers above 10% of
    revenue. Matching those names against confirmed theme spenders is a genuine free
    supply-chain edge.
  * **hyperscaler_capex_growth** - the demand side. Capex from the companies actually
    writing the cheques, pulled from their own XBRL tags.
  * **backlog_growth** - year-over-year growth in remaining performance obligation, read
    from the filing's raw XBRL/Inline XBRL contexts rather than ``company_concept``, since
    this concept is routinely tagged only in ``SatisfactionPeriodAxis`` bands with no
    undimensioned total for the aggregator API to return.

Every function degrades to None rather than raising, and every network read is cached.
"""

import re

from cache import CACHE
from common import LOG
from xbrl_dimensions import dimensional_facts, facts_on_axis, undimensioned_facts

CAPEX_CONCEPTS = ("PaymentsToAcquirePropertyPlantAndEquipment",
                  "PaymentsToAcquireProductiveAssets")
REVENUE_CONCEPTS = ("RevenueFromContractWithCustomerExcludingAssessedTax",
                    "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax")
# Post-ASC 606 remaining performance obligation. Frequently tagged only in
# SatisfactionPeriodAxis bands ("within 12 months" / "beyond 12 months") with no
# undimensioned total - a shape ``company_concept`` cannot serve, since it returns
# default (non-dimensional) facts only. See ``backlog_total``.
BACKLOG_CONCEPTS = ("RevenueRemainingPerformanceObligation",)
BACKLOG_AXIS = "SatisfactionPeriodAxis"


# ---------------- pure text measurement ----------------

def strip_markup(text):
    """Crude but adequate HTML-to-text for filing bodies."""
    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", without_tags)


def keyword_density(text, include, exclude=()):
    """Theme keyword hits per thousand words, net of excluded buzzword phrases.

    The exclusion list matters more than it looks. "AI" appears in the filings of companies
    selling AI-branded marketing software and companies building the accelerators; without
    an exclusion list a keyword screen tags both identically, which is exactly the buzzword
    dilution that makes naive thematic tagging useless.
    """
    if not text:
        return None
    lowered = strip_markup(text).lower()
    words = max(1, len(lowered.split()))
    hits = sum(lowered.count(str(phrase).lower()) for phrase in include or ())
    penalties = sum(lowered.count(str(phrase).lower()) for phrase in exclude or ())
    return round(max(0, hits - penalties) / words * 1000, 4)


def density_trend(current, prior):
    """Relative change in keyword density between two filings. None without both."""
    if current is None or not prior:
        return None
    return round(current / prior - 1, 4)


def segment_share(segment_revenue, total_revenue):
    """Fraction of revenue from the theme-relevant segment."""
    if segment_revenue is None or not total_revenue or total_revenue <= 0:
        return None
    return round(min(1.0, segment_revenue / total_revenue), 4)


def customer_overlap_share(customers, spenders):
    """Share of named >=10%-of-revenue customers that are confirmed theme spenders.

    ASC 280 requires disclosing customers above 10% of revenue. When a supplier's named
    customers are the companies doing the spending, the pull-through is documented rather
    than inferred.
    """
    named = [(str(name).upper(), share) for name, share in (customers or {}).items()]
    if not named:
        return None
    targets = {str(name).upper() for name in spenders or ()}
    if not targets:
        return None
    matched = sum(share for name, share in named
                  if any(target in name or name in target for target in targets))
    return round(min(1.0, matched), 4)


def backlog_total(facts):
    """One filing's total remaining performance obligation from dimensional facts.

    Prefers the undimensioned entity-wide tag when a filer reports one. Falls back to
    summing the ``SatisfactionPeriodAxis`` bands when it does not, since some filers
    disclose only the near-term/long-term split and never tag a consolidated total.
    Returns ``None`` when neither shape is present rather than guessing.
    """
    total_facts = undimensioned_facts(facts)
    if total_facts:
        return total_facts[0]["value"]
    banded = facts_on_axis(facts, BACKLOG_AXIS)
    if not banded:
        return None
    return sum(values[0]["value"] for values in banded.values() if values)


def growth_rate(series):
    """Year-over-year growth from a newest-first numeric series."""
    values = [value for value in (series or []) if isinstance(value, (int, float))]
    if len(values) < 2 or not values[1]:
        return None
    return round(values[0] / values[1] - 1, 4)


# ---------------- EDGAR-backed provider ----------------

def _concept_values(sec, ticker, concepts, *, cache=None, units="USD", limit=8):
    """Newest-first annual values for the first concept the filer actually tags."""
    cache = cache or CACHE
    for concept in concepts:
        def produce(concept=concept):
            return sec.company_concept(ticker, concept)
        try:
            payload = cache.fetch("sec_xbrl", f"{ticker}:{concept}", produce, source="sec_edgar")
        except Exception:  # noqa: BLE001
            continue
        rows = ((payload or {}).get("units") or {}).get(units) or []
        annual = [row for row in rows if row.get("form") in {"10-K", "20-F"} and row.get("val") is not None]
        if not annual:
            continue
        annual.sort(key=lambda row: row.get("end", ""), reverse=True)
        deduped, seen = [], set()
        for row in annual:
            year = str(row.get("end", ""))[:4]
            if year in seen:
                continue
            seen.add(year)
            deduped.append(float(row["val"]))
        if deduped:
            return deduped[:limit]
    return []


def hyperscaler_capex_growth(sec, universe, *, cache=None):
    """Aggregate capex growth across the theme's named big spenders.

    This is a theme-level number, not a company-level one: it measures whether the demand
    driving the theme is accelerating. Every company scored against the theme receives the
    same reading, which is correct - the pull-through is a property of the theme.
    """
    totals = {}
    for symbol in universe or ():
        values = _concept_values(sec, symbol, CAPEX_CONCEPTS, cache=cache)
        for index, value in enumerate(values[:2]):
            totals[index] = totals.get(index, 0.0) + value
    if len(totals) < 2:
        return None
    return growth_rate([totals.get(0), totals.get(1)])


class EdgarThemeSignals:
    """Callable signal provider backed by SEC EDGAR. Pass to ``build_theme_screen``.

    Constructed once per run so theme-level readings (hyperscaler capex, which is identical
    for every company scored against a theme) are computed once rather than per ticker.
    """

    def __init__(self, sec, *, cache=None, segment_map=None, customer_map=None):
        self.sec = sec
        self.cache = cache or CACHE
        # Segment and named-customer extraction from filing text is filer-specific enough
        # that a curated override map is more honest than a generic parser that quietly
        # guesses wrong. Anything absent from the map simply does not answer that signal.
        self.segment_map = segment_map or {}
        self.customer_map = customer_map or {}
        self._theme_level = {}

    @property
    def available(self):
        return bool(self.sec and self.sec.available)

    def theme_level(self, theme):
        """Signals shared by every company in a theme, computed once and memoized."""
        if theme["id"] in self._theme_level:
            return self._theme_level[theme["id"]]
        values = {}
        for signal in theme["signals"]:
            if signal["name"] == "hyperscaler_capex_growth":
                try:
                    values["hyperscaler_capex_growth"] = hyperscaler_capex_growth(
                        self.sec, signal.get("universe"), cache=self.cache)
                except Exception as exc:  # noqa: BLE001
                    LOG.warn(f"{theme['id']}: capex signal unavailable ({type(exc).__name__})")
        self._theme_level[theme["id"]] = values
        return values

    def filing_keyword_signals(self, ticker, theme):
        """Keyword density in the two most recent 10-Ks, and the trend between them."""
        keywords = theme.get("keywords") or {}
        include = keywords.get("include") or []
        if not include:
            return {}
        try:
            filings = self.cache.fetch(
                "sec_submissions", f"10k:{ticker}",
                lambda: self._recent_annual_reports(ticker), source="sec_edgar")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{ticker}: 10-K lookup failed ({type(exc).__name__})")
            return {}
        densities = []
        for filing in (filings or [])[:2]:
            try:
                text = self.cache.fetch(
                    "sec_document", filing["url"],
                    lambda filing=filing: self.sec.filing_document(
                        filing["cik"], filing["accession"], filing["document"]),
                    source="sec_edgar")
            except Exception:  # noqa: BLE001
                continue
            densities.append(keyword_density(text, include, keywords.get("exclude")))
        if not densities:
            return {}
        trend = density_trend(densities[0], densities[1]) if len(densities) > 1 else None
        return {"filing_keyword_density_trend": trend,
                "_keyword_density": densities[0]}

    def backlog_values(self, ticker):
        """Two most recent annual remaining-performance-obligation totals, newest first.

        Reads the raw filing document (already fetched for keyword-density scoring, so
        this is usually a cache hit) instead of ``company_concept``, because backlog is
        routinely tagged only in dimensional bands with no undimensioned total - exactly
        the shape ``company_concept`` has no way to report.
        """
        try:
            filings = self.cache.fetch(
                "sec_submissions", f"10k:{ticker}",
                lambda: self._recent_annual_reports(ticker), source="sec_edgar")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{ticker}: 10-K lookup failed ({type(exc).__name__})")
            return []
        values = []
        for filing in (filings or [])[:2]:
            try:
                text = self.cache.fetch(
                    "sec_document", filing["url"],
                    lambda filing=filing: self.sec.filing_document(
                        filing["cik"], filing["accession"], filing["document"]),
                    source="sec_edgar")
            except Exception:  # noqa: BLE001
                continue
            facts = [fact for concept in BACKLOG_CONCEPTS
                     for fact in dimensional_facts(text, concept)]
            total = backlog_total(facts)
            if total is not None:
                values.append(total)
        return values

    def _recent_annual_reports(self, ticker):
        cik = self.sec.ticker_map().get(ticker.upper())
        if not cik:
            return []
        payload = self.sec._get(f"https://data.sec.gov/submissions/CIK{cik}.json", as_json=True)
        recent = payload.get("filings", {}).get("recent", {})
        filings = []
        for index, form in enumerate(recent.get("form", [])):
            if form != "10-K":
                continue
            accession = recent["accessionNumber"][index]
            document = recent["primaryDocument"][index]
            filings.append({
                "cik": cik, "accession": accession, "document": document,
                "filed": recent.get("filingDate", [""])[index],
                "url": f"{int(cik)}/{accession}/{document}",
            })
            if len(filings) >= 2:
                break
        return filings

    def __call__(self, ticker, theme):
        if not self.available:
            return {}
        values = dict(self.theme_level(theme))
        declared = {signal["name"] for signal in theme["signals"]}

        if "segment_revenue_share" in declared:
            mapping = (self.segment_map.get(theme["id"]) or {}).get(ticker.upper())
            if mapping:
                total = _concept_values(self.sec, ticker, REVENUE_CONCEPTS, cache=self.cache)
                values["segment_revenue_share"] = segment_share(
                    mapping.get("segment_revenue"), mapping.get("total_revenue") or
                    (total[0] if total else None))

        if "filing_keyword_density_trend" in declared:
            values.update(self.filing_keyword_signals(ticker, theme))

        if "backlog_growth" in declared:
            values["backlog_growth"] = growth_rate(self.backlog_values(ticker))

        if "customer_concentration_to_spenders" in declared:
            customers = (self.customer_map.get(theme["id"]) or {}).get(ticker.upper())
            spenders = next((signal.get("universe") for signal in theme["signals"]
                             if signal["name"] == "hyperscaler_capex_growth"), None)
            values["customer_concentration_to_spenders"] = customer_overlap_share(
                customers, spenders or theme.get("seed_tickers"))

        return {key: value for key, value in values.items()
                if not key.startswith("_") and value is not None}
