"""Build the public investment-research dataset from Alpha Vantage + Yahoo fundamentals."""

import math
import os
import re
import statistics
import time
from datetime import date, datetime, timezone

from advisor_engine import (RANKING_WEIGHTS, build_research, cross_sectional_challenger,
                            normalized_metric_scores, signal_correction_variants)
from alpha_vantage import AlphaVantageClient, AlphaVantageError, load_local_env
from cache import CACHE, limiter_for, parallel_map, retry_with_backoff
from canonical_metrics import Observation, classify_profile
from data_coverage import data_coverage_components, run_source_reliability
from data_health import publication_gate, statement_health
from price_archive import archive_health
from edgar_enrichment import merge_edgar_fallback
from edgar_entities import normalize_ticker
from edgar_sue import sue_for
from providers import YahooAdapter
from common import CONFIG_DIR, LOG, load_json, save_json, update_pipeline_status
from fetch_prices import fetch_snapshot
from fundamentals_extended import (derive_extended, earnings_surprise_rows, extended_inputs,
                                   extended_observations)
from insider_signal import summarize as summarize_insiders
from reverse_dcf import derive_market_implied_growth, derive_value_creation, growth_expectations_gap
from filing_extraction import collect_operating_kpi_signals, filing_extraction_group
import return_attribution
from concentration_risk import summarize as summarize_concentration
from geographic_exposure import summarize as summarize_geography
from institutional_ownership import decay as institutional_decay
from congress_signal import score_congressional_buying
import pit_store
from fred import FredClient, FredError, fetch_regime
from layer_health import assert_layers_vary
from plausibility import screen as screen_plausibility
from market_history import (BASIS, analytics_series_payload, chart_grid,
                            hypothetical_vs_benchmark, sector_percentiles, series_payload)
from peer_groups import canonical_percentiles, peer_group_multiple_medians
from observability import diagnostics_payload, run_manifest
from marketaux import (MarketauxClient, MarketauxError, advisor_articles,
                       advisor_articles_for_symbols)
from evidence_events import build_evidence
from news_intelligence import annotate_article, deduplicate_articles
from yahoo_estimates import collect_estimate_detail
from yahoo_news import fetch_company_news, new_diagnostics as new_news_diagnostics
from scorer import (CrossSectionalNormalizer, SETTINGS, VALUATION_MULTIPLES,
                    sector_percentile_ranks, valuation_score)
from normalization_report import write_normalization_report
from normalization_audit import write_normalization_audit
from bias_report import write_bias_report
from signal_report import write_signal_report
from explainability import attach_explainability, attribution_errors, build_score_history
import growth_pit_store
import quality_pit_store
from sec_edgar import SecEdgarClient
from theme_signals import EdgarThemeSignals, recent_10k_filings
from theme_graph import build_connectivity
import theme_pit_store
from themes import build_theme_screen, empty_screen, expand_theme_candidates, load_themes
from validation.experiment_manifest import sha256_of_file
from validation.ic_harness import (append_refresh as append_ic_refresh,
                                   read_snapshots,
                                   rows_from_advisor as ic_rows_from_advisor,
                                   write_report as write_ic_report)

UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}
DEFAULT_SYMBOLS = tuple(UNIVERSE.get("symbols", ()))
PUBLISH_LIMIT = int(UNIVERSE.get("publish_limit", 20))
REVERSE_DCF_ASSUMPTIONS = SETTINGS.get("reverse_dcf", {})
RETURN_ATTRIBUTION_MONTHS_BACK = int(SETTINGS.get("return_attribution", {}).get("months_back", 12))
NEWS_CONFIG = SETTINGS["news_intelligence"]
# The event layer reuses the article annotation vocabulary (source tiers, event-type markers,
# title-similarity threshold) and adds materiality, per-event half-lives and horizon settings
# on top, so it reads one merged config rather than two half-configs.
EVIDENCE_CONFIG = {**NEWS_CONFIG, **SETTINGS["evidence_events"]}
MIN_ALPHA_PRIMARY_RELEVANCE = NEWS_CONFIG["alpha_vantage_primary_relevance_minimum"]
# How many shortlisted companies get the multi-request financial-statement treatment.
EXTENDED_LIMIT = int(UNIVERSE.get("extended_limit", PUBLISH_LIMIT * 3))
PORTFOLIO_SYMBOLS = tuple(UNIVERSE.get("portfolio_symbols", ()))
INCUMBENT_ENRICH_LIMIT = 20
CHALLENGER_ENRICH_LIMIT = 5
# Statement-starved names admitted to enrichment each refresh regardless of rank. Without
# this the enrichment queue is a closed loop over the previous run's leaders and the model
# can only rediscover names it already liked - see enrichment_rotation.
ENRICHMENT_ROTATION_SIZE = max(0, int(os.getenv("ADVISOR_ENRICHMENT_ROTATION_SIZE", "20")))
# A dedicated, sector-filtered top-up on top of the plain rotation above: bank, insurer, and
# REIT profiles carry structurally different metric sets (Round 8 found JPM's financial_health
# null even fully enriched - not a defect, just a bank balance sheet not mapping to standard
# ratios), so a sector-agnostic rotation slot spent there doesn't grow "usable, comparable
# fundamentals coverage" at the same rate as one spent on a general/industrial/tech/healthcare
# name. This queue only ever draws from profiles outside EXCLUDED_EXPANSION_PROFILES.
ENRICHMENT_EXPANSION_SIZE = max(0, int(os.getenv("ADVISOR_ENRICHMENT_EXPANSION_SIZE", "140")))
EXCLUDED_EXPANSION_PROFILES = {
    "bank", "life_insurer", "property_casualty_insurer", "diversified_insurer",
    "insurance_broker", "managed_care_insurer", "reinsurer",
    "capital_markets", "asset_manager", "consumer_finance", "financial_exchange",
    "payment_processor",
    "reit", "office_reit", "retail_reit", "industrial_reit", "residential_reit",
    "healthcare_reit", "hotel_reit", "mortgage_reit", "self_storage_reit",
    "data_center_reit", "net_lease_reit", "timber_reit",
}
# Deliberately sized close to the full financial/real-estate population in the committed
# universe, not left to the small, unfiltered general rotation - see
# enrichment_expansion_financial_real_estate. (This set grew alongside classify_profile's
# sub-industry splits: a name that used to classify as the bare "reit" or "bank" profile and
# route here still does, now under whichever subtype it splits into -- e.g. a self-storage
# REIT that used to be generic "reit" is "self_storage_reit" today, but omitting it here would
# silently reroute it into the general expansion queue this set exists to keep it out of.)
ENRICHMENT_EXPANSION_FINANCIAL_REAL_ESTATE_SIZE = max(
    0, int(os.getenv("ADVISOR_ENRICHMENT_EXPANSION_FINANCIAL_REAL_ESTATE_SIZE", "130")))
NEWS_DISCOVERY_LIMIT = 75
# Research-mode override (A3): the production enrichment queue seeds itself with the prior
# refresh's top 20 and admits only 5 new challengers, which means statement-derived metrics
# (EV/EBITDA, ROIC, interest coverage, Piotroski F) only ever exist for names a weaker model
# already liked - the champion can never discover a name its own history didn't surface.
# Setting FULL_UNIVERSE_RESEARCH=true ignores that history entirely for one run so every
# candidate gets statement enrichment on equal footing. Never the default production path -
# a full-universe statement sweep is far more Yahoo requests than the normal fast refresh.
FULL_UNIVERSE_RESEARCH = os.getenv("FULL_UNIVERSE_RESEARCH", "").strip().lower() in {"1", "true", "yes"}

# The unpublished remainder of the universe rides along so the value and momentum screens
# can scan more than the leaderboard. It carries only the fields those screens actually
# read - the full technical block is roughly three times the size, and at a universe of
# several hundred names that difference is most of the payload the browser downloads.
# Keep this in sync with src/lib/researchScreens.js.
SCREEN_TECHNICAL_FIELDS = (
    "return_5d", "return_20d", "momentum_12_1", "momentum_12_1_pct", "risk_adjusted",
    "relative_strength", "relative_strength_20d", "volume_confirmation",
    "pct_above_52w_low", "drawdown_60d", "volume_ratio_60d",
    # The swing model's continuation leg is 52-week-high proximity (George-Hwang), the one
    # momentum-family measure that carries no recent-month return and so cannot cancel its
    # reversal leg. Without this on the tail the leg only ever resolves for the published
    # leaderboard, which is the opposite of what a cross-sectional screen is for.
    "pct_from_52w_high",
    # ...and that leg is scored in the name's own volatility, not raw, because raw proximity
    # is mechanically higher for a quiet stock (measured -0.49 against realized volatility
    # across the universe) and would import an undeclared low-volatility and sector tilt.
    # See rule 4 in pipeline/swing_signals.py.
    "annualized_volatility",
    # return_60d/return_252d back a multi-horizon breadth check for rankMomentum's
    # corroboration gate - a 5d/20d pop inside a longer downtrend shouldn't pass as
    # genuine momentum. Keep in sync with src/lib/researchScreens.js.
    "return_60d", "return_252d",
    # MetricSections.jsx's "Behaviour & tradability" section (@technical.* keys) reads all
    # four of these directly off the row's own detail modal - without them here a tail name
    # (anything outside the top publish_limit) opened the "All metrics" tab to a blank
    # section no matter how current the refresh was, the same class of bug EXTENDED_METRIC_
    # FIELDS below fixes for the rest of the panel.
    "max_drawdown_252d", "sharpe_ratio", "sortino_ratio", "relative_acceleration",
    "relative_acceleration_detail",
)

# Every scalar valuation/profitability/financial-health/accounting-quality/capital-allocation/
# growth/ownership metric MetricSections.jsx (the "All metrics" detail panel) reads directly
# off a row - kept in sync with that file's SECTIONS list. Published for the whole scored
# universe, not just the top publish_limit: a client-side ranking model (rankingModels.js)
# scores every one of these names on these inputs, so "why is this name ranked where it is"
# has to be answerable from any screen, not only the leaderboard. Before this, opening a
# tail name's stock detail sheet showed every one of these as a dash regardless of how
# current the refresh was or how fully the pipeline had enriched it - the values existed on
# the full advisor.json row, this projection just never carried them past it.
EXTENDED_METRIC_FIELDS = (
    "peg", "forward_pe", "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "ev_to_sales",
    "price_to_sales", "price_to_book", "price_to_tangible_book", "dividend_yield",
    "return_on_invested_capital", "gross_profits_to_assets", "return_on_equity",
    "cash_conversion", "free_cash_flow_yield", "operating_margin", "operating_margin_trend",
    "incremental_margin", "profit_margin", "interest_coverage", "net_debt_to_ebitda",
    "debt_to_equity", "current_ratio", "altman_z", "piotroski_f", "accruals_ratio",
    "days_sales_outstanding", "days_sales_outstanding_trend", "inventory_days",
    "inventory_days_trend", "net_buyback_yield", "stock_comp_to_revenue",
    "capex_to_depreciation", "asset_growth", "gross_buyback_yield", "revenue_growth",
    "earnings_growth", "fcf_growth_3y", "institutional_ownership", "insider_ownership",
    "beta", "average_dollar_volume", "implied_volatility", "realized_volatility_20d",
    "implied_realized_vol_ratio",
)

# The Financial Report, Portfolio, and browseable Research list need prices, chart history,
# scoring inputs, and published action guidance, but not several megabytes of statement-level
# evidence. Publishing this projection keeps those routes fast while advisor.json remains the
# complete source fetched on demand for a deep company-research sheet.
REPORT_ROW_FIELDS = (
    "ticker", "name", "price", "sector", "industry", "average_dollar_volume",
    "score", "stance", "strengths", "recommendation", "components",
    "fundamental_detail", "technical_detail", "sentiment_detail", "debt_to_equity",
    "current_ratio", "return_on_equity", "revenue_growth", "data_fetched_at",
    "theme_exposure", "data_coverage", "risks", "fundamental_categories",
    "evidence_summary", "sentiment_summary", "estimate_detail", "earnings_surprise",
    "standardized_unexpected_earnings", "analyst_count", "analyst_rating",
    "analyst_target_upside", "sector_valuation_percentile", "fcf_growth_3y",
    "free_cash_flow_yield", "interest_coverage", "net_buyback_yield",
    "operating_margin", "operating_margin_trend", "short_percent_of_float",
    "days_to_cover", "is_etf",
    # The full extended-metrics stack (MetricSections.jsx's "All metrics" panel) - see
    # EXTENDED_METRIC_FIELDS's own docstring above. Appended rather than merged into the
    # list above: several names overlap (e.g. debt_to_equity, revenue_growth) and a tuple
    # used only to drive a `{key: row.get(key) ...}` comprehension in report_row() below
    # tolerates that duplication for free, so there is no need to hand-dedupe two lists
    # that already agree on the field name and would just have to be kept in sync twice.
    # Without this, report.json's projection (report_row(), applied on top of
    # advisor.json's already-lightweight screen_universe rows) stripped these metrics a
    # second time even after _screen_row() started publishing them.
    *EXTENDED_METRIC_FIELDS,
)
# Symbols withdrawn from the product entirely, with the reason each was retired - the reason
# is published into the point-in-time universe store's churn note (see record_universe below)
# so the departure is explained in `universe_churn`, not just observable. Retiring a symbol has
# to reach the refresh list, not just the published report: portfolio holdings are carried
# forward from the previous run's own `portfolio_coverage`, so anything that ever entered that
# list re-seeded itself on every subsequent run and could never be removed - not by deleting
# it in the app, not by editing config. Membership checks below use `in`, which reads dict
# keys, so this stays a drop-in for the former set.
RETIRED_SYMBOLS = {
    "DECJ": "typo for DECK (already tracked); resolves to nothing at any provider",
    # Round 7 Task 1: the two `missing_price_tickers` breaching data_quality_counters as of
    # refresh advisor-2026-08-21T18:56:08. Both are hand-entered holdings (neither is in the
    # Aug 14 Fidelity reference export), both have price:null and last_polled_at:null - no
    # provider has ever returned a row for either, so this is not a rate limit and not a
    # join bug.
    "TTM": "Tata Motors NYSE ADR delisted January 2025; no provider serves this line anymore",
    "AMZM": "resolves to nothing at any provider (likely a typo for AMZN - re-add AMZN with "
            "real cost basis if the position was intended)",
}


def _layer(*path):
    """Extractor that walks a nested payload path, returning None at the first gap."""
    def read(row):
        node = row
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node
    return read


# Every number this pipeline publishes as a scored "layer", checked for cross-sectional
# variance before the payload is written (see layer_health.assert_layers_vary). Adding a
# scored layer without adding it here means nothing verifies it is a layer at all.
PUBLISHED_LAYERS = {
    "score": _layer("score"),
    "base_score": _layer("base_score"),
    "raw_score": _layer("raw_score"),
    "components.fundamentals": _layer("components", "fundamentals"),
    "components.market_behavior": _layer("components", "market_behavior"),
    "components.news_sentiment": _layer("components", "news_sentiment"),
    "fundamental_categories.valuation": _layer("fundamental_categories", "valuation"),
    "fundamental_categories.profitability": _layer("fundamental_categories", "profitability"),
    "fundamental_categories.financial_health": _layer("fundamental_categories", "financial_health"),
    "fundamental_categories.growth": _layer("fundamental_categories", "growth"),
    "fundamental_categories.capital_allocation": _layer("fundamental_categories", "capital_allocation"),
    "fundamental_categories.accounting_quality": _layer("fundamental_categories", "accounting_quality"),
    "analysis_v2.structural.effective_score": _layer("analysis_v2", "structural", "effective_score"),
    "analysis_v2.timeliness.effective_score": _layer("analysis_v2", "timeliness", "effective_score"),
}


def report_row(row):
    history = row.get("history") or {}
    analytics_history = row.get("analytics_history") or {}
    projected = {key: row.get(key) for key in REPORT_ROW_FIELDS if row.get(key) is not None}
    # Full leaderboard rows carry detailed evidence/article records while lightweight rows
    # already carry summaries. The route-critical projection always publishes the compact
    # shape so client-side ranking models retain their inputs without downloading every raw
    # event in advisor.json.
    if "evidence_summary" not in projected:
        summary = _evidence_summary(row.get("evidence"))
        if summary:
            projected["evidence_summary"] = summary
    if "sentiment_summary" not in projected:
        summary = _sentiment_summary(row.get("sentiment_detail"))
        if summary:
            projected["sentiment_summary"] = summary
    structural = (row.get("analysis_v2") or {}).get("structural")
    if structural:
        projected["analysis_v2"] = {"structural": structural}
    if history.get("dates") and history.get("closes"):
        projected["history"] = {"dates": history["dates"], "closes": history["closes"]}
    if analytics_history.get("dates") and analytics_history.get("closes"):
        projected["analytics_history"] = analytics_history
    return projected


def report_snapshot(payload):
    """Create the compact, route-critical subset consumed by report/research views."""
    def active(rows):
        return [row for row in rows if str(row.get("ticker") or "").upper() not in RETIRED_SYMBOLS]

    theme_screen = payload.get("theme_screen") or {}

    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "data_mode": payload.get("data_mode"),
        "universe_count": payload.get("universe_count"),
        # A flat list of ~900 ticker strings (a few KB) — Search.jsx needs it to find a
        # tracked-but-unscored ticker beyond the scored screen_universe rows above; nothing
        # else in this snapshot needed it, which is why it was not carried before.
        "universe": payload.get("universe"),
        "hypothetical_basis": payload.get("hypothetical_basis"),
        "benchmark_history": payload.get("benchmark_history"),
        "benchmark_analytics_history": payload.get("benchmark_analytics_history"),
        "source_status": payload.get("source_status"),
        "market": payload.get("market"),
        "theme_screen": {
            key: theme_screen.get(key) for key in ("generated_at", "by_ticker", "unavailable_reason")
            if theme_screen.get(key) is not None
        },
        "research": [report_row(row) for row in active(payload.get("research", []))],
        "portfolio_coverage": [report_row(row) for row in active(payload.get("portfolio_coverage", []))],
        "screen_universe": [report_row(row) for row in active(payload.get("screen_universe", []))],
    }


