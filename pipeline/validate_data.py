"""Validate public JSON against versioned schemas and cross-file invariants."""

import argparse
import json
import os
import sys
from datetime import date
from jsonschema import Draft202012Validator, FormatChecker

from common import DATA_DIR

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
FILES = ("trades", "prices", "news", "politicians", "signals", "picks", "status", "advisor", "etfs")
CONGRESS_TRADES_SCHEMA = os.path.join(SCHEMA_DIR, "congress-trades.schema.json")


def load(path):
    with open(path) as handle:
        return json.load(handle)


def theme_screen_errors(screen):
    """Enforce the anti-hype guardrails as a published contract, not just a code comment.

    The failure mode for a thematic screen is that it quietly becomes a momentum screen -
    exactly the pattern behind specialized ETFs losing about 30% risk-adjusted over five
    years. Two things make that impossible to ship by accident: price momentum must carry
    zero weight, and every published row must declare whether it cleared the guardrails.

    The theme *trend* block reads price deliberately - it answers whether a trend is moving
    and whether it is already paid for - so the separation between the two questions is
    enforced here rather than left to whoever edits ``themes.py`` next: a trend block must
    declare that it does not feed exposure, and an exposure row must not carry price behavior
    at all. A row that arrived with a technical block would be one careless spread away from
    a score that reads it.
    """
    price_fields = ("technical_detail", "history", "relative_strength", "momentum_12_1",
                    "return_20d", "return_60d")
    if not screen or not screen.get("themes"):
        return []
    errors = []
    for theme in screen["themes"]:
        theme_id = theme.get("id", "?")
        guardrails = theme.get("guardrails") or {}
        if guardrails.get("max_price_momentum_contribution", 0) != 0:
            errors.append(f"advisor.json:theme_screen.{theme_id}: price momentum must "
                          "contribute zero to theme exposure")
        for signal in theme.get("signals") or []:
            if signal.get("name") in ("price_momentum", "return_12m", "return_1m",
                                      "distance_from_52w_high", "social_mentions"):
                errors.append(f"advisor.json:theme_screen.{theme_id}: lagging signal "
                              f"'{signal['name']}' cannot contribute to theme exposure")
        for index, row in enumerate(theme.get("rows") or []):
            if row.get("eligible") is None:
                errors.append(f"advisor.json:theme_screen.{theme_id}.rows.{index}: "
                              "every row must declare whether it cleared the guardrails")
            score = row.get("theme_exposure_score")
            if score is not None and not 0 <= score <= 100:
                errors.append(f"advisor.json:theme_screen.{theme_id}.rows.{index}: "
                              f"exposure score {score} is outside 0-100")
            leaked = [field for field in price_fields if field in row]
            if leaked:
                errors.append(f"advisor.json:theme_screen.{theme_id}.rows.{index}: exposure "
                              f"rows must not carry price behavior ({', '.join(leaked)})")
        trend = theme.get("trend")
        if trend is not None and trend.get("contributes_to_exposure") is not False:
            errors.append(f"advisor.json:theme_screen.{theme_id}.trend: the trend block reads "
                          "price and must declare contributes_to_exposure: false")
    return errors


def enrichment_coverage_errors(advisor):
    """A full sweep that attempts statement enrichment and enriches zero companies means
    Yahoo's statement endpoints are broken universe-wide (this happened on 2026-08-06: .info
    raised for every symbol and discarded already-fetched statement frames along with it,
    collapsing fundamental coverage to ~0.3 and confidence to ~0.4 across the board). That
    must block publication rather than ship a silently degraded dataset -- see
    docs/BASELINE-2026-08-06.md.
    """
    if not advisor:
        return []
    diagnostics = advisor.get("enrichment_diagnostics") or {}
    attempted = diagnostics.get("attempted", 0)
    enriched = advisor.get("statement_enriched_count", 0)
    if advisor.get("universe_mode") != "full" or not attempted or enriched:
        return []
    return [
        "advisor.json: statement_enriched_count is 0 on a full sweep despite "
        f"{attempted} enrichment attempts (info_fetch_failed="
        f"{diagnostics.get('info_fetch_failed', 'unknown')}, "
        f"statement_fetch_failed={diagnostics.get('statement_fetch_failed', 'unknown')}, "
        f"derivation_failed={diagnostics.get('derivation_failed', 'unknown')}, "
        f"no_statement_data={diagnostics.get('no_statement_data', 'unknown')}) -- "
        "Yahoo statement enrichment appears broken universe-wide; investigate before publishing"
    ]


