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
from sec_edgar import SecEdgarClient, entity_name_matches

INSTITUTIONAL_DIR = os.path.join(STORE_DIR, "institutional_13f")
POSITIONS = "positions.jsonl"
REVISIONS = "revisions.jsonl"
CUSIP_TICKERS = "cusip_tickers.json"
MANAGERS_CONFIG = load_json("institutional_managers.json", from_config=True) or {}
UNIVERSE = load_json("advisor_universe.json", from_config=True) or {}
# Fetched per manager rather than the bare 2 needed, so an amendment landing after its
# original still leaves both of the two most recent *distinct periods* reachable.
FILINGS_LOOKBACK = 6
FILER_FORMS = ("13F-HR", "13F-HR/A")
# A company-name prefix search returns alphabetical neighbours, not just the family being
# looked for; the name guard rejects those, this only bounds how many are examined.
FILER_SEARCH_LIMIT = 40
# A manager family filing through more than a handful of adviser subsidiaries is far more
# likely to be an over-broad name match than a real structure, so resolution stops there
# rather than fanning out into an unbounded number of submissions requests.
MAX_FILERS_PER_MANAGER = 6
# A CUSIP OpenFIGI has already answered for does not change its answer, so the mapping is
# cached across runs and only the CUSIPs never asked about cost requests. That is what makes
# an unauthenticated run viable at all: the anonymous tier maps 10 CUSIPs per request at 25
# requests a minute, so a first sight of ~3,500 CUSIPs is a quarter of an hour of pacing,
# while every later monthly run only asks about the handful the managers newly bought.
UNMAPPED_RETRY_DAYS = 180
# Bounded so a first run finishes inside the job timeout with a usable, published prefix
# rather than being killed with nothing. Keyed runs map 100 per request and need no ceiling.
ANONYMOUS_REQUEST_BUDGET = 400


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


def _ticker_cache_path():
    os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
    return os.path.join(INSTITUTIONAL_DIR, CUSIP_TICKERS)


def read_ticker_cache(path=None):
    """Everything OpenFIGI has already answered, as ``{"tickers": {...}, "unmapped": {...}}``.

    Both halves matter. ``tickers`` spares the next run from re-asking a question with a
    stable answer; ``unmapped`` remembers the CUSIPs OpenFIGI had no ticker for, so a
    delisted or non-equity holding does not consume the request budget every single month
    ahead of the CUSIPs that could still resolve. Unmapped entries carry the date they were
    asked and are re-asked after ``UNMAPPED_RETRY_DAYS``, since "no ticker" can become one.
    """
    path = path or _ticker_cache_path()
    if not os.path.exists(path):
        return {"tickers": {}, "unmapped": {}}
    try:
        with open(path) as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {"tickers": {}, "unmapped": {}}
    tickers = payload.get("tickers")
    unmapped = payload.get("unmapped")
    return {"tickers": tickers if isinstance(tickers, dict) else {},
            "unmapped": unmapped if isinstance(unmapped, dict) else {}}


