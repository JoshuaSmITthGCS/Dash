"""Regression tests for the Round 4 remediation (docs/AUDIT-ROUND-4-FINDINGS.md).

Covers the defects the audit measured: directional coverage penalties, missingness
changing rank direction, suppressed metrics leaking into the imputed vector, silent
provider outages, ETF rows reaching the ranked stock path, hysteresis, and experiment
reproducibility.
"""
import copy

import pytest

import data_health
from advisor_engine import build_research, shrink_research_components
from portfolio_construction import rank_buffer_selection
from scorer import CrossSectionalNormalizer, valuation_score
from validation.experiment_manifest import build_manifest, sha256_of_json


def _snapshot(ticker="TEST", sector="Technology", **overrides):
    base = {
        "ticker": ticker, "sector": sector, "is_etf": False,
        "market_cap": 5_000_000_000, "price": 100.0,
        "ev_to_ebitda": 9.0, "ev_to_ebit": 11.0, "ev_to_fcf": 12.0,
        "forward_pe": 15.0, "peg": 1.4, "ev_to_sales": 3.0, "price_to_sales": 3.2,
        "price_to_book": 3.0, "price_to_tangible_book": 4.0,
        "return_on_invested_capital": 0.18, "gross_profits_to_assets": 0.35,
        "free_cash_flow_yield": 0.05, "cash_conversion": 1.1,
        "return_on_equity": 0.2, "profit_margin": 0.15,
        "interest_coverage": 12.0, "net_debt_to_ebitda": 1.0, "altman_z": 4.0,
        "debt_to_equity": 0.5, "current_ratio": 2.0,
        "revenue_growth": 0.1, "earnings_growth": 0.12, "fcf_growth_3y": 0.08,
        "operating_margin_trend": 0.01, "earnings_surprise": 0.03,
        "net_buyback_yield": 0.02, "stock_comp_to_revenue": 0.05,
        "asset_growth": 0.06, "capex_to_depreciation": 1.1,
        "piotroski_f": 7.0, "accruals_ratio": -0.03,
        "days_sales_outstanding_trend": -0.01, "inventory_days_trend": -0.02,
    }
    base.update(overrides)
    return base


def _universe(n=40):
    import random
    rng = random.Random(7)
    snaps = []
    for i in range(n):
        jitter = {key: value * (1 + rng.uniform(-0.4, 0.4))
                  for key, value in _snapshot().items()
                  if isinstance(value, (int, float)) and key not in ("market_cap", "price")}
        snaps.append(_snapshot(ticker=f"T{i:03d}", **jitter))
    return snaps


class TestFixedFeatureImputation:
    def test_full_vector_after_imputation(self):
        snaps = _universe()
        nz = CrossSectionalNormalizer(snaps)
        sparse = copy.deepcopy(snaps[0])
        for key in ("ev_to_ebitda", "piotroski_f", "gross_profits_to_assets",
                    "accruals_ratio", "net_buyback_yield"):
            sparse[key] = None
        score, detail = valuation_score(sparse, mode="fixed_feature", normalizer=nz)
        assert score is not None
        fractions = (detail["observed_weight_fraction"] + detail["imputed_weight_fraction"]
                     + detail["suppressed_weight_fraction"])
        assert fractions == pytest.approx(1.0, abs=0.02)
        assert "piotroski_f" in detail["imputed_metrics"]
        assert detail["piotroski_f"] == 50.0

    def test_missingness_moves_toward_neutral_not_down(self):
        """Deleting evidence from a strong name must pull its score toward the center,
        never below a weak name whose evidence all resolved. The production path fails
        this by construction (two completeness multipliers), which is the measured
        +0.51 coverage-score correlation."""
        snaps = _universe()
        nz = CrossSectionalNormalizer(snaps)
        full = copy.deepcopy(snaps[1])
        full_score, full_detail = valuation_score(full, mode="fixed_feature", normalizer=nz)
        sparse = copy.deepcopy(full)
        for key in ("ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "piotroski_f",
                    "gross_profits_to_assets", "return_on_invested_capital"):
            sparse[key] = None
        sparse_score, sparse_detail = valuation_score(sparse, mode="fixed_feature",
                                                      normalizer=nz)
        lo, hi = sorted((full_score, 50.0))
        assert lo - 1e-6 <= sparse_score <= hi + 1e-6
        assert sparse_detail["coverage"] < full_detail["coverage"]

    def test_suppressed_metrics_never_imputed(self):
        snaps = _universe()
        nz = CrossSectionalNormalizer(snaps)
        negative_ebitda = copy.deepcopy(snaps[2])
        negative_ebitda["ev_to_ebitda"] = -5.0
        _score, detail = valuation_score(negative_ebitda, mode="fixed_feature",
                                         normalizer=nz)
        assert "ev_to_ebitda" in detail["suppressed_metrics"]
        assert "ev_to_ebitda" not in detail["imputed_metrics"]
        assert detail["normalization"]["ev_to_ebitda"]["status"] == "suppressed_not_applicable"

    def test_no_completeness_multiplier(self):
        """The fixed-feature score equals its category blend. No 0.65 + 0.35 * coverage."""
        snaps = _universe()
        nz = CrossSectionalNormalizer(snaps)
        score, detail = valuation_score(snaps[3], mode="fixed_feature", normalizer=nz)
        assert score == detail["raw_score"]


