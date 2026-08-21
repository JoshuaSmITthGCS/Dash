"""Point-in-time fundamentals, universe membership, and data-freshness tracking.

Why this exists: Yahoo (and yfinance on top of it) serves *restated* current fundamentals
with no as-originally-reported history, and its universe is today's universe. Backtesting a
scoring change against that data is contaminated twice over - by look-ahead into numbers
nobody had at the time, and by survivorship into a universe that quietly excludes everything
that failed. Neither can be fixed retroactively. Both can be fixed prospectively, by
appending a timestamped observation on every run starting now.

Three stores, all append-only JSON Lines under ``pipeline/data/pit/``:

  observations.jsonl  one row per (ticker, observation_date, field-set) actually observed
  revisions.jsonl     a row every time a previously-observed value changes (restatements)
  universe.jsonl      one row per run recording exactly who was in the universe that day

``as_of`` reads never see a value observed after the requested date, which is the entire
point: a backtest asking "what did we know on 2026-03-01" gets what was on the wire then.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from common import LOG, STORE_DIR

PIT_DIR = os.path.join(STORE_DIR, "pit")
OBSERVATIONS = "observations.jsonl"
REVISIONS = "revisions.jsonl"
UNIVERSE = "universe.jsonl"

# Fields worth preserving point-in-time. Quote-derived fields that only ever reflect
# "now" (analyst targets, short interest) are recorded too, because a snapshot of them
# taken weekly is the only history of them that will ever exist.
TRACKED_FIELDS = (
    "price", "market_cap", "sector", "forward_pe", "trailing_pe", "peg", "price_to_sales",
    "price_to_book", "price_to_tangible_book", "ev_to_ebitda", "ev_to_ebit", "ev_to_fcf",
    "ev_to_sales", "enterprise_value", "return_on_equity", "return_on_invested_capital",
    "gross_profits_to_assets", "free_cash_flow_yield", "profit_margin", "gross_margin",
    "operating_margin", "cash_conversion", "debt_to_equity", "current_ratio",
    "interest_coverage", "net_debt_to_ebitda", "altman_z", "altman_z_variant",
    "piotroski_f", "accruals_ratio", "revenue_growth", "earnings_growth", "fcf_growth_3y",
    "operating_margin_trend", "asset_growth", "earnings_surprise", "net_buyback_yield",
    "stock_comp_to_revenue", "capex_to_depreciation", "days_sales_outstanding_trend",
    "inventory_days_trend", "short_percent_of_float", "days_to_cover", "beta",
    "analyst_rating", "analyst_target_upside", "analyst_count", "statement_periods",
    "average_dollar_volume",
    # Expectation change. Yahoo serves only today's view of every one of these, so a later
    # backtest can reconstruct what the model knew on a past date from this archive or from
    # nowhere at all - which is the whole argument for writing it from day one rather than
    # once the first backtest needs it.
    "analyst_consensus_target", "revision_breadth_30d", "eps_revision_30d_pct",
    "net_upgrades_90d",
)

# How long a field stays trustworthy before it should be flagged, in hours. Statement-derived
# metrics move quarterly; a quote moves constantly. Flagging is deliberately separate from
# discarding - the pipeline surfaces staleness rather than silently dropping a company.
DEFAULT_FIELD_TTL_HOURS = {
    "price": 24,
    "market_cap": 48,
    "forward_pe": 72,
    "analyst_rating": 168,
    "analyst_target_upside": 168,
    "short_percent_of_float": 168,
    "days_to_cover": 168,
    "beta": 720,
    "average_dollar_volume": 48,
    "default": 24 * 100,          # statement-derived metrics: a quarter plus slack
}


def _path(name):
    os.makedirs(PIT_DIR, exist_ok=True)
    return os.path.join(PIT_DIR, name)


def _append(name, rows):
    if not rows:
        return 0
    path = _path(name)
    try:
        with open(path, "a") as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
    except OSError as exc:
        LOG.warn(f"point-in-time append to {name} failed ({type(exc).__name__})")
        return 0
    return len(rows)


def _read(name, limit=None):
    path = _path(name)
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows[-limit:] if limit else rows


def _now():
    return datetime.now(timezone.utc)


def _iso_date(value=None):
    return (value or _now()).date().isoformat()


# ---------------- writing ----------------

def tracked_fields(snapshot, fields=TRACKED_FIELDS):
    """The subset of a snapshot worth preserving, with None values dropped."""
    return {field: snapshot[field] for field in fields
            if field in snapshot and snapshot[field] is not None}


def latest_values(ticker, rows=None):
    """Most recent observed value per field for one ticker, used for restatement diffing."""
    rows = rows if rows is not None else _read(OBSERVATIONS)
    values = {}
    for row in rows:
        if row.get("ticker") != ticker:
            continue
        for field, value in (row.get("values") or {}).items():
            values[field] = (value, row.get("observed_at"))
    return values


def latest_snapshots(symbols=None, rows=None):
    """Latest actually observed raw snapshot for each requested ticker.

    This is intended for offline challenger comparisons. It never invents or backfills a
    value, and each returned row retains the latest field value that had reached the store.
    """
    allowed = {str(symbol).upper() for symbol in symbols} if symbols is not None else None
    snapshots = {}
    for row in rows if rows is not None else _read(OBSERVATIONS):
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or (allowed is not None and ticker not in allowed):
            continue
        snapshot = snapshots.setdefault(ticker, {"ticker": ticker})
        snapshot.update(row.get("values") or {})
        snapshot["observed_at"] = row.get("observed_at")
    return list(snapshots.values())


def diff_revisions(ticker, previous, current, observed_at):
    """Rows for every field whose previously-observed value changed.

    A changed value is either a genuine update (a new quarter landed) or a restatement of
    a period already reported. Both are worth keeping; the revision log is what makes it
    possible to tell later which numbers the model was actually scored on.
    """
    revisions = []
    for field, value in current.items():
        if field not in previous:
            continue
        before, before_at = previous[field]
        if before == value:
            continue
        revisions.append({
            "ticker": ticker, "field": field, "previous": before, "current": value,
            "previously_observed_at": before_at, "observed_at": observed_at,
        })
    return revisions


def append_snapshot(rows, *, observed_at=None, source="pipeline", fields=TRACKED_FIELDS, config_hash=None):
    """Append one point-in-time observation per row and log any restatements.

    ``rows`` is an iterable of snapshot dicts that each carry a ``ticker``. Returns counts
    so the caller can report how much history the run actually added.

    ``config_hash`` (a SHA-256 of settings.json, not a per-ticker metric) records which
    scoring configuration was live when this observation was taken -- a PIT row is read
    back months later, by which point settings.json has likely changed underneath it, and
    without this there is no way to tell which formula version actually produced it short
    of cross-referencing git history by timestamp.
    """
    observed_at = (observed_at or _now()).isoformat() if not isinstance(observed_at, str) else observed_at
    existing = _read(OBSERVATIONS)
    observations, revisions = [], []
    for row in rows:
        ticker = (row.get("ticker") or "").upper()
        if not ticker:
            continue
        values = tracked_fields(row, fields)
        if not values:
            continue
        previous = latest_values(ticker, existing)
        revisions.extend(diff_revisions(ticker, previous, values, observed_at))
        observation = {
            "ticker": ticker,
            "observed_at": observed_at,
            "observation_date": observed_at[:10],
            "source": source,
            "values": values,
        }
        if config_hash is not None:
            observation["config_hash"] = config_hash
        observations.append(observation)
    written = _append(OBSERVATIONS, observations)
    revised = _append(REVISIONS, revisions)
    LOG.info(f"Point-in-time store: +{written} observations, +{revised} revisions")
    return {"observations": written, "revisions": revised}


def record_universe(symbols, *, observed_at=None, source="pipeline", note=None):
    """Persist exactly who was in the universe on this run, delisted names included.

    Backtesting on today's constituents only is survivorship bias by construction: the
    universe silently excludes everything that was delisted, acquired, or collapsed. The
    membership log is the only defence, and it only works if it starts before it is needed.
    """
    observed_at = (observed_at or _now()).isoformat() if not isinstance(observed_at, str) else observed_at
    ordered = sorted({str(symbol).upper() for symbol in symbols if symbol})
    previous = universe_as_of(None)
    departed = sorted(set(previous) - set(ordered)) if previous else []
    added = sorted(set(ordered) - set(previous)) if previous else []
    row = {
        "observed_at": observed_at, "observation_date": observed_at[:10], "source": source,
        "count": len(ordered), "symbols": ordered, "added": added, "removed": departed,
        **({"note": note} if note else {}),
    }
    _append(UNIVERSE, [row])
    if departed:
        LOG.info(f"Universe membership: {len(departed)} symbol(s) left the universe "
                 f"({', '.join(departed[:8])}{'...' if len(departed) > 8 else ''})")
    return row


# ---------------- reading ----------------

def as_of(ticker, when=None, *, rows=None):
    """Every field's value as most recently observed on or before ``when``.

    This is the read a backtest must use. Values observed after the as-of date are
    invisible, so a restated number cannot leak backwards into a period that never saw it.
    """
    rows = rows if rows is not None else _read(OBSERVATIONS)
    cutoff = when if isinstance(when, str) else (_iso_date(when) if when else None)
    ticker = (ticker or "").upper()
    result, stamps = {}, {}
    for row in rows:
        if row.get("ticker") != ticker:
            continue
        observed = row.get("observed_at", "")
        if cutoff and observed[:10] > cutoff:
            continue
        for field, value in (row.get("values") or {}).items():
            result[field] = value
            stamps[field] = observed
    if not result:
        return None
    return {"ticker": ticker, "as_of": cutoff, "values": result, "observed_at": stamps}


def universe_as_of(when=None, *, rows=None):
    """Universe membership as recorded on or before ``when``. Empty list when unknown."""
    rows = rows if rows is not None else _read(UNIVERSE)
    cutoff = when if isinstance(when, str) else (_iso_date(when) if when else None)
    selected = None
    for row in rows:
        if cutoff and row.get("observed_at", "")[:10] > cutoff:
            continue
        selected = row
    return list(selected.get("symbols", [])) if selected else []


def revision_log(ticker=None, field=None, limit=None):
    """Restatements, optionally narrowed to one ticker and/or field."""
    rows = _read(REVISIONS)
    if ticker:
        rows = [row for row in rows if row.get("ticker") == ticker.upper()]
    if field:
        rows = [row for row in rows if row.get("field") == field]
    return rows[-limit:] if limit else rows


def history(ticker, field, *, rows=None):
    """Every observed value of one field over time, oldest first."""
    rows = rows if rows is not None else _read(OBSERVATIONS)
    ticker = (ticker or "").upper()
    series = []
    for row in rows:
        if row.get("ticker") != ticker:
            continue
        values = row.get("values") or {}
        if field in values:
            series.append({"observed_at": row.get("observed_at"), "value": values[field]})
    return series


def valuation_histories(*, rows=None, years, days_per_year, as_of=None, metrics=()):
    """Trailing, prospectively observed valuation histories keyed by ticker and metric.

    One value per observation date is retained. This prevents three scheduled refreshes on
    the same day from pretending to be three independent historical observations. Nothing
    is reconstructed before the store began, so the result accumulates honestly forward.
    """
    rows = rows if rows is not None else _read(OBSERVATIONS)
    end = as_of or _now()
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    cutoff = end - timedelta(days=int(days_per_year) * int(years))
    selected = set(metrics)
    dated = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        stamp = row.get("observed_at")
        try:
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        if not ticker or observed < cutoff or observed > end:
            continue
        day = observed.date().isoformat()
        values = dict(row.get("values") or {})
        if "sales_multiple" in selected:
            values["sales_multiple"] = values.get("ev_to_sales", values.get("price_to_sales"))
        for metric, value in values.items():
            if selected and metric not in selected:
                continue
            if isinstance(value, (int, float)):
                dated[(ticker, metric, day)] = float(value)
    histories = {}
    for (ticker, metric, day), value in sorted(dated.items()):
        histories.setdefault(ticker, {}).setdefault(metric, []).append({
            "observed_at": day,
            "value": value,
        })
    return histories


def depth():
    """How much point-in-time history exists, so the UI can say when backtests become honest."""
    rows = _read(OBSERVATIONS)
    if not rows:
        return {"observations": 0, "tickers": 0, "first_observed": None,
                "last_observed": None, "days": 0}
    stamps = sorted(row.get("observed_at", "") for row in rows if row.get("observed_at"))
    first, last = stamps[0], stamps[-1]
    try:
        days = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).days
    except (TypeError, ValueError):
        days = 0
    return {
        "observations": len(rows),
        "tickers": len({row.get("ticker") for row in rows}),
        "first_observed": first, "last_observed": last, "days": days,
        "revisions": len(_read(REVISIONS)),
    }


# ---------------- staleness ----------------

def field_ttls(overrides=None):
    return {**DEFAULT_FIELD_TTL_HOURS, **(overrides or {})}


def stale_fields(observed_at_by_field, *, now=None, ttls=None):
    """Fields whose most recent observation has aged past their TTL.

    Returns ``{field: age_hours}``. The caller decides whether to quarantine, annotate,
    or simply display - this function only reports, so a stale reading is never silently
    scored as if it were fresh.
    """
    ttls = field_ttls(ttls)
    now = now or _now()
    stale = {}
    for field, observed in (observed_at_by_field or {}).items():
        try:
            stamp = datetime.fromisoformat(observed)
        except (TypeError, ValueError):
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_hours = (now - stamp).total_seconds() / 3600
        allowed = ttls.get(field, ttls["default"])
        if age_hours > allowed:
            stale[field] = round(age_hours, 1)
    return stale


def freshness_report(rows, *, now=None, ttls=None, stale_after_hours=36):
    """A dashboard-ready summary of how fresh the published dataset actually is.

    ``rows`` carry an optional ``data_fetched_at``; anything older than
    ``stale_after_hours`` is called out by name so a silently frozen provider shows up
    as a warning instead of as unchanged numbers.
    """
    now = now or _now()
    total = len(rows)
    ages, stale_rows = [], []
    for row in rows:
        stamp = row.get("data_fetched_at") or row.get("observed_at")
        try:
            observed = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age_hours = (now - observed).total_seconds() / 3600
        ages.append(age_hours)
        if age_hours > stale_after_hours:
            stale_rows.append({"ticker": row.get("ticker"), "age_hours": round(age_hours, 1)})
    stale_rows.sort(key=lambda item: item["age_hours"], reverse=True)
    return {
        "rows": total,
        "timestamped": len(ages),
        "median_age_hours": round(sorted(ages)[len(ages) // 2], 1) if ages else None,
        "oldest_age_hours": round(max(ages), 1) if ages else None,
        "stale_after_hours": stale_after_hours,
        "stale_count": len(stale_rows),
        "stale": stale_rows[:20],
        "status": "healthy" if not stale_rows else (
            "degraded" if len(stale_rows) < max(1, total // 4) else "error"),
    }


def prune(before_days=1825):
    """Drop observations older than five years so the log cannot grow without bound."""
    cutoff = (_now() - timedelta(days=before_days)).isoformat()
    for name in (OBSERVATIONS, REVISIONS, UNIVERSE):
        rows = [row for row in _read(name) if row.get("observed_at", "") >= cutoff]
        path = _path(name)
        try:
            with open(path, "w") as handle:
                for row in rows:
                    handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
        except OSError:
            continue
    return depth()
