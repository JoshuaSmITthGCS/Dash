"""Derive quality, capital-allocation, accounting-integrity, and market-structure metrics.

Two layers, deliberately separated:

  * ``statement_series`` / ``extended_inputs`` adapt yfinance objects into plain dicts.
  * every ``derive_*`` function below is pure, so the arithmetic is unit-tested offline.

Every metric returns None when its inputs are missing or nonsensical. Downstream scoring
reweights around missing values rather than assuming a neutral reading, so a company is
never rewarded for hiding a number.
"""

from datetime import datetime, timezone

from canonical_metrics import Observation

# Line-item aliases. yfinance normalizes statement rows, but names still drift between
# filers and between annual/quarterly frames, so each concept lists its known spellings.
ALIASES = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "cost_of_revenue": ("Cost Of Revenue", "Cost Of Goods Sold"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income", "Total Operating Income As Reported", "EBIT"),
    "ebit": ("EBIT", "Operating Income"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "net_income": ("Net Income", "Net Income Common Stockholders",
                   "Net Income From Continuing Operation Net Minority Interest"),
    "pretax_income": ("Pretax Income", "Income Before Tax"),
    "tax_provision": ("Tax Provision", "Income Tax Expense"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating",
                         "Net Interest Income Expense"),
    "diluted_shares": ("Diluted Average Shares", "Basic Average Shares"),
    "total_assets": ("Total Assets",),
    "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
    "current_assets": ("Current Assets", "Total Current Assets"),
    "current_liabilities": ("Current Liabilities", "Total Current Liabilities"),
    "total_debt": ("Total Debt",),
    "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
    "equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    "retained_earnings": ("Retained Earnings",),
    "working_capital": ("Working Capital",),
    "goodwill": ("Goodwill",),
    "intangibles": ("Other Intangible Assets", "Goodwill And Other Intangible Assets"),
    "receivables": ("Accounts Receivable", "Receivables", "Gross Accounts Receivable"),
    "inventory": ("Inventory",),
    "shares_outstanding": ("Ordinary Shares Number", "Share Issued"),
    "operating_cash_flow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    "free_cash_flow": ("Free Cash Flow",),
    "capex": ("Capital Expenditure", "Purchase Of PPE"),
    "depreciation": ("Depreciation And Amortization", "Depreciation Amortization Depletion",
                     "Reconciled Depreciation"),
    "stock_comp": ("Stock Based Compensation",),
    "buybacks": ("Repurchase Of Capital Stock",),
    # REIT-specific: FFO adds back real-estate D&A and backs out property-sale gains (Nareit
    # definition). yfinance rarely tags the gain line separately for a REIT, so it is treated
    # as an optional adjustment -- FFO still computes without it, just without that add-back.
    "gain_on_sale_of_real_estate": ("Gain On Sale Of Business", "Net Gains Losses On Sale Of "
                                    "Investments Real Estate", "Gain On Sale Of Investment "
                                    "Real Estate", "Gains Losses On Disposition Of Assets"),
}

FINANCIAL_SECTORS = ("Financial Services", "Financials", "Financial")

# Altman's original 1968 Z-score was estimated on publicly traded *manufacturers*. Applied
# to an asset-light software company it reports a misleadingly low score, because the model
# leans on asset turnover and working capital that such a company structurally does not
# carry. Altman's own Z'' revision drops the asset-turnover term and reweights the rest for
# non-manufacturers, so each sector gets the variant it was fitted for - and financials get
# neither, because the model has no meaning for a leveraged balance sheet by design.
MANUFACTURING_SECTORS = ("Industrials", "Basic Materials", "Energy", "Materials",
                         "Consumer Defensive", "Utilities")


# ---------------- adapters ----------------

def statement_series(frame):
    """Turn a yfinance statement DataFrame into {"periods": [...], "rows": {name: [newest-first]}}."""
    if frame is None or getattr(frame, "empty", True):
        return {"periods": [], "rows": {}}
    columns = list(frame.columns)
    order = sorted(range(len(columns)), key=lambda i: str(columns[i]), reverse=True)
    rows = {}
    for position, name in enumerate(frame.index):
        values = []
        for i in order:
            try:
                value = float(frame.iloc[position, i])
            except (TypeError, ValueError):
                value = None
            values.append(None if value is None or value != value else value)  # drop NaN
        rows.setdefault(str(name), values)
    return {"periods": [str(columns[i])[:10] for i in order], "rows": rows}


def extended_inputs(ticker_obj, quarterly=False):
    """Collect the statement frames one company at a time. Never raises.

    Quarterly frames triple the request count per symbol, so they stay opt-in; every metric
    here is computed from annual statements, which is also the period filers restate least.
    """
    def frame(attr):
        try:
            return statement_series(getattr(ticker_obj, attr))
        except Exception:  # noqa: BLE001 - a missing statement must not sink the symbol
            return {"periods": [], "rows": {}}

    empty = {"periods": [], "rows": {}}
    return {
        "annual": {"income": frame("income_stmt"), "balance": frame("balance_sheet"),
                   "cashflow": frame("cashflow")},
        "quarterly": {"income": frame("quarterly_income_stmt"),
                      "balance": frame("quarterly_balance_sheet"),
                      "cashflow": frame("quarterly_cashflow")} if quarterly else
                     {"income": empty, "balance": empty, "cashflow": empty},
    }


# ---------------- small numeric helpers ----------------

def line(statement, concept):
    """Values for a concept, newest period first. Empty list when absent."""
    rows = (statement or {}).get("rows", {})
    for alias in ALIASES.get(concept, (concept,)):
        if alias in rows:
            return rows[alias]
    lowered = {str(key).lower(): value for key, value in rows.items()}
    for alias in ALIASES.get(concept, (concept,)):
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return []


def at(values, index=0):
    """Value at a period index, or None when the period is missing or blank."""
    if not values or index >= len(values):
        return None
    return values[index]


def ratio(numerator, denominator, *, denominator_floor=0.0):
    if numerator is None or denominator is None:
        return None
    if denominator_floor is not None and abs(denominator) <= denominator_floor:
        return None
    return numerator / denominator


def rounded(value, digits=4):
    return None if value is None else round(value, digits)


def average(*values):
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def cagr(newest, oldest, years):
    """Compound annual growth. Undefined when either endpoint is non-positive."""
    if newest is None or oldest is None or years <= 0 or oldest <= 0 or newest <= 0:
        return None
    return (newest / oldest) ** (1 / years) - 1


# ---------------- profitability and quality ----------------

def effective_tax_rate(income):
    rate = ratio(at(line(income, "tax_provision")), at(line(income, "pretax_income")))
    if rate is None or not 0.0 <= rate <= 0.6:
        return 0.21  # statutory federal fallback keeps NOPAT comparable across filers
    return rate


def derive_roic(income, balance):
    """NOPAT over invested capital. Beats ROE because leverage cannot inflate it."""
    ebit = at(line(income, "ebit"))
    if ebit is None:
        return None
    nopat = ebit * (1 - effective_tax_rate(income))
    debt, equity, cash = line(balance, "total_debt"), line(balance, "equity"), line(balance, "cash")

    def invested(index):
        total_debt, total_equity = at(debt, index), at(equity, index)
        if total_equity is None:
            return None
        capital = (total_debt or 0) + total_equity - (at(cash, index) or 0)
        return capital if capital > 0 else None

    base = average(invested(0), invested(1)) or invested(0)
    return rounded(ratio(nopat, base))


def derive_cash_conversion(income, cashflow):
    """Free cash flow per dollar of reported net income - the earnings-quality litmus test."""
    fcf = at(line(cashflow, "free_cash_flow"))
    if fcf is None:
        operating, capex = at(line(cashflow, "operating_cash_flow")), at(line(cashflow, "capex"))
        fcf = None if operating is None else operating - abs(capex or 0)
    net_income = at(line(income, "net_income"))
    if net_income is None or net_income <= 0:
        return None
    return rounded(ratio(fcf, net_income))


def derive_fcf_growth(cashflow):
    """Free-cash-flow CAGR across every annual period on file (3-4 years in practice)."""
    values = [value for value in line(cashflow, "free_cash_flow") if value is not None]
    if len(values) < 3:
        return None
    return rounded(cagr(values[0], values[-1], len(values) - 1))


# Below this year-over-year revenue change, incremental margin is a ratio of a real number
# to a rounding error. THG published 89.9% and NEM 128.2% on exactly this arithmetic, both
# presented as operating leverage. See pipeline/plausibility.py and
# research/audit/CURRENT_MODEL_AUDIT.md section 5c.
MINIMUM_INCREMENTAL_REVENUE_FRACTION = 0.02


def derive_margins(income):
    """Operating margin level, its year-over-year change, and the margin on incremental revenue.

    Incremental margin is withheld, rather than published and flagged downstream, whenever
    the revenue denominator is too small to carry information -- this function is the only
    place that holds both revenue figures, so it is the only place that can tell. The
    revenue change is published alongside so a reader can see the denominator the ratio
    rests on instead of taking the ratio on trust.
    """
    revenue, operating = line(income, "revenue"), line(income, "operating_income")
    gross = line(income, "gross_profit")
    now = ratio(at(operating), at(revenue))
    prior = ratio(at(operating, 1), at(revenue, 1))
    gross_now = ratio(at(gross), at(revenue))
    gross_prior = ratio(at(gross, 1), at(revenue, 1))
    current_revenue, prior_revenue = at(revenue), at(revenue, 1)
    revenue_delta = None
    if current_revenue is not None and prior_revenue is not None:
        revenue_delta = current_revenue - prior_revenue
    change_fraction = (abs(revenue_delta) / abs(prior_revenue)
                       if revenue_delta is not None and prior_revenue else None)
    incremental = None
    denominator_too_small = (change_fraction is not None
                             and change_fraction < MINIMUM_INCREMENTAL_REVENUE_FRACTION)
    if (revenue_delta and revenue_delta > 0 and not denominator_too_small
            and at(operating) is not None and at(operating, 1) is not None):
        incremental = (at(operating) - at(operating, 1)) / revenue_delta
        # A share of an incremental revenue dollar cannot exceed that dollar. Anything
        # outside the unit interval is denominator noise however large the revenue change.
        if abs(incremental) > 1.0:
            incremental = None
    return {
        "operating_margin": rounded(now),
        "operating_margin_trend": rounded(None if now is None or prior is None else now - prior),
        "gross_margin": rounded(gross_now),
        # Semiconductor/cyclical KPI-layer research: the gross-margin bridge (level and
        # direction) is the single most decision-relevant read for a memory/foundry name,
        # where margin expansion is priced-and-mix driven, not volume driven -- see
        # docs/MODEL-CARD.md's sector-metrics section. Same construction as
        # operating_margin_trend above, just on the gross line.
        "gross_margin_trend": rounded(
            None if gross_now is None or gross_prior is None else gross_now - gross_prior),
        "incremental_margin": rounded(incremental),
        "revenue_change_fraction": rounded(change_fraction),
        "incremental_margin_unavailable_reason": (
            "revenue moved less than "
            f"{MINIMUM_INCREMENTAL_REVENUE_FRACTION * 100:.0f}% year over year, so the "
            "incremental-margin denominator carries no information"
            if denominator_too_small else None),
    }


# ---------------- financial health ----------------

def derive_interest_coverage(income):
    """EBIT per dollar of interest. No debt service at all reads as maximum comfort."""
    ebit, interest = at(line(income, "ebit")), at(line(income, "interest_expense"))
    if ebit is None:
        return None
    if interest is None or abs(interest) < 1:
        return 99.0 if ebit > 0 else None
    return rounded(ebit / abs(interest), 2)


def derive_net_debt_to_ebitda(income, balance, info=None):
    ebitda = at(line(income, "ebitda")) or (info or {}).get("ebitda")
    debt = at(line(balance, "total_debt"))
    if debt is None:
        debt = (info or {}).get("totalDebt")
    cash = at(line(balance, "cash")) or (info or {}).get("totalCash")
    if ebitda is None or debt is None or ebitda <= 0:
        return None
    return rounded((debt - (cash or 0)) / ebitda, 2)


def altman_variant_for(sector):
    """Which Z-score model a sector should be scored against, or None to suppress it."""
    if sector in FINANCIAL_SECTORS:
        return None
    return "z" if sector in MANUFACTURING_SECTORS else "z_double_prime"


def derive_altman_z(income, balance, market_cap, sector=None):
    """Solvency composite using the variant fitted for the filer's sector.

    Returns ``(score, variant)``. ``z`` is the original 1968 five-factor manufacturing model
    (distress below 1.81, safe above 2.99). ``z_double_prime`` is Altman's non-manufacturer
    revision: it drops the asset-turnover term, substitutes book equity for market
    capitalization in the leverage term, and reweights the remainder onto a different scale
    (distress below 1.1, safe above 2.6). Reporting the raw number without the variant would
    be meaningless, since the same value means opposite things under the two models.

    Financials return ``(None, None)``: the accuracy figures quoted for Z-scores were
    measured on manufacturers, and a bank's balance sheet breaks every assumption behind it.
    """
    variant = altman_variant_for(sector)
    if variant is None:
        return None, None
    assets = at(line(balance, "total_assets"))
    if not assets:
        return None, None
    working_capital = at(line(balance, "working_capital"))
    if working_capital is None:
        current_assets, current_liabilities = at(line(balance, "current_assets")), at(line(balance, "current_liabilities"))
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities
    liabilities = at(line(balance, "total_liabilities"))
    equity = at(line(balance, "equity"))

    if variant == "z":
        parts = {
            "working_capital": ratio(working_capital, assets),
            "retained_earnings": ratio(at(line(balance, "retained_earnings")), assets),
            "ebit": ratio(at(line(income, "ebit")), assets),
            "equity_to_liabilities": ratio(market_cap, liabilities),
            "asset_turnover": ratio(at(line(income, "revenue")), assets),
        }
        weights = {"working_capital": 1.2, "retained_earnings": 1.4, "ebit": 3.3,
                   "equity_to_liabilities": 0.6, "asset_turnover": 1.0}
        required = 4
    else:
        parts = {
            "working_capital": ratio(working_capital, assets),
            "retained_earnings": ratio(at(line(balance, "retained_earnings")), assets),
            "ebit": ratio(at(line(income, "ebit")), assets),
            "equity_to_liabilities": ratio(equity, liabilities),
        }
        weights = {"working_capital": 6.56, "retained_earnings": 3.26, "ebit": 6.72,
                   "equity_to_liabilities": 1.05}
        required = 3
    if sum(value is not None for value in parts.values()) < required:
        return None, None
    score = sum(weights[key] * value for key, value in parts.items() if value is not None)
    return rounded(score, 2), variant


def derive_gross_profits_to_assets(income, balance):
    """Gross profit over total assets - Novy-Marx's (JFE 2013) profitability measure.

    Novy-Marx shows gross profits-to-assets has "roughly the same power as book-to-market
    predicting the cross-section of average returns", and crucially it is *negatively*
    correlated with book-to-market, so it adds information a value screen cannot. Gross
    profit is used rather than earnings precisely because it sits above the line where
    accounting discretion, R&D expensing, and SG&A choices distort comparability.
    """
    gross = at(line(income, "gross_profit"))
    if gross is None:
        revenue, cost = at(line(income, "revenue")), at(line(income, "cost_of_revenue"))
        gross = None if revenue is None or cost is None else revenue - cost
    assets = average(at(line(balance, "total_assets")), at(line(balance, "total_assets"), 1))
    if assets is None:
        assets = at(line(balance, "total_assets"))
    return rounded(ratio(gross, assets))


def derive_asset_growth(balance):
    """Year-over-year total asset growth - the canonical investment-factor input.

    The Fama-French five-factor model's investment factor (conservative-minus-aggressive)
    says firms growing assets aggressively earn *lower* subsequent returns. Capex over
    depreciation captures only reinvestment in fixed assets; total asset growth captures
    acquisitions and balance-sheet expansion too, which is where empire-building shows up.
    """
    now, prior = at(line(balance, "total_assets")), at(line(balance, "total_assets"), 1)
    if now is None or not prior or prior <= 0:
        return None
    return rounded(now / prior - 1)


def derive_piotroski(income, balance, cashflow):
    """Nine-point fundamental-strength composite (Piotroski 2000). None below six testable points."""
    assets_now, assets_prior = at(line(balance, "total_assets")), at(line(balance, "total_assets"), 1)
    net_income, net_income_prior = at(line(income, "net_income")), at(line(income, "net_income"), 1)
    operating_cash = at(line(cashflow, "operating_cash_flow"))
    roa = ratio(net_income, assets_now)
    roa_prior = ratio(net_income_prior, assets_prior)
    long_term = ratio(at(line(balance, "long_term_debt")), assets_now)
    long_term_prior = ratio(at(line(balance, "long_term_debt"), 1), assets_prior)
    current = ratio(at(line(balance, "current_assets")), at(line(balance, "current_liabilities")))
    current_prior = ratio(at(line(balance, "current_assets"), 1), at(line(balance, "current_liabilities"), 1))
    shares, shares_prior = at(line(balance, "shares_outstanding")), at(line(balance, "shares_outstanding"), 1)
    gross = ratio(at(line(income, "gross_profit")), at(line(income, "revenue")))
    gross_prior = ratio(at(line(income, "gross_profit"), 1), at(line(income, "revenue"), 1))
    turnover = ratio(at(line(income, "revenue")), assets_now)
    turnover_prior = ratio(at(line(income, "revenue"), 1), assets_prior)

    tests = {
        "positive_roa": None if roa is None else roa > 0,
        "positive_operating_cash": None if operating_cash is None else operating_cash > 0,
        "rising_roa": None if roa is None or roa_prior is None else roa > roa_prior,
        "cash_exceeds_income": None if operating_cash is None or net_income is None else operating_cash > net_income,
        "falling_leverage": None if long_term is None or long_term_prior is None else long_term <= long_term_prior,
        "rising_liquidity": None if current is None or current_prior is None else current > current_prior,
        "no_dilution": None if shares is None or shares_prior is None else shares <= shares_prior * 1.001,
        "rising_gross_margin": None if gross is None or gross_prior is None else gross > gross_prior,
        "rising_asset_turnover": None if turnover is None or turnover_prior is None else turnover > turnover_prior,
    }
    answered = {key: value for key, value in tests.items() if value is not None}
    if len(answered) < 6:
        return None, tests
    # Scale the passed tests up to the familiar 0-9 range so partial coverage stays comparable.
    return round(9 * sum(answered.values()) / len(answered), 1), tests


# ---------------- accounting quality ----------------

def derive_accruals_ratio(income, balance, cashflow):
    """(Net income - operating cash flow) / average assets. The classic earnings-quality red flag."""
    net_income, operating_cash = at(line(income, "net_income")), at(line(cashflow, "operating_cash_flow"))
    assets = average(at(line(balance, "total_assets")), at(line(balance, "total_assets"), 1))
    if net_income is None or operating_cash is None or not assets:
        return None
    return rounded((net_income - operating_cash) / assets)


def _days(numerator, annual_flow):
    value = ratio(numerator, annual_flow)
    return None if value is None else value * 365


def derive_working_capital_trends(income, balance):
    """Days-sales-outstanding and inventory-days levels plus their year-over-year drift.

    Receivables or inventory growing faster than the business is the standard tell for
    revenue recognized ahead of cash or for stock nobody wants.
    """
    revenue, cost = line(income, "revenue"), line(income, "cost_of_revenue")
    receivables, inventory = line(balance, "receivables"), line(balance, "inventory")
    dso = _days(at(receivables), at(revenue))
    dso_prior = _days(at(receivables, 1), at(revenue, 1))
    inventory_days = _days(at(inventory), at(cost))
    inventory_days_prior = _days(at(inventory, 1), at(cost, 1))

    def drift(now, prior):
        if now is None or not prior:
            return None
        return rounded(now / prior - 1)

    return {
        "days_sales_outstanding": rounded(dso, 1),
        "days_sales_outstanding_trend": drift(dso, dso_prior),
        "inventory_days": rounded(inventory_days, 1),
        "inventory_days_trend": drift(inventory_days, inventory_days_prior),
        "inventory_correction_flag": inventory_correction_flag(drift(inventory_days, inventory_days_prior)),
    }


# Rule-of-thumb bands on the year-over-year drift, not the absolute day count: what counts as
# "lean" inventory is sector-relative (120 days is lean for a memory chipmaker mid-shortage,
# elevated for a grocer), and this pipeline has no sector-relative inventory-days percentile
# built yet. The direction and magnitude of the drift is the part every cyclical KPI-layer
# writeup (semis, autos, chemicals, retail) actually leans on: inventory building for several
# consecutive periods is the standard channel-correction tell regardless of the sub-industry's
# absolute day-count norm.
INVENTORY_LEAN_TREND = -0.10
INVENTORY_ELEVATED_TREND = 0.15


def inventory_correction_flag(inventory_days_trend):
    """"lean" / "normal" / "elevated", or None when the trend itself is unavailable."""
    if inventory_days_trend is None:
        return None
    if inventory_days_trend <= INVENTORY_LEAN_TREND:
        return "lean"
    if inventory_days_trend >= INVENTORY_ELEVATED_TREND:
        return "elevated"
    return "normal"


# ---------------- capital allocation ----------------

def derive_capital_allocation(income, balance, cashflow, market_cap=None):
    """Dilution, buybacks, stock compensation, and reinvestment intensity."""
    shares = [value for value in line(balance, "shares_outstanding") if value]
    if len(shares) < 2:
        shares = [value for value in line(income, "diluted_shares") if value]
    share_change = None
    if len(shares) >= 2 and shares[1]:
        share_change = shares[0] / shares[1] - 1  # positive means dilution

    stock_comp = at(line(cashflow, "stock_comp"))
    revenue = at(line(income, "revenue"))
    buybacks = at(line(cashflow, "buybacks"))
    capex, depreciation = at(line(cashflow, "capex")), at(line(cashflow, "depreciation"))
    return {
        "share_count_change": rounded(share_change),
        # Net of dilution: what a holder's ownership stake actually did over the year.
        "net_buyback_yield": rounded(None if share_change is None else -share_change),
        "gross_buyback_yield": rounded(ratio(abs(buybacks) if buybacks else None, market_cap)),
        "stock_comp_to_revenue": rounded(ratio(abs(stock_comp) if stock_comp else None, revenue)),
        "capex_to_depreciation": rounded(ratio(abs(capex) if capex else None,
                                               abs(depreciation) if depreciation else None), 2),
    }


# ---------------- valuation ----------------

def derive_enterprise_multiples(income, balance, cashflow, info, market_cap):
    """Capital-structure-neutral multiples. A cheap P/E on a debt-laden balance sheet is not cheap."""
    info = info or {}
    enterprise_value = info.get("enterpriseValue")
    if enterprise_value is None and market_cap:
        debt = at(line(balance, "total_debt")) or info.get("totalDebt")
        cash = at(line(balance, "cash")) or info.get("totalCash")
        enterprise_value = market_cap + (debt or 0) - (cash or 0)
    ebitda = at(line(income, "ebitda")) or info.get("ebitda")
    ebit = at(line(income, "ebit"))
    revenue = at(line(income, "revenue")) or info.get("totalRevenue")
    fcf = at(line(cashflow, "free_cash_flow")) or info.get("freeCashflow")

    equity = at(line(balance, "equity"))
    goodwill = at(line(balance, "goodwill")) or 0
    intangibles = at(line(balance, "intangibles")) or 0
    tangible_book = None if equity is None else equity - goodwill - intangibles

    def multiple(denominator):
        """Guard against a quote-scale numerator meeting a statement-scale denominator."""
        value = ratio(enterprise_value, denominator) if (denominator or 0) > 0 else None
        return None if value is None or value > 500 else value

    return {
        "enterprise_value": None if enterprise_value is None else round(enterprise_value),
        # Raw inputs, not just the multiples derived from them -- pipeline/reverse_dcf.py
        # needs the dollar figures themselves to solve for market-implied growth.
        "free_cash_flow": rounded(fcf, 0),
        "total_debt": rounded(at(line(balance, "total_debt")), 0),
        "ev_to_ebitda": rounded(multiple(ebitda), 2),
        # EV/EBIT is EV/EBITDA's twin without the depreciation add-back, which is where
        # capital intensity hides. Gray & Vogel's multiples horse race finds the two produce
        # nearly identical results; carrying both means one covers the other's data gaps.
        "ev_to_ebit": rounded(multiple(ebit), 2),
        # EV/Sales rather than P/S: including debt is the whole point of an enterprise
        # multiple, and a levered company looks artificially cheap on price-to-sales.
        "ev_to_sales": rounded(multiple(revenue), 2),
        "ev_to_fcf": rounded(multiple(fcf), 2),
        "price_to_tangible_book": rounded(
            ratio(market_cap, tangible_book) if (tangible_book or 0) > 0 else None, 2),
        "earnings_yield": rounded(ratio(info.get("trailingEps"), info.get("currentPrice") or info.get("regularMarketPrice"))),
    }


def derive_tangible_returns(income, balance):
    """Return on tangible common equity: net income over average tangible book value.

    ROTCE is the bank/capital-markets scorecard metric -- ROE inflated by goodwill from a
    roll-up acquisition reads identically to organic returns on a clean balance sheet, and
    stripping intangibles is exactly what price_to_tangible_book already does on the other
    side of the same ledger. Averaging the two most recent tangible-book readings (rather
    than the single latest one) matches how the multiple itself is conventionally quoted.
    """
    net_income = at(line(income, "net_income"))
    if net_income is None:
        return None
    equity, goodwill, intangibles = line(balance, "equity"), line(balance, "goodwill"), line(balance, "intangibles")

    def tangible(index):
        equity_value = at(equity, index)
        if equity_value is None:
            return None
        return equity_value - (at(goodwill, index) or 0) - (at(intangibles, index) or 0)

    base = average(tangible(0), tangible(1)) or tangible(0)
    if base is None or base <= 0:
        return None
    return rounded(ratio(net_income, base))


def derive_reit_ffo(income, cashflow, market_cap=None):
    """Funds from operations: net income plus real-estate D&A, less property-sale gains.

    GAAP net income is close to meaningless for a REIT because straight-line depreciation on
    a building that (unlike a machine) does not actually wear out mechanically overstates the
    economic expense -- Nareit defines FFO precisely to back that distortion out. The
    property-sale-gain add-back only fires when the filer breaks that line out separately;
    see the ``gain_on_sale_of_real_estate`` alias note for why it is often unavailable.
    """
    net_income = at(line(income, "net_income"))
    depreciation = at(line(cashflow, "depreciation"))
    if net_income is None or depreciation is None:
        return None, None
    gain_on_sale = at(line(income, "gain_on_sale_of_real_estate"))
    ffo = net_income + abs(depreciation) - (gain_on_sale or 0)
    price_to_ffo = None
    if market_cap and ffo and ffo > 0:
        price_to_ffo = rounded(ratio(market_cap, ffo), 2)
    return rounded(ffo, 0), price_to_ffo


def derive_earnings_surprise(surprises):
    """Recent earnings-surprise momentum from a list of ``{"date", "surprise_pct"}`` rows.

    Novy-Marx (2014) makes the case that price momentum is largely a shadow of fundamental
    momentum - "fundamentally, momentum is fundamental momentum". Trailing growth on its own
    is a weak predictor of forward returns; the *direction of surprise against expectations*
    is the part that carries drift. Averaging the last four quarters, newest weighted
    heaviest, keeps one noisy quarter from dominating.
    """
    rows = [row for row in (surprises or [])
            if isinstance(row, dict) and row.get("surprise_pct") is not None]
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)[:4]
    weights = [0.4, 0.3, 0.2, 0.1][:len(ordered)]
    total = sum(weights)
    try:
        weighted = sum(float(row["surprise_pct"]) * weight
                       for row, weight in zip(ordered, weights))
    except (TypeError, ValueError):
        return None
    return rounded(weighted / total)


