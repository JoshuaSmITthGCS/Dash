import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import politician_performance as module

TODAY = date(2026, 8, 9)

# Flat +10% SPY window shared by every trade below, so a trade's alpha is just its raw
# return minus 10 unless a test overrides the window.
BENCHMARK = {"dates": ["2026-01-01", "2026-06-01"], "closes": [400.0, 440.0]}


def priced_buy(representative, return_pct, *, transaction_date="2026-01-01",
              price_as_of="2026-06-01", amount_lower=50_000, disclosure_date=None,
              transaction_type="Purchase", symbol="ACME", chamber="senate",
              asset_type="Stock", amount="$15,001 - $50,000"):
    return {
        "representative": representative, "transaction_type": transaction_type,
        "transaction_date": transaction_date, "price_as_of": price_as_of,
        "disclosure_date": disclosure_date or transaction_date,
        "return_since_purchase_pct": return_pct, "amount_lower": amount_lower,
        "symbol": symbol, "chamber": chamber, "asset_type": asset_type, "amount": amount,
    }


def unpriced_buy(representative, symbol, *, transaction_date="2026-01-01",
                 chamber="senate", asset_type="Stock", amount="$15,001 - $50,000"):
    """An equity buy with no return_since_purchase_pct/price_as_of yet - a backfill
    candidate, not something raw_stats_by_politician can score."""
    return {
        "representative": representative, "transaction_type": "Purchase",
        "transaction_date": transaction_date, "disclosure_date": transaction_date,
        "symbol": symbol, "chamber": chamber, "asset_type": asset_type, "amount": amount,
    }


class TestTradeAlpha:
    def test_alpha_is_return_minus_the_benchmarks_return_over_the_same_window(self):
        row = priced_buy("Rep A", 20.0)
        assert round(module.trade_alpha(row, BENCHMARK), 6) == 10.0

    def test_no_priced_return_yields_no_alpha(self):
        row = priced_buy("Rep A", None)
        assert module.trade_alpha(row, BENCHMARK) is None

    def test_no_benchmark_data_yields_no_alpha(self):
        row = priced_buy("Rep A", 20.0)
        assert module.trade_alpha(row, {"dates": [], "closes": []}) is None


class TestComputePerformanceScores:
    def test_a_brand_new_politician_with_no_priced_buys_is_absent_and_falls_back_to_population(self):
        performance = module.compute_performance_scores([priced_buy("Rep A", 20.0)], benchmark=BENCHMARK)
        stats = module.score_for_politician("Rep Nobody Has Ever Heard Of", performance)
        assert stats["performance_score"] == performance["population"]["performance_score"]
        assert stats["confidence"] == "low"

    def test_an_empty_dataset_yields_a_neutral_population_baseline(self):
        performance = module.compute_performance_scores([], benchmark=BENCHMARK)
        assert performance["population"]["n_priced_buys"] == 0
        assert performance["population"]["win_rate"] == 0.5
        assert performance["population"]["avg_alpha_pct"] == 0.0
        # a neutral prior should sit near the middle of the [0, 1] range, not at an extreme
        assert 0.4 < performance["population"]["performance_score"] < 0.6

    def test_a_negative_alpha_politician_scores_below_a_positive_alpha_politician(self):
        rows = [priced_buy("Winner", 30.0), priced_buy("Winner", 25.0),
                priced_buy("Loser", -10.0), priced_buy("Loser", -15.0)]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        winner = performance["politicians"]["Winner"]
        loser = performance["politicians"]["Loser"]
        assert winner["performance_score"] > loser["performance_score"]
        # still bounded, never driven to the floor by two bad trades alone
        assert loser["performance_score"] > 0.0

    def test_a_single_huge_outlier_trade_is_pulled_toward_the_population_by_shrinkage(self):
        rows = [priced_buy("Steady", 12.0)] * 6 + [priced_buy("Steady", 8.0)] * 6 + [
            priced_buy("OneHitWonder", 500.0)]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        one_hit = performance["politicians"]["OneHitWonder"]
        # raw alpha would be ~490%; shrinkage plus the tanh saturation must keep the
        # published avg_alpha_pct far below the raw outlier and the score within [0, 1]
        assert one_hit["raw_avg_alpha_pct"] > 400
        assert one_hit["avg_alpha_pct"] < 400
        assert 0.0 <= one_hit["performance_score"] <= 1.0

    def test_small_sample_size_does_not_inflate_weight_versus_a_deep_track_record(self):
        # Both politicians have an identical 100% raw win rate; the one with only 2 trades
        # should be shrunk further toward the population mean than the one with 20.
        rows = [priced_buy("FewTrades", 20.0), priced_buy("FewTrades", 20.0)]
        rows += [priced_buy("ManyTrades", 20.0) for _ in range(20)]
        rows += [priced_buy("Baseline", -20.0) for _ in range(20)]  # drags the population down
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        few = performance["politicians"]["FewTrades"]
        many = performance["politicians"]["ManyTrades"]
        assert few["raw_win_rate"] == many["raw_win_rate"] == 1.0
        assert few["win_rate"] < many["win_rate"]
        assert few["confidence"] == "low"
        assert many["confidence"] == "high"

    def test_only_buys_are_scored_not_sells(self):
        rows = [priced_buy("Rep A", 50.0, transaction_type="Sale")]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        assert performance["politicians"] == {}


