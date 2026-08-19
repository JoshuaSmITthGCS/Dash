"""Statement enrichment from the local SEC EDGAR point-in-time store.

Round 4 of the methodology audit (docs/AUDIT-ROUND-4-FINDINGS.md) found that the
2026-08-06 Yahoo statement outage left the intended high-evidence fundamentals
(EV multiples, gross profitability, Piotroski, Altman) unresolved for roughly 85% of the
universe, while pipeline/data/pit/fundamentals already held 1.45M as-filed XBRL facts for
all 860 universe CIKs back to 2010. This module closes that gap offline: it adapts the
EDGAR concept rows into the exact statement shape ``fundamentals_extended.derive_extended``
consumes, so every existing derivation runs unchanged on as-filed data.

Point-in-time discipline: only facts with ``filed`` on or before the as-of date are
visible, and for one (concept, period_end) the latest such filing wins, so an amendment
becomes visible on its own filing date and never rewrites what an earlier date could see.

The adapter is a fallback, not a replacement: Yahoo statement data, when present, is
fresher (EDGAR quarterly concepts here are annual-period 10-K facts for several filers).
``merge_edgar_fallback`` fills only metrics Yahoo left as None.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from common import LOG
from fundamentals_extended import derive_extended
from pit_fundamentals_store import ShardedStore, shard_for

HERE = os.path.dirname(os.path.abspath(__file__))
PIT_DIR = os.path.join(HERE, "data", "pit")
FUNDAMENTALS_DIR = os.path.join(PIT_DIR, "fundamentals")
ENTITY_MAP = os.path.join(PIT_DIR, "entity_map.json")

# EDGAR concept -> the Yahoo statement row name fundamentals_extended.ALIASES resolves.
INCOME_ROWS = {
    "revenue": "Total Revenue",
    "cost_of_revenue": "Cost Of Revenue",
    "gross_profit": "Gross Profit",
    "operating_income": "Operating Income",
    "net_income": "Net Income",
    "pretax_income": "Pretax Income",
    "tax_provision": "Tax Provision",
    "interest_expense": "Interest Expense",
    "shares_diluted": "Diluted Average Shares",
    "shares_basic": "Basic Average Shares",
}
BALANCE_ROWS = {
    "retained_earnings": "Retained Earnings",
    "assets": "Total Assets",
    "liabilities": "Total Liabilities",
    "current_assets": "Current Assets",
    "current_liabilities": "Current Liabilities",
    "long_term_debt": "Long Term Debt",
    "cash": "Cash And Cash Equivalents",
    "equity": "Stockholders Equity",
    "goodwill": "Goodwill",
    "intangibles": "Other Intangible Assets",
    "receivables": "Accounts Receivable",
    "inventory": "Inventory",
}
CASHFLOW_ROWS = {
    "operating_cash_flow": "Operating Cash Flow",
    "capital_expenditure": "Capital Expenditure",
    "depreciation_amortization": "Depreciation And Amortization",
    "share_based_compensation": "Stock Based Compensation",
    "share_repurchases": "Repurchase Of Capital Stock",
}

_ANNUAL_DAYS = (330, 400)


@lru_cache(maxsize=1)
def _ticker_to_cik():
    try:
        payload = json.load(open(ENTITY_MAP, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows", [])
    return {str(r["ticker"]).upper(): str(r["cik_str"]).zfill(10) for r in rows
            if r.get("ticker") and r.get("cik_str") is not None}


@lru_cache(maxsize=128)
def _shard_rows(shard):
    """Light per-shard cache: {cik: [(concept, period_end, filed, period_days, value)]}."""
    from datetime import date

    def days_between(start, end):
        if not start or not end:
            return None
        try:
            return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
        except ValueError:
            return None

    by_cik = {}
    for row in ShardedStore(FUNDAMENTALS_DIR).load_compact(shard):
        by_cik.setdefault(row.get("cik"), []).append((
            row.get("concept"), row.get("period_end"), row.get("filed"),
            days_between(row.get("period_start"), row.get("period_end")),
            row.get("value")))
    return by_cik


def _annual_facts_as_of(cik, as_of):
    """{(concept, period_end): value} using only filings visible on the as-of date."""
    best = {}
    for concept, period_end, filed, days, value in _shard_rows(shard_for(cik)).get(cik, []):
        if not filed or filed > as_of or concept is None or period_end is None:
            continue
        is_balance = concept in BALANCE_ROWS
        if not is_balance and not (isinstance(days, (int, float))
                                   and _ANNUAL_DAYS[0] <= days <= _ANNUAL_DAYS[1]):
            continue
        key = (concept, period_end)
        prior = best.get(key)
        if prior is None or filed > prior[0]:
            best[key] = (filed, value)
    return {key: value for key, (_filed, value) in best.items()}


def _statements(facts):
    """Build {"income": ..., "balance": ..., "cashflow": ...} in statement_series shape."""
    fiscal_ends = sorted({pe for (concept, pe) in facts if concept == "revenue"},
                         reverse=True)[:5]
    if not fiscal_ends:
        fiscal_ends = sorted({pe for (_c, pe) in facts}, reverse=True)[:5]
    if not fiscal_ends:
        return None

    def series(concept):
        return [facts.get((concept, pe)) for pe in fiscal_ends]

    def build(mapping):
        return {"periods": list(fiscal_ends),
                "rows": {yahoo_name: series(concept)
                         for concept, yahoo_name in mapping.items()}}

    income = build(INCOME_ROWS)
    balance = build(BALANCE_ROWS)
    cashflow = build(CASHFLOW_ROWS)

    def combine(a, b, op):
        return [op(x, y) if x is not None and y is not None else None for x, y in zip(a, b)]

    rows_i, rows_b, rows_c = income["rows"], balance["rows"], cashflow["rows"]
    if all(v is None for v in rows_i["Gross Profit"]):
        rows_i["Gross Profit"] = combine(rows_i["Total Revenue"], rows_i["Cost Of Revenue"],
                                         lambda r, c: r - c)
    rows_i["EBITDA"] = combine(rows_i["Operating Income"],
                               rows_c["Depreciation And Amortization"],
                               lambda o, d: o + abs(d))
    short_debt = [facts.get(("short_term_debt", pe)) for pe in fiscal_ends]
    rows_b["Total Debt"] = [
        (lt or 0) + (st or 0) if lt is not None or st is not None else None
        for lt, st in zip(rows_b["Long Term Debt"], short_debt)]
    rows_b["Working Capital"] = combine(rows_b["Current Assets"],
                                        rows_b["Current Liabilities"], lambda a, l: a - l)
    rows_c["Free Cash Flow"] = combine(rows_c["Operating Cash Flow"],
                                       rows_c["Capital Expenditure"],
                                       lambda o, c: o - abs(c))
    return {"income": income, "balance": balance, "cashflow": cashflow}


_FLOW_CONCEPTS = set(INCOME_ROWS) | set(CASHFLOW_ROWS)
_YTD_KINDS = {90: (75, 105), 180: (165, 195), 270: (255, 285)}


def _all_facts_as_of(cik, as_of):
    """[(concept, period_end, period_days, value)] visible on as_of, latest filing wins."""
    best = {}
    for concept, period_end, filed, days, value in _shard_rows(shard_for(cik)).get(cik, []):
        if not filed or filed > as_of or concept is None or period_end is None:
            continue
        key = (concept, period_end, days if concept in _FLOW_CONCEPTS else None)
        prior = best.get(key)
        if prior is None or filed > prior[0]:
            best[key] = (filed, days, value)
    return [(concept, pe, days, value)
            for (concept, pe, _d), (_f, days, value) in best.items()]


def _ttm_facts_as_of(cik, as_of):
    """Trailing-twelve-month flow values plus latest balance instants, as-filed.

    Construction per flow concept: TTM = latest visible fiscal-year value plus the
    latest visible year-to-date period that starts where that fiscal year ended, minus
    the matching prior-year year-to-date. A quarter filed after the as-of date never
    enters, by the same visibility rule the annual path tests. When no post-FY quarter
    is visible the fiscal-year value stands alone, which reproduces the annual path.
    Balance concepts take the latest visible instant, quarterly or annual.
    """
    rows = _all_facts_as_of(cik, as_of)
    annual = _annual_facts_as_of(cik, as_of)
    fiscal_ends = sorted({pe for (c, pe) in annual if c == "revenue"}, reverse=True)
    if not fiscal_ends:
        fiscal_ends = sorted({pe for (_c, pe) in annual}, reverse=True)
    if not fiscal_ends:
        return None, None
    fye = fiscal_ends[0]

    from datetime import date, timedelta

    def d(iso):
        return date.fromisoformat(iso[:10])

    ttm = {}
    for concept in _FLOW_CONCEPTS:
        base = annual.get((concept, fye))
        if base is None:
            continue
        candidates = []
        for c, pe, days, value in rows:
            if c != concept or not isinstance(days, (int, float)) or value is None:
                continue
            for _kind, (lo, hi) in _YTD_KINDS.items():
                if lo <= days <= hi:
                    start = d(pe) - timedelta(days=days)
                    if timedelta(days=-5) <= (start - d(fye)) <= timedelta(days=20):
                        candidates.append((pe, days, value))
        ttm_value = base
        for pe, days, ytd_cur in sorted(candidates, key=lambda x: x[0], reverse=True):
            prior_end = d(pe) - timedelta(days=365)
            prior = [v for c, p, dd, v in rows
                     if c == concept and isinstance(dd, (int, float))
                     and abs(dd - days) <= 10 and v is not None
                     and abs((d(p) - prior_end).days) <= 10]
            if prior:
                ttm_value = base + ytd_cur - prior[0]
                break
        ttm[concept] = ttm_value

    balance_latest = {}
    balance_concepts = set(BALANCE_ROWS) | {"short_term_debt", "retained_earnings"}
    for c, pe, _days, value in rows:
        if c in balance_concepts and value is not None:
            if c not in balance_latest or pe > balance_latest[c][0]:
                balance_latest[c] = (pe, value)
    return ttm, {c: v for c, (_pe, v) in balance_latest.items()}


def edgar_ttm_statements(symbol, as_of):
    """Statement dicts where index 0 is the as-filed TTM row and 1..4 are prior FYs."""
    cik = _ticker_to_cik().get(str(symbol).upper())
    if not cik:
        return None
    annual_stmts = _statements(_annual_facts_as_of(cik, as_of))
    if annual_stmts is None:
        return None
    ttm, balance_now = _ttm_facts_as_of(cik, as_of)
    if not ttm:
        return annual_stmts
    result = {}
    for name, mapping in (("income", INCOME_ROWS), ("cashflow", CASHFLOW_ROWS)):
        stmt = annual_stmts[name]
        rows = {label: [ttm.get(concept, series[0] if series else None)] + list(series)
                for concept, label in mapping.items()
                for series in [stmt["rows"].get(label, [])]}
        result[name] = {"periods": [as_of] + stmt["periods"], "rows": rows}
    bal = annual_stmts["balance"]
    result["balance"] = {"periods": [as_of] + bal["periods"],
                         "rows": {label: [balance_now.get(concept,
                                                          series[0] if series else None)]
                                  + list(series)
                                  for concept, label in BALANCE_ROWS.items()
                                  for series in [bal["rows"].get(label, [])]}}
    # Derived rows, mirroring _statements().
    for name in ("income", "cashflow", "balance"):
        rows = result[name]["rows"]
        n = len(result[name]["periods"])
        for label in list(rows):
            rows[label] = (rows[label] + [None] * n)[:n]
    ri, rb, rc = result["income"]["rows"], result["balance"]["rows"], result["cashflow"]["rows"]

    def combine(a, b, op):
        return [op(x, y) if x is not None and y is not None else None for x, y in zip(a, b)]

    if all(v is None for v in ri.get("Gross Profit", [None])):
        ri["Gross Profit"] = combine(ri["Total Revenue"], ri["Cost Of Revenue"], lambda r, c: r - c)
    ri["EBITDA"] = combine(ri["Operating Income"], rc["Depreciation And Amortization"],
                           lambda o, dd: o + abs(dd))
    st_now = (balance_now or {}).get("short_term_debt")
    rb["Total Debt"] = [
        ((lt or 0) + (st_now or 0)) if index == 0 and (lt is not None or st_now is not None)
        else lt
        for index, lt in enumerate(rb["Long Term Debt"])]
    rb["Working Capital"] = combine(rb["Current Assets"], rb["Current Liabilities"],
                                    lambda a, l: a - l)
    rc["Free Cash Flow"] = combine(rc["Operating Cash Flow"], rc["Capital Expenditure"],
                                   lambda o, c: o - abs(c))
    return result


def edgar_extended(symbol, *, as_of, market_cap=None, price=None, sector=None,
                   closes=(), volumes=()):
    """Every derivable extended metric for one company from as-filed EDGAR facts."""
    cik = _ticker_to_cik().get(str(symbol).upper())
    if not cik:
        return None
    facts = _annual_facts_as_of(cik, as_of)
    annual = _statements(facts)
    if annual is None:
        return None
    result = derive_extended(annual=annual, info={}, market_cap=market_cap, price=price,
                             sector=sector, closes=closes, volumes=volumes)
    result["statement_source"] = "sec_edgar_pit"
    return result


def merge_edgar_fallback(symbol, result, snapshot, *, as_of, diagnostics=None):
    """Fill metrics the provider path left missing, from the local EDGAR store.

    Never raises, never overwrites a resolved provider value, and can be disabled with
    DISABLE_EDGAR_ENRICHMENT=1. Adds ``statement_source`` describing the mix.
    """
    if os.getenv("DISABLE_EDGAR_ENRICHMENT", "").lower() in {"1", "true", "yes"}:
        return result
    try:
        fallback = edgar_extended(
            symbol, as_of=as_of, market_cap=snapshot.get("market_cap"),
            price=snapshot.get("price"), sector=snapshot.get("sector"))
    except Exception as exc:  # noqa: BLE001 - enrichment fallback must never sink the symbol
        LOG.warn(f"{symbol}: EDGAR PIT fallback failed ({type(exc).__name__}: {exc})")
        return result
    if not fallback:
        return result
    result = dict(result or {})
    filled = 0
    for key, value in fallback.items():
        if key in ("statement_source",):
            continue
        if result.get(key) is None and value is not None:
            result[key] = value
            filled += 1
    if filled:
        result["statement_source"] = ("yahoo+sec_edgar_pit"
                                      if result.get("statement_periods") else "sec_edgar_pit")
        if diagnostics is not None:
            diagnostics["edgar_fallback_filled"] = (
                diagnostics.get("edgar_fallback_filled", 0) + 1)
    return result
