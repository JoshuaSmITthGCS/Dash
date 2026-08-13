"""Backfill point-in-time fundamentals from SEC EDGAR XBRL (Phase 2.2). Runnable job.

    python pipeline/build_pit_fundamentals.py --limit 25          # a first, cheap pass
    python pipeline/build_pit_fundamentals.py                     # the whole universe
    python pipeline/build_pit_fundamentals.py --audit-only        # resolve tickers, fetch nothing
    python pipeline/build_pit_fundamentals.py --since 2015-01-01  # bound the history

Requires ``SEC_USER_AGENT`` (SEC fair-access policy requires a declaring User-Agent with a
contact address, e.g. ``ValueSignal research you@example.com``). Pacing is the process-wide
9/s token bucket; the client backs off on 403/429.

**Why this job exists.** Every fundamental in this repository today comes from a provider
that serves *restated* figures with no as-reported history, keyed by ticker. Two independent
contaminations follow, and neither can be fixed after the fact: look-ahead, because a
restated figure was not what anybody saw at the time; and survivorship, because today's
universe silently excludes everything that failed. This job reconstructs the first one from
the source of record -- each XBRL fact carries the date its filing was accepted -- and writes
it keyed by CIK. See ``research/audit/CURRENT_MODEL_AUDIT.md`` section 1 (C-3).

**What it writes.** ``pipeline/data/pit/fundamentals.jsonl``, append-only, one JSON object per
(company, concept, period, filing). Re-running is safe: existing (cik, concept, period,
accession) keys are skipped, so an interrupted run resumes and a scheduled run only adds new
filings. A companion ``fundamentals_manifest.json`` records coverage per company.

**What it deliberately does not do.** It does not derive ratios, score anything, or feed the
live pipeline. It accumulates the substrate Phases 4-10 need. Deriving point-in-time ratios
from these observations is the next step and is intentionally separate: the raw facts should
be written once and re-derived from as often as the derivation changes.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import LOG, STORE_DIR, load_json
from edgar_entities import EntityResolver
from edgar_facts import CONCEPT_TAGS, company_observations, restatements
from pit_fundamentals_store import ShardedStore, dedupe
from sec_edgar import SecEdgarClient

PIT_DIR = os.path.join(STORE_DIR, "pit")
# Sharded by CIK. One 2.2 GB file would exceed GitHub's 100 MB per-file limit at
# full-universe scale and weigh on every clone forever; see pit_fundamentals_store.
FUNDAMENTALS_DIR = os.path.join(PIT_DIR, "fundamentals")
LEGACY_FUNDAMENTALS = os.path.join(PIT_DIR, "fundamentals.jsonl")
MANIFEST = os.path.join(PIT_DIR, "fundamentals_manifest.json")
# Separate file so an audit-only run and a later backfill do not overwrite each other's
# report. The entity audit is the thing to read before trusting any fetched history, so it
# has to survive the run that comes after it.
ENTITY_AUDIT = os.path.join(PIT_DIR, "entity_audit.json")
RESTATEMENTS = os.path.join(PIT_DIR, "fundamental_restatements.jsonl")


def observation_key(row):
    """Identity of one filed fact. An amendment is a different key, not an overwrite."""
    return (row.get("cik"), row.get("concept"), row.get("period_start"),
            row.get("period_end"), row.get("unit"), row.get("accession"))


def store():
    # Resolved at call time, not bound at import, so a test can redirect the directory.
    return ShardedStore(FUNDAMENTALS_DIR)


def existing_keys():
    return store().keys()


def append_rows(path, rows):
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return len(rows)


def classify_unresolved(unresolved, published_rows):
    """Sort unresolvable tickers into the three cases that need different responses.

    A single bucket of 49 failures hides the one that matters. Against the first real run:
    3 were ETFs, 45 were configured tickers that no longer appear in published data at all,
    and 1 was a company being scored live with no CIK -- and only that last case is a
    problem to investigate.

      ``fund``            An ETF or trust. Funds do not file operating-company financials, so
                          having no CIK here is correct and expected, not a gap.
      ``absent_from_data`` Configured in the universe but not in the published payload
                          either. Almost always an acquisition that closed or a ticker that
                          was reassigned -- the universe file is stale. These are also the
                          survivorship-bias names: still listed in config, no longer trading.
      ``scored_but_unresolved`` Being scored and published right now with no CIK behind it.
                          The only category that needs a person to look.
    """
    published = {row.get("ticker"): row for row in published_rows or [] if row.get("ticker")}
    buckets = {"fund": [], "absent_from_data": [], "scored_but_unresolved": []}
    for ticker in sorted(unresolved):
        row = published.get(ticker)
        if row is None:
            buckets["absent_from_data"].append(ticker)
        elif row.get("is_etf") or row.get("sector") == "ETF":
            buckets["fund"].append(ticker)
        else:
            buckets["scored_but_unresolved"].append(
                {"ticker": ticker, "published_name": row.get("name"),
                 "sector": row.get("sector"), "score": row.get("score")})
    return buckets


def published_rows():
    payload = load_json("advisor.json") or {}
    return [*payload.get("research", []), *payload.get("screen_universe", []),
            *payload.get("portfolio_coverage", [])]


def migrate_legacy_store():
    """Fold a single-file store into the sharded, deduplicated layout. One-way, idempotent."""
    if not os.path.exists(LEGACY_FUNDAMENTALS):
        return 0, 0
    rows = []
    with open(LEGACY_FUNDAMENTALS, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("filed") and row.get("period_end") and row["filed"] < row["period_end"]:
                    continue
                rows.append(row)
    written = store().write(rows)
    os.remove(LEGACY_FUNDAMENTALS)
    return len(rows), written


def repair_store(path=None):
    """Re-deduplicate and rewrite every shard through the current parser.

    Derived fields are recomputed on read (``pit_fundamentals_store.expand``), so a parser
    fix needs no re-fetch. Returns ``(kept, reclassified, dropped)`` where ``reclassified``
    counts rows whose stored identity changed and ``dropped`` counts impossible filing dates.
    """
    current = store()
    kept = dropped = 0
    for name in current.shards():
        shard = name.removeprefix("fundamentals-").removesuffix(".jsonl")
        rows = current.load_compact(shard)
        usable = [row for row in rows
                  if not (row.get("filed") and row.get("period_end")
                          and row["filed"] < row["period_end"])]
        dropped += len(rows) - len(usable)
        merged = dedupe(usable)
        temporary = f"{current.path(shard)}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            for row in merged:
                handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        os.replace(temporary, current.path(shard))
        kept += len(merged)
    reclassified = 0
    # A store the manifest no longer describes is the same defect one layer up, so record
    # the repair rather than leaving the counts stale.
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["observations_total"] = kept
        manifest["store"] = current.stats()
        manifest.setdefault("repairs", []).append({
            "repaired_at": datetime.now(timezone.utc).isoformat(),
            "rows_kept": kept, "rows_reclassified": reclassified,
            "rows_dropped_filed_before_period_end": dropped,
        })
        _write_json(MANIFEST, manifest)
    return kept, reclassified, dropped


def universe_symbols():
    payload = load_json("advisor_universe.json", from_config=True) or {}
    return tuple(dict.fromkeys((*payload.get("symbols", ()), *payload.get("portfolio_symbols", ()))))


def collect_company(client, resolver, ticker, cik, *, since=None, concepts=None, seen=None):
    """Fetch and shape one company's facts. Returns ``(rows, summary)``.

    Network failures are returned as a summary rather than raised: a universe pass must not
    abort on one filer, and a company that failed is recorded so a rerun can target it.
    """
    requested_at = datetime.now(timezone.utc).isoformat()
    try:
        facts = client.company_facts_by_cik(cik)
    except Exception as error:  # noqa: BLE001 - provider failures are data, not crashes
        return [], {"ticker": ticker, "cik": cik, "status": "fetch_failed",
                    "reason": f"{type(error).__name__}: {error}"[:300]}
    rows, detail = company_observations(
        facts, concepts=concepts, cik=cik, ticker=ticker, requested_at=requested_at)
    if not detail["resolved_tags"]:
        # A fetch that returns no usable facts at all is not a success. The first sample run
        # reported 25/25 "ok" with zero observations, because an empty payload and a fetched
        # one were the same status. A filer that genuinely tags nothing this model asks for
        # is worth seeing too -- it means the concept map needs widening for that filer.
        return [], {"ticker": ticker, "cik": cik, "status": "no_usable_facts",
                    "entity_name": resolver.entity_name(cik) or facts.get("entityName"),
                    "fact_taxonomies": sorted((facts.get("facts") or {}).keys()),
                    "missing_concepts": detail["missing_concepts"]}
    if since:
        rows = [row for row in rows if str(row.get("period_end")) >= since]
    if seen is not None:
        rows = [row for row in rows if observation_key(row) not in seen]
    periods = sorted({row["period_end"] for row in rows})
    filings = sorted({row["filed"] for row in rows})
    return rows, {
        "ticker": ticker, "cik": cik, "status": "ok",
        "entity_name": resolver.entity_name(cik) or facts.get("entityName"),
        "new_observations": len(rows),
        "concepts_resolved": len(detail["resolved_tags"]),
        "resolved_tags": detail["resolved_tags"],
        "missing_concepts": detail["missing_concepts"],
        "earliest_period": periods[0] if periods else None,
        "latest_period": periods[-1] if periods else None,
        "earliest_filing": filings[0] if filings else None,
        "latest_filing": filings[-1] if filings else None,
    }


def run(tickers=None, *, limit=None, since=None, concepts=None, audit_only=False,
        client=None, resolver=None):
    client = client or SecEdgarClient()
    if not client.available:
        LOG.error("SEC_USER_AGENT is unset. SEC fair-access policy requires a declaring "
                  "User-Agent with a contact address, for example "
                  "'ValueSignal research you@example.com'. Nothing was fetched.")
        return 1

    symbols = tuple(tickers or universe_symbols())
    if resolver is None:
        try:
            resolver = EntityResolver.from_client(client)
        except Exception as error:  # noqa: BLE001 - a clean message beats a traceback
            LOG.error("Could not load SEC's company_tickers map "
                      f"({type(error).__name__}: {error}). Nothing was fetched. Check network "
                      "egress to www.sec.gov and that SEC_USER_AGENT names a real contact.")
            return 1
    audit = resolver.audit(symbols)
    LOG.info(f"Entity resolution: {audit['resolved']}/{audit['requested']} tickers -> CIK; "
             f"{audit['unresolved']} unresolved; {len(audit['shared_cik'])} CIKs claimed by "
             "more than one ticker (share classes)")
    if audit["ambiguous_tickers"]:
        LOG.warn("Ambiguous tickers, excluded rather than guessed: "
                 + ", ".join(audit["ambiguous_tickers"]))

    # Written on every run, not just audit-only: the resolution behind a backfill is part of
    # its provenance, and a reader needs it to interpret coverage.
    unresolved_kinds = classify_unresolved(audit["unresolved_reasons"], published_rows())
    _write_json(ENTITY_AUDIT, {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "audit_only" if audit_only else "backfill",
        "universe_size": len(symbols),
        "unresolved_kinds": unresolved_kinds,
        **audit,
    })
    needs_review = unresolved_kinds["scored_but_unresolved"]
    if needs_review:
        LOG.warn(f"{len(needs_review)} ticker(s) are scored and published with no CIK behind "
                 "them, which is the only unresolved category that needs a person: "
                 + ", ".join(row["ticker"] for row in needs_review))
    LOG.info(f"Unresolved breakdown: {len(unresolved_kinds['fund'])} funds (expected), "
             f"{len(unresolved_kinds['absent_from_data'])} absent from published data "
             f"(stale universe entries), {len(needs_review)} scored but unresolved")
    if audit_only:
        print(json.dumps({**{k: v for k, v in audit.items()
                             if k not in ("resolved_map", "unresolved_reasons")},
                          "unresolved_kinds": unresolved_kinds}, indent=2))
        return 0

    resolved = list(audit["resolved_map"].items())
    if limit:
        resolved = resolved[:limit]
    seen = existing_keys()
    LOG.info(f"Backfilling {len(resolved)} companies; {len(seen)} observations already stored")

    written = 0
    summaries = []
    restatement_rows = []
    for index, (ticker, cik) in enumerate(resolved, 1):
        rows, summary = collect_company(client, resolver, ticker, cik,
                                        since=since, concepts=concepts, seen=seen)
        summaries.append(summary)
        if summary["status"] != "ok":
            LOG.warn(f"{ticker} ({cik}): {summary['status']} "
                     f"{summary.get('reason') or summary.get('fact_taxonomies') or ''}")
            continue
        for row in rows:
            seen.add(observation_key(row))
        written += store().write(rows)
        restatement_rows.extend(
            {**entry, "cik": cik, "ticker": ticker} for entry in restatements(rows))
        if index % 25 == 0 or index == len(resolved):
            LOG.info(f"  {index}/{len(resolved)} companies, {written} new observations")
    append_rows(RESTATEMENTS, restatement_rows)

    ok = [row for row in summaries if row["status"] == "ok"]
    periods = sorted(row["earliest_period"] for row in ok if row["earliest_period"])
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "backfill",
        "companies_requested": len(resolved),
        "companies_ok": len(ok),
        "companies_failed": len(summaries) - len(ok),
        "observations_written": written,
        "observations_total": len(seen),
        "store": store().stats(),
        "restatements_found": len(restatement_rows),
        "earliest_period_end": periods[0] if periods else None,
        "concepts_requested": sorted(concepts or CONCEPT_TAGS),
        "since": since,
        "entity_audit": {k: v for k, v in audit.items() if k != "unresolved_reasons"},
        "companies": summaries,
    }
    _write_manifest(manifest)
    LOG.info(f"Wrote {written} new point-in-time observations for {len(ok)} companies "
             f"({len(restatement_rows)} restatements recorded). Store now holds {len(seen)}.")
    print(json.dumps({key: manifest[key] for key in (
        "companies_requested", "companies_ok", "companies_failed", "observations_written",
        "observations_total", "restatements_found", "earliest_period_end")}, indent=2))
    return 0


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str, sort_keys=True)
        handle.write("\n")


def _write_manifest(payload):
    _write_json(MANIFEST, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tickers", help="comma-separated tickers; defaults to the universe")
    parser.add_argument("--limit", type=int, help="stop after this many companies")
    parser.add_argument("--since", help="drop periods ending before this ISO date")
    parser.add_argument("--concepts", help="comma-separated canonical concepts to fetch")
    parser.add_argument("--audit-only", action="store_true",
                        help="resolve tickers to CIKs and report; fetch no facts")
    parser.add_argument("--repair", action="store_true",
                        help="re-deduplicate the existing store; fetch nothing")
    parser.add_argument("--migrate-legacy", action="store_true",
                        help="fold a single-file store into the sharded layout; fetch nothing")
    args = parser.parse_args(argv)
    if args.migrate_legacy:
        read, written = migrate_legacy_store()
        LOG.info(f"Migrated {read} legacy rows into the sharded store ({written} kept)")
        print(json.dumps({"legacy_rows_read": read, "stored": written,
                          **store().stats()}, indent=2, default=str))
        return 0
    if args.repair:
        kept, reclassified, dropped = repair_store()
        LOG.info(f"Repaired the store: {kept} rows kept, {reclassified} reclassified, "
                 f"{dropped} dropped as filed-before-period-end")
        print(json.dumps({"kept": kept, "reclassified": reclassified, "dropped": dropped},
                         indent=2))
        return 0
    tickers = tuple(t.strip().upper() for t in args.tickers.split(",")) if args.tickers else None
    concepts = tuple(c.strip() for c in args.concepts.split(",")) if args.concepts else None
    return run(tickers, limit=args.limit, since=args.since, concepts=concepts,
               audit_only=args.audit_only)


if __name__ == "__main__":
    raise SystemExit(main())
