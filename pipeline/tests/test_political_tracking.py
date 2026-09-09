import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import political_tracking as module

# The real curated tables are hand-maintained and will keep growing, so every test below
# runs against a fixed fake config instead - a test that breaks the moment somebody adds a
# committee assignment is testing the config, not the code.
CONFIG = {
    "name_aliases": {
        "ro khanna": ["rohit khanna"],
        "gil cisneros": ["gilbert cisneros", "gilbert ray cisneros jr"],
    },
    "tracked_filers": {
        "ro khanna": {"tiers": ["activity", "jurisdiction"], "display_name": "Ro Khanna"},
        "gil cisneros": {"tiers": ["activity"], "display_name": "Gil Cisneros"},
    },
    "external_reference": {
        "_source": {"publisher": "Fake Source", "as_of": "2025-12-29"},
        "politicians": {
            "ro khanna": {"display_name": "Ro Khanna", "return_2025_pct": 12.6,
                          "trades_2025": 4284, "party": "D", "seat": "CA-17"},
        },
    },
    "unusual_timing": {
        "top_n": 5, "max_per_filer": 2, "size_reference": 100_000.0,
        "excess_return_reference": 20.0, "filing_delay_reference": 90,
        "news_lookahead_days": 14, "minimum_components": 2,
        "weights": {"size": 1.0, "committee_overlap": 2.0, "excess_return": 2.0,
                    "filing_delay": 1.0, "news_proximity": 1.0},
    },
}

# committees.json's own spelling of Cisneros deliberately differs from the roster's, so the
# canonicalization seam is exercised rather than assumed.
COMMITTEES = {
    "politicians": {
        "ro khanna": {"committees": ["Armed Services"], "sectors": ["semiconductors"],
                      "market_sectors": ["Technology"]},
        "gilbert cisneros": {"committees": ["Veterans Affairs"], "sectors": [],
                             "market_sectors": ["Healthcare"]},
    }
}

POLICY_MAP = {"sectors": {"semiconductors": {"tickers": ["NVDA", "MU"]}}}
LIVE_NEWS = {"data_mode": "live", "items": [
    {"published": "2026-03-10", "flags": [{"sector": "semiconductors", "tickers": ["NVDA"]}]}]}
DEMO_NEWS = {"data_mode": "demo", "items": [
    {"published": "2026-03-10", "flags": [{"sector": "semiconductors", "tickers": ["NVDA"]}]}]}


@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    payloads = {"political_tracking.json": CONFIG, "committees.json": COMMITTEES,
                "policy_map.json": POLICY_MAP, "news.json": DEMO_NEWS}

    def load_json(name, from_config=False):
        return json.loads(json.dumps(payloads.get(name)))

    monkeypatch.setattr(module, "load_json", load_json)
    module.reset_caches()
    yield payloads
    module.reset_caches()


def trade(representative="Rohit Khanna", **overrides):
    row = {"representative": representative, "symbol": "NVDA", "transaction_type": "Purchase",
           "transaction_date": "2026-03-01", "disclosure_date": "2026-03-20",
           "amount_lower": 50_000.0, "amount_upper": 100_000.0, "filing_delay_days": 19,
           "flags": []}
    row.update(overrides)
    return row


class TestCanonicalName:
    def test_alias_resolves_a_disclosed_spelling_to_one_key(self):
        assert module.canonical_name("Rohit Khanna") == "ro khanna"

    def test_punctuation_and_generational_suffixes_are_not_identity(self):
        assert module.canonical_name("Gilbert Ray Cisneros Jr.") == "gil cisneros"

    def test_middle_initial_is_dropped_when_it_lands_on_a_curated_person(self):
        assert module.canonical_name("Ro T. Khanna") == "ro khanna"

    def test_an_uncurated_filer_keeps_their_whole_name(self):
        # The first+last shortcut must never merge two strangers who happen to share a
        # first and last name with each other - it only ever resolves onto a curated key.
        assert module.canonical_name('Charles J. "Chuck" Fleischmann') == "charles j chuck fleischmann"

    def test_blank_names_resolve_to_nothing_rather_than_a_shared_bucket(self):
        assert module.canonical_name(None) == ""


