"""Collect AUM and net-flows disclosures from earnings-release exhibits for asset managers and
broker-dealers.

Standalone and opt-in, run separately from ``pipeline/fetch_advisor.py`` -- the same pattern
``pipeline/collect_operating_kpis.py`` (its comps/same-store-sales sibling) already uses for a
data source that should not silently become part of the scheduled refresh's hot path before it
has been checked.

Source: reuses the accessions ``pipeline/collect_earnings_releases.py`` has already found (one
Item 2.02 8-K per quarterly release, in ``pipeline/data/pit/earnings_releases.jsonl``) and fetches
each one's Exhibit 99.x text (``pipeline/filing_text.py``), then runs both
``pipeline/operating_kpis_asset_manager.extract_assets_under_management`` and
``.extract_net_flows`` against it. No new filing discovery, one earnings-release fetch per
release covers both metrics.

Scope: ``pipeline/config/operating_kpi_universe_asset_manager.json``'s asset-manager symbol
list, not the whole universe -- see that file's own comment for why, and for which symbols are
broker-dealers or a trading venue rather than a pure asset manager (expected to legitimately
come back "not_found" for one or both metrics).

Output: ``pipeline/data/pit/operating_kpis_asset_manager.jsonl``, append-only, one record per
(ticker, accession) actually resolved. Re-running skips accessions already on disk.

    python pipeline/collect_operating_kpis_asset_manager.py --limit 5      # sample
    python pipeline/collect_operating_kpis_asset_manager.py                # whole configured list
    python pipeline/collect_operating_kpis_asset_manager.py --report        # coverage of what's on disk, fetch nothing

IMPORTANT: this collector, and the extraction patterns it runs, have not been validated against
a broad, live sample of real filings -- see pipeline/filing_text.py's module docstring,
pipeline/operating_kpis_asset_manager.py's module docstring, and docs/LIMITATIONS.md. Run with
``--report`` after a run with real SEC EDGAR access and read the coverage numbers before
treating this store as a scoring input.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from common import LOG, load_json
from earnings_release import RELEASES_PATH, _releases_by_cik, reset_cache
from filing_text import earnings_release_text
from operating_kpis_asset_manager import extract_assets_under_management, extract_net_flows
from sec_edgar import SecEdgarClient

HERE = os.path.dirname(os.path.abspath(__file__))
KPI_STORE_PATH = os.path.join(HERE, "data", "pit", "operating_kpis_asset_manager.jsonl")


def _configured_symbols():
    config = load_json("operating_kpi_universe_asset_manager.json", from_config=True) or {}
    asset_managers = list(config.get("asset_manager_symbols") or ())
    return {symbol: "asset_manager" for symbol in asset_managers}


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
    AUM/flows in the phrasing this looks for" from "the one release we tried happened not to
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
                              "assets_under_management": None, "net_flows": None,
                              "status": "exhibit_unavailable"}
                else:
                    aum_value, aum_detail = extract_assets_under_management(text)
                    flows_value, flows_detail = extract_net_flows(text)
                    status = (
                        "matched" if (aum_value is not None or flows_value is not None)
                        else "not_found"
                    )
                    record = {"ticker": ticker, "cik": cik, "industry_group": industry_group,
                              "accession": release["accession"], "release_date": release["release_date"],
                              "assets_under_management": aum_value, "net_flows": flows_value,
                              "status": status,
                              "detail": {"assets_under_management": aum_detail, "net_flows": flows_detail}}
                    if aum_value is not None or flows_value is not None:
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
    """Coverage of what's on disk -- how much of the configured universe resolved a value for
    either metric, and the breakdown of why the rest did not, without fetching anything new.
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
    aum_matched_tickers = {row["ticker"] for row in rows if row.get("assets_under_management") is not None}
    flows_matched_tickers = {row["ticker"] for row in rows if row.get("net_flows") is not None}
    status_counts = {}
    for row in rows:
        status_counts[row.get("status", "unknown")] = status_counts.get(row.get("status", "unknown"), 0) + 1
    return {
        "symbols_configured": len(configured),
        "symbols_with_any_attempt": len(tickers_with_a_row),
        "symbols_matched_aum": len(aum_matched_tickers),
        "symbols_matched_net_flows": len(flows_matched_tickers),
        "aum_match_rate_of_attempted": (round(len(aum_matched_tickers) / len(tickers_with_a_row), 4)
                                        if tickers_with_a_row else None),
        "net_flows_match_rate_of_attempted": (round(len(flows_matched_tickers) / len(tickers_with_a_row), 4)
                                              if tickers_with_a_row else None),
        "status_breakdown": status_counts,
        "store": path,
        "note": ("Coverage of ATTEMPTED symbols only, not the full configured list, until "
                 "`collect` has been run for all of them. Not every configured symbol is a pure "
                 "asset manager -- see pipeline/config/operating_kpi_universe_asset_manager.json's "
                 "own comment -- so a non-zero not_found rate for some tickers is expected, not "
                 "necessarily a pattern-quality problem. See this module's docstring: this "
                 "extraction has not been validated against a broad, live filing sample."),
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
        LOG.warn("No symbols configured in operating_kpi_universe_asset_manager.json, nothing to collect")
        return 1
    summary = collect(SecEdgarClient(), symbols, path=args.out, limit=args.limit,
                      releases_per_symbol=args.releases_per_symbol)
    summary["coverage"] = report(args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
