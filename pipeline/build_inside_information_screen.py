"""Combined "Inside Information" screen: institutional 13F + Congressional trading, merged
and filtered down to what's rare or clearly matters.

No new ranking logic - ``political_institutional.rank_disclosed_trades`` already merges the
two "somebody who might know something already bought this" sources into one per-ticker
ranked list with each source's contribution kept separate. Until now that function was only
used internally, to rank a shadow-portfolio backtest
(``pipeline/backtest_political_institutional.py``); this module is the first thing that
*publishes* it for the UI.

Publishing the full ranked list would just be two existing screens concatenated - not what
was asked for. This module adds exactly one thing on top: a notability filter, applied to
flags the two upstream screens already computed (``build_institutional_screen.flag_for`` and
``build_congress_screen.classify``), never a new "what counts as notable" judgment invented
here. A row survives only if:

  * its 13F side carries ``CLUSTER_ACCUMULATION``/``CLUSTER_DISTRIBUTION`` (several curated
    active managers moved together, not just one), or
  * its Congress side carries ``EXTRAORDINARY_BUY``, ``CLUSTER_TRADE``, or ``BUY_SELL_FLIP``
    on any trade in the published 120-day window.

Runs every 3 days (``.github/workflows/inside-information.yml``), reading only the two
screens' last publish - no network calls of its own.
"""

from datetime import datetime, timezone

from build_filings_screen import shortlist_symbols
from common import LOG, load_json, save_json
from political_institutional import rank_disclosed_trades

NOTABLE_INSTITUTIONAL_FLAGS = {"CLUSTER_ACCUMULATION", "CLUSTER_DISTRIBUTION"}
NOTABLE_CONGRESS_FLAGS = {"EXTRAORDINARY_BUY", "CLUSTER_TRADE", "BUY_SELL_FLIP"}


def congress_flags_by_ticker(congress_rows):
    """Every notable flag seen on any of a ticker's rows in the published congress window -
    a ticker can be notable because of one representative's cluster-trade even if most of
    its other disclosed trades carry no flag at all."""
    by_ticker = {}
    for row in congress_rows or []:
        ticker = str(row.get("symbol") or "").upper()
        if not ticker:
            continue
        flags = set(row.get("flags") or []) & NOTABLE_CONGRESS_FLAGS
        if flags:
            by_ticker.setdefault(ticker, set()).update(flags)
    return by_ticker


def filter_notable(ranked, congress_flags):
    """Keep only rows a cluster of managers or a flagged Congressional trade actually
    moved - see the module docstring for exactly which upstream flags qualify."""
    notable = []
    for row in ranked:
        ticker = row["ticker"]
        institutional_notable = row.get("institutional_flag") in NOTABLE_INSTITUTIONAL_FLAGS
        matched_congress_flags = sorted(congress_flags.get(ticker) or ())
        if not institutional_notable and not matched_congress_flags:
            continue
        notable.append({**row, "congress_flags": matched_congress_flags})
    return notable


def run():
    generated_at = datetime.now(timezone.utc)
    congress_payload = load_json("screens/congress-trades.json") or {}
    institutional_payload = load_json("screens/institutional-13f.json") or {}
    congress_rows = congress_payload.get("results") or []
    institutional_rows = institutional_payload.get("results") or []

    if not congress_rows and not institutional_rows:
        LOG.warn("Inside Information screen skipped: neither the congress nor the "
                 "institutional 13F screen has published results yet")
        payload = {"schema_version": "1.0.0", "model_version": "inside-information-v1.0.0",
                  "generated_at": generated_at.isoformat(), "status": "skipped", "results": [],
                  "by_ticker": {}}
        save_json("screens/inside-information.json", payload)
        return payload

    universe = shortlist_symbols()
    ranked = rank_disclosed_trades(congress_rows, institutional_rows, as_of=generated_at.date(),
                                   universe=universe or None)
    notable = filter_notable(ranked, congress_flags_by_ticker(congress_rows))
    by_ticker = {row["ticker"]: row for row in notable}

    status = "success" if (congress_rows or institutional_rows) else "unavailable"
    payload = {
        "schema_version": "1.0.0",
        "model_version": "inside-information-v1.0.0",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "sources": {
            "congress": {"generated_at": congress_payload.get("generated_at"),
                        "status": congress_payload.get("status")},
            "institutional_13f": {"generated_at": institutional_payload.get("generated_at"),
                                  "status": institutional_payload.get("status")},
        },
        "ranked_count": len(ranked),
        "notable_count": len(notable),
        "disclaimer": "Congressional STOCK Act disclosures and curated active-manager "
                      "Schedule 13F filings, merged and shown only where the underlying "
                      "screen already flagged the activity as a cluster (3+ managers "
                      "moving together, 3+ representatives in a 14-day span, a same-name "
                      "buy/sell round trip, or a representative's first-ever disclosed "
                      "trade in a small, unfamiliar company). Not a claim that any of this "
                      "activity was informed or improper - see the congress-trades and "
                      "institutional-13f screens for the full, unfiltered disclosures.",
        "results": notable,
        "by_ticker": by_ticker,
    }
    save_json("screens/inside-information.json", payload)
    LOG.info(f"Inside Information screen: {len(notable)}/{len(ranked)} ranked ticker(s) "
             "notable")
    return payload


if __name__ == "__main__":
    run()
