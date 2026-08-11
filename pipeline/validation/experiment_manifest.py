"""Immutable experiment manifests for historical validation runs.

Round 4 of the methodology audit established that nominally identical backtests produced
materially different headline statistics (alpha -2.57% vs +0.43%, turnover 64.9% vs 50.6%)
because the price/fundamentals cache is mutable state: picks diverged 55% at the first
rebalance between cache pulls taken one week apart. Every historical result is therefore a
statement about one specific cache state, and is meaningless without a fingerprint of it.

This module produces that fingerprint. Hash everything that can change a result, hash it
deterministically, and attach the manifest to every published validation artifact. Two runs
with equal manifests must produce byte-identical holdings and return streams (enforced by
pipeline/tests/test_experiment_manifest.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(HERE)
REPO = os.path.dirname(PIPELINE)


def sha256_of_json(payload) -> str:
    """Deterministic SHA-256 of any JSON-serializable payload (sorted keys, no whitespace)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_tree(root: str, suffix: str = "") -> str:
    """Order-independent digest of a directory: hash of sorted (relpath, file-digest) pairs.

    Mutating, adding, or deleting any file changes the digest. Used to fingerprint the
    price/fundamentals caches, which are exactly the mutable state that broke
    reproducibility.
    """
    entries = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if suffix and not name.endswith(suffix):
                continue
            path = os.path.join(dirpath, name)
            entries.append((os.path.relpath(path, root), sha256_of_file(path)))
    entries.sort()
    return sha256_of_json(entries)


def _git(*args) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def build_manifest(*, strategy: str, start_date: str, end_date: str,
                   normalization_mode: str, scoring_mode: str,
                   rebalance_frequency: str, universe_tickers: list[str],
                   execution_assumptions: dict, cost_model: dict,
                   price_cache_dir: str | None = None,
                   fundamentals_cache_dir: str | None = None,
                   factor_files: list[str] | None = None,
                   calendar: list[str] | None = None,
                   extra: dict | None = None) -> dict:
    """Assemble the full manifest for one historical experiment."""
    settings_path = os.path.join(PIPELINE, "config", "settings.json")
    universe_path = os.path.join(PIPELINE, "config", "universe.json")
    tickers = sorted(set(universe_tickers))
    manifest = {
        "git_commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "model_version": _read_model_version(),
        "config_hash": sha256_of_file(settings_path),
        "universe_hash": sha256_of_file(universe_path) if os.path.exists(universe_path) else None,
        "universe_size": len(tickers),
        "ticker_list_hash": sha256_of_json(tickers),
        "price_cache_hash": sha256_of_tree(price_cache_dir, ".json") if price_cache_dir else None,
        "fundamentals_cache_hash": (sha256_of_tree(fundamentals_cache_dir)
                                    if fundamentals_cache_dir else None),
        "factor_dataset_hash": (sha256_of_json([sha256_of_file(f) for f in sorted(factor_files)])
                                if factor_files else None),
        "backtest_calendar_hash": sha256_of_json(calendar) if calendar else None,
        "execution_assumptions_hash": sha256_of_json(execution_assumptions),
        "cost_model_hash": sha256_of_json(cost_model),
        "normalization_mode": normalization_mode,
        "scoring_mode": scoring_mode,
        "rebalance_frequency": rebalance_frequency,
        "strategy": strategy,
        "start_date": start_date,
        "end_date": end_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        manifest["extra"] = extra
    manifest["manifest_hash"] = sha256_of_json(
        {k: v for k, v in manifest.items() if k != "created_at"})
    return manifest


def _read_model_version() -> str:
    try:
        settings = json.load(open(os.path.join(PIPELINE, "config", "settings.json")))
        return str(settings.get("model_version", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
