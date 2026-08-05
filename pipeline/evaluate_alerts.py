"""Evaluate Firestore alert rules after a scored refresh and write deduplicated events.

The evaluator has no market-data provider calls. It reads the just-published advisor artifact,
compares each rule with its stored last state, writes in-app events first, then asks the Netlify
delivery function to send one grouped push per user. Missing server credentials skip cleanly so
local refreshes and forks without alert infrastructure still work.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from collections import defaultdict
from pathlib import Path

from common import load_json

SETTINGS = json.loads((Path(__file__).parent / "config" / "settings.json").read_text())
ALERT_CONFIG = SETTINGS["alerts"]
BAND_ORDER = {"ATTRACTIVE": 0, "NEUTRAL": 1, "CAUTIOUS": 2, "UNATTRACTIVE": 3}


def _finite(value):
    try:
        return value is not None and not isinstance(value, bool) and float(value) == float(value)
    except (TypeError, ValueError):
        return False


def _daily_return(row, days):
    history = row.get("history") or {}
    closes = [float(value) for value in history.get("closes", []) if _finite(value)]
    if len(closes) <= days or not closes[-days - 1]:
        technical = row.get("technical_detail") or {}
        fallback = technical.get("return_5d" if days == 5 else "return_1d")
        return float(fallback) if _finite(fallback) else None
    return (closes[-1] / closes[-days - 1] - 1) * 100


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        try:
            return dt.datetime.combine(dt.date.fromisoformat(str(value)[:10]), dt.time(), dt.timezone.utc)
        except ValueError:
            return None


def evaluate_rule(rule, row=None, generated_at=None, now=None):
    """Return one observable condition state with stable fingerprint for deduplication."""
    now = now or dt.datetime.now(dt.timezone.utc)
    kind = rule.get("type")
    ticker = str(rule.get("ticker") or "").upper()
    url = "/alerts" if kind == "pipeline_stale" else f"/search?q={ticker}"
    active, value, message, fingerprint = False, None, "", None
    if kind == "pipeline_stale":
        generated = _parse_date(generated_at)
        hours = float(rule.get("staleHours") or ALERT_CONFIG["default_pipeline_stale_hours"])
        age = (now - generated).total_seconds() / 3600 if generated else float("inf")
        active, value = age >= hours, age
        message = f"Research data is {age:.1f} hours old. The alert threshold is {hours:g} hours."
        fingerprint = f"pipeline:{generated_at}:{active}"
    elif not row:
        return {"active": False, "fingerprint": "ticker-unavailable", "value": None}
    elif kind == "price_cross":
        value = row.get("price")
        threshold = float(rule.get("threshold")) if _finite(rule.get("threshold")) else None
        if threshold is None or threshold <= 0:
            return {"active": False, "fingerprint": "invalid-threshold", "value": value}
        active = _finite(value) and (float(value) >= threshold if rule.get("direction") == "above" else float(value) <= threshold)
        message = f"{ticker} is ${float(value):.2f}, {rule.get('direction')} the ${threshold:.2f} alert level." if _finite(value) else f"{ticker} has no current price."
        fingerprint = f"price:{ticker}:{rule.get('direction')}:{threshold}:{active}"
    elif kind == "percent_move":
        days = 5 if int(rule.get("periodDays") or 1) == 5 else 1
        value = _daily_return(row, days)
        threshold = float(rule.get("threshold")) if _finite(rule.get("threshold")) else None
        if threshold is None or threshold <= 0:
            return {"active": False, "fingerprint": "invalid-threshold", "value": value}
        active = _finite(value) and (float(value) >= threshold if rule.get("direction") == "above" else float(value) <= -threshold)
        message = f"{ticker} moved {float(value):+.1f}% over {days} day{'s' if days != 1 else ''}." if _finite(value) else f"{ticker} has insufficient return history."
        fingerprint = f"move:{ticker}:{days}:{rule.get('direction')}:{threshold}:{active}"
    elif kind == "stop_trigger":
        value = row.get("price")
        threshold = float(rule.get("threshold")) if _finite(rule.get("threshold")) else None
        if threshold is None or threshold <= 0:
            return {"active": False, "fingerprint": "invalid-threshold", "value": value}
        active = _finite(value) and float(value) <= threshold
        message = f"{ticker} is ${float(value):.2f}, at or below the {rule.get('stopKind', 'trim')} stop of ${threshold:.2f}." if _finite(value) else f"{ticker} has no current price."
        fingerprint = f"stop:{ticker}:{rule.get('stopKind')}:{threshold}:{active}"
    elif kind == "score_band":
        value = str(row.get("stance") or "").upper()
        target = str(rule.get("band") or "ATTRACTIVE").upper()
        current_order, target_order = BAND_ORDER.get(value), BAND_ORDER.get(target)
        active = current_order is not None and (current_order <= target_order if rule.get("direction") == "above" else current_order > target_order)
        message = f"{ticker} is now in the {value.title()} research band."
        fingerprint = f"band:{ticker}:{rule.get('direction')}:{target}:{value}"
    elif kind == "guidance_change":
        value = str(((row.get("recommendation") or {}).get("action")) or "").upper()
        actions = [str(item).upper() for item in rule.get("guidanceActions") or ["TRIM", "SELL"]]
        active = value in actions
        message = f"{ticker} guidance changed to {value.title()}."
        fingerprint = f"guidance:{ticker}:{value}"
    elif kind == "earnings_upcoming":
        earnings = _parse_date(row.get("next_earnings_date") or row.get("earnings_date"))
        days = (earnings.date() - now.date()).days if earnings else None
        limit = int(rule.get("daysAhead") or ALERT_CONFIG["default_earnings_notice_days"])
        active, value = days is not None and 0 <= days <= limit, days
        message = f"{ticker} earnings are scheduled in {days} day{'s' if days != 1 else ''}." if days is not None else f"{ticker} has no published upcoming earnings date."
        fingerprint = f"earnings:{ticker}:{earnings.date() if earnings else 'unknown'}:{active}"
    else:
        return {"active": False, "fingerprint": "unsupported-rule", "value": None}
    return {
        "active": bool(active), "fingerprint": fingerprint, "value": value,
        "title": "Research data is stale" if kind == "pipeline_stale" else f"{ticker} alert",
        "message": message, "url": url, "kind": kind, "ticker": ticker or None,
    }


def should_fire(previous, current):
    """Fire only on inactive-to-active or a materially changed active condition."""
    return bool(current.get("active")) and (not (previous or {}).get("active") or (previous or {}).get("fingerprint") != current.get("fingerprint"))


def _deliver(deliveries):
    url = os.getenv("ALERT_DELIVERY_URL")
    secret = os.getenv("ALERT_DELIVERY_SECRET")
    if not url or not secret or not deliveries:
        return
    request = urllib.request.Request(url, data=json.dumps({"deliveries": deliveries}).encode(), method="POST", headers={"content-type": "application/json", "x-alert-delivery-secret": secret})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status >= 300:
            raise RuntimeError(f"alert delivery returned {response.status}")


def main():
    credentials = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not credentials:
        print("Alert evaluation skipped: FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
        return 0
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(firebase_credentials.Certificate(json.loads(credentials)))
    db = firestore.client()
    advisor = load_json("advisor.json") or {}
    rows = {row.get("ticker"): row for row in [*(advisor.get("research") or []), *(advisor.get("portfolio_coverage") or [])] if row.get("ticker")}
    now = dt.datetime.now(dt.timezone.utc)
    deliveries = defaultdict(list)
    evaluated = fired = 0
    for snapshot in db.collection_group("rules").stream():
        rule = snapshot.to_dict()
        if rule.get("enabled") is False:
            continue
        user_ref = snapshot.reference.parent.parent
        current = evaluate_rule(rule, rows.get(str(rule.get("ticker") or "").upper()), advisor.get("generated_at"), now)
        previous = rule.get("lastState") or {}
        state = {"active": current.get("active"), "fingerprint": current.get("fingerprint"), "value": current.get("value"), "evaluatedAt": now.isoformat()}
        snapshot.reference.set({"lastState": state}, merge=True)
        evaluated += 1
        if not should_fire(previous, current):
            continue
        event_ref = user_ref.collection("events").document()
        event = {key: current.get(key) for key in ("title", "message", "url", "kind", "ticker")}
        event.update({"ruleId": snapshot.id, "createdAt": now.isoformat(), "readAt": None, "pushedAt": None})
        event_ref.set(event)
        deliveries[user_ref.id].append({"id": event_ref.id, **event})
        fired += 1
    grouped = [{"uid": uid, "events": events[:ALERT_CONFIG["maximum_grouped_push_events"]]} for uid, events in deliveries.items()]
    _deliver(grouped)
    print(f"Evaluated {evaluated} alert rules and fired {fired} deduplicated events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
