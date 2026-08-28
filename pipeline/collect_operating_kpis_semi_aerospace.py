"""Collect book-to-bill ratio from earnings-release exhibits for semiconductor and
aerospace/defense names.

Standalone and opt-in, run separately from ``pipeline/fetch_advisor.py`` -- the same pattern
``pipeline/collect_operating_kpis.py`` (comparable-sales growth) already uses for a data source
that should not silently become part of the scheduled refresh's hot path before it has been
checked.

Source: reuses the accessions ``pipeline/collect_earnings_releases.py`` has already found (one
Item 2.02 8-K per quarterly release, in ``pipeline/data/pit/earnings_releases.jsonl``) and fetches
each one's Exhibit 99.x text (``pipeline/filing_text.py``), then runs
``pipeline/operating_kpis_semi_aerospace.extract_book_to_bill_ratio`` against it. No new filing
discovery.

Scope: ``pipeline/config/operating_kpi_universe_semi_aerospace.json``'s symbol list, not the
whole universe -- see that file's own comment for why, and for which sub-group (semiconductor
capital equipment) is actually expected to disclose this ratio.

Output: ``pipeline/data/pit/operating_kpis_semi_aerospace.jsonl``, append-only, one record per
(ticker, accession) actually resolved. Re-running skips accessions already on disk.

    python pipeline/collect_operating_kpis_semi_aerospace.py --limit 5      # sample
    python pipeline/collect_operating_kpis_semi_aerospace.py                # whole configured list
    python pipeline/collect_operating_kpis_semi_aerospace.py --report        # coverage of what's
                                                                              # on disk, fetch nothing

IMPORTANT: this collector, and the extraction pattern it runs, have not been validated against
a broad, live sample of real filings -- see pipeline/filing_text.py's module docstring and
docs/LIMITATIONS.md. Run with ``--report`` after a run with real SEC EDGAR access and read the
coverage numbers before treating this store as a scoring input. Expect the match rate to be
concentrated in the semiconductor-capital-equipment names (AMAT, ENTG, KLAC, LRCX, ONTO, TER,
VECO) -- a low overall rate driven by fabless chipmakers and aerospace primes not using this
phrasing is the expected result, not a sign the pattern is broken.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from common import LOG, load_json
from earnings_release import RELEASES_PATH, _releases_by_cik, reset_cache
from filing_text import earnings_release_text
from operating_kpis_semi_aerospace import extract_book_to_bill_ratio
from sec_edgar import SecEdgarClient

HERE = os.path.dirname(os.path.abspath(__file__))
KPI_STORE_PATH = os.path.join(HERE, "data", "pit", "operating_kpis_semi_aerospace.jsonl")

# Sub-industry grouping for the coverage report only -- not part of the config file's shape, and
# not used for anything beyond making the report's status breakdown interpretable (see this
# module's docstring, and the config file's comment, for why match rate should be expected to
# concentrate here).
_SEMICAP_EQUIPMENT = frozenset({"AMAT", "ENTG", "KLAC", "LRCX", "ONTO", "TER", "VECO"})
_AEROSPACE_DEFENSE = frozenset({
    "AXON", "BA", "CW", "GD", "GE", "HEI", "HII", "HWM", "HXL", "LHX", "LMT",
    "MRCY", "NOC", "RKLB", "RTX", "TDG", "WWD",
})


def _industry_group(ticker):
    if ticker in _SEMICAP_EQUIPMENT:
        return "semicap_equipment"
    if ticker in _AEROSPACE_DEFENSE:
        return "aerospace_defense"
    return "semiconductor"


def _configured_symbols():
    config = load_json("operating_kpi_universe_semi_aerospace.json", from_config=True) or {}
    symbols = list(config.get("semi_aerospace_symbols") or ())
    return {symbol: _industry_group(symbol) for symbol in symbols}


def _existing_keys(path):
    seen = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ticker") and row.get("accession"):
                    seen.add((row["ticker"], row["accession"]))
    except OSError:
        return seen
    return seen


def collect(client, symbols_and_industry, *, path=KPI_STORE_PATH, releases_path=RELEASES_PATH,
           limit=None, releases_per_symbol=1):
    """Fetch and extract for each configured symbol's most recent release(s).

    ``releases_per_symbol`` caps how many of a company's most recent Item 2.02 filings are
    read -- more than one lets a coverage report distinguish "this company has never disclosed
    book-to-bill in the phrasing this looks for" from "the one release we tried happened not to
    match", without multiplying the SEC request budget by the whole release history.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    reset_cache()
    by_cik = _releases_by_cik(releases_path)
    ticker_to_cik = _resolve_ciks(symbols_and_industry)
    seen = _existing_keys(path)
    items = list(symbols_and_industry.items())[:limit] if limit else list(symbols_and_industry.items())

    written, matched, attempted, failed = 0, 0, 0, []
    with open(path, "a", encoding="utf-8") as handle:
        for ticker, industry_group in items:
            cik = ticker_to_cik.get(ticker)
            if not cik:
                failed.append({"ticker": ticker, "error": "no_cik"})
                continue
            releases = list(reversed(by_cik.get(cik, [])))[:releases_per_symbol]
            if not releases:
                failed.append({"ticker": ticker, "error": "no_releases_on_disk"})
                continue
            for release in releases:
                key = (ticker, release["accession"])
                if key in seen:
                    continue
                seen.add(key)
                attempted += 1
                text = earnings_release_text(client, cik, release["accession"])
                if text is None:
                    record = {"ticker": ticker, "cik": cik, "industry_group": industry_group,
                              "accession": release["accession"], "release_date": release["release_date"],
                              "book_to_bill_ratio": None, "status": "exhibit_unavailable"}
                else:
                    value, detail = extract_book_to_bill_ratio(text)
                    record = {"ticker": ticker, "cik": cik, "industry_group": industry_group,
                              "accession": release["accession"], "release_date": release["release_date"],
                              "book_to_bill_ratio": value, "status": detail["status"],
                              "detail": detail}
                    if value is not None:
                        matched += 1
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                written += 1
    return {"symbols_configured": len(items), "releases_attempted": attempted,
            "records_written": written, "matched": matched, "failed": failed[:20],
            "failed_count": len(failed), "store": path}


