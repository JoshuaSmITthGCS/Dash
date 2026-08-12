"""The O-0 through O-4 ablation, and the acceptance rule applied to its results.

Five cells and that is the whole budget. This module runs them, reports the metrics the freeze
file says each variant owes, and applies the acceptance rule that was written down before any
result existed.

The acceptance rule is not a judgement made here. It is read out of
pipeline/validation/harness_freeze.json, where it was registered on 2026-08-12 with a
timestamp, and applied mechanically. A variant is adopted only when it improves net-of-cost
deflated Sharpe over the O-0 control by at least the registered margin AND clears t > 3.0
(Harvey, Liu & Zhu, Review of Financial Studies 29(1), 2016). Otherwise the overlay stays off
and the momentum-turn code is deleted rather than left dormant.

Nothing here has run yet. The prospective clock starts 2026-09-01 and this module reports
``status: awaiting_prospective_data`` until it has periods to read.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(HERE)
sys.path.insert(0, PIPELINE)

from overlay.entry_timing import (REGISTERED_VARIANTS, apply_overlay,  # noqa: E402
                                  config_for_variant, deferral_distribution,
                                  gate_pass_rates)
from validation.deflated_sharpe import (clears_hlz_hurdle,  # noqa: E402
                                        deflated_sharpe_ratio,
                                        probability_of_backtest_overfitting, sharpe_ratio,
                                        sharpe_variance_across_trials)
from validation.hypothesis_log import trial_count  # noqa: E402

FREEZE_PATH = os.path.join(PIPELINE, "validation", "harness_freeze.json")
CONTROL_VARIANT = "O-0"


def acceptance_rule(freeze_path=FREEZE_PATH):
    with open(freeze_path, encoding="utf-8") as handle:
        freeze = json.load(handle)
    return (freeze.get("entry_timing_overlay") or {}).get("acceptance_rule") or {}


def maximum_drawdown(returns):
    """Worst peak-to-trough decline of the cumulative return path, as a positive fraction."""
    peak, worst, level = 1.0, 0.0, 1.0
    for value in returns:
        level *= 1 + value
        peak = max(peak, level)
        worst = max(worst, (peak - level) / peak if peak else 0.0)
    return worst


def variant_metrics(name, returns, *, turnover=None, holding_periods=None, hit_rate=None,
                    deferrals=None, trials=None, trial_variance=None):
    """Everything the freeze file says a variant owes, for one variant.

    ``returns`` are net of cost. Reporting a gross Sharpe beside a cost model and leaving the
    subtraction to the reader is how a strategy that does not survive its own costs gets
    published as one that does.
    """
    returns = [float(value) for value in (returns or [])]
    if len(returns) < 3:
        return {"variant_id": name, "status": "awaiting_prospective_data",
                "observations": len(returns)}
    trials = trials or trial_count(family="entry_timing_overlay") or len(REGISTERED_VARIANTS)
    sessions = sorted(entry.get("sessions_deferred", 0) for entry in (deferrals or []))
    return {
        "variant_id": name,
        "status": "measured",
        "observations": len(returns),
        "net_of_cost_return": sum(returns),
        "net_of_cost_mean_return": sum(returns) / len(returns),
        "sharpe": sharpe_ratio(returns),
        "deflated_sharpe": deflated_sharpe_ratio(returns, trials=trials,
                                                 trial_variance=trial_variance),
        "maximum_drawdown": maximum_drawdown(returns),
        "turnover": turnover,
        "average_holding_period": (sum(holding_periods) / len(holding_periods)
                                   if holding_periods else None),
        "hit_rate": hit_rate,
        "average_sessions_deferred": (sum(sessions) / len(sessions) if sessions else 0.0),
        "deferral_counterfactual": deferral_distribution(deferrals or []),
    }


def _improvement_t_statistic(variant_returns, control_returns):
    """Paired t statistic on the per-period return difference against the control.

    Paired rather than two-sample: the two variants trade the same universe over the same
    periods, so the common market movement is a nuisance term that pairing removes. Leaving it
    in inflates the standard error and would make the t > 3.0 hurdle unreachable for reasons
    that have nothing to do with the overlay.
    """
    length = min(len(variant_returns), len(control_returns))
    if length < 3:
        return None
    differences = [variant_returns[index] - control_returns[index] for index in range(length)]
    mean = sum(differences) / length
    variance = sum((value - mean) ** 2 for value in differences) / (length - 1)
    deviation = math.sqrt(variance)
    if not deviation:
        return None
    return mean / (deviation / math.sqrt(length))


def evaluate(returns_by_variant, *, extras=None, freeze_path=FREEZE_PATH):
    """Run the acceptance rule across the ablation and return an adoption decision.

    ``returns_by_variant`` is {variant_id: [net-of-cost returns per period]}. ``extras`` is
    {variant_id: {turnover, holding_periods, hit_rate, deferrals}} for the fields that are not
    derivable from returns alone.
    """
    extras = extras or {}
    rule = acceptance_rule(freeze_path)
    control = returns_by_variant.get(CONTROL_VARIANT) or []
    trials = trial_count(family="entry_timing_overlay") or len(REGISTERED_VARIANTS)
    trial_variance = sharpe_variance_across_trials(
        {name: series for name, series in returns_by_variant.items() if series})

    metrics = {name: variant_metrics(name, series, trials=trials,
                                     trial_variance=trial_variance,
                                     **(extras.get(name) or {}))
               for name, series in returns_by_variant.items()}

    if len(control) < 3:
        return {"status": "awaiting_prospective_data",
                "clock_start": "2026-09-01",
                "control_observations": len(control),
                "acceptance_rule": rule,
                "metrics": metrics,
                "note": ("The prospective clock has not produced enough periods to evaluate. "
                         "No variant has an out-of-sample record and none may be adopted.")}

    control_dsr = (metrics[CONTROL_VARIANT].get("deflated_sharpe") or {}).get("deflated_sharpe")
    margin = rule.get("minimum_deflated_sharpe_improvement_over_O_0", 0.10)
    hurdle = rule.get("t_hurdle", 3.0)

    decisions = {}
    for name, series in returns_by_variant.items():
        if name == CONTROL_VARIANT:
            continue
        variant_dsr = (metrics[name].get("deflated_sharpe") or {}).get("deflated_sharpe")
        improvement = (None if variant_dsr is None or control_dsr is None
                       else variant_dsr - control_dsr)
        statistic = _improvement_t_statistic(series, control)
        hlz = clears_hlz_hurdle(statistic, hurdle)
        decisions[name] = {
            "deflated_sharpe": variant_dsr,
            "control_deflated_sharpe": control_dsr,
            "improvement": improvement,
            "required_improvement": margin,
            "clears_margin": improvement is not None and improvement >= margin,
            "t_statistic": statistic,
            "clears_t_hurdle": hlz["clears"],
            "adopt": bool(improvement is not None and improvement >= margin and hlz["clears"]),
        }

    adopted = [name for name, decision in decisions.items() if decision["adopt"]]
    return {
        "status": "evaluated",
        "acceptance_rule": rule,
        "trials": trials,
        "metrics": metrics,
        "decisions": decisions,
        "adopted": adopted,
        "pbo": probability_of_backtest_overfitting(returns_by_variant),
        "outcome": ("adopt " + ", ".join(sorted(adopted)) if adopted else
                    "no variant clears the rule: the overlay stays off permanently and the "
                    "momentum-turn code is deleted rather than left dormant"),
    }


def run_variant(ranked_rows, series_for, variant_id, *, deferrals=None,
                freeze_path=FREEZE_PATH):
    """Apply one registered ablation cell to a ranked screen and report its gate pass rates."""
    config = config_for_variant(variant_id)
    rows = apply_overlay(ranked_rows, series_for, config, deferrals=deferrals,
                         freeze_path=freeze_path)
    return {"variant_id": variant_id,
            "label": REGISTERED_VARIANTS[variant_id]["label"],
            "rows": rows,
            "gate_pass_rates": gate_pass_rates(rows)}
