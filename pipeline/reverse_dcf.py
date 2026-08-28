"""Market-implied growth: a momentum-free "is this already priced in" read.

Rather than forecasting a fair value and comparing it to price, this inverts the question --
Mauboussin & Rappaport's *Expectations Investing* framing -- and asks what growth rate the
current enterprise value already assumes, given the company's own free cash flow and an
estimated cost of capital. A high implied growth rate means the market is pricing in a lot of
future delivery already; nothing here reads price history or momentum to get there.

This is a deliberately simplified **single-stage** (Gordon growth) reverse DCF, not the full
multi-stage model with an explicit forecast horizon and competitive-advantage-period estimate
that Mauboussin & Rappaport describe. A single closed-form solve is transparent and auditable;
a multi-stage version would need forecast-horizon and terminal-growth assumptions layered on
top of the ones already here, compounding the same estimation uncertainty. Treat the output as
a rough, comparable-across-companies read, not a precise fair-value estimate.

Every rate below (risk-free rate, equity risk premium, cost of debt, tax rate) is a declared
assumption in ``pipeline/config/settings.json``'s ``reverse_dcf`` block, not a fitted or fetched
figure -- the same "labeled, not measured" honesty ``pipeline/costs.py`` applies to its spread
proxy. Getting the assumption wrong shifts every company's implied growth by roughly the same
amount, which is why this is published as a comparable cross-sectional read, never as a
precise, standalone growth forecast for one company.
"""


def estimate_cost_of_equity(beta, risk_free_rate, equity_risk_premium):
    """CAPM cost of equity. Falls back to the market-average beta of 1.0 when beta is absent."""
    if risk_free_rate is None or equity_risk_premium is None:
        return None
    return risk_free_rate + (beta if beta is not None else 1.0) * equity_risk_premium


def estimate_wacc(*, market_cap, total_debt, cost_of_equity, cost_of_debt, tax_rate):
    """Weighted-average cost of capital from market-value equity and book-value debt.

    Debt below is unlevered (book value, no market discount) because market values for
    corporate debt are not fetched by this pipeline -- a modest source of imprecision that
    matters far less than the cost-of-equity assumptions above, since debt is the minority
    weight for the large majority of the universe this scores.
    """
    if market_cap is None or market_cap <= 0 or cost_of_equity is None:
        return None
    debt = max(total_debt or 0, 0)
    capital = market_cap + debt
    equity_weight = market_cap / capital
    debt_weight = debt / capital
    after_tax_cost_of_debt = (cost_of_debt or 0) * (1 - (tax_rate if tax_rate is not None else 0.21))
    return equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt


def market_implied_growth(*, enterprise_value, free_cash_flow, wacc):
    """Solve EV = FCF*(1+g)/(WACC-g) for g: the perpetual growth rate priced into EV today.

    Undefined (returns None) whenever the perpetuity itself is undefined for this company:
    non-positive EV, FCF, or WACC. Given positive EV and FCF, the algebraic solution
    ``g = (EV*WACC - FCF) / (EV + FCF)`` is always strictly below WACC before rounding -- a
    perpetuity priced at g >= WACC would have an infinite or negative value, so no positive,
    finite EV could ever produce that solve. There is deliberately no separate guard for it;
    the 4-decimal rounding below can round an extreme ratio's solve up to meet WACC exactly,
    but never past it.
    """
    if enterprise_value is None or enterprise_value <= 0:
        return None
    if free_cash_flow is None or free_cash_flow <= 0:
        return None
    if wacc is None or wacc <= 0:
        return None
    growth = (enterprise_value * wacc - free_cash_flow) / (enterprise_value + free_cash_flow)
    return round(growth, 4)


def derive_market_implied_growth(*, beta, market_cap, total_debt, enterprise_value,
                                  free_cash_flow, tax_rate=0.21, assumptions):
    """One company's market-implied growth reading, or None when an input is missing.

    ``assumptions`` is ``settings.json``'s ``reverse_dcf`` block: risk_free_rate,
    equity_risk_premium, and default_cost_of_debt.
    """
    cost_of_equity = estimate_cost_of_equity(
        beta, assumptions.get("risk_free_rate"), assumptions.get("equity_risk_premium"))
    wacc = estimate_wacc(
        market_cap=market_cap, total_debt=total_debt, cost_of_equity=cost_of_equity,
        cost_of_debt=assumptions.get("default_cost_of_debt"), tax_rate=tax_rate)
    growth = market_implied_growth(
        enterprise_value=enterprise_value, free_cash_flow=free_cash_flow, wacc=wacc)
    if growth is None:
        return None
    ceiling = assumptions.get("implausible_growth_ceiling", 0.15)
    return {
        "market_implied_growth": growth,
        "wacc_assumed": round(wacc, 4) if wacc is not None else None,
        "exceeds_plausible_ceiling": growth > ceiling,
    }
