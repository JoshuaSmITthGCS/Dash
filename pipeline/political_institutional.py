"""Rank a universe by disclosed political and institutional buying alone.

This is the "just follow the trades" signal: no fundamentals, no momentum, no research
score. A ticker earns a place only because members of Congress disclosed buying it or
because curated active 13F managers added to it - the two "somebody who might know
something already bought this" inputs the pipeline already collects.

Neither side's scoring math is reimplemented here. ``congress_signal.score_congressional
_buying`` and ``institutional_ownership.score_institutional_ownership`` are the audited
implementations the research score itself uses, and this module calls them unchanged so a
follow-the-trades portfolio and the research score can never disagree about what a given
disclosure is worth. What this module adds is the two things a *standalone* strategy needs
and a score modifier does not:

* **A point-in-time visibility gate.** A modifier scores whatever the live screen holds.
  A backtest must not. ``visible_congress_rows`` and ``visible_institutional_rows`` filter
  on ``disclosure_date`` and 13F ``as_of`` (the filing date), never on ``transaction_date``
  or the quarter end - the dates the information became public, not the dates the trades
  happened. A senator's April purchase disclosed in July is unusable in May, and reading it
  then is the single easiest way to manufacture a spectacular fake backtest here, because
  the disclosure lag in this store runs to 465 days.
* **A cross-sectional ranking.** Modifiers return points per ticker; a portfolio needs an
  ordering. Points from the two sources are summed at their native scale, which is the same
  convention ``advisor_engine.apply_modifiers`` uses when it adds unrelated modifiers
  together, and each side's contribution is kept on the row so the sum stays decomposable.

**The evidence base is weak and gets weaker.** congress_signal.py's own docstring records
that the Ziobrowski abnormal-return findings predate the STOCK Act's mandatory-disclosure
regime, and 13F positions are already 45+ days stale at filing. Nothing here asserts the
strategy works; it exists so it can be measured instead of argued about.
"""

from __future__ import annotations

from datetime import date, datetime

from build_congress_screen import is_equity_purchase
from congress_signal import DEFAULTS as CONGRESS_DEFAULTS, score_congressional_buying
from institutional_ownership import decay

# The caps advisor_engine applies to each family, reported alongside the score so a reader
# can see how much of the ordering each source is able to move.
POLITICAL_POINT_CAP = CONGRESS_DEFAULTS["max_points"] + CONGRESS_DEFAULTS["extraordinary_bonus"]
INSTITUTIONAL_POINT_CAP = 3.0
INSTITUTIONAL_POINT_FLOOR = -2.0


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def visible_congress_rows(rows, as_of):
    """Disclosed equity purchases a reader could have seen on ``as_of``.

    Filtered on ``disclosure_date`` because that is publication. A row with no disclosure
    date is dropped rather than falling back to ``transaction_date``: the fallback would
    silently date a trade to when it happened, which is exactly the leak this gate exists
    to prevent.
    """
    cutoff = _as_date(as_of)
    if cutoff is None:
        return []
    visible = []
    for row in rows or []:
        disclosed = _as_date(row.get("disclosure_date"))
        if disclosed is None or disclosed > cutoff:
            continue
        if not is_equity_purchase(row):
            continue
        visible.append(row)
    return visible


def visible_institutional_rows(rows, as_of):
    """13F rows whose filing was public on ``as_of``.

    ``as_of`` on a published institutional row is the filing date (build_institutional_
    screen.build_results), not the quarter end it reports, so this compares like with like.
    """
    cutoff = _as_date(as_of)
    if cutoff is None:
        return []
    visible = []
    for row in rows or []:
        filed = _as_date(row.get("as_of"))
        if filed is None or filed > cutoff:
            continue
        visible.append(row)
    return visible


def institutional_points(row, as_of):
    """A filed 13F row's lag-decayed, clamped contribution, or 0.0 when it has none."""
    magnitude = row.get("undecayed_magnitude")
    filed = _as_date(row.get("as_of"))
    cutoff = _as_date(as_of)
    if magnitude is None or filed is None or cutoff is None:
        return 0.0
    weight = decay((cutoff - filed).days)
    if not weight:
        return 0.0
    points = float(magnitude) * weight
    return round(max(INSTITUTIONAL_POINT_FLOOR, min(INSTITUTIONAL_POINT_CAP, points)), 4)


