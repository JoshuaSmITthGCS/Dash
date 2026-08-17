"""SEC filing tracker: 10-K/10-Q, DEF 14A, and 8-K, published as descriptive facts plus the
per-symbol detail ``advisor_engine``'s three new filing modifiers score.

Runs every 3 days (``.github/workflows/sec-filings.yml``). One EDGAR submissions fetch per
symbol covers every form type this module reads, so polling DEF 14A/8-K at that cadence costs
nothing extra for 10-K/10-Q - those simply never appear more than quarterly regardless of how
often this runs, and polling every 3 days means a late-filing notice (``NT 10-K``/``NT 10-Q``)
is caught within days rather than a full quarter later.

Mirrors ``build_congress_screen.py``'s shape: append-only point-in-time log (never
overwritten, same convention as ``pit_store.py``), a ``status``/``degraded_reason`` pair so a
broken run cannot publish as a quiet one, and pure scoring left entirely to
``edgar_filing_signals.py`` - this module only collects and classifies which filing is which.

Covers the same shortlist ``advisor.json`` already publishes (its ``research`` and
``portfolio_coverage`` rows) rather than the full ~900-name universe: SEC fair-access limits
apply per process, and a name that never made the scored shortlist has no research score for
this to modify anyway.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG, STORE_DIR, load_json, save_json
from edgar_filing_signals import (score_8k_activity, score_filing_integrity,
                                  score_proxy_activity)
from sec_edgar import SecEdgarClient

FILINGS_DIR = os.path.join(STORE_DIR, "filings")
SEEN = "seen.jsonl"

FORM_10K = ("10-K", "NT 10-K")
FORM_10Q = ("10-Q", "NT 10-Q")
FORM_PROXY = ("DEF 14A", "DEFC14A", "DEFA14A")
FORM_8K = ("8-K",)

LOOKBACK_10K = 2
LOOKBACK_10Q = 2
LOOKBACK_PROXY = 3
LOOKBACK_8K = 8


def _path():
    os.makedirs(FILINGS_DIR, exist_ok=True)
    return os.path.join(FILINGS_DIR, SEEN)


def _filing_key(symbol, row):
    return (symbol, row.get("cik"), row.get("form"), row.get("accession"))


def _read_all():
    path = _path()
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def append_new_filings(symbol, rows, *, collected_at=None):
    """Point-in-time log of every filing seen, keyed by its own accession number so a
    re-run recording the same filing again is a no-op, never a duplicate."""
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    existing_keys = {_filing_key(row.get("symbol"), row) for row in _read_all()}
    fresh = [row for row in rows if _filing_key(symbol, row) not in existing_keys]
    if not fresh:
        return 0
    with open(_path(), "a") as handle:
        for row in fresh:
            handle.write(json.dumps({**row, "symbol": symbol, "collected_at": collected_at},
                                    default=str, sort_keys=True) + "\n")
    return len(fresh)


def shortlist_symbols():
    """The same tickers already published on ``advisor.json`` - research rows plus
    portfolio holdings, the same coverage convention ``build_congress_screen.sector_by_
    ticker`` uses. A ticker outside this set has no research score here to modify."""
    payload = load_json("advisor.json") or {}
    symbols = set()
    for row in (*payload.get("research", []), *payload.get("portfolio_coverage", [])):
        ticker = row.get("ticker")
        if ticker:
            symbols.add(ticker.upper())
    return sorted(symbols)


def collect_symbol(sec, symbol):
    """One symbol's 10-K/10-Q, DEF 14A variants, and 8-K activity - four calls that share
    one cached EDGAR submissions fetch (``SecEdgarClient.submissions`` caches per CIK per
    process), so this costs one network round trip, not four."""
    filings_10k = sec.recent_forms(symbol, FORM_10K, limit=LOOKBACK_10K)
    filings_10q = sec.recent_forms(symbol, FORM_10Q, limit=LOOKBACK_10Q)
    filings_proxy = sec.recent_forms(symbol, FORM_PROXY, limit=LOOKBACK_PROXY)
    filings_8k = sec.recent_forms(symbol, FORM_8K, limit=LOOKBACK_8K)
    return filings_10k, filings_10q, filings_proxy, filings_8k


def build_result(symbol, filings_10k, filings_10q, filings_proxy, filings_8k, *, as_of):
    filing_integrity_points, filing_integrity_detail = score_filing_integrity(
        filings_10k, filings_10q, as_of=as_of)
    proxy_points, proxy_detail = score_proxy_activity(filings_proxy, as_of=as_of)
    eightk_points, eightk_detail = score_8k_activity(filings_8k, as_of=as_of)
    return {
        "ticker": symbol,
        "filing_integrity": {"score_points": filing_integrity_points, **filing_integrity_detail},
        "proxy_activity": {"score_points": proxy_points, **proxy_detail},
        "eightk_activity": {"score_points": eightk_points, **eightk_detail},
    }


def run():
    sec = SecEdgarClient()
    generated_at = datetime.now(timezone.utc)
    symbols = shortlist_symbols()
    if not sec.available or not symbols:
        LOG.warn("SEC filings screen skipped: "
                 f"{'SEC_USER_AGENT not set' if not sec.available else 'no shortlisted symbols'}")
        payload = {"schema_version": "1.0.0", "model_version": "sec-filings-v1.0.0",
                  "generated_at": generated_at.isoformat(), "status": "skipped", "results": []}
        save_json("screens/filings.json", payload)
        return payload

    results, failures, logged = [], [], 0
    for symbol in symbols:
        try:
            filings_10k, filings_10q, filings_proxy, filings_8k = collect_symbol(sec, symbol)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{symbol}: {type(exc).__name__}")
            LOG.warn(f"SEC filings: {symbol} unavailable ({type(exc).__name__})")
            continue
        all_rows = [*filings_10k, *filings_10q, *filings_proxy, *filings_8k]
        logged += append_new_filings(symbol, all_rows, collected_at=generated_at.isoformat())
        results.append(build_result(symbol, filings_10k, filings_10q, filings_proxy,
                                    filings_8k, as_of=generated_at.date()))

    status = "success" if results else "degraded"
    degraded_reason = None if results else (
        f"No symbol's filings were readable ({len(failures)} failure(s)): "
        f"{'; '.join(failures[:5]) or 'unknown'}")
    if degraded_reason:
        LOG.warn(f"SEC filings screen degraded: {degraded_reason}")

    payload = {
        "schema_version": "1.0.0",
        "model_version": "sec-filings-v1.0.0",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "degraded_reason": degraded_reason,
        "symbols_reviewed": len(results),
        "symbols_configured": len(symbols),
        "failures": failures,
        "new_filings_logged": logged,
        "disclaimer": "10-K/10-Q dates and late-filing notices (NT 10-K/NT 10-Q), DEF 14A "
                      "form variant (contested DEFC14A / soliciting-material DEFA14A), and "
                      "8-K Item-code materiality, classified from SEC EDGAR form codes alone "
                      "- never parsed from filing text. Coverage is limited to the currently "
                      "scored shortlist, not the full universe.",
        "results": results,
    }
    save_json("screens/filings.json", payload)
    LOG.info(f"SEC filings screen: {len(results)}/{len(symbols)} symbol(s) reviewed, "
             f"{logged} new filing(s) logged, {len(failures)} failure(s)")
    return payload


if __name__ == "__main__":
    run()