class TestCuratedLookups:
    def test_committees_and_roster_unify_despite_disagreeing_on_the_spelling(self):
        # committees.json says "gilbert cisneros", the roster says "gil cisneros".
        profile = module.committee_profile("Gilbert Ray Cisneros Jr.")
        assert profile["committees"] == ["Veterans Affairs"]
        assert module.tracked_profile("Gilbert Cisneros")["tiers"] == ["activity"]

    def test_an_uncurated_filer_has_no_profile_rather_than_an_empty_one(self):
        assert module.committee_profile("Jane Doe") is None
        assert module.tracked_profile("Jane Doe") is None
        assert module.external_profile("Jane Doe") is None

    def test_coverage_counts_report_how_much_curation_actually_exists(self):
        assert module.tracked_coverage() == {
            "tracked_filers": 2, "committee_profiles": 2, "external_reference_politicians": 1}


class TestCommitteeOverlap:
    def test_research_sector_match_reports_the_evidence_not_a_verdict(self):
        overlap = module.committee_overlap(trade(), sector_lookup={"NVDA": "Technology"})
        assert overlap == {"committees": ["Armed Services"], "sector": "Technology",
                           "basis": "market_sector"}

    def test_policy_map_tickers_are_the_fallback_vocabulary(self):
        overlap = module.committee_overlap(
            trade(), sector_lookup={}, policy_lookup=module.policy_sector_by_ticker())
        assert overlap["basis"] == "policy_sector"
        assert overlap["sector"] == "semiconductors"

    def test_a_sector_the_committee_does_not_oversee_is_not_an_overlap(self):
        assert module.committee_overlap(trade(), sector_lookup={"NVDA": "Utilities"}) is None

    def test_an_uncurated_filer_never_produces_an_overlap(self):
        # Absence must read as "not curated", never as a finding about the filer.
        assert module.committee_overlap(
            trade("Jane Doe"), sector_lookup={"NVDA": "Technology"}) is None

    def test_a_row_without_a_ticker_has_nothing_to_check(self):
        assert module.committee_overlap(
            trade(symbol=None), sector_lookup={"NVDA": "Technology"}) is None


class TestNewsProximity:
    def test_demo_feed_switches_the_component_off_entirely(self, fake_config):
        # Scoring "traded ahead of the news" against placeholder headlines would
        # manufacture the exact finding this screen refuses to manufacture.
        index, live = module.news_proximity_index()
        assert (index, live) == ({}, False)

    def test_live_feed_indexes_headline_dates_by_ticker(self, fake_config, monkeypatch):
        fake_config["news.json"] = LIVE_NEWS
        module.reset_caches()
        index, live = module.news_proximity_index()
        assert live and str(index["NVDA"][0]) == "2026-03-10"

    def test_only_a_headline_that_broke_after_the_trade_counts(self, fake_config):
        fake_config["news.json"] = LIVE_NEWS
        module.reset_caches()
        index, _ = module.news_proximity_index()
        assert module.preceded_news(trade(transaction_date="2026-03-01"), index, lookahead_days=14)
        # Trading after the headline is just reading the news like anybody else.
        assert not module.preceded_news(
            trade(transaction_date="2026-03-20"), index, lookahead_days=14)


class TestActivityProfiles:
    def test_one_persons_spellings_are_counted_once(self):
        rows = [trade("Rohit Khanna"), trade("Ro Khanna"), trade("Ro Khanna", symbol="MU")]
        profile = module.activity_profiles(rows)[0]
        assert profile["trades"] == 3
        assert profile["distinct_symbols"] == 2
        assert profile["name_variants"] == ["Ro Khanna", "Rohit Khanna"]
        # Displayed under whichever spelling the feeds used most.
        assert profile["politician"] == "Ro Khanna"

    def test_volume_uses_the_midpoint_because_the_forms_report_bands(self):
        profile = module.activity_profiles([trade()])[0]
        assert profile["disclosed_volume_midpoint"] == 75_000.0

    def test_late_filings_are_counted_against_the_stock_act_threshold(self):
        rows = [trade(filing_delay_days=10), trade(filing_delay_days=60)]
        profile = module.activity_profiles(rows, late_filing_days=45)[0]
        assert profile["late_filings"] == 1
        assert profile["late_filing_rate"] == 0.5
        assert profile["avg_filing_delay_days"] == 35.0

    def test_ranking_is_by_activity_not_by_performance(self):
        rows = [trade("Rohit Khanna"), trade("Rohit Khanna"), trade("Gil Cisneros")]
        ranked = module.activity_profiles(rows)
        assert [row["politician"] for row in ranked] == ["Rohit Khanna", "Gil Cisneros"]
        assert [row["rank"] for row in ranked] == [1, 2]

    def test_performance_is_attached_under_any_spelling_the_feed_used(self):
        performance = {"politicians": {"Rohit Khanna": {
            "avg_alpha_pct": 4.0, "win_rate": 0.6, "n_priced_buys": 12, "confidence": "high"}}}
        profile = module.activity_profiles([trade("Rohit Khanna")], performance=performance)[0]
        assert profile["performance"]["n_priced_buys"] == 12

    def test_external_figures_ride_along_without_being_mixed_in(self):
        profile = module.activity_profiles([trade()])[0]
        assert profile["external"]["return_2025_pct"] == 12.6
        assert "return_2025_pct" not in profile

    def test_committee_overlap_trades_are_tallied_from_the_flag(self):
        rows = [trade(flags=["COMMITTEE_OVERLAP"]), trade(flags=[])]
        assert module.activity_profiles(rows)[0]["committee_overlap_trades"] == 1

    def test_rows_without_a_filer_are_dropped_not_bucketed_together(self):
        assert module.activity_profiles([trade(representative=None)]) == []