def rank_disclosed_trades(congress_rows, institutional_rows, *, as_of, universe=None,
                          minimum_score=0.0):
    """Rank tickers by summed political and institutional points visible on ``as_of``.

    ``universe`` optionally restricts the result to tradable symbols; without it every
    disclosed ticker is eligible, including ones no price series exists for. Rows scoring
    at or below ``minimum_score`` are dropped rather than ranked, so a period in which
    nobody disclosed anything returns nothing at all instead of an arbitrary ordering of
    zeros - the caller then holds cash, which is the honest representation of "this
    strategy had no signal this month".
    """
    congress = visible_congress_rows(congress_rows, as_of)
    institutional = visible_institutional_rows(institutional_rows, as_of)
    allowed = {symbol.upper() for symbol in universe} if universe else None

    tickers = {str(row.get("symbol") or "").upper() for row in congress}
    tickers |= {str(row.get("ticker") or "").upper() for row in institutional}
    tickers.discard("")

    institutional_by_ticker = {}
    for row in institutional:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            institutional_by_ticker.setdefault(ticker, row)

    disclosed_value = {}
    for row in congress:
        ticker = str(row.get("symbol") or "").upper()
        if ticker:
            disclosed_value[ticker] = disclosed_value.get(ticker, 0.0) + float(row.get("amount_lower") or 0)

    ranked = []
    for ticker in sorted(tickers):
        if allowed is not None and ticker not in allowed:
            continue
        political, political_detail = score_congressional_buying(congress, ticker, as_of=_as_date(as_of))
        institutional_row = institutional_by_ticker.get(ticker)
        institutional_score = institutional_points(institutional_row, as_of) if institutional_row else 0.0
        total = round(political + institutional_score, 4)
        if total <= minimum_score:
            continue
        ranked.append({
            "ticker": ticker,
            "score": total,
            "political_points": round(political, 4),
            "institutional_points": institutional_score,
            "members_buying": political_detail.get("members_buying") or 0,
            "extraordinary_members": political_detail.get("extraordinary_members") or 0,
            "days_since_latest_disclosure": political_detail.get("days_since_latest"),
            "disclosed_purchase_value_lower": round(disclosed_value.get(ticker, 0.0), 2),
            "managers_added": (institutional_row or {}).get("managers_added") or 0,
            "managers_dropped": (institutional_row or {}).get("managers_dropped") or 0,
            "institutional_flag": (institutional_row or {}).get("flag"),
            "institutional_filed": (institutional_row or {}).get("as_of"),
        })
    # Score alone leaves large ties: breadth is integer-valued and most names are bought by
    # exactly one member, so a top-20 cut taken on score plus ticker is an *alphabetical*
    # slice of the tied block - AAPL and ABBV get in on their names, not their disclosures.
    # Freshness breaks the tie first (the decay curve congress_signal already argues for,
    # read at finer resolution than the score's rounding preserves), then disclosed size,
    # then ticker so the result stays deterministic.
    ranked.sort(key=lambda row: (
        -row["score"],
        row["days_since_latest_disclosure"] if row["days_since_latest_disclosure"] is not None else 10**6,
        -row["disclosed_purchase_value_lower"],
        row["ticker"],
    ))
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    return ranked


def coverage(congress_rows, institutional_rows):
    """What history actually exists, for disclosure on any report built from this module."""
    congress_dates = sorted(str(row.get("disclosure_date"))[:10] for row in congress_rows or []
                            if row.get("disclosure_date"))
    filed_dates = sorted(str(row.get("as_of"))[:10] for row in institutional_rows or []
                         if row.get("as_of"))
    return {
        "congress_disclosures": len(congress_rows or []),
        "congress_first_disclosure": congress_dates[0] if congress_dates else None,
        "congress_last_disclosure": congress_dates[-1] if congress_dates else None,
        "congress_distinct_disclosure_months": len({value[:7] for value in congress_dates}),
        "institutional_rows": len(institutional_rows or []),
        "institutional_first_filed": filed_dates[0] if filed_dates else None,
        "institutional_last_filed": filed_dates[-1] if filed_dates else None,
        "institutional_distinct_filing_dates": len(set(filed_dates)),
    }
