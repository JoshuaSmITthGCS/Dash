import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from recommendation_policy_v2 import build_recommendation_v2, effective_score


def analysis(structural=80, timeliness=80, confidence=0.9, profile="general", categories=None):
    base = {
        "raw_score": structural, "effective_score": structural,
        "confidence": confidence, "coverage": confidence,
        "available_weight": confidence, "applicable_weight": 1.0,
        "missing_metrics": [], "stale_metrics": [], "provider_conflicts": [],
        "categories": categories or {},
    }
    timely = {
        "raw_score": timeliness, "effective_score": timeliness,
        "confidence": confidence, "coverage": confidence,
        "available_weight": confidence, "applicable_weight": 1.0,
        "missing_metrics": [], "stale_metrics": [], "provider_conflicts": [],
    }
    return {"structural": base, "timeliness": timely, "applicability_profile": profile}


def position(**updates):
    value = {
        "shares": 100, "current_price": 100, "weighted_cost_basis": 90,
        "adjusted_high_water_mark": 105, "portfolio_value": 100000,
        "price_fresh": True, "liquidity": "normal", "tax_cost": "normal",
    }
    value.update(updates)
    return value


def portfolio(weight=0.03, target=0.03, maximum=0.05, **updates):
    value = {"current_weight": weight, "target_weight": target, "maximum_weight": maximum}
    value.update(updates)
    return value


def group_signals(severity, confidence=0.9):
    return [
        {"reason_code": "subfactor_a", "severity": severity, "confidence": confidence, "persistence_periods": 2},
        {"reason_code": "subfactor_b", "severity": severity, "confidence": confidence, "persistence_periods": 2},
    ]


