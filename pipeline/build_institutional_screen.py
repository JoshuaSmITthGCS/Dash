"""Quarterly 13F institutional accumulation/distribution screen and score input.

Reads a curated list of *publicly traded, actively managed* filers' own 13F-HR
information tables - there is no per-company "who holds this ticker" EDGAR endpoint, only
per-manager filings, so full 13F-universe coverage would need SEC's bulk quarterly data
sets instead. Restricting reads to public managers is not a random subset of
institutional flow (it oversamples the largest passive indexers, whose position changes
track index membership more than conviction), which is why coverage here defaults to
``style: active`` managers only and excludes ``passive``/``alternative`` ones entirely -
see ``pipeline/config/institutional_managers.json``. That mitigates the sampling bias, it
does not remove it.

Two separate consumers read this module's output:

  * This file's own ``run()`` publishes a factual, disclaimed screen
    (``public/data/screens/institutional-13f.json``) the same way
    ``build_congress_screen.py`` publishes STOCK Act disclosures - descriptive flags, not
    a score.
  * ``advisor_engine.institutional_ownership_modifier`` (via ``fetch_advisor.py``) reads
    *that published screen*, not the network, and folds a lag-decayed version of the same
    magnitude into the research score - see ``institutional_ownership.decay``. Nothing in
    the main hourly/daily advisor refresh re-fetches SEC or OpenFIGI for this; staleness
    is computed at scoring time from the screen's own ``as_of`` date.

Point-in-time correctness: a 13F position is disclosed up to 45 days after quarter-end,
so it is always stale relative to "today" by construction, and it can be *amended*
(13F-HR/A) after the fact, revising a quarter already reported. Both are handled
explicitly rather than left implicit:

  * Every stored/published record is timestamped by its **filing** date, never the
    quarter-end it describes - the same anchor ``pit_store.py`` uses everywhere else in
    this codebase.
  * ``manager_quarters`` groups filings by the *period* they cover (EDGAR's
    ``reportDate``), not by filing order, and prefers the most recently *filed* record for
    each period - so an amendment supersedes the original it revises instead of being
    mistaken for a new quarter.
  * A revision (an amendment that changes a previously recorded value) is logged to its
    own append-only file rather than silently overwriting history, mirroring
    ``pit_store.diff_revisions``.

Runs on its own schedule (13F data is inherently quarterly; there is nothing to gain from
polling more often than that changes), append-only point-in-time store under
``pipeline/data/institutional_13f/``.
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
REVISIONS = "revisions.jsonl"
MANAGERS_CONFIG = load_json("institutional_managers.json", from_config=True) or {}
UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}
# Fetched per manager rather than the bare 2 needed, so an amendment landing after its
# original still leaves both of the two most recent *distinct periods* reachable.
FILINGS_LOOKBACK = 6


def active_managers(config=None):
    """Publicly traded, actively managed curated filers - the default sleeve.

    Excludes ``passive`` (index/ETF-dominated AUM - position changes there track index
    membership, not conviction) and ``alternative`` (private-equity stakes are typically
    residual take-private holdings, lumpy and idiosyncratic) by design.
    """
    managers = (config or MANAGERS_CONFIG).get("managers", [])
    return [manager for manager in managers if manager.get("style") == "active"]


def _positions_path():
    os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
    return os.path.join(INSTITUTIONAL_DIR, POSITIONS)


def _revisions_path():
    os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
    return os.path.join(INSTITUTIONAL_DIR, REVISIONS)


def _read_jsonl(path):
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


def _append_jsonl(path, rows):
    if not rows:
        return 0
    with open(path, "a") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
    return len(rows)


def _read_all():
    return _read_jsonl(_positions_path())


def _position_key(row):
    """(manager, cusip, period), never ``filed`` - an amendment reports a new ``filed``
    date for the *same* period, and has to update that period's record, not create a
    second one next to it."""
    return (row.get("manager"), row.get("cusip"), row.get("period"))


def append_new_positions(rows, *, collected_at=None):
    """Append point-in-time holdings, logging (not silently applying) any revision.

    A row whose (manager, cusip, period) was never seen before is a new observation. One
    whose key was seen before with a *different* share count is an amendment revising a
    quarter already on record - logged to ``revisions.jsonl`` the same way
    ``pit_store.diff_revisions`` logs a restated fundamental, and still appended (never
    overwritten) so the original observation stays in history. A repeat with the same
    value is a no-op re-run and is skipped.
    """
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    existing = _read_all()
    latest_by_key = {}
    for row in existing:
        latest_by_key[_position_key(row)] = row  # last occurrence in file order wins

    fresh, revisions = [], []
    seen_this_batch = {}
    for row in rows:
        key = _position_key(row)
        prior = seen_this_batch.get(key) or latest_by_key.get(key)
        if prior is not None:
            if prior.get("shares") == row.get("shares") and prior.get("filed") == row.get("filed"):
                continue  # identical repeat - nothing new to record
            if prior.get("shares") != row.get("shares"):
                revisions.append({
                    "manager": row.get("manager"), "cusip": row.get("cusip"),
                    "period": row.get("period"), "previous_shares": prior.get("shares"),
                    "current_shares": row.get("shares"),
                    "previously_filed": prior.get("filed"), "filed": row.get("filed"),
                    "recorded_at": collected_at,
                })
        fresh.append({**row, "collected_at": collected_at})
        seen_this_batch[key] = row

    written = _append_jsonl(_positions_path(), fresh)
    revised = _append_jsonl(_revisions_path(), revisions)
    if revised:
        LOG.info(f"Institutional 13F: {revised} amendment(s) revised a previously recorded quarter")
    return written


def _info_table_holdings(sec, ticker, filing):
    """A filing's holdings, trying its ``primaryDocument`` first and falling back to the
    filing's own directory listing when that yields nothing.

    A 13F-HR's ``primaryDocument`` is routinely the cover page, not the information
    table - the holdings live in a separate exhibit (conventionally named something like
    ``InfoTable.xml``) that the submissions API never names directly. There is no fixed
    naming convention to hardcode, unlike Form 4's rendering-directory pattern, so this
    searches the real per-filing document listing (``filing_index``) for a name
    containing "infotable" and tries each candidate in turn, keeping the first that
    actually parses to a non-empty holdings list. Returns ``(holdings, unreadable)``;
    ``unreadable`` means the fetch or parse itself failed, not "found nothing".
    """
    cik, accession = filing["cik"], filing["accession"]
    try:
        text = sec.filing_document(cik, accession, filing["document"])
        holdings = parse_13f_info_table(text, ticker)
    except Exception:  # noqa: BLE001
        return [], True
    if holdings:
        return holdings, False
    try:
        candidates = [name for name in sec.filing_index(cik, accession)
                     if "infotable" in name.lower() and name != filing["document"]]
    except Exception:  # noqa: BLE001
        return [], False
    for name in candidates:
        try:
            text = sec.filing_document(cik, accession, name)
            holdings = parse_13f_info_table(text, ticker)
        except Exception:  # noqa: BLE001
            continue
        if holdings:
            return holdings, False
    return [], False


def manager_quarters(sec, manager):
    """A curated manager's two most recent *distinct periods*, newest first.

    Fetches ``FILINGS_LOOKBACK`` filings (not just 2) and groups by the period each one
    covers, keeping only the most recently *filed* record per period - so a 13F-HR/A
    amendment supersedes the 13F-HR it revises instead of being counted as its own
    quarter. ``is_amendment`` is carried through so the point-in-time layer and the
    published screen can both show which number is original and which was revised.
    """
    ticker = manager["ticker"]
    filings = sec.recent_forms(ticker, ("13F-HR", "13F-HR/A"), limit=FILINGS_LOOKBACK)
    by_period = {}
    for filing in filings:
        period = filing.get("period") or filing["filed"]
        current = by_period.get(period)
        if current is None or filing["filed"] > current["filed"]:
            by_period[period] = filing
    ordered_periods = sorted(by_period, reverse=True)[:2]

    quarters = []
    for period in ordered_periods:
        filing = by_period[period]
        holdings, unreadable = _info_table_holdings(sec, ticker, filing)
        quarters.append({
            "period": period, "filed": filing["filed"], "holdings": holdings,
            "unreadable": unreadable, "is_amendment": filing.get("form") == "13F-HR/A",
        })
    return quarters


def flag_for(points):
    """A descriptive label, not a score point - the screen reports facts, not a number
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


