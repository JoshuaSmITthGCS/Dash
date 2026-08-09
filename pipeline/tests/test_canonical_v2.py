import json
import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from canonical_metrics import (Observation, applicability_for, calculate_peg,
                               classify_profile, METRIC_REGISTRY, reconcile, yahoo_observations)
from fundamentals_extended import extended_observations
from migrate_advisor_v2 import migrate
from peer_groups import canonical_percentiles
from scoring_v2 import build_v2_analysis
from scorer import SETTINGS


with open(os.path.join(os.path.dirname(__file__), "fixtures", "regression_cases.json")) as handle:
    CASES = json.load(handle)


class PegTests(unittest.TestCase):
    def test_percentage_points(self):
        self.assertEqual(calculate_peg(10, 10, "percentage_points", periods_match=True, definition_known=True), 1.0)

    def test_decimal_is_normalized(self):
        self.assertEqual(calculate_peg(10, 0.10, "decimal", periods_match=True, definition_known=True), 1.0)

    def test_negative_growth_is_unavailable(self):
        self.assertIsNone(calculate_peg(10, -10, "percentage_points", periods_match=True, definition_known=True))

    def test_unknown_or_mismatched_growth_is_unavailable(self):
        self.assertIsNone(calculate_peg(10, 10, "percentage_points", periods_match=False, definition_known=True))
        self.assertIsNone(calculate_peg(10, 10, "percentage_points", periods_match=True, definition_known=False))


class RegistryTests(unittest.TestCase):
    def test_every_registered_metric_has_the_full_contract(self):
        required = {
            "human_label", "definition", "formula_version", "required_normalized_inputs",
            "accepted_units", "output_unit", "period_type", "designation",
            "preferred_providers", "fallback_providers", "applicability_profiles",
            "direction", "missing_data_policy", "stale_after_days", "valid_numeric_range",
            "denominator_handling", "quality_checks", "scoring_transformation",
            "confidence_calculation",
        }
        for metric_id, declaration in METRIC_REGISTRY["metrics"].items():
            with self.subTest(metric_id=metric_id):
                self.assertFalse(required - set(declaration))


class YahooObservationsTests(unittest.TestCase):
    def test_debt_to_equity_is_converted_from_a_percentage(self):
        observations = yahoo_observations({"debtToEquity": 80})
        self.assertEqual(observations["debt_to_equity"][0]["value"], 0.8)

    def test_free_cash_flow_yield_is_derived_from_the_quote(self):
        observations = yahoo_observations({"freeCashflow": 500, "marketCap": 10000})
        self.assertEqual(observations["free_cash_flow_yield"][0]["value"], 0.05)

    def test_free_cash_flow_yield_is_skipped_without_a_market_cap(self):
        observations = yahoo_observations({"freeCashflow": 500})
        self.assertNotIn("free_cash_flow_yield", observations)

    def test_covers_the_remaining_directly_mapped_quote_fields(self):
        observations = yahoo_observations({
            "priceToSalesTrailing12Months": 3.5, "returnOnEquity": 0.2, "profitMargins": 0.15,
        })
        self.assertEqual(observations["price_to_sales"][0]["value"], 3.5)
        self.assertEqual(observations["return_on_equity"][0]["value"], 0.2)
        self.assertEqual(observations["profit_margin"][0]["value"], 0.15)


class ProfileTests(unittest.TestCase):
    def test_all_regression_profiles_route_deterministically(self):
        for name, case in CASES.items():
            with self.subTest(name=name):
                self.assertEqual(classify_profile(case), case["expected_profile"])

    def test_insurer_suppresses_industrial_metrics(self):
        for metric in ("peg", "current_ratio", "free_cash_flow_yield", "return_on_invested_capital",
                       "net_debt_to_ebitda", "ev_to_ebitda", "altman_z"):
            with self.subTest(metric=metric):
                self.assertIn(applicability_for(metric, "diversified_insurer")["status"], ("suppressed", "replaced"))


