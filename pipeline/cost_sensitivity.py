"""How much of the strategy's return does turning the book over consume?

`docs/P0-REPAIRS.md` WO-3 wired `costs.py` into the backtest and the IC harness but could not
answer the question the brief called "the single most important number in this phase": whether
a realistic tiered cost model wipes out more than 200bps of annual return relative to the flat
10bps the published backtest assumed. Answering it exactly needs a full re-run with per-name
liquidity, which needs network access.

It does not need network access to answer it *approximately*, and the approximation is tight,
because the published backtest already records what actually drives the answer: the realized
turnover of every one of the 60 rebalances. Cost drag is
``turnover x one-way rate``, so re-pricing the same realized trading at a different rate is
arithmetic on committed data, not a simulation.

What this cannot do is derive the correct rate per name -- that needs each traded name's own
median dollar volume and realized volatility. So instead of inventing those, this prices the
recorded turnover across the full range of rates `costs.py` can produce, from its most
optimistic liquid-name assumption to its stress illiquid one, and reports where the 200bps
threshold falls. The reader can then locate the strategy's actual book within that range.

Usage: python pipeline/cost_sensitivity.py
Output: pipeline/reports/cost_sensitivity.json
"""

import json
import os
import sys
from statistics import mean, median

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from costs import IMPACT_SCENARIOS, SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER, estimate_cost_bps  # noqa: E402
from strategy_diagnostics import _annualized  # noqa: E402
from p0_q1_benchmark_factor_report import monthly_returns  # noqa: E402

BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")
OUT_PATH = os.path.join(HERE, "reports", "cost_sensitivity.json")

PERIODS_PER_YEAR = 12
PUBLISHED_RATE_BPS = 10.0
THRESHOLD_BPS_OF_ANNUAL_RETURN = 200.0

# Median dollar volumes standing in for each liquidity tier, used only to read the rate
# costs.py assigns to that tier -- not to claim the strategy's book sits at any of them.
TIER_PROBES = {"liquid": 200_000_000.0, "thin": 12_000_000.0, "illiquid": 2_000_000.0}


def realized_turnover(rebalances):
    values = [row["turnover"] for row in rebalances if row.get("turnover") is not None]
    return {
        "rebalances": len(values),
        "mean_monthly": round(mean(values), 4) if values else None,
        "median_monthly": round(median(values), 4) if values else None,
        "annualized": round(mean(values) * PERIODS_PER_YEAR, 3) if values else None,
    }


def annual_drag_bps(mean_turnover, one_way_bps):
    """Annual return given up to trading, in basis points.

    The backtest charges ``value * turnover * bps / 10000`` per rebalance, so annual drag is
    ``mean_turnover * bps * 12``. This reproduces that identity rather than re-deriving it.
    """
    return mean_turnover * one_way_bps * PERIODS_PER_YEAR


def tier_rates():
    """The one-way rate costs.py assigns per liquidity tier and scenario.

    No volatility is supplied, so these are spread plus fees only -- market impact scales
    with a name's realized volatility, which this environment cannot observe. That makes
    every figure here a *floor*, and it is labelled as one rather than presented as the
    answer.
    """
    return {
        scenario: {
            tier: round(estimate_cost_bps(median_dollar_volume_60d=volume,
                                          scenario=scenario)["total_bps"], 2)
            for tier, volume in TIER_PROBES.items()
        }
        for scenario in IMPACT_SCENARIOS
    }