def build_results(current_by_cusip, prior_by_cusip, ticker_by_cusip, universe, *, as_of_by_cusip=None):
    """Publishable results: descriptive flags, plus the two fields
    ``fetch_advisor.collect_institutional_signals`` needs to turn this into a lag-decayed
    score modifier without re-deriving the breadth math itself - ``undecayed_magnitude``
    (this quarter's raw breadth score at full, undecayed weight) and ``as_of`` (its filing
    date, so the reader can compute how stale it now is). Neither is itself a score; the
    screen stays descriptive, the decay and clamping happen downstream in
    ``advisor_engine.institutional_ownership_modifier``.
    """
    as_of_by_cusip = as_of_by_cusip or {}
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
            "as_of": as_of_by_cusip.get(cusip),
            "undecayed_magnitude": magnitude,
        })
    return sorted(results, key=lambda row: row["ticker"])


def run():
    sec = SecEdgarClient()
    managers = active_managers()
    generated_at = datetime.now(timezone.utc)
    if not sec.available or not managers:
        LOG.warn("Institutional 13F screen skipped: "
                 f"{'SEC_USER_AGENT not set' if not sec.available else 'no active managers configured'}")
        payload = {"schema_version": "1.1.0", "model_version": "institutional-13f-v1.1.0",
                  "generated_at": generated_at.isoformat(), "status": "skipped", "results": []}
        save_json("screens/institutional-13f.json", payload)
        return payload

    current_by_cusip, prior_by_cusip, as_of_by_cusip = {}, {}, {}
    managers_reviewed, filings_unreadable, amendments_seen = 0, 0, 0
    new_position_rows = []
    for manager in managers:
        quarters = manager_quarters(sec, manager)
        if not quarters:
            continue
        managers_reviewed += 1
        filings_unreadable += sum(1 for quarter in quarters if quarter["unreadable"])
        amendments_seen += sum(1 for quarter in quarters if quarter["is_amendment"])
        for index, quarter in enumerate(quarters[:2]):
            target = current_by_cusip if index == 0 else prior_by_cusip
            for cusip, manager_shares in aggregate_by_cusip(quarter["holdings"]).items():
                target.setdefault(cusip, {}).update(manager_shares)
                if index == 0:
                    # Latest-filed wins across managers too, since as_of drives decay for
                    # every ticker this manager contributes to, not just this one CUSIP.
                    existing = as_of_by_cusip.get(cusip)
                    if existing is None or quarter["filed"] > existing:
                        as_of_by_cusip[cusip] = quarter["filed"]
            for holding in quarter["holdings"]:
                new_position_rows.append({
                    "manager": manager["ticker"], "cusip": holding["cusip"],
                    "issuer": holding.get("issuer"), "shares": holding["shares"],
                    "filed": quarter["filed"], "period": quarter["period"],
                    "quarter_rank": index, "is_amendment": quarter["is_amendment"],
                })

    added = append_new_positions(new_position_rows, collected_at=generated_at.isoformat())
    LOG.info(f"Institutional 13F positions: +{added} new point-in-time record(s)")

    all_cusips = set(current_by_cusip) | set(prior_by_cusip)
    openfigi = OpenFigiClient()
    ticker_by_cusip = openfigi.map_cusips(all_cusips) if all_cusips else {}

    results = build_results(current_by_cusip, prior_by_cusip, ticker_by_cusip,
                            UNIVERSE.get("symbols", ()), as_of_by_cusip=as_of_by_cusip)

    payload = {
        "schema_version": "1.1.0",
        "model_version": "institutional-13f-v1.1.0",
        "generated_at": generated_at.isoformat(),
        "status": "success",
        "manager_universe": "publicly traded, style=active only - see "
                            "pipeline/config/institutional_managers.json",
        "managers_reviewed": managers_reviewed,
        "managers_configured": len(managers),
        "filings_unreadable": filings_unreadable,
        "amendments_seen": amendments_seen,
        "cusips_seen": len(all_cusips),
        "cusips_mapped": len(ticker_by_cusip),
        "disclaimer": "Which curated, publicly traded active managers added or cut a "
                      "position between their two most recent distinct 13F reporting "
                      "periods. Not a claim about why, and coverage is necessarily "
                      "partial - large privately held managers (Renaissance "
                      "Technologies, Citadel Advisors, Bridgewater, ...) have no ticker "
                      "and are not reachable this way. Each result's `as_of` is the SEC "
                      "filing date, which trails the quarter it describes by up to 45 "
                      "days - advisor_engine.institutional_ownership_modifier decays its "
                      "score contribution by that lag rather than treating it as current.",
        "results": results,
    }
    save_json("screens/institutional-13f.json", payload)
    LOG.info(f"Institutional 13F screen: {len(results)} ticker(s) with a flagged "
             f"manager-breadth change, {managers_reviewed}/{len(managers)} managers reviewed, "
             f"{amendments_seen} amendment(s) seen")
    return payload


if __name__ == "__main__":
    run()
