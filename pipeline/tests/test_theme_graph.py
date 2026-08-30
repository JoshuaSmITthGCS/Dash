import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import theme_graph as tg
import themes


def theme(id_, root_driver_tag, role="supplier", theme_exposure_score=80):
    return {"theme_id": id_, "display_name": id_, "root_driver_tag": root_driver_tag,
            "role": role, "theme_exposure_score": theme_exposure_score}


class EdgeWeightTests(unittest.TestCase):
    def test_same_root_driver_outweighs_everything_else(self):
        a = theme("a", "ELECTRIFICATION_DEMAND", role="root")
        b = theme("b", "ELECTRIFICATION_DEMAND", role="supplier")
        edge_type, weight = tg.edge_between(a, b)
        self.assertEqual(edge_type, "shared_root_driver")
        self.assertEqual(weight, 3.0)

    def test_two_null_root_drivers_are_not_treated_as_shared(self):
        # A null root_driver_tag means "not a claim about one of the five drivers", not "the
        # same unnamed driver" - two themes with no tag must not collapse together.
        a = theme("a", None, role="root")
        b = theme("b", None, role="root")
        edge_type, _ = tg.edge_between(a, b)
        self.assertNotEqual(edge_type, "shared_root_driver")

    def test_supplier_roles_across_different_drivers_is_a_supplier_edge(self):
        a = theme("a", "ELECTRIFICATION_DEMAND", role="supplier")
        b = theme("b", "DEGLOBALIZATION_SECURITY", role="enabler")
        edge_type, weight = tg.edge_between(a, b)
        self.assertEqual(edge_type, "shared_supplier")
        self.assertEqual(weight, 2.0)

    def test_labor_scarcity_theme_with_a_supplying_role_is_a_workforce_edge(self):
        a = theme("a", "AGING_LABOR_SCARCITY", role="enabler")
        b = theme("b", "DEGLOBALIZATION_SECURITY", role="root")
        edge_type, weight = tg.edge_between(a, b)
        self.assertEqual(edge_type, "shared_workforce_constraint")
        self.assertEqual(weight, 1.5)

    def test_unrelated_root_roles_fall_back_to_coincidental(self):
        a = theme("a", "DEGLOBALIZATION_SECURITY", role="root")
        b = theme("b", "RESOURCE_WATER_FOOD_SECURITY", role="root")
        edge_type, weight = tg.edge_between(a, b)
        self.assertEqual(edge_type, "coincidental_sector")
        self.assertEqual(weight, 0.5)

    def test_edge_classification_is_order_independent(self):
        a = theme("a", "AGING_LABOR_SCARCITY", role="enabler")
        b = theme("b", "DEGLOBALIZATION_SECURITY", role="root")
        self.assertEqual(tg.edge_between(a, b), tg.edge_between(b, a))


class ClusterCollapseTests(unittest.TestCase):
    def test_three_or_more_same_driver_themes_collapse_to_one(self):
        cleared = [theme("a", "ELECTRIFICATION_DEMAND"), theme("b", "ELECTRIFICATION_DEMAND"),
                   theme("c", "ELECTRIFICATION_DEMAND")]
        effective_count, groups = tg.collapse_clusters(cleared)
        self.assertEqual(effective_count, 1)
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]["original_themes"]), {"a", "b", "c"})

    def test_two_same_driver_themes_do_not_collapse(self):
        cleared = [theme("a", "ELECTRIFICATION_DEMAND"), theme("b", "ELECTRIFICATION_DEMAND")]
        effective_count, groups = tg.collapse_clusters(cleared)
        self.assertEqual(effective_count, 2)
        self.assertEqual(groups, [])

    def test_collapse_representative_is_the_highest_exposure_member(self):
        cleared = [theme("a", "ELECTRIFICATION_DEMAND", theme_exposure_score=40),
                   theme("b", "ELECTRIFICATION_DEMAND", theme_exposure_score=95),
                   theme("c", "ELECTRIFICATION_DEMAND", theme_exposure_score=60)]
        _, groups = tg.collapse_clusters(cleared)
        self.assertEqual(groups[0]["representative"], "b")

    def test_untagged_themes_never_collapse_into_each_other(self):
        cleared = [theme("a", None), theme("b", None), theme("c", None)]
        effective_count, groups = tg.collapse_clusters(cleared)
        self.assertEqual(effective_count, 3)
        self.assertEqual(groups, [])

    def test_a_cross_driver_theme_is_not_swept_into_an_unrelated_collapse(self):
        # The Eaton-style case: four electrification themes collapse to one effective theme,
        # a fifth theme on a different driver stays its own effective theme.
        cleared = [theme("ai", "ELECTRIFICATION_DEMAND"), theme("grid", "ELECTRIFICATION_DEMAND"),
                   theme("energy", "ELECTRIFICATION_DEMAND"), theme("cooling", "ELECTRIFICATION_DEMAND"),
                   theme("reshoring", "DEGLOBALIZATION_SECURITY")]
        effective_count, groups = tg.collapse_clusters(cleared)
        self.assertEqual(effective_count, 2)
        self.assertEqual(len(groups), 1)


