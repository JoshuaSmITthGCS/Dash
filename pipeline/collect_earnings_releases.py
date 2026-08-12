"""Build the point-in-time earnings release store from Form 8-K Item 2.02.

Item 2.02 of Form 8-K is "Results of Operations and Financial Condition": the filing a US
issuer makes on the day it releases quarterly results. It is a different document from the
10-Q, arrives weeks earlier, and is therefore an anchor for post-earnings drift that does not
inherit the periodic report's lag. That independence is the whole point of this collector.

Source: the EDGAR submissions API, ``data.sec.gov/submissions/CIK##########.json``, which
lists every filing a company has made with its form type, its 8-K item codes, the item's own
report date and the EDGAR acceptance timestamp. No page scraping and no third-party provider.

Output: pipeline/data/pit/earnings_releases.jsonl, append-only, one record per 8-K. Re-running
skips accessions already on disk, so an interrupted run resumes.

    python pipeline/collect_earnings_releases.py --limit 25      # sample
    python pipeline/collect_earnings_releases.py                 # whole universe
    python pipeline/collect_earnings_releases.py --since 2015-01-01

The release datetime written is the EDGAR acceptance timestamp when present, because that is
the moment the document became public, and the 8-K item report date otherwise. Which one
answered is recorded per row so a reader can tell a minute-accurate anchor from a date-only
one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from common import LOG
from earnings_release import ANNOUNCEMENT_ANCHOR, RELEASES_PATH, parse_release_datetime
from sec_edgar import SEC_DATA, SecEdgarClient

# Item 2.02 is the results-of-operations item. EDGAR writes the items field as a
# comma-separated list of codes, sometimes with a trailing description, so this matches the
# code as a token rather than the whole field.
RESULTS_ITEM = "2.02"

# Form types that carry the item. 8-K/A is an amendment and is collected too, but the
# earliest filing for a period still wins in earnings_release.release_for_period, so an
# amendment never moves an anchor the market already reacted to.
FORMS = ("8-K", "8-K/A")


def has_results_item(items):
    """Whether an EDGAR items field declares Item 2.02."""
    text = str(items or "")
    return any(token.strip().startswith(RESULTS_ITEM) for token in text.split(","))


def recent_filings(submissions):
    """``filings.recent`` transposed from column arrays into per-filing dicts."""
    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    columns = ("accessionNumber", "form", "items", "filingDate", "reportDate",
               "acceptanceDateTime")
    length = min((len(recent.get(column) or []) for column in columns), default=0)
    rows = []
    for index in range(length):
        rows.append({column: (recent.get(column) or [])[index] for column in columns})
    return rows


def release_records(cik, submissions, *, since=None):
    """One record per Item 2.02 8-K in this company's submissions payload.

    ``period_end`` is deliberately left None. The 8-K item date is the date of the release
    event, not the fiscal period end, and inventing a period end by rounding that date would
    put a guess into a point-in-time store. earnings_release.release_for_period matches an
    undated release into the lag band after a period end instead, which is a stated heuristic
    rather than a fabricated field.
    """
    records = []
    for filing in recent_filings(submissions):
        if filing.get("form") not in FORMS or not has_results_item(filing.get("items")):
            continue
        stamp = (parse_release_datetime(filing.get("acceptanceDateTime"))
                 or parse_release_datetime(filing.get("reportDate"))
                 or parse_release_datetime(filing.get("filingDate")))
        if stamp is None:
            continue
        if since and stamp.date().isoformat() < since:
            continue
        records.append({
            "cik": str(cik).zfill(10),
            "release_datetime": stamp.isoformat(),
            "period_end": None,
            "accession": filing.get("accessionNumber"),
            "form": filing.get("form"),
            "items": filing.get("items"),
            "event_date": filing.get("reportDate"),
            "filing_date": filing.get("filingDate"),
            "precision": ("acceptance_timestamp" if filing.get("acceptanceDateTime")
                          else "event_date_only"),
            "source": ANNOUNCEMENT_ANCHOR,
        })
    return records


def existing_accessions(path):
    seen = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("accession"):
                    seen.add(row["accession"])
    except OSError:
        return seen
    return seen


def collect(client, entity_map, *, path=RELEASES_PATH, limit=None, since=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen = existing_accessions(path)
    companies = list(entity_map.items())[:limit] if limit else list(entity_map.items())
    written, failed = 0, []
    with open(path, "a", encoding="utf-8") as handle:
        for ticker, cik in companies:
            url = f"{SEC_DATA}/submissions/CIK{str(cik).zfill(10)}.json"
            try:
                submissions = client._get(url, as_json=True)  # noqa: SLF001 - same package, one rate limiter
            except Exception as error:  # noqa: BLE001 - one company is not the run
                failed.append({"ticker": ticker, "error": type(error).__name__})
                continue
            for record in release_records(cik, submissions, since=since):
                if record["accession"] in seen:
                    continue
                seen.add(record["accession"])
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                written += 1
    return {"companies_read": len(companies) - len(failed), "records_written": written,
            "failed": failed[:20], "failed_count": len(failed), "store": path}


def _entity_map(*, whole_ticker_map=False):
    """{ticker: cik} for the companies worth collecting.

    Scoped to the configured universe by default, the same list
    pipeline/build_pit_fundamentals.py backfills. The SEC ticker map carries about eight
    thousand filers and the screen scores under a thousand of them, so collecting the whole
    map spends roughly nine times the SEC's rate budget to anchor drift windows for companies
    this pipeline never ranks. ``--whole-ticker-map`` opts into that deliberately.
    """
    from edgar_sue import _ticker_to_cik  # noqa: PLC0415 - avoids a module-level import cycle

    resolved = _ticker_to_cik()
    if whole_ticker_map:
        return resolved
    from build_pit_fundamentals import universe_symbols  # noqa: PLC0415

    symbols = universe_symbols()
    scoped = {symbol: resolved[symbol.upper()] for symbol in symbols
              if resolved.get(symbol.upper())}
    return scoped or resolved


def report(entity_map, *, path=RELEASES_PATH):
    """How much of the universe the store can now anchor, without scoring anything.

    The question a scheduled run has to answer is whether the drift leg came back, and this
    answers the part of it that lives in the store: how many universe companies have at least
    one Item 2.02 release on disk, and how fresh the newest one is. It deliberately stops
    short of a coverage figure for the leg itself, because that also depends on whether each
    company's *most recent fiscal period* has a release inside the lag band, which needs the
    fundamentals store and the price cache the screen build reads.
    """
    from earnings_release import _releases_by_cik, reset_cache  # noqa: PLC0415

    reset_cache()
    by_cik = _releases_by_cik(path)
    universe = {str(cik).zfill(10) for cik in entity_map.values()}
    covered = universe & set(by_cik)
    records = [record for cik in covered for record in by_cik[cik]]
    latest = max((record["release_date"] for record in records), default=None)
    per_company = sorted(len(by_cik[cik]) for cik in covered)
    return {
        "universe_companies": len(universe),
        "companies_with_a_release": len(covered),
        "company_coverage": round(len(covered) / len(universe), 4) if universe else None,
        "total_releases": len(records),
        "median_releases_per_company": per_company[len(per_company) // 2] if per_company else 0,
        "most_recent_release": latest,
        "store": path,
        "note": ("Company coverage is not leg coverage. The drift leg also needs the "
                 "company's most recent fiscal period to have a release inside the lag band, "
                 "which the screen build reports as pead_anchor_diagnostic."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="only read the first N companies, for a sample run")
    parser.add_argument("--since", default=None,
                        help="drop releases before this ISO date")
    parser.add_argument("--out", default=RELEASES_PATH)
    parser.add_argument("--report", action="store_true",
                        help="print what the store already covers and fetch nothing")
    parser.add_argument("--whole-ticker-map", action="store_true",
                        help="collect every filer in the SEC ticker map, not just the "
                             "configured universe")
    args = parser.parse_args(argv)

    entity_map = _entity_map(whole_ticker_map=args.whole_ticker_map)
    if not entity_map:
        LOG.warn("No EDGAR entity map on disk, nothing to collect")
        return 1
    if args.report:
        print(json.dumps(report(entity_map, path=args.out), indent=2))
        return 0
    summary = collect(SecEdgarClient(), entity_map, path=args.out, limit=args.limit,
                      since=args.since)
    summary["coverage"] = report(entity_map, path=args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