# Trust ordering for pipeline/config/settings.json's source_quality tiers (by weight:
# regulatory_primary 1.5, established_press 1.2, neutral 1.0, aggregator_syndicated 0.65).
# Used only to pick the single best tier present for the lightweight screen projection
# below - the full per-article breakdown stays published-leaderboard-only.
SOURCE_QUALITY_TRUST_ORDER = ("regulatory_primary", "established_press", "neutral", "aggregator_syndicated")


def _sentiment_summary(sentiment_detail):
    """Distill sentiment_detail to the handful of fields rankCatalyst's corroboration
    check needs (article count, filing count, best source quality) without carrying the
    full per-article breakdown onto every screen_universe row."""
    detail = sentiment_detail or {}
    articles = detail.get("articles") or []
    tiers_present = {article.get("source_quality_tier") for article in articles if article.get("source_quality_tier")}
    best_tier = next((tier for tier in SOURCE_QUALITY_TRUST_ORDER if tier in tiers_present), None)
    if detail.get("article_count") is None and not articles and best_tier is None:
        return None
    return {
        "article_count": detail.get("article_count"),
        "filing_count": detail.get("filing_count"),
        "best_source_quality_tier": best_tier,
    }


def _evidence_summary(evidence):
    """The evidence block trimmed to what a client-side screen actually reads.

    The full per-event breakdown is for the published leaderboard, where a reader can open one
    company and audit it. Shipping twelve fully-detailed events for each of ~900 universe rows
    would roughly double the payload to answer a question nobody asks of the 800th-ranked
    name, so the tail carries the scores, the freshness that produced them, and the single
    dominant event - enough for a screen to rank on and explain itself.
    """
    if not evidence:
        return None
    # A carried-forward row from a fast refresh arrives already in this shape (it was
    # projected by an earlier run), so re-projecting it would strip the dominant-event fields
    # it already holds - same "may already be lightweight" case _screen_row handles.
    if "news_detail" not in evidence and "event_count" in evidence:
        return evidence
    news_detail = evidence.get("news_detail") or {}
    insider_detail = evidence.get("insider_detail") or {}
    return {
        "news_score": evidence.get("news_score"),
        "insider_score": evidence.get("insider_score"),
        "insider_score_long_term": evidence.get("insider_score_long_term"),
        "expectation_score": evidence.get("expectation_score"),
        "dominant_event": news_detail.get("dominant_event"),
        "dominant_event_types": news_detail.get("dominant_event_types"),
        "dominant_age_trading_days": news_detail.get("dominant_age_trading_days"),
        "dominant_materiality": news_detail.get("dominant_materiality"),
        "event_count": news_detail.get("event_count", 0),
        "insider_freshest_age_trading_days": insider_detail.get("freshest_age_trading_days"),
        "expectation_inputs_resolved": (evidence.get("expectation_detail") or {}).get("inputs_resolved", 0),
    }


def _screen_sue(row):
    """Standardized unexpected earnings for a screen row, read from the EDGAR PIT store.

    Published with its announcement date rather than as a bare number: the client-side swing
    model has to be able to tell an open drift window from a closed one, and the store is the
    only place the announcement date exists. Costs no network call - the facts are on disk.
    Carried-forward rows keep whatever they already had rather than re-reading the store.
    """
    existing = row.get("standardized_unexpected_earnings")
    if existing is not None:
        return existing
    try:
        return sue_for(row.get("ticker"), datetime.now(timezone.utc).date().isoformat())
    except Exception as exc:  # noqa: BLE001 - a missing surprise must not sink the row
        LOG.warn(f"{row.get('ticker')}: SUE unavailable ({type(exc).__name__}: {exc})")
        return None


def _screen_data_coverage(row):
    """This row's measured data coverage, from the row itself or its champion variant.

    The variant fallback is what makes the fix reach the tail on the very next run rather
    than only as names are re-polled. A fast refresh carries several hundred rows forward
    from the last published file, and every one of those predates the row-level field - but
    they all already carry the identical number under ``score_variants.champion``, because
    that is the variant the published score is taken from. Without the fallback those
    carried rows would keep reporting no measurement until their rotation slot came up.
    """
    coverage = row.get("data_coverage")
    if coverage is None:
        champion = (row.get("score_variants") or {}).get("champion") or {}
        coverage = champion.get("data_coverage")
    return coverage if isinstance(coverage, (int, float)) else None


def _screen_row(row):
    """Project a full or already-lightweight row into the screen_universe shape.

    ``.get`` throughout because a carried-forward row from a fast refresh may itself
    already be in this lightweight shape (if it was never published to begin with).
    """
    detail = row.get("technical_detail") or {}
    variants = {
        key: {field: variant.get(field) for field in (
            "variant", "normalization_mode", "score", "base_score", "data_coverage",
            "fundamental_categories", "normalized_metric_scores", "largest_metric_changes",
        ) if variant.get(field) is not None}
        for key, variant in (row.get("score_variants") or {}).items()
    }
    return {
        "ticker": row["ticker"], "name": row.get("name"), "sector": row.get("sector"),
        # Carried at the theme screen's request: sector alone cannot tell a chip-equipment
        # maker from a trucking company, so a reader judging whether a name really belongs in
        # a structural trend needs the finer classification the theme scope is matched on.
        "industry": row.get("industry"),
        "price": row.get("price"), "score": row["score"], "stance": row.get("stance"),
        # Without this flag every fund in the universe reads as an ordinary company to the
        # client-side strategy screens, which gate on per-security fundamentals a fund does
        # not have - VOO ranked as a stock and, at one point, was the single name clearing
        # the catalyst screen.
        "is_etf": row.get("is_etf", False),
        # Measured for every scored row, and previously discarded here - the single most
        # consequential omission this projection ever made. The browser gates every action
        # label on the row-level field (src/lib/confidenceGate.js), so dropping it made all
        # ~840 tail rows read "no coverage measurement was published", which the confidence
        # gate correctly treats as `insufficient`. The measurement existed the whole time:
        # the champion variant below carried it, and against the published snapshot only 117
        # of 839 rows were actually under the 40% floor while 114 measured high enough to
        # carry an action call. Absent and zero are different claims (see the band table in
        # confidenceGate.js), so this stays None rather than 0.0 when nothing resolved.
        "data_coverage": _screen_data_coverage(row),
        # When this row's inputs were last actually fetched, as opposed to carried forward
        # from an earlier run. It is what lets a fast refresh rotate the stalest part of the
        # tail back into the poll (see rotation_slice) instead of re-polling the same
        # leaders every time and leaving the rest to age indefinitely.
        "last_polled_at": row.get("last_polled_at"),
        "score_variants": variants or None,
        "components": row.get("components"), "fundamental_categories": row.get("fundamental_categories"),
        # Just the one field enrichment_rotation()'s last_enriched() reads, not the ~2KB
        # nested fundamental_detail every research row carries: publishing that for the
        # ~850-name tail would bloat the payload for no reader-facing purpose. Without even
        # this much, a name enriched via rotation that doesn't crack the top publish_limit
        # loses its "already has statement coverage" signal the moment it lands here, so
        # every subsequent run sees it as never-enriched and rotation keeps re-selecting it
        # instead of a genuinely untouched name -- silently capping how much of the universe
        # ever gets past the initial shortlist.
        "fundamental_detail": {"raw_score": (row.get("fundamental_detail") or {}).get("raw_score")},
        "technical_detail": {key: detail.get(key) for key in SCREEN_TECHNICAL_FIELDS
                             if detail.get(key) is not None},
        # The full valuation/profitability/financial-health/accounting-quality/capital-
        # allocation/growth/ownership metric stack - see EXTENDED_METRIC_FIELDS above for
        # why this is published for every scored row, not just the leaderboard.
        **{key: row.get(key) for key in EXTENDED_METRIC_FIELDS if row.get(key) is not None},
        # Needed by the client-side strategy-lens sorts (rankCatalyst, rankAnalystConviction,
        # tailwind/theme opportunity) so those lenses can scan beyond the published
        # leaderboard - the same "scan more than the leaderboard" rationale as the
        # technical fields above, not the full nested SEC filing/estimate detail.
        "insider_activity": row.get("insider_activity"),
        "analyst_count": row.get("analyst_count"),
        "analyst_rating": row.get("analyst_rating"),
        "analyst_target_upside": row.get("analyst_target_upside"),
        "analyst_consensus_target": row.get("analyst_consensus_target"),
        # Small enough to carry for the whole universe, and the analyst-conviction model is
        # specifically meant to surface names outside the published leaderboard.
        "estimate_detail": row.get("estimate_detail"),
        "theme_exposure": row.get("theme_exposure"),
        # Corroboration inputs for the strategy-lens gates (rankReversal,
        # rankValueTurnarounds, rankAnalystConviction, rankCatalyst) - independent
        # cross-checks against each lens's primary signal, not part of any score.
        "earnings_surprise": row.get("earnings_surprise"),
        # The swing ranking model's post-earnings-drift leg. Deliberately a separate field
        # from earnings_surprise above: that one is a four-quarter weighted average of
        # percent surprise built for fundamental momentum (and 0/839 populated while the
        # Yahoo earnings-dates scrape is down), this is the most-recent standardized
        # seasonal surprise PEAD is a claim about, read from the EDGAR point-in-time store.
        # See edgar_sue.py. The two are not interchangeable and are never blended.
        "standardized_unexpected_earnings": _screen_sue(row),
        "short_percent_of_float": row.get("short_percent_of_float"),
        "days_to_cover": row.get("days_to_cover"),
        "sector_valuation_percentile": row.get("sector_valuation_percentile"),
        "sentiment_summary": _sentiment_summary(row.get("sentiment_detail")),
        # Dated evidence for the whole universe, not just the leaderboard - the catalyst and
        # analyst-conviction screens are meant to surface names that are *not* already top
        # fundamentals scores, so they need this on the tail or they cannot do their job.
        "evidence_summary": _evidence_summary(row.get("evidence") or row.get("evidence_summary")),
        "stale_carryforward": row.get("stale_carryforward", False),
    }


def resolve_refresh_symbols(
    requested_symbols,
    configured_portfolio,
    portfolio_override="",
    previous_portfolio=(),
):
    """Include every valid current holding in Yahoo fetches and portfolio coverage."""
    dynamic_portfolio = portfolio_override.split(",") if portfolio_override else ()

    def valid_symbols(values):
        normalized = []
        for value in values:
            symbol = str(value or "").strip().upper()
            if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
                normalized.append(symbol)
        return normalized

    portfolio_symbols = tuple(dict.fromkeys(
        symbol
        for symbol in (
            *valid_symbols(configured_portfolio),
            *valid_symbols(previous_portfolio),
            *valid_symbols(dynamic_portfolio),
        )
        # Filtered here rather than at the point of publication so a retired symbol also stops
        # being polled and stops re-entering the carry-forward it seeds itself from.
        if symbol not in RETIRED_SYMBOLS
    ))
    symbols = tuple(dict.fromkeys(
        (*valid_symbols(requested_symbols), *portfolio_symbols)
    ))
    return symbols, portfolio_symbols


def number(value, digits=4):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def daily_history(payload):
    series = payload.get("Time Series (Daily)", {})
    rows = sorted(series.items())
    dates = [day for day, values in rows if values.get("4. close")]
    closes = [float(values["4. close"]) for _, values in rows if values.get("4. close")]
    volumes = [float(values.get("5. volume") or 0) for _, values in rows if values.get("4. close")]
    highs = [float(values["2. high"]) for _, values in rows if values.get("4. close")]
    lows = [float(values["3. low"]) for _, values in rows if values.get("4. close")]
    return {"dates": dates, "closes": closes, "volumes": volumes, "highs": highs, "lows": lows}


EMPTY_HISTORY = {"dates": [], "closes": [], "volumes": [], "highs": [], "lows": []}


def carry_forward_missing_sessions(previous_dates, previous_closes, fresh):
    """Union a freshly fetched price history with the previously published one, by date.

    A live fetch (Alpha Vantage or Yahoo) can legitimately return fewer sessions than a prior
    run already published - a provider outage, a truncated response window, a transient NaN
    row - and every downstream consumer (the live-tracking countdown among them) counts on
    ``dates`` only ever growing. Publishing a shorter series makes real progress look like it
    reversed. Dates the fresh fetch has always win (a provider can restate a close); any date
    only the previous run had is carried forward with its previous close and zero volume.
    """
    fresh_dates = fresh.get("dates") or []
    if not previous_dates:
        return fresh
    # Runs once per symbol across the whole universe, so membership goes through a set rather
    # than a scan of the fresh date list.
    fresh_lookup = set(fresh_dates)
    missing = [date for date in previous_dates if date not in fresh_lookup]
    if not missing:
        return fresh
    fresh_volumes = fresh.get("volumes") or [0.0] * len(fresh_dates)
    merged = dict(zip(fresh_dates, zip(fresh["closes"], fresh_volumes)))
    previous_close_by_date = dict(zip(previous_dates, previous_closes))
    for date in missing:
        close = previous_close_by_date.get(date)
        if close is not None:
            merged[date] = (close, 0.0)
    ordered = sorted(merged)
    return {
        "dates": ordered,
        "closes": [merged[date][0] for date in ordered],
        "volumes": [merged[date][1] for date in ordered],
    }


def yahoo_history(symbol, yf, period="2y", ticker_obj=None, cache=None):
    """Dates, closes, and volumes. Two years so max drawdown and 52-week context are real.

    Served from the on-disk cache when a recent copy exists, which is what makes a rerun
    cheap and keeps the universe sweep off Yahoo's undocumented rate limiter.
    """
    if not yf:
        return dict(EMPTY_HISTORY)
    cache = cache or CACHE

    def produce():
        source = ticker_obj or yf.Ticker(symbol)
        frame = source.history(period=period, auto_adjust=False).dropna(subset=["Close"])
        if frame.empty:
            raise ValueError("empty price frame")
        return {
            "dates": [str(index)[:10] for index in frame.index],
            "closes": [float(value) for value in frame["Close"].tolist()],
            "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
            "highs": [float(value) for value in frame["High"].tolist()],
            "lows": [float(value) for value in frame["Low"].tolist()],
        }

    try:
        return cache.fetch("price_history", f"{symbol}:{period}", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return dict(EMPTY_HISTORY)


def prefetch_histories(symbols, yf, period="2y", cache=None):
    """Warm the price cache for the whole universe in a handful of HTTP calls.

    ``yf.download`` batches many symbols into far fewer requests than one Ticker call each,
    which is both the biggest speed win available and the most reliable way to stay under a
    rate limit nobody publishes. Anything the batch misses falls back to a per-symbol fetch
    at the normal call site, so a partial batch degrades rather than fails.
    """
    if not yf or not symbols:
        return 0
    cache = cache or CACHE
    missing = [symbol for symbol in symbols
               if cache.get("price_history", f"{symbol}:{period}") is None]
    if not missing:
        LOG.info(f"Price history: all {len(symbols)} symbols served from cache")
        return 0
    warmed = 0
    batch_size = int(os.getenv("YAHOO_BATCH_SIZE", "60"))
    for start in range(0, len(missing), batch_size):
        chunk = missing[start:start + batch_size]
        try:
            frame = retry_with_backoff(
                lambda chunk=chunk: yf.download(chunk, period=period, auto_adjust=False,
                                                group_by="ticker", progress=False, threads=True),
                description=f"batch history for {len(chunk)} symbols")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"batch history failed ({type(exc).__name__}); "
                     "per-symbol fetches will cover this chunk")
            continue
        for symbol in chunk:
            payload = YahooAdapter.extract_symbol_frame(frame, symbol, single=len(chunk) == 1)
            if payload:
                cache.set("price_history", f"{symbol}:{period}", payload, source="yahoo")
                warmed += 1
    LOG.info(f"Price history: warmed {warmed}/{len(missing)} uncached symbols in batches")
    return warmed


def yahoo_snapshot(symbol, yf, ticker_obj=None, attempts=2, cache=None):
    """Quote-derived snapshot for one company, served from cache when it is fresh."""
    if not yf:
        return None
    cache = cache or CACHE
    cached = cache.get("quote", f"snapshot:{symbol}")
    if cached:
        return cached
    for attempt in range(attempts):
        snapshot = fetch_snapshot(symbol, yf, set(), ticker_obj)
        if snapshot:
            return cache.set("quote", f"snapshot:{symbol}", snapshot, source="yahoo")
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return None


