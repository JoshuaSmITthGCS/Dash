"""Quarterly 13F institutional accumulation/distribution screen.

Pulled out of the main research score entirely - it used to be a score modifier and no
longer is, for two reasons surfaced by review rather than found independently:

  * **Sampling bias, not just coverage.** There is no per-company "who holds this ticker"
    EDGAR endpoint, only per-manager filings, so covering the full 13F universe needs
    SEC's bulk quarterly data sets. The workaround - reading a curated list of *publicly
    traded* managers' own filings - is not a random subset of institutional flow: it
    oversamples the largest passive indexers (BlackRock, State Street, Invesco), whose
    position changes are close to mechanically determined by index membership and fund
    flows, not conviction. Feeding that into a score that already carries valuation and
    sector-percentile inputs would partly reintroduce market-cap/size as a second, hidden
    input under a "smart money" label. Default coverage here is ``style: active`` managers
    only - see ``pipeline/config/institutional_managers.json`` for the classification and
    why "alternative" (private-equity) managers are excluded from that sleeve too.
  * **A published fact, not a scored claim.** This module reports what happened -
    curated managers adding or cutting a position - the same way
    ``build_congress_screen.py`` reports STOCK Act disclosures: descriptive flags with an
    explicit disclaimer, never blended into a composite score. Following that precedent
    is also what point-in-time correctness demands here: a 13F position is disclosed up
    to 45 days after quarter-end, so it is always stale relative to "today" by
    construction. A screen that timestamps every entry with the *filing* date (not the
    quarter-end the filing describes) makes that lag visible instead of silently implying
    the position was known as of the period it covers.

Runs on its own schedule (13F data is inherently quarterly; there is nothing to gain from
polling more often than that changes), append-only point-in-time store under
``pipeline/data/institutional_13f/``, same convention as ``pit_store.py`` and
``build_congress_screen.py``.
"""

import json
import os
from datetime import datetime, timezone

from common import LOG, STORE_DIR, load_json, save_json
from institutional_ownership import (aggregate_by_cusip, holdings_change,
                                     parse_13f_info_table, score_institutional_ownership)
from openfigi_client import OpenFigiClient
from sec_edgar import SecEdgarClient

INSTITUTIONAL_DIR = os.path.join(STORE_DIR, "institutional_13f")
POSITIONS = "positions.jsonl"
MANAGERS_CONFIG = load_json("institutional_managers.json", from_config=True) or {}
UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}


def active_managers(config=None):
    """Publicly traded, actively managed curated filers - the default sleeve.

    Excludes ``passive`` (index/ETF-dominated AUM - position changes there track index
    membership, not conviction) and ``alternative`` (private-equity stakes are typically
    residual take-private holdings, lumpy and idiosyncratic) by design.
    """
    managers = (config or MANAGERS_CONFIG).get("managers", [])
    return [manager for manager in managers if manager.get("style") == "active"]


def _path():
    os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
    return os.path.join(INSTITUTIONAL_DIR, POSITIONS)


def _position_key(row):
    return (row.get("manager"), row.get("cusip"), row.get("filed"))


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


def append_new_positions(rows, *, collected_at=None):
    """Append point-in-time holdings not already recorded, keyed by (manager, cusip, filed).

    ``filed`` - not the quarter-end the filing describes - is the point-in-time anchor.
    Nothing here should ever be re-timestamped by period-end; a later reader asking "what
    did we know on date X" needs the date this became public, not the date it describes.
    """
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    existing_keys = {_position_key(row) for row in _read_all()}
    fresh = [row for row in rows if _position_key(row) not in existing_keys]
    if not fresh:
        return 0
    with open(_path(), "a") as handle:
        for row in fresh:
            handle.write(json.dumps({**row, "collected_at": collected_at}, default=str,
                                    sort_keys=True) + "\n")
    return len(fresh)


def manager_quarters(sec, manager):
    """A curated manager's two most recent 13F-HR information tables, newest first."""
    ticker = manager["ticker"]
    filings = sec.recent_forms(ticker, ("13F-HR", "13F-HR/A"), limit=2)
    quarters = []
    for filing in filings:
        try:
            text = sec.filing_document(filing["cik"], filing["accession"], filing["document"])
            holdings = parse_13f_info_table(text, ticker)
            unreadable = False
        except Exception:  # noqa: BLE001
            holdings, unreadable = [], True
        quarters.append({"filed": filing["filed"], "holdings": holdings, "unreadable": unreadable})
    return quarters