def etf_peer_group_errors(payload):
    """A fund's rank is only meaningful inside its peer group; make that explicit."""
    rows = payload.get("etfs") or []
    if not rows or payload.get("schema_version", 2) < 3:
        return []
    errors = []
    for index, row in enumerate(rows):
        if not row.get("ranked_against"):
            errors.append(f"etfs.json:etfs.{index}: missing the peer group the fund was ranked in")
        if row.get("ranked_against") == "_pooled" and not row.get("cross_asset_class_rank"):
            errors.append(f"etfs.json:etfs.{index}: pooled ranking must be flagged as "
                          "cross-asset-class so it is not read as a like-for-like comparison")
        if payload.get("schema_version", 0) >= 4:
            available = bool(row.get("sector_weights"))
            if row.get("sector_lookthrough_available") is not available:
                errors.append(f"etfs.json:etfs.{index}: sector look-through flag does not match sector weights")
    groups = {row.get("ranked_against") for row in rows}
    if len(groups) == 1 and len(rows) > 10:
        errors.append("etfs.json: every fund landed in one peer group, so the whole batch is "
                      "being cross-ranked again")
    return errors


# Every context-only field the swing screen's extended context layer publishes - see
# pipeline/swing_signals.py's CONTEXT_SIGNAL_EVIDENCE/CONTEXT_NOTE and
# pipeline/market_regime.py's MARKET_REGIME_EVIDENCE. None of these may ever appear as a
# declared weight or among a row's scored legs - this is the structural check for that
# promise, mirroring theme_screen_errors's anti-hype guardrail pattern for a different screen.
SWING_CONTEXT_ONLY_FIELDS = {
    "bandwidth_squeeze", "volume_dry_up", "rsi_2", "narrow_range", "atr_compression", "vcp",
    "chaikin_money_flow", "weinstein_stage2", "sector_relative_strength",
    "above_50dma_pct", "above_200dma_pct", "hurst", "regime_gate",
}


def swing_context_signal_errors():
    """Context signals published on ``screens/swing.json`` must never enter a scored leg.

    A missing file is not reported here, matching congress_trades_schema_errors: this screen
    legitimately does not exist yet in a fresh checkout or an environment that has never run
    build_swing_screen.py.
    """
    data_path = os.path.join(DATA_DIR, "screens", "swing.json")
    if not os.path.exists(data_path):
        return []
    swing = load(data_path)
    errors = []
    if SWING_CONTEXT_ONLY_FIELDS & set(swing.get("weights") or {}):
        errors.append("screens/swing.json: a context-only signal appears in the top-level "
                      "declared weights")
    for index, row in enumerate(swing.get("results") or []):
        if SWING_CONTEXT_ONLY_FIELDS & set(row.get("legs") or {}):
            errors.append(f"screens/swing.json:results.{index}: a context-only signal "
                          "appears among the scored legs")
    for tier_key, tier in (swing.get("tiers") or {}).items():
        if SWING_CONTEXT_ONLY_FIELDS & set(tier.get("weights") or {}):
            errors.append(f"screens/swing.json:tiers.{tier_key}: a context-only signal "
                          "appears in this tier's declared weights")
        for index, row in enumerate(tier.get("results") or []):
            if SWING_CONTEXT_ONLY_FIELDS & set(row.get("legs") or {}):
                errors.append(f"screens/swing.json:tiers.{tier_key}.results.{index}: a "
                              "context-only signal appears among the scored legs")
    if "observations" in ((swing.get("regime_gate") or {}).get("vix") or {}):
        errors.append("screens/swing.json: raw FRED observations must not be published "
                      "inside regime_gate.vix")
    return errors


def congress_trades_schema_errors():
    """``screens/*.json`` files sit outside the ``FILES`` loop above, which only covers
    fixtures at ``DATA_DIR`` root - congress-trades.json is the first screen file to get
    schema coverage, added alongside its executive-branch (OGE) rows. A missing file is not
    reported here, unlike a ``FILES`` fixture: this screen legitimately does not exist yet
    in a fresh checkout or an environment that has never run ``build_congress_screen.py``,
    and that is that module's own concern (see ``run()``'s "nothing to publish yet" case),
    not this validator's.
    """
    data_path = os.path.join(DATA_DIR, "screens", "congress-trades.json")
    if not os.path.exists(data_path):
        return []
    payload = load(data_path)
    validator = Draft202012Validator(load(CONGRESS_TRADES_SCHEMA), format_checker=FormatChecker())
    return [f"screens/congress-trades.json:{'.'.join(str(part) for part in error.path) or '$'}: "
            f"{error.message}"
            for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))]