class TestSignalStrength:
    def test_stale_disclosure_scores_zero(self):
        row = priced_buy("Rep A", 20.0, disclosure_date="2020-01-01")
        performance = module.compute_performance_scores([row], benchmark=BENCHMARK)
        assert module.signal_strength(row, performance, as_of=TODAY) == 0.0

    def test_a_better_track_record_yields_a_strictly_higher_signal_for_an_identical_trade(self):
        rows = [priced_buy("Winner", 40.0), priced_buy("Loser", -40.0)]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        fresh_trade_winner = priced_buy("Winner", 0.0, disclosure_date=str(TODAY))
        fresh_trade_loser = priced_buy("Loser", 0.0, disclosure_date=str(TODAY))
        winner_signal = module.signal_strength(fresh_trade_winner, performance, as_of=TODAY)
        loser_signal = module.signal_strength(fresh_trade_loser, performance, as_of=TODAY)
        assert winner_signal > loser_signal

    def test_a_zero_dollar_trade_still_scores_zero_regardless_of_performance(self):
        row = priced_buy("Rep A", 40.0, amount_lower=0, disclosure_date=str(TODAY))
        performance = module.compute_performance_scores([row], benchmark=BENCHMARK)
        assert module.signal_strength(row, performance, as_of=TODAY) == 0.0

    def test_a_poor_track_record_is_discounted_but_never_zeroed_by_the_floor(self):
        rows = [priced_buy("Loser", -50.0) for _ in range(20)]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        row = priced_buy("Loser", 0.0, disclosure_date=str(TODAY), amount_lower=1_000_000)
        signal = module.signal_strength(row, performance, as_of=TODAY)
        assert signal > 0.0
        assert signal <= module.DEFAULTS["signal_floor"] + 0.05


class TestLeaderboard:
    def test_ranked_by_performance_score_then_more_evidence_then_name(self):
        rows = [priced_buy("A", 30.0), priced_buy("A", 30.0), priced_buy("A", 30.0),
                priced_buy("B", 30.0), priced_buy("B", 30.0)]
        performance = module.compute_performance_scores(rows, benchmark=BENCHMARK)
        board = module.leaderboard(performance)
        assert [row["politician"] for row in board] == ["A", "B"]
        assert board[0]["rank"] == 1 and board[1]["rank"] == 2


class TestSelectBackfillCandidates:
    def test_never_priced_symbols_are_offered_and_already_cached_trades_are_not(self):
        cached_row = unpriced_buy("Rep A", "CACHED")
        uncached_row = unpriced_buy("Rep A", "NEW")
        key = module._cache_key(("senate", "Rep A", "CACHED", "2026-01-01", "Purchase", "$15,001 - $50,000"))
        cache = {key: {"return_since_purchase_pct": 5.0}}
        candidates = module.select_backfill_candidates([cached_row, uncached_row], cache)
        symbols = {row["symbol"] for row in candidates}
        assert symbols == {"NEW"}

    def test_only_equity_purchases_are_candidates(self):
        rows = [unpriced_buy("Rep A", "SOLD", transaction_date="2026-01-01"),
                {**unpriced_buy("Rep A", "OPT"), "asset_type": "Stock Option"},
                {**unpriced_buy("Rep A", "SALE"), "transaction_type": "Sale"}]
        candidates = module.select_backfill_candidates(rows, {})
        assert {row["symbol"] for row in candidates} == {"SOLD"}

    def test_symbols_with_more_distinct_politicians_are_prioritized(self):
        rows = ([unpriced_buy("Rep A", "POPULAR"), unpriced_buy("Rep B", "POPULAR"),
                 unpriced_buy("Rep C", "POPULAR")]
                + [unpriced_buy("Rep A", "LONELY")])
        candidates = module.select_backfill_candidates(rows, {}, max_symbols=1)
        assert {row["symbol"] for row in candidates} == {"POPULAR"}

    def test_respects_the_max_symbols_budget(self):
        rows = [unpriced_buy("Rep A", f"SYM{i}") for i in range(10)]
        candidates = module.select_backfill_candidates(rows, {}, max_symbols=3)
        assert len({row["symbol"] for row in candidates}) == 3


