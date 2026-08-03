"""Append-only point-in-time analyst-estimate snapshot collection."""

import hashlib
import json
import os
from datetime import datetime, timezone


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
