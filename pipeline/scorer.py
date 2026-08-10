"""
scorer.py
Turn normalized trades + prices + news into a ranked signal list.

Two independent scores per ticker:
  political_score (0-100)  -- from the 6-factor weight table (settings.json)
  valuation_score (0-100)  -- broad fundamental score retained under the legacy field name

The ranker (rank_picks.py) blends these differently per bucket.
Also emits a cooling list: tickers with heavy congressional selling.

Output labels are research tiers, never 'BUY':
  HIGH CONVICTION / WATCH / NEUTRAL / COOLING
"""

from collections import defaultdict
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

from canonical_metrics import BUSINESS_PROFILES, classify_profile, required_for_score, suppressed_metrics
from common import (LOG, data_mode, load_json, save_json, days_between, today_iso,
                    normalize_name, update_pipeline_status)

SETTINGS = load_json("settings.json", from_config=True) or {}
COMMITTEES = (load_json("committees.json", from_config=True) or {}).get("politicians", {})


# ---------------- political factors ----------------

def score_track_record(politician, track_index, w):
    row = track_index.get(normalize_name(politician))
    if not row:
        return 0.0
    return round(w * (row["percentile"] / 100.0), 2)


def score_committee(politician, ticker, ticker_sector, w):
    cfg = COMMITTEES.get(normalize_name(politician))
    if not cfg or not ticker_sector:
        return 0.0
    return round(w, 2) if ticker_sector in cfg.get("sectors", []) else 0.0


def score_cluster(ticker, cluster_counts, w):
    cfg = SETTINGS["cluster"]
    n = cluster_counts.get(ticker, 0)
    if n >= cfg["min_politicians_for_max"]:
        return round(w, 2)
    if n == 2:
        return round(w * 0.5, 2)
    return 0.0


def score_size(amount_mid, w):
    b = SETTINGS["trade_size_bands"]
    if amount_mid >= b["high_min"]:
        return round(w, 2)
    if amount_mid >= b["mid_max"]:
        return round(w * 0.75, 2)
    if amount_mid > b["low_max"]:
        return round(w * 0.5, 2)
    if amount_mid > 0:
        return round(w * 0.25, 2)
    return 0.0


def score_direction_recency(trade, w):
    if trade.get("type") != "buy":
        return 0.0
    r = SETTINGS["recency"]
    lag = days_between(trade.get("filing_date"), today_iso())
    if lag is None:
        return round(w * 0.5, 2)
    if lag <= r["hot_filing_days"]:
        return round(w, 2)
    if lag <= r["warm_filing_days"]:
        return round(w * 0.66, 2)
    return round(w * 0.33, 2)


def score_policy(ticker, ticker_sector, flagged_sectors, flagged_tickers, w):
    if ticker in flagged_tickers:
        return round(w, 2)
    if ticker_sector and ticker_sector in flagged_sectors:
        return round(w * 0.7, 2)
    return 0.0


# ---------------- fundamental factor ----------------

def band_score(value, bands, lower_is_better=True):
    """Map a metric to 0-100 across ordered bands. Returns None if value missing."""
    if value is None:
        return None
    if value < 0:
        return 15.0  # negative earnings / odd data -> penalize, don't zero out
    keys = list(bands.keys())
    tiers = [100, 75, 50, 25]
    for i, k in enumerate(keys):
        if value <= bands[k]:
            return float(tiers[i]) if lower_is_better else float(tiers[len(keys) - 1 - i])
    return 10.0 if lower_is_better else 100.0


def higher_is_better_score(value, bands):
    """Score decimal ratios/growth where more is generally better."""
    if value is None:
        return None
    for key, score in (("excellent_min", 100), ("good_min", 80),
                       ("fair_min", 55), ("weak_min", 30)):
        if value >= bands[key]:
            return float(score)
    return 10.0


def lower_is_better_score(value, bands):
    """Score a metric where less is better and negative readings are genuinely good.

    Unlike band_score this never penalizes a negative value, so net cash (negative net
    debt) or a cash-backed negative accrual scores as the strength it actually is.
    """
    if value is None:
        return None
    for key, score in (("excellent_max", 100), ("good_max", 80),
                       ("fair_max", 55), ("poor_max", 30)):
        if value <= bands[key]:
            return float(score)
    return 10.0


def range_score(value, bands):
    """Score a metric where both extremes are bad - under-investment and empire-building alike."""
    if value is None:
        return None
    if bands["ideal_min"] <= value <= bands["ideal_max"]:
        return 100.0
    if bands["acceptable_min"] <= value <= bands["acceptable_max"]:
        return 65.0
    return 25.0