class TestNeutralShrinkage:
    def test_low_confidence_moves_toward_prior_from_both_sides(self):
        config = {"shrinkage_target": 50.0, "shrinkage_max_pull": 1.0}
        low = shrink_research_components({"fundamentals": 30.0}, {"fundamentals": 0.5},
                                         config, 0.0)
        high = shrink_research_components({"fundamentals": 70.0}, {"fundamentals": 0.5},
                                          config, 0.0)
        assert low["base_score"] > 30.0
        assert high["base_score"] < 70.0
        assert low["base_score"] < 50.0 < high["base_score"]

    def test_production_form_is_directional(self):
        """Documents the defect: the production multiplier pushes a below-neutral name
        further down when confidence falls, the opposite of the Bayesian pull."""
        raw, coverage = 30.0, 0.2
        production = raw * (0.8 + 0.2 * coverage)
        assert production < raw


class TestFundamentalsCategoryMultiplierScope:
    """Corrects an over-broad finding from an earlier pass of this audit
    (docs/AUDIT-VERIFICATION-RESULTS.md Sec6, since corrected there): the earlier finding
    treated _band_valuation_score's confidence_multiplier as still live for the *champion's
    published score*. It is not -- build_research() (advisor_engine.py) reads
    fundamental_parts["raw_score"] (the pre-multiplier value) for the champion's
    components["fundamentals"], never valuation_score()'s multiplied first return value.
    test_champion_published_score_bypasses_the_multiplier below proves that directly, and
    test_advisor_engine.py::TestChampionMultiplier (pre-existing) already covered this from a
    different angle.

    The multiplier is not fully dead, though: valuation_score(snapshot)[0] (the multiplied
    value) is exactly the sort key fetch_advisor.py::enrich() uses to rank which of ~910
    candidate names get financial-statement enrichment -- a name with thin *pre-enrichment*
    fundamentals coverage has its already-computed raw evidence pushed further down in that
    ranking by this multiplier, on top of whatever structural shortlist-gating bias already
    exists (docs/CONSOLIDATED-ASSESSMENT.md Sec2.2, the 0.820/114-rank incident in
    docs/AUDIT-VERIFICATION-RESULTS.md Sec7.3). test_enrichment_priority_sort_key_is_still_directional
    below documents that live effect precisely, at the layer it actually happens (enrich()'s
    sort key), not at the champion's published score.

    Changing enrich()'s sort key to use raw_score instead is a real, live scoring-selection
    change (it would alter which names get enriched, one further mechanism upstream of the
    already-known shortlist bias) and needs the same registered-challenger-then-promotion
    discipline as any other production scoring change -- not a one-line edit here. See
    docs/AUDIT-ROADMAP.md and docs/MODEL-RISK-REGISTER.md Sec1 for the corrected finding and
    what measuring this properly would take.
    """

    def test_champion_published_score_bypasses_the_multiplier(self):
        partial = _snapshot(earnings_surprise=None, net_buyback_yield=None,
                             stock_comp_to_revenue=None, capex_to_depreciation=None,
                             accruals_ratio=None)
        multiplied_score, detail = valuation_score(partial)
        assert detail["coverage"] < 1.0
        assert multiplied_score < detail["raw_score"], (
            "valuation_score()'s own multiplied return value is directional in isolation -- "
            "the point of this test is that the champion never uses it, not that it's absent."
        )
        row = build_research("TEST", partial, [100 + i * 0.2 for i in range(300)],
                             [100 + i * 0.2 for i in range(300)], [])
        assert row["components"]["fundamentals"] == row["fundamental_detail"]["raw_score"], (
            "the champion's fundamentals component must be the pre-multiplier raw score, "
            "exactly as advisor_engine.py's build_research() computes it, regardless of "
            "what valuation_score()'s own multiplied return value says."
        )

    def test_enrichment_priority_sort_key_is_still_directional(self):
        """fetch_advisor.py::enrich() ranks candidates by valuation_score(snapshot)[0] --
        the multiplied value -- to decide who gets scarce statement-enrichment budget. A name
        with strong raw evidence but thin pre-enrichment coverage is pushed down that specific
        ranking by this multiplier, which is the one place in the live pipeline it still
        matters."""
        full = _snapshot()
        partial = _snapshot(earnings_surprise=None, net_buyback_yield=None,
                             stock_comp_to_revenue=None, capex_to_depreciation=None,
                             accruals_ratio=None)
        full_sort_key = valuation_score(full)[0]
        partial_sort_key, partial_detail = valuation_score(partial)
        assert partial_detail["coverage"] < 1.0
        assert partial_sort_key < partial_detail["raw_score"], (
            "enrich()'s sort key for a partial-coverage name is worse than its own raw "
            "evidence, purely from the multiplier -- this can keep a name off the "
            "enrichment shortlist for a reason unrelated to its actual fundamentals."
        )