class ReconciliationTests(unittest.TestCase):
    def test_preserves_conflict_and_uses_preferred_without_averaging(self):
        rows = [
            Observation(100, "usd", "yahoo", "totalRevenue").to_dict(),
            Observation(110, "usd", "sec_xbrl", "Revenues").to_dict(),
        ]
        result = reconcile("revenue_ttm", rows)
        self.assertEqual(result["canonical"]["value"], 110)
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(len(result["conflicts"]), 1)


class PeerTests(unittest.TestCase):
    """Peer claims are tiers over a sufficient sample, or nothing at all.

    See research/audit/CURRENT_MODEL_AUDIT.md section 2 for the published claim these
    replace: "Cheaper than approximately 85% of Property & casualty insurers, based on 14
    valid peers", printed for a name in the expensive half of its group.
    """

    def group(self, count, *, sector="Healthcare", start=10.0, step=1.0):
        return [{"ticker": f"T{index:03d}", "sector": sector,
                 "categories": {"valuation": start + index * step}}
                for index in range(count)]

    def test_a_sufficient_sample_publishes_a_tier_and_its_n(self):
        result = canonical_percentiles(self.group(30), constructed_at="2026-08-02")
        cheapest = result["T029"]
        self.assertEqual(cheapest["tier"], "cheapest_third")
        self.assertEqual(cheapest["peer_context"]["tier"], "cheapest_third")
        self.assertEqual(cheapest["peer_context"]["peer_count_with_valid_data"], 30)
        self.assertEqual(result["T000"]["tier"], "most_expensive_third")
        self.assertEqual(result["T015"]["tier"], "middle_third")

    def test_no_continuous_percentile_is_published_at_all(self):
        """The ranked quantity is a composite of discrete bands. It has no percentile."""
        result = canonical_percentiles(self.group(30))
        for metadata in result.values():
            self.assertNotIn("value", metadata)
            self.assertNotIn("display_value", metadata)

    def test_below_the_minimum_the_claim_is_absent_not_degraded(self):
        result = canonical_percentiles(self.group(29))
        for ticker, metadata in result.items():
            self.assertIsNone(metadata["peer_context"], ticker)
            self.assertIsNone(metadata["tier"], ticker)
            self.assertIsNone(metadata["ordinal"], ticker)
            self.assertEqual(metadata["invalid_reason"], "insufficient_valid_peers")
            self.assertEqual(metadata["peer_count_with_valid_data"], 29)

    def test_a_fourteen_name_insurer_group_publishes_nothing(self):
        """The exact shape of the THG claim: 14 valid P&C insurer peers."""
        rows = [{"ticker": f"INS{index}", "sector": "Financial Services",
                 "industry": "Insurance - Property & Casualty",
                 "categories": {"valuation": 50.0 + index}} for index in range(14)]
        result = canonical_percentiles(rows)
        self.assertEqual(result["INS13"]["peer_group_id"], "property_casualty_insurer")
        self.assertIsNone(result["INS13"]["peer_context"])
        self.assertEqual(result["INS13"]["invalid_reason"], "insufficient_valid_peers")

    def test_tied_scores_share_a_tier_rather_than_being_split_alphabetically(self):
        """THG and SIGI both scored exactly 95.7 and were published 7.7 points apart."""
        rows = self.group(30)
        for row in rows[10:20]:
            row["categories"]["valuation"] = 50.0
        result = canonical_percentiles(rows)
        tied = {result[row["ticker"]]["tier"] for row in rows[10:20]}
        self.assertEqual(len(tied), 1, f"tied names landed in different tiers: {tied}")

    def test_the_ordinal_handed_downstream_is_a_tier_midpoint(self):
        result = canonical_percentiles(self.group(30))
        self.assertEqual(sorted({metadata["ordinal"] for metadata in result.values()}),
                         [16.7, 50.0, 83.3])