class RecommendationPolicyV2Tests(unittest.TestCase):
    def test_confidence_shrinkage(self):
        self.assertEqual(effective_score(90, 0.5), 70.0)

    def test_1_strong_structural_and_timing_is_buy_candidate(self):
        result = build_recommendation_v2("AAA", analysis())
        self.assertEqual(result["company"]["action"]["label"], "buy")
        self.assertEqual(result["position_action"]["label"], "no_action")

    def test_2_strong_structural_weak_timing_is_quality_watch(self):
        result = build_recommendation_v2("AAA", analysis(85, 30))
        self.assertEqual(result["company"]["action"]["label"], "quality_watch")

    def test_3_existing_strong_company_with_weak_timing_is_hold(self):
        result = build_recommendation_v2("AAA", analysis(85, 30), position=position(), portfolio=portfolio())
        self.assertEqual(result["company"]["action"]["label"], "hold_existing_position")
        self.assertEqual(result["position_action"]["label"], "hold")

    def test_4_weak_structural_strong_timing_is_tactical_only(self):
        result = build_recommendation_v2("AAA", analysis(30, 90))
        self.assertEqual(result["company"]["action"]["label"], "tactical_candidate")
        self.assertNotEqual(result["company"]["action"]["label"], "buy")

    def test_5_two_mild_groups_are_not_fixed_33_percent(self):
        overrides = {"business_fundamentals": group_signals(0.5), "market_behavior": group_signals(0.5)}
        result = build_recommendation_v2("AAA", analysis(), position=position(), portfolio=portfolio(), deterioration_overrides=overrides)
        self.assertEqual(result["position_action"]["label"], "trim")
        self.assertNotEqual(result["position_action"]["trim_percent"], 0.33)
        self.assertLess(result["position_action"]["trim_percent"], 0.20)

    def test_6_two_severe_persistent_groups_produce_material_trim(self):
        overrides = {"business_fundamentals": group_signals(1), "market_behavior": group_signals(1)}
        result = build_recommendation_v2("AAA", analysis(), position=position(), portfolio=portfolio(), deterioration_overrides=overrides)
        self.assertGreaterEqual(result["position_action"]["trim_percent"], 0.20)

    def test_7_three_severe_groups_produce_large_trim(self):
        overrides = {name: group_signals(1) for name in ("business_fundamentals", "market_behavior", "positioning_sentiment")}
        result = build_recommendation_v2("AAA", analysis(), position=position(), portfolio=portfolio(), deterioration_overrides=overrides)
        self.assertGreaterEqual(result["position_action"]["trim_percent"], 0.50)

    def test_8_hard_stop_exits_position_without_selling_thesis(self):
        result = build_recommendation_v2(
            "AAA", analysis(85, 55), position=position(current_price=70, weighted_cost_basis=100), portfolio=portfolio()
        )
        self.assertNotEqual(result["company"]["action"]["label"], "sell_thesis")
        self.assertEqual(result["position_action"]["label"], "exit")
        self.assertIn("sell_position_hard_cost_basis_stop", result["position_action"]["reason_codes"])

    def test_9_verified_thesis_break_sells_thesis_and_exits_if_held(self):
        event = {"code": "fraud_verified", "source": "regulator", "timestamp": "2026-08-01T12:00:00Z",
                 "confidence": 0.99, "materiality": 1.0, "explanation": "Regulator confirmed fabricated accounts."}
        result = build_recommendation_v2("AAA", analysis(), position=position(), portfolio=portfolio(), thesis_events=[event])
        self.assertEqual(result["company"]["action"]["label"], "sell_thesis")
        self.assertEqual(result["position_action"]["label"], "exit")

    def test_ordinary_headline_cannot_break_thesis(self):
        event = {"code": "fraud_verified", "source": "blog", "timestamp": "2026-08-01T12:00:00Z",
                 "confidence": 0.3, "materiality": 0.4, "explanation": "Unverified claim."}
        result = build_recommendation_v2("AAA", analysis(), thesis_events=[event])
        self.assertNotEqual(result["company"]["action"]["label"], "sell_thesis")

    def test_10_low_confidence_gates_company_action(self):
        result = build_recommendation_v2("AAA", analysis(confidence=0.3))
        self.assertEqual(result["company"]["action"]["label"], "insufficient_evidence")
        self.assertLessEqual(result["company"]["action"]["confidence"], 0.3)

    def test_11_small_position_returns_immaterial_review(self):
        overrides = {"business_fundamentals": group_signals(1), "market_behavior": group_signals(1)}
        result = build_recommendation_v2(
            "AAA", analysis(), position=position(shares=0.1, current_price=100), portfolio=portfolio(),
            deterioration_overrides=overrides,
        )
        self.assertEqual(result["position_action"]["label"], "review")
        self.assertIn("trim_economically_immaterial", result["position_action"]["reason_codes"])

    def test_12_concentration_trim_is_not_thesis_deterioration(self):
        result = build_recommendation_v2("AAA", analysis(), position=position(), portfolio=portfolio(weight=0.10))
        self.assertEqual(result["position_action"]["label"], "trim")
        self.assertEqual(result["position_action"]["reason_namespace"], "portfolio_concentration")

    def test_13_price_decline_and_trailing_stop_are_not_two_thesis_groups(self):
        technical = {"return_20d": -12, "return_60d": -25, "relative_strength_20d": -18, "coverage": 0.9}
        result = build_recommendation_v2(
            "AAA", analysis(), technical=technical,
            position=position(current_price=80, adjusted_high_water_mark=100, weighted_cost_basis=70), portfolio=portfolio(),
        )
        flagged = [group for group in result["company"]["deterioration_groups"] if group["flagged"]]
        self.assertEqual([group["group"] for group in flagged], ["market_behavior"])
        self.assertEqual(result["position_action"]["reason_namespace"], "position_rule")

    def test_14_insurer_declares_sector_specific_critical_inputs(self):
        result = build_recommendation_v2("HIG", analysis(profile="diversified_insurer"))
        self.assertIn("insurer_capital", result["critical_field_requirements"])

    def test_15_etf_uses_its_own_stop_profile(self):
        result = build_recommendation_v2(
            "VOO", analysis(profile="etf"), position=position(stop_profile="broad_etf"), portfolio=portfolio()
        )
        self.assertEqual(result["position_rule_state"]["profile"], "broad_etf")
        self.assertIn("tracking_quality", result["critical_field_requirements"])

    def test_average_down_is_stricter_than_initial_entry(self):
        result = build_recommendation_v2(
            "AAA", analysis(), portfolio=portfolio(),
            position=position(current_price=80, weighted_cost_basis=100, valuation_meaningfully_improved=False),
        )
        self.assertEqual(result["entry_action"]["type"], "average_down")
        self.assertFalse(result["entry_action"]["allowed"])
        self.assertIn("valuation_improvement_not_confirmed", result["entry_action"]["reason_codes"])

    def test_reentry_requires_cooldown_recovery_and_requalification(self):
        result = build_recommendation_v2(
            "AAA", analysis(), portfolio=portfolio(),
            position={"shares": 0, "stopped_out_at": "2026-07-25T00:00:00Z", "recovery_condition_met": False},
            generated_at="2026-08-02T00:00:00Z",
        )
        self.assertEqual(result["entry_action"]["type"], "reentry_after_stop")
        self.assertFalse(result["entry_action"]["allowed"])
        self.assertIn("reentry_cooldown_active", result["entry_action"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()


def analysis_without_timeliness(structural=80, confidence=0.9, profile="general"):
    """What build_v2_analysis actually emits when no forward estimate resolves."""
    payload = analysis(structural=structural, confidence=confidence, profile=profile)
    payload["timeliness"] = {
        "raw_score": None, "effective_score": None, "confidence": 0.0, "coverage": 0.0,
        "available_weight": 0.0, "applicable_weight": 1.0,
        "missing_metrics": ["earnings_surprise", "forward_eps_revision_30d"],
        "stale_metrics": [], "provider_conflicts": [],
        "unavailable_reason": "no free forward-estimate provider",
    }
    return payload


class UnresolvedTimelinessTest(unittest.TestCase):
    """An unresolved axis must be reported as unresolved, never scored as neutral.

    Before this, timeliness published a constant 50.0, which sat below the configured
    timeliness_acceptable of 55, so buy_candidate was unreachable and every published
    company resolved to insufficient_evidence.
    """

    def test_matrix_names_the_missing_axis_instead_of_scoring_it(self):
        result = build_recommendation_v2("TEST", analysis_without_timeliness(structural=90))
        self.assertEqual(result["company"]["matrix_classification"],
                         "quality_watch_timeliness_unavailable")

    def test_strong_structural_alone_never_becomes_a_buy(self):
        result = build_recommendation_v2("TEST", analysis_without_timeliness(structural=99))
        self.assertNotEqual(result["company_action"]["label"], "buy")

    def test_confidence_reflects_the_assessed_layer_not_the_missing_one(self):
        result = build_recommendation_v2("TEST", analysis_without_timeliness(confidence=0.9))
        self.assertAlmostEqual(result["company_action"]["confidence"], 0.9)
        self.assertNotEqual(result["company_action"]["label"], "insufficient_evidence")

    def test_the_missing_layer_is_named_in_the_payload(self):
        result = build_recommendation_v2("TEST", analysis_without_timeliness())
        self.assertEqual(result["company"]["timeliness"]["effective_score"], None)

    def test_averaging_down_is_blocked_when_timing_is_unknown(self):
        """Unknown timing is not acceptable timing."""
        result = build_recommendation_v2(
            "TEST", analysis_without_timeliness(structural=90),
            position=position(current_price=80, weighted_cost_basis=100,
                              valuation_meaningfully_improved=True),
            portfolio=portfolio())
        entry = result["entry_action"] if "entry_action" in result else result.get("entry")
        self.assertEqual(entry["type"], "average_down")
        self.assertFalse(entry["allowed"])
        self.assertIn("timeliness_unavailable_or_deteriorating", entry["reason_codes"])

    def test_a_resolved_timeliness_axis_still_reaches_buy(self):
        result = build_recommendation_v2("TEST", analysis(structural=90, timeliness=90))
        self.assertEqual(result["company"]["matrix_classification"], "buy_candidate")
