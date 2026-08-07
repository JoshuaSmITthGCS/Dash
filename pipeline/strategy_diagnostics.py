"""Strategy-level diagnostics the dashboard has never had: expectancy, profit factor, R.

CAGR and Sharpe describe a return series. They say nothing about the *shape* of how the
strategy makes money -- whether it wins often and small or rarely and large, how deep the
losing streaks run, or whether the edge survives once the cost of turning the book over is
charged against it. Those are the numbers that decide whether a strategy is sizeable, and
none of them existed anywhere in this repository.

Everything here is computed from artifacts already on disk: the published monthly backtest
(``pipeline/backtest_monthly_results.json``, 60 rebalances with a 1,255-day portfolio value
series, per-rebalance turnover and cost) and the committed Ken French factor series. No
network access.

**What a "trade" means here, stated plainly.** The backtest artifact stores each rebalance's
20 picks and the portfolio value path, but not per-name entry and exit prices. So the unit of
account is the *rebalance period* -- one month of holding a 20-name book -- not an individual
position. Expectancy of +1.2% therefore means "the average month returns +1.2%", not "the
average position returns +1.2%". Those are different statistics and conflating them would
overstate what this measures. Per-name R-multiples need a backtest that records per-name fills;
that is noted as a gap rather than approximated.

Regimes are defined by objective rules fixed before any strategy performance was inspected:
market direction from the benchmark's own 200-session trend, volatility from trailing realized
volatility against the sample median, and rate direction from the French risk-free series.

Usage: python pipeline/strategy_diagnostics.py
Output: pipeline/reports/strategy_diagnostics.json
"""

import json
import math
import os
import sys
from statistics import mean, median, pstdev

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from p0_q1_benchmark_factor_report import monthly_returns  # noqa: E402

BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")
FRENCH_PATH = os.path.join(ROOT, "public", "data", "factors", "french.json")
OUT_PATH = os.path.join(HERE, "reports", "strategy_diagnostics.json")

PERIODS_PER_YEAR = 12
TREND_SESSIONS = 200
VOLATILITY_SESSIONS = 63
ROLLING_WINDOW_MONTHS = 12


# ---------------- trade-shape diagnostics ----------------

def expectancy(returns):
    """Mean return per period, decomposed the way a trader reads it.

    E = P(win) * average win - P(loss) * average loss. Reported alongside the plain mean so
    the identity is checkable rather than asserted.
    """
    if not returns:
        return None
    wins = [value for value in returns if value > 0]
    losses = [-value for value in returns if value < 0]
    win_rate = len(wins) / len(returns)
    loss_rate = len(losses) / len(returns)
    average_win = mean(wins) if wins else 0.0
    average_loss = mean(losses) if losses else 0.0
    return {
        "periods": len(returns),
        "win_rate": round(win_rate, 4),
        "average_win": round(average_win, 5),
        "average_loss": round(average_loss, 5),
        "payoff_ratio": round(average_win / average_loss, 3) if average_loss else None,
        "expectancy_per_period": round(win_rate * average_win - loss_rate * average_loss, 5),
        "mean_return_per_period": round(mean(returns), 5),
    }


def profit_factor(returns):
    """Gross profit over gross loss. Above 1.0 is a positive edge; 1.5+ is usually tradeable."""
    gross_profit = sum(value for value in returns if value > 0)
    gross_loss = -sum(value for value in returns if value < 0)
    return {
        "gross_profit": round(gross_profit, 5),
        "gross_loss": round(gross_loss, 5),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
    }


def streaks(returns):
    longest_win = longest_loss = current_win = current_loss = 0
    for value in returns:
        if value > 0:
            current_win += 1
            current_loss = 0
        elif value < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)
    return {"longest_winning_streak": longest_win, "longest_losing_streak": longest_loss}