def validate(production=False):
    errors = []
    payloads = {}
    for name in FILES:
        data_path = os.path.join(DATA_DIR, f"{name}.json")
        schema_path = os.path.join(SCHEMA_DIR, f"{name}.schema.json")
        if not os.path.exists(data_path):
            errors.append(f"{name}.json: missing")
            continue
        payload = payloads[name] = load(data_path)
        validator = Draft202012Validator(load(schema_path), format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
            location = ".".join(str(part) for part in error.path) or "$"
            errors.append(f"{name}.json:{location}: {error.message}")

    for name in ("trades", "prices", "news", "politicians", "signals", "etfs"):
        payload = payloads.get(name, {})
        collection = payload.get(name if name != "politicians" else "leaderboard")
        if name == "prices":
            collection = payload.get("prices")
        if collection is not None and payload.get("count") != len(collection):
            errors.append(f"{name}.json: count does not match collection length")

    advisor = payloads.get("advisor", {})
    if advisor and advisor.get("count") != len(advisor.get("research", [])):
        errors.append("advisor.json: count does not match research length")
    # The blend is a config decision, so validate the contract rather than the constants:
    # three components that sum to one, fundamentals dominant, news a bounded tilt.
    weights = advisor.get("methodology", {}).get("weights") if advisor else None
    if advisor:
        if set(weights or {}) != {"fundamentals", "market_behavior", "news_sentiment"}:
            errors.append("advisor.json: methodology.weights must name exactly fundamentals, "
                          "market_behavior, and news_sentiment")
        else:
            total = sum(weights.values())
            if abs(total - 1.0) > 1e-6:
                errors.append(f"advisor.json: ranking weights sum to {total}, not 1.0")
            if weights["fundamentals"] < 0.6:
                errors.append("advisor.json: fundamentals must carry at least 60% of the blend")
            if weights["fundamentals"] <= weights["market_behavior"] + weights["news_sentiment"]:
                errors.append("advisor.json: fundamentals must outweigh price and news combined")
            # Headline sentiment alpha decays within days; it cannot be a core component.
            if weights["news_sentiment"] > 0.15:
                errors.append("advisor.json: news sentiment is a tilt, capped at 15% of the blend")
    regime = advisor.get("market", {}).get("macro", {}).get("regime")
    if regime and "observations" in regime:
        errors.append("advisor.json: raw FRED observations must not be published")
    scores = [row.get("score", -1) for row in advisor.get("research", [])]
    if scores != sorted(scores, reverse=True):
        errors.append("advisor.json: research rows are not ranked by descending score")
    if advisor:
        publish_limit = advisor.get("publish_limit", 20)
        expected = min(publish_limit, advisor.get("universe_count", publish_limit))
        if advisor.get("count") != expected:
            errors.append(f"advisor.json: expected {expected} published rankings, found {advisor.get('count')}")
    # Schema at which peer tiers replaced continuous percentiles (see peer_groups.py).
    PEER_TIER_SCHEMA = 6
    peer_contract_applies = int(advisor.get("schema_version") or 0) >= PEER_TIER_SCHEMA
    for index, row in enumerate(advisor.get("research", [])):
        if row.get("components", {}).get("fundamentals") is None:
            errors.append(f"advisor.json:research.{index}: ranked company lacks a fundamental score")
        if all(row.get(metric) is None for metric in ("peg", "forward_pe", "price_to_sales", "price_to_book")):
            errors.append(f"advisor.json:research.{index}: ranked company lacks every valuation metric")
        history = row.get("history")
        for key in ("closes", "growth"):
            if history and len(history.get("dates", [])) != len(history.get(key, [])):
                errors.append(f"advisor.json:research.{index}: price history dates and {key} series disagree")
        recommendation = row.get("recommendation")
        if recommendation and recommendation.get("action") in ("TRIM", "SELL") and recommendation.get("agreement_count", 0) < 2:
            errors.append(f"advisor.json:research.{index}: sell guidance requires two agreeing factors")
        percentile = row.get("valuation_percentile")
        # A payload is validated against the contract it was written under. The peer rules
        # below arrived with schema 6 (tiers replacing continuous percentiles); an older
        # committed artifact predates them and is migrated at read time by
        # src/lib/schemaMigrations.js advisorV5ToV6, which strips the fields this rejects.
        if percentile and peer_contract_applies:
            if row.get("sector_valuation_percentile") != percentile.get("ordinal"):
                errors.append(f"advisor.json:research.{index}: legacy and canonical peer ordinals disagree")
            # A peer claim below the minimum sample must be absent, not degraded, and no
            # continuous percentile may be published at all -- the ranked quantity is a
            # composite of discrete bands and cannot support one. See peer_groups.py.
            context = percentile.get("peer_context")
            valid_peers = percentile.get("peer_count_with_valid_data", 0)
            minimum = percentile.get("minimum_peer_count", 30)
            if context is not None and valid_peers < minimum:
                errors.append(f"advisor.json:research.{index}: peer context published below minimum peer count")
            if context is None and percentile.get("tier") is not None:
                errors.append(f"advisor.json:research.{index}: suppressed peer group still published a tier")
            for banned in ("value", "display_value"):
                if percentile.get(banned) is not None:
                    errors.append(f"advisor.json:research.{index}: peer payload published a continuous "
                                  f"percentile ('{banned}'), which the sample cannot support")
        analysis = row.get("analysis_v2", {})
        structural = analysis.get("structural", {})
        evidence_weight = structural.get("evidence_weight_resolved", structural.get("confidence", 1))
        if evidence_weight < 0.4 and analysis.get("company_classification") != "insufficient_evidence":
            errors.append(f"advisor.json:research.{index}: low resolved evidence weight must classify as "
                          "insufficient evidence")
    errors.extend(enrichment_coverage_errors(advisor))

    benchmark_history = advisor.get("benchmark_history", {})
    benchmark_dates = benchmark_history.get("dates", [])
    for key in ("closes", "growth"):
        if advisor and len(benchmark_history.get(key, [])) != len(benchmark_dates):
            errors.append(f"advisor.json: benchmark dates and {key} series disagree")
    configured_portfolio = {
        symbol.upper()
        for symbol in (load(os.path.join(os.path.dirname(__file__), "config", "advisor_universe.json"))
                       .get("portfolio_symbols", []))
    }
    covered_portfolio = {
        row.get("ticker", "").upper()
        for row in advisor.get("portfolio_coverage", [])
    }
    if advisor and configured_portfolio - covered_portfolio:
        missing = ", ".join(sorted(configured_portfolio - covered_portfolio))
        errors.append(f"advisor.json: portfolio coverage missing configured symbols: {missing}")

    errors.extend(theme_screen_errors(advisor.get("theme_screen")))
    errors.extend(etf_peer_group_errors(payloads.get("etfs", {})))
    errors.extend(congress_trades_schema_errors())
    errors.extend(swing_context_signal_errors())

    # Legacy political fixtures stay explicitly demo while the independent advisor and ETF
    # datasets are live.
    modes = {p.get("data_mode") for key, p in payloads.items() if key not in ("status", "advisor", "etfs")}
    if len(modes) > 1:
        errors.append(f"data_mode mismatch across payloads: {sorted(modes)}")
    if production and modes != {"live"}:
        errors.append("production validation requires data_mode=live in every payload")

    for index, trade in enumerate(payloads.get("trades", {}).get("trades", [])):
        if trade.get("filing_lag_days") is not None and trade["filing_lag_days"] < 0:
            errors.append(f"trades.json:trades.{index}: filing date precedes trade date")
        if production and trade.get("source") == "mock":
            errors.append(f"trades.json:trades.{index}: mock source forbidden in production")

    if production:
        oldest = payloads.get("trades", {}).get("history_oldest_trade_date")
        try:
            history_days = (date.today() - date.fromisoformat(oldest)).days
        except (TypeError, ValueError):
            history_days = 0
        if history_days < 95:
            errors.append(f"production requires at least 95 days of trade history (found {history_days})")

    for index, item in enumerate(payloads.get("news", {}).get("items", [])):
        if payloads["news"].get("data_mode") == "live" and not item.get("url", "").startswith("http"):
            errors.append(f"news.json:items.{index}: live item needs an http(s) source URL")

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true", help="reject demo/mock data")
    args = parser.parse_args()
    errors = validate(production=args.production)
    if errors:
        print("Data validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(FILES)} public data contracts ({'production' if args.production else 'any mode'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
