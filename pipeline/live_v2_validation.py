"""Controlled representative-universe refresh that never replaces production outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone

from canonical_metrics import yahoo_observations
from common import LOG
from fetch_advisor import yahoo_extended
from fetch_prices import fetch_snapshot
from fundamentals_extended import EXTENDED_METRIC_UNITS, extended_observations
from peer_groups import MINIMUM_VALID_PEERS, canonical_percentiles
from recommendation_policy_v2 import build_recommendation_v2
from research_screens_v2 import momentum_boundary_diagnostics, momentum_factors
from scorer import valuation_score
from scoring_v2 import MODEL_VERSION, build_v2_analysis

REPRESENTATIVE_UNIVERSE = ("HIG", "JPM", "O", "NEE", "BSX", "MSFT", "XOM", "MRNA", "VTI", "TLT")
ETF_TICKERS = {"VTI", "TLT"}


def _clean(value):
    if value is None or isinstance(value, (str, bool, int)): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, dict): return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_clean(item) for item in value]
    return str(value)


def _atomic_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(_clean(payload), handle, indent=2, allow_nan=False); handle.write("\n")
    os.replace(temporary, path)


def _history_rows(frame):
    if frame is None or frame.empty: return []
    rows = []
    for stamp, row in frame.iterrows():
        price = row.get("Close")
        if price is not None and math.isfinite(float(price)):
            rows.append({"date": stamp.date().isoformat(), "adjusted_close": float(price)})
    return rows


def _closes_volumes(frame):
    """``derive_extended``'s market-structure inputs, from the same price frame already
    fetched for momentum -- no second history request."""
    if frame is None or frame.empty: return [], []
    closes, volumes = [], []
    for _, row in frame.iterrows():
        price = row.get("Close")
        if price is not None and math.isfinite(float(price)):
            closes.append(float(price))
            volumes.append(float(row.get("Volume") or 0))
    return closes, volumes


def _observation_count(observations):
    return sum(len(rows) for rows in (observations or {}).values())


def _invariants(ticker, analysis, recommendation, observations, peer):
    statuses = analysis.get("metric_status") or {}
    checks = {
        "legacy_values_never_contribute": all("legacy_value_missing_lineage" not in detail.get("quality_flags", [])
                                               or detail.get("score_contribution") is None
                                               for detail in statuses.values()),
        "suppressed_metrics_no_score": all(detail.get("score_contribution") is None for detail in statuses.values()
                                            if detail.get("status") in {"suppressed", "replaced"}),
        "inapplicable_not_neutral": all(detail.get("score_contribution") is None for detail in statuses.values()
                                       if detail.get("status") in {"suppressed", "replaced"}),
        "critical_gaps_reduce_profile_confidence": (not analysis["applicability"]["critical_data_gaps"]
                                                    or analysis["applicability"]["profile_confidence"] < 1),
        # A peer sample below peer_groups.MINIMUM_VALID_PEERS must never carry a tier/ordinal
        # -- canonical_percentiles() already guarantees this, but the gate used to be a bare
        # `True` literal that could not fail regardless of what "classification" published.
        "invalid_peer_sample_no_percentile": (
            peer is None or peer.get("tier") is not None or peer.get("ordinal") is None),
        # Minimum over the layers that actually produced a score. A layer that resolved
        # nothing has no opinion to be confident or unconfident about; folding its zero in
        # here forced every company below the gate regardless of the evidence behind it.
        "low_confidence_action_gate": (
            min((layer["evidence_weight_resolved"] for layer in (analysis["structural"], analysis["timeliness"])
                 if layer.get("effective_score") is not None), default=0.0) >= .60
            or recommendation["company_action"]["label"] not in {"buy", "accumulate", "sell_thesis"}),
        # A layer that resolved nothing must publish no score at all, on every row.
        "unresolved_layer_publishes_no_score": all(
            layer.get("effective_score") is None
            for layer in (analysis["structural"], analysis["timeliness"])
            if layer.get("raw_score") is None),
        "company_and_position_actions_separate": recommendation["company_action"] is not recommendation["position_action"],
        "timestamps_explicit": all(row.get("fetched_at") and row.get("observed_at")
                                   for rows in observations.values() for row in rows),
        "hig_invalid_metrics_suppressed": (ticker != "HIG" or all(
            statuses.get(metric, {}).get("score_contribution") is None
            for metric in ("peg", "current_ratio", "return_on_invested_capital", "free_cash_flow_yield"))),
    }
    return {key: {"status": "pass" if passed else "fail"} for key, passed in checks.items()}


def validate_live(output_path, raw_root, tickers=REPRESENTATIVE_UNIVERSE):
    import yfinance as yf
    fetched_at = datetime.now(timezone.utc).isoformat()
    prepared, errors = [], []
    for ticker in tickers:
        try:
            instrument = yf.Ticker(ticker)
            info = _clean(instrument.info or {})
            raw = {"provider": "yahoo", "ticker": ticker, "fetched_at": fetched_at, "info": info}
            raw_json = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
            raw_path = os.path.join(raw_root, f"{ticker}-{fetched_at[:10]}.json")
            _atomic_json(raw_path, raw)
            observations = yahoo_observations(info, fetched_at)
            LOG.info(f"{ticker}: quote observations -- {_observation_count(observations)} non-null "
                     f"of {len(info)} raw Yahoo .info field(s)")
            snapshot = fetch_snapshot(ticker, yf, ETF_TICKERS, ticker_obj=instrument) or {"ticker": ticker}
            snapshot.update({"ticker": ticker, "is_etf": ticker in ETF_TICKERS,
                             "observations": observations, "data_fetched_at": fetched_at})
            price_frame = instrument.history(period="15mo", auto_adjust=True, actions=True)
            history = _history_rows(price_frame)

            # Statement enrichment: the same call fetch_advisor.enrich() makes for the
            # production shortlist. Without it, `observations` covers only the ~11 quote-level
            # Yahoo .info fields yahoo_observations() maps, and every statement-derived metric
            # (ROIC, EV/EBITDA, Piotroski F, interest coverage, accruals ratio, ...) -- the
            # metrics carrying most of the structural score's declared weight -- reports
            # missing for every ticker regardless of real coverage. That is what made this
            # view's confidence gate read "insufficient evidence" for MSFT and JPM: not a
            # miscalculation, but company evidence computed from a fraction of what production
            # actually gathers. See fundamentals_extended.py's EXTENDED_METRIC_UNITS docstring.
            closes, volumes = _closes_volumes(price_frame)
            enrichment_diagnostics = {"attempted": 1, "info_fetch_failed": 0, "statement_fetch_failed": 0,
                                      "derivation_failed": 0, "no_statement_data": 0}
            extended = yahoo_extended(ticker, instrument, snapshot, {"closes": closes, "volumes": volumes},
                                      enrichment_diagnostics)
            extended_observation_count = 0
            if extended and extended.get("extended_coverage"):
                extended_rows = extended_observations(extended, fetched_at)
                extended_observation_count = _observation_count(extended_rows)
                for metric_id, rows in extended_rows.items():
                    observations.setdefault(metric_id, []).extend(rows)
                snapshot = {**snapshot, **extended, "observations": observations}
            LOG.info(f"{ticker}: statement observations -- {extended_observation_count} non-null of "
                     f"{len(EXTENDED_METRIC_UNITS)} extended metric(s) (diagnostics={enrichment_diagnostics})")

            _, legacy_parts = valuation_score(snapshot)
            # Scores derived without canonical lineage are diagnostic-only and cannot enter v2.
            analysis = build_v2_analysis(snapshot, legacy_parts or {}, observations=observations)
            recommendation = build_recommendation_v2(ticker, analysis, generated_at=fetched_at)
            factors = momentum_factors(history, as_of=fetched_at[:10])
            boundaries = momentum_boundary_diagnostics(history, as_of=fetched_at[:10])
            prepared.append({
                "ticker": ticker, "provider_status": "success", "raw_response": {"retention": "private_staging",
                    "path": os.path.relpath(raw_path), "sha256": hashlib.sha256(raw_json.encode()).hexdigest()},
                "observations": observations, "analysis": analysis, "snapshot": snapshot,
                "company_action": recommendation["company_action"], "portfolio_fit_state": recommendation["portfolio_fit_state"],
                "position_action": recommendation["position_action"],
                "momentum": {"factors": factors, "boundaries": boundaries},
            })
        except Exception as error:  # provider failures are explicit, not imputed
            errors.append({"ticker": ticker, "status": "fail", "provider_status": "error",
                           "reason_code": type(error).__name__, "message": str(error)[:500], "invariants": {}})

    # Peer percentiles are a cross-sectional computation (peer_groups.canonical_percentiles
    # ranks each company against the others in its peer group), so they can only be resolved
    # once every ticker's structural valuation category score is known -- after the loop
    # above, not hardcoded per-ticker inside it. This ten-name representative universe spans
    # roughly ten different peer groups (bank, insurer, REIT, utility, ...), so real peer
    # counts here will usually still read INSUFFICIENT_VALID_PEERS (MINIMUM_VALID_PEERS=30) --
    # that is an honest small-sample result, not the same as the unconditional "0 of 0"
    # this used to publish for every ticker including single-name peer groups of one.
    peer_rows = [{"ticker": row["ticker"], **{k: row["snapshot"].get(k) for k in ("sector", "industry", "is_etf")},
                 "categories": (row["analysis"]["structural"].get("categories") or {})}
                for row in prepared]
    peer_context = canonical_percentiles(peer_rows, key="valuation", constructed_at=fetched_at[:10])
    resolved = sum(1 for meta in peer_context.values() if meta.get("tier") is not None)
    LOG.info(f"peer batch: {resolved} of {len(peer_context)} ticker(s) resolved a valid tier "
             f"(minimum {MINIMUM_VALID_PEERS} peers with valid data required)")

    results = []
    for row in prepared:
        peer = peer_context.get(row["ticker"])
        invariants = _invariants(row["ticker"], row["analysis"], {
            "company_action": row["company_action"], "position_action": row["position_action"],
        }, row["observations"], peer)
        classification = {
            "company": row["analysis"]["company_classification"],
            "profile_id": row["analysis"]["applicability_profile"],
            "peer_group": peer.get("peer_group_id") if peer else None,
            "total_peer_count": peer.get("peer_count_total", 0) if peer else 0,
            "valid_peer_count": peer.get("peer_count_with_valid_data", 0) if peer else 0,
            "percentile_status": "VALID" if peer and peer.get("tier") is not None else "INSUFFICIENT_VALID_PEERS",
        }
        results.append({
            "ticker": row["ticker"], "status": ("pass" if all(check["status"] == "pass" for check in invariants.values()) else "fail"),
            "provider_status": row["provider_status"], "raw_response": row["raw_response"],
            "classification": classification, "observations": row["observations"], "analysis": row["analysis"],
            "company_action": row["company_action"], "portfolio_fit_state": row["portfolio_fit_state"],
            "position_action": row["position_action"], "momentum": row["momentum"], "invariants": invariants,
        })
    results.extend(errors)
    results.sort(key=lambda row: tickers.index(row["ticker"]))

    payload = {"schema_version": "1.0.0", "model_version": MODEL_VERSION,
               "config_version": "live-validation-v1.0.0", "universe_version": "representative-v1",
               "data_cutoff": fetched_at, "run_id": hashlib.sha256(fetched_at.encode()).hexdigest()[:16],
               "production_outputs_replaced": False, "raw_response_publication": "not_published",
               "results": results,
               "summary": {"passed": sum(row["status"] == "pass" for row in results),
                           "failed": sum(row["status"] != "pass" for row in results)}}
    _atomic_json(output_path, payload)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "public", "data", "validation", "live_v2_validation.json"))
    parser.add_argument("--raw-root", default=os.path.join(os.path.dirname(__file__), "data", "staging", "raw_provider"))
    args = parser.parse_args()
    payload = validate_live(os.path.abspath(args.output), os.path.abspath(args.raw_root))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