def r_multiples(returns):
    """Period returns expressed in units of the strategy's own downside dispersion.

    A true R-multiple divides by the risk deliberately taken on each trade (the distance to
    the stop). This backtest has no per-position stop and no per-name fills, so the risk unit
    used is the standard deviation of losing periods -- a defensible proxy at the portfolio
    level, and explicitly not the same statistic. Labelled in the output.
    """
    losses = [value for value in returns if value < 0]
    unit = pstdev(losses) if len(losses) > 1 else None
    if not unit:
        return {"risk_unit": None, "basis": "insufficient losing periods to estimate dispersion"}
    multiples = [value / unit for value in returns]
    return {
        "risk_unit": round(unit, 5),
        "basis": "standard deviation of losing periods (portfolio level, not per-position stops)",
        "mean_r": round(mean(multiples), 3),
        "median_r": round(median(multiples), 3),
        "best_r": round(max(multiples), 3),
        "worst_r": round(min(multiples), 3),
    }


# ---------------- risk-adjusted and drawdown ----------------

def _annualized(returns):
    if not returns:
        return None
    growth = 1.0
    for value in returns:
        growth *= 1 + value
    return growth ** (PERIODS_PER_YEAR / len(returns)) - 1


def drawdown_profile(returns):
    peak = equity = 1.0
    worst = 0.0
    underwater = longest_underwater = 0
    for value in returns:
        equity *= 1 + value
        if equity >= peak:
            peak = equity
            underwater = 0
        else:
            underwater += 1
            longest_underwater = max(longest_underwater, underwater)
        worst = min(worst, equity / peak - 1)
    return {"max_drawdown": round(worst, 5),
            "longest_underwater_periods": longest_underwater}


def risk_adjusted(returns):
    if len(returns) < 2:
        return {}
    average = mean(returns)
    deviation = pstdev(returns)
    downside = [value for value in returns if value < 0]
    downside_deviation = pstdev(downside) if len(downside) > 1 else None
    annual_return = _annualized(returns)
    max_drawdown = drawdown_profile(returns)["max_drawdown"]
    root = math.sqrt(PERIODS_PER_YEAR)
    return {
        "annualized_return": round(annual_return, 5),
        "annualized_volatility": round(deviation * root, 5),
        "sharpe_zero_rate": round(average / deviation * root, 3) if deviation else None,
        "sortino_zero_rate": (round(average / downside_deviation * root, 3)
                              if downside_deviation else None),
        "calmar": (round(annual_return / abs(max_drawdown), 3)
                   if max_drawdown else None),
        "recovery_factor": (round((_annualized(returns) or 0) / abs(max_drawdown), 3)
                            if max_drawdown else None),
    }


def rolling(returns, months, window=ROLLING_WINDOW_MONTHS):
    """Rolling annualized Sharpe -- stability matters more than the full-sample number."""
    if len(returns) < window:
        return []
    root = math.sqrt(PERIODS_PER_YEAR)
    series = []
    for end in range(window, len(returns) + 1):
        chunk = returns[end - window:end]
        deviation = pstdev(chunk)
        series.append({
            "through": months[end - 1],
            "sharpe": round(mean(chunk) / deviation * root, 3) if deviation else None,
            "return": round(_annualized(chunk), 5),
        })
    return series


# ---------------- turnover and cost ----------------

def turnover_profile(rebalances):
    turnovers = [row["turnover"] for row in rebalances if row.get("turnover") is not None]
    costs, values = [], []
    for row in rebalances:
        if row.get("cost") is not None and row.get("portfolio_value"):
            costs.append(row["cost"] / row["portfolio_value"])
            values.append(row["portfolio_value"])
    return {
        "rebalances": len(rebalances),
        "mean_monthly_turnover": round(mean(turnovers), 4) if turnovers else None,
        "median_monthly_turnover": round(median(turnovers), 4) if turnovers else None,
        "annualized_turnover": round(mean(turnovers) * PERIODS_PER_YEAR, 3) if turnovers else None,
        "mean_cost_drag_per_rebalance": round(mean(costs), 6) if costs else None,
        "annualized_cost_drag": round(mean(costs) * PERIODS_PER_YEAR, 5) if costs else None,
    }