def earnings_surprise_rows(ticker_obj, *, on_error=None):
    """Adapt a yfinance ``earnings_dates`` frame into plain rows. Never raises.

    ``earnings_dates`` is not part of the statement bundle - yfinance serves it by scraping
    a separate page, one request per symbol, and that endpoint is markedly less reliable
    than the rest. Failures are reported through ``on_error`` rather than swallowed, because
    a silently empty result is indistinguishable from a company that simply has no reported
    surprises, and that ambiguity is what let this signal sit at zero coverage unnoticed.
    """
    try:
        frame = ticker_obj.earnings_dates
    except Exception as exc:  # noqa: BLE001 - an absent calendar must not sink the symbol
        if on_error:
            on_error(exc)
        return []
    if frame is None or getattr(frame, "empty", True):
        return []
    column = next((name for name in frame.columns if "surprise" in str(name).lower()), None)
    if column is None:
        return []
    rows = []
    for index, value in zip(frame.index, frame[column].tolist()):
        try:
            surprise = float(value)
        except (TypeError, ValueError):
            continue
        if surprise != surprise:  # NaN: the quarter has not been reported yet
            continue
        rows.append({"date": str(index)[:10], "surprise_pct": surprise})
    return rows


# ---------------- market structure ----------------

def derive_market_structure(info, price, closes=(), volumes=()):
    """Short positioning, ownership, liquidity, and 52-week context - all from the quote payload."""
    info = info or {}
    high, low = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
    if high is None and len(closes) >= 200:
        high, low = max(closes[-252:]), min(closes[-252:])
    volume = info.get("averageVolume") or (sum(volumes[-30:]) / len(volumes[-30:]) if len(volumes) >= 30 else None)
    target = info.get("targetMeanPrice")
    return {
        "short_percent_of_float": rounded(info.get("shortPercentOfFloat")),
        "days_to_cover": rounded(info.get("shortRatio"), 2),
        "institutional_ownership": rounded(info.get("heldPercentInstitutions")),
        "insider_ownership": rounded(info.get("heldPercentInsiders")),
        "beta": rounded(info.get("beta"), 2),
        "average_dollar_volume": None if not (volume and price) else round(volume * price),
        "pct_from_52w_high": rounded(None if not (high and price) else (price / high - 1) * 100, 2),
        "pct_above_52w_low": rounded(None if not (low and price) else (price / low - 1) * 100, 2),
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "analyst_rating": rounded(info.get("recommendationMean"), 2),
        "analyst_consensus_target": rounded(target, 2),
        "analyst_target_upside": rounded(None if not (target and price) else (target / price - 1) * 100, 2),
        "payout_ratio": rounded(info.get("payoutRatio")),
    }


