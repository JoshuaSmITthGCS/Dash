"""Sharded, deduplicated storage for point-in-time fundamentals.

A 25-company sample produced 89,434 observations in 64.5 MB. The full universe projects to
3.08M rows and **2.2 GB** in one file -- past GitHub's 100 MB hard limit per file, and a
permanent weight on every clone of a repository that also serves a website. Two lossless
reductions and one layout change fix that without giving up a single fact that matters.

**Deduplication to what is actually knowable.** 50.8% of the sample was redundant. A 10-K
repeats the prior two years as comparatives, so the same value for the same period arrives
again under a later filing date. For the only question this store exists to answer -- what
could have been known on a given date -- a repeat of a value already filed adds nothing. What
matters is the *first* filing of each (company, concept, period), and any *later* filing whose
value differs. The second case is a restatement, and it is preserved exactly. Dropping
unchanged repeats loses no answer to any point-in-time or restatement question.

**Constants belong in the header, not on every row.** ``source``, ``source_taxonomy``,
``transformation``, ``reliability_tier``, ``split_adjusted`` and ``point_in_time`` were
identical on all 89,434 rows and cost more bytes than the values did. ``requested_at`` and
``observed_at`` duplicated ``filed``. ``ticker`` is a lookup from ``cik``. ``period_type`` and
``period_days`` are functions of the two period dates. ``source_field`` -- the XBRL tag that
satisfied a concept -- is constant per (company, concept) and moves to the manifest, where a
reader can still see exactly which tag every series came through.

**Sharding by CIK.** One file per CIK suffix bucket keeps every file small, spreads companies
evenly regardless of sector or alphabet, and means re-fetching one company rewrites one shard
instead of a 2 GB file.

The reader (`load`) rehydrates the dropped fields, so consumers see the same full record the
unsharded store produced. Nothing downstream needs to know this file exists.
"""

import json
import os
from datetime import datetime, timezone

from edgar_facts import _period_kind

# Fields identical on every observation this pipeline writes. Stored once per shard.
CONSTANT_FIELDS = {
    "source": "sec_edgar_xbrl",
    "source_taxonomy": "us-gaap",
    "transformation": "identity",
    "split_adjusted": False,
    "reliability_tier": "regulatory_primary",
    "point_in_time": True,
}

# Written per row. Everything else is a constant, a duplicate of `filed`, or derivable.
ROW_FIELDS = ("cik", "concept", "unit", "period_start", "period_end", "filed", "value",
              "accession", "form", "fiscal_year", "fiscal_period")

# 100 shards keeps each file in the low megabytes at full-universe scale. The last two CIK
# digits distribute evenly; the first two would pile every old filer into one bucket.
SHARD_COUNT = 100


def shard_for(cik):
    return f"{int(str(cik)[-2:]) % SHARD_COUNT:02d}"


def dedupe(rows):
    """Keep the first filing of each series and every later filing that changed the value.

    A repeat of an already-filed value cannot change what was knowable on any date, and
    cannot be a restatement. Everything else is kept, including every genuine revision.
    """
    grouped = {}
    for row in rows:
        key = (row.get("cik"), row.get("concept"), row.get("period_start"),
               row.get("period_end"), row.get("unit"))
        grouped.setdefault(key, []).append(row)
    kept = []
    for series in grouped.values():
        series.sort(key=lambda row: (str(row.get("filed")), str(row.get("accession"))))
        previous = _MISSING
        for row in series:
            if row.get("value") != previous:
                kept.append(row)
                previous = row.get("value")
    kept.sort(key=lambda row: (row.get("cik") or "", row.get("concept") or "",
                               str(row.get("period_end")), str(row.get("filed"))))
    return kept


_MISSING = object()


def compact(row):
    return {field: row.get(field) for field in ROW_FIELDS if row.get(field) is not None}


def expand(row, *, tags=None, tickers=None):
    """Rehydrate a compact row into the full observation shape consumers expect."""
    period_type, period_days = _period_kind({"start": row.get("period_start"),
                                             "end": row.get("period_end")})
    cik = row.get("cik")
    form = row.get("form") or ""
    return {
        **CONSTANT_FIELDS,
        **row,
        "ticker": (tickers or {}).get(cik),
        "source_field": (tags or {}).get((cik, row.get("concept"))),
        "period_type": period_type,
        "period_days": period_days,
        "amended": form.endswith("/A"),
        "available_at": row.get("filed"),
        "observed_at": row.get("filed"),
    }


class ShardedStore:
    """Append-and-merge storage for point-in-time observations, sharded by CIK."""

    def __init__(self, directory):
        self.directory = directory

    def path(self, shard):
        return os.path.join(self.directory, f"fundamentals-{shard}.jsonl")

    def shards(self):
        if not os.path.isdir(self.directory):
            return []
        return sorted(name for name in os.listdir(self.directory)
                      if name.startswith("fundamentals-") and name.endswith(".jsonl"))

    def load(self, *, tags=None, tickers=None, shard=None):
        """Every stored observation, rehydrated. Pass ``shard`` to read one bucket."""
        names = [f"fundamentals-{shard}.jsonl"] if shard else self.shards()
        rows = []
        for name in names:
            path = os.path.join(self.directory, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(expand(json.loads(line), tags=tags, tickers=tickers))
        return rows

    def load_compact(self, shard):
        path = self.path(shard)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def keys(self):
        """Identity of every stored fact, for resumability."""
        found = set()
        for name in self.shards():
            with open(os.path.join(self.directory, name), encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    found.add((row.get("cik"), row.get("concept"), row.get("period_start"),
                               row.get("period_end"), row.get("unit"), row.get("accession")))
        return found

    def write(self, rows):
        """Merge rows into their shards, deduplicating against what is already stored.

        Merging rather than appending is what keeps a re-run idempotent: a company fetched
        twice contributes its facts once, and a restatement fetched later slots into its
        series in filing order rather than at the end of the file.
        """
        os.makedirs(self.directory, exist_ok=True)
        by_shard = {}
        for row in rows:
            by_shard.setdefault(shard_for(row["cik"]), []).append(row)
        written = 0
        for shard, incoming in by_shard.items():
            existing = self.load_compact(shard)
            merged = dedupe([*existing, *(compact(row) for row in incoming)])
            temporary = f"{self.path(shard)}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                for row in merged:
                    handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            os.replace(temporary, self.path(shard))
            written += len(merged) - len(existing)
        return written

    def stats(self):
        sizes = [os.path.getsize(os.path.join(self.directory, name)) for name in self.shards()]
        rows = sum(sum(1 for line in open(os.path.join(self.directory, name), encoding="utf-8")
                       if line.strip()) for name in self.shards())
        return {
            "shards": len(sizes),
            "observations": rows,
            "total_bytes": sum(sizes),
            "largest_shard_bytes": max(sizes) if sizes else 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
