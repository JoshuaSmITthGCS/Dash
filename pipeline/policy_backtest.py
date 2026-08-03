"""Exit-policy comparison for point-in-time weekly rankings.

The entry universe and top-N entry signal are held constant across policies.  This module
is called by ``backtest_historical.py --policy-suite`` after its walk-forward snapshots are
built; it never substitutes today's fundamentals into a historical week.
"""

from __future__ import annotations

from math import sqrt


POLICIES = (
    "no_stops", "fixed_20_stop", "volatility_adjusted_stop", "trailing_stop",
    "two_of_three_trim", "severity_based_trim", "thesis_only_exits", "combined_policy",
)


def _drawdown(values):
    peak, worst = 0.0, 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    return worst


def _statistics(history, invested, traded_value, costs, events):
    values = [row["value"] for row in history]
    returns = [(b / a - 1) for a, b in zip(values[:-1], values[1:]) if a > 0]
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((value - mean) ** 2 for value in returns) / len(returns) if returns else 0.0
    downside = [min(0.0, value) for value in returns]
    down_var = sum(value ** 2 for value in downside) / len(downside) if downside else 0.0
    years = max(len(history) / 52.0, 1 / 52.0)
    final = values[-1] if values else 0.0
    cagr = (final / invested) ** (1 / years) - 1 if invested > 0 and final > 0 else None
    exits = [event for event in events if event["kind"] == "exit"]
    trims = [event for event in events if event["kind"] == "trim"]
    return {
        "final_value": round(final, 2),
        "net_return": round(final / invested - 1, 6) if invested else None,
        "cagr": None if cagr is None else round(cagr, 6),
        "sharpe": round(mean / sqrt(variance) * sqrt(52), 4) if variance > 0 else None,
        "sortino": round(mean / sqrt(down_var) * sqrt(52), 4) if down_var > 0 else None,
        "maximum_drawdown": round(_drawdown(values), 6),
        "turnover": round(traded_value / invested, 6) if invested else None,
        "estimated_spread_slippage_tax": round(costs, 2),
        "exit_count": len(exits), "trim_count": len(trims),
        "tax_lot_turnover": None,
        "stopped_before_recovery_pct": None,
        "average_loss_avoided": None,
        "upside_forfeited_after_trims": None,
        "whipsaw_rate": None,
        "reentry_cost": None,
        "performance_by_volatility_bucket": {},
        "performance_by_sector": {},
        "performance_by_holding_period": {},
        "trim_outcomes": {
            "return_after_trim_vs_hold": None, "risk_reduction": None,
            "subsequent_recovery": None, "percent_improved_outcomes": None,
            "average_shares_sold_before_rebound": None, "drawdown_control_contribution": None,
        },
    }


def _decision(policy, row, holding):
    price = row.get("price")
    if not price:
        return None, 0.0, None
    cost, high = holding["cost"], holding["high"]
    recommendation = row.get("recommendation") or {}
    shadow = row.get("recommendation_v2") or {}
    company_action = ((shadow.get("company") or {}).get("action") or {}).get("label")
    agreement = recommendation.get("agreement_count", 0)
    groups = [group for group in ((shadow.get("company") or {}).get("deterioration_groups") or []) if group.get("flagged")]
    fixed = price <= cost * 0.80
    trailing = price <= high * 0.85
    volatility = ((row.get("technical_detail") or {}).get("annualized_volatility") or 25) / 100
    volatility_stop = price <= cost * (1 - min(0.40, max(0.12, volatility * 0.8)))
    thesis = company_action == "sell_thesis"
    if policy == "fixed_20_stop" and fixed:
        return "exit", 1.0, "hard_cost_basis_stop"
    if policy == "volatility_adjusted_stop" and volatility_stop:
        return "exit", 1.0, "volatility_adjusted_stop"
    if policy == "trailing_stop" and trailing:
        return "exit", 1.0, "trailing_high_water_stop"
    if policy == "two_of_three_trim" and agreement >= 2:
        return "trim", 0.33 if agreement == 2 else 0.50, "legacy_two_of_three"
    if policy == "severity_based_trim" and len(groups) >= 2:
        severity = sum(group.get("severity", 0) for group in groups) / len(groups)
        confidence = min(group.get("confidence", 0) for group in groups)
        base = 0.20 if len(groups) == 2 else 0.50
        return "trim", min(0.75, base * (0.75 if severity < 0.65 else 1.5 if severity >= 0.8 else 1) * (0.5 if confidence < 0.6 else 0.85 if confidence < 0.8 else 1)), "severity_based"
    if policy == "thesis_only_exits" and thesis:
        return "exit", 1.0, "sell_thesis"
    if policy == "combined_policy":
        if thesis or fixed or trailing:
            return "exit", 1.0, "sell_thesis" if thesis else "position_stop"
        if len(groups) >= 2:
            return "trim", 0.20 if len(groups) == 2 else 0.50, "severity_based"
    return None, 0.0, None


def simulate_policy(weekly_rankings, week_dates, policy, top_n=20, initial_capital=100000,
                    spread_bps=5, slippage_bps=5, tax_bps=0):
    if policy not in POLICIES:
        raise ValueError("unknown policy: " + str(policy))
    cash, holdings = float(initial_capital), {}
    history, events, traded_value, costs = [], [], 0.0, 0.0
    friction = (spread_bps + slippage_bps + tax_bps) / 10000
    for rows, as_of in zip(weekly_rankings, week_dates):
        by_ticker = {row["ticker"]: row for row in rows if row.get("price")}
        for ticker, holding in list(holdings.items()):
            row = by_ticker.get(ticker)
            if not row:
                continue
            holding["high"] = max(holding["high"], row["price"])
            kind, fraction, reason = _decision(policy, row, holding)
            if not kind or holding.get("acted_this_signal") == reason:
                continue
            shares = holding["shares"] * fraction
            gross = shares * row["price"]
            cost = gross * friction
            cash += gross - cost
            traded_value += gross
            costs += cost
            holding["shares"] -= shares
            holding["acted_this_signal"] = reason
            events.append({"date": str(as_of), "ticker": ticker, "kind": kind, "fraction": fraction, "reason": reason})
            if holding["shares"] <= 1e-10:
                del holdings[ticker]

        candidates = [row for row in rows[:top_n] if row.get("price") and row["ticker"] not in holdings]
        slots = max(0, top_n - len(holdings))
        if cash > 0 and slots and candidates:
            allocation = cash / min(slots, len(candidates))
            for row in candidates[:slots]:
                gross = min(allocation, cash / (1 + friction))
                cost = gross * friction
                shares = gross / row["price"]
                holdings[row["ticker"]] = {"shares": shares, "cost": row["price"], "high": row["price"], "acted_this_signal": None}
                cash -= gross + cost
                traded_value += gross
                costs += cost
        value = cash + sum(holding["shares"] * by_ticker.get(ticker, {}).get("price", holding["cost"]) for ticker, holding in holdings.items())
        history.append({"date": str(as_of), "value": round(value, 2)})
    return {"policy": policy, "history": history, "events": events,
            "metrics": _statistics(history, initial_capital, traded_value, costs, events)}


def compare_policies(weekly_rankings, week_dates, **kwargs):
    return {
        "method": "walk_forward_identical_top_n_entries_net_of_configured_costs",
        "provisional_metrics": [
            "tax_lot_turnover", "stopped_before_recovery_pct", "average_loss_avoided",
            "upside_forfeited_after_trims", "whipsaw_rate", "reentry_cost", "segment_performance",
        ],
        "policies": {policy: simulate_policy(weekly_rankings, week_dates, policy, **kwargs) for policy in POLICIES},
    }
