"""B3 — cost sensitivity report, built entirely from committed data.

``costs.py`` (WO-3) is already wired into ``backtest_monthly.py`` and ``ic_harness.py``. What
was missing is a report that actually shows the sensitivity. Re-running the backtest itself
under each cost regime needs each traded name's 5-year daily price/volume history. That cache
is now committed, so the full tiered rerun is reproducible; this report remains the cheaper
flat-rate sensitivity and labels the per-name rerun as available but not measured here.

What *is* real: every one of the 60 monthly rebalances in
``pipeline/backtest_monthly_results.json`` already stores its realized ``turnover`` and the
dollar ``cost`` actually charged under the flat 10bps model
(``cost = value_before * turnover * bps / 10000``). Because that formula is linear in bps,
``value_before`` is recoverable exactly from the two numbers already on each rebalance
(``value_before = cost / (turnover * 10 / 10000)``), without needing any price data. That
lets every rebalance be re-priced at a different flat bps rate -- gross (0bps) and the
optimistic/base/stress spread-only rates ``costs.estimate_cost_bps`` returns when no per-name
liquidity is available (conservative illiquid-tier spread, zero market impact, since impact
needs a trade size and per-name volatility this dataset does not carry).

What this does NOT do, stated plainly: it re-prices each historical trade at a different
rate holding the realized portfolio-value path fixed. It does not re-simulate the
compounding effect of a higher-cost regime on smaller future trade sizes -- that requires
the full backtest re-run, which is the blocked leg. This is a sensitivity estimate on the
already-realized trade sequence, not a new simulated one.
"""

import json
import os

from costs import estimate_cost_bps

HERE = os.path.dirname(__file__)
REPORT_PATH = os.path.join(HERE, "reports", "cost_sensitivity.json")
BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")
FLAT_BPS_REALIZED = 10.0  # the rate pipeline/backtest_monthly_results.json was actually run at
SCENARIOS = ("gross", "optimistic", "base", "stress")


def _scenario_bps():
    """Spread-only bps per scenario (no per-name liquidity/volatility available, so impact
    is necessarily zero -- costs.py itself falls back to the conservative illiquid tier's
    spread proxy when median_dollar_volume_60d is None, never a fabricated tighter number).
    """
    bps = {"gross": 0.0}
    for scenario in ("optimistic", "base", "stress"):
        estimate = estimate_cost_bps(median_dollar_volume_60d=None, scenario=scenario)
        bps[scenario] = estimate["total_bps"]
    return bps


def reprice_rebalance(rebalance, bps):
    """value_before recovered from the known flat-10bps cost actually charged, then the
    same trade re-priced at ``bps``. turnover == 0 costs nothing at any rate.
    """
    turnover = rebalance.get("turnover") or 0.0
    cost = rebalance.get("cost") or 0.0
    if turnover <= 0:
        return 0.0, 0.0
    value_before = cost / (turnover * FLAT_BPS_REALIZED / 10_000) if cost else None
    if value_before is None:
        return None, turnover
    return round(value_before * turnover * bps / 10_000, 2), turnover


def _load_backtest():
    with open(BACKTEST_PATH) as handle:
        return json.load(handle)


def build_report(backtest=None):
    backtest = backtest or _load_backtest()
    rebalances = (backtest.get("portfolio") or {}).get("rebalances") or []
    metrics = (backtest.get("portfolio") or {}).get("metrics") or {}
    scenario_bps = _scenario_bps()

    per_scenario = {}
    for scenario, bps in scenario_bps.items():
        costs_by_rebalance = []
        total_cost = 0.0
        for rebalance in rebalances:
            cost, turnover = reprice_rebalance(rebalance, bps)
            if cost is not None:
                total_cost += cost
            costs_by_rebalance.append({
                "signal_date": rebalance.get("signal_date"),
                "turnover": turnover,
                "cost": cost,
            })
        per_scenario[scenario] = {
            "cost_bps": bps,
            "total_cost": round(total_cost, 2),
            "cost_drag_vs_realized_flat_10bps": round(total_cost - metrics.get("estimated_transaction_cost", 0.0), 2),
        }

    turnovers = [rebalance.get("turnover") for rebalance in rebalances if isinstance(rebalance.get("turnover"), (int, float))]
    return {
        "method": (
            "Each rebalance's already-realized turnover and flat-10bps cost are used to "
            "recover value_before (cost = value_before * turnover * bps / 10000, solved for "
            "value_before), then re-priced at gross/optimistic/base/stress spread-only bps. "
            "Holds the realized portfolio-value path fixed; does not re-simulate compounding "
            "effects. No network calls."
        ),
        "realized_flat_10bps": {
            "cost_bps": FLAT_BPS_REALIZED,
            "total_cost": metrics.get("estimated_transaction_cost"),
            "final_value": metrics.get("final_value"),
            "cagr": metrics.get("cagr"),
        },
        "scenarios": per_scenario,
        "turnover": {
            "rebalances": len(rebalances),
            "mean_turnover": round(sum(turnovers) / len(turnovers), 4) if turnovers else None,
            "total_turnover": round(sum(turnovers), 4) if turnovers else None,
            "source": "pipeline/backtest_monthly_results.json portfolio.rebalances (already committed, real)",
        },
        "per_name_liquidity_legs": {
            "status": "not_measured_inputs_available",
            "measures": ["adv_participation_pct", "estimated_spread_bps_by_name",
                        "estimated_market_impact_bps_by_name", "days_to_liquidate"],
            "reason": (
                "costs.estimate_cost_bps's tiered/impact legs need each traded name's own "
                "median_dollar_volume_60d and annualized_volatility on the rebalance date. "
                "The committed pipeline/data/backtest_cache contains those inputs, but the "
                "three tiered scenario reruns are separate experiments and are not inferred "
                "from this flat-rate repricing."
            ),
            "reproduction_command": (
                "python pipeline/backtest_monthly.py --cost-model tiered --cost-scenario "
                "{optimistic,base,stress} --out pipeline/reports/backtest_tiered_<scenario>.json"
            ),
        },
        "never_present_gross_as_net": True,
    }


def write_report(backtest=None, path=REPORT_PATH):
    report = build_report(backtest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    return report


def main():
    report = write_report()
    print(f"Wrote {REPORT_PATH}")
    for scenario, detail in report["scenarios"].items():
        print(f"  {scenario}: {detail['cost_bps']:.2f}bps, total_cost=${detail['total_cost']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
