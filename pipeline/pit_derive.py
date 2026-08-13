"""Point-in-time fundamentals: raw filed facts into scoreable ratios, as of any date.

The store holds what each company *filed* and when. This turns that into the quantities a
model ranks on -- margins, returns on capital, leverage, accruals, growth -- computed from
only the filings accepted on or before a given date. It is the layer between
``pipeline/data/pit/fundamentals/`` and any honest backtest.

Three rules, and they are the whole design:

1. **Nothing is visible before its filing date.** Every lookup goes through
   ``edgar_facts.as_of``, which selects the latest period whose filing had been accepted by
   the as-of date, and within a period the latest filing -- so an amendment supersedes the
   original from the date the amendment itself was filed, not retroactively.
2. **Trailing twelve months is built from as-reported quarters, not from a stale annual.**
   Filers tag quarters, six-month and nine-month cumulatives, and full years. A naive "latest
   annual" reading is up to a year out of date for eleven months of every year. TTM here sums
   the four most recent non-overlapping quarters, synthesising the missing fourth quarter
   from ``annual - nine_months`` where a filer reports no standalone Q4 (most do not).
3. **A ratio whose inputs are missing is absent, not defaulted.** Every derived value is
   ``None`` unless everything it needs resolved, and ``inputs_missing`` names what was
   absent. There is no neutral fundamental.

What this deliberately does not do: score, rank, or compare. It produces one company's
fundamentals as of one date. Cross-sectional work belongs above it.
"""

from datetime import date, timedelta

from edgar_facts import as_of

# Concepts read as instantaneous balances rather than flows.
INSTANT_CONCEPTS = ("assets", "current_assets", "liabilities", "current_liabilities",
                    "equity", "cash", "inventory", "receivables", "goodwill", "intangibles",
                    "long_term_debt", "short_term_debt")

# Concepts accumulated over a trailing twelve months.
FLOW_CONCEPTS = ("revenue", "cost_of_revenue", "gross_profit", "operating_income",
                 "net_income", "pretax_income", "tax_provision", "interest_expense",
                 "operating_cash_flow", "capital_expenditure", "depreciation_amortization",
                 "share_based_compensation", "dividends_paid", "share_repurchases")

# A four-quarter span this far from 365 days is not a trailing year.
TTM_DAY_TOLERANCE = 45


def _latest_per_period(rows, when):
    """One value per period, restatement-aware: the newest filing accepted by ``when``."""
    cutoff = str(when)[:10]
    chosen = {}
    for row in rows:
        if str(row.get("available_at"))[:10] > cutoff:
            continue
        key = (row.get("period_start"), row.get("period_end"))
        current = chosen.get(key)
        if current is None or str(row["filed"]) > str(current["filed"]):
            chosen[key] = row
    return chosen


def _synthesised_fourth_quarters(periods):
    """Q4 as ``annual - nine_months`` for filers that report no standalone fourth quarter.

    Most annual filers do not tag Q4 separately: the 10-K carries the full year and the
    third 10-Q carried nine months. Without this, TTM for those companies would be missing a
    quarter for a third of every year, or would silently fall back to a year-old annual.
    """
    annuals = {row["period_end"]: row for (start, end), row in periods.items()
               if row.get("period_type") == "annual" and start}
    nine_months = {row["period_start"]: row for (start, end), row in periods.items()
                   if row.get("period_type") == "nine_months" and start}
    synthesised = {}
    for end, annual in annuals.items():
        nine = nine_months.get(annual["period_start"])
        if not nine or annual.get("value") is None or nine.get("value") is None:
            continue
        start = nine["period_end"]
        if (start, end) in periods:
            continue
        synthesised[(start, end)] = {
            **annual,
            "period_start": start,
            "period_end": end,
            "period_type": "quarter",
            "value": annual["value"] - nine["value"],
            # The synthesised quarter is only knowable once *both* its inputs were filed.
            "available_at": max(str(annual["available_at"]), str(nine["available_at"])),
            "filed": max(str(annual["filed"]), str(nine["filed"])),
            "derived_from": "annual_minus_nine_months",
        }
    return synthesised