class TestMergeAndFullHistory:
    def test_priced_trades_are_written_into_the_cache(self):
        row = priced_buy("Rep A", 20.0, symbol="AAPL")
        key = module._cache_key(("senate", "Rep A", "AAPL", "2026-01-01", "Purchase", "$15,001 - $50,000"))
        priced = {("senate", "Rep A", "AAPL", "2026-01-01", "Purchase", "$15,001 - $50,000"):
                  {"return_since_purchase_pct": 20.0, "price_as_of": "2026-06-01"}}
        cache = module.merge_price_performance([row], priced, {})
        assert key in cache
        assert cache[key]["return_since_purchase_pct"] == 20.0

    def test_full_priced_equity_buys_annotates_only_cached_rows(self):
        cached = unpriced_buy("Rep A", "CACHED")
        uncached = unpriced_buy("Rep A", "UNCACHED")
        key = module._cache_key(("senate", "Rep A", "CACHED", "2026-01-01", "Purchase", "$15,001 - $50,000"))
        cache = {key: {"return_since_purchase_pct": 12.0, "price_as_of": "2026-06-01"}}
        annotated = module.full_priced_equity_buys([cached, uncached], cache)
        assert len(annotated) == 1
        assert annotated[0]["symbol"] == "CACHED"
        assert annotated[0]["return_since_purchase_pct"] == 12.0

    def test_full_history_feeds_compute_performance_scores_beyond_a_narrow_window(self):
        # Simulates what a window-only view would miss: a politician whose only priced buy
        # is old (out of any short publish window) still shows up once the cache carries it.
        old_row = priced_buy("Old Timer", 25.0, transaction_date="2020-01-01",
                             price_as_of="2020-06-01", symbol="OLD")
        cache = module.merge_price_performance(
            [old_row], {("senate", "Old Timer", "OLD", "2020-01-01", "Purchase", "$15,001 - $50,000"):
                        {"return_since_purchase_pct": 25.0, "price_as_of": "2020-06-01"}}, {})
        full_history = module.full_priced_equity_buys([old_row], cache)
        benchmark = {"dates": ["2020-01-01", "2020-06-01"], "closes": [300.0, 315.0]}  # flat +5% SPY
        performance = module.compute_performance_scores(full_history, benchmark=benchmark)
        assert "Old Timer" in performance["politicians"]
        assert performance["politicians"]["Old Timer"]["n_priced_buys"] == 1


class TestBackfillCoverage:
    def test_reports_total_priced_and_coverage_percent(self):
        cached = unpriced_buy("Rep A", "CACHED")
        uncached = unpriced_buy("Rep A", "UNCACHED")
        key = module._cache_key(("senate", "Rep A", "CACHED", "2026-01-01", "Purchase", "$15,001 - $50,000"))
        cache = {key: {"return_since_purchase_pct": 1.0}}
        coverage = module.backfill_coverage([cached, uncached], cache)
        assert coverage == {"equity_buys_total": 2, "equity_buys_priced": 1, "coverage_pct": 50.0}

    def test_an_empty_history_reports_zero_coverage_not_a_division_error(self):
        assert module.backfill_coverage([], {})["coverage_pct"] == 0.0


class TestPriceCacheRoundTrip:
    def test_save_then_load_round_trips_through_the_store(self, tmp_path, monkeypatch):
        import common
        monkeypatch.setattr(common, "STORE_DIR", str(tmp_path))
        assert module.load_price_cache() == {}
        module.save_price_cache({"a|b|c|d|e|f": {"return_since_purchase_pct": 7.0}})
        assert module.load_price_cache() == {"a|b|c|d|e|f": {"return_since_purchase_pct": 7.0}}