class TestDataHealth:
    def test_outage_turns_critical(self):
        rows = [{"ev_to_ebitda": None, "piotroski_f": None, "altman_z": None}] * 90 + [
            {"ev_to_ebitda": 9.0, "piotroski_f": 7.0, "altman_z": 3.0}] * 10
        health = data_health.statement_health(rows, {"data_health": {
            "monitored_metrics": ["ev_to_ebitda", "piotroski_f", "altman_z"]}})
        assert health["state"] == "critical"
        assert health["mean_statement_coverage"] == pytest.approx(0.1, abs=0.01)

    def test_healthy_state(self):
        rows = [{"ev_to_ebitda": 9.0, "piotroski_f": 7.0, "altman_z": 3.0}] * 9 + [
            {"ev_to_ebitda": None, "piotroski_f": None, "altman_z": None}]
        health = data_health.statement_health(rows, {"data_health": {
            "monitored_metrics": ["ev_to_ebitda", "piotroski_f", "altman_z"]}})
        assert health["state"] == "healthy"

    def test_publication_gate(self):
        publishable, reason = data_health.publication_gate(0.1, {})
        assert not publishable and "floor" in reason
        publishable, reason = data_health.publication_gate(0.9, {})
        assert publishable and reason is None
        publishable, _reason = data_health.publication_gate(None, {})
        assert not publishable


class TestHysteresis:
    def test_held_between_entry_and_exit(self):
        ranked = [{"ticker": f"T{i:02d}"} for i in range(30)]
        previous = ["T25", "T00"]  # T25 sits between N=10 and 2*N=20? rank 26 -> out
        selected = rank_buffer_selection(previous, ranked, 10, 2.0)
        assert "T00" in selected
        assert "T25" not in selected
        previous = ["T14"]  # rank 15, inside the 2N=20 buffer -> held
        selected = rank_buffer_selection(previous, ranked, 10, 2.0)
        assert "T14" in selected
        assert len(selected) == 10


class TestReproducibility:
    def test_manifest_hash_deterministic(self):
        kwargs = dict(strategy="s", start_date="2021-01-31", end_date="2026-01-31",
                      normalization_mode="bands", scoring_mode="champion",
                      rebalance_frequency="monthly", universe_tickers=["B", "A"],
                      execution_assumptions={"x": 1}, cost_model={"bps": 10})
        first = build_manifest(**kwargs)
        second = build_manifest(**kwargs)
        assert first["manifest_hash"] == second["manifest_hash"]
        assert first["ticker_list_hash"] == second["ticker_list_hash"]

    def test_json_hash_key_order_invariant(self):
        assert sha256_of_json({"a": 1, "b": 2}) == sha256_of_json({"b": 2, "a": 1})
        assert sha256_of_json({"a": 1}) != sha256_of_json({"a": 2})


class TestEtfClassification:
    def test_etf_rows_refused_by_stock_scorer(self):
        snaps = _universe()
        nz = CrossSectionalNormalizer(snaps)
        etf = _snapshot(ticker="VOO")
        etf["is_etf"] = True
        assert valuation_score(etf, mode="bands") == (None, {})
        assert valuation_score(etf, mode="fixed_feature", normalizer=nz) == (None, {})

    def test_market_cap_overrides_glitched_quote_type(self):
        """PINC 2026-08-10: quoteType claimed ETF for an operating company, which
        suppressed every fundamental. A company market cap outvotes the glitch unless
        the ticker is in the configured ETF list."""
        from fetch_prices import fetch_snapshot

        class FakeHistory(list):
            pass

        class FakeTicker:
            info = {"quoteType": "ETF", "marketCap": 4_132_973_056,
                    "currentPrice": 20.0, "shortName": "Premier Inc"}

            def history(self, period):
                return FakeHistory()

        snap = fetch_snapshot("PINC", None, etf_ids=set(), ticker_obj=FakeTicker())
        assert snap["is_etf"] is False
        real_etf = FakeTicker()
        real_etf.info = {"quoteType": "ETF", "currentPrice": 400.0, "shortName": "VOO"}
        snap = fetch_snapshot("VOO", None, etf_ids={"VOO"}, ticker_obj=real_etf)
        assert snap["is_etf"] is True