def multiple_score(value, bands):
    """Score a positive valuation multiple while flagging unusually low P/E as possible value-trap risk."""
    if value is None:
        return None
    if value <= 0:
        return 5.0
    if bands.get("suspicious_below") and value < bands["suspicious_below"]:
        return 60.0
    if value <= bands["cheap_max"]:
        return 100.0
    if value <= bands["healthy_max"]:
        return 80.0
    if value <= bands["elevated_max"]:
        return 45.0
    return 15.0


def weighted_available(scores, weights):
    available = [(scores[k], weights[k]) for k in weights if scores.get(k) is not None]
    if not available:
        return None
    return sum(score * weight for score, weight in available) / sum(weight for _, weight in available)


# Retired. Both of these were sector-string heuristics that decided applicability
# independently of pipeline/config/applicability_matrix.json, and they disagreed with it.
# FINANCIAL_EXEMPT forced price_to_book and debt_to_equity to null for every financial --
# the two canonical insurer inputs -- while leaving days_sales_outstanding_trend scored, and
# then removed the nulled metrics from the coverage *denominator*, so deleting the evidence
# raised measured coverage. THG published a Value score of 95.7 and 0.97 coverage with 13 of
# 33 metrics missing. Applicability now has exactly one authority, read by this path and the
# v2 path alike: canonical_metrics.suppressed_metrics / required_for_score. See
# research/audit/CURRENT_MODEL_AUDIT.md section 5.
#
# Price-to-tangible-book keeps a sector gate of its own because it is not an applicability
# question about the *business* but about whether tangible book carries economic meaning:
# for an asset-light software company it is close to an accounting accident. Profiles that
# name it a replacement metric (banks, insurers, REITs) always score it.
TANGIBLE_BOOK_SECTORS = ("Financial Services", "Financials", "Financial", "Real Estate",
                         "Utilities", "Energy", "Basic Materials", "Materials", "Industrials")

LOWER_IS_BETTER_METRICS = {
    "peg", "forward_pe", "sales_multiple", "price_to_book", "price_to_tangible_book",
    "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "debt_to_equity",
    "net_debt_to_ebitda", "stock_comp_to_revenue", "accruals_ratio",
    "days_sales_outstanding_trend", "inventory_days_trend",
}
VALUATION_MULTIPLES = {
    "peg", "forward_pe", "sales_multiple", "price_to_book", "price_to_tangible_book",
    "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf",
}
RANGE_METRICS = {"capex_to_depreciation", "asset_growth"}


def altman_score(value, variant, cfg):
    """Score an Altman Z against the bands for the variant it was computed under.

    Passing a Z'' through the original model's cutoffs (or the reverse) is the single
    easiest way to mislabel a healthy company as distressed, because the two models put
    their distress thresholds in different places on different scales.
    """
    bands = cfg.get("altman_z", {})
    if value is None or not variant:
        return None
    variant_bands = bands.get(variant)
    if not variant_bands:
        return None
    return higher_is_better_score(value, variant_bands)


def sales_multiple_score(snap, cfg):
    """Score sales valuation, preferring EV/Sales and falling back to P/S.

    EV/Sales is the better measure - it includes debt, so a levered company cannot look
    cheap simply by borrowing - but it needs the balance sheet, which only the enriched
    shortlist has. P/S comes free from the quote payload and covers everyone else.
    Returns ``(score, basis)`` so the output can say which input answered.
    """
    sector = snap.get("sector") or "default"
    enterprise = snap.get("ev_to_sales")
    if enterprise is not None:
        bands = cfg["ev_to_sales_by_sector"].get(sector, cfg["ev_to_sales_by_sector"]["default"])
        return multiple_score(enterprise, bands), "ev_to_sales"
    bands = cfg["price_to_sales_by_sector"].get(sector, cfg["price_to_sales_by_sector"]["default"])
    return multiple_score(snap.get("price_to_sales"), bands), "price_to_sales"


# Every metric the fundamentals model can score, in the order the category weights declare
# them. Suppression is a lookup against the applicability registry, never a literal in code.
SCORED_METRICS = (
    "peg", "forward_pe", "sales_multiple", "price_to_book", "price_to_tangible_book",
    "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "return_on_equity",
    "return_on_invested_capital", "gross_profits_to_assets", "cash_conversion",
    "free_cash_flow_yield", "profit_margin", "debt_to_equity", "current_ratio",
    "interest_coverage", "net_debt_to_ebitda", "altman_z", "revenue_growth",
    "earnings_growth", "fcf_growth_3y", "operating_margin_trend", "earnings_surprise",
    "net_buyback_yield", "stock_comp_to_revenue", "capex_to_depreciation", "asset_growth",
    "accruals_ratio", "piotroski_f", "days_sales_outstanding_trend", "inventory_days_trend",
)


