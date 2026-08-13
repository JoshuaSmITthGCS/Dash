"""
common.py -- shared utilities for the pipeline.
No external dependencies beyond `requests` (and stdlib). Keeps every script consistent.
"""

import json
import hashlib
import math
import os
import subprocess
import tempfile
import time
from datetime import datetime, date, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "public", "data")
STORE_DIR = os.path.join(HERE, "data")
CONFIG_DIR = os.path.join(HERE, "config")
LOG_DIR = os.path.join(HERE, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STORE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


class _Log:
    """Tiny logger that prints and appends to a local dated logfile."""

    def __init__(self):
        self.path = os.path.join(LOG_DIR, f"pipeline-{date.today().isoformat()}.log")

    def _write(self, level, msg):
        line = f"{datetime.now(timezone.utc).isoformat()} [{level}] {msg}"
        print(line, flush=True)
        try:
            with open(self.path, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def info(self, m): self._write("INFO", m)
    def warn(self, m): self._write("WARN", m)
    def error(self, m): self._write("ERROR", m)


LOG = _Log()


# ---------- HTTP ----------

def http_get_json(url, params=None, headers=None, retries=3, backoff=2.0, timeout=30):
    """GET JSON with exponential backoff. Returns parsed JSON or None on failure."""
    try:
        import requests
    except ImportError:
        LOG.error("requests not installed. pip install -r requirements.txt")
        return None

    request_headers = {"User-Agent": "PolitiTrade/2.0 (personal research dashboard)", **(headers or {})}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=request_headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            LOG.warn(f"{url} -> HTTP {resp.status_code} (attempt {attempt}/{retries})")
        except Exception as e:  # noqa: BLE001
            LOG.warn(f"{url} -> {type(e).__name__}: {e} (attempt {attempt}/{retries})")
        if attempt < retries:
            time.sleep(backoff ** attempt)
    LOG.error(f"GET failed after {retries} attempts: {url}")
    return None


# ---------- JSON IO ----------

def load_json(name, from_config=False):
    base = CONFIG_DIR if from_config else DATA_DIR
    path = os.path.join(base, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _git_commit_sha():
    """Return the exact code revision that produced an artifact for reproducibility."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(HERE), text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _settings_version():
    """Read semantic version and hash the full settings source of truth.

    Hashing the serialized config, rather than a hand-selected subset, makes any weight,
    threshold, or band change reproduce a distinct published model configuration.
    """
    settings = load_json("settings.json", from_config=True) or {}
    encoded = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    return (
        (settings.get("model") or {}).get("semantic_version", "0.0.0"),
        hashlib.sha256(encoded).hexdigest(),
    )


def config_hash():
    """Public accessor for the settings.json hash _settings_version computes internally.

    Every published research row is required to carry a model version and a config hash
    (docs/RESEARCH-CONTRACT.md, invariant tests) so a scoring result can always be traced
    back to the exact configuration that produced it. Callers outside this module (the
    sleeve interface, experiment records) should use this rather than reaching into the
    private _settings_version helper.
    """
    return _settings_version()[1]


def versioned_artifact(obj):
    """Add an additive model-version envelope to a public JSON object.

    Existing dataset-specific ``model_version`` strings remain untouched for schema
    compatibility. ``model_metadata`` supplies the shared semantic version, exact code
    revision, complete settings hash, and generation time requested for reproducibility.
    """
    if not isinstance(obj, dict):
        return obj
    generated_at = obj.get("generated_at") or datetime.now(timezone.utc).isoformat()
    semantic_version, config_hash = _settings_version()
    artifact = dict(obj)
    artifact.setdefault("generated_at", generated_at)
    artifact.setdefault("model_version", semantic_version)
    artifact["model_metadata"] = {
        "semantic_version": semantic_version,
        "git_commit_sha": _git_commit_sha(),
        "config_hash": config_hash,
        "generated_at": generated_at,
    }
    return artifact


def _json_safe(value):
    """Replace non-finite floats with JSON's explicit missing-value marker.

    Python's encoder otherwise writes Infinity/NaN even though neither token is valid JSON.
    Browsers reject the entire research snapshot when one upstream ratio is non-finite, so
    clean recursively and keep ``allow_nan=False`` as a final publication guard.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    return value


def save_json(name, obj, to_config=False, to_store=False):
    """Atomically write JSON so readers never observe a partially-written payload."""
    base = STORE_DIR if to_store else (CONFIG_DIR if to_config else DATA_DIR)
    if not to_config and not to_store:
        obj = versioned_artifact(obj)
    path = os.path.join(base, name)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(name)}.", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(_json_safe(obj), f, indent=2, default=str, allow_nan=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_store_json(name):
    path = os.path.join(STORE_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def data_mode(*payloads):
    """Return demo if any input is explicitly demo or contains mock-sourced trades."""
    for payload in payloads:
        if not payload:
            continue
        if payload.get("data_mode") == "demo":
            return "demo"
        if any(row.get("source") == "mock" for row in payload.get("trades", [])):
            return "demo"
    return "live"


def update_pipeline_status(stage, *, status, source=None, message=None, details=None):
    """Publish stage/source health for the site and scheduled-run diagnostics."""
    payload = load_json("status.json") or {"stages": {}}
    payload.setdefault("stages", {})[stage] = {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **({"source": source} if source else {}),
        **({"message": message} if message else {}),
        **({"details": details} if details is not None else {}),
    }
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    stages = payload["stages"].values()
    payload["status"] = "error" if any(s["status"] == "error" for s in stages) else (
        "degraded" if any(s["status"] == "degraded" for s in stages) else "healthy"
    )
    save_json("status.json", payload)
    return payload


# ---------- Dates / names ----------

def today_iso():
    return date.today().isoformat()


def _parse(d):
    if not d:
        return None
    if isinstance(d, (datetime, date)):
        return d if isinstance(d, date) else d.date()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(d)[:19], fmt).date()
        except ValueError:
            continue
    return None


def days_between(start, end):
    """Whole days from start to end. None if either is unparseable."""
    a, b = _parse(start), _parse(end)
    if a is None or b is None:
        return None
    return (b - a).days


def normalize_name(name):
    return " ".join(str(name).lower().split())