def _resolve_ciks(symbols_and_industry):
    from edgar_sue import _ticker_to_cik  # noqa: PLC0415 - avoids a module-level import cycle

    resolved = _ticker_to_cik()
    return {ticker: resolved.get(ticker.upper()) for ticker in symbols_and_industry
           if resolved.get(ticker.upper())}


def report(path=KPI_STORE_PATH):
    """Coverage of what's on disk -- how much of the configured universe resolved a value,
    and the breakdown of why the rest did not, without fetching anything new.
    """
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        rows = []
    configured = _configured_symbols()
    tickers_with_a_row = {row["ticker"] for row in rows}
    matched_tickers = {row["ticker"] for row in rows if row.get("book_to_bill_ratio") is not None}
    status_counts = {}
    for row in rows:
        status_counts[row.get("status", "unknown")] = status_counts.get(row.get("status", "unknown"), 0) + 1
    return {
        "symbols_configured": len(configured),
        "symbols_with_any_attempt": len(tickers_with_a_row),
        "symbols_matched": len(matched_tickers),
        "match_rate_of_attempted": (round(len(matched_tickers) / len(tickers_with_a_row), 4)
                                    if tickers_with_a_row else None),
        "status_breakdown": status_counts,
        "store": path,
        "note": ("Coverage of ATTEMPTED symbols only, not the full configured list, until "
                 "`collect` has been run for all of them. See this module's docstring: this "
                 "extraction has not been validated against a broad, live filing sample, and a "
                 "low match rate outside semiconductor-capital-equipment names is expected, not "
                 "a bug."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="only process the first N configured symbols, for a sample run")
    parser.add_argument("--out", default=KPI_STORE_PATH)
    parser.add_argument("--releases-per-symbol", type=int, default=1,
                        help="how many of each company's most recent Item 2.02 releases to try")
    parser.add_argument("--report", action="store_true",
                        help="print coverage of what's already on disk and fetch nothing")
    args = parser.parse_args(argv)

    if args.report:
        print(json.dumps(report(args.out), indent=2))
        return 0

    symbols = _configured_symbols()
    if not symbols:
        LOG.warn("No symbols configured in operating_kpi_universe_semi_aerospace.json, nothing to collect")
        return 1
    summary = collect(SecEdgarClient(), symbols, path=args.out, limit=args.limit,
                      releases_per_symbol=args.releases_per_symbol)
    summary["coverage"] = report(args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