def write_ticker_cache(cache, *, path=None, updated_at=None):
    path = path or _ticker_cache_path()
    payload = {
        "schema_version": "1.0.0",
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "_comment": "CUSIP->ticker answers from OpenFIGI, cached because they do not change "
                    "and the anonymous rate limit makes re-asking expensive. 'unmapped' "
                    f"entries are re-asked after {UNMAPPED_RETRY_DAYS} days.",
        "tickers": dict(sorted(cache.get("tickers", {}).items())),
        "unmapped": dict(sorted(cache.get("unmapped", {}).items())),
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return payload


def cusips_to_map(current_by_cusip, prior_by_cusip, cache, *, today=None):
    """Which CUSIPs still need an OpenFIGI answer, most worth asking about first.

    Ordering is the whole point: with a request ceiling, whatever is asked first is what
    gets published. A CUSIP some curated manager actually opened or exited this quarter is
    the only kind that can produce a flag, so those lead; within each group, the ones held
    by more managers lead, since breadth is what the screen scores on and a widely held
    name is likelier to be in the covered universe at all.
    """
    today = today or datetime.now(timezone.utc).date()
    tickers, unmapped = cache.get("tickers", {}), cache.get("unmapped", {})
    ranked = []
    for cusip in set(current_by_cusip) | set(prior_by_cusip):
        if cusip in tickers:
            continue
        asked = unmapped.get(cusip)
        if asked and _days_since(asked, today) < UNMAPPED_RETRY_DAYS:
            continue
        current = current_by_cusip.get(cusip, {})
        prior = prior_by_cusip.get(cusip, {})
        moved = set(current) != set(prior)
        ranked.append((0 if moved else 1, -len(set(current) | set(prior)), cusip))
    return [cusip for _, _, cusip in sorted(ranked)]


def _days_since(iso_date, today):
    try:
        asked = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return UNMAPPED_RETRY_DAYS  # unparseable - treat as due for another ask
    return (today - asked).days


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


# Ranked hints for which exhibit in a 13F accession is the information table. Ordering only -
# every XML document in the filing is tried regardless, because filers name this exhibit
# whatever they like ("form13fInfoTable.xml", "informationTable.xml", "13f_hr_q2.xml",
# "holdings.xml"). Matching on a single spelling is what produced a screen that reported
# healthy runs and zero holdings: "informationTable.xml" does not contain the substring
# "infotable", so the one filter previously applied skipped the very file it was looking for.
_INFO_TABLE_HINTS = ("infotable", "informationtable", "information_table", "info_table",
                     "table", "13f", "holding")


def _rank_info_table_candidate(name):
    lowered = name.lower()
    for rank, hint in enumerate(_INFO_TABLE_HINTS):
        if hint in lowered:
            return rank
    return len(_INFO_TABLE_HINTS)


def _info_table_holdings(sec, manager_id, filing):
    """A filing's holdings, trying its ``primaryDocument`` first and falling back to every
    XML document in the filing's own directory listing.

    A 13F-HR's ``primaryDocument`` is essentially always the cover page, not the information
    table - the holdings live in a separate exhibit that the submissions API never names.
    There is no naming convention to hardcode, unlike Form 4's rendering-directory pattern,
    so this reads the real per-filing document listing (``filing_index``), sorts the XML
    documents by how much their name looks like an information table, and keeps the first
    that actually parses to a non-empty holdings list. Sorting rather than filtering is the
    point: the name hints decide what to try *first*, never what to exclude.

    Returns ``(holdings, unreadable)``. ``unreadable`` means the fetch or parse itself failed;
    a filing whose documents were all readable but held no equity rows is not unreadable, and
    the two are counted separately so a blank screen can say which one it hit.
    """
    cik, accession = filing["cik"], filing["accession"]
    # Tracked rather than returned immediately: a primary document that could not be fetched
    # is a real failure to report, but it is not a reason to skip the exhibit that actually
    # holds the positions - the fallback still runs, and this only decides what to report if
    # the fallback also comes up empty.
    unreadable = False
    try:
        text = sec.filing_document(cik, accession, filing["document"])
        holdings = parse_13f_info_table(text, manager_id)
    except Exception:  # noqa: BLE001
        holdings, unreadable = [], True
    if holdings:
        return holdings, False
    try:
        listing = sec.filing_index(cik, accession)
    except Exception:  # noqa: BLE001
        return [], True
    candidates = [name for name in listing
                  if name.lower().endswith(".xml") and name != filing["document"]]
    candidates.sort(key=_rank_info_table_candidate)
    for name in candidates:
        try:
            text = sec.filing_document(cik, accession, name)
            holdings = parse_13f_info_table(text, manager_id)
        except Exception:  # noqa: BLE001
            unreadable = True
            continue
        if holdings:
            return holdings, False
    return [], unreadable


def resolve_filer_ciks(sec, manager):
    """Every EDGAR entity that actually files 13F-HRs for one curated manager family.

    This is the step whose absence made the screen publish successful, empty runs. The
    curated config identifies a manager by its *listed* ticker, and ``ticker_map`` resolves
    that to the CIK of the operating company - which for an asset manager is the entity that
    files the 10-K, not the one that files the 13F. Those are different registrants with
    different CIKs (T. Rowe Price Group vs. its adviser subsidiaries), and asking the
    operating company's CIK for 13F-HRs correctly returns nothing at all. Berkshire is the
    exception that hid this: it files its own 13F, so a spot check on the one recognisable
    name passes while most of the sleeve silently resolves to zero filings.

    Resolution order, widest net first, with every candidate verified before it is trusted:

      1. the ticker's own CIK, for the minority of managers that do file their own 13F;
      2. an EDGAR company-name prefix search for the configured name and any ``filer_aliases``
         (adviser subsidiaries are filed under names the colloquial one does not prefix -
         "PRICE T ROWE ASSOCIATES" is not reachable from "T. Rowe Price").

    Every candidate has to actually file 13F-HRs, and every *searched* candidate additionally
    has to token-match the configured name or one of its aliases - re-checked against the
    submissions payload rather than the search feed's own label, so the name a holding is
    attributed under is the one EDGAR reports for the CIK being read. Together those are what
    let the config keep its rule of never hand-typing a CIK: identity is asserted by name and
    confirmed against EDGAR, so a bad match drops out loudly here instead of publishing a
    different manager's holdings under this one's label. The ticker's own CIK is exempt from
    the name check only because it comes from SEC's ticker file, which already established it.

    Returns ``(ciks, notes)``; ``notes`` records what was searched and what was rejected, so a
    manager that resolves to nothing says why in the published payload.
    """
    names = [manager.get("name") or manager["ticker"], *(manager.get("filer_aliases") or [])]
    candidates, notes, seen = [], [], set()

    # The ticker's own CIK comes from SEC's own ticker file, so its identity is already
    # established and is not re-checked by name - only search hits need the guard, and
    # applying it here could only reject a correct CIK whose EDGAR name is spelled
    # differently from the config's.
    ticker_cik = sec.ticker_map().get(manager["ticker"].upper())
    if ticker_cik:
        candidates.append((ticker_cik, False, None))
        seen.add(ticker_cik)
    else:
        notes.append(f"ticker {manager['ticker']} did not resolve to a CIK")

    for name in names:
        try:
            hits = sec.company_search(name, form_type="13F-HR", limit=FILER_SEARCH_LIMIT)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"company search for {name!r} failed ({type(exc).__name__})")
            continue
        for cik, conformed in hits:
            if cik in seen:
                continue
            seen.add(cik)
            if not any(entity_name_matches(conformed, candidate) for candidate in names):
                notes.append(f"rejected CIK {cik} ({conformed!r}): name does not match")
                continue
            candidates.append((cik, True, conformed))

    resolved = []
    for cik, from_search, searched_name in candidates:
        try:
            # Falls back to the name the search feed reported. A submissions payload without
            # a "name" is rare but real, and treating that absence as a failed name check
            # rejected filers EDGAR had already matched by name - a silent coverage loss
            # that read, in the published notes, exactly like a wrong-manager rejection.
            conformed = sec.entity_name(cik) or searched_name
            filings = sec.filings_for_cik(cik, FILER_FORMS, limit=1)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"CIK {cik} unreadable ({type(exc).__name__})")
            continue
        if not filings:
            notes.append(f"CIK {cik} ({conformed!r}) files no 13F-HR")
            continue
        # Re-checked against the submissions payload rather than trusting the search feed's
        # own label, so the name a holding is attributed under is the one EDGAR reports for
        # the CIK actually being read.
        if from_search and not any(entity_name_matches(conformed, candidate) for candidate in names):
            notes.append(f"rejected CIK {cik} ({conformed!r}): name does not match")
            continue
        resolved.append(cik)
        if len(resolved) >= MAX_FILERS_PER_MANAGER:
            break
    return resolved, notes