def applicability(snap):
    """Business profile and the metrics suppressed for it, from the shared registry.

    Returns ``(profile, suppressed_set)``. ``suppressed`` means "this metric carries no
    meaning for this kind of business", which is different from "we could not obtain it":
    a suppressed metric leaves the coverage denominator, a missing one does not.
    """
    snap = snap or {}
    profile = classify_profile(snap)
    suppressed = set(suppressed_metrics(profile, SCORED_METRICS))
    # Tangible book is scored where the accounting measure has economic meaning: the sectors
    # below, plus any profile that names it a replacement metric for its own industry.
    profile_contract = (BUSINESS_PROFILES.get("profiles") or {}).get(profile, {})
    tangible_book_expected = ("price_to_tangible_book" in (profile_contract.get("replacement_metrics") or [])
                              or (snap.get("sector") or "default") in TANGIBLE_BOOK_SECTORS)
    if not tangible_book_expected:
        suppressed.add("price_to_tangible_book")
    return profile, suppressed


def raw_fundamental_metrics(snap):
    """Comparable raw inputs after applying the registry's applicability rules.

    This is the single raw-input contract shared by normalization fitting and scoring. What
    changed: suppression is now read from pipeline/config/applicability_matrix.json rather
    than from a hardcoded financial-sector tuple, so the live score and the v2 layer cannot
    disagree about what an insurer can be measured on. In particular price_to_book and
    debt_to_equity are no longer discarded for financials -- they are the canonical inputs
    for those profiles, and are declared required-for-score below.
    """
    snap = snap or {}
    sector = snap.get("sector") or "default"
    profile, suppressed = applicability(snap)
    sales_value = snap.get("ev_to_sales")
    sales_basis = "ev_to_sales"
    if sales_value is None:
        sales_value = snap.get("price_to_sales")
        sales_basis = "price_to_sales"
    raw = {metric: snap.get(metric) for metric in SCORED_METRICS}
    raw["sales_multiple"] = sales_value
    values = {metric: (None if metric in suppressed else value) for metric, value in raw.items()}
    return values, {"sales_multiple_basis": sales_basis, "sector": sector,
                    "applicability_profile": profile, "suppressed_metrics": sorted(suppressed)}


def _quantile(ordered, probability):
    """Linearly interpolated quantile used for deterministic winsorization."""
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _range_distance(metric, value, fundamentals):
    """Distance from a range metric's ideal band, where zero is ideal."""
    bands = fundamentals[metric]
    if bands["ideal_min"] <= value <= bands["ideal_max"]:
        return 0.0
    return min(abs(value - bands["ideal_min"]), abs(value - bands["ideal_max"]))


