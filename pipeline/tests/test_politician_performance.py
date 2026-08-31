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
              transaction_type="Purchase"):
    return {
        "representative": representative, "transaction_type": transaction_type,
        "transaction_date": transaction_date, "price_as_of": price_as_of,
        "disclosure_date": disclosure_date or transaction_date,
        "return_since_purchase_pct": return_pct, "amount_lower": amount_lower,
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
