import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import theme_trend as tt
import themes


def member(ticker, *, relative_strength=None, acceleration=None, closes=None, role=None,
           market_cap=None, expensiveness=None, revision_breadth=None, eps_revision=None,
           volume_ratio=None, exposure=None):
    return {
        "ticker": ticker,
        "name": f"{ticker} Inc",
        "role": role,
        "market_cap": market_cap,
        "theme_exposure_score": exposure,
        "history": {"closes": closes} if closes else {},
        "technical_detail": {"relative_strength": relative_strength,
                             "relative_acceleration": acceleration,
                             "volume_ratio_60d": volume_ratio},
        "revision_breadth_30d": revision_breadth,
        "eps_revision_30d_pct": eps_revision,
        "valuation_expensiveness_percentile": expensiveness,
    }


def rising(length=60, start=100.0, step=1.0):
    return [start + step * index for index in range(length)]


def falling(length=60, start=160.0, step=1.0):
    return [start - step * index for index in range(length)]


def alternating(length=70, start=100.0, amplitude=0.02, invert=False):
    """A price path whose daily returns alternate sign -- used to build two groups whose
    return *sequences* are genuine opposites (not just trending in opposite price directions,
    which linear rising()/falling() series do not actually produce: their returns both trend
    downward over time and so end up positively, not negatively, correlated)."""
    sign = -1 if invert else 1
    prices = [start]
    for step in range(length - 1):
        direction = sign if step % 2 == 0 else -sign
        prices.append(prices[-1] * (1 + direction * amplitude))
    return prices


class MovingAverageTests(unittest.TestCase):
    def test_a_rising_series_sits_above_its_own_average(self):
        self.assertTrue(tt.above_moving_average(rising(), 50))

    def test_a_falling_series_sits_below_it(self):
        self.assertFalse(tt.above_moving_average(falling(), 50))

    def test_too_short_a_series_is_unanswered_rather_than_guessed(self):
        # A 50-day average of 30 closes is a different statistic wearing the same name.
        self.assertIsNone(tt.above_moving_average(rising(30), 50))
        self.assertIsNone(tt.above_moving_average([], 20))


class DirectionAndBreadthTests(unittest.TestCase):
    def test_a_group_beating_the_market_and_speeding_up_reads_as_strengthening(self):
        rows = [member(f"T{index}", relative_strength=6, acceleration=2, closes=rising())
                for index in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["direction"]["label"], "strengthening")
        self.assertEqual(result["breadth"]["label"], "broad")
        self.assertEqual(result["breadth"]["above_50d_share"], 1.0)

    def test_a_lagging_group_reads_as_cooling_however_cheap_it_is(self):
        rows = [member(f"T{index}", relative_strength=-8, acceleration=-3, closes=falling(),
                       expensiveness=10) for index in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["direction"]["label"], "weakening")
        self.assertEqual(result["verdict"]["label"], "cooling")

    def test_one_name_up_in_a_lagging_group_is_cooling_not_a_theme(self):
        rows = [member("A", relative_strength=40, acceleration=5, closes=rising(),
                       market_cap=2e12)]
        rows += [member(f"T{index}", relative_strength=-2, acceleration=-1, closes=falling(),
                        market_cap=1e10) for index in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["breadth"]["label"], "narrow")
        self.assertEqual(result["verdict"]["label"], "cooling")
        # The group is lagging *and* the one name that is not is named, so the reader can see
        # it is a company story rather than a trend.
        self.assertTrue(result["leadership"]["led_by_one_name"])

    def test_an_advance_most_members_do_not_share_is_narrow_leadership(self):
        # Median positive, participation below the broad threshold: the group is up, but the
        # advance belongs to a minority of it.
        rows = [member(f"UP{index}", relative_strength=7, acceleration=2, closes=rising(),
                       market_cap=1e10) for index in range(4)]
        rows += [member(f"DN{index}", relative_strength=-3, acceleration=-1, closes=falling(),
                        market_cap=1e10) for index in range(3)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["direction"]["label"], "strengthening")
        self.assertEqual(result["breadth"]["label"], "mixed")
        self.assertEqual(result["verdict"]["label"], "narrow leadership")

    def test_a_group_too_small_to_be_a_group_returns_no_verdict(self):
        rows = [member(f"T{index}", relative_strength=5) for index in range(3)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["verdict"]["label"], "unmeasured")
        self.assertEqual(result["members_measured"], 3)
        self.assertNotIn("direction", result)