class CrossSectionalNormalizer:
    """Fit and reproduce winsorized cross-sectional fundamental metric percentiles.

    Every metric is winsorized against the full refreshed universe. Scoring then uses the
    sector distribution when it has enough observations, otherwise the universe
    distribution. Percentile ranks average ties and are flipped for lower-is-better inputs.
    Range inputs first become distance from their configured ideal band.
    """

    def __init__(self, snapshots, config=None, own_history=None):
        config = config or {}
        self.lower = float(config.get("winsor_lower_percentile", 0.01))
        self.upper = float(config.get("winsor_upper_percentile", 0.99))
        self.sector_minimum = int(config.get("sector_minimum_count", 8))
        self.own_history_years = int(config.get("own_history_years", 5))
        self.own_history_minimum = int(config.get("own_history_minimum_observations", 12))
        self.own_history = own_history or {}
        self.fundamentals = SETTINGS["fundamentals"]
        self.distributions = {}
        self._fit(list(snapshots or []))

    @classmethod
    def from_published(cls, payload, own_history=None):
        """Restore an exact prior full-refresh fit for an intraday partial refresh."""
        if not payload or payload.get("mode") != "cross_sectional" or not payload.get("metrics"):
            return None
        normalizer = cls.__new__(cls)
        first = next(iter(payload["metrics"].values()))
        normalizer.lower = first.get("winsor_lower_percentile", 0.01)
        normalizer.upper = first.get("winsor_upper_percentile", 0.99)
        normalizer.sector_minimum = payload.get("sector_minimum_count", 8)
        config = (SETTINGS.get("challengers") or {}).get("cross_sectional_normalization", {})
        normalizer.own_history_years = int(config.get("own_history_years", 5))
        normalizer.own_history_minimum = int(config.get("own_history_minimum_observations", 12))
        normalizer.own_history = own_history or {}
        normalizer.fundamentals = SETTINGS["fundamentals"]
        normalizer.distributions = payload["metrics"]
        return normalizer

    @staticmethod
    def _eligible(metric, value):
        if not isinstance(value, (int, float)):
            return False
        return not (metric in VALUATION_MULTIPLES and value <= 0)

    def _transform(self, metric, value):
        return _range_distance(metric, value, self.fundamentals) if metric in RANGE_METRICS else value

    def _fit(self, snapshots):
        collected = defaultdict(list)
        sectors = defaultdict(lambda: defaultdict(list))
        for snap in snapshots:
            values, metadata = raw_fundamental_metrics(snap)
            sector = metadata["sector"]
            for metric, raw in values.items():
                if not self._eligible(metric, raw):
                    continue
                transformed = float(self._transform(metric, raw))
                collected[metric].append(transformed)
                sectors[metric][sector].append(transformed)
        for metric, raw_values in collected.items():
            ordered = sorted(raw_values)
            lower_bound = _quantile(ordered, self.lower)
            upper_bound = _quantile(ordered, self.upper)

            def winsor(values):
                return sorted(max(lower_bound, min(upper_bound, value)) for value in values)

            universe = winsor(raw_values)
            sector_values = {sector: winsor(values) for sector, values in sectors[metric].items()}
            self.distributions[metric] = {
                "direction": "distance_from_ideal" if metric in RANGE_METRICS else
                             ("lower_is_better" if metric in LOWER_IS_BETTER_METRICS else "higher_is_better"),
                "winsor_lower_percentile": self.lower,
                "winsor_upper_percentile": self.upper,
                "winsor_lower_value": lower_bound,
                "winsor_upper_value": upper_bound,
                "universe_values": universe,
                "sector_values": sector_values,
            }

    def _own_history_detail(self, ticker, metric, value):
        if metric not in VALUATION_MULTIPLES:
            return {}
        series = ((self.own_history.get(str(ticker or "").upper()) or {}).get(metric) or [])
        values = sorted(float(row["value"] if isinstance(row, dict) else row) for row in series
                        if isinstance(row.get("value") if isinstance(row, dict) else row, (int, float))
                        and float(row.get("value") if isinstance(row, dict) else row) > 0)
        metadata = {
            "own_history_percentile": None,
            "own_history_observations": len(values),
            "own_history_years": self.own_history_years,
            "own_history_status": "accumulating",
        }
        if len(values) < self.own_history_minimum or not isinstance(value, (int, float)) or value <= 0:
            return metadata
        left = bisect_left(values, float(value))
        right = bisect_right(values, float(value))
        average_rank = (left + right - 1) / 2
        percentile = 50.0 if len(values) == 1 else 100 * average_rank / (len(values) - 1)
        return {
            **metadata,
            "own_history_percentile": round(max(0.0, min(100.0, percentile)), 1),
            "own_history_status": "scored",
        }

    def score(self, metric, value, sector, ticker=None):
        """Map one raw input to 0 through 100 and return its reproducibility metadata."""
        if value is None:
            return None, {"normalization_scope": "universe", "status": "missing",
                          **self._own_history_detail(ticker, metric, value)}
        if metric in VALUATION_MULTIPLES and value <= 0:
            return None, {"normalization_scope": "universe", "status": "not_applicable_nonpositive",
                          **self._own_history_detail(ticker, metric, value)}
        distribution = self.distributions.get(metric)
        if not distribution:
            return None, {"normalization_scope": "universe", "status": "insufficient_universe",
                          **self._own_history_detail(ticker, metric, value)}
        sector_values = distribution["sector_values"].get(sector, [])
        if len(sector_values) >= self.sector_minimum:
            values, scope = sector_values, "sector"
        else:
            values, scope = distribution["universe_values"], "universe"
        transformed = float(self._transform(metric, value))
        transformed = max(distribution["winsor_lower_value"],
                          min(distribution["winsor_upper_value"], transformed))
        if len(values) == 1:
            percentile = 50.0
        else:
            left = bisect_left(values, transformed)
            right = bisect_right(values, transformed)
            average_rank = (left + right - 1) / 2
            percentile = 100 * average_rank / (len(values) - 1)
        raw_percentile = percentile
        if metric in LOWER_IS_BETTER_METRICS or metric in RANGE_METRICS:
            percentile = 100 - percentile
        return round(percentile, 1), {
            "normalization_scope": scope,
            "status": "scored",
            "raw_value": value,
            "winsorized_value": transformed,
            "raw_percentile": round(raw_percentile, 1),
            "desirability_percentile": round(percentile, 1),
            "direction": distribution["direction"],
            "peer_count": len(values),
            **self._own_history_detail(ticker, metric, value),
        }

    def published_distributions(self):
        """Exact sorted distributions and fit parameters needed to reproduce this refresh."""
        return {
            "mode": "cross_sectional",
            "sector_minimum_count": self.sector_minimum,
            "metrics": self.distributions,
        }