def manager_quarters(sec, manager, ciks):
    """A curated manager's two most recent *distinct periods*, newest first.

    Fetches ``FILINGS_LOOKBACK`` filings per resolved filer (not just 2) and groups by the
    period each one covers, keeping only the most recently *filed* record per (filer, period)
    - so a 13F-HR/A amendment supersedes the 13F-HR it revises instead of being counted as
    its own quarter. ``is_amendment`` is carried through so the point-in-time layer and the
    published screen can both show which number is original and which was revised.

    Holdings from several filers are unioned into the period they share, because a manager
    family that files through more than one adviser subsidiary holds one economic position
    split across those filings - counting them as separate managers would inflate the very
    breadth count this screen is built on.
    """
    manager_id = manager["ticker"]
    filings = []
    for cik in ciks:
        try:
            filings.extend(sec.filings_for_cik(cik, FILER_FORMS, limit=FILINGS_LOOKBACK))
        except Exception:  # noqa: BLE001
            continue

    by_period = {}
    for filing in filings:
        period = filing.get("period") or filing["filed"]
        slot = by_period.setdefault(period, {})
        current = slot.get(filing["cik"])
        if current is None or filing["filed"] > current["filed"]:
            slot[filing["cik"]] = filing
    ordered_periods = sorted(by_period, reverse=True)[:2]

    quarters = []
    for period in ordered_periods:
        holdings, unreadable, is_amendment, filed = [], False, False, ""
        for filing in by_period[period].values():
            parsed, failed = _info_table_holdings(sec, manager_id, filing)
            holdings.extend(parsed)
            unreadable = unreadable or failed
            is_amendment = is_amendment or filing.get("form") == "13F-HR/A"
            filed = max(filed, filing["filed"] or "")
        quarters.append({
            "period": period, "filed": filed, "holdings": holdings,
            "unreadable": unreadable, "is_amendment": is_amendment,
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
    new_position_rows, coverage = [], []
    for manager in managers:
        ciks, notes = resolve_filer_ciks(sec, manager)
        quarters = manager_quarters(sec, manager, ciks) if ciks else []
        holdings_parsed = sum(len(quarter["holdings"]) for quarter in quarters)
        # Recorded for every configured manager, including the ones that produced nothing.
        # A manager silently absent from the totals is exactly how this screen published
        # confident, empty runs; the per-manager reason travels with the payload instead.
        coverage.append({
            "manager": manager["ticker"], "name": manager.get("name"),
            "filer_ciks": ciks, "periods": [quarter["period"] for quarter in quarters],
            "holdings_parsed": holdings_parsed,
            "notes": notes if not ciks or not holdings_parsed else [],
        })
        if not quarters:
            LOG.warn(f"Institutional 13F: no readable 13F-HR for {manager['ticker']} "
                     f"({'; '.join(notes) or 'no filings found'})")
            continue
        managers_reviewed += 1
        filings_unreadable += sum(1 for quarter in quarters if quarter["unreadable"])
        amendments_seen += sum(1 for quarter in quarters if quarter["is_amendment"])
        for index, quarter in enumerate(quarters[:2]):
            target = current_by_cusip if index == 0 else prior_by_cusip
            positions = aggregate_by_cusip(quarter["holdings"])
            for cusip, manager_shares in positions.items():
                target.setdefault(cusip, {}).update(manager_shares)
                if index == 0:
                    # Latest-filed wins across managers too, since as_of drives decay for
                    # every ticker this manager contributes to, not just this one CUSIP.
                    existing = as_of_by_cusip.get(cusip)
                    if existing is None or quarter["filed"] > existing:
                        as_of_by_cusip[cusip] = quarter["filed"]
            # Stored per (manager, cusip) already summed, matching ``_position_key``. Writing
            # one row per raw information-table line instead would hand the point-in-time
            # layer several rows sharing a key, which it reads as this manager amending its
            # own filing mid-batch and logs as a phantom revision.
            issuers = {holding["cusip"]: holding.get("issuer") for holding in quarter["holdings"]}
            for cusip, manager_shares in positions.items():
                new_position_rows.append({
                    "manager": manager["ticker"], "cusip": cusip,
                    "issuer": issuers.get(cusip),
                    "shares": manager_shares.get(manager["ticker"]),
                    "filed": quarter["filed"], "period": quarter["period"],
                    "quarter_rank": index, "is_amendment": quarter["is_amendment"],
                })

    added = append_new_positions(new_position_rows, collected_at=generated_at.isoformat())
    LOG.info(f"Institutional 13F positions: +{added} new point-in-time record(s)")

    all_cusips = set(current_by_cusip) | set(prior_by_cusip)
    cache = read_ticker_cache()
    wanted = cusips_to_map(current_by_cusip, prior_by_cusip, cache,
                           today=generated_at.date())
    openfigi = OpenFigiClient(max_requests=(None if os.getenv("OPENFIGI_API_KEY", "").strip()
                                            else ANONYMOUS_REQUEST_BUDGET))
    newly_mapped = openfigi.map_cusips(wanted) if wanted else {}
    if wanted:
        # Recorded whether or not anything resolved: an unresolved CUSIP that was actually
        # asked about must not be asked again next month, and one that was never reached
        # (refused batch, or the request ceiling) must be.
        unattempted = set(openfigi.pending)
        attempted = [cusip for cusip in wanted if cusip not in unattempted]
        cache["tickers"].update(newly_mapped)
        for cusip in attempted:
            if cusip in newly_mapped:
                cache["unmapped"].pop(cusip, None)
            else:
                cache["unmapped"][cusip] = generated_at.date().isoformat()
        write_ticker_cache(cache, updated_at=generated_at.isoformat())
    for error in openfigi.errors:
        LOG.warn(f"Institutional 13F: OpenFIGI ({openfigi.tier}) {error}")
    ticker_by_cusip = {cusip: ticker for cusip, ticker in cache["tickers"].items()
                       if cusip in all_cusips}
    cusips_pending = len([cusip for cusip in all_cusips
                          if cusip not in ticker_by_cusip and cusip not in cache["unmapped"]])

    results = build_results(current_by_cusip, prior_by_cusip, ticker_by_cusip,
                            UNIVERSE.get("symbols", ()), as_of_by_cusip=as_of_by_cusip)

    # "No manager moved a position" and "nothing was collected" produce the same empty
    # results list and are not the same claim. Only the first is a finding; the second is a
    # broken run, and reporting it as success is what left the screen reading "no flagged
    # activity yet" while the collection underneath it had failed outright.
    status, degraded_reason = "success", None
    if not managers_reviewed:
        status = "degraded"
        degraded_reason = ("No configured manager resolved to a readable 13F-HR filer - see "
                           "manager_coverage for the per-manager reason.")
    elif not all_cusips:
        status = "degraded"
        degraded_reason = (f"{managers_reviewed} manager(s) had 13F-HR filings but no "
                           "information table could be parsed from them.")
    elif not ticker_by_cusip:
        status = "degraded"
        # Says what OpenFIGI actually refused rather than "check the mapping step". The
        # anonymous tier's job cap is a tenth of the keyed one, so a keyed-size batch sent
        # without a key is rejected on every request - a failure that used to be swallowed
        # whole and published as a confident, empty screen.
        refusal = f" OpenFIGI ({openfigi.tier}): {openfigi.errors[0]}." if openfigi.errors else ""
        degraded_reason = (f"{len(all_cusips)} CUSIP(s) were collected but none mapped to a "
                           f"ticker.{refusal}")
    if degraded_reason:
        LOG.warn(f"Institutional 13F screen degraded: {degraded_reason}")

    payload = {
        "schema_version": "1.3.0",
        "model_version": "institutional-13f-v1.3.0",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "degraded_reason": degraded_reason,
        "manager_coverage": coverage,
        "manager_universe": "publicly traded, style=active only - see "
                            "pipeline/config/institutional_managers.json",
        "managers_reviewed": managers_reviewed,
        "managers_configured": len(managers),
        "filings_unreadable": filings_unreadable,
        "amendments_seen": amendments_seen,
        "cusips_seen": len(all_cusips),
        "cusips_mapped": len(ticker_by_cusip),
        # Not yet asked about, or asked and refused - the honest denominator for how
        # complete this run's coverage is, and what the next run picks up first.
        "cusips_pending": cusips_pending,
        "openfigi_tier": openfigi.tier,
        "openfigi_errors": openfigi.errors,
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
             f"{amendments_seen} amendment(s) seen, {len(ticker_by_cusip)}/{len(all_cusips)} "
             f"CUSIP(s) mapped ({cusips_pending} still pending)")
    return payload


if __name__ == "__main__":
    run()
