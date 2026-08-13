"""Put every backtest in this repository side by side, on comparable terms.

Thirteen backtests exist here and no two of them report the same way. The monthly research
backtest publishes a daily equity curve and a SPY leg; the options screens publish a trade
ledger with a win rate; the swing factor study publishes IC and a quantile spread and no
portfolio at all. Reading them from thirteen files means comparing an annualized return
against a per-trade hit rate against a rank correlation and calling the biggest number the
best method. This module normalizes them into one table so the comparison is at least
between like quantities, and labels the places where it cannot be.

**Success rate is three different measurements and they are not interchangeable.** Each row
carries ``success_rate_basis`` naming which one it is:

  ``rebalance_periods_positive``  share of held periods that made money. Computed here from
                                  the equity curve between consecutive execution dates, not
                                  taken from the source file - portfolio backtests do not
                                  publish it.
  ``trades_profitable``           share of individual option trades closing green. A 33% win
                                  rate is normal and can be excellent for a long-option
                                  book, where the winners are the fat tail; the same number
                                  on a monthly stock portfolio would be dire.
  ``periods_with_positive_ic``    share of periods where the *ranking* pointed the right way.
                                  Says nothing about what a book of the top names returned.

Sorting one column across all three would be meaningless, so ``comparable_group`` marks
which rows may be ranked against each other, and ``beat_benchmark_rate`` - share of periods
the method beat SPY over the same span - is computed only where a benchmark leg exists,
because that is the one success measure that survives a rising market honestly.

**The feature rollup is co-occurrence, not attribution.** ``features`` lists the declared
inputs each method reads, and the rollup averages success rates across methods sharing a
feature. With a handful of methods, overlapping inputs and wildly different windows, that is
a descriptive index for finding what to investigate - it cannot isolate a feature's
contribution, and ``interpretation`` on the payload says so. Attribution needs the
incremental-IC evidence the research contract already requires.

Reads only files already on disk and writes public/data/screens/backtest-comparison.json.
Missing inputs are reported as ``unavailable`` rows rather than omitted, so a backtest that
silently stopped publishing is visible instead of quietly vanishing from the comparison.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from common import LOG, save_json  # noqa: E402

REPO_ROOT = os.path.dirname(HERE)
SCREENS = os.path.join(REPO_ROOT, "public", "data", "screens")

# Declared inputs per method. Kept here as data rather than inferred from the payloads so the
# feature rollup is auditable: a reader can check a claim about what a method reads against
# the screen builder itself, which inference from result files would never allow.
PORTFOLIO_METHODS = [
    {
        "id": "research_score_monthly",
        "label": "Research score, top 20 monthly",
        "source": "pipeline/backtest_monthly_results.json",
        "features": ["fundamentals", "valuation", "quality", "growth", "price momentum"],
        "note": "The champion model: the appeal score this app ranks on, rebalanced monthly.",
    },
    {
        "id": "emerging_growth",
        "label": "Emerging growth screen",
        "source": "pipeline/backtest_emerging_growth_results.json",
        "features": ["growth", "fundamentals", "valuation"],
        "note": "A strict qualification screen - unfilled slots sit in cash rather than being backfilled.",
    },
    {
        "id": "swing_only",
        "label": "Swing signals only",
        "source": "pipeline/backtest_swing_portfolio_results.json",
        "features": ["earnings drift", "volume", "52-week proximity", "short-term reversal"],
        "note": "The swing screen traded as a weekly-rebalanced book, equal weighted.",
    },
    {
        "id": "political_institutional_only",
        "label": "Political + institutional trades only",
        "source": "pipeline/backtest_political_institutional_results.json",
        "features": ["congressional disclosures", "13F institutional breadth"],
        "note": "Follows disclosed trades and nothing else, gated on disclosure and filing dates.",
    },
]

OPTIONS_METHODS = [
    ("multi_day_options", "Multi-day options", "options-backtest.json", None),
    ("short_term_trades", "Short-term trades", "short-term-trades-backtest.json", None),
    ("covered_call", "Covered call", "covered-calls-backtest.json", None),
    ("cash_secured_put", "Cash-secured put", "cash-secured-puts-backtest.json", None),
    ("protective_put", "Protective put", "protective-puts-backtest.json", None),
    ("collar", "Collar", "collars-backtest.json", None),
    ("vertical_spread", "Vertical spread", "vertical-spreads-backtest.json", None),
    ("iron_condor", "Iron condor", "advanced-strategies-backtest.json", "iron_condor"),
    ("straddle", "Straddle", "advanced-strategies-backtest.json", "straddle"),
]

OPTIONS_FEATURES = ["option pricing", "realized volatility", "price momentum"]


def _read_json(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


def _percent(value, digits=4):
    return None if value is None else round(float(value) * 100, digits)


def _value_at(history, target):
    """The last recorded value on or before ``target``, or None before the series starts."""
    latest = None
    for row in history:
        if row["date"] <= target:
            latest = row["value"]
        else:
            break
    return latest


def period_success(portfolio, benchmark):
    """Success and beat-benchmark rates over the periods the portfolio was actually held.

    Boundaries are the execution dates the backtest itself recorded, so a "period" is one
    holding period of the declared strategy rather than an arbitrary calendar slice. The
    final stretch from the last rebalance to the end of the series is included as its own
    period - it is real held time, and dropping it would quietly discard the most recent
    (and only untouched-by-later-rebalancing) observation.

    **Periods holding nothing are excluded from the rate and counted separately.** A strict
    screen that qualifies nobody sits in cash, and a cash period returns exactly zero, which
    is not greater than zero, which would score as a loss. That is how the emerging-growth
    screen - which qualified nobody in all 60 months - first came out of here at a 0% success
    rate, reading as a strategy that lost every single month rather than one that never
    traded. The count of cash periods is the honest headline for such a strategy and is
    reported as ``periods_in_cash`` so it cannot be mistaken for either.
    """
    history = portfolio.get("history") or []
    rebalances = portfolio.get("rebalances") or []
    if len(history) < 2 or len(rebalances) < 2:
        return {"periods": 0, "success_rate": None, "beat_benchmark_rate": None,
                "periods_in_cash": 0, "benchmark_comparable_periods": 0}
    benchmark_history = (benchmark or {}).get("history") or []
    holdings_at = {row["execution_date"]: len(row.get("picks") or []) for row in rebalances}
    boundaries = sorted(set(holdings_at) | {history[-1]["date"]})

    wins = beats = comparable = periods = cash = 0
    for start, end in zip(boundaries, boundaries[1:]):
        before, after = _value_at(history, start), _value_at(history, end)
        if not before or after is None:
            continue
        if not holdings_at.get(start):
            cash += 1
            continue
        periods += 1
        portfolio_return = after / before - 1
        if portfolio_return > 0:
            wins += 1
        benchmark_before = _value_at(benchmark_history, start)
        benchmark_after = _value_at(benchmark_history, end)
        if benchmark_before and benchmark_after is not None:
            comparable += 1
            if portfolio_return > (benchmark_after / benchmark_before - 1):
                beats += 1
    return {
        "periods": periods,
        "success_rate": round(wins / periods, 4) if periods else None,
        "beat_benchmark_rate": round(beats / comparable, 4) if comparable else None,
        "benchmark_comparable_periods": comparable,
        "periods_in_cash": cash,
    }


def portfolio_row(spec):
    payload = _read_json(os.path.join(REPO_ROOT, spec["source"]))
    base = {
        "id": spec["id"], "label": spec["label"], "family": "portfolio",
        "comparable_group": "held_portfolio", "features": spec["features"],
        "note": spec["note"], "source": spec["source"],
    }
    if not payload:
        return {**base, "status": "unavailable",
                "status_detail": "no result file on disk; run this backtest to populate it"}

    portfolio = payload.get("portfolio") or {}
    metrics = portfolio.get("metrics") or {}
    benchmark = payload.get("benchmark_spy") or {}
    benchmark_metrics = benchmark.get("metrics") or {}
    success = period_success(portfolio, benchmark)
    method = payload.get("method") or {}
    total = metrics.get("total_return")
    benchmark_total = benchmark_metrics.get("total_return")

    # A strategy that qualified nobody sat in cash and returned ~0. Differencing that against
    # SPY's full-window return produces a headline like "-82% versus SPY", which reads as a
    # catastrophic loss and describes a portfolio that was never invested. The excess is
    # withheld below half-invested, and the share of time actually invested is published in
    # its place so the reason is visible rather than merely the absence.
    held_periods = success["periods"] + success["periods_in_cash"]
    invested_share = success["periods"] / held_periods if held_periods else None
    comparable_to_benchmark = invested_share is not None and invested_share >= 0.5

    caveats = []
    disclosures = payload.get("bias_disclosures") or {}
    if invested_share is not None and not comparable_to_benchmark:
        caveats.append(
            f"Invested in only {round(invested_share * 100, 1)}% of its rebalance periods and "
            "held cash for the rest, so its return is not comparable with a fully invested "
            "benchmark over the same window.")
    if disclosures.get("survivorship_bias"):
        caveats.append("Survivorship bias: the universe is today's candidate list walked backward.")
    for key in ("analyst_revision_leg", "congressional_source_coverage", "institutional_history",
                "disclosure_window", "market_cap_gate"):
        if disclosures.get(key):
            caveats.append(str(disclosures[key]))

    return {
        **base,
        "status": payload.get("status") or "measured",
        "status_detail": payload.get("status_detail"),
        "generated_at": payload.get("generated_at"),
        "window_start": metrics.get("start_date"),
        "window_end": metrics.get("end_date"),
        "total_return_pct": _percent(total),
        "cagr_pct": _percent(metrics.get("cagr")),
        "sharpe": metrics.get("sharpe_zero_rate"),
        "max_drawdown_pct": _percent(metrics.get("maximum_drawdown")),
        "annualized_volatility_pct": _percent(metrics.get("annualized_volatility")),
        "turnover": metrics.get("turnover"),
        "benchmark_total_return_pct": _percent(benchmark_total),
        "benchmark_cagr_pct": _percent(benchmark_metrics.get("cagr")),
        "excess_return_pct": (_percent(total - benchmark_total)
                              if comparable_to_benchmark and total is not None
                              and benchmark_total is not None else None),
        "time_invested_pct": _percent(invested_share, 2),
        "excess_return_withheld_reason": (
            None if comparable_to_benchmark
            else "held cash for most of the window; a benchmark difference would misreport "
                 "not being invested as underperformance"),
        "success_rate": success["success_rate"],
        "success_rate_basis": "rebalance_periods_positive",
        "beat_benchmark_rate": success["beat_benchmark_rate"],
        "periods_measured": success["periods"],
        "periods_in_cash": success["periods_in_cash"],
        "unique_names_held": metrics.get("unique_tickers_selected"),
        "cost_bps_one_way": method.get("transaction_cost_bps_one_way"),
        "caveats": caveats,
    }


def options_row(method_id, label, filename, strategy_key):
    payload = _read_json(os.path.join(SCREENS, filename))
    base = {
        "id": method_id, "label": label, "family": "options",
        "comparable_group": "option_trades", "features": OPTIONS_FEATURES,
        "source": f"public/data/screens/{filename}",
        "note": "Simulated option pricing: entry legs are Black-Scholes estimates from trailing "
                "realized volatility, not quoted historical prices.",
    }
    if not payload or payload.get("status") != "success":
        return {**base, "status": "unavailable",
                "status_detail": "screen backtest did not publish a successful run"}
    stats = (payload.get("backtest") or {})
    if strategy_key:
        stats = stats.get(strategy_key) or {}
    if not stats:
        return {**base, "status": "unavailable", "status_detail": "no statistics in the published run"}
    window = payload.get("window") or {}
    return {
        **base,
        "status": "measured",
        "generated_at": payload.get("generated_at"),
        "window_start": window.get("start") or window.get("first_entry"),
        "window_end": window.get("end") or window.get("last_entry"),
        "total_return_pct": _percent(stats.get("total_return")),
        "cagr_pct": _percent(stats.get("annualized_return")),
        "sharpe": stats.get("sharpe_ratio"),
        "deflated_sharpe": stats.get("deflated_sharpe_ratio"),
        "max_drawdown_pct": _percent(stats.get("max_drawdown")),
        "success_rate": stats.get("win_rate"),
        "success_rate_basis": "trades_profitable",
        "beat_benchmark_rate": None,
        "periods_measured": stats.get("num_trades"),
        "average_pnl_per_trade": stats.get("average_pnl_per_trade"),
        "universe_tickers": payload.get("universe_tickers"),
        "caveats": ["Option entry prices are modeled, not quoted; spreads, open interest and "
                    "fill quality are not simulated."],
    }


def swing_ranking_row():
    """The swing factor study, as a ranking measurement rather than a portfolio one."""
    payload = _read_json(os.path.join(REPO_ROOT, "pipeline", "backtest_swing_results.json"))
    base = {
        "id": "swing_ranking_ic", "label": "Swing signals — ranking quality (IC)",
        "family": "ranking", "comparable_group": "rank_quality",
        "features": ["earnings drift", "volume", "52-week proximity", "short-term reversal"],
        "source": "pipeline/backtest_swing_results.json",
        "note": "Measures whether the swing composite ranks correctly, not what a book of its "
                "top names returned. Paired with the swing portfolio row above.",
    }
    if not payload:
        return {**base, "status": "unavailable", "status_detail": "no result file on disk"}
    variant = (payload.get("variants") or {}).get("A") or {}
    ic = variant.get("ic") or {}
    window = payload.get("data_window") or {}
    return {
        **base,
        "status": "measured",
        "generated_at": payload.get("generated_at"),
        "window_start": window.get("first_graded_date"),
        "window_end": window.get("last_graded_date"),
        "mean_ic": ic.get("mean_ic"),
        "icir": ic.get("icir"),
        "t_stat": ic.get("t_stat"),
        "success_rate": ic.get("hit_rate"),
        "success_rate_basis": "periods_with_positive_ic",
        "beat_benchmark_rate": None,
        "periods_measured": ic.get("periods"),
        "mean_quantile_spread_net_pct": _percent(variant.get("mean_quantile_spread_net_of_cost")),
        "deflated_sharpe": variant.get("deflated_sharpe_probability_net_of_cost"),
        "clears_multiple_testing_bar": ic.get("clears_multiple_testing_bar"),
        "probability_of_backtest_overfitting": payload.get("probability_of_backtest_overfitting"),
        "caveats": ["Four of the five declared legs are measured; the analyst-revision leg has "
                    "no reconstructable history, so this is a sub-composite of the shipped model."],
    }


def contribution_row():
    """The weekly dollar-cost-averaging backtest.

    Its portfolio takes monthly contributions, so period returns computed from the value
    series would count deposits as performance. Total return is reported from the file's own
    contribution-aware summary and the period success rate is left unmeasured rather than
    computed wrongly.
    """
    payload = _read_json(os.path.join(REPO_ROOT, "pipeline", "backtest_historical_results.json"))
    base = {
        "id": "research_score_weekly_dca", "label": "Research score, weekly with contributions",
        "family": "portfolio", "comparable_group": "contribution_flows",
        "features": ["fundamentals", "valuation", "quality", "growth", "price momentum"],
        "source": "pipeline/backtest_historical_results.json",
        "note": "Adds a fixed monthly contribution, so its return is not comparable with the "
                "lump-sum backtests above.",
    }
    if not payload:
        return {**base, "status": "unavailable", "status_detail": "no result file on disk"}
    summary = payload.get("summary") or {}
    strategy = summary.get("strategy") or {}
    spy = (summary.get("benchmarks") or {}).get("SPY") or {}
    history = (payload.get("portfolio") or {}).get("history") or []
    return {
        **base,
        "status": "measured",
        "generated_at": summary.get("generated_at"),
        "window_start": history[0]["date"] if history else None,
        "window_end": history[-1]["date"] if history else None,
        "total_return_pct": strategy.get("return_pct"),
        "benchmark_total_return_pct": spy.get("return_pct"),
        "excess_return_pct": (round(strategy["return_pct"] - spy["return_pct"], 4)
                              if strategy.get("return_pct") is not None
                              and spy.get("return_pct") is not None else None),
        "success_rate": None,
        "success_rate_basis": "not_measurable_with_contribution_flows",
        "beat_benchmark_rate": None,
        "periods_measured": summary.get("weeks"),
        "caveats": ["Monthly contributions mean period-level returns cannot be read off the "
                    "value series without counting deposits as gains."],
    }


def feature_rollup(methods):
    """Mean success rate of the methods declaring each feature, within one basis at a time.

    Grouped by ``success_rate_basis`` because averaging a 33% option win rate with a 55%
    monthly-period win rate would produce a number describing nothing.
    """
    grouped = {}
    for method in methods:
        rate, basis = method.get("success_rate"), method.get("success_rate_basis")
        if rate is None or not basis or method.get("status") != "measured":
            continue
        for feature in method.get("features") or []:
            entry = grouped.setdefault((feature, basis), {"rates": [], "methods": []})
            entry["rates"].append(float(rate))
            entry["methods"].append(method["label"])
    rollup = [{
        "feature": feature,
        "success_rate_basis": basis,
        "methods": len(entry["methods"]),
        "method_labels": sorted(entry["methods"]),
        "mean_success_rate": round(sum(entry["rates"]) / len(entry["rates"]), 4),
        "minimum_success_rate": round(min(entry["rates"]), 4),
        "maximum_success_rate": round(max(entry["rates"]), 4),
    } for (feature, basis), entry in grouped.items()]
    rollup.sort(key=lambda row: (-row["mean_success_rate"], row["feature"]))
    return rollup


def build():
    methods = [portfolio_row(spec) for spec in PORTFOLIO_METHODS]
    methods.append(contribution_row())
    methods.append(swing_ranking_row())
    methods.extend(options_row(*spec) for spec in OPTIONS_METHODS)
    measured = [row for row in methods if row.get("status") == "measured"]
    return {
        "schema_version": "1.0.0",
        "model_version": "backtest-comparison-v1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if measured else "unavailable",
        "methods_total": len(methods),
        "methods_measured": len(measured),
        "success_rate_definitions": {
            "rebalance_periods_positive": "Share of holding periods, measured between the "
                                          "backtest's own execution dates, that ended positive.",
            "trades_profitable": "Share of individual simulated option trades that closed "
                                 "profitably. A low rate is normal for long-option strategies "
                                 "whose returns live in the tail.",
            "periods_with_positive_ic": "Share of periods in which the ranking correlated "
                                        "positively with forward returns. A ranking measure, "
                                        "not a portfolio return.",
            "not_measurable_with_contribution_flows": "The portfolio receives cash "
                                                      "contributions, so period returns cannot "
                                                      "be separated from deposits.",
        },
        "comparable_groups": {
            "held_portfolio": "Lump-sum portfolios rebalanced on a schedule. Directly comparable.",
            "contribution_flows": "Portfolio with ongoing contributions; returns are not "
                                  "comparable with the lump-sum rows.",
            "option_trades": "Per-trade option simulations. Comparable with each other only.",
            "rank_quality": "Ranking diagnostics. Not a portfolio return at all.",
        },
        "interpretation": "Success rates may be ranked only inside a comparable group. The "
                          "feature rollup reports co-occurrence, not attribution: methods share "
                          "inputs and cover different windows, so a feature's mean success rate "
                          "indicates where to look, never how much that feature contributed.",
        "methods": methods,
        "feature_rollup": feature_rollup(methods),
    }


def run():
    payload = build()
    save_json("screens/backtest-comparison.json", payload)
    LOG.info(f"Backtest comparison: {payload['methods_measured']}/{payload['methods_total']} "
             "methods measured")
    return payload


if __name__ == "__main__":
    run()