def sector_percentile_ranks(snapshots, metric, minimum_count):
    """Ascending percentile rank by sector with a full-universe fallback.

    The returned scale is 0 through 1. Low values therefore identify the least-shorted
    names when ``metric`` is short interest. Ties share their average rank.
    """
    valid = [row for row in snapshots
             if row.get("ticker") and isinstance(row.get(metric), (int, float))]
    universe = sorted(float(row[metric]) for row in valid)
    sectors = defaultdict(list)
    for row in valid:
        sectors[row.get("sector") or "Unclassified"].append(float(row[metric]))
    sectors = {sector: sorted(values) for sector, values in sectors.items()}

    def percentile(values, value):
        if len(values) == 1:
            return 0.5
        left, right = bisect_left(values, value), bisect_right(values, value)
        return ((left + right - 1) / 2) / (len(values) - 1)

    result = {}
    for row in valid:
        sector_values = sectors.get(row.get("sector") or "Unclassified", [])
        values = sector_values if len(sector_values) >= minimum_count else universe
        result[row["ticker"]] = {
            "percentile": round(percentile(values, float(row[metric])), 6),
            "normalization_scope": "sector" if values is sector_values else "universe",
            "peer_count": len(values),
        }
    return result


def weighted_coverage(metrics, cfg, exempt=()):
    """Fraction of the total metric weight that was actually answered.

    Weight-aware so a missing minor input barely moves confidence while a missing
    headline input moves it a lot. Sector-exempt metrics leave the denominator entirely.
    """
    answered = total = 0.0
    for category, weights in cfg["metric_weights"].items():
        category_weight = cfg["category_weights"].get(category, 0)
        for metric, weight in weights.items():
            if metric in exempt:
                continue
            share = category_weight * weight
            total += share
            if metrics.get(metric) is not None:
                answered += share
    return answered / total if total else 0.0


def category_coverage(metrics, cfg, exempt=()):
    """Per-category share of applicable metric weight that resolved, with counts.

    ``weighted_available`` renormalizes silently, so a category score alone cannot say
    whether it came from the full evidence base or from two surviving metrics. Suppressed
    metrics are excluded from both sides, matching ``weighted_coverage``.
    """
    detail = {}
    for category, weights in cfg["metric_weights"].items():
        answered_weight = applicable_weight = 0.0
        used = applicable = 0
        for metric, weight in weights.items():
            if metric in exempt:
                continue
            applicable += 1
            applicable_weight += weight
            if metrics.get(metric) is not None:
                used += 1
                answered_weight += weight
        detail[category] = {
            "answered_weight_share": round(answered_weight / applicable_weight, 2) if applicable_weight else None,
            "metrics_used": used,
            "metrics_applicable": applicable,
        }
    return detail


def _categories_with_required_gate(metrics, cfg, profile):
    """Category scores, withholding any category missing a metric it is defined by.

    Renormalizing onto whatever resolved is the right treatment for a minor missing input
    and the wrong one for a defining input. An insurer's valuation without price-to-book is
    not a thin valuation reading; it is not a valuation reading. The published dataset had
    125 of 125 financial-sector rows carrying a Value score with price-to-book forced to
    null, THG's reading 95.7. Returns ``(categories, withheld)`` where ``withheld`` maps a
    null category to the required metrics that were absent, so the payload says why.
    """
    categories, withheld = {}, {}
    for category, weights in cfg["metric_weights"].items():
        missing_required = [metric for metric in required_for_score(profile, category)
                            if metric in weights and metrics.get(metric) is None]
        if missing_required:
            categories[category] = None
            withheld[category] = missing_required
            continue
        value = weighted_available(metrics, weights)
        categories[category] = round(value, 1) if value is not None else None
    return categories, withheld


