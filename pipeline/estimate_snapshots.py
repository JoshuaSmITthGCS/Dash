"""Append-only point-in-time analyst-estimate snapshot collection."""

import hashlib
import json
import os
from datetime import datetime, timezone

ESTIMATE_HORIZONS = ("current_quarter", "next_quarter", "current_year", "next_year")
ESTIMATE_FIELDS = ("eps_consensus", "revenue_consensus", "analyst_count", "upward_revisions",
                   "downward_revisions", "estimate_high", "estimate_low", "dispersion")


def normalize_estimates(estimates, provider, fetched_at, freshness=None):
    """Create the declared four-horizon contract without inventing unavailable values."""
    result = {"provider": provider, "fetched_at": fetched_at, "freshness": freshness,
              "collection_status": "FORWARD_COLLECTION_ONLY", "horizons": {}}
    for horizon in ESTIMATE_HORIZONS:
        source = (estimates or {}).get(horizon) or {}
        result["horizons"][horizon] = {field: source.get(field) for field in ESTIMATE_FIELDS}
        result["horizons"][horizon]["fiscal_period"] = source.get("fiscal_period")
        result["horizons"][horizon]["available_at"] = source.get("available_at") or fetched_at
    return result


def append_estimate_snapshot(root, ticker, observed_at, estimates, source):
    """Persist exactly what was observed; an existing observation can never be replaced."""
    timestamp = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    canonical = json.dumps(estimates, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    directory = os.path.join(root, ticker.upper())
    os.makedirs(directory, exist_ok=True)
    stem = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(directory, f"{stem}-{digest[:12]}.json")
    if os.path.exists(path): return path
    if any(name.startswith(f"{stem}-") for name in os.listdir(directory)):
        raise FileExistsError("estimate observation already exists at this timestamp")
    payload = {"schema_version": "1.0.0", "ticker": ticker.upper(),
               "observed_at": timestamp.astimezone(timezone.utc).isoformat(), "source": source,
               "point_in_time": True, "content_sha256": digest, "estimates": estimates}
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)
    return path


def snapshots_at_or_before(root, ticker, as_of):
    """Only return observations actually collected by the requested point in time."""
    cutoff = datetime.fromisoformat(str(as_of).replace("Z", "+00:00")).astimezone(timezone.utc)
    directory = os.path.join(root, ticker.upper())
    if not os.path.isdir(directory): return []
    output = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"): continue
        with open(os.path.join(directory, name)) as handle: payload = json.load(handle)
        observed = datetime.fromisoformat(payload["observed_at"])
        if observed <= cutoff: output.append(payload)
    return output


def estimate_revision_diagnostics(snapshots, horizon="current_year", metric="eps_consensus",
                                  as_of=None, windows=(7, 30, 90)):
    """Use only actually collected observations; absent historical depth stays unavailable."""
    if as_of is None and snapshots:
        as_of = snapshots[-1]["observed_at"]
    cutoff = datetime.fromisoformat(str(as_of).replace("Z", "+00:00")) if as_of else None
    if cutoff is None: return {"status": "FORWARD_COLLECTION_ONLY", "reason_code": "NO_SNAPSHOTS"}
    current = None
    observations = []
    for snapshot in snapshots:
        stamp = datetime.fromisoformat(snapshot["observed_at"])
        if stamp > cutoff: continue
        contract = snapshot.get("estimates") or {}
        value = ((contract.get("horizons") or {}).get(horizon) or {}).get(metric)
        if value is not None:
            observations.append((stamp, float(value)))
            current = float(value)
    if current is None:
        return {"status": "FORWARD_COLLECTION_ONLY", "reason_code": "NO_CURRENT_CONSENSUS"}
    revisions = {}
    for days in windows:
        target = cutoff.timestamp() - days * 86400
        prior = min(observations, key=lambda item: abs(item[0].timestamp() - target), default=None)
        # Do not pretend a two-day-old snapshot is a 90-day comparison.
        adequate = prior and abs(prior[0].timestamp() - target) <= max(2, days * .15) * 86400
        revisions[f"revision_{days}d"] = (None if not adequate or prior[1] == 0
                                           else current / prior[1] - 1)
    available = [value for value in revisions.values() if value is not None]
    status = "AVAILABLE" if len(available) == len(windows) else "FORWARD_COLLECTION_ONLY"
    return {"status": status, "as_of": cutoff.astimezone(timezone.utc).isoformat(),
            "horizon": horizon, "metric": metric, **revisions,
            "revision_agreement": (sum(value > 0 for value in available) / len(available) if available else None),
            "revision_magnitude": (sum(available) / len(available) if available else None),
            "revision_acceleration": (revisions.get("revision_7d") - revisions.get("revision_30d")
                                      if revisions.get("revision_7d") is not None
                                      and revisions.get("revision_30d") is not None else None)}


def append_earnings_event(root, ticker, event):
    required = {"announcement_timestamp", "actual_eps", "consensus_eps",
                "actual_revenue", "consensus_revenue", "provider"}
    missing = required - set(event)
    if missing: raise ValueError(f"missing earnings-event fields: {sorted(missing)}")
    timestamp = datetime.fromisoformat(str(event["announcement_timestamp"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None: raise ValueError("announcement_timestamp must include timezone")
    hour = timestamp.astimezone(timezone.utc).hour
    session = event.get("session")
    if session not in {"premarket", "after_hours", "regular_session"}:
        raise ValueError("session must be premarket, after_hours, or regular_session")
    payload = {"schema_version": "1.0.0", "ticker": ticker.upper(), **event,
               "announcement_timestamp": timestamp.astimezone(timezone.utc).isoformat(),
               "standardized_surprise": None, "post_earnings_drift": None,
               "guidance_direction": event.get("guidance_direction")}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    directory = os.path.join(root, ticker.upper()); os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{timestamp.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json")
    if os.path.exists(path): return path
    if any(name.startswith(path.split(os.sep)[-1][:16]) for name in os.listdir(directory)):
        raise FileExistsError("earnings event already exists at this timestamp")
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False); handle.write("\n")
    os.replace(temporary, path)
    return path
