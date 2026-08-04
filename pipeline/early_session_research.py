"""Capability-gated early-session research infrastructure.

Two of the six capabilities below - premarket/after-hours OHLCV and first-hour intraday
bars - are computed from what pipeline/collect_marketstack.py has actually collected,
not hardcoded, so a real Marketstack collection run flips them to available with real
evidence instead of a guess. Even once real data exists, the two live screens stay
killed: reversal detection (support zones, confirmation, trigger/invalidation) is a
separate module that does not exist yet. This module deliberately contains no synthetic
premarket/first-hour scoring fallback: daily closes must never masquerade as
early-session observations, and raw bars must never masquerade as a detected reversal.
"""

from __future__ import annotations

from datetime import datetime, timezone

from collect_marketstack import depth as marketstack_depth
from common import save_json


def _marketstack_capabilities():
    info = marketstack_depth()
    available = info["rows"] > 0
    freshness = f"Last collected {info['last_observed']}" if info["last_observed"] else "Not collected"
    provider = f"Marketstack ({'/'.join(info['modes'])})" if available else "None"
    granularity = "Intraday bars" if "intraday" in info["modes"] else (
        "End-of-day only (intraday not available on the configured plan)"
        if available else "Daily regular-session history only")
    evidence = [
        "pipeline/collect_marketstack.py collects the top-100 published tickers via Marketstack",
        f"pipeline/data/marketstack/collected.jsonl: {info['rows']} row(s) collected",
    ] if available else [
        "pipeline/collect_marketstack.py has not collected any rows yet",
        "pipeline/fetch_advisor.py:yahoo_history requests period only; no interval or prepost",
    ]
    verdict = ("PREMARKET_DATA_AVAILABLE_NO_REVERSAL_ENGINE" if available
               else "KILL_PREMARKET_SCREEN")
    return {
        "capability": "Premarket and after-hours OHLCV", "available": available,
        "provider": provider, "granularity": granularity, "freshness": freshness,
        "verdict": verdict, "evidence": evidence,
    }, {
        "capability": "First-hour intraday bars", "available": "intraday" in info["modes"],
        "provider": provider if "intraday" in info["modes"] else "None",
        "granularity": granularity, "freshness": freshness,
        "verdict": ("INTRADAY_DATA_AVAILABLE_NO_REVERSAL_ENGINE" if "intraday" in info["modes"]
                    else "KILL_FIRST_HOUR_SCREEN"),
        "evidence": evidence,
    }


STATIC_CAPABILITIES = (
    {
        "capability": "Stock bid/ask, spread, quote timestamp, and halt flags",
        "available": False,
        "provider": "None for common-stock research",
        "granularity": "Current price snapshot only",
        "freshness": "Fetch timestamp; no exchange quote timestamp",
        "verdict": "NO_EXECUTION_QUALITY_SCORE",
        "evidence": [
            "pipeline/providers.py:Quote has price but no bid, ask, spread, or halt fields",
            "ETF disclosure spread fields are fund-only and cannot cover the stock universe",
        ],
    },
    {
        "capability": "Earnings calendar and timestamped instrument news",
        "available": True,
        "provider": "Marketaux plus point-in-time earnings events",
        "granularity": "Event/article",
        "freshness": "Marketaux cache up to 4 hours; earnings appended when collected",
        "verdict": "CONTEXT_ONLY_WHEN_TIMESTAMP_AND_PRIMARY_TICKER_PRESENT",
        "evidence": [
            "pipeline/marketaux.py maps published_at and a strong primary ticker",
            "pipeline/estimate_snapshots.py stores timestamped earnings events and session",
            "RSS fallback is policy-keyword mapping and is not sufficient for confirmation",
        ],
    },
    {
        "capability": "Sector and industry context",
        "available": True,
        "provider": "Yahoo Finance; SPY daily benchmark",
        "granularity": "Classification plus daily prices",
        "freshness": "Pipeline refresh cadence",
        "verdict": "DAILY_CONTEXT_ONLY",
        "evidence": [
            "pipeline/fetch_prices.py stores sector and industry",
            "pipeline/fetch_advisor.py fetches SPY daily history",
        ],
    },
    {
        "capability": "Existing support-zone engine and structural score",
        "available": False,
        "provider": "Structural score exists; support-zone engine does not",
        "granularity": "Daily structural research",
        "freshness": "Pipeline refresh cadence",
        "verdict": "SUPPORT_ZONE_REQUIRED_BEFORE_CANDIDATES",
        "evidence": [
            "pipeline/research_screens_v2.py provides structural research formulas",
            "No production module emits support-zone bounds or evidence counts",
        ],
    },
    {
        "capability": "Shadow-trade store and point-in-time snapshots",
        "available": False,
        "provider": "Point-in-time fundamentals/universe store only",
        "granularity": "Per pipeline run",
        "freshness": "Append-only on refresh",
        "verdict": "EARLY_SESSION_SHADOW_LEDGER_REQUIRED",
        "evidence": [
            "pipeline/pit_store.py stores fundamentals and universe membership",
            "Existing shadow portfolios are research outputs, not timestamped intraday trades",
        ],
    },
)


