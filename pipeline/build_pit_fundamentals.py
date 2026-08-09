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
from sec_edgar import SecEdgarClient

PIT_DIR = os.path.join(STORE_DIR, "pit")
FUNDAMENTALS = os.path.join(PIT_DIR, "fundamentals.jsonl")
MANIFEST = os.path.join(PIT_DIR, "fundamentals_manifest.json")
RESTATEMENTS = os.path.join(PIT_DIR, "fundamental_restatements.jsonl")


def observation_key(row):
    """Identity of one filed fact. An amendment is a different key, not an overwrite."""
    return (row.get("cik"), row.get("concept"), row.get("period_start"),
            row.get("period_end"), row.get("unit"), row.get("accession"))


def existing_keys(path=FUNDAMENTALS):
    keys = set()
    if not os.path.exists(path):
        return keys
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(observation_key(json.loads(line)))
            except ValueError:
                continue
    return keys


def append_rows(path, rows):
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return len(rows)


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
        facts = client.company_facts(cik)
    except Exception as error:  # noqa: BLE001 - provider failures are data, not crashes
        return [], {"ticker": ticker, "cik": cik, "status": "fetch_failed",
                    "reason": f"{type(error).__name__}: {error}"[:300]}
    rows, detail = company_observations(
        facts, concepts=concepts, cik=cik, ticker=ticker, requested_at=requested_at)
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

    if audit_only:
        _write_manifest({"generated_at": datetime.now(timezone.utc).isoformat(),
                         "mode": "audit_only", "entity_audit": audit})
        print(json.dumps({k: v for k, v in audit.items()
                          if k not in ("resolved_map", "unresolved_reasons")}, indent=2))
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
            LOG.warn(f"{ticker} ({cik}): {summary['reason']}")
            continue
        for row in rows:
            seen.add(observation_key(row))
        written += append_rows(FUNDAMENTALS, rows)
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


def _write_manifest(payload):
    os.makedirs(PIT_DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tickers", help="comma-separated tickers; defaults to the universe")
    parser.add_argument("--limit", type=int, help="stop after this many companies")
    parser.add_argument("--since", help="drop periods ending before this ISO date")
    parser.add_argument("--concepts", help="comma-separated canonical concepts to fetch")
    parser.add_argument("--audit-only", action="store_true",
                        help="resolve tickers to CIKs and report; fetch no facts")
    args = parser.parse_args(argv)
    tickers = tuple(t.strip().upper() for t in args.tickers.split(",")) if args.tickers else None
    concepts = tuple(c.strip() for c in args.concepts.split(",")) if args.concepts else None
    return run(tickers, limit=args.limit, since=args.since, concepts=concepts,
               audit_only=args.audit_only)


if __name__ == "__main__":
    raise SystemExit(main())
