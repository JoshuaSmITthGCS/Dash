"""Analyst expectation data from Yahoo, reduced to the handful of fields the models read.

The catalyst and analyst-conviction models both need the same thing and neither had it: not
what analysts currently think, but how fast what they think is *changing*. A static 2.6/5
consensus and a 3% target upside are already in the price; a fiscal-year EPS estimate that has
moved from $5.10 to $5.72 in thirty days, with seven upgrades against one downgrade, is the
part that may still be repricing.

Yahoo exposes the raw material for that through four families - EPS revision counts, the EPS
trend by age, upgrade/downgrade history, and consensus price targets. What it does not expose
is any of it as-of a past date: every call returns today's view. That is why
``target_change_30d_pct`` is derived from this repository's own stored snapshots rather than
from a provider field, and why nothing here is treated as a substitute for the point-in-time
store. Without archived snapshots there is no honest way to reconstruct what the model would
have known on a given date, so the collection path stamps every reading with when it was
observed and the store keeps it.

Every reader is defensive by design. yfinance's return shapes drift between versions - a
DataFrame here, a dict there, a differently-cased column somewhere else - and a research
pipeline that raises on an unexpected column loses the whole company. Each field resolves
independently and returns None when it cannot, which the models handle by dropping the
component and lowering that mode's confidence.
"""

from datetime import datetime, timedelta, timezone

from common import LOG

# yfinance indexes both the revision and trend frames by forecast period. "0y" is the current
# fiscal year, which is the horizon a revision signal is normally read on: quarterly estimates
# are noisier and the out-year is too far away to have been revised on real information.
PREFERRED_PERIODS = ("0y", "+1y", "0q", "+1q")
UPGRADE_WINDOW_DAYS = 90


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _frame_records(frame):
    """Normalize a yfinance return into ``[(index_label, {column: value}), ...]``.

    A list of pairs rather than a dict keyed by index, because the upgrade/downgrade frame is
    indexed by grade date and two firms moving the same name on the same day is the normal
    case, not an edge case. Collapsing those into one key - which is what a dict does, and
    what ``to_dict(orient="index")`` refuses to do at all - would silently drop half of a
    cluster of rating changes, exactly when the signal is strongest.

    Accepts a DataFrame, a plain dict of dicts, or None, because which one comes back depends
    on the yfinance version installed.
    """
    if frame is None:
        return []
    if hasattr(frame, "to_dict") and not isinstance(frame, dict):
        try:
            if getattr(frame, "empty", False):
                return []
            labels = [str(label) for label in frame.index]
            return list(zip(labels, frame.to_dict(orient="records")))
        except (TypeError, ValueError, AttributeError):
            return []
    if isinstance(frame, dict):
        return [(str(key), value) for key, value in frame.items() if isinstance(value, dict)]
    return []


def _frame_rows(frame):
    """Records keyed by index label, for the frames whose index is a forecast period."""
    rows = {}
    for label, row in _frame_records(frame):
        rows.setdefault(label, row)
    return rows


def _pick_period(rows):
    """The first forecast horizon actually present, preferring the current fiscal year."""
    for period in PREFERRED_PERIODS:
        if period in rows and isinstance(rows[period], dict):
            return period, rows[period]
    for key, value in rows.items():
        if isinstance(value, dict):
            return key, value
    return None, {}


def _column(row, *names):
    """Case- and spacing-insensitive column lookup, since these names drift by version."""
    normalized = {str(key).replace(" ", "").replace("_", "").lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.replace(" ", "").replace("_", "").lower())
        if value is not None:
            return value
    return None


def revision_breadth(eps_revisions):
    """Net share of estimate revisions that were upward in the last 30 days, -1 to 1.

    Breadth rather than a raw count: three upgrades out of three analysts is a different
    statement from three out of thirty, and only the ratio is comparable across coverage
    levels.
    """
    period, row = _pick_period(_frame_rows(eps_revisions))
    if not row:
        return None, None
    up = _number(_column(row, "upLast30days", "up last 30 days"))
    down = _number(_column(row, "downLast30days", "down last 30 days"))
    if up is None and down is None:
        return None, None
    up, down = up or 0.0, down or 0.0
    total = up + down
    if total <= 0:
        # Zero revisions is a real observation - nobody moved - not missing data. Neutral
        # breadth is the honest reading of it.
        return 0.0, period
    return round((up - down) / total, 4), period