class CrowdingTests(unittest.TestCase):
    def test_a_strong_but_expensive_theme_is_never_reported_as_a_clean_signal(self):
        # The single combination this screen exists to warn about: a real trend that has
        # already been paid for. It must not be reported as "broadening".
        rows = [member(f"T{index}", relative_strength=9, acceleration=3, closes=rising(),
                       expensiveness=85) for index in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertTrue(result["crowding"]["already_priced"])
        self.assertEqual(result["verdict"]["label"], "strong but already priced")

    def test_the_same_strength_at_an_ordinary_valuation_is_broadening(self):
        rows = [member(f"T{index}", relative_strength=9, acceleration=3, closes=rising(),
                       expensiveness=40) for index in range(6)]
        self.assertEqual(tt.evaluate_theme(rows)["verdict"]["label"], "broadening")

    def test_crowding_is_unanswered_when_no_member_resolved_a_valuation(self):
        rows = [member(f"T{index}", relative_strength=9, closes=rising()) for index in range(6)]
        self.assertIsNone(tt.evaluate_theme(rows)["crowding"]["already_priced"])


class MaturityTests(unittest.TestCase):
    """Return dispersion and pairwise correlation: the crowding signal that fires even when a
    theme is not (yet) expensive -- everything trading together regardless of valuation."""

    def test_identical_price_series_read_as_fully_crowded(self):
        readings = [tt.member_reading(member(f"T{i}", relative_strength=5.0, closes=rising(70)))
                   for i in range(6)]
        result = tt.maturity_reading(readings)
        self.assertEqual(result["label"], "crowded")
        self.assertAlmostEqual(result["average_pairwise_correlation"], 1.0, places=2)
        self.assertEqual(result["return_dispersion"], 0.0)

    def test_offsetting_price_series_read_as_differentiated(self):
        readings = [tt.member_reading(member(f"UP{i}", relative_strength=5.0 + i,
                                             closes=alternating(70, invert=False)))
                   for i in range(3)]
        readings += [tt.member_reading(member(f"DN{i}", relative_strength=-5.0 - i,
                                              closes=alternating(70, invert=True)))
                    for i in range(3)]
        result = tt.maturity_reading(readings)
        self.assertLess(result["average_pairwise_correlation"], 0)
        self.assertEqual(result["label"], "differentiated")
        self.assertGreater(result["return_dispersion"], 0)

    def test_too_few_members_is_unmeasured(self):
        readings = [tt.member_reading(member(f"T{i}", relative_strength=5.0, closes=rising(70)))
                   for i in range(3)]
        result = tt.maturity_reading(readings)
        self.assertEqual(result["label"], "unmeasured")
        self.assertIsNone(result["average_pairwise_correlation"])

    def test_short_price_history_leaves_correlation_unmeasured_not_guessed(self):
        readings = [tt.member_reading(member(f"T{i}", relative_strength=5.0, closes=rising(10)))
                   for i in range(6)]
        result = tt.maturity_reading(readings)
        self.assertIsNone(result["average_pairwise_correlation"])

    def test_maturity_is_attached_to_the_published_trend_block(self):
        rows = [member(f"T{i}", relative_strength=5.0 + i, acceleration=0.5, closes=rising(70),
                       market_cap=1e9) for i in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertIn("maturity", result)
        self.assertIn(result["maturity"]["label"],
                      ("crowded", "broadening", "differentiated", "unmeasured"))

    def test_maturity_never_leaks_a_raw_price_series_into_the_published_block(self):
        # member_reading carries "closes" for this module's own internal use; it must never
        # surface in what evaluate_theme actually publishes.
        rows = [member(f"T{i}", relative_strength=5.0 + i, closes=rising(70), market_cap=1e9)
               for i in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertNotIn("closes", result["maturity"])
        self.assertNotIn("closes", result.get("leadership", {}))


class LeadershipTests(unittest.TestCase):
    def test_one_mega_cap_carrying_a_flat_group_is_flagged(self):
        rows = [member("MEGA", relative_strength=30, market_cap=3e12, closes=rising())]
        rows += [member(f"T{index}", relative_strength=-1, market_cap=1e10, closes=falling())
                 for index in range(6)]
        result = tt.evaluate_theme(rows)
        self.assertEqual(result["leadership"]["largest"], "MEGA")
        self.assertTrue(result["leadership"]["led_by_one_name"])

    def test_a_group_moving_together_is_not_flagged_as_one_name(self):
        rows = [member("MEGA", relative_strength=12, market_cap=3e12, closes=rising())]
        rows += [member(f"T{index}", relative_strength=9, market_cap=1e10, closes=rising())
                 for index in range(6)]
        self.assertFalse(tt.evaluate_theme(rows)["leadership"]["led_by_one_name"])


class RoleRotationTests(unittest.TestCase):
    def _chain(self, root_strength, supplier_strength):
        rows = [member(f"R{index}", relative_strength=root_strength, role="root",
                       market_cap=1e11, closes=rising()) for index in range(3)]
        rows += [member(f"S{index}", relative_strength=supplier_strength, role="supplier",
                        market_cap=1e10, closes=rising()) for index in range(4)]
        return tt.evaluate_theme(rows)

    def test_roles_are_ranked_so_a_rotation_is_visible(self):
        result = self._chain(root_strength=2, supplier_strength=11)
        self.assertEqual([row["role"] for row in result["roles"]], ["supplier", "root"])
        self.assertEqual(result["roles"][0]["relative_strength_median"], 11)

    def test_a_chain_whose_suppliers_participate_confirms_the_headline(self):
        confirmation = self._chain(root_strength=8, supplier_strength=5)["chain_confirmation"]
        self.assertTrue(confirmation["confirms"])

    def test_a_headline_the_supply_chain_does_not_follow_is_not_confirmed(self):
        # A defense thesis carried entirely by the primes is a company story, not a chain.
        confirmation = self._chain(root_strength=15, supplier_strength=-4)["chain_confirmation"]
        self.assertFalse(confirmation["confirms"])

    def test_confirmation_is_unanswered_when_a_theme_declares_no_roles(self):
        rows = [member(f"T{index}", relative_strength=5, closes=rising()) for index in range(6)]
        self.assertIsNone(tt.evaluate_theme(rows)["chain_confirmation"]["confirms"])


class BiggestPlayersTests(unittest.TestCase):
    def test_the_largest_members_are_listed_with_their_exposure_and_role(self):
        rows = [member("SMALL", market_cap=1e9, exposure=95, role="supplier"),
                member("HUGE", market_cap=3e12, exposure=60, role="root"),
                member("MID", market_cap=5e10, exposure=80, role="supplier")]
        players = tt.biggest_players(rows)
        self.assertEqual([row["ticker"] for row in players], ["HUGE", "MID", "SMALL"])
        # Size ordering, deliberately not exposure ordering: the names most identified with a
        # trend are frequently not the ones the exposure leaderboard ranks first.
        self.assertEqual(players[0]["theme_exposure_score"], 60)
        self.assertEqual(players[0]["role"], "root")

    def test_a_member_without_a_market_cap_is_omitted_rather_than_ranked_last(self):
        players = tt.biggest_players([member("NOCAP"), member("HUGE", market_cap=1e12)])
        self.assertEqual([row["ticker"] for row in players], ["HUGE"])


class SeparationFromExposureTests(unittest.TestCase):
    """The trend layer reads price. Nothing it produces may reach an exposure score."""

    def test_the_published_block_declares_that_it_does_not_feed_exposure(self):
        rows = [member(f"T{index}", relative_strength=5, closes=rising()) for index in range(6)]
        self.assertFalse(tt.evaluate_theme(rows)["contributes_to_exposure"])

    def test_price_behavior_cannot_change_a_companys_exposure_score(self):
        theme = themes.normalize_theme({
            "id": "t", "signals": [
                {"name": "segment_revenue_share", "weight": 0.5},
                {"name": "filing_keyword_density_trend", "weight": 0.5}]})
        signals = {"segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.3}
        flat = [{"ticker": "AAA", "components": {"fundamentals": 70},
                 "technical_detail": {"relative_strength": -20}, "history": {"closes": falling()}}]
        hot = [{"ticker": "AAA", "components": {"fundamentals": 70},
                "technical_detail": {"relative_strength": 60}, "history": {"closes": rising()}}]
        cold_screen = themes.build_theme_screen([theme], flat, lambda t, th: signals)
        hot_screen = themes.build_theme_screen([theme], hot, lambda t, th: signals)
        self.assertEqual(cold_screen["themes"][0]["rows"][0]["theme_exposure_score"],
                         hot_screen["themes"][0]["rows"][0]["theme_exposure_score"])

    def test_an_exposure_row_never_carries_price_behavior(self):
        theme = themes.normalize_theme({
            "id": "t", "signals": [
                {"name": "segment_revenue_share", "weight": 0.5},
                {"name": "filing_keyword_density_trend", "weight": 0.5}]})
        rows = [{"ticker": "AAA", "components": {"fundamentals": 70},
                 "technical_detail": {"relative_strength": 60}, "history": {"closes": rising()}}]
        screen = themes.build_theme_screen(
            [theme], rows,
            lambda t, th: {"segment_revenue_share": 0.4, "filing_keyword_density_trend": 0.3})
        published = screen["themes"][0]["rows"][0]
        for field in ("technical_detail", "history", "relative_strength"):
            self.assertNotIn(field, published)


class RoleAssignmentTests(unittest.TestCase):
    def _theme(self):
        return themes.normalize_theme({
            "id": "t",
            "signals": [{"name": "filing_keyword_density_trend", "weight": 1}],
            "roles": {
                "root": {"industries": ["utilities - regulated electric"]},
                "supplier": {"industries": ["electrical equipment"], "tickers": ["ODDONE"]},
            },
        })

    def test_a_company_is_placed_by_its_industry(self):
        theme = self._theme()
        self.assertEqual(themes.assign_role(
            theme, {"ticker": "X", "industry": "Utilities - Regulated Electric"}), "root")
        self.assertEqual(themes.assign_role(
            theme, {"ticker": "Y", "industry": "Electrical Equipment & Parts"}), "supplier")

    def test_a_named_ticker_overrides_its_classification(self):
        # Naming one is only ever done because its classification does not capture what it
        # does in this chain.
        self.assertEqual(themes.assign_role(
            self._theme(), {"ticker": "ODDONE", "industry": "Utilities - Regulated Electric"}),
            "supplier")

    def test_an_unplaceable_company_has_no_role_rather_than_a_default_one(self):
        self.assertIsNone(themes.assign_role(
            self._theme(), {"ticker": "Z", "industry": "Trucking"}))
        self.assertIsNone(themes.assign_role(self._theme(), {"ticker": "Z"}))


if __name__ == "__main__":
    unittest.main()