def _band_valuation_score(snap):
    """Score valuation, profitability, solvency, growth, capital allocation, and accounting quality.

    ETFs remain unscored because corporate accounting ratios are not comparable to fund holdings.
    Missing values are reweighted, then the final score is confidence-adjusted for data coverage.
    """
    if not snap or snap.get("is_etf"):
        return None, {}
    cfg = SETTINGS["fundamentals"]
    sector = snap.get("sector") or "default"
    profile, suppressed = applicability(snap)
    pe_bands = cfg["forward_pe_by_sector"].get(sector, cfg["forward_pe_by_sector"]["default"])
    sales_score, sales_basis = sales_multiple_score(snap, cfg)
    altman_variant = snap.get("altman_z_variant")

    metrics = {
        # PEG survives as a minor growth-adjusted sanity check only. It ignores the time
        # value of money, risk, and cost of capital, and its support as a return predictor
        # is thin, so it no longer carries the largest weight in the bucket.
        "peg": band_score(snap.get("peg"), cfg["peg"]),
        "forward_pe": multiple_score(snap.get("forward_pe"), pe_bands),
        "sales_multiple": sales_score,
        # Goodwill makes reported book value meaningless for banks; tangible book replaces it there.
        "price_to_book": band_score(snap.get("price_to_book"), cfg["price_to_book"]),
        "price_to_tangible_book": band_score(snap.get("price_to_tangible_book"), cfg["price_to_tangible_book"]),
        "ev_to_ebitda": multiple_score(snap.get("ev_to_ebitda"), cfg["ev_to_ebitda"]),
        "ev_to_ebit": multiple_score(snap.get("ev_to_ebit"), cfg["ev_to_ebit"]),
        "ev_to_fcf": multiple_score(snap.get("ev_to_fcf"), cfg["ev_to_fcf"]),
        "return_on_equity": higher_is_better_score(snap.get("return_on_equity"), cfg["return_on_equity"]),
        # ROIC is the one ROE should have been: leverage cannot inflate it.
        "return_on_invested_capital": higher_is_better_score(snap.get("return_on_invested_capital"),
                                                             cfg["return_on_invested_capital"]),
        # Gross profits over assets - the cleanest profitability signal in the literature,
        # measured above the line where accounting discretion does its work.
        "gross_profits_to_assets": higher_is_better_score(
            snap.get("gross_profits_to_assets"), cfg["gross_profits_to_assets"]),
        "cash_conversion": higher_is_better_score(snap.get("cash_conversion"), cfg["cash_conversion"]),
        "free_cash_flow_yield": higher_is_better_score(snap.get("free_cash_flow_yield"), cfg["free_cash_flow_yield"]),
        "profit_margin": higher_is_better_score(snap.get("profit_margin"), cfg["profit_margin"]),
        # Bank balance sheets are structurally leveraged; these industrial-company cutoffs do not apply.
        "debt_to_equity": band_score(snap.get("debt_to_equity"), cfg["debt_to_equity"]),
        "current_ratio": higher_is_better_score(snap.get("current_ratio"), cfg["current_ratio"]),
        "interest_coverage": higher_is_better_score(snap.get("interest_coverage"), cfg["interest_coverage"]),
        "net_debt_to_ebitda": lower_is_better_score(snap.get("net_debt_to_ebitda"),
                                                    cfg["net_debt_to_ebitda"]),
        "altman_z": altman_score(snap.get("altman_z"), altman_variant, cfg),
        "revenue_growth": higher_is_better_score(snap.get("revenue_growth"), cfg["revenue_growth"]),
        "earnings_growth": higher_is_better_score(snap.get("earnings_growth"), cfg["earnings_growth"]),
        "fcf_growth_3y": higher_is_better_score(snap.get("fcf_growth_3y"), cfg["fcf_growth_3y"]),
        "operating_margin_trend": higher_is_better_score(snap.get("operating_margin_trend"),
                                                         cfg["operating_margin_trend"]),
        # Fundamental momentum: beating expectations, not merely growing.
        "earnings_surprise": higher_is_better_score(snap.get("earnings_surprise"), cfg["earnings_surprise"]),
        "net_buyback_yield": higher_is_better_score(snap.get("net_buyback_yield"), cfg["net_buyback_yield"]),
        "stock_comp_to_revenue": lower_is_better_score(snap.get("stock_comp_to_revenue"), cfg["stock_comp_to_revenue"]),
        "capex_to_depreciation": range_score(snap.get("capex_to_depreciation"), cfg["capex_to_depreciation"]),
        # The investment factor: aggressive balance-sheet expansion predicts weak returns,
        # and shrinking the asset base is not a virtue either, so both tails are penalized.
        "asset_growth": range_score(snap.get("asset_growth"), cfg["asset_growth"]),
        # Earnings that never become cash are a classic warning, but the anomaly has decayed
        # sharply in US data since 2002, so this is now a minor input rather than the bucket.
        "accruals_ratio": lower_is_better_score(snap.get("accruals_ratio"), cfg["accruals_ratio"]),
        "piotroski_f": higher_is_better_score(snap.get("piotroski_f"), cfg["piotroski_f"]),
        "days_sales_outstanding_trend": lower_is_better_score(snap.get("days_sales_outstanding_trend"),
                                                              cfg["days_sales_outstanding_trend"]),
        "inventory_days_trend": lower_is_better_score(snap.get("inventory_days_trend"), cfg["inventory_days_trend"]),
    }
    # A metric the registry suppresses for this profile is not scored and does not sit in
    # the coverage denominator. A metric that is merely absent stays in the denominator.
    metrics = {name: (None if name in suppressed else value) for name, value in metrics.items()}
    categories, blocked = _categories_with_required_gate(metrics, cfg, profile)
    raw = weighted_available(categories, cfg["category_weights"])
    coverage = weighted_coverage(metrics, cfg, tuple(suppressed))
    if raw is None:
        return None, {**metrics, "categories": categories, "coverage": round(coverage, 2),
                      "applicability_profile": profile, "suppressed_metrics": sorted(suppressed),
                      "categories_withheld": blocked}
    confidence_multiplier = 0.65 + (0.35 * coverage)
    total = round(raw * confidence_multiplier, 1)
    return total, {**metrics, "categories": categories, "coverage": round(coverage, 2),
                   "category_coverage": category_coverage(metrics, cfg, tuple(suppressed)),
                   "raw_score": round(raw, 1), "sector": sector,
                   "applicability_profile": profile,
                   "suppressed_metrics": sorted(suppressed),
                   "categories_withheld": blocked,
                   "sales_multiple_basis": sales_basis if sales_score is not None else None,
                   "altman_z_variant": altman_variant}