def eps_revision_magnitude(eps_trend):
    """Fractional change in the consensus EPS estimate over the last 30 days.

    Magnitude matters independently of breadth: ten analysts nudging an estimate by a cent is
    not the same event as three of them raising it 14%.
    """
    period, row = _pick_period(_frame_rows(eps_trend))
    if not row:
        return None, None
    current = _number(_column(row, "current"))
    prior = _number(_column(row, "30daysAgo", "30 days ago"))
    if current is None or prior is None or prior == 0:
        return None, None
    # A sign flip makes a percentage change meaningless (a loss narrowing from -1.00 to 0.50
    # is not "150% better" in any usable sense), so it is reported as unavailable instead.
    if (current > 0) != (prior > 0):
        return None, period
    return round(current / prior - 1, 4), period


def net_upgrades(upgrades_downgrades, *, now=None, window_days=UPGRADE_WINDOW_DAYS):
    """Upgrades minus downgrades inside the window, ignoring reiterations and initiations.

    A reiteration is not new information and an initiation is coverage, not a change of mind;
    counting either would let a busy coverage calendar look like rising conviction.
    """
    rows = _frame_records(upgrades_downgrades)
    if not rows:
        return None
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    up = down = 0
    for stamp, row in rows:
        when = _parse_timestamp(stamp) or _parse_timestamp(_column(row, "GradeDate", "grade date"))
        if when is None or when < cutoff:
            continue
        action = str(_column(row, "Action", "action") or "").strip().lower()
        if action in {"up", "upgrade"}:
            up += 1
        elif action in {"down", "downgrade"}:
            down += 1
    if not up and not down:
        return None
    return up - down


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    for parse in (
        lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
        lambda raw: datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc),
    ):
        try:
            parsed = parse(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def consensus_target(analyst_price_targets):
    """Mean consensus price target, whichever shape this yfinance version returns."""
    targets = analyst_price_targets
    if targets is None:
        return None
    if hasattr(targets, "to_dict") and not isinstance(targets, dict):
        try:
            targets = targets.to_dict()
        except (TypeError, ValueError, AttributeError):
            return None
    if not isinstance(targets, dict):
        return None
    return _number(targets.get("mean") or targets.get("median") or targets.get("targetMeanPrice"))


def target_change(current_target, previous_target):
    """Percent drift in the consensus target since the last stored snapshot.

    Yahoo has no as-of-a-past-date endpoint for this, so the comparison point comes from this
    repository's own archive. When there is no prior snapshot the answer is genuinely unknown
    and stays None rather than being reported as no change.
    """
    current = _number(current_target)
    previous = _number(previous_target)
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 2)


def collect_estimate_detail(symbol, ticker_obj, *, previous_target=None, now=None):
    """Everything the expectation-change leg needs for one company.

    Each family is fetched in its own try/except: the analyst endpoints fail independently,
    and losing the upgrade history is not a reason to discard resolved revision data.
    """
    if ticker_obj is None:
        return {}

    def attempt(label, call):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - provider shapes vary; one gap is not fatal
            LOG.warn(f"{symbol}: Yahoo {label} unavailable ({type(exc).__name__})")
            return None

    revisions = attempt("EPS revisions", lambda: ticker_obj.get_eps_revisions())
    trend = attempt("EPS trend", lambda: ticker_obj.get_eps_trend())
    grades = attempt("upgrade/downgrade history", lambda: ticker_obj.get_upgrades_downgrades())
    targets = attempt("analyst price targets", lambda: ticker_obj.get_analyst_price_targets())

    breadth, breadth_period = revision_breadth(revisions)
    magnitude, magnitude_period = eps_revision_magnitude(trend)
    current_target = consensus_target(targets)

    detail = {
        "revision_breadth_30d": breadth,
        "eps_revision_30d_pct": magnitude,
        "net_upgrades_90d": net_upgrades(grades, now=now),
        "consensus_target": current_target,
        "target_change_30d_pct": target_change(current_target, previous_target),
        "revision_period": breadth_period or magnitude_period,
        # Stamped per company rather than per run: these are the four calls whose freshness
        # the expectation leg depends on, and a backtest has to know when each was actually
        # visible, not when the run happened to finish.
        "available_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    resolved = sum(1 for key in ("revision_breadth_30d", "eps_revision_30d_pct",
                                 "net_upgrades_90d", "target_change_30d_pct")
                   if detail[key] is not None)
    detail["inputs_resolved"] = resolved
    return detail