def flag_for(points):
    """A descriptive label, not a score point - this screen reports facts, not a number
    meant to be added to anything."""
    if points >= 1.5:
        return "CLUSTER_ACCUMULATION"
    if points > 0:
        return "ACCUMULATION"
    if points <= -1.5:
        return "CLUSTER_DISTRIBUTION"
    if points < 0:
        return "DISTRIBUTION"
    return None


def build_results(current_by_cusip, prior_by_cusip, ticker_by_cusip, universe):
    results = []
    universe = {symbol.upper() for symbol in universe}
    for cusip, resolved_ticker in ticker_by_cusip.items():
        ticker = resolved_ticker.upper()
        if universe and ticker not in universe:
            continue
        change = holdings_change(current_by_cusip.get(cusip, {}), prior_by_cusip.get(cusip, {}))
        magnitude, detail = score_institutional_ownership(change)
        if not detail.get("available"):
            continue
        results.append({
            "ticker": ticker,
            "cusip": cusip,
            "managers_added": detail["managers_added"],
            "managers_dropped": detail["managers_dropped"],
            "share_change_pct": detail.get("share_change_pct"),
            "flag": flag_for(magnitude),
            "notes": detail.get("notes") or [],
        })
    return sorted(results, key=lambda row: row["ticker"])


def run():
    sec = SecEdgarClient()
    managers = active_managers()
    generated_at = datetime.now(timezone.utc)
    if not sec.available or not managers:
        LOG.warn("Institutional 13F screen skipped: "
                 f"{'SEC_USER_AGENT not set' if not sec.available else 'no active managers configured'}")
        payload = {"schema_version": "1.0.0", "model_version": "institutional-13f-v1.0.0",
                  "generated_at": generated_at.isoformat(), "status": "skipped", "results": []}
        save_json("screens/institutional-13f.json", payload)
        return payload

    current_by_cusip, prior_by_cusip = {}, {}
    managers_reviewed, filings_unreadable = 0, 0
    new_position_rows = []
    for manager in managers:
        quarters = manager_quarters(sec, manager)
        if not quarters:
            continue
        managers_reviewed += 1
        filings_unreadable += sum(1 for quarter in quarters if quarter["unreadable"])
        for index, quarter in enumerate(quarters[:2]):
            target = current_by_cusip if index == 0 else prior_by_cusip
            for cusip, manager_shares in aggregate_by_cusip(quarter["holdings"]).items():
                target.setdefault(cusip, {}).update(manager_shares)
            for holding in quarter["holdings"]:
                new_position_rows.append({
                    "manager": manager["ticker"], "cusip": holding["cusip"],
                    "issuer": holding.get("issuer"), "shares": holding["shares"],
                    "filed": quarter["filed"], "quarter_rank": index,
                })

    added = append_new_positions(new_position_rows, collected_at=generated_at.isoformat())
    LOG.info(f"Institutional 13F positions: +{added} new point-in-time record(s)")

    all_cusips = set(current_by_cusip) | set(prior_by_cusip)
    openfigi = OpenFigiClient()
    ticker_by_cusip = openfigi.map_cusips(all_cusips) if all_cusips else {}

    results = build_results(current_by_cusip, prior_by_cusip, ticker_by_cusip,
                            UNIVERSE.get("symbols", ()))

    payload = {
        "schema_version": "1.0.0",
        "model_version": "institutional-13f-v1.0.0",
        "generated_at": generated_at.isoformat(),
        "status": "success",
        "manager_universe": "publicly traded, style=active only - see "
                            "pipeline/config/institutional_managers.json",
        "managers_reviewed": managers_reviewed,
        "managers_configured": len(managers),
        "filings_unreadable": filings_unreadable,
        "cusips_seen": len(all_cusips),
        "cusips_mapped": len(ticker_by_cusip),
        "disclaimer": "Descriptive only: which curated, publicly traded active managers "
                      "added or cut a position between their two most recent 13F-HR "
                      "filings. Not a claim about why, not a prediction, and not blended "
                      "into any research score. Coverage is necessarily partial - large "
                      "privately held managers (Renaissance Technologies, Citadel "
                      "Advisors, Bridgewater, ...) have no ticker and are not reachable "
                      "this way. Each position is timestamped by its SEC filing date, "
                      "which trails the quarter it describes by up to 45 days.",
        "results": results,
    }
    save_json("screens/institutional-13f.json", payload)
    LOG.info(f"Institutional 13F screen: {len(results)} ticker(s) with a flagged "
             f"manager-breadth change, {managers_reviewed}/{len(managers)} managers reviewed")
    return payload


if __name__ == "__main__":
    run()