def capability_report(*, generated_at=None):
    """Build the published gate report from repository-audited capabilities."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    premarket_capability, intraday_capability = _marketstack_capabilities()
    capabilities = [premarket_capability, intraday_capability, *(dict(row) for row in STATIC_CAPABILITIES)]
    # Real bars unblock the data half of each screen but not the screen itself - reversal
    # detection (support zones, confirmation, trigger/invalidation) is a separate module
    # that still does not exist, so both stay killed either way. Only the reason changes,
    # from "no data at all" to the honest, narrower reason once data is actually flowing.
    premarket_reason = ("SUPPORT_ZONE_ENGINE_NOT_BUILT" if premarket_capability["available"]
                        else "NO_EXTENDED_HOURS_OHLCV")
    first_hour_reason = ("SUPPORT_ZONE_ENGINE_NOT_BUILT" if intraday_capability["available"]
                         else "NO_SUB_15_MINUTE_BARS")
    return {
        "schema_version": "1.0.0",
        "model_version": "early-session-gate-v1.0.0",
        "generated_at": generated_at,
        "mode": "shadow_only",
        "status": "gated",
        "capabilities": capabilities,
        "screens": {
            "premarket_reversal": {
                "status": "killed",
                "reason_code": premarket_reason,
                "fallback": "next_open_daily_research_only",
                "candidate_count": 0,
            },
            "first_hour_reversal": {
                "status": "killed",
                "reason_code": first_hour_reason,
                "fallback": "end_of_day_studies_only",
                "candidate_count": 0,
            },
        },
        "execution_quality": {
            "status": "unavailable",
            "reason_code": "NO_STOCK_BID_ASK_OR_SPREAD",
            "permitted_liquidity_proxy": "median_daily_dollar_volume",
        },
        "candidate_contract": ["setup", "trigger", "confirmation", "invalidation"],
        "permitted_labels": [
            "possible support zone", "early reversal", "confirmation pending",
            "confirmed reversal", "failed reversal", "invalidated setup",
        ],
        "disclaimer": (
            "Research-only shadow mode. No trades are placed. Killed screens are a successful "
            "data-quality outcome and must not be bypassed with daily or stale observations."
        ),
    }


def enforce_candidate_contract(candidate):
    """Keep incomplete candidates at Watch and prevent positive stale-data labels."""
    result = dict(candidate or {})
    missing = [field for field in ("setup", "trigger", "confirmation", "invalidation")
               if not str(result.get(field) or "").strip()]
    data_quality = result.get("data_quality") or {}
    if missing or not data_quality.get("fresh", False):
        result["state"] = "insufficient_data" if not data_quality.get("fresh", False) else "watch"
        result["actionable"] = False
    else:
        result["actionable"] = bool(result.get("actionable", False))
    result["missing_contract_fields"] = missing
    result["mode"] = "shadow_only"
    return result


def run():
    report = capability_report()
    save_json("screens/early-session.json", report)
    return report


if __name__ == "__main__":
    run()