def _cross_sectional_valuation_score(snap, normalizer):
    """Score the unchanged category structure from cross-sectional metric percentiles."""
    if not snap or snap.get("is_etf"):
        return None, {}
    if normalizer is None:
        raise ValueError("cross_sectional mode requires a fitted CrossSectionalNormalizer")
    cfg = SETTINGS["fundamentals"]
    raw_metrics, raw_metadata = raw_fundamental_metrics(snap)
    sector = raw_metadata["sector"]
    metrics, normalization = {}, {}
    for metric, raw in raw_metrics.items():
        score, detail = normalizer.score(metric, raw, sector, snap.get("ticker"))
        metrics[metric] = score
        normalization[metric] = detail
    profile = raw_metadata["applicability_profile"]
    categories, blocked = _categories_with_required_gate(metrics, cfg, profile)
    raw = weighted_available(categories, cfg["category_weights"])
    exempt = set(raw_metadata["suppressed_metrics"])
    exempt.update(metric for metric in VALUATION_MULTIPLES
                  if isinstance(raw_metrics.get(metric), (int, float))
                  and raw_metrics[metric] <= 0)
    coverage = weighted_coverage(metrics, cfg, tuple(exempt))
    if raw is None:
        return None, {**metrics, "categories": categories, "coverage": round(coverage, 2),
                      "applicability_profile": profile, "categories_withheld": blocked,
                      "normalization": normalization, "normalization_mode": "cross_sectional"}
    confidence_multiplier = 0.65 + (0.35 * coverage)
    total = round(raw * confidence_multiplier, 1)
    scopes = {detail["normalization_scope"] for metric, detail in normalization.items()
              if metrics.get(metric) is not None}
    return total, {
        **metrics,
        "categories": categories,
        "coverage": round(coverage, 2),
        "category_coverage": category_coverage(metrics, cfg, tuple(exempt)),
        "raw_score": round(raw, 1),
        "sector": sector,
        "sales_multiple_basis": raw_metadata["sales_multiple_basis"],
        "altman_z_variant": snap.get("altman_z_variant"),
        "applicability_profile": profile,
        "suppressed_metrics": raw_metadata["suppressed_metrics"],
        "categories_withheld": blocked,
        "normalization_mode": "cross_sectional",
        "normalization_scope": "sector" if scopes == {"sector"} else "universe",
        "normalization": normalization,
    }


def valuation_score(snap, *, mode=None, normalizer=None):
    """Score fundamentals using the configured champion or an explicit challenger mode.

    ``bands`` preserves the production champion. ``cross_sectional`` requires a normalizer
    fitted once on the complete refresh universe so every row uses the same distributions.
    """
    selected = mode or SETTINGS.get("normalization_mode", "bands")
    if selected == "bands":
        score, detail = _band_valuation_score(snap)
        if detail:
            detail.setdefault("normalization_mode", "bands")
        return score, detail
    if selected == "cross_sectional":
        return _cross_sectional_valuation_score(snap, normalizer)
    raise ValueError(f"unsupported normalization mode: {selected}")


# ---------------- assembly ----------------

def ticker_sector_lookup(prices, policy):
    """Best-effort ticker -> policy sector (for committee + policy scoring)."""
    lut = {}
    for sector, cfg in policy.get("sectors", {}).items():
        for tk in cfg.get("tickers", []):
            lut.setdefault(tk, sector)
    return lut


def label_for(score):
    lb = SETTINGS["labels"]
    if score >= lb["high_conviction_min"]:
        return "HIGH CONVICTION"
    if score >= lb["watch_min"]:
        return "WATCH"
    if score >= lb["neutral_min"]:
        return "NEUTRAL"
    return "LOW"