def turnover_adjusted_return(returns, rebalances):
    """What the strategy would have returned gross of its own trading costs.

    The published series is already net of 10bps one-way. Adding the recorded cost back
    isolates how much of the result the turnover is consuming.
    """
    drag = turnover_profile(rebalances)["annualized_cost_drag"]
    net = _annualized(returns)
    if drag is None or net is None:
        return {}
    return {
        "net_annualized_return": round(net, 5),
        "annualized_cost_drag": round(drag, 5),
        "implied_gross_annualized_return": round(net + drag, 5),
        "share_of_gross_return_consumed_by_costs": (
            round(drag / (net + drag), 4) if (net + drag) else None),
    }


# ---------------- regimes ----------------

def _trend_regime(dates, closes):
    """Bull when the benchmark sits above its own 200-session average, bear when below.

    Defined on the benchmark's price path alone, so the classification cannot be influenced
    by how the strategy happened to do.
    """
    labels = {}
    for index in range(len(closes)):
        if index < TREND_SESSIONS:
            continue
        window = closes[index - TREND_SESSIONS:index]
        labels[dates[index]] = "bull" if closes[index] >= mean(window) else "bear"
    return labels


def _volatility_regime(dates, closes):
    daily = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    realized = {}
    for index in range(VOLATILITY_SESSIONS, len(daily)):
        realized[dates[index + 1]] = pstdev(daily[index - VOLATILITY_SESSIONS:index])
    if not realized:
        return {}
    threshold = median(realized.values())
    return {day: ("high_volatility" if value >= threshold else "low_volatility")
            for day, value in realized.items()}


def _rate_regime(french_observations):
    """Rising or falling short rates, from the French risk-free series' own 6-month change."""
    months = sorted(row["month"] for row in french_observations)
    by_month = {row["month"]: row["risk_free"] for row in french_observations}
    labels = {}
    for index in range(6, len(months)):
        current, prior = by_month[months[index]], by_month[months[index - 6]]
        labels[months[index]] = "rising_rates" if current > prior else "falling_rates"
    return labels


def _month_end_labels(daily_labels):
    by_month = {}
    for day in sorted(daily_labels):
        by_month[day[:7]] = daily_labels[day]
    return by_month


def regime_attribution(strategy_returns, benchmark_returns, regimes):
    """Strategy and benchmark performance conditional on each regime."""
    output = {}
    for family, labels in regimes.items():
        buckets = {}
        for month, value in strategy_returns.items():
            label = labels.get(month)
            if label is None:
                continue
            buckets.setdefault(label, {"strategy": [], "benchmark": []})
            buckets[label]["strategy"].append(value)
            if month in benchmark_returns:
                buckets[label]["benchmark"].append(benchmark_returns[month])
        output[family] = {
            label: {
                "months": len(values["strategy"]),
                "strategy_annualized": round(_annualized(values["strategy"]), 5),
                "benchmark_annualized": (round(_annualized(values["benchmark"]), 5)
                                         if values["benchmark"] else None),
                "strategy_mean_monthly": round(mean(values["strategy"]), 5),
                "excess_annualized": (
                    round(_annualized(values["strategy"]) - _annualized(values["benchmark"]), 5)
                    if values["benchmark"] else None),
                "win_rate": round(
                    sum(1 for value in values["strategy"] if value > 0) / len(values["strategy"]), 4),
            }
            for label, values in sorted(buckets.items())
            if values["strategy"]
        }
    return output


# ---------------- report ----------------