# ---------------- assembly ----------------

def derive_extended(*, annual, quarterly=None, info=None, market_cap=None, price=None,
                    sector=None, closes=(), volumes=(), earnings_surprises=()):
    """Every extended metric for one company, merged into a single flat dict."""
    income = (annual or {}).get("income", {})
    balance = (annual or {}).get("balance", {})
    cashflow = (annual or {}).get("cashflow", {})
    info = info or {}
    market_cap = market_cap or info.get("marketCap")
    piotroski, piotroski_tests = derive_piotroski(income, balance, cashflow)
    altman, altman_variant = derive_altman_z(income, balance, market_cap, sector)
    funds_from_operations, price_to_ffo = derive_reit_ffo(income, cashflow, market_cap)

    metrics = {
        "return_on_invested_capital": derive_roic(income, balance),
        "gross_profits_to_assets": derive_gross_profits_to_assets(income, balance),
        "cash_conversion": derive_cash_conversion(income, cashflow),
        "fcf_growth_3y": derive_fcf_growth(cashflow),
        "interest_coverage": derive_interest_coverage(income),
        "net_debt_to_ebitda": derive_net_debt_to_ebitda(income, balance, info),
        "altman_z": altman,
        "altman_z_variant": altman_variant,
        "piotroski_f": piotroski,
        "accruals_ratio": derive_accruals_ratio(income, balance, cashflow),
        "asset_growth": derive_asset_growth(balance),
        "earnings_surprise": derive_earnings_surprise(earnings_surprises),
        "return_on_tangible_common_equity": derive_tangible_returns(income, balance),
        "funds_from_operations": funds_from_operations,
        "price_to_ffo": price_to_ffo,
    }
    metrics.update(derive_margins(income))
    metrics.update(derive_working_capital_trends(income, balance))
    metrics.update(derive_capital_allocation(income, balance, cashflow, market_cap))
    metrics.update(derive_enterprise_multiples(income, balance, cashflow, info, market_cap))
    metrics.update(derive_market_structure(info, price, closes, volumes))
    metrics["piotroski_tests"] = {key: value for key, value in piotroski_tests.items() if value is not None}
    metrics["statement_periods"] = (income or {}).get("periods", [])[:4]
    metrics["extended_coverage"] = round(
        sum(metrics.get(key) is not None for key in COVERAGE_KEYS) / len(COVERAGE_KEYS), 2)
    return metrics


