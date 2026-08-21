"""Round 7 Task 4 follow-up: backtest the proposed leg reweighting on the locked panel.

Reads pipeline/backtest_signal_panel.json (60 monthly periods, 2021-09-01..2026-08-03,
860 tickers/period, forward returns at the panel's primary 21-trading-day horizon) and
compares top-20 equal-weight portfolios formed under:

  * champion       - the frozen flat leg weights (panel's own leg_weights block)
  * proposal_a     - growth, news_sentiment, capital_allocation, accounting_quality zeroed,
                     survivors renormalized (docs/AUDIT-ROUND-7-FINDINGS.md section 4.4)
  * proposal_b     - proposal A with market_behavior halved before renormalization
  * universe_mean  - equal-weight mean forward return of every ticker with a return that
                     period (the no-skill baseline every variant must beat)

Every variant recomposes its composite from the same per-ticker leg_scores with
renormalization over available legs (evaluation.composite_score), so the comparison is
method-identical - the only difference between variants is the weight vector. Returns are
reported gross, plus a labeled cost sensitivity: net = gross - turnover x 20 bps
(the shadow contract's spread_bps + slippage_bps on the traded fraction, both sides).

Offline and deterministic: no network, no clock, no randomness.
"""

import json
import os
import sys
from math import sqrt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from evaluation import composite_score, ic_summary, _period_ic  # noqa: E402

PANEL = os.path.join(REPO, "pipeline", "backtest_signal_panel.json")
OUTPUT = os.path.join(HERE, "reweighting_backtest_results.json")
TOP_N = 20
PERIODS_PER_YEAR = 12
ROUND_TRIP_COST = 0.0020  # 20 bps on the traded fraction per rebalance, both sides


def normalized(weights):
    active = {leg: weight for leg, weight in weights.items() if weight}
    total = sum(active.values())
    return {leg: weight / total for leg, weight in active.items()}


def select_top(period, weights):
    scored = sorted(
        ((ticker, composite_score(scores or {}, weights))
         for ticker, scores in (period.get("leg_scores") or {}).items()),
        key=lambda item: (item[1] is not None, item[1]), reverse=True,
    )
    return [ticker for ticker, score in scored if score is not None][:TOP_N]


def run_variant(periods, weights):
    gross, net, turnovers, held_counts = [], [], [], []
    previous = None
    for period in periods:
        forwards = period.get("forward_returns") or {}
        held = [t for t in select_top(period, weights) if forwards.get(t) is not None]
        if len(held) < 5:
            previous = None
            continue
        period_return = sum(forwards[t] for t in held) / len(held)
        turnover = 1.0 if previous is None else 1 - len(set(held) & set(previous)) / max(len(held), 1)
        gross.append(period_return)
        net.append(period_return - turnover * ROUND_TRIP_COST)
        turnovers.append(turnover)
        held_counts.append(len(held))
        previous = held
    return gross, net, turnovers, held_counts


def summarize(returns):
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    deviation = sqrt(variance)
    growth = 1.0
    peak, max_drawdown = 1.0, 0.0
    for r in returns:
        growth *= 1 + r
        peak = max(peak, growth)
        max_drawdown = min(max_drawdown, growth / peak - 1)
    years = len(returns) / PERIODS_PER_YEAR
    return {
        "periods": len(returns),
        "cumulative_growth": round(growth, 4),
        "annualized_return_pct": round(((growth ** (1 / years)) - 1) * 100, 2),
        "annualized_volatility_pct": round(deviation * sqrt(PERIODS_PER_YEAR) * 100, 2),
        "sharpe_rf0": round((mean / deviation) * sqrt(PERIODS_PER_YEAR), 3) if deviation else None,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "hit_rate": round(sum(1 for r in returns if r > 0) / len(returns), 3),
    }


def main():
    panel = json.load(open(PANEL))
    periods = panel["periods"]
    champion = panel["leg_weights"]
    proposal_a = normalized({**champion, "growth": 0, "news_sentiment": 0,
                             "capital_allocation": 0, "accounting_quality": 0})
    proposal_b = normalized({**champion, "growth": 0, "news_sentiment": 0,
                             "capital_allocation": 0, "accounting_quality": 0,
                             "market_behavior": champion["market_behavior"] / 2})

    variants = {"champion": champion, "proposal_a": proposal_a, "proposal_b": proposal_b}
    results = {}
    for name, weights in variants.items():
        gross, net, turnovers, held_counts = run_variant(periods, weights)
        ic = ic_summary(
            [_period_ic(period,
                        lambda t, period=period, weights=weights: composite_score(
                            (period.get("leg_scores") or {}).get(t) or {}, weights))
             for period in periods], PERIODS_PER_YEAR)
        results[name] = {
            "weights": {leg: round(weight, 4) for leg, weight in normalized(weights).items()},
            "gross": summarize(gross),
            "net_of_20bps_turnover_cost": summarize(net),
            "mean_turnover": round(sum(turnovers[1:]) / max(len(turnovers) - 1, 1), 3) if len(turnovers) > 1 else None,
            "mean_names_held": round(sum(held_counts) / max(len(held_counts), 1), 1),
            "ic": {key: ic[key] for key in ("periods", "mean_ic", "ic_std", "icir", "t_stat", "hit_rate")},
        }

    universe = []
    for period in periods:
        forwards = [value for value in (period.get("forward_returns") or {}).values() if value is not None]
        if len(forwards) >= 5:
            universe.append(sum(forwards) / len(forwards))
    results["universe_mean"] = {"gross": summarize(universe)}

    payload = {
        "purpose": "Round 7 Task 4 reweighting backtest - proposal only, champion untouched",
        "panel": {"path": "pipeline/backtest_signal_panel.json",
                  "generated_at": panel.get("generated_at"),
                  "periods": len(periods),
                  "first_date": periods[0]["date"], "last_date": periods[-1]["date"],
                  "primary_horizon": panel.get("primary_horizon")},
        "construction": {"selection": f"top {TOP_N} by composite, equal weight",
                          "renormalization": "composite_score over available legs",
                          "cost_model": "net = gross - turnover x 20 bps (shadow contract spread+slippage)"},
        "results": results,
    }
    json.dump(payload, open(OUTPUT, "w"), indent=1)
    print(json.dumps(payload["results"], indent=1))
    print(f"\nwritten: {os.path.relpath(OUTPUT, REPO)}")


if __name__ == "__main__":
    main()