def prefetch_snapshots(symbols, yf, cache=None):
    """Warm the quote cache in parallel so the sequential collect loop mostly reads memory.

    Quotes cannot be batched the way price history can - each one is its own request - so
    the lever here is concurrency rather than batching. The pool is bounded and paced by the
    Yahoo rate limiter, which is what makes a universe of several hundred names finish
    inside the workflow's timeout instead of crawling through them one at a time.
    """
    if not yf or not symbols:
        return 0
    cache = cache or CACHE
    missing = [symbol for symbol in symbols
               if cache.get("quote", f"snapshot:{symbol}") is None]
    if not missing:
        LOG.info(f"Quotes: all {len(symbols)} symbols served from cache")
        return 0

    def fetch_one(symbol):
        limiter_for("yahoo").acquire()
        snapshot = fetch_snapshot(symbol, yf, set())
        if snapshot:
            cache.set("quote", f"snapshot:{symbol}", snapshot, source="yahoo")
            return 1
        return 0

    workers = int(os.getenv("YAHOO_QUOTE_WORKERS", "6"))
    warmed = sum(result or 0 for result in
                 parallel_map(fetch_one, missing, provider="yahoo", max_workers=workers))
    LOG.info(f"Quotes: warmed {warmed}/{len(missing)} uncached symbols")
    return warmed


# Earnings surprises come from a scraped page, one request per symbol, on an endpoint that
# is noticeably flakier than the statement bundle. Opt-in for the same reason option chains
# are: a per-symbol extra request has to earn its place. The first production run scored
# 0/40 companies on it, so leaving it on by default would spend ~110 requests to populate a
# metric that never resolves. The weight stays in config - missing values reweight - so
# enabling it later needs no other change.
EARNINGS_SURPRISE_ENABLED = os.getenv("ENABLE_EARNINGS_SURPRISE", "").lower() in {"1", "true", "yes"}
EARNINGS_SURPRISE_STATS = {"requested": 0, "resolved": 0, "failed": 0}


def fetch_earnings_surprises(symbol, ticker_obj, cache=None):
    """Cached, opt-in earnings-surprise history with visible failures."""
    if not EARNINGS_SURPRISE_ENABLED or ticker_obj is None:
        return []
    cache = cache or CACHE
    EARNINGS_SURPRISE_STATS["requested"] += 1

    def produce():
        failures = []
        rows = earnings_surprise_rows(ticker_obj, on_error=failures.append)
        if failures:
            raise failures[0]
        return rows

    try:
        rows = cache.fetch("statements", f"earnings_surprise:{symbol}", produce, source="yahoo")
    except Exception as exc:  # noqa: BLE001
        EARNINGS_SURPRISE_STATS["failed"] += 1
        LOG.warn(f"{symbol}: earnings surprise history unavailable ({type(exc).__name__})")
        return []
    if rows:
        EARNINGS_SURPRISE_STATS["resolved"] += 1
    return rows or []