def build_report(backtest=None):
    if backtest is None:
        with open(BACKTEST_PATH, encoding="utf-8") as handle:
            backtest = json.load(handle)
    portfolio = backtest["portfolio"]
    rebalances = portfolio["rebalances"]
    turnover = realized_turnover(rebalances)
    dates = [row["date"] for row in portfolio["history"]]
    values = [row["value"] for row in portfolio["history"]]
    monthly = monthly_returns(dates, values)
    net_return = _annualized([monthly[month] for month in sorted(monthly)])

    published_drag = annual_drag_bps(turnover["mean_monthly"], PUBLISHED_RATE_BPS)
    gross_return = net_return + published_drag / 10_000

    rates = tier_rates()
    scenarios = {}
    for scenario, by_tier in rates.items():
        scenarios[scenario] = {
            tier: {
                "one_way_bps": rate,
                "annual_drag_bps": round(annual_drag_bps(turnover["mean_monthly"], rate), 1),
                "net_annualized_return": round(
                    gross_return - annual_drag_bps(turnover["mean_monthly"], rate) / 10_000, 5),
                "additional_drag_vs_published_bps": round(
                    annual_drag_bps(turnover["mean_monthly"], rate) - published_drag, 1),
                "exceeds_200bp_threshold": (
                    annual_drag_bps(turnover["mean_monthly"], rate) - published_drag
                    > THRESHOLD_BPS_OF_ANNUAL_RETURN),
            }
            for tier, rate in by_tier.items()
        }

    breakeven_rate = (PUBLISHED_RATE_BPS + THRESHOLD_BPS_OF_ANNUAL_RETURN
                      / (turnover["mean_monthly"] * PERIODS_PER_YEAR))
    worst_modelled_rate = max(rate for by_tier in rates.values() for rate in by_tier.values())
    worst_additional = annual_drag_bps(turnover["mean_monthly"], worst_modelled_rate) - published_drag
    return {
        "schema_version": 1,
        "generated_at": backtest.get("generated_at"),
        "source": "pipeline/backtest_monthly_results.json",
        "method": ("re-prices the backtest's own recorded per-rebalance turnover at each rate "
                   "costs.py can produce; annual drag = mean_monthly_turnover x one_way_bps x 12, "
                   "which is the identity backtest_monthly.py already charges"),
        "realized_turnover": turnover,
        "published_assumption": {
            "one_way_bps": PUBLISHED_RATE_BPS,
            "annual_drag_bps": round(published_drag, 1),
            "net_annualized_return": round(net_return, 5),
            "implied_gross_annualized_return": round(gross_return, 5),
            "share_of_gross_consumed": round((published_drag / 10_000) / gross_return, 4)
            if gross_return else None,
        },
        "cost_model_rates_by_tier": rates,
        "rates_are_a_floor": ("no per-name realized volatility is available in this "
                              "environment, so estimate_cost_bps prices spread and fees only "
                              "and omits volatility-scaled market impact; every drag figure "
                              "here is therefore a lower bound"),
        "scenarios": scenarios,
        "threshold_check": {
            "question": ("does a realistic cost model give up more than 200bps of annual "
                         "return relative to the published flat 10bps?"),
            "breakeven_one_way_bps": round(breakeven_rate, 1),
            "worst_modelled_one_way_bps": worst_modelled_rate,
            "worst_modelled_additional_drag_bps": round(worst_additional, 1),
            "verdict": ("not_crossed_by_the_spread_and_fee_floor"
                        if worst_additional <= THRESHOLD_BPS_OF_ANNUAL_RETURN
                        else "crossed"),
            "interpretation": (
                f"at {turnover['mean_monthly']:.1%} mean monthly turnover, any one-way rate "
                f"above roughly {breakeven_rate:.0f}bps crosses the 200bps threshold. The most "
                f"pessimistic rate this cost model produces without a volatility input is "
                f"{worst_modelled_rate:.0f}bps (stress scenario, illiquid tier), giving up "
                f"{worst_additional:.0f}bps a year more than the published flat 10bps -- under "
                "the threshold. But these rates are spread and fees only; the volatility-scaled "
                "market-impact term is omitted for want of per-name volatility, and adding it "
                "could push an illiquid book past 36bps. So: the floor does not cross the "
                "threshold, and the full model might. Turnover this high is a real cost "
                "problem, just not yet a demonstrated 200bps one."),
        },
        "unresolved": {
            "status": "blocked_network_policy",
            "what_is_missing": ("per-traded-name median dollar volume and realized volatility, "
                                "which decide the tier and the impact term for each leg"),
            "reproduction": [
                "python pipeline/backtest_monthly.py --cost-model tiered --cost-scenario base "
                "--out pipeline/reports/backtest_tiered_base.json",
                "python pipeline/backtest_monthly.py --cost-model tiered --cost-scenario stress "
                "--out pipeline/reports/backtest_tiered_stress.json",
            ],
        },
    }


def main():
    report = build_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    published = report["published_assumption"]
    print(f"mean monthly turnover: {report['realized_turnover']['mean_monthly']:.1%}")
    print(f"published 10bps: {published['annual_drag_bps']:.0f}bps/yr drag, "
          f"net {published['net_annualized_return']:.2%}, "
          f"implied gross {published['implied_gross_annualized_return']:.2%}")
    for scenario, tiers in report["scenarios"].items():
        parts = "  ".join(
            f"{tier} {block['one_way_bps']:.0f}bps -> {block['annual_drag_bps']:.0f}bps/yr "
            f"(net {block['net_annualized_return']:.2%})"
            for tier, block in tiers.items())
        print(f"{scenario:<11} {parts}")
    check = report["threshold_check"]
    print(f"200bps threshold crossed above ~{check['breakeven_one_way_bps']:.0f}bps one-way")
    print(f"wrote {OUT_PATH}")
    return report


if __name__ == "__main__":
    main()