class StructuralRankTests(unittest.TestCase):
    def base_payload(self, **overrides):
        payload = {
            "id": "t", "count": 10, "eligible_count": 8, "mean_confidence_eligible": 0.9,
            "trend": {"direction": {"relative_strength_median": 12.0},
                      "verdict": {"label": "broadening"},
                      "breadth": {"outperforming_share": 0.7}},
            "rows": [],
        }
        payload.update(overrides)
        return payload

    def test_composite_score_matches_the_declared_weights(self):
        rank = tg.structural_rank(self.base_payload())
        # evidence 0.9*0.40 + excess_return norm((12+30)/60=0.7)*0.35 + breadth 0.8*0.25
        expected = 0.9 * 0.40 + 0.7 * 0.35 + 0.8 * 0.25
        self.assertAlmostEqual(rank["composite_score"], expected, places=3)
        self.assertEqual(rank["contributes_to_exposure"], False)
        self.assertEqual(rank["tier"], "broadening")

    def test_a_theme_with_no_ranking_legs_resolved_returns_none(self):
        payload = self.base_payload(count=0, eligible_count=0, mean_confidence_eligible=None,
                                     trend={"direction": {}, "verdict": {"label": "unmeasured"},
                                           "breadth": {}})
        self.assertIsNone(tg.structural_rank(payload))

    def test_a_missing_leg_renormalizes_rather_than_zeroing_the_composite(self):
        # No price history resolved (excess_return leg absent) but evidence and breadth did -
        # the composite should rest entirely on those two, not silently drop by 35%.
        payload = self.base_payload(trend={"direction": {"relative_strength_median": None},
                                           "verdict": {"label": "unmeasured"}, "breadth": {}})
        rank = tg.structural_rank(payload)
        expected = (0.9 * 0.40 + 0.8 * 0.25) / (0.40 + 0.25)
        self.assertAlmostEqual(rank["composite_score"], expected, places=3)
        self.assertEqual(rank["tier"], "unmeasured")

    def test_thin_evidence_can_still_lose_to_strong_evidence_regardless_of_tier(self):
        # The "honesty rule": a mixed/unmeasured theme with strong evidence should be able to
        # outrank a broadening theme with thin evidence, since tier is a display label only.
        broadening_thin = tg.structural_rank(self.base_payload(
            mean_confidence_eligible=0.2,
            trend={"direction": {"relative_strength_median": 5.0}, "verdict": {"label": "broadening"},
                  "breadth": {"outperforming_share": 0.5}}))
        mixed_strong = tg.structural_rank(self.base_payload(
            mean_confidence_eligible=0.98, eligible_count=10, count=10,
            trend={"direction": {"relative_strength_median": 0.0}, "verdict": {"label": "mixed"},
                  "breadth": {"outperforming_share": 0.5}}))
        self.assertGreater(mixed_strong["composite_score"], broadening_thin["composite_score"])


class TailPickTests(unittest.TestCase):
    def make_payload(self, theme_id, rows):
        return {"id": theme_id, "rows": rows}

    def test_a_zero_connectivity_candidate_is_tier_one(self):
        payload = self.make_payload("t", [{"ticker": "A", "eligible": True, "opportunity_score": 90}])
        connectivity_by_ticker = {"A": {"edges": [], "connectivity_score": 0,
                                        "cleared_theme_count": 1, "effective_theme_count": 1}}
        pick = tg.tail_pick(payload, connectivity_by_ticker, {})
        self.assertEqual(pick["tier"], 1)
        self.assertEqual(pick["ticker"], "A")
        self.assertIsNone(pick["caveat"])

    def test_falls_back_to_the_least_connected_candidate_with_a_caveat(self):
        payload = self.make_payload("t", [
            {"ticker": "A", "eligible": True, "opportunity_score": 90},
            {"ticker": "B", "eligible": True, "opportunity_score": 80},
        ])
        edges_a = [{"theme_a": "t", "theme_b": "other", "edge_type": "shared_root_driver", "weight": 3.0}]
        edges_b = [{"theme_a": "t", "theme_b": "other2", "edge_type": "coincidental_sector", "weight": 0.5}]
        connectivity_by_ticker = {
            "A": {"edges": edges_a, "connectivity_score": 3.0, "cleared_theme_count": 2, "effective_theme_count": 2},
            "B": {"edges": edges_b, "connectivity_score": 0.5, "cleared_theme_count": 2, "effective_theme_count": 2},
        }
        theme_lookup = {"other": {"display_name": "Other Theme"}, "other2": {"display_name": "Other2"}}
        pick = tg.tail_pick(payload, connectivity_by_ticker, theme_lookup)
        self.assertEqual(pick["tier"], 2)
        self.assertEqual(pick["ticker"], "B")
        self.assertIn("Other2", pick["caveat"])
        self.assertIn("coincidental sector", pick["caveat"])

    def test_no_eligible_candidate_is_tier_four_with_a_reason(self):
        payload = self.make_payload("t", [{"ticker": "A", "eligible": False, "opportunity_score": 90}])
        pick = tg.tail_pick(payload, {}, {})
        self.assertEqual(pick["tier"], 4)
        self.assertIsNone(pick["ticker"])
        self.assertTrue(pick["reason"])

    def test_walks_candidates_in_opportunity_score_order(self):
        # Both candidates are equally connected, so the higher-ranked one by opportunity score
        # should be the one considered first (and here, picked, since it clears zero-connectivity).
        payload = self.make_payload("t", [
            {"ticker": "LOW", "eligible": True, "opportunity_score": 40},
            {"ticker": "HIGH", "eligible": True, "opportunity_score": 99},
        ])
        connectivity_by_ticker = {
            "LOW": {"edges": [], "connectivity_score": 0, "cleared_theme_count": 1, "effective_theme_count": 1},
            "HIGH": {"edges": [], "connectivity_score": 0, "cleared_theme_count": 1, "effective_theme_count": 1},
        }
        pick = tg.tail_pick(payload, connectivity_by_ticker, {})
        self.assertEqual(pick["ticker"], "HIGH")