def yahoo_extended(symbol, ticker_obj, snapshot, history, diagnostics=None):
    """Statement-derived quality, capital-allocation, and accounting metrics for one company.

    ``.info`` and the annual/quarterly statement frames are two independent Yahoo requests
    with independent failure modes (``.info`` is the fragile quoteSummary/crumb-backed call;
    the statement frames have their own per-call fallback in ``extended_inputs``). They used
    to share one try/except, so a broken ``.info`` call silently discarded statement data that
    had already been fetched successfully -- the entire company enriched to nothing even when
    ROIC, Piotroski, Altman-Z, and the other statement-only metrics were available. Fetching
    them separately lets a company enrich on whatever half of the data actually came back.
    """
    as_of_today = datetime.now(timezone.utc).date().isoformat()
    if ticker_obj is None:
        return merge_edgar_fallback(symbol, {}, snapshot, as_of=as_of_today,
                                    diagnostics=diagnostics)
    try:
        inputs = extended_inputs(ticker_obj)
    except Exception as exc:  # noqa: BLE001 - extended_inputs already guards each statement call
        LOG.warn(f"{symbol}: statement frames unavailable ({type(exc).__name__}: {exc})")
        if diagnostics is not None:
            diagnostics["statement_fetch_failed"] += 1
        return merge_edgar_fallback(symbol, {}, snapshot, as_of=as_of_today,
                                    diagnostics=diagnostics)
    try:
        info = ticker_obj.info or {}
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo quote-summary (.info) unavailable ({type(exc).__name__}: {exc}); "
                 "continuing with statement-only metrics")
        if diagnostics is not None:
            diagnostics["info_fetch_failed"] += 1
        info = {}
    try:
        result = derive_extended(
            annual=inputs["annual"], quarterly=inputs["quarterly"], info=info,
            market_cap=snapshot.get("market_cap"), price=snapshot.get("price"),
            sector=snapshot.get("sector"), closes=history["closes"], volumes=history["volumes"],
            earnings_surprises=fetch_earnings_surprises(symbol, ticker_obj),
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: extended fundamentals derivation failed ({type(exc).__name__}: {exc})")
        if diagnostics is not None:
            diagnostics["derivation_failed"] += 1
        return merge_edgar_fallback(symbol, {}, snapshot, as_of=as_of_today,
                                    diagnostics=diagnostics)
    if REVERSE_DCF_ASSUMPTIONS:
        priced_in = derive_market_implied_growth(
            beta=result.get("beta"), market_cap=snapshot.get("market_cap"),
            total_debt=result.get("total_debt"), enterprise_value=result.get("enterprise_value"),
            free_cash_flow=result.get("free_cash_flow"),
            interest_coverage=result.get("interest_coverage"), assumptions=REVERSE_DCF_ASSUMPTIONS)
        if priced_in:
            result["market_implied_growth"] = priced_in["market_implied_growth"]
            result["market_implied_growth_wacc"] = priced_in["wacc_assumed"]
            result["market_implied_growth_exceeds_ceiling"] = priced_in["exceeds_plausible_ceiling"]
            result["growth_expectations_gap"] = growth_expectations_gap(
                market_implied_growth=priced_in["market_implied_growth"],
                realized_growth=result.get("fcf_growth_3y"))
        value_creation = derive_value_creation(
            roic=result.get("return_on_invested_capital"), beta=result.get("beta"),
            market_cap=snapshot.get("market_cap"), total_debt=result.get("total_debt"),
            interest_coverage=result.get("interest_coverage"), assumptions=REVERSE_DCF_ASSUMPTIONS)
        result["wacc_assumed"] = value_creation["wacc_assumed"]
        result["value_creation_spread"] = value_creation["value_creation_spread"]
    if os.getenv("ENABLE_OPTIONS_VOLATILITY", "").lower() in {"1", "true", "yes"}:
        result.update(yahoo_options_volatility(ticker_obj, snapshot.get("price"), history["closes"]))
    return merge_edgar_fallback(symbol, result, snapshot, as_of=as_of_today,
                                diagnostics=diagnostics)


def yahoo_options_volatility(ticker_obj, price, closes):
    """Near-the-money implied volatility against 20-session realized volatility.

    Options data is opt-in because each symbol adds an option-chain request. Median IV
    across calls and puts within 10% of spot is more robust than trusting one contract.
    """
    realized = None
    if len(closes) >= 21 and all(value > 0 for value in closes[-21:]):
        returns = [math.log(closes[index] / closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
        realized = statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    try:
        expirations = ticker_obj.options
        if not expirations or not price:
            return {"implied_volatility": None, "realized_volatility_20d": number(realized)}
        chain = ticker_obj.option_chain(expirations[0])
        values = []
        for frame in (chain.calls, chain.puts):
            for _, contract in frame.iterrows():
                strike, iv = contract.get("strike"), contract.get("impliedVolatility")
                if strike and iv and abs(strike / price - 1) <= 0.10 and 0 < iv < 5:
                    values.append(float(iv))
        implied = statistics.median(values) if values else None
        return {
            "implied_volatility": number(implied),
            "realized_volatility_20d": number(realized),
            "implied_realized_vol_ratio": number(implied / realized) if implied and realized else None,
            "options_expiration_sampled": expirations[0],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"options volatility unavailable ({type(exc).__name__})")
        return {"implied_volatility": None, "realized_volatility_20d": number(realized)}


def overview_snapshot(symbol, overview, closes):
    market_cap = number(overview.get("MarketCapitalization"), 0)
    fetched_at = datetime.now(timezone.utc).isoformat()
    observation_specs = {
        "market_cap": ("MarketCapitalization", "usd", False, False),
        "forward_pe": ("ForwardPE", "multiple", False, True),
        "provider_peg": ("PEGRatio", "multiple", False, False),
        "price_to_book": ("PriceToBookRatio", "multiple", False, False),
        "trailing_revenue_growth": ("QuarterlyRevenueGrowthYOY", "decimal", False, False),
        "quarterly_eps_growth": ("QuarterlyEarningsGrowthYOY", "decimal", False, False),
    }
    observations = {}
    for metric_id, (field, unit, is_ttm, is_forward) in observation_specs.items():
        value = number(overview.get(field))
        if value is None:
            continue
        flags = [] if metric_id == "market_cap" else ["provider_period_not_supplied"]
        if metric_id == "provider_peg":
            flags.append("unknown_growth_definition_and_horizon")
        if metric_id in ("trailing_revenue_growth", "quarterly_eps_growth"):
            flags.append("quarterly_not_ttm")
        observations[metric_id] = [Observation(
            value=value, unit=unit, source="alpha_vantage", source_field=field,
            observed_at=fetched_at, fetched_at=fetched_at, is_ttm=is_ttm,
            is_forward=is_forward, quality_flags=flags,
        ).to_dict()]
    return {
        "ticker": symbol,
        "name": overview.get("Name") or symbol,
        "description": overview.get("Description") or "",
        "exchange": overview.get("Exchange"),
        "currency": overview.get("Currency"),
        "sector": overview.get("Sector"),
        "industry": overview.get("Industry"),
        "price": round(closes[-1], 2) if closes else None,
        "market_cap": market_cap,
        "dividend_yield": number(overview.get("DividendYield")),
        "is_etf": False,
        "price_to_sales": number(overview.get("PriceToSalesRatioTTM")),
        "price_to_book": number(overview.get("PriceToBookRatio")),
        "forward_pe": number(overview.get("ForwardPE")),
        "trailing_pe": number(overview.get("PERatio")),
        "peg": number(overview.get("PEGRatio")),
        "return_on_equity": number(overview.get("ReturnOnEquityTTM")),
        "profit_margin": number(overview.get("ProfitMargin")),
        "revenue_growth": number(overview.get("QuarterlyRevenueGrowthYOY")),
        "earnings_growth": number(overview.get("QuarterlyEarningsGrowthYOY")),
        "observations": observations,
        "analyst_target_price": number(overview.get("AnalystTargetPrice"), 2),
        "week_52_high": number(overview.get("52WeekHigh"), 2),
        "week_52_low": number(overview.get("52WeekLow"), 2),
    }


def merge_snapshots(primary, fallback):
    if not fallback:
        return primary
    merged = dict(primary)
    for key, value in fallback.items():
        if merged.get(key) is None or merged.get(key) == "":
            merged[key] = value
    observations = {}
    for source in (primary.get("observations", {}), fallback.get("observations", {})):
        for metric_id, rows in source.items():
            observations.setdefault(metric_id, []).extend(rows)
    if observations:
        merged["observations"] = observations
    return merged


def compact_news(payload, symbol):
    """Keep only articles whose primary Alpha Vantage entity is unambiguous.

    NEWS_SENTIMENT may return an article because the requested company is mentioned
    incidentally. The highest-relevance entity is the article's ticker; requiring a
    strong primary score keeps broad market stories from being assigned arbitrarily.
    """
    items = []
    for row in payload.get("feed", [])[:12]:
        entities = []
        for entity in row.get("ticker_sentiment", []):
            try:
                relevance = float(entity.get("relevance_score"))
            except (TypeError, ValueError):
                continue
            ticker = str(entity.get("ticker") or "").strip().upper()
            if ticker:
                entities.append((relevance, ticker, entity))
        if not entities:
            continue
        relevance, primary_ticker, primary_entity = max(entities, key=lambda item: item[0])
        if relevance < MIN_ALPHA_PRIMARY_RELEVANCE:
            continue
        primary_entity = {**primary_entity, "ticker": primary_ticker}
        items.append(annotate_article({
            "title": row.get("title"), "url": row.get("url"), "source": row.get("source"),
            "published_at": row.get("time_published"), "summary": row.get("summary"),
            "overall_sentiment_score": number(row.get("overall_sentiment_score"), 3),
            "ticker_sentiment": [primary_entity],
            "ticker": primary_ticker,
        }, NEWS_CONFIG))
    return items


def latest_unique_news(items, limit=30):
    """Newest novel stories, preserving the primary ticker assigned by its adapter."""
    return deduplicate_articles(items, NEWS_CONFIG["title_similarity_threshold"])[:limit]


def fetch_discovery_news(client, symbols, limit=NEWS_DISCOVERY_LIMIT):
    """Fetch one broader company-news batch for strong candidates beyond the leaders."""
    if not client:
        return []
    selected = tuple(dict.fromkeys(symbols))[:limit]
    if not selected:
        return []
    payload = client.news(
        symbols=",".join(selected),
        filter_entities="true",
        language="en",
        group_similar="true",
        limit=limit,
    )
    return advisor_articles_for_symbols(payload, selected)


def curate_candidate_news(items, research_context, limit=70, discovery_slots=25):
    """Reserve room for broader candidates so leader coverage cannot crowd them out."""
    annotated = [
        {**item, **research_context.get(item.get("ticker"), {})}
        for item in latest_unique_news(items, limit=max(limit * 3, limit))
    ]
    leaders = [item for item in annotated if item.get("published_research")]
    discovery = [item for item in annotated if not item.get("published_research")]
    selected_discovery = discovery[:min(discovery_slots, limit)]
    selected_leaders = leaders[:limit - len(selected_discovery)]
    remaining = limit - len(selected_leaders) - len(selected_discovery)
    if remaining:
        selected_discovery.extend(discovery[len(selected_discovery):len(selected_discovery) + remaining])
    return [*selected_leaders, *selected_discovery]


def insider_summary(payload):
    buys = sells = 0
    for row in payload.get("data", [])[:100]:
        kind = str(row.get("acquisition_or_disposal", "")).upper()
        if kind == "A":
            buys += 1
        elif kind == "D":
            sells += 1
    return {"recent_acquisitions": buys, "recent_disposals": sells, "records_reviewed": min(100, len(payload.get("data", [])))}


def collect_insider_signals(sec, symbols, *, lookback_days=1100, cache=None):
    """Score Form 4 activity for a shortlist, before the final ranking rather than after.

    This used to run at the very end, purely as display, which meant the single
    best-supported unused signal in the dataset could not influence a single score. It now
    runs ahead of scoring so ``insider_modifier`` can act on it. Results are cached for a
    day - Form 4 filings are not intraday data - and the whole thing is skipped silently
    when ``SEC_USER_AGENT`` is unset, since SEC fair-access policy requires it.

    Returns ``(signals, failures, diagnostics)``. The diagnostics exist because "every
    symbol scored zero insider activity" has two very different causes - a quiet market and
    a layer that cannot read a single filing - and the published payload could not tell them
    apart. ``filings_reviewed`` versus ``filings_unreadable`` separates them.
    """
    empty_diagnostics = {"filings_reviewed": 0, "filings_unreadable": 0, "symbols_with_filings": 0}
    if not sec.available or not symbols:
        return {}, [], empty_diagnostics
    cache = cache or CACHE
    failures = []

    def collect_one(symbol):
        def produce():
            transactions, filings = sec.form4_transactions(symbol, lookback_days=lookback_days)
            return {
                "transactions": transactions,
                "filings_reviewed": len(filings),
                "filings_unreadable": sum(1 for filing in filings if not filing.get("parsed")),
            }
        try:
            # `v2` in the key retires entries cached by the build that fetched EDGAR's
            # XSL-rendered HTML and parsed nothing out of it; those cached empties would
            # otherwise keep the layer dark for a day after the fix.
            collected = cache.fetch("sec_submissions", f"form4:v2:{symbol}:{lookback_days}",
                                    produce, source="sec_edgar")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: SEC Form 4 unavailable ({type(exc).__name__})")
            return symbol, None, None
        return symbol, summarize_insiders(collected.get("transactions") or []), collected

    # SEC fair access allows 10 requests/second, so a small pool is safely inside the limit
    # while still overlapping the latency of dozens of filing downloads.
    results = parallel_map(collect_one, list(symbols), provider="sec_edgar", max_workers=4)
    signals = {}
    diagnostics = dict(empty_diagnostics)
    for entry in results:
        if not entry:
            continue
        symbol, summary, collected = entry
        if summary is None:
            failures.append(symbol)
            continue
        signals[symbol] = summary
        reviewed = collected.get("filings_reviewed", 0)
        diagnostics["filings_reviewed"] += reviewed
        diagnostics["filings_unreadable"] += collected.get("filings_unreadable", 0)
        diagnostics["symbols_with_filings"] += 1 if reviewed else 0
    return signals, failures, diagnostics


def collect_filing_risk_signals(sec, symbols, *, cache=None):
    """Customer-concentration and geographic-concentration risk from each symbol's latest 10-K.

    Reads the raw filing document through the identical ``("sec_submissions", "10k:{ticker}")``
    / ``("sec_document", url)`` cache keys ``theme_signals.EdgarThemeSignals`` uses for
    ``backlog_growth`` and ``filing_keyword_density_trend`` - see ``recent_10k_filings``'s
    docstring. Whichever of this collector or the theme layer runs first in a given refresh
    warms the cache for the other, so the two risk modifiers below cost no extra filing
    fetches beyond what the theme screen was already going to make.
    """
    empty_diagnostics = {"filings_reviewed": 0, "filings_unreadable": 0,
                         "concentration_tagged": 0, "geographic_tagged": 0}
    if not sec.available or not symbols:
        return {}, {}, empty_diagnostics
    cache = cache or CACHE

    def collect_one(symbol):
        try:
            filings = cache.fetch(
                "sec_submissions", f"10k:{symbol}",
                lambda: recent_10k_filings(sec, symbol), source="sec_edgar")
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"{symbol}: 10-K lookup failed ({type(exc).__name__})")
            return symbol, None, None, {"filings_reviewed": 0, "filings_unreadable": 0}
        if not filings:
            return symbol, None, None, {"filings_reviewed": 0, "filings_unreadable": 0}
        filing = filings[0]
        try:
            text = cache.fetch(
                "sec_document", filing["url"],
                lambda filing=filing: sec.filing_document(
                    filing["cik"], filing["accession"], filing["document"]),
                source="sec_edgar")
        except Exception:  # noqa: BLE001
            # The filing exists but could not be read. That is a measurement failure, not
            # evidence of diversified revenue, and must not be scored as either.
            return (symbol, summarize_concentration("", filing_read=False), None,
                    {"filings_reviewed": 1, "filings_unreadable": 1})
        return (symbol, summarize_concentration(text), summarize_geography(text),
                {"filings_reviewed": 1, "filings_unreadable": 0})

    results = parallel_map(collect_one, list(symbols), provider="sec_edgar", max_workers=4)
    concentration_signals, geographic_signals = {}, {}
    diagnostics = dict(empty_diagnostics)
    for entry in results:
        if not entry:
            continue
        symbol, concentration, geography, counted = entry
        diagnostics["filings_reviewed"] += counted.get("filings_reviewed", 0)
        diagnostics["filings_unreadable"] += counted.get("filings_unreadable", 0)
        if concentration is not None:
            concentration_signals[symbol] = concentration
            if concentration.get("available"):
                diagnostics["concentration_tagged"] += 1
        if geography is not None:
            geographic_signals[symbol] = geography
            if geography.get("available") and geography.get("shares"):
                diagnostics["geographic_tagged"] += 1
    return concentration_signals, geographic_signals, diagnostics


def collect_institutional_signals(symbols, *, as_of=None, screen_payload=None):
    """Fold the monthly-published institutional 13F screen into a lag-decayed score input.

    No live SEC/OpenFIGI calls here: ``build_institutional_screen.py`` runs on its own
    monthly schedule and is the source of record. This just reads what it last published
    (``public/data/screens/institutional-13f.json``) and computes how stale each ticker's
    underlying filing now is relative to ``as_of`` (defaults to today, the day this
    advisor refresh is actually running) - decay happens here, at read time, precisely so
    a screen that has not refreshed in three weeks scores less each day without needing a
    new fetch. ``undecayed_magnitude`` is the screen's raw breadth score at full weight;
    multiplying it by ``institutional_ownership.decay`` here reproduces exactly what
    ``institutional_ownership.score_institutional_ownership`` would have returned had it
    been called with today's ``days_since_filed`` directly.
    """
    payload = (screen_payload if screen_payload is not None
              else (load_json("screens/institutional-13f.json") or {}))
    diagnostics = {"requested": len(symbols), "screen_available": payload.get("status") == "success",
                   "screen_generated_at": payload.get("generated_at"), "tickers_matched": 0}
    if not diagnostics["screen_available"]:
        return {}, diagnostics
    as_of_date = as_of or date.today()
    universe = {str(symbol).upper() for symbol in symbols}
    cfg = SETTINGS.get("modifiers", {}).get("institutional_13f", {})
    signals = {}
    for row in payload.get("results") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in universe:
            continue
        magnitude, filed = row.get("undecayed_magnitude"), row.get("as_of")
        if magnitude is None or not filed:
            continue
        try:
            days_since_filed = (as_of_date - datetime.strptime(filed[:10], "%Y-%m-%d").date()).days
        except ValueError:
            continue
        freshness = institutional_decay(days_since_filed, cfg.get("half_life_days", 45),
                                        cfg.get("max_age_days", 135))
        points = round(magnitude * freshness, 2)
        if not points:
            continue
        diagnostics["tickers_matched"] += 1
        signals[ticker] = {
            "source": "SEC EDGAR Form 13F-HR (curated active managers, monthly screen)",
            "score_points": points,
            "days_since_filed": days_since_filed,
            "notes": [*(row.get("notes") or []), f"{days_since_filed}d since 13F filed"],
        }
    return signals, diagnostics


def collect_congressional_signals(symbols, *, as_of=None, screen_payload=None):
    """Fold the weekly-published congress screen into a reward-only score input.

    No live FMP calls here: ``build_congress_screen.py`` runs on its own weekly schedule
    and is the source of record. Reads ``public/data/screens/congress-trades.json``
    (already-classified rows carrying ``flags`` from ``build_congress_screen.classify``,
    including the ``EXTRAORDINARY_BUY`` tier) and scores each requested ticker with
    ``congress_signal.score_congressional_buying`` - see that module and
    ``advisor_engine.py``'s module docstring for why this is scored at all.
    """
    payload = (screen_payload if screen_payload is not None
              else (load_json("screens/congress-trades.json") or {}))
    results = payload.get("results") or []
    diagnostics = {"requested": len(symbols), "screen_available": bool(results),
                   "tickers_matched": 0}
    if not results:
        return {}, diagnostics
    as_of_date = as_of or date.today()
    cfg = SETTINGS.get("modifiers", {}).get("congressional_buying", {})
    by_ticker = {}
    for row in results:
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            by_ticker.setdefault(symbol, []).append(row)

    signals = {}
    for symbol in symbols:
        ticker = str(symbol).upper()
        rows = by_ticker.get(ticker)
        if not rows:
            continue
        points, detail = score_congressional_buying(rows, ticker, as_of=as_of_date, config=cfg)
        if not points:
            continue
        diagnostics["tickers_matched"] += 1
        signals[ticker] = {
            "source": "Congressional STOCK Act disclosures (weekly screen)",
            "score_points": points,
            "notes": detail.get("notes") or [],
        }
    return signals, diagnostics


def collect_filings_signals(symbols, *, screen_payload=None):
    """Fold the 3-day-published SEC filings screen (10-K/10-Q, DEF 14A, 8-K) into three
    already-scored, already-decayed score inputs.

    No live SEC calls here: ``build_filings_screen.py`` runs on its own 3-day schedule and
    is the source of record. Unlike the institutional 13F screen, decay is baked in at
    publish time rather than recomputed at read time - ``edgar_filing_signals.py``'s
    half-lives (30-45 days) are long enough relative to a 3-day publish cadence that the
    difference is immaterial, and it keeps this reader a plain lookup, matching how
    ``build_congress_screen.py``'s flags are read.
    """
    payload = (screen_payload if screen_payload is not None
              else (load_json("screens/filings.json") or {}))
    results = payload.get("results") or []
    diagnostics = {"requested": len(symbols), "screen_available": bool(results),
                   "screen_generated_at": payload.get("generated_at"), "tickers_matched": 0}
    if not results:
        return {}, {}, {}, diagnostics
    universe = {str(symbol).upper() for symbol in symbols}
    eightk, proxy, integrity = {}, {}, {}
    for row in results:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in universe:
            continue
        diagnostics["tickers_matched"] += 1
        if row.get("eightk_activity"):
            eightk[ticker] = row["eightk_activity"]
        if row.get("proxy_activity"):
            proxy[ticker] = row["proxy_activity"]
        if row.get("filing_integrity"):
            integrity[ticker] = row["filing_integrity"]
    return eightk, proxy, integrity, diagnostics


def fetch_optional(client, function, **params):
    try:
        return client.query(function, **params)
    except (AlphaVantageError, OSError, ValueError) as exc:
        LOG.warn(f"{function} unavailable: {exc}")
        return {}


def macro_context(client):
    specs = {
        "treasury_10y": ("TREASURY_YIELD", {"interval": "monthly", "maturity": "10year"}),
        "federal_funds_rate": ("FEDERAL_FUNDS_RATE", {"interval": "monthly"}),
        "inflation": ("INFLATION", {}),
    }
    result = {}
    for key, (function, params) in specs.items():
        payload = fetch_optional(client, function, **params)
        first = next((row for row in payload.get("data", []) if number(row.get("value")) is not None), None)
        result[key] = {"value": number(first.get("value")) if first else None,
                       "date": first.get("date") if first else None,
                       "unit": payload.get("unit")}
    return result


def collect(symbol, client, yf, alpha_symbols, delay, marketaux_client=None,
            news_diagnostics=None):
    """The cheap first pass: quote snapshot, two years of prices, and any Alpha Vantage extras.

    Financial statements are deliberately left out here. They cost several requests per
    company, so they are fetched later for shortlisted names only.
    """
    # Yahoo, like SEC EDGAR, writes share-class suffixes with a hyphen where this repo's own
    # universe config uses a dot (MOG.A here, MOG-A at Yahoo) - reuse edgar_entities'
    # normalization rather than requesting the dotted form and getting nothing back.
    ticker_obj = yf.Ticker(normalize_ticker(symbol)) if yf else None
    fallback = yahoo_snapshot(symbol, yf, ticker_obj)
    history = yahoo_history(symbol, yf, ticker_obj=ticker_obj)
    overview = daily = news_payload = insiders = {}
    # Yahoo's own per-symbol news, for every polled company rather than the five-symbol
    # Alpha shortlist. This is what gives the catalyst model a universe to work over: entity
    # sentiment covered 3 of 877 rows, so the model was complete and had nothing to score.
    # One cached request per symbol, and a dark feed degrades this company's news leg rather
    # than the run.
    news = fetch_company_news(symbol, ticker_obj, EVIDENCE_CONFIG, cache=CACHE,
                              diagnostics=news_diagnostics)
    marketaux_failed = False
    alpha_failed = False
    if symbol in alpha_symbols:
        overview = fetch_optional(client, "OVERVIEW", symbol=symbol)
        time.sleep(delay)
        daily = fetch_optional(client, "TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
        time.sleep(delay)
        # Provider-scored articles are merged ahead of the Yahoo baseline rather than
        # replacing it. They carry real entity sentiment, which outranks the headline lexicon
        # wherever the same story appears in both; clustering folds the duplicates together
        # and the provider reading wins the resulting event outright.
        provider_news = []
        if marketaux_client:
            try:
                marketaux_payload = marketaux_client.news(
                    symbols=symbol, filter_entities="true", language="en",
                    group_similar="true", limit=10,
                )
                provider_news = advisor_articles(marketaux_payload, symbol)
            except (MarketauxError, OSError, ValueError) as exc:
                marketaux_failed = True
                LOG.warn(f"{symbol}: Marketaux news unavailable ({type(exc).__name__}: {exc})")
        if not marketaux_client or marketaux_failed:
            news_payload = fetch_optional(client, "NEWS_SENTIMENT", tickers=symbol, sort="LATEST", limit="12")
            provider_news = compact_news(news_payload, symbol)
            time.sleep(delay)
        news = [*provider_news, *news]
        insiders = fetch_optional(client, "INSIDER_TRANSACTIONS", symbol=symbol)
        alpha_history = daily_history(daily)
        # Alpha Vantage only returns 100 sessions; Yahoo's two years wins whenever it exists.
        if alpha_history["closes"] and len(alpha_history["closes"]) > len(history["closes"]):
            history = alpha_history
        alpha_failed = not overview or not daily

    primary = overview_snapshot(symbol, overview, history["closes"]) if overview else {"ticker": symbol}
    snapshot = merge_snapshots(primary, fallback)
    # Fail loud before anything ranks on it. merge_snapshots takes the first non-null value
    # across providers with no arbitration, so this is also where a cross-provider
    # disagreement is visible for the last time -- see plausibility.screen.
    snapshot, plausibility_violations = screen_plausibility(snapshot, cross_source={
        "market_cap": {source: payload.get("market_cap")
                       for source, payload in (("alpha_vantage", primary), ("yahoo", fallback or {}))},
        "price": {source: payload.get("price")
                  for source, payload in (("alpha_vantage", primary), ("yahoo", fallback or {}))},
    })
    if plausibility_violations:
        LOG.warn(f"{symbol}: dropped {len(plausibility_violations)} implausible field(s): "
                 + ", ".join(f"{item['field']}={item['value']!r} ({item['rule']})"
                             for item in plausibility_violations))
    if not snapshot.get("name") or len(history["closes"]) < 21:
        raise ValueError("insufficient company snapshot or price history")
    closes = history["closes"]
    snapshot["pct_30d"] = round((closes[-1] / closes[-21] - 1) * 100, 2)
    return {
        "symbol": symbol, "snapshot": snapshot, "extended": {}, "ticker_obj": ticker_obj,
        "history": history, "news": news,
        "plausibility_violations": plausibility_violations,
        "insider_activity": insider_summary(insiders),
        "alpha_enriched": symbol in alpha_symbols and bool(overview),
        "alpha_failed": alpha_failed,
        "marketaux_enriched": symbol in alpha_symbols and bool(marketaux_client) and not marketaux_failed,
        "marketaux_failed": marketaux_failed,
    }


def enrich(contexts, limit, delay, priority=()):
    """Pull financial statements for the shortlist and fold the derived metrics into each snapshot.

    Shortlisting is done on core fundamentals alone, which every candidate has in equal
    measure, so nothing is ranked down merely for being outside the statement budget.

    Returns ``(enriched_count, diagnostics)``. ``enriched_count`` requires
    ``extended_coverage > 0`` (at least one statement metric actually resolved), not merely
    that ``yahoo_extended`` returned a non-empty dict -- ``derive_extended`` always returns
    every key, so an all-None dict from total data starvation used to count as "enriched".
    ``diagnostics`` breaks failures down by which Yahoo call failed, so a repeat of a
    universe-wide enrichment collapse is diagnosable from the published artifact instead of
    a single opaque zero.
    """
    ranked_by_score = sorted(contexts, key=lambda context: valuation_score(context["snapshot"])[0] or 0,
                             reverse=True)
    by_symbol = {context["symbol"]: context for context in contexts}
    ranked = [by_symbol[symbol] for symbol in priority if symbol in by_symbol]
    ranked.extend(context for context in ranked_by_score if context["symbol"] not in set(priority))
    diagnostics = {"attempted": 0, "info_fetch_failed": 0, "statement_fetch_failed": 0,
                   "derivation_failed": 0, "no_statement_data": 0,
                   "implausible_fields_dropped": 0}
    enriched = 0
    for context in ranked[:limit]:
        diagnostics["attempted"] += 1
        extended = yahoo_extended(context["symbol"], context["ticker_obj"],
                                  context["snapshot"], context["history"], diagnostics)
        if extended and extended.get("extended_coverage"):
            context["extended"] = extended
            # The derived values above carry no lineage on their own; without this, the v2
            # scoring layer treats them as legacy scalars with no canonical observation and
            # discards them (see scoring_v2.build_v2_analysis).
            observations = dict(context["snapshot"].get("observations") or {})
            for metric_id, rows in extended_observations(extended).items():
                observations.setdefault(metric_id, []).extend(rows)
            merged = {**context["snapshot"], **extended, "observations": observations}
            # Statement enrichment is where the derived ratios arrive -- ROIC, accruals and
            # incremental margin among them -- so it needs its own screening pass.
            merged, violations = screen_plausibility(merged)
            if violations:
                context["plausibility_violations"] = [*(context.get("plausibility_violations") or []),
                                                      *violations]
                diagnostics["implausible_fields_dropped"] += len(violations)
                LOG.warn(f"{context['symbol']}: dropped {len(violations)} implausible derived "
                         "field(s): " + ", ".join(f"{item['field']}={item['value']!r} "
                                                  f"({item['rule']})" for item in violations))
            context["snapshot"] = merged
            enriched += 1
        elif extended:
            diagnostics["no_statement_data"] += 1
        time.sleep(delay)
    LOG.info(f"Extended statement metrics derived for {enriched}/{min(limit, len(contexts))} shortlisted companies "
             f"(diagnostics: {diagnostics})")
    return enriched, diagnostics


def build_theme_layer(sec, rows):
    """Score the structural-trend screen, or explain why it could not run.

    Kept out of the score by design: a forward-looking thematic bet blended into the
    fundamentals score would make that score impossible to interpret. This emits an
    independent ``theme_screen`` block the UI renders beside the other screens.
    """
    if os.getenv("THEMES_DISABLE", "").lower() in {"1", "true", "yes"}:
        return empty_screen("disabled via THEMES_DISABLE")
    themes = load_themes()
    if not themes:
        return empty_screen("no active theme definitions in pipeline/themes/")
    provider = EdgarThemeSignals(sec)
    if not provider.available:
        return empty_screen("SEC_USER_AGENT is required by SEC fair-access policy; "
                            "theme signals come from EDGAR filings")
    screen = build_theme_screen(themes, rows, provider)
    LOG.info(f"Theme screen: {len(screen['themes'])} theme(s), "
             f"{sum(theme['count'] for theme in screen['themes'])} scored exposures")
    # The connectivity graph is pure arithmetic over what build_theme_screen just published -
    # no re-scoring, no new fetches. Computed even when a theme's own signals came back thin,
    # since a graph over N-1 working themes is still real; only a wholly empty screen skips it.
    if screen.get("themes"):
        screen["connectivity"] = build_connectivity(screen["themes"], screen.get("by_ticker") or {})
    # Candidate themes deliberately not scored (see pipeline/config/theme_watchlist.json for
    # why) - hand-maintained reference data, published verbatim so the frontend can note them as
    # "watching, not promoted" rather than silently absent.
    watchlist = load_json("theme_watchlist.json", from_config=True)
    if watchlist:
        screen["watchlist"] = watchlist.get("candidates") or []
    # Point-in-time capture for future rank-IC validation (Phase 5) - starts recording today,
    # never reconstructs history. See theme_pit_store.py and validation/theme_ic.py.
    try:
        price_by_ticker = {row.get("ticker"): row.get("price") for row in rows if row.get("ticker")}
        theme_pit_store.append_snapshot(screen, price_by_ticker)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"theme_pit_store snapshot failed ({type(exc).__name__}): {exc}")
    return screen


def previous_ranked_symbols(limit=INCUMBENT_ENRICH_LIMIT):
    """Return the prior published leaders so their deep coverage persists across refreshes."""
    payload = load_json("advisor.json") or {}
    return tuple(
        row["ticker"].upper()
        for row in payload.get("research", [])[:limit]
        if row.get("ticker")
    )


def previous_rows_by_ticker(payload):
    """Every row from the last run, published or screen-only, keyed by ticker.

    Insertion order follows score - ``research`` is the top ``publish_limit`` and
    ``screen_universe`` is the sorted remainder immediately below it - which is what lets
    ``previous_top_symbols`` slice this same dict for a threshold above ``publish_limit``.
    """
    rows = {}
    for row in (*payload.get("research", []), *payload.get("screen_universe", [])):
        ticker = (row.get("ticker") or "").upper()
        if ticker and ticker not in rows:
            rows[ticker] = row
    return rows


def previous_top_symbols(payload, limit):
    """Prior top-``limit`` tickers by score, spanning published research and the screen tail.

    ``previous_ranked_symbols`` only sees ``research`` (the published top ``publish_limit``,
    e.g. 40) - fine for its own callers, which ask for fewer than that. A fast refresh asks
    for more (e.g. 100), so it needs the screen-universe tail too or it silently gets fewer
    names than requested.
    """
    return tuple(previous_rows_by_ticker(payload).keys())[:limit]


def rank_publishable(research, publish_limit):
    """The top ``publish_limit`` rows eligible for the ranked leaderboard, and their tickers.

    ``research`` must already be sorted by ``score`` descending. A row failing
    ``publication_gate`` must never occupy a ranked slot regardless of its raw score -- the
    gate's own docstring promises "its champion score is not published as a ranked stance"
    (docs/AUDIT-ROUND-4-FINDINGS.md, Task 6) -- but slicing ``research[:publish_limit]``
    directly only ever changed the row's displayed ``stance`` label, never its ranking
    eligibility. A name with zero usable fundamentals (an all-momentum score, renormalized
    away from the unavailable fundamentals leg) could still out-rank names with real
    coverage and land an INSUFFICIENT DATA row inside the published top ``publish_limit`` --
    caught by validate_data.py's "ranked company lacks a fundamental score" check. Excluded
    rows are not deleted: the caller is expected to route every row not in the returned
    ticker set into ``screen_universe`` (by ticker membership, not a positional slice, since
    a gate-failing row can sit anywhere in the score order), so they keep their diagnostics
    and challenger scores exactly as the gate's docstring promises.
    """
    ranked = [row for row in research if row["publication_gate"]["published"]][:publish_limit]
    return ranked, {row["ticker"] for row in ranked}


def carry_forward_rows(research, symbols, previous_payload):
    """Previous-run rows for symbols a fast refresh didn't poll this cycle.

    Each carried row is flagged ``stale_carryforward`` so consumers (screens, the
    freshness report) can tell it apart from a symbol that was actually re-fetched. A
    symbol with no prior row simply has nothing to carry - it stays absent until the next
    full refresh, same as it would on a brand-new universe entry. The caller is responsible
    for only ever routing these into `screen_universe`, never the published `research` list
    - see `_screen_row`.
    """
    previous_rows = previous_rows_by_ticker(previous_payload)
    refreshed = {row["ticker"] for row in research}
    return [
        {**previous_rows[symbol], "stale_carryforward": True}
        for symbol in symbols
        if symbol not in refreshed and symbol in previous_rows
    ]


def rotation_slice(symbols, already_polling, previous_payload, size):
    """The stalest symbols outside this refresh's priority set, oldest poll first.

    A fast refresh polls the previous leaders plus the portfolio, which is a fixed set: a
    name that is not a prior leader is never re-fetched by a fast run, so it carries the
    same row forward indefinitely and quietly falls behind whatever fields later runs
    started publishing. That is not a display problem - it decides which names a screen can
    evaluate at all. The published dataset showed the result plainly: 756 of 837 screen rows
    had no 60-day drawdown, so the reversal screen could only ever see the 121 names polled
    that day, out of a 926-name universe.

    Rotating the oldest rows back in bounds that staleness: with the default sizes the whole
    universe is re-polled within a handful of fast refreshes, and a symbol that has never
    been polled at all sorts first because it has no timestamp to compare.
    """
    if size <= 0:
        return ()
    previous_rows = previous_rows_by_ticker(previous_payload)
    candidates = [symbol for symbol in symbols if symbol not in already_polling]
    candidates.sort(key=lambda symbol: (
        str((previous_rows.get(symbol) or {}).get("last_polled_at") or ""),
        symbol,
    ))
    return tuple(candidates[:size])


def enrichment_rotation(preliminary_symbols, already_selected, previous_payload, size):
    """The statement-starved names that have waited longest, oldest first -- theme-flagged
    names first among them.

    Statement-derived metrics -- ROIC, EV/EBITDA, Piotroski, Altman, accruals -- only ever
    existed for the previous run's top 20 plus five challengers, because that is who
    ``select_enrichment_priority`` sent to ``enrich``. A name outside that set could never
    acquire the metrics that would let it out-rank an incumbent, so the leaderboard could
    only ever rediscover what a weaker version of the model already liked. That is a
    self-reinforcing ranking bias, and no amount of scoring-methodology work touches it.

    This is the same fix ``rotation_slice`` applies to price polling, one layer up: a
    bounded slice of the never-enriched and longest-unenriched names joins every refresh,
    so the whole universe passes through statement enrichment over a predictable number of
    runs instead of never. A symbol that has never been enriched sorts first because it has
    no timestamp to compare.

    Within that never-enriched group, a name the theme screen already published as exposed
    (``theme_exposure`` non-empty last run -- this is how ``themes.expand_theme_candidates``'s
    sector-peer group surfaces) goes first. ``themes.explain_rank`` already discloses that
    most of that group is "ranked on a business-quality reading with no financial statements
    behind it"; this clears that backlog before the plain oldest-unenriched queue resumes, so
    a name a reader is already looking at on a theme screen gets real statement metrics sooner
    than one nothing has surfaced yet.

    The already-enriched tier is ranked strictly last regardless of where a symbol now sits
    in ``preliminary_symbols`` -- the sort key's first element is the tier, so a name that
    moved up in preliminary order after a past rotation gave it real fundamentals still loses
    a rotation slot to any name with none at all, exactly as if it hadn't moved.
    """
    if size <= 0:
        return ()
    previous_rows = previous_rows_by_ticker(previous_payload)
    candidates = [symbol for symbol in preliminary_symbols if symbol not in already_selected]
    def last_enriched(symbol):
        row = previous_rows.get(symbol) or {}
        if (row.get("fundamental_detail") or {}).get("raw_score"):
            # Already enriched: falls back to oldest-polled-first once the never-enriched
            # tiers below are exhausted.
            return (2, str(row.get("last_polled_at") or ""), symbol)
        # Never enriched. A name the theme screen already flagged as exposed jumps the rest
        # of this queue; everything else never-enriched follows in universe order.
        return (0 if row.get("theme_exposure") else 1, "", symbol)
    candidates.sort(key=last_enriched)
    return tuple(candidates[:size])


def _never_enriched_matching(preliminary_symbols, already_selected, previous_payload, size, admit_profile):
    """Never-enriched names whose classified profile satisfies ``admit_profile``, theme-flagged first.

    Shared by ``enrichment_expansion`` (non-financial/non-real-estate) and
    ``enrichment_expansion_financial_real_estate`` (the reverse set) -- same ordering as
    ``enrichment_rotation`` (never-enriched before already-enriched, theme-flagged jumping
    the queue), except this never falls back to already-enriched names once never-enriched
    candidates run out: both expansion queues exist to grow *new* usable coverage, not to
    re-touch names already covered, so they return fewer than ``size`` rather than admitting
    a mover a rotation-priority test elsewhere already relies on excluding (see
    ``test_select_enrichment_priority_also_skips_a_mover_already_enriched``).

    A candidate is only eligible if it has a previous row to classify at all -- a symbol
    never polled has an unknown profile and is left out of both targeted queues rather than
    guessed at; it can still be picked up by the untargeted ``enrichment_rotation`` slot.
    """
    if size <= 0:
        return ()
    previous_rows = previous_rows_by_ticker(previous_payload)
    def never_enriched_and_eligible(symbol):
        row = previous_rows.get(symbol)
        if row is None or (row.get("fundamental_detail") or {}).get("raw_score"):
            return None
        if not admit_profile(classify_profile(row)):
            return None
        return (0 if row.get("theme_exposure") else 1, "", symbol)
    candidates = [(symbol, key) for symbol in preliminary_symbols if symbol not in already_selected
                 for key in [never_enriched_and_eligible(symbol)] if key is not None]
    candidates.sort(key=lambda item: item[1])
    return tuple(symbol for symbol, _ in candidates[:size])


def enrichment_expansion(preliminary_symbols, already_selected, previous_payload, size,
                         excluded_profiles=EXCLUDED_EXPANSION_PROFILES):
    """Never-enriched, non-financial/non-real-estate names, theme-flagged first.

    Every name this admits is a name we already know isn't in a profile whose metric set is
    structurally different (Round 8: JPM's financial_health stayed null even fully enriched,
    a bank balance sheet not mapping to standard ratios, not a fetch failure) -- that is what
    keeps this expansion's yield directly "usable" the moment it lands. See
    ``enrichment_expansion_financial_real_estate`` for the deliberate, separately-sized
    counterpart that covers exactly the profiles this one skips.
    """
    return _never_enriched_matching(preliminary_symbols, already_selected, previous_payload, size,
                                    lambda profile: profile not in excluded_profiles)


def enrichment_expansion_financial_real_estate(preliminary_symbols, already_selected, previous_payload, size,
                                               included_profiles=EXCLUDED_EXPANSION_PROFILES):
    """Never-enriched bank/insurer/REIT names, theme-flagged first.

    ``enrichment_expansion`` deliberately skips these profiles because their metric set is
    structurally different, not because they don't matter -- a bank or REIT still deserves
    the same growth in statement coverage, just not folded into a queue sized and reasoned
    about in terms of the general fundamentals set. Sized independently
    (``ADVISOR_ENRICHMENT_EXPANSION_FINANCIAL_REAL_ESTATE_SIZE``) so financial/real-estate
    coverage grows on its own deliberate schedule rather than competing for slots against
    everything else, or being left to whatever the small, unfiltered ``enrichment_rotation``
    happens to reach. Defaults to roughly the full financial/real-estate population
    (~126 names: reit 50, bank 42, property_casualty_insurer 15, diversified_insurer 12,
    life_insurer 7, as classified in the committed universe), so it isn't a token gesture --
    the whole subclass can cycle through in a small number of refreshes.
    """
    return _never_enriched_matching(preliminary_symbols, already_selected, previous_payload, size,
                                    lambda profile: profile in included_profiles)


def select_enrichment_priority(previous_top, preliminary_symbols, available, portfolio_symbols=(),
                               full_universe_research=False, previous_payload=None,
                               rotation_size=ENRICHMENT_ROTATION_SIZE,
                               expansion_size=ENRICHMENT_EXPANSION_SIZE,
                               financial_real_estate_expansion_size=ENRICHMENT_EXPANSION_FINANCIAL_REAL_ESTATE_SIZE,
                               focus_symbols=()):
    """Prior leaders, the best outsiders, a rotation of statement-starved names, then holdings.

    ``focus_symbols`` (a re-ranking request for one named set) goes to the front of the queue.
    A refresh asked to re-rank specific companies that then gave their statement budget to
    yesterday's leaders would return the same ranking it was asked to revisit, since the
    metrics carrying most of the model's weight only exist for names that were enriched.

    ``full_universe_research=True`` is the A3 research-mode override: ``previous_top`` is
    ignored completely (not truncated, not consulted - the parameter is simply never read
    in this branch) and every preliminary candidate becomes a challenger, so the resulting
    priority ordering cannot depend on what a prior, weaker model happened to rank highly.

    Outside that override, the rotation slice is what stops the ordinary path from being
    a closed loop -- see ``enrichment_rotation``.
    """
    focused = tuple(symbol for symbol in focus_symbols if symbol in available)
    if full_universe_research:
        priority = tuple(dict.fromkeys((*focused, *preliminary_symbols, *portfolio_symbols)))
        return (), tuple(preliminary_symbols), priority
    incumbents = tuple(
        symbol for symbol in previous_top
        if symbol in available
    )[:INCUMBENT_ENRICH_LIMIT]
    if not incumbents:
        incumbents = tuple(preliminary_symbols[:INCUMBENT_ENRICH_LIMIT])
    incumbent_set = set(incumbents)
    challengers = tuple(
        symbol for symbol in preliminary_symbols
        if symbol not in incumbent_set
    )[:CHALLENGER_ENRICH_LIMIT]
    selected = incumbent_set | set(challengers) | set(portfolio_symbols) | set(focused)
    rotation = enrichment_rotation(preliminary_symbols, selected, previous_payload or {},
                                   rotation_size)
    expansion = enrichment_expansion(preliminary_symbols, selected | set(rotation),
                                     previous_payload or {}, expansion_size)
    financial_real_estate_expansion = enrichment_expansion_financial_real_estate(
        preliminary_symbols, selected | set(rotation) | set(expansion),
        previous_payload or {}, financial_real_estate_expansion_size)
    priority = tuple(dict.fromkeys(
        (*focused, *incumbents, *challengers, *rotation, *expansion,
         *financial_real_estate_expansion, *portfolio_symbols)))
    return incumbents, challengers, priority


def build_portfolio_coverage(research, portfolio_symbols, previous=()):
    """Keep configured holdings visible even when a quote provider drops a symbol."""
    research_by_ticker = {row["ticker"]: row for row in research}
    previous_by_ticker = {
        row.get("ticker", "").upper(): row
        for row in previous
        if row.get("ticker")
    }
    coverage = []
    for symbol in portfolio_symbols:
        if symbol in research_by_ticker:
            coverage.append(research_by_ticker[symbol])
        elif symbol in previous_by_ticker:
            coverage.append({
                **previous_by_ticker[symbol],
                "coverage_status": "stale_provider_unavailable",
            })
        else:
            coverage.append({
                "ticker": symbol,
                "name": symbol,
                "price": None,
                "coverage_status": "provider_unavailable",
            })
    return coverage


def attach_history(row, context, grid, benchmark_growth, previous_row=None):
    """Weekly series plus the equal-dollar comparison against the S&P 500.

    ``previous_row`` is this symbol's last published row. A batch download drops individual
    bars often enough that a symbol's session tape can come back with holes, or shorter than
    it was last run; unioning against what was already published keeps each symbol's history
    monotonic the same way the benchmark's is.
    """
    history = context["history"]
    previous_analytics = (previous_row or {}).get("analytics_history") or {}
    history = carry_forward_missing_sessions(
        previous_analytics.get("dates"),
        previous_analytics.get("closes"),
        history,
    )
    payload = series_payload(history["dates"], history["closes"], grid)
    if not payload:
        return
    row["history"] = {"dates": grid, **payload}
    analytics_history = analytics_series_payload(history["dates"], history["closes"])
    if analytics_history:
        row["analytics_history"] = analytics_history
    row["hypothetical"] = hypothetical_vs_benchmark(payload["growth"], benchmark_growth)


def run():
    load_local_env()
    previous_payload = load_json("advisor.json") or {}
    previous_coverage = previous_payload.get("portfolio_coverage", [])
    previous_portfolio = tuple(
        row.get("ticker", "")
        for row in previous_coverage
        if row.get("ticker")
    )
    configured = os.getenv("ADVISOR_SYMBOLS")
    requested_symbols = configured.split(",") if configured else DEFAULT_SYMBOLS
    symbols, portfolio_symbols = resolve_refresh_symbols(
        requested_symbols,
        PORTFOLIO_SYMBOLS,
        os.getenv("ADVISOR_PORTFOLIO_SYMBOLS", ""),
        previous_portfolio,
    )
    publish_limit = max(1, int(os.getenv("ADVISOR_PUBLISH_LIMIT", PUBLISH_LIMIT)))
    extended_limit = max(publish_limit, int(os.getenv("ADVISOR_EXTENDED_LIMIT", EXTENDED_LIMIT)))
    # Intraday refreshes don't need to re-poll all ~900 names - only the previously ranked
    # leaders move enough intraday to matter for the leaderboard. The full universe still
    # gets swept once a day (ADVISOR_UNIVERSE_MODE=full); everything left out of a fast
    # refresh carries its last full-refresh row forward rather than disappearing from the
    # published dataset (see the carry-forward merge below `research.sort`).
    universe_mode = os.getenv("ADVISOR_UNIVERSE_MODE", "full").strip().lower()
    # A focused refresh: re-poll and re-rank one named set of companies and nothing else.
    # The theme screen's re-run button sends its own members here, so a reader who wants the
    # thematic ranking refreshed does not have to pay for a 900-name sweep to get it.
    #
    # Deliberately NOT routed through ADVISOR_PORTFOLIO_SYMBOLS, which is the only existing
    # way to force a symbol into a refresh: that list means "the user owns this", and it
    # feeds portfolio coverage and tags theme rows as holdings. Re-ranking a screen would
    # have relabelled every name on it as something the user owns.
    focus_symbols = tuple(
        symbol for symbol in dict.fromkeys(
            part.strip().upper()
            for part in os.getenv("ADVISOR_FOCUS_SYMBOLS", "").split(",")
            if part.strip()
        )
        if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol) and symbol in set(symbols)
    )
    fast_universe_size = max(1, int(os.getenv("ADVISOR_FAST_UNIVERSE_SIZE", "100")))
    # Sized so a ~900-name universe is fully re-polled within roughly seven fast refreshes
    # rather than only when a full sweep happens to run.
    fast_rotation_size = max(0, int(os.getenv("ADVISOR_FAST_ROTATION_SIZE", "120")))
    alpha_enabled = os.getenv("ALPHA_DISABLE", "").lower() not in {"1", "true", "yes"}
    # 25 is Alpha Vantage's real free-tier daily cap, not an arbitrary code-side ceiling -
    # weekday runs default ALPHA_ENRICH_LIMIT to 5 (conservative, since the same quota also
    # has to last the day's other intraday refreshes), while the once-daily weekend run
    # can safely ask for the full 25 since nothing else on a non-trading day competes for it.
    # ALPHA_VANTAGE_CALL_DELAY must be raised alongside a higher limit to stay under the
    # 5-calls-per-minute sub-limit (12s/call minimum for 25/day) - the workflow sets both together.
    alpha_limit = max(0, min(25, int(os.getenv("ALPHA_ENRICH_LIMIT", "5")))) if alpha_enabled else 0
    previous_top = previous_ranked_symbols()
    requested_enrichment = tuple(s.strip().upper() for s in os.getenv("ALPHA_ENRICH_SYMBOLS", "").split(",") if s.strip())
    enrichment_order = requested_enrichment or previous_top or symbols
    eligible_enrichment = tuple(symbol for symbol in enrichment_order if symbol in symbols)
    alpha_symbols = set(eligible_enrichment[:alpha_limit])
    client = AlphaVantageClient() if alpha_enabled else None
    try:
        marketaux_client = MarketauxClient()
    except MarketauxError:
        marketaux_client = None
    delay = float(os.getenv("ALPHA_VANTAGE_CALL_DELAY", "0"))
    try:
        import yfinance as yf
    except ImportError:
        yf = None

    if focus_symbols:
        # Focus wins over the usual fast-refresh priorities rather than adding to them: the
        # point of the button is a short run over a named set, and folding in the prior top
        # 100 plus a rotation slice would quietly turn it back into an ordinary fast refresh.
        # Holdings stay in because portfolio coverage is published every run.
        refresh_symbols = tuple(
            symbol for symbol in symbols
            if symbol in set(focus_symbols) or symbol in set(portfolio_symbols)
        ) or symbols
        LOG.info(f"Focused refresh: polling {len(refresh_symbols)}/{len(symbols)} symbols "
                 f"({len(focus_symbols)} requested, plus holdings); every other name carries "
                 "its last published row forward")
    elif universe_mode == "fast":
        fast_priority = set(previous_top_symbols(previous_payload, fast_universe_size)) | set(portfolio_symbols)
        rotation = set(rotation_slice(symbols, fast_priority, previous_payload, fast_rotation_size))
        refresh_symbols = tuple(
            symbol for symbol in symbols if symbol in fast_priority or symbol in rotation
        ) or symbols
        LOG.info(f"Fast refresh: polling {len(refresh_symbols)}/{len(symbols)} symbols "
                 f"(prior top {fast_universe_size}, portfolio holdings, and the {len(rotation)} "
                 "stalest names in the tail); the rest carry forward until their turn")
    else:
        refresh_symbols = symbols

    benchmark_payload = (
        fetch_optional(client, "TIME_SERIES_DAILY", symbol="SPY", outputsize="compact")
        if client else {}
    )
    # One batched download for the whole universe before the per-symbol loop starts, so the
    # loop mostly reads cache instead of making a few hundred separate HTTP calls.
    prefetch_histories(("SPY", *refresh_symbols), yf)
    prefetch_snapshots(refresh_symbols, yf)
    benchmark = daily_history(benchmark_payload)
    yahoo_benchmark = yahoo_history("SPY", yf)
    if len(yahoo_benchmark["closes"]) > len(benchmark["closes"]):
        benchmark = yahoo_benchmark
    previous_benchmark_analytics = previous_payload.get("benchmark_analytics_history") or {}
    benchmark = carry_forward_missing_sessions(
        previous_benchmark_analytics.get("dates"),
        previous_benchmark_analytics.get("closes"),
        benchmark,
    )

    contexts, all_news = [], []
    alpha_failures, marketaux_failures, research_failures = [], [], []
    yahoo_news_diagnostics = new_news_diagnostics()
    for symbol in refresh_symbols:
        try:
            context = collect(symbol, client, yf, alpha_symbols, delay, marketaux_client,
                              news_diagnostics=yahoo_news_diagnostics)
            contexts.append(context)
            all_news.extend(context["news"])
            if context["alpha_failed"]:
                alpha_failures.append(symbol)
            if context["marketaux_failed"]:
                marketaux_failures.append(symbol)
            LOG.info(f"Advisor research collected for {symbol}")
        except Exception as exc:  # keep other symbols useful
            research_failures.append(symbol)
            LOG.error(f"{symbol}: advisor fetch failed ({type(exc).__name__}: {exc})")
        time.sleep(delay)

    if not contexts:
        update_pipeline_status("advisor", status="error", source="Alpha Vantage + Yahoo Finance",
                               message="No research records were produced")
        return None

    fred_regime = None
    fred_failure = None
    try:
        fred_regime = fetch_regime(FredClient())
        if fred_regime.get("failed_series"):
            fred_failure = f"Unavailable series: {', '.join(fred_regime['failed_series'])}"
    except FredError as exc:
        fred_failure = str(exc)
        LOG.warn(f"FRED macro regime unavailable ({exc})")

    # Establish the five closest challengers from the inexpensive first-pass score.
    # Then statements are pulled for those names and the prior top 20 before final scoring.
    preliminary_peer_diagnostics = canonical_percentiles([
        {**context["snapshot"], "ticker": context["symbol"],
         "categories": valuation_score(context["snapshot"])[1].get("categories", {})}
        for context in contexts
    ])
    preliminary = []
    for context in contexts:
        row = build_research(
            context["symbol"], context["snapshot"], context["history"]["closes"], benchmark["closes"],
            context["news"], volumes=context["history"]["volumes"], extended={},
            sector_percentile=(preliminary_peer_diagnostics.get(context["symbol"]) or {}).get("ordinal"),
            macro_regime=fred_regime,
        )
        preliminary.append(row)
    preliminary.sort(key=lambda row: row["score"], reverse=True)

    available = {context["symbol"] for context in contexts}
    preliminary_symbols = tuple(row["ticker"] for row in preliminary)
    discovery_limit = max(0, min(
        NEWS_DISCOVERY_LIMIT,
        int(os.getenv("ADVISOR_NEWS_DISCOVERY_LIMIT", str(NEWS_DISCOVERY_LIMIT))),
    ))
    try:
        discovery_news = fetch_discovery_news(
            marketaux_client, preliminary_symbols, discovery_limit
        )
    except (MarketauxError, OSError, ValueError) as exc:
        discovery_news = []
        LOG.warn(f"Broader candidate news unavailable ({type(exc).__name__}: {exc})")
    discovery_by_ticker = {}
    for item in discovery_news:
        discovery_by_ticker.setdefault(item["ticker"], []).append(item)
    for context in contexts:
        additions = discovery_by_ticker.get(context["symbol"], [])
        if additions:
            context["news"] = latest_unique_news([*context["news"], *additions], limit=12)
    all_news.extend(discovery_news)

    incumbents, challengers, statement_priority = select_enrichment_priority(
        previous_top, preliminary_symbols, available, portfolio_symbols,
        full_universe_research=FULL_UNIVERSE_RESEARCH,
        previous_payload=previous_payload,
        focus_symbols=focus_symbols,
    )
    effective_extended_limit = len(preliminary_symbols) if FULL_UNIVERSE_RESEARCH else extended_limit
    enriched_count, enrichment_diagnostics = enrich(contexts, effective_extended_limit, delay, statement_priority)

    challenger_cfg = (SETTINGS.get("challengers") or {}).get(
        "cross_sectional_normalization", {}
    )
    cross_normalizer = None
    normalization_fit_source = None
    if challenger_cfg.get("enabled"):
        if universe_mode == "full":
            cross_normalizer = CrossSectionalNormalizer(
                ({**context["snapshot"], "ticker": context["symbol"]} for context in contexts),
                challenger_cfg,
                pit_store.valuation_histories(
                    years=challenger_cfg["own_history_years"],
                    days_per_year=challenger_cfg["own_history_days_per_year"],
                    metrics=VALUATION_MULTIPLES,
                ),
            )
            normalization_fit_source = "current_full_refresh"
        else:
            cross_normalizer = CrossSectionalNormalizer.from_published(
                previous_payload.get("normalization_distributions"),
                pit_store.valuation_histories(
                    years=challenger_cfg["own_history_years"],
                    days_per_year=challenger_cfg["own_history_days_per_year"],
                    metrics=VALUATION_MULTIPLES,
                ),
            )
            if cross_normalizer:
                normalization_fit_source = "prior_full_refresh"
    signal_cfg = (SETTINGS.get("challengers") or {}).get("signal_corrections", {})
    short_interest_ranks = sector_percentile_ranks(
        ({**context["snapshot"], "ticker": context["symbol"]} for context in contexts),
        "short_percent_of_float",
        signal_cfg["short_interest_sector_minimum_count"],
    ) if signal_cfg.get("enabled") else {}

    # Valuation is scored once up front so 'cheap for its sector' can be measured against peers
    # before the final score is assembled.
    peer_diagnostics = canonical_percentiles([
        {**context["snapshot"], "ticker": context["symbol"],
         "categories": valuation_score(context["snapshot"])[1].get("categories", {})}
        for context in contexts
    ])

    # SEC Form 4 is the free source-of-record for genuine open-market insider trades. It is
    # collected here, ahead of scoring, so opportunistic cluster buying can actually move a
    # score - previously it was fetched after ranking and could only ever be displayed.
    sec = SecEdgarClient()
    sec_limit = max(0, int(os.getenv("SEC_FORM4_LIMIT", str(publish_limit))))
    insider_candidates = tuple(dict.fromkeys(
        (*preliminary_symbols[:sec_limit], *portfolio_symbols)
    )) if sec.available else ()
    insider_signals, sec_failures, sec_diagnostics = collect_insider_signals(sec, insider_candidates)
    if sec_diagnostics["filings_unreadable"]:
        LOG.warn(f"SEC Form 4: {sec_diagnostics['filings_unreadable']} of "
                 f"{sec_diagnostics['filings_reviewed']} filings could not be parsed")

    # Customer-concentration and geographic-concentration risk, from the same shortlist of
    # candidates and the same rate-limited SEC client - see collect_filing_risk_signals for
    # why this shares its cache keys with the theme layer's filing fetches. Customer
    # concentration feeds the champion score as of Phase 3.3; geographic exposure stays
    # challenger-only. See advisor_engine.apply_modifiers's docstring.
    concentration_signals, geographic_signals, filing_risk_diagnostics = (
        collect_filing_risk_signals(sec, insider_candidates)
    )

    # Operating-KPI text extraction (same-store sales, NIM, ARPU, ...) from 8-K earnings-
    # release exhibits. Off by default -- see settings.json's filing_extraction._comment and
    # pipeline/filing_extraction.py's module docstring for why this stays gated until a human
    # validates it against real filings. Every reading carries "unaudited": True and is
    # informational only, same reasoning as reverse_dcf and the new sector metrics.
    filing_extraction_cfg = SETTINGS.get("filing_extraction") or {}
    filing_extraction_signals, filing_extraction_diagnostics = {}, {
        "attempted": 0, "resolved_tickers": 0, "near_misses": {}}
    if filing_extraction_cfg.get("enabled"):
        snapshot_by_symbol = {context["symbol"]: context["snapshot"] for context in contexts}
        filing_extraction_signals, filing_extraction_diagnostics = collect_operating_kpi_signals(
            sec, insider_candidates,
            metrics_by_profile=filing_extraction_cfg.get("metrics_by_profile", {}),
            profile_for_ticker=lambda ticker: filing_extraction_group(snapshot_by_symbol.get(ticker, {})),
            limit_per_ticker=filing_extraction_cfg.get("limit_per_ticker", 4),
        )

    # Institutional 13F, decayed by filing lag - reads build_institutional_screen.py's
    # last monthly publish, no live SEC/OpenFIGI calls in this per-refresh path. Back in
    # the champion score (see advisor_engine.apply_modifiers); the sampling-bias caveat
    # (publicly traded, style=active managers only) is unchanged by the decay and is
    # documented on the modifier itself, not fixed by it.
    institutional_signals, institutional_diagnostics = collect_institutional_signals(insider_candidates)

    # Congressional buying, reward-only - reads build_congress_screen.py's last weekly
    # publish, no live FMP calls in this per-refresh path. This is advisor_engine.py's one
    # scoped exception to "no political inputs" - see that module's docstring and
    # congress_signal.py for what is and is not claimed.
    congressional_signals, congressional_diagnostics = collect_congressional_signals(insider_candidates)

    # 8-K materiality, contested-proxy, and late-10-K/10-Q signals - reads
    # build_filings_screen.py's last 3-day publish, no live SEC calls in this per-refresh
    # path. See advisor_engine.filing_8k_modifier/proxy_modifier/filing_integrity_modifier.
    eightk_signals, proxy_signals, filing_integrity_signals, filings_diagnostics = (
        collect_filings_signals(insider_candidates)
    )

    # Computed once per refresh, not per row: several of these providers (FRED regime, SEC
    # Form 4) are shared across every published company, so there is no per-ticker source
    # reliability signal to attach -- only a run-wide one.
    source_reliability_this_run = run_source_reliability({
        "yahoo_statement_enrichment": (
            "unavailable" if enrichment_diagnostics["attempted"] == 0 else
            "failed" if enriched_count == 0 else
            "degraded" if enriched_count < enrichment_diagnostics["attempted"] else
            "healthy"
        ),
        "sec_form4": ("unavailable" if not sec.available else
                     "degraded" if sec_failures else "healthy"),
        "sec_filing_risk": ("unavailable" if not sec.available else
                            "degraded" if filing_risk_diagnostics["filings_unreadable"] else
                            "healthy"),
        "institutional_13f_screen": ("unavailable" if not institutional_diagnostics["screen_available"]
                                     else "healthy"),
        "congress_screen": ("unavailable" if not congressional_diagnostics["screen_available"]
                            else "healthy"),
        "sec_filings_screen": ("unavailable" if not filings_diagnostics["screen_available"]
                               else "healthy"),
        "fred": "unavailable" if not fred_regime else ("degraded" if fred_failure else "healthy"),
    })

    # A descriptive peer-group median EV/EBITDA, computed from the fully enriched multiples
    # now that enrich() has populated context["extended"] for the shortlist -- unlike
    # peer_diagnostics above (computed earlier from the cheap preliminary snapshot alone,
    # because it feeds the sector_valuation modifier before enrichment runs), this needs the
    # deep enterprise multiple derive_enterprise_multiples only produces after statement
    # enrichment. Display-only: see peer_group_multiple_medians' own docstring for why this
    # publishes one group median rather than a per-company ranking against it.
    peer_multiple_medians = peer_group_multiple_medians([
        {**context["snapshot"], "ticker": context["symbol"],
         "ev_to_ebitda": (context.get("extended") or {}).get("ev_to_ebitda")}
        for context in contexts
    ])

    research = []
    polled_at = datetime.now(timezone.utc).isoformat()
    previous_rows = previous_rows_by_ticker(previous_payload)
    for context in contexts:
        symbol = context["symbol"]
        row = build_research(
            symbol, context["snapshot"], context["history"]["closes"], benchmark["closes"],
            context["news"], volumes=context["history"]["volumes"], extended=context["extended"],
            sector_percentile=(peer_diagnostics.get(context["symbol"]) or {}).get("ordinal"),
            macro_regime=fred_regime,
            insider_activity=insider_signals.get(symbol),
            institutional_ownership=institutional_signals.get(symbol),
            congressional_activity=congressional_signals.get(symbol),
            concentration_risk=concentration_signals.get(symbol),
            eightk_activity=eightk_signals.get(symbol),
            proxy_activity=proxy_signals.get(symbol),
            filing_integrity=filing_integrity_signals.get(symbol),
        )
        # The Form 4 record when we have one; the Alpha Vantage count as a display-only
        # fallback when we do not.
        row["insider_activity"] = insider_signals.get(symbol) or context["insider_activity"]
        row["institutional_ownership"] = institutional_signals.get(symbol)
        row["congressional_activity"] = congressional_signals.get(symbol)
        row["eightk_activity"] = eightk_signals.get(symbol)
        row["proxy_activity"] = proxy_signals.get(symbol)
        row["filing_integrity"] = filing_integrity_signals.get(symbol)
        # concentration_risk is now a champion-path input (Phase 3.3, see
        # advisor_engine.concentration_risk_modifier). geographic_exposure remains a display
        # field and a challenger-only input - see geographic_concentration_modifier.
        row["concentration_risk"] = concentration_signals.get(symbol)
        row["geographic_exposure"] = geographic_signals.get(symbol)
        # Display-only, unaudited, off by default -- see settings.json's filing_extraction
        # block. Never a champion-score input; not even a challenger one yet.
        row["filing_extracted_metrics"] = filing_extraction_signals.get(symbol)
        # Multiple-expansion decomposition (pipeline/return_attribution.py): how much of this
        # company's realized return over the window was re-rating vs. implied fundamental
        # delivery, computed purely from this ticker's own archived price/multiple history --
        # no new data, no network call, and None until pit_store has accumulated a long enough
        # baseline. Informational only, same reasoning as market_implied_growth above.
        return_attribution_multiple = ("price_to_ffo"
                                       if classify_profile(context["snapshot"]) == "reit"
                                       else "forward_pe")
        row["return_attribution"] = return_attribution.attribute_return_from_history(
            symbol, multiple_field=return_attribution_multiple,
            months_back=RETURN_ATTRIBUTION_MONTHS_BACK, pit_store=pit_store)
        # Expectation change - the leg the catalyst and analyst-conviction models were missing.
        # The previous run's consensus target is the only comparison point that exists for
        # target drift: Yahoo serves today's view and nothing else, which is precisely why
        # the snapshot archive has to be written from day one.
        estimate_detail = collect_estimate_detail(
            symbol, context.get("ticker_obj"),
            previous_target=(previous_rows.get(symbol) or {}).get("analyst_consensus_target"),
        )
        row["estimate_detail"] = estimate_detail
        # Lifted flat alongside analyst_rating/analyst_target_upside, which already live at
        # row level, so the point-in-time store archives them without having to learn about
        # nested blocks. The consensus target only fills a gap - it never overwrites a value
        # another source already resolved.
        for field in ("revision_breadth_30d", "eps_revision_30d_pct", "net_upgrades_90d"):
            if estimate_detail.get(field) is not None:
                row[field] = estimate_detail[field]
        if row.get("analyst_consensus_target") is None and estimate_detail.get("consensus_target") is not None:
            row["analyst_consensus_target"] = estimate_detail["consensus_target"]
        row["alpha_enriched"] = context["alpha_enriched"]
        # Every provider value this run refused to score, with the rule that refused it.
        row["data_quality_violations"] = context.get("plausibility_violations") or []
        row["valuation_percentile"] = peer_diagnostics.get(context["symbol"])
        row["peer_group_valuation_context"] = peer_multiple_medians.get(symbol)
        champion_variant = {
            "variant": "bands_champion",
            "normalization_mode": SETTINGS.get("normalization_mode", "bands"),
            "score": row["score"],
            "base_score": row["base_score"],
            "raw_score": row["raw_score"],
            "data_coverage": row["data_coverage"],
            "components": row["components"],
            "fundamental_categories": row["fundamental_categories"],
            "normalized_metric_scores": normalized_metric_scores(row["fundamental_detail"]),
        }
        row["score_variants"] = {"champion": champion_variant}
        if cross_normalizer and signal_cfg.get("enabled"):
            row["score_variants"].update(signal_correction_variants(
                row,
                context["snapshot"],
                cross_normalizer,
                signal_cfg,
                short_interest_ranks.get(symbol),
                fred_regime,
                insider_signals.get(symbol),
                concentration_signals.get(symbol),
                geographic_signals.get(symbol),
                institutional_signals.get(symbol),
                congressional_signals.get(symbol),
            ))
        elif cross_normalizer:
            row["score_variants"]["challenger"] = cross_sectional_challenger(
                row, context["snapshot"], cross_normalizer,
            )
        # Stamp the fetch time before the coverage decomposition reads it: it used to be
        # stamped only after this loop, so freshness_component saw no data_fetched_at and
        # published null -- with a false "freshness unavailable for this row" limitation --
        # for every freshly polled row.
        row.setdefault("data_fetched_at", polled_at)
        row["data_coverage_detail"] = data_coverage_components(
            row, source_reliability=source_reliability_this_run,
        )
        # Round 4 coverage floor: a name scored on too little of the intended metric
        # weight keeps its diagnostics and challengers, but its champion score is not
        # published as a ranked stance (docs/AUDIT-ROUND-4-FINDINGS.md, Task 6).
        publishable, gate_reason = publication_gate(
            (row.get("fundamental_detail") or {}).get("coverage"), SETTINGS)
        row["publication_gate"] = {"published": publishable, "reason": gate_reason}
        if not publishable:
            row["stance"] = "INSUFFICIENT DATA"
        # Every row in `research` was polled during this run by construction (carried-forward
        # rows join `screen_universe` later and keep their older stamp), so the poll time is
        # simply now. The next fast refresh reads it to decide what has waited longest.
        row["last_polled_at"] = polled_at
        # Dated evidence with per-event decay, published alongside the static component
        # scores rather than replacing them: the screens read the events, the long-term
        # score keeps reading the blended components it was calibrated on.
        row["evidence"] = build_evidence(row, context["news"], EVIDENCE_CONFIG)
        research.append(row)

    research.sort(key=lambda row: row["score"], reverse=True)

    # A layer that resolves to the same number for every company in the universe carries no
    # information and must not be published as evidence. This failed loudly is the difference
    # between catching the degenerate timeliness layer on its first run and shipping it for a
    # year -- see research/audit/CURRENT_MODEL_AUDIT.md section 3.
    assert_layers_vary(research, PUBLISHED_LAYERS)

    ranked, ranked_tickers = rank_publishable(research, publish_limit)

    # The trend-exposure layer runs as its own screen, deliberately outside the score. It
    # is scored on the published leaders, every configured holding, and a bounded set of
    # sector/peer-group neighbours of each theme's seed tickers - drawn only from names
    # already scored this run, so a name that isn't a top fundamentals score today (the
    # kind of name a sector-tailwind thesis is trying to catch before it re-rates) still
    # gets evaluated. See themes.expand_theme_candidates for the full rationale. This runs
    # before `screen_universe` is projected below so the lightweight rows it ships to the
    # browser carry `theme_exposure` too, not just the published leaderboard.
    theme_candidates = expand_theme_candidates(load_themes(), research, ranked, portfolio_symbols)
    theme_screen = build_theme_layer(sec, theme_candidates)
    theme_by_ticker = theme_screen.get("by_ticker") or {}
    for row in research:
        row["theme_exposure"] = theme_by_ticker.get(row["ticker"], [])

    # The momentum and 52-week-low screens rank on price behavior, not the fundamentals-led
    # composite score, so a strong screen candidate can rank outside the published leaderboard.
    # technical_detail and fundamental_categories are populated for the whole scored universe
    # (see technical_factors' closes-based 52-week fallback above), so publish a lightweight,
    # history-free slice of the rest of the universe for those screens to scan. Filtered by
    # ticker membership, not a `research[publish_limit:]` positional slice: `ranked` above
    # already skips publication-gate-failing rows regardless of their score-sorted position,
    # so a positional slice here would silently drop exactly those rows from both lists.
    screen_universe = [_screen_row(row) for row in research if row["ticker"] not in ranked_tickers]
    if universe_mode == "fast":
        # Carried-forward rows only ever join the lightweight screen tail, never the
        # published `research`/`ranked` list - a stale row is never promoted to "top pick"
        # on unverified data, and it lacks the fields (confidence, history, ...) the schema
        # requires of a published row anyway.
        carried = carry_forward_rows(research, symbols, previous_payload)
        screen_universe = sorted((*screen_universe, *(_screen_row(row) for row in carried)),
                                key=lambda row: row["score"], reverse=True)
        LOG.info(f"Fast refresh: carried {len(carried)} unpolled symbols forward as "
                 "screen-only rows")
    # Publish every configured holding explicitly. A provider can temporarily stop resolving
    # a symbol (for example, an expired structured product); omitting that row made the UI look
    # as if the user's holding itself had disappeared. A stale prior row is preferable, and a
    # price-less placeholder still lets the portfolio use its brokerage snapshot.
    portfolio_coverage = build_portfolio_coverage(
        research, portfolio_symbols, previous_coverage
    )
    research_context = {
        row["ticker"]: {
            "research_score": row["score"],
            "research_stance": row["stance"],
            "research_rank": index + 1,
            "published_research": index < publish_limit,
        }
        for index, row in enumerate(research)
    }
    published_news = curate_candidate_news(all_news, research_context)

    # Append this run's observations to the point-in-time store. It only becomes valuable
    # with time depth, so it starts accumulating now, well before any backtest needs it -
    # there is no way to reconstruct it retroactively from a provider that only serves today.
    # Rows carry the raw metric values merged from their snapshot, which is what a later
    # backtest needs - the derived 0-100 scores can always be recomputed from them.
    # `research` only ever holds freshly polled rows now - carried-forward rows join
    # `screen_universe` directly and never pass through here, so there is nothing to filter.
    # A SHA-256 of settings.json, not a bumped semantic version -- it changes on every
    # config edit whether or not anyone remembers to bump model_version, which is exactly
    # what "which formula version scored this row" needs from a PIT observation taken
    # months ago (see docs/BUILD-PLAN.md's B9 section: model_version/config_hash were
    # claimed as published per-row but were not, on either the row or the PIT store).
    config_hash = sha256_of_file(os.path.join(CONFIG_DIR, "settings.json"))
    pit_summary = pit_store.append_snapshot(research, source="advisor_refresh", config_hash=config_hash)
    # Point-in-time capture of the Fast Growth screens' raw inputs, for future rank-IC
    # validation - starts recording today, never reconstructs history. See
    # growth_pit_store.py and validation/growth_ic.py.
    try:
        growth_pit_store.append_snapshot(research)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"growth_pit_store snapshot failed ({type(exc).__name__}): {exc}")
    # Point-in-time capture of the Quality-value screen's quality composite inputs
    # (fundamental_categories, already published on every row above) - starts recording
    # today, never reconstructs history. See quality_pit_store.py and
    # validation/quality_ic.py.
    try:
        quality_pit_store.append_snapshot(research)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"quality_pit_store snapshot failed ({type(exc).__name__}): {exc}")
    # When a retired symbol was actually filtered out of this run's inputs, its departure
    # shows up in the universe store's added/removed diff - carry the documented reason
    # alongside it so `universe_churn` explains the removal instead of just recording it.
    retired_this_run = sorted(
        symbol for symbol in {*previous_portfolio, *requested_symbols}
        if str(symbol or "").strip().upper() in RETIRED_SYMBOLS
    )
    churn_note = "; ".join(
        f"{symbol} retired: {RETIRED_SYMBOLS[str(symbol).strip().upper()]}"
        for symbol in retired_this_run
    ) or None
    pit_store.record_universe(symbols, source="advisor_refresh", note=churn_note)
    pit_depth = pit_store.depth()

    grid = chart_grid(benchmark["dates"])
    benchmark_series = series_payload(benchmark["dates"], benchmark["closes"], grid)
    benchmark_growth = (benchmark_series or {}).get("growth")
    contexts_by_symbol = {context["symbol"]: context for context in contexts}
    previous_rows = previous_rows_by_ticker(previous_payload)
    for row in ranked:
        context = contexts_by_symbol.get(row["ticker"])
        if context:
            attach_history(row, context, grid, benchmark_growth, previous_rows.get(row["ticker"]))
    for row in portfolio_coverage:
        context = contexts_by_symbol.get(row["ticker"])
        if row["ticker"] not in ranked_tickers and context:
            attach_history(row, context, grid, benchmark_growth, previous_rows.get(row["ticker"]))

    market_status = fetch_optional(client, "MARKET_STATUS") if client else {}
    macro = macro_context(client) if client else {}
    generated_at = datetime.now(timezone.utc).isoformat()
    fundamentals_cfg = SETTINGS["fundamentals"]
    normalization_comparison = None
    if cross_normalizer:
        normalization_comparison = write_normalization_report(
            research,
            challenger_cfg["largest_movers_count"],
            challenger_cfg["sector_minimum_count"],
            generated_at,
        )
    signal_comparison = write_signal_report(research, generated_at) if signal_cfg.get("enabled") else None
    bias_check = write_bias_report(research, generated_at) if signal_cfg.get("enabled") else None
    for row in research:
        row.setdefault("data_fetched_at", generated_at)
    payload = {
        # Bumped to 2: market-behavior detail keys changed (12-1 momentum and real
        # risk-adjusted ratios replaced the invented trend/risk fields), and theme exposure
        # plus data-freshness blocks were added. All additive except the technical rename,
        # which the frontend migration in src/lib/schemaMigrations.js maps for v1 readers.
        "schema_version": SETTINGS["model"]["advisor_schema_version"],
        "model_version": SETTINGS["model"]["semantic_version"],
        "config_hash": config_hash,
        "generated_at": generated_at, "data_mode": "live",
        "count": len(ranked), "universe_count": len(symbols), "universe": list(symbols),
        "publish_limit": publish_limit, "statement_enriched_count": enriched_count, "benchmark": "SPY",
        "statement_health": statement_health(
            [row.get("fundamental_detail") or {} for row in research], SETTINGS),
        "price_archive_health": archive_health(),
        "universe_mode": universe_mode, "polled_count": len(refresh_symbols),
        "enrichment_selection": {
            "previous_top": list(incumbents),
            "challengers": list(challengers),
            "rotation_size": ENRICHMENT_ROTATION_SIZE,
            "expansion_size": ENRICHMENT_EXPANSION_SIZE,
            "expansion_excluded_profiles": sorted(EXCLUDED_EXPANSION_PROFILES),
            "financial_real_estate_expansion_size": ENRICHMENT_EXPANSION_FINANCIAL_REAL_ESTATE_SIZE,
            "financial_real_estate_expansion_profiles": sorted(EXCLUDED_EXPANSION_PROFILES),
            "priority_count": len(statement_priority),
            "note": "Statement enrichment previously covered only the prior run's top 20 "
                    "plus five challengers, so a name outside that set could never acquire "
                    "the metrics that would let it out-rank an incumbent. A rotation of "
                    "statement-starved names now joins every refresh, plus two dedicated "
                    "expansion queues sized independently: one for non-financial/non-real-"
                    "estate names, one for bank/insurer/REIT names -- so financial and real-"
                    "estate coverage grows on its own deliberate schedule instead of being "
                    "left to whatever the small, unfiltered rotation happens to reach.",
        },
        "enrichment_diagnostics": enrichment_diagnostics,
        "normalization_distributions": {
            **(cross_normalizer.published_distributions() if cross_normalizer else {}),
            "fit_source": normalization_fit_source,
        },
        "normalization_comparison": normalization_comparison,
        "bias_check": ({
            "comparable_universe_count": bias_check["comparable_universe_count"],
            "market_cap_correlation_drop_passed": bias_check["market_cap_correlation_absolute_drop"]["passed"],
        } if bias_check else None),
        "signal_comparison": signal_comparison,
        "methodology": {
            "weights": RANKING_WEIGHTS,
            "fundamental_weights": fundamentals_cfg["category_weights"],
            "metric_weights": fundamentals_cfg["metric_weights"],
            "market_behavior_weights": SETTINGS.get("market_behavior", {}).get("weights", {}),
            "modifiers": SETTINGS.get("modifiers", {}),
            "position_risk": SETTINGS.get("position_risk", {}),
            "portfolio_analytics": SETTINGS.get("portfolio_analytics", {}),
            "news_intelligence": SETTINGS.get("news_intelligence", {}),
            "principle": "Fundamentals lead. Price behavior and news modify confidence; they do not replace business quality.",
            "evidence": {
                "valuation": "EV/EBITDA and EV/EBIT carry the valuation bucket (Loughran & Wellman's "
                             "enterprise-multiple factor; Gray & Vogel's multiples comparison). PEG is a "
                             "minor sanity check because it ignores the time value of money, risk, and "
                             "cost of capital.",
                "profitability": "Gross profits-to-assets added per Novy-Marx (JFE 2013), which finds it "
                                 "roughly as predictive as book-to-market and complementary to it.",
                "accounting_quality": "Accruals down-weighted and Piotroski raised: the accruals anomaly "
                                      "has decayed in US data since 2002 while the F-score still validates.",
                "market_behavior": "12-1 momentum (Jegadeesh & Titman 1993) plus Sharpe/Sortino and a "
                                   "low-beta reward (Frazzini & Pedersen 2014), using the same functions "
                                   "as the ETF model.",
                "news_sentiment": "Weighted as a 4% tilt using recency decay, source quality, source-of-record "
                                  "filing labels, entity confidence, and title-level novelty.",
                "insider_activity": "Form 4 trades split routine vs opportunistic per Cohen, Malloy & "
                                    "Pomorski (JF 2012); only opportunistic cluster activity scores.",
                "caveat": "Published factor premia are historical in-sample estimates. They indicate which "
                          "signals have mattered, not what any of them will return next.",
            },
        },
        "market": {"status": market_status.get("markets", []), "macro": {**macro, "regime": fred_regime}},
        "benchmark_history": {"symbol": "SPY", "dates": grid, **(benchmark_series or {})},
        "benchmark_analytics_history": {
            "symbol": "SPY",
            **(analytics_series_payload(benchmark["dates"], benchmark["closes"]) or {}),
        },
        "hypothetical_basis": BASIS,
        "research": ranked,
        "screen_universe": screen_universe,
        "theme_screen": theme_screen,
        "portfolio_coverage": portfolio_coverage,
        "news": published_news,
        "data_freshness": pit_store.freshness_report(research),
        "point_in_time_store": {
            **pit_depth, "appended": pit_summary,
            "note": "Timestamped observations accumulate from each run so future backtests "
                    "can score on what was actually known at the time. Yahoo serves restated "
                    "fundamentals only, so this history cannot be rebuilt retroactively.",
        },
        "cache": CACHE.stats(),
        "capability_status": {
            "form4_insider_transactions": {
                "status": (
                    "configuration_required" if not sec.available else
                    "degraded" if sec_diagnostics["filings_unreadable"] else
                    "available"
                ),
                "source": "SEC EDGAR",
                "scored_symbols": len(insider_signals),
                "filings_reviewed": sec_diagnostics["filings_reviewed"],
                "filings_unreadable": sec_diagnostics["filings_unreadable"],
                "note": "Open-market purchase/sale codes only, split routine vs opportunistic "
                        "and scored as a bounded decaying modifier; set SEC_USER_AGENT.",
            },
            "implied_vs_realized_volatility": {
                "status": "available" if os.getenv("ENABLE_OPTIONS_VOLATILITY", "").lower() in {"1", "true", "yes"} else "opt_in",
                "source": "Yahoo option chains + calculated price returns",
                "note": "Set ENABLE_OPTIONS_VOLATILITY=1; options requests are intentionally opt-in.",
            },
            "filing_extracted_operating_kpis": {
                "status": "opt_in" if not filing_extraction_cfg.get("enabled") else (
                    "degraded" if filing_extraction_diagnostics["resolved_tickers"] == 0
                    else "available"
                ),
                "source": "SEC EDGAR 8-K Exhibit 99.x earnings releases (text/table extraction)",
                "filings_attempted": filing_extraction_diagnostics["attempted"],
                "tickers_resolved": filing_extraction_diagnostics["resolved_tickers"],
                # Diagnostic only, never a value: for a metric that resolved on 0 tickers this
                # run, a real filing line where its label matched but no value-shaped text
                # followed it closely enough. Distinguishes "this filer doesn't disclose it"
                # from "the pattern doesn't recognize how it's phrased" -- see
                # filing_extraction.near_miss_samples. Capped small per metric (the batch stops
                # collecting a metric's samples once it has enough), so this never grows with
                # universe size.
                "near_miss_samples": filing_extraction_diagnostics.get("near_misses", {}),
                "note": "Same-store sales, NIM, ARPU, and similar operating KPIs that are not "
                        "standardized XBRL facts (pipeline/filing_extraction.py). Off by default "
                        "(settings.json filing_extraction.enabled) and, even enabled, informational "
                        "only -- display field row.filing_extracted_metrics, no score input. Has "
                        "run against live SEC EDGAR fetches (first: 2026-08-28, refresh commit "
                        "0f911d94); resolution rate is still low (a handful of tickers out of the "
                        "whole universe). near_miss_samples above is the diagnostic for improving "
                        "that: real evidence lines for labels that matched without resolving a "
                        "value. Confirm settings.json's minimum_coverage is actually cleared per "
                        "metric before treating any reading here as reliable.",
            },
            "earnings_surprise_momentum": {
                "status": "available" if EARNINGS_SURPRISE_ENABLED else "opt_in",
                "source": "Yahoo earnings calendar (scraped, one request per symbol)",
                **EARNINGS_SURPRISE_STATS,
                "note": "Set ENABLE_EARNINGS_SURPRISE=1. Off by default: the first production "
                        "run resolved it for 0 of 40 published companies, so it spent a "
                        "request per symbol for nothing. Its growth-bucket weight stays in "
                        "config and reweights away while unavailable.",
            },
            "analyst_revision_trends": {"status": "provider_required", "note": "Point-in-time estimate history is not supplied by current providers."},
            "guidance_beat_miss_history": {"status": "provider_required", "note": "Needs normalized company guidance and contemporaneous consensus snapshots."},
            "backlog_growth": {
                "status": "available",
                "source": "SEC EDGAR XBRL (dimensional contexts read from the raw filing)",
                "note": "RevenueRemainingPerformanceObligation is XBRL-tagged, not free text - the "
                        "prior 'filing_parser_required' status was wrong. The blocker was that "
                        "company_concept/companyfacts return default (non-dimensional) facts only, "
                        "and filers routinely tag this concept solely in SatisfactionPeriodAxis "
                        "bands with no undimensioned total for those APIs to see. "
                        "pipeline.xbrl_dimensions reads contexts out of the filing document "
                        "directly instead, and EdgarThemeSignals.backlog_values sums the bands "
                        "when no total exists. Wired into ai_infrastructure.yaml. Per-symbol "
                        "coverage has not yet been measured on a live production run.",
            },
            "institutional_13f_changes": {
                "status": ("unavailable" if not institutional_diagnostics["screen_available"] else
                          "available"),
                "source": "SEC EDGAR Form 13F-HR (curated, publicly traded, style=active "
                         "managers, via pipeline/build_institutional_screen.py's monthly "
                         "publish) + OpenFIGI CUSIP mapping",
                "screen_generated_at": institutional_diagnostics["screen_generated_at"],
                "tickers_matched": institutional_diagnostics["tickers_matched"],
                "note": "Back in the champion score as a bounded, two-sided modifier "
                        "('institutional_13f'), decayed by filing lag rather than treated "
                        "as current - a 13F position is disclosed up to 45 days after "
                        "quarter-end, and this reads the monthly screen's own publish "
                        "date, not today, to compute that lag. Residual bias, not fixed "
                        "by decay: restricting to publicly traded managers oversamples "
                        "the largest passive indexers, mitigated (not eliminated) by "
                        "defaulting to style=active-only managers - see "
                        "pipeline/config/institutional_managers.json and "
                        "pipeline/institutional_ownership.py's module docstring. "
                        "Retroactive amendments (13F-HR/A) are handled explicitly: "
                        "build_institutional_screen.manager_quarters groups by the "
                        "period a filing covers rather than filing order, so an "
                        "amendment supersedes the original it revises instead of being "
                        "mistaken for a new quarter, and a value change is logged to "
                        "pipeline/data/institutional_13f/revisions.jsonl rather than "
                        "silently overwritten. Has never run against the live OpenFIGI "
                        "endpoint or live 13F filings (no network access existed while "
                        "this was written); verify CUSIP resolution rate and manager "
                        "coverage on the first real run.",
            },
            "congressional_buying": {
                "status": ("unavailable" if not congressional_diagnostics["screen_available"] else
                          "available"),
                "source": "STOCK Act disclosures via pipeline/build_congress_screen.py's "
                         "weekly publish (Financial Modeling Prep)",
                "tickers_matched": congressional_diagnostics["tickers_matched"],
                "note": "Explicit, scoped exception to advisor_engine.py's 'no political "
                        "inputs' principle - see that module's docstring. Reward-only "
                        "modifier ('congressional_buying'): breadth x freshness of "
                        "disclosed purchases, with a bonus for EXTRAORDINARY_BUY (a "
                        "member's first-ever trade in a sub-$2B company, "
                        "build_congress_screen.classify). A request to instead score "
                        "whether Congress 'wouldn't let a stock/sector fail' was raised "
                        "and declined - not implemented, see TODO.md. Evidentiary basis "
                        "(Ziobrowski et al., JFQA 2004) predates the STOCK Act's 2012 "
                        "disclosure regime; untested against the post-2012 world this "
                        "reads. Has never run against live FMP data or a live congress "
                        "screen publish (no network access existed while this was "
                        "written); verify EXTRAORDINARY_BUY hit rate on the first real run.",
            },
            "fx_exposure": {
                "status": "shadow_only",
                "source": "SEC EDGAR XBRL (Revenues x StatementGeographicalAxis)",
                "filings_reviewed": filing_risk_diagnostics["filings_reviewed"],
                "geographic_tag_coverage": (
                    round(filing_risk_diagnostics["geographic_tagged"] /
                         filing_risk_diagnostics["filings_reviewed"], 3)
                    if filing_risk_diagnostics["filings_reviewed"] else None
                ),
                "note": "Geographic revenue is XBRL-tagged, not free text - the prior "
                        "'filing_parser_required' status was wrong for the same reason "
                        "backlog_growth's was: company_concept/companyfacts return default "
                        "(non-dimensional) facts only. Scored as single-country revenue "
                        "concentration (pipeline/geographic_exposure.py) on the same "
                        "risk-not-direction principle as customer_concentration_risk below, but "
                        "kept out of the live score ('shadow_only', challenger score_variants "
                        "only): revenue tagged by geography often reflects shipping destination "
                        "or contracting entity rather than end demand (a contract manufacturer "
                        "can book enormous 'China' revenue that is really an assembly step), so "
                        "this needs spot-checking against real filings, and geographic_tag_"
                        "coverage above needs measuring, before it penalizes a live score.",
            },
            "customer_concentration_risk": {
                "status": "scored",
                "source": "SEC EDGAR XBRL (ConcentrationRiskPercentage1)",
                "filings_reviewed": filing_risk_diagnostics["filings_reviewed"],
                "filings_unreadable": filing_risk_diagnostics["filings_unreadable"],
                "concentration_tag_coverage": (
                    round(filing_risk_diagnostics["concentration_tagged"] /
                         filing_risk_diagnostics["filings_reviewed"], 3)
                    if filing_risk_diagnostics["filings_reviewed"] else None
                ),
                "note": "ASC 280 customer-concentration percentage read from dimensional XBRL "
                        "(pipeline/concentration_risk.py), scored as a penalty-only modifier in "
                        "the champion path as of Phase 3.3. The objection that kept it in shadow "
                        "mode - that a penalty-only modifier firing only on tagged filers favors "
                        "whichever companies never tagged the concept - is answered by separating "
                        "'filing read, nothing disclosed' from 'no filing read': ASC 280-10-50-42 "
                        "requires naming any customer at or above 10% of consolidated revenue, so "
                        "a read filing with no such tag is affirmative evidence of diversified "
                        "revenue, while an unreadable filing is scored nothing at all. Distinct "
                        "from the theme layer's "
                        "customer_concentration_to_spenders: the percentage gives magnitude, not "
                        "the customer's identity, so it cannot replace that signal's name-matching "
                        "against confirmed theme spenders.",
            },
        },
        "source_status": {
            "alpha_vantage": {"status": "disabled_for_intraday_refresh" if not client else
                              ("healthy" if not alpha_failures else "degraded"), "failed_symbols": alpha_failures,
                              "enriched_symbols": sorted(alpha_symbols),
                              "quota_strategy": f"up to {alpha_limit} symbol(s) this refresh (ALPHA_ENRICH_LIMIT, capped at Alpha Vantage's 25/day free-tier ceiling)"},
            "marketaux": {
                "status": "unavailable" if not marketaux_client else ("degraded" if marketaux_failures else "healthy"),
                "failed_symbols": marketaux_failures,
                "enriched_symbols": sorted(alpha_symbols) if marketaux_client else [],
                "note": "Set MARKETAUX_API_TOKEN to enable entity-level company news sentiment"
                        if not marketaux_client else "Entity-level sentiment for the Alpha-enriched shortlist",
            },
            "fred": {
                "status": "unavailable" if not fred_regime else ("degraded" if fred_failure else "healthy"),
                "failed_series": fred_regime.get("failed_series", []) if fred_regime else [],
                "note": fred_failure or "Six high-value series condensed into a bounded sector-sensitive regime modifier",
            },
            "yahoo_fundamentals": {"status": "degraded" if research_failures else ("healthy" if yf else "unavailable"),
                                   "failed_symbols": research_failures},
            "yahoo_statement_enrichment": {
                "status": (
                    "unavailable" if not yf else
                    "failed" if enrichment_diagnostics["attempted"] and not enriched_count else
                    "degraded" if enriched_count < enrichment_diagnostics["attempted"] else
                    "healthy"
                ),
                "attempted": enrichment_diagnostics["attempted"],
                "enriched": enriched_count,
                "info_fetch_failed": enrichment_diagnostics["info_fetch_failed"],
                "statement_fetch_failed": enrichment_diagnostics["statement_fetch_failed"],
                "derivation_failed": enrichment_diagnostics["derivation_failed"],
                "no_statement_data": enrichment_diagnostics["no_statement_data"],
                "note": "Distinct request from the cheap-pass price/snapshot fetch above. "
                        "income_stmt/balance_sheet/cashflow and .info are Yahoo's "
                        "quoteSummary-backed endpoints and fail independently of price data; "
                        "a company still enriches on statement frames alone if only .info fails.",
            },
            "yahoo_news": {
                # `unreadable` is the status that matters here. yfinance passes Yahoo's stream
                # items through untouched, so this pipeline parses an undocumented shape that
                # can change without warning; when it does, every item fails to normalize and
                # the catalyst model quietly loses its only universe-wide input. Publishing
                # received-versus-readable makes that a visible failure rather than a silent
                # one, the same lesson the Form 4 layer taught below.
                "status": (
                    "unavailable" if yahoo_news_diagnostics["symbols_requested"] == 0 else
                    "unreadable" if (yahoo_news_diagnostics["items_received"] > 0
                                     and yahoo_news_diagnostics["items_normalized"] == 0) else
                    "degraded" if (yahoo_news_diagnostics["feed_failures"]
                                   or yahoo_news_diagnostics["symbols_with_news"] == 0) else
                    "healthy"
                ),
                **yahoo_news_diagnostics,
                "note": "Per-symbol company news for the whole polled universe. Yahoo publishes "
                        "no sentiment score, so event direction is derived from the "
                        "evidence_events.headline_direction_markers phrase lexicon - a "
                        "deterministic keyword match, not a sentiment model. A headline that "
                        "matches no phrase is recorded as coverage and scores nothing.",
            },
            "sec_form4": {
                # Distinguish "we never asked" from "we asked and SEC EDGAR failed us" -
                # confidence.py excludes the former from source reliability (an unconfigured
                # feature is not evidence of anything) and counts the latter as a real
                # failure, same as any other provider outage.
                "status": (
                    "unavailable_not_configured" if not sec.available else
                    "unavailable_provider_error" if sec_failures and not insider_signals else
                    # Filings that download but cannot be parsed are a defect in this
                    # client, not a quiet insider market, and they must not be published as
                    # a healthy layer that simply found nothing.
                    "degraded" if sec_failures or sec_diagnostics["filings_unreadable"] else
                    "healthy"
                ),
                "failed_symbols": sec_failures,
                "scored_symbols": len(insider_signals),
                "filings_reviewed": sec_diagnostics["filings_reviewed"],
                "filings_unreadable": sec_diagnostics["filings_unreadable"],
                "symbols_with_filings": sec_diagnostics["symbols_with_filings"],
                "note": "Set SEC_USER_AGENT to enable free source-of-record insider transactions" if not sec.available else
                        "Open-market Form 4 codes P/S only; routine calendar trades score zero, "
                        "opportunistic cluster activity is a bounded decaying modifier",
            },
        },
        "disclaimer": "General research, not individualized investment advice. Verify filings, estimates, valuation context, and suitability before acting.",
    }
    validation_append = append_ic_refresh(
        ic_rows_from_advisor(payload),
        refresh_id=f"advisor-{generated_at}",
        recorded_at=generated_at,
        data_as_of=generated_at,
        universe=symbols,
        published=ranked_tickers,
        model_version=SETTINGS["model"]["semantic_version"],
        # So a dark provider's modifier is snapshotted as unavailable coverage rather than
        # as a neutral 0.0 that later validation would grade as real evidence.
        source_status=payload.get("source_status"),
    )
    score_history = build_score_history(read_snapshots())
    for row in research:
        attach_explainability(row, score_history.get(row["ticker"]))
    for row in portfolio_coverage:
        if not row.get("explainability"):
            attach_explainability(row, score_history.get(row.get("ticker")))
    reconciliation_failures = attribution_errors(research)
    if reconciliation_failures:
        raise ValueError(f"Score attribution failed to reconcile: {reconciliation_failures[:5]}")
    # score_history itself is not published standalone: nothing in the browser ever fetched
    # score-history.json (confirmed by grep — it was 31 MB of committed dead weight), and the
    # per-row explainability.score_history field attach_explainability() writes above is what
    # ScoreExplainability.jsx actually reads.
    if cross_normalizer:
        normalization_audit = write_normalization_audit(cross_normalizer, payload, generated_at)
        payload["normalization_audit"] = {
            "all_metrics_cross_sectional": normalization_audit["all_configured_metrics_have_cross_sectional_challenger"],
            "pit_file_count": normalization_audit["point_in_time_store"]["file_count"],
            "pit_row_count": normalization_audit["point_in_time_store"]["total_row_count"],
        }
    validation_report = write_ic_report()
    payload["validation_harness"] = {
        "snapshot": {key: value for key, value in validation_append.items() if key != "path"},
        "snapshot_refreshes": validation_report["snapshot_refreshes"],
        "champion_1m_status": validation_report["variants"]["champion"]["1M"]["status_message"],
        "challenger_1m_status": validation_report["variants"]["challenger"]["1M"]["status_message"],
    }
    payload["run_manifest"] = run_manifest(payload, {
        "provider_collection": len(research_failures),
        "statement_enrichment": max(0, len(contexts) - enriched_count),
        "publication_limit": max(0, len(research) - len(ranked)),
    })
    save_json("advisor.json", payload)
    save_json("report.json", report_snapshot(payload))
    save_json("diagnostics.json", diagnostics_payload(payload))
    all_failures = sorted(set(alpha_failures + marketaux_failures + research_failures))
    update_pipeline_status("advisor", status="healthy" if not all_failures else "degraded",
                           source="Alpha Vantage + Yahoo Finance + Marketaux",
                           details={"universe": len(symbols), "scored": len(research), "ranked": len(ranked), "failed": all_failures})
    LOG.info(f"Wrote advisor.json with the top {len(ranked)} of {len(research)} scored companies")
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
