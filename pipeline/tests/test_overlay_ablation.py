"""The O-0 through O-4 ablation and the acceptance rule written before any result existed.

The rule is not a judgement made at evaluation time. It is read out of the freeze file, where
it was registered on 2026-08-12 with a timestamp, and applied mechanically. These tests check
that it is applied as written, in both directions, and that with no prospective data the
answer is that nothing may be adopted.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from overlay import ablation
from overlay.entry_timing import REGISTERED_VARIANTS


def test_the_acceptance_rule_was_written_before_results_existed():
    rule = ablation.acceptance_rule()

    assert rule["written_before_results_exist"] is True
    assert rule["written_at"] == "2026-08-12T00:00:00+00:00"
    assert rule["t_hurdle"] == 3.0
    assert rule["minimum_deflated_sharpe_improvement_over_O_0"] == 0.10
    assert rule["no_winner_is_chosen_on_historical_data"] is True
    assert "deleted rather than left dormant" in rule["outcome_if_not_met"]


def test_with_no_prospective_data_nothing_can_be_adopted():
    """The clock starts 2026-09-01. Until it reports, there is no out-of-sample record."""
    result = ablation.evaluate({variant: [] for variant in REGISTERED_VARIANTS})

    assert result["status"] == "awaiting_prospective_data"
    assert "adopted" not in result
    assert result["clock_start"] == "2026-09-01"


def test_a_variant_that_is_merely_better_does_not_clear_the_rule():
    """Both conditions, not either: the margin AND t > 3.0."""
    random.seed(41)
    control = [random.gauss(0.010, 0.030) for _ in range(60)]
    # Barely ahead of the control and noisy, which is the common case and must be refused.
    slight = [value + random.gauss(0.0005, 0.020) for value in control]

    result = ablation.evaluate({"O-0": control, "O-3": slight})

    assert result["status"] == "evaluated"
    assert result["decisions"]["O-3"]["adopt"] is False
    assert result["adopted"] == []
    assert "deleted rather than left dormant" in result["outcome"]


def test_a_variant_must_clear_the_margin_even_with_a_large_t_statistic():
    """A tiny but very consistent edge clears t > 3.0 and still fails the registered margin."""
    random.seed(43)
    control = [random.gauss(0.010, 0.030) for _ in range(120)]
    tiny_but_consistent = [value + 0.0004 for value in control]

    result = ablation.evaluate({"O-0": control, "O-2": tiny_but_consistent})

    decision = result["decisions"]["O-2"]
    assert decision["t_statistic"] > 3.0
    assert decision["clears_t_hurdle"] is True
    assert decision["clears_margin"] is False
    assert decision["adopt"] is False


def test_the_paired_t_statistic_removes_the_common_market_movement():
    """Both variants trade the same universe over the same periods, so pairing is correct.

    Leaving the shared movement in would inflate the standard error and make t > 3.0
    unreachable for reasons that have nothing to do with the overlay.
    """
    random.seed(47)
    market = [random.gauss(0.0, 0.08) for _ in range(80)]
    control = [value + random.gauss(0.0, 0.002) for value in market]
    variant = [value + 0.004 for value in control]

    paired = ablation._improvement_t_statistic(variant, control)

    # Unpaired, an 0.4% edge inside 8% market noise is invisible. Paired, it is not.
    assert paired > 10


def test_every_variant_reports_the_metrics_the_freeze_file_says_it_owes():
    random.seed(53)
    returns = [random.gauss(0.01, 0.03) for _ in range(40)]

    metrics = ablation.variant_metrics(
        "O-3", returns, turnover=1.8, holding_periods=[4, 6, 8], hit_rate=.54,
        deferrals=[{"sessions_deferred": 2, "deferral_benefit_pct": 1.2},
                   {"sessions_deferred": 1, "deferral_benefit_pct": -0.8}])

    for field in ("net_of_cost_return", "sharpe", "deflated_sharpe", "maximum_drawdown",
                  "turnover", "average_holding_period", "hit_rate",
                  "average_sessions_deferred", "deferral_counterfactual"):
        assert field in metrics, field
    assert metrics["average_sessions_deferred"] == 1.5
    assert metrics["deferral_counterfactual"]["measured"] == 2


def test_maximum_drawdown_is_measured_on_the_cumulative_path():
    assert ablation.maximum_drawdown([0.1, -0.5, 0.1]) > 0.4
    assert ablation.maximum_drawdown([0.01] * 10) == 0.0


def test_the_evaluation_carries_a_pbo_estimate_beside_every_comparison():
    random.seed(59)
    returns = {variant: [random.gauss(0.0, 0.03) for _ in range(96)]
               for variant in REGISTERED_VARIANTS}

    result = ablation.evaluate(returns)

    assert result["pbo"]["status"] == "ok"
    assert result["pbo"]["variants"] == 5


def test_the_trial_count_comes_from_the_hypothesis_log():
    random.seed(61)
    returns = {variant: [random.gauss(0.0, 0.03) for _ in range(40)]
               for variant in REGISTERED_VARIANTS}

    result = ablation.evaluate(returns)

    assert result["trials"] == 5
