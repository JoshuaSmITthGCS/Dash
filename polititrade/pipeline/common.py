"""
common.py -- shared utilities for the pipeline.
No external dependencies beyond `requests` (and stdlib). Keeps every script consistent.
"""

import json
import os
import time
from datetime import datetime, date, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "site", "public", "data")
CONFIG_DIR = os.path.join(HERE, "config")
LOG_DIR = os.path.join(HERE, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


class _Log:
    """Tiny logger that prints and appends to a dated logfile (committed to repo so silent failures are visible)."""

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

def http_get_json(url, params=None, retries=3, backoff=2.0, timeout=30):
    """GET JSON with exponential backoff. Returns parsed JSON or None on failure."""
    try:
        import requests
    except ImportError:
        LOG.error("requests not installed. pip install -r requirements.txt")
        return None

    headers = {"User-Agent": "PolitiTrade/1.0 (personal research dashboard)"}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
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


def save_json(name, obj, to_config=False):
    base = CONFIG_DIR if to_config else DATA_DIR
    path = os.path.join(base, name)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


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