class DecisionLayerTests(unittest.TestCase):
    def test_hig_rejects_provider_peg_and_suppresses_generic_insurer_metrics(self):
        case = CASES["HIG"]
        legacy = {"peg": 100, "current_ratio": 100, "free_cash_flow_yield": 100,
                  "return_on_equity": 100, "categories": {}}
        result = build_v2_analysis(case, legacy)
        self.assertIsNone(result["canonical_metrics"]["peg"])
        self.assertEqual(result["metric_status"]["peg"]["status"], "suppressed")
        self.assertEqual(result["metric_status"]["current_ratio"]["status"], "suppressed")
        self.assertIn("free_cash_flow_yield", result["structural"]["suppressed_metrics"])

    def test_bsx_negative_revisions_are_visible_and_not_erased_by_trailing_growth(self):
        case = CASES["BSX"]
        legacy = {"peg": 45, "forward_pe": 45, "price_to_sales": 15, "ev_to_ebitda": 15,
                  "revenue_growth": 100, "earnings_growth": 100, "categories": {}}
        result = build_v2_analysis(case, legacy)
        self.assertIsNone(result["structural"]["categories"]["valuation"])
        self.assertIn("legacy_value_missing_lineage", result["metric_status"]["forward_pe"]["quality_flags"])
        self.assertEqual(result["timeliness"]["forward"]["revision_30d"], -8)
        self.assertLess(result["timeliness"]["effective_score"], 45)
        self.assertNotEqual(result["timeliness"]["classification"], "improving")

    def test_coverage_and_evidence_weight_are_distinct(self):
        result = build_v2_analysis({"sector": "Technology", "forward_pe": 20}, {"forward_pe": 80})
        self.assertEqual(result["structural"]["coverage"], 0)
        self.assertEqual(result["structural"]["evidence_weight_resolved"], 0)
        self.assertNotEqual(result["structural"]["coverage_basis"], result["structural"]["evidence_weight_basis"])

    def test_stale_fundamental_is_disclosed_and_reduces_confidence(self):
        observation = Observation(20, "multiple", "yahoo", "forwardPE", fetched_at="2020-01-01T00:00:00+00:00", is_forward=True).to_dict()
        result = build_v2_analysis(
            {"ticker": "STALE", "sector": "Industrials", "forward_pe": 20,
             "observations": {"forward_pe": [observation]}},
            {"forward_pe": 80},
        )
        self.assertIn("forward_pe", result["structural"]["stale_metrics"])
        self.assertGreater(result["structural"]["stale_weight"], 0)

    def test_conflicting_providers_are_disclosed_without_averaging(self):
        observations = {
            "forward_pe": [
                Observation(20, "multiple", "alpha_vantage", "ForwardPE").to_dict(),
                Observation(30, "multiple", "yahoo", "forwardPE").to_dict(),
            ]
        }
        result = build_v2_analysis(
            {"ticker": "CONFLICT", "sector": "Industrials", "forward_pe": 20, "observations": observations},
            {"forward_pe": 80},
        )
        self.assertIn("forward_pe", result["structural"]["provider_conflicts"])
        self.assertGreater(result["structural"]["conflicted_weight"], 0)

    def test_negative_book_multiple_is_not_a_valid_observation(self):
        rows = [Observation(-4, "multiple", "yahoo", "priceToBook").to_dict()]
        self.assertIsNone(reconcile("price_to_book", rows)["canonical"])

    def test_statement_derived_metrics_are_no_longer_discarded_for_missing_lineage(self):
        # Regression for the gap that left most companies at ~7% v2 evidence weight despite
        # derive_extended() having computed real values: those values never got a canonical
        # observation, so build_v2_analysis treated them as unlineaged legacy scalars and
        # dropped them. extended_observations() is the fix - wired into fetch_advisor.py's
        # enrich() step, it gives them the same lineage a directly-observed metric gets.
        extended = {
            "altman_z": 10.13, "accruals_ratio": -0.04, "asset_growth": 0.01,
            "statement_periods": ["2025-12-31", "2024-12-31"],
        }
        legacy = {"altman_z": 70, "accruals_ratio": 60, "asset_growth": 55, "categories": {}}
        snapshot = {
            "sector": "Healthcare", "altman_z": 10.13, "accruals_ratio": -0.04, "asset_growth": 0.01,
            "observations": extended_observations(extended),
        }
        result = build_v2_analysis(snapshot, legacy)
        for metric_id in ("altman_z", "accruals_ratio", "asset_growth"):
            with self.subTest(metric_id=metric_id):
                self.assertEqual(result["metric_status"][metric_id]["status"], "applied")
                self.assertNotIn("legacy_value_missing_lineage",
                                 result["metric_status"][metric_id]["quality_flags"])
        self.assertNotIn("altman_z", result["structural"]["missing_metrics"])
        self.assertGreater(result["structural"]["evidence_weight_resolved"], 0)

    def test_sales_multiple_aliases_to_the_registered_price_to_sales_metric(self):
        # settings.json's valuation weights key this "sales_multiple"; the canonical metric
        # (and every observation for it) is registered as "price_to_sales". Without the
        # alias, applicability/observation lookups miss and this metric is always dropped.
        observations = {"price_to_sales": [Observation(3.5, "multiple", "yahoo",
                                                        "priceToSalesTrailing12Months").to_dict()]}
        snapshot = {"sector": "Technology", "price_to_sales": 3.5, "observations": observations}
        result = build_v2_analysis(snapshot, {"sales_multiple": 65, "categories": {}})
        self.assertEqual(result["metric_status"]["price_to_sales"]["status"], "applied")
        self.assertEqual(result["metric_status"]["price_to_sales"]["score_contribution"], 65)