def trailing_twelve_months(rows, when):
    """Sum of the four most recent non-overlapping quarters knowable at ``when``.

    Returns ``(value, detail)``. ``detail`` names the method, the periods used and the span
    in days, so a consumer can see whether a figure is a true trailing year, a synthesised
    one, or a fallback to the latest filed annual.
    """
    periods = _latest_per_period(rows, when)
    if not periods:
        return None, {"method": "unavailable", "reason": "no filings accepted by this date"}
    periods = {**periods, **_synthesised_fourth_quarters(periods)}
    quarters = sorted(
        (row for (start, end), row in periods.items()
         if row.get("period_type") == "quarter" and start),
        key=lambda row: row["period_end"], reverse=True)

    selected, cursor = [], None
    for row in quarters:
        # `>` not `>=`: SEC period conventions are inconsistent about boundaries. Apple's
        # Q3 FY2024 ends 2024-06-29 and the quarter after it starts on that same date, so a
        # `>=` test rejected an adjacent quarter as overlapping, left a hole in the year, and
        # silently fell back to a stale annual for a third of every year.
        if cursor is not None and row["period_end"] > cursor:
            continue  # genuinely overlaps a quarter already taken
        selected.append(row)
        cursor = row["period_start"]
        if len(selected) == 4:
            break
    if len(selected) == 4:
        try:
            span = (date.fromisoformat(selected[0]["period_end"])
                    - date.fromisoformat(selected[-1]["period_start"])).days
        except (TypeError, ValueError):
            span = None
        if span is not None and abs(span - 365) <= TTM_DAY_TOLERANCE:
            return sum(row["value"] for row in selected), {
                "method": "four_quarters",
                "span_days": span,
                "periods": [row["period_end"] for row in reversed(selected)],
                "synthesised_quarters": [row["period_end"] for row in selected
                                         if row.get("derived_from")],
                "as_reported_through": selected[0]["period_end"],
                "latest_filing_used": max(str(row["filed"]) for row in selected),
            }
    annual = as_of(list(rows), when, period_type="annual")
    if annual is not None:
        return annual["value"], {
            "method": "latest_annual",
            "periods": [annual["period_end"]],
            "as_reported_through": annual["period_end"],
            "latest_filing_used": annual["filed"],
            "caveat": "no four contiguous quarters were available, so this is the most "
                      "recent full year filed and may be up to a year stale",
        }
    return None, {"method": "unavailable",
                  "reason": "neither four quarters nor a filed annual period"}


def _ratio(numerator, denominator, *, allow_negative_denominator=False):
    if numerator is None or denominator in (None, 0):
        return None
    if denominator < 0 and not allow_negative_denominator:
        return None
    return numerator / denominator


