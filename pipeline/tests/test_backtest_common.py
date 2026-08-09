import backtest_common as module
import options_common as oc


def test_synthetic_chain_prices_are_positive_and_bid_below_ask():
    calls, puts = module.synthetic_chain(price=100, iv=0.3, dte=30)
    assert calls.rows and puts.rows
    for row in calls.rows + puts.rows:
        assert row["bid"] > 0
        assert row["ask"] > row["bid"]
        assert row["strike"] > 0


def test_synthetic_chain_atm_call_roughly_matches_black_scholes_price():
    calls, _ = module.synthetic_chain(price=100, iv=0.3, dte=30, strike_step_pct=1)
    atm = min(calls.rows, key=lambda row: abs(row["strike"] - 100))
    theoretical = oc.call_price(100, atm["strike"], 0.3, 30)
    mid = (atm["bid"] + atm["ask"]) / 2
    assert abs(mid - theoretical) < 0.05


def test_synthetic_chain_handles_degenerate_inputs():
    calls, puts = module.synthetic_chain(price=None, iv=0.3, dte=30)
    assert calls.rows == [] and puts.rows == []
    calls, puts = module.synthetic_chain(price=100, iv=0, dte=30)
    assert calls.rows == [] and puts.rows == []
    calls, puts = module.synthetic_chain(price=100, iv=0.3, dte=0)
    assert calls.rows == [] and puts.rows == []


def test_walk_periods_are_sequential_and_non_overlapping():
    closes = list(range(200))
    periods = module.walk_periods(closes, target_dte=30, lookback=21)
    assert periods[0][0] == 21
    for (entry, expiry), (next_entry, _) in zip(periods, periods[1:]):
        assert expiry == next_entry
        assert expiry > entry


def test_walk_periods_returns_empty_when_history_too_short():
    assert module.walk_periods(list(range(10)), target_dte=30, lookback=21) == []


def test_performance_stats_all_positive_periods_has_full_win_rate_and_positive_return():
    stats = module.performance_stats([0.02, 0.03, 0.01, 0.015], periods_per_year=12)
    assert stats["win_rate"] == 1.0
    assert stats["total_return"] > 0
    assert stats["annualized_return"] > 0
    assert stats["num_trades"] == 4
    assert stats["equity_curve"][0] == 1.0
    assert stats["equity_curve"][-1] > 1.0


def test_performance_stats_computes_drawdown_on_a_loss_after_a_gain():
    stats = module.performance_stats([0.10, -0.20, 0.05], periods_per_year=12)
    assert stats["max_drawdown"] < 0
    assert stats["max_drawdown"] >= -0.20 - 1e-9


def test_performance_stats_returns_none_for_empty_input():
    assert module.performance_stats([], periods_per_year=12) is None


def test_performance_stats_sharpe_none_when_stdev_zero():
    stats = module.performance_stats([0.01, 0.01, 0.01], periods_per_year=12)
    assert stats["sharpe_ratio"] is None


def test_performance_stats_includes_average_pnl_when_trade_pnls_given():
    stats = module.performance_stats([0.01, -0.01], periods_per_year=12, trade_pnls=[50, -30])
    assert stats["average_pnl_per_trade"] == 10.0


def test_performance_stats_publishes_deflated_sharpe_fields_with_enough_observations():
    returns = [0.02, -0.01, 0.03, 0.01, -0.02, 0.015, 0.005, -0.01, 0.02, 0.01]
    stats = module.performance_stats(returns, periods_per_year=12, num_trials=8)
    assert stats["skewness"] is not None
    assert stats["kurtosis"] is not None
    assert stats["probabilistic_sharpe_ratio"] is not None
    assert 0 <= stats["probabilistic_sharpe_ratio"] <= 1
    assert stats["deflated_sharpe_ratio"] is not None
    assert 0 <= stats["deflated_sharpe_ratio"] <= 1
    assert stats["deflated_sharpe_trials"] == 8
    # More trials is a harder bar to clear than fewer - DSR should be <= PSR against SR*=0.
    assert stats["deflated_sharpe_ratio"] <= stats["probabilistic_sharpe_ratio"] + 1e-9


def test_performance_stats_sharpe_ratio_fields_none_when_stdev_zero():
    stats = module.performance_stats([0.01, 0.01, 0.01], periods_per_year=12)
    assert stats["sharpe_ratio"] is None
    assert stats["probabilistic_sharpe_ratio"] is None
    assert stats["deflated_sharpe_ratio"] is None


def test_skew_kurtosis_is_none_below_three_observations_or_zero_stdev():
    assert module.probabilistic_sharpe_ratio(1.0, n=1, skew=0.0, kurtosis=3.0) is None
    assert module.deflated_sharpe_ratio(1.0, n=1, skew=0.0, kurtosis=3.0) is None
    assert module.probabilistic_sharpe_ratio(None, n=10, skew=0.0, kurtosis=3.0) is None


def test_deflated_sharpe_ratio_more_trials_is_a_higher_bar():
    # Same observed Sharpe ratio, more trials to compare against -> harder to clear, so DSR
    # should not increase as num_trials grows.
    dsr_few = module.deflated_sharpe_ratio(1.2, n=200, skew=-0.3, kurtosis=4.0, num_trials=2)
    dsr_many = module.deflated_sharpe_ratio(1.2, n=200, skew=-0.3, kurtosis=4.0, num_trials=50)
    assert dsr_many <= dsr_few + 1e-9


def test_deflated_sharpe_ratio_rejects_non_positive_trials():
    assert module.deflated_sharpe_ratio(1.0, n=10, skew=0.0, kurtosis=3.0, num_trials=0) is None
