"""Derive quality, capital-allocation, accounting-integrity, and market-structure metrics.

Two layers, deliberately separated:

  * ``statement_series`` / ``extended_inputs`` adapt yfinance objects into plain dicts.
  * every ``derive_*`` function below is pure, so the arithmetic is unit-tested offline.

Every metric returns None when its inputs are missing or nonsensical. Downstream scoring
reweights around missing values rather than assuming a neutral reading, so a company is
never rewarded for hiding a number.
"""

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
}

FINANCIAL_SECTORS = ("Financial Services", "Financials", "Financial")


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


def derive_margins(income):
    """Operating margin level, its year-over-year change, and the margin on incremental revenue."""
    revenue, operating = line(income, "revenue"), line(income, "operating_income")
    gross = line(income, "gross_profit")
    now = ratio(at(operating), at(revenue))
    prior = ratio(at(operating, 1), at(revenue, 1))
    revenue_delta = None
    if at(revenue) is not None and at(revenue, 1) is not None:
        revenue_delta = at(revenue) - at(revenue, 1)
    incremental = None
    if revenue_delta and revenue_delta > 0 and at(operating) is not None and at(operating, 1) is not None:
        incremental = (at(operating) - at(operating, 1)) / revenue_delta
    return {
        "operating_margin": rounded(now),
        "operating_margin_trend": rounded(None if now is None or prior is None else now - prior),
        "gross_margin": rounded(ratio(at(gross), at(revenue))),
        "incremental_margin": rounded(incremental),
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


def derive_altman_z(income, balance, market_cap, sector=None):
    """Classic five-factor solvency composite. Undefined for banks, where it has no meaning."""
    if sector in FINANCIAL_SECTORS:
        return None
    assets = at(line(balance, "total_assets"))
    if not assets:
        return None
    working_capital = at(line(balance, "working_capital"))
    if working_capital is None:
        current_assets, current_liabilities = at(line(balance, "current_assets")), at(line(balance, "current_liabilities"))
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities
    liabilities = at(line(balance, "total_liabilities"))
    parts = {
        "working_capital": ratio(working_capital, assets),
        "retained_earnings": ratio(at(line(balance, "retained_earnings")), assets),
        "ebit": ratio(at(line(income, "ebit")), assets),
        "equity_to_liabilities": ratio(market_cap, liabilities),
        "asset_turnover": ratio(at(line(income, "revenue")), assets),
    }
    if sum(value is not None for value in parts.values()) < 4:
        return None
    weights = {"working_capital": 1.2, "retained_earnings": 1.4, "ebit": 3.3,
               "equity_to_liabilities": 0.6, "asset_turnover": 1.0}
    return rounded(sum(weights[key] * value for key, value in parts.items() if value is not None), 2)


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
    }


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
        "ev_to_ebitda": rounded(multiple(ebitda), 2),
        "ev_to_fcf": rounded(multiple(fcf), 2),
        "price_to_tangible_book": rounded(
            ratio(market_cap, tangible_book) if (tangible_book or 0) > 0 else None, 2),
        "earnings_yield": rounded(ratio(info.get("trailingEps"), info.get("currentPrice") or info.get("regularMarketPrice"))),
    }


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
        "analyst_target_upside": rounded(None if not (target and price) else (target / price - 1) * 100, 2),
        "payout_ratio": rounded(info.get("payoutRatio")),
    }


# ---------------- assembly ----------------

def derive_extended(*, annual, quarterly=None, info=None, market_cap=None, price=None,
                    sector=None, closes=(), volumes=()):
    """Every extended metric for one company, merged into a single flat dict."""
    income = (annual or {}).get("income", {})
    balance = (annual or {}).get("balance", {})
    cashflow = (annual or {}).get("cashflow", {})
    info = info or {}
    market_cap = market_cap or info.get("marketCap")
    piotroski, piotroski_tests = derive_piotroski(income, balance, cashflow)

    metrics = {
        "return_on_invested_capital": derive_roic(income, balance),
        "cash_conversion": derive_cash_conversion(income, cashflow),
        "fcf_growth_3y": derive_fcf_growth(cashflow),
        "interest_coverage": derive_interest_coverage(income),
        "net_debt_to_ebitda": derive_net_debt_to_ebitda(income, balance, info),
        "altman_z": derive_altman_z(income, balance, market_cap, sector),
        "piotroski_f": piotroski,
        "accruals_ratio": derive_accruals_ratio(income, balance, cashflow),
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
    "return_on_invested_capital", "cash_conversion", "fcf_growth_3y", "interest_coverage",
    "net_debt_to_ebitda", "altman_z", "piotroski_f", "accruals_ratio", "operating_margin_trend",
    "days_sales_outstanding_trend", "net_buyback_yield", "stock_comp_to_revenue",
    "capex_to_depreciation", "ev_to_ebitda", "ev_to_fcf", "price_to_tangible_book",
)