def derive(observations, when, *, cik=None):
    """One company's point-in-time fundamentals as of ``when``.

    ``observations`` is that company's rows from the store. Every output is either a real
    value derived from filings accepted by ``when``, or ``None`` with its absence recorded in
    ``inputs_missing``.
    """
    by_concept = {}
    for row in observations:
        by_concept.setdefault(row.get("concept"), []).append(row)

    flows, flow_detail = {}, {}
    for concept in FLOW_CONCEPTS:
        value, detail = trailing_twelve_months(by_concept.get(concept, []), when)
        flows[concept] = value
        flow_detail[concept] = detail

    instants, instant_detail = {}, {}
    for concept in INSTANT_CONCEPTS:
        chosen = as_of(by_concept.get(concept, []), when, period_type="instant")
        instants[concept] = chosen["value"] if chosen else None
        instant_detail[concept] = ({"period_end": chosen["period_end"], "filed": chosen["filed"]}
                                   if chosen else None)

    revenue = flows["revenue"]
    net_income = flows["net_income"]
    operating_income = flows["operating_income"]
    equity = instants["equity"]
    assets = instants["assets"]
    debt = None
    if instants["long_term_debt"] is not None or instants["short_term_debt"] is not None:
        debt = (instants["long_term_debt"] or 0) + (instants["short_term_debt"] or 0)
    free_cash_flow = None
    if flows["operating_cash_flow"] is not None and flows["capital_expenditure"] is not None:
        free_cash_flow = flows["operating_cash_flow"] - abs(flows["capital_expenditure"])
    invested_capital = None
    if equity is not None and debt is not None:
        invested_capital = equity + debt - (instants["cash"] or 0)
    # NOPAT rather than net income: return on invested capital should not move with the
    # capital structure it is meant to be independent of.
    nopat = None
    if operating_income is not None:
        tax_rate = _ratio(flows["tax_provision"], flows["pretax_income"])
        nopat = operating_income * (1 - tax_rate) if tax_rate is not None and 0 <= tax_rate < 1 \
            else operating_income

    metrics = {
        "revenue_ttm": revenue,
        "net_income_ttm": net_income,
        "operating_income_ttm": operating_income,
        "free_cash_flow_ttm": free_cash_flow,
        "assets": assets,
        "equity": equity,
        "total_debt": debt,
        "invested_capital": invested_capital,
        "profit_margin": _ratio(net_income, revenue),
        "operating_margin": _ratio(operating_income, revenue),
        "gross_margin": _ratio(flows["gross_profit"], revenue),
        "return_on_equity": _ratio(net_income, equity),
        "return_on_assets": _ratio(net_income, assets),
        "return_on_invested_capital": _ratio(nopat, invested_capital),
        "debt_to_equity": _ratio(debt, equity),
        "current_ratio": _ratio(instants["current_assets"], instants["current_liabilities"]),
        "cash_conversion": _ratio(free_cash_flow, net_income),
        # Sloan's accrual: the part of earnings that never became cash, scaled by assets.
        "accruals_ratio": (_ratio(net_income - flows["operating_cash_flow"], assets)
                           if None not in (net_income, flows["operating_cash_flow"], assets)
                           else None),
        "capex_to_depreciation": (_ratio(abs(flows["capital_expenditure"]),
                                         flows["depreciation_amortization"])
                                  if flows["capital_expenditure"] is not None else None),
        "stock_comp_to_revenue": _ratio(flows["share_based_compensation"], revenue),
        "interest_coverage": _ratio(operating_income, abs(flows["interest_expense"])
                                    if flows["interest_expense"] else None),
    }
    missing = sorted(name for name, value in metrics.items() if value is None)
    return {
        "cik": cik,
        "as_of": str(when)[:10],
        "metrics": metrics,
        # The levels the ratios above were built from, published so a consumer can form its
        # own ratios -- enterprise value, tangible book, EBITDA -- without re-deriving the
        # trailing twelve months. Absent inputs stay absent here too.
        "components": {**flows, **instants, "free_cash_flow": free_cash_flow,
                       "nopat": nopat, "invested_capital": invested_capital},
        "inputs_missing": missing,
        "coverage": round(1 - len(missing) / len(metrics), 3),
        "flow_detail": flow_detail,
        "instant_detail": instant_detail,
        "as_reported_through": (flow_detail.get("revenue") or {}).get("as_reported_through"),
        "latest_filing_used": (flow_detail.get("revenue") or {}).get("latest_filing_used"),
    }


def growth(observations, when, *, concept="revenue", years=1):
    """Year-over-year growth of a trailing-twelve-month flow, both legs point-in-time.

    The prior-year leg is evaluated as of *that* date, not with today's knowledge, so a
    figure restated since is not retroactively applied to the comparison.
    """
    rows = [row for row in observations if row.get("concept") == concept]
    current, current_detail = trailing_twelve_months(rows, when)
    try:
        earlier_date = date.fromisoformat(str(when)[:10]) - timedelta(days=365 * years)
    except ValueError:
        return None, {"method": "unavailable", "reason": "unparseable as-of date"}
    prior, prior_detail = trailing_twelve_months(rows, earlier_date.isoformat())
    if current is None or prior is None or prior == 0:
        return None, {"method": "unavailable", "current": current_detail, "prior": prior_detail}
    return (current - prior) / abs(prior), {
        "method": "ttm_over_ttm",
        "current": current_detail,
        "prior": prior_detail,
        "prior_as_of": earlier_date.isoformat(),
    }