def run():
    trade_payload = load_json("trades.json") or {}
    price_payload = load_json("prices.json") or {}
    trades = trade_payload.get("trades", [])
    prices = price_payload.get("prices", {})
    news = load_json("news.json") or {}
    track = (load_json("politicians.json") or {}).get("leaderboard", [])
    policy = load_json("policy_map.json", from_config=True) or {}

    track_index = {normalize_name(r["politician"]): r for r in track}
    sector_lut = ticker_sector_lookup(prices, policy)
    flagged_sectors = news.get("flagged_sectors", {})
    flagged_tickers = news.get("flagged_tickers", {})
    w = SETTINGS["signal_weights"]
    cluster_cfg = SETTINGS["cluster"]

    # cluster counts: distinct politicians buying same ticker within window
    buyers = defaultdict(set)
    sellers = defaultdict(set)
    for t in trades:
        lag = days_between(t.get("trade_date"), today_iso())
        if lag is None or lag > cluster_cfg["window_days"]:
            continue
        if t.get("type") == "buy":
            buyers[t["ticker"]].add(normalize_name(t["politician"]))
        elif t.get("type") == "sell":
            sellers[t["ticker"]].add(normalize_name(t["politician"]))
    cluster_counts = {tk: len(p) for tk, p in buyers.items()}

    # aggregate per ticker: take the strongest supporting buy
    best = {}
    for t in trades:
        if t.get("type") != "buy" or not t.get("ticker"):
            continue
        tk = t["ticker"]
        sec = sector_lut.get(tk)
        breakdown = {
            "track_record": score_track_record(t["politician"], track_index, w["track_record"]),
            "committee_relevance": score_committee(t["politician"], tk, sec, w["committee_relevance"]),
            "cluster_detection": score_cluster(tk, cluster_counts, w["cluster_detection"]),
            "trade_size": score_size(t.get("amount_mid", 0), w["trade_size"]),
            "direction_recency": score_direction_recency(t, w["direction_recency"]),
            "policy_catalyst": score_policy(tk, sec, flagged_sectors, flagged_tickers, w["policy_catalyst"]),
        }
        political = round(sum(breakdown.values()), 1)
        if tk not in best or political > best[tk]["political_score"]:
            snap = prices.get(tk, {})
            val_score, val_parts = valuation_score(snap)
            best[tk] = {
                "ticker": tk,
                "name": snap.get("name", tk),
                "sector": snap.get("sector") or sec,
                "is_etf": snap.get("is_etf", False),
                "political_score": political,
                "breakdown": breakdown,
                "cluster_size": cluster_counts.get(tk, 0),
                "top_buyer": t["politician"],
                "filing_lag_days": t.get("filing_lag_days"),
                "amount_range": t.get("amount_range"),
                # broad fundamentals (legacy valuation_score name kept for data compatibility)
                "valuation_score": val_score,
                "valuation_parts": val_parts,
                "fundamental_categories": val_parts.get("categories", {}),
                "fundamental_coverage": val_parts.get("coverage", 0.0),
                "peg": snap.get("peg"),
                "forward_pe": snap.get("forward_pe"),
                "price_to_sales": snap.get("price_to_sales"),
                "price_to_book": snap.get("price_to_book"),
                "return_on_equity": snap.get("return_on_equity"),
                "free_cash_flow": snap.get("free_cash_flow"),
                "free_cash_flow_yield": snap.get("free_cash_flow_yield"),
                "debt_to_equity": snap.get("debt_to_equity"),
                "current_ratio": snap.get("current_ratio"),
                "profit_margin": snap.get("profit_margin"),
                "revenue_growth": snap.get("revenue_growth"),
                "earnings_growth": snap.get("earnings_growth"),
                "pct_30d": snap.get("pct_30d"),
                "dividend_yield": snap.get("dividend_yield"),
                "market_cap": snap.get("market_cap"),
                "price": snap.get("price"),
                "label": label_for(political),
            }

    signals = sorted(best.values(), key=lambda x: x["political_score"], reverse=True)

    # cooling list: heavy selling clusters
    cooling = []
    for tk, pols in sellers.items():
        if len(pols) >= 2:
            snap = prices.get(tk, {})
            cooling.append({
                "ticker": tk,
                "name": snap.get("name", tk),
                "sellers": len(pols),
                "sector": snap.get("sector"),
                "pct_30d": snap.get("pct_30d"),
                "label": "COOLING",
            })
    cooling.sort(key=lambda x: x["sellers"], reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": data_mode(trade_payload, price_payload, news),
        "count": len(signals),
        "hot_sectors": flagged_sectors,
        "signals": signals,
        "cooling": cooling,
    }
    save_json("signals.json", payload)
    update_pipeline_status("scoring", status="healthy", source="local scoring engine",
                           details={"signals": len(signals), "cooling": len(cooling)})
    LOG.info(f"Wrote signals.json: {len(signals)} signals, {len(cooling)} cooling")
    return payload


if __name__ == "__main__":
    run()