def build_report(backtest=None, french=None):
    if backtest is None:
        with open(BACKTEST_PATH, encoding="utf-8") as handle:
            backtest = json.load(handle)
    if french is None:
        with open(FRENCH_PATH, encoding="utf-8") as handle:
            french = json.load(handle)

    portfolio = backtest["portfolio"]
    benchmark = backtest["benchmark_spy"]
    dates = [row["date"] for row in portfolio["history"]]
    values = [row["value"] for row in portfolio["history"]]
    benchmark_dates = [row["date"] for row in benchmark["history"]]
    benchmark_values = [row["value"] for row in benchmark["history"]]

    strategy_monthly = monthly_returns(dates, values)
    benchmark_monthly = monthly_returns(benchmark_dates, benchmark_values)
    months = sorted(strategy_monthly)
    returns = [strategy_monthly[month] for month in months]
    rebalances = portfolio["rebalances"]

    regimes = {
        "market_direction": _month_end_labels(_trend_regime(benchmark_dates, benchmark_values)),
        "volatility": _month_end_labels(_volatility_regime(benchmark_dates, benchmark_values)),
        "rates": _rate_regime(french["observations"]),
    }

    return {
        "schema_version": 1,
        "generated_at": backtest.get("generated_at"),
        "source": "pipeline/backtest_monthly_results.json",
        "unit_of_account": {
            "trade": "one monthly rebalance period holding a 20-name book",
            "why": ("the committed backtest stores per-rebalance picks and the portfolio value "
                    "path but not per-name entry and exit prices, so position-level statistics "
                    "cannot be computed from it"),
            "not_measured": ["per-position R-multiples", "per-name win rate",
                             "per-name maximum adverse excursion"],
        },
        "sample": {"months": len(returns), "first": months[0] if months else None,
                   "last": months[-1] if months else None},
        "expectancy": expectancy(returns),
        "profit_factor": profit_factor(returns),
        "streaks": streaks(returns),
        "r_multiples": r_multiples(returns),
        "risk_adjusted": risk_adjusted(returns),
        "drawdown": drawdown_profile(returns),
        "turnover": turnover_profile(rebalances),
        "turnover_adjusted_return": turnover_adjusted_return(returns, rebalances),
        "rolling_12m": rolling(returns, months),
        "regime_definitions": {
            "market_direction": f"benchmark above/below its trailing {TREND_SESSIONS}-session mean",
            "volatility": (f"trailing {VOLATILITY_SESSIONS}-session realized volatility of the "
                           "benchmark, split at the sample median"),
            "rates": "6-month change in the Ken French risk-free series",
            "preregistration": ("all three rules are functions of benchmark or macro series "
                                "only, never of strategy performance"),
        },
        "regime_attribution": regime_attribution(strategy_monthly, benchmark_monthly, regimes),
        "benchmark": {"name": "SPY", "annualized_return": round(
            _annualized([benchmark_monthly[month] for month in sorted(benchmark_monthly)]), 5)},
    }


def main():
    report = build_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    exp, pf = report["expectancy"], report["profit_factor"]
    print(f"months: {report['sample']['months']} "
          f"({report['sample']['first']} .. {report['sample']['last']})")
    print(f"win rate {exp['win_rate']:.1%}  avg win {exp['average_win']:+.2%}  "
          f"avg loss -{exp['average_loss']:.2%}  payoff {exp['payoff_ratio']}")
    print(f"expectancy/month {exp['expectancy_per_period']:+.3%}  "
          f"profit factor {pf['profit_factor']}")
    print(f"longest losing streak: {report['streaks']['longest_losing_streak']} months")
    adjusted = report["turnover_adjusted_return"]
    if adjusted:
        print(f"net {adjusted['net_annualized_return']:.2%} vs implied gross "
              f"{adjusted['implied_gross_annualized_return']:.2%} "
              f"(costs consume {adjusted['share_of_gross_return_consumed_by_costs']:.1%})")
    for family, buckets in report["regime_attribution"].items():
        parts = "  ".join(
            f"{label} n={block['months']} {block['strategy_annualized']:+.1%}"
            f" vs {block['benchmark_annualized']:+.1%}"
            for label, block in buckets.items() if block["benchmark_annualized"] is not None)
        print(f"{family}: {parts}")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