COVERAGE_KEYS = (
    "return_on_invested_capital", "gross_profits_to_assets", "cash_conversion", "fcf_growth_3y",
    "interest_coverage", "net_debt_to_ebitda", "altman_z", "piotroski_f", "accruals_ratio",
    "operating_margin_trend", "days_sales_outstanding_trend", "net_buyback_yield",
    "stock_comp_to_revenue", "capex_to_depreciation", "asset_growth", "ev_to_ebitda",
    "ev_to_ebit", "ev_to_sales", "ev_to_fcf", "price_to_tangible_book",
    "return_on_tangible_common_equity", "funds_from_operations", "gross_margin_trend",
)

# Every statement-derived metric the legacy scorer weighs (pipeline/config/settings.json's
# fundamentals.metric_weights), mapped to the unit its canonical_metrics registry entry
# declares. Without an Observation, scoring_v2.build_v2_analysis treats these as legacy
# scalars with no lineage and discards them even though they were computed from the same
# annual statements as everything else here - that's what left the v2 confidence/coverage
# layer reporting near-zero evidence for most companies despite the values being present.
EXTENDED_METRIC_UNITS = {
    "price_to_tangible_book": "multiple",
    "return_on_tangible_common_equity": "decimal",
    "funds_from_operations": "usd",
    "price_to_ffo": "multiple",
    "free_cash_flow": "usd",
    "total_debt": "usd",
    "gross_margin_trend": "decimal",
    "ev_to_ebitda": "multiple",
    "ev_to_ebit": "multiple",
    "ev_to_fcf": "multiple",
    "return_on_invested_capital": "decimal",
    "gross_profits_to_assets": "decimal",
    "cash_conversion": "decimal",
    "interest_coverage": "multiple",
    "net_debt_to_ebitda": "multiple",
    "altman_z": "score",
    "fcf_growth_3y": "decimal",
    "operating_margin_trend": "decimal",
    "earnings_surprise": "decimal",
    "net_buyback_yield": "decimal",
    "stock_comp_to_revenue": "decimal",
    "capex_to_depreciation": "multiple",
    "asset_growth": "decimal",
    "accruals_ratio": "decimal",
    "piotroski_f": "count",
    "days_sales_outstanding_trend": "decimal",
    "inventory_days_trend": "decimal",
}


def extended_observations(metrics, fetched_at=None):
    """Canonical-observation lineage for every statement-derived metric in ``metrics``.

    Mirrors ``canonical_metrics.yahoo_observations`` for the values ``derive_extended``
    computes, all sourced from the same matched annual statements recorded in
    ``metrics["statement_periods"]``.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    period_end = (metrics.get("statement_periods") or [None])[0]
    result = {}
    for metric_id, unit in EXTENDED_METRIC_UNITS.items():
        value = metrics.get(metric_id)
        if value is None:
            continue
        result[metric_id] = [Observation(
            value=value, unit=unit, source="yahoo", source_field=f"derived:{metric_id}",
            period_end=period_end, observed_at=fetched_at, fetched_at=fetched_at,
            is_ttm=False, is_forward=False,
            quality_flags=["derived_from_annual_statements"],
        ).to_dict()]
    return result