class MigrationTests(unittest.TestCase):
    def test_v1_migration_retains_legacy_and_adds_v2(self):
        payload = {
            "schema_version": 1, "generated_at": "2026-08-02T00:00:00+00:00",
            "universe": ["TEST"], "research": [{"ticker": "TEST", "score": 77,
            "sector": "Technology", "fundamental_detail": {"forward_pe": 80},
            "fundamental_categories": {"valuation": 80}}], "portfolio_coverage": [],
            "source_status": {}, "methodology": {}
        }
        migrated = migrate(payload)
        self.assertEqual(migrated["schema_version"], SETTINGS["model"]["advisor_schema_version"])
        self.assertEqual(migrated["research"][0]["score"], 77)
        self.assertIn("analysis_v2", migrated["research"][0])
        self.assertIn("run_manifest", migrated)


if __name__ == "__main__":
    unittest.main()


class TimelinessLayerAbsenceTest(unittest.TestCase):
    """The timeliness layer must publish nothing when no timing input resolves.

    It used to publish effective_score 50.0 with confidence 0.0 for every company in the
    universe -- a constant that the shadow policy then branched on. See
    research/audit/CURRENT_MODEL_AUDIT.md section 3.
    """

    def snapshot(self, **updates):
        base = {"ticker": "TEST", "sector": "Technology", "industry": "Software",
                "forward_pe": 20.0, "return_on_equity": 0.2}
        base.update(updates)
        return base

    def test_no_timing_input_publishes_no_score(self):
        analysis = build_v2_analysis(self.snapshot(), {"forward_pe": 80.0})
        timeliness = analysis["timeliness"]
        self.assertIsNone(timeliness["raw_score"])
        self.assertIsNone(timeliness["effective_score"])
        self.assertEqual(timeliness["classification"], "unavailable")
        self.assertIsNotNone(timeliness["unavailable_reason"])

    def test_a_resolved_timing_input_produces_a_score(self):
        analysis = build_v2_analysis(
            self.snapshot(earnings_surprise=5.0), {"forward_pe": 80.0})
        timeliness = analysis["timeliness"]
        self.assertIsNotNone(timeliness["raw_score"])
        self.assertIsNotNone(timeliness["effective_score"])
        self.assertNotEqual(timeliness["classification"], "unavailable")

    def test_dropped_timing_weight_is_recorded_not_imputed(self):
        analysis = build_v2_analysis(
            self.snapshot(earnings_surprise=5.0), {"forward_pe": 80.0})
        record = analysis["timeliness"]["weight_renormalization"]
        self.assertEqual(record["inputs_dropped"], ["forward_eps_revision_30d"])
        self.assertEqual(record["weights_effective"], {"earnings_surprise": 1.0})
        self.assertAlmostEqual(record["covered_weight_fraction"], 0.3)