class TestUnusualTiming:
    def test_missing_evidence_lowers_the_score_rather_than_being_excused(self):
        """A row measurable on two saturated axes must not outrank one that is unusual on
        four - the bug that averaging over available components alone would introduce."""
        thin = trade("Jane Doe", amount_lower=1_000_000.0, filing_delay_days=400)
        rich = trade(amount_lower=1_000_000.0, filing_delay_days=400,
                     flags=["COMMITTEE_OVERLAP"], excess_return_vs_spy_pct=50.0)
        ranked = module.unusual_timing([thin, rich])["results"]
        assert ranked[0]["representative"] == "Rohit Khanna"
        assert ranked[0]["unusual_score"] > ranked[1]["unusual_score"]
        # Nothing can reach 1.0 while a component is unmeasurable for that row.
        assert ranked[1]["unusual_score"] < 1.0

    def test_a_component_switched_off_run_wide_leaves_the_denominator(self):
        # News is in demo mode here, so it must not drag every row's score down uniformly.
        row = trade(amount_lower=100_000.0, filing_delay_days=90,
                    flags=["COMMITTEE_OVERLAP"], excess_return_vs_spy_pct=20.0)
        result = module.unusual_timing([row])
        assert result["news_component_active"] is False
        assert result["results"][0]["unusual_score"] == 1.0

    def test_unmeasurable_components_are_reported_apart_from_measured_zeroes(self):
        row = module.unusual_timing([trade(filing_delay_days=400)])["results"][0]
        assert "excess_return" in row["components_unavailable"]
        assert row["components"]["committee_overlap"] == 0.0

    def test_rows_with_too_little_evidence_are_dropped_not_ranked(self):
        thin = {"representative": "Jane Doe", "symbol": "NVDA", "amount_lower": 100_000.0,
                "flags": []}
        assert module.unusual_timing([thin], config={"minimum_components": 3})["results"] == []

    def test_non_equity_rows_have_no_ticker_to_check(self):
        assert module.unusual_timing([trade(symbol=None, filing_delay_days=400)])["results"] == []

    def test_one_filers_bulk_disclosure_cannot_crowd_out_the_panel(self):
        bulk = [trade(filing_delay_days=400, amount_lower=1_000_000.0) for _ in range(5)]
        other = trade("Gil Cisneros", filing_delay_days=400, amount_lower=1_000_000.0)
        results = module.unusual_timing([*bulk, other])["results"]
        assert sum(1 for row in results if row["representative"] == "Rohit Khanna") == 2
        assert any(row["representative"] == "Gil Cisneros" for row in results)

    def test_candidates_counts_everything_that_qualified_before_the_cut(self):
        rows = [trade(filing_delay_days=400) for _ in range(8)]
        assert module.unusual_timing(rows)["candidates"] == 8


class TestExternalReference:
    def test_external_columns_are_named_apart_from_pipeline_computed_ones(self):
        leaderboard = [{"politician": "Rohit Khanna", "avg_alpha_pct": 3.1, "rank": 1}]
        merged = module.merge_external_into_leaderboard(leaderboard)[0]
        assert merged["avg_alpha_pct"] == 3.1          # untouched
        assert merged["external_return_2025_pct"] == 12.6
        assert merged["tracked_tiers"] == ["activity", "jurisdiction"]

    def test_a_filer_with_no_external_figures_gets_no_external_keys_at_all(self):
        merged = module.merge_external_into_leaderboard([{"politician": "Jane Doe"}])[0]
        assert not any(key.startswith("external_") for key in merged)
        assert merged["tracked"] is False
