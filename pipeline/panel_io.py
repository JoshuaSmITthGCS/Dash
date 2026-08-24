"""Gzip-transparent read/write for the backtest signal panels.

The 10-year fundamentals panel with per-metric tagging (R11-P8's ``metric_scores``) is
~174MB of extremely repetitive JSON -- past GitHub's hard 100MB file limit, so it cannot be
committed raw, and an uncommitted panel means the scheduled refresh
(``refresh-advisor.yml`` -> ``signal_metrics.py``) computes the rolling-IC regime monitor
against whatever stale panel is in the tree. The same repetition that makes the file huge
makes it compress on the order of 10x, so the panel of record is committed as
``<name>.json.gz`` and every reader falls back to it transparently:

  * ``load_panel(path)``: reads ``path`` if it exists; otherwise ``path + ".gz"``; otherwise
    returns None. A fresh local rebuild (plain ``.json``) therefore always wins over the
    committed compressed copy, which is the right precedence -- newest data first.
  * ``save_panel(path, data)``: writes gzip when ``path`` ends in ``.gz``, plain JSON
    otherwise, so ``--panel-out foo.json.gz`` is all it takes to produce a committable
    panel. Compact separators either way: the panel is machine-read only, and indent was
    a third of the raw file's size.
"""

from __future__ import annotations

import gzip
import json
import os


def _opener(path):
    return gzip.open if str(path).endswith(".gz") else open


def load_panel(path):
    """The panel at ``path``, or at ``path + '.gz'``, or None if neither exists."""
    candidates = (path,) if str(path).endswith(".gz") else (path, str(path) + ".gz")
    for candidate in candidates:
        if os.path.exists(candidate):
            with _opener(candidate)(candidate, "rt", encoding="utf-8") as handle:
                return json.load(handle)
    return None


def save_panel(path, data):
    """Write ``data`` as JSON, gzipped when ``path`` ends in ``.gz``."""
    with _opener(path)(path, "wt", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))