class ConnectivityLeadersTests(unittest.TestCase):
    def test_ranks_by_connectivity_score_descending(self):
        payload = {"rows": [
            {"ticker": "A", "eligible": True, "theme_exposure_score": 50, "role": "root"},
            {"ticker": "B", "eligible": True, "theme_exposure_score": 90, "role": "supplier"},
        ]}
        connectivity_by_ticker = {
            "A": {"connectivity_score": 9.0, "effective_theme_count": 2, "cleared_theme_count": 3},
            "B": {"connectivity_score": 3.0, "effective_theme_count": 2, "cleared_theme_count": 2},
        }
        leaders = tg.connectivity_leaders(payload, connectivity_by_ticker)
        self.assertEqual([leader["ticker"] for leader in leaders], ["A", "B"])

    def test_ineligible_rows_are_excluded(self):
        payload = {"rows": [{"ticker": "A", "eligible": False, "theme_exposure_score": 99, "role": "root"}]}
        connectivity_by_ticker = {"A": {"connectivity_score": 9.0, "effective_theme_count": 1, "cleared_theme_count": 1}}
        self.assertEqual(tg.connectivity_leaders(payload, connectivity_by_ticker), [])


class BuildConnectivityIntegrationTests(unittest.TestCase):
    def test_the_shipped_theme_set_produces_a_well_formed_connectivity_block(self):
        # A stub provider that resolves every declared signal generously, so every shipped
        # theme's guardrails and structure get exercised end to end - a real integration check
        # over all 20 shipped theme YAMLs, not just a synthetic fixture.
        loaded = themes.load_themes()
        self.assertGreaterEqual(len(loaded), 20)

        def provider(ticker, theme_def):
            values = {}
            for signal in theme_def["signals"]:
                if signal["name"] == "segment_revenue_share":
                    values[signal["name"]] = 0.4
                else:
                    values[signal["name"]] = 0.3
            return values

        rows = []
        for theme_def in loaded:
            for ticker in theme_def.get("seed_tickers") or []:
                rows.append({"ticker": ticker, "name": ticker,
                             "sector": (theme_def.get("sectors") or [None])[0],
                             "industry": None, "components": {"fundamentals": 70},
                             "valuation_expensiveness_percentile": 40})
        screen = themes.build_theme_screen(loaded, rows, provider)
        connectivity = tg.build_connectivity(screen["themes"], screen["by_ticker"])

        self.assertEqual(set(connectivity["per_theme"].keys()), {t["id"] for t in loaded})
        self.assertEqual(set(connectivity["ranked_themes"]), {t["id"] for t in loaded})
        for theme_id, entry in connectivity["per_theme"].items():
            with self.subTest(theme=theme_id):
                self.assertIn("tail_pick", entry)
                self.assertIn(entry["tail_pick"]["tier"], (1, 2, 4))
                if entry["tail_pick"]["tier"] != 1:
                    # Stage 3 discipline: never a clean pick unless it actually is one.
                    if entry["tail_pick"]["tier"] == 2:
                        self.assertTrue(entry["tail_pick"]["caveat"])
        # A ticker seeded into several electrification-driver themes (e.g. Eaton-style names)
        # should show a collapsed, honest effective_theme_count lower than its raw clearance.
        for ticker, conn in connectivity["by_ticker"].items():
            with self.subTest(ticker=ticker):
                self.assertLessEqual(conn["effective_theme_count"], conn["cleared_theme_count"])


if __name__ == "__main__":
    unittest.main()
