import build_backtest_comparison as comparison


def history(pairs):
    return [{"date": date, "value": value} for date, value in pairs]


def rebalance(execution_date, picks=1):
    return {"execution_date": execution_date,
            "picks": [{"ticker": f"T{index}"} for index in range(picks)]}


def test_success_rate_counts_only_periods_the_portfolio_was_actually_held():
    portfolio = {
        "history": history([("2026-01-02", 100), ("2026-02-02", 110), ("2026-03-02", 99)]),
        "rebalances": [rebalance("2026-01-02"), rebalance("2026-02-02")],
    }

    result = comparison.period_success(portfolio, {})

    assert result["periods"] == 2
    assert result["success_rate"] == 0.5      # up then down
    assert result["periods_in_cash"] == 0


def test_a_strategy_that_qualified_nobody_reports_cash_periods_not_a_zero_percent_win_rate():
    # A cash period returns exactly 0, which is not > 0, so counting it would score a screen
    # that never traded as one that lost every single period.
    portfolio = {
        "history": history([("2026-01-02", 100), ("2026-02-02", 100), ("2026-03-02", 100)]),
        "rebalances": [rebalance("2026-01-02", picks=0), rebalance("2026-02-02", picks=0)],
    }

    result = comparison.period_success(portfolio, {})

    assert result["success_rate"] is None
    assert result["periods"] == 0
    assert result["periods_in_cash"] == 2


def test_beat_benchmark_rate_compares_the_same_spans_only():
    portfolio = {
        "history": history([("2026-01-02", 100), ("2026-02-02", 110), ("2026-03-02", 121)]),
        "rebalances": [rebalance("2026-01-02"), rebalance("2026-02-02")],
    }
    benchmark = {"history": history([("2026-01-02", 100), ("2026-02-02", 105), ("2026-03-02", 130)])}

    result = comparison.period_success(portfolio, benchmark)

    assert result["periods"] == 2
    assert result["beat_benchmark_rate"] == 0.5   # beat the first span, lost the second
    assert result["benchmark_comparable_periods"] == 2


def test_portfolio_row_withholds_the_benchmark_difference_when_mostly_in_cash(tmp_path, monkeypatch):
    payload = {
        "generated_at": "2026-08-13T00:00:00Z",
        "status": "insufficient_disclosure_history",
        "method": {"transaction_cost_bps_one_way": 10.0},
        "bias_disclosures": {"survivorship_bias": True},
        "portfolio": {
            "history": history([("2026-01-02", 100), ("2026-02-02", 100),
                                ("2026-03-02", 100), ("2026-04-02", 101)]),
            "rebalances": [rebalance("2026-01-02", picks=0), rebalance("2026-02-02", picks=0),
                           rebalance("2026-03-02", picks=1)],
            "metrics": {"total_return": 0.01, "start_date": "2026-01-02", "end_date": "2026-04-02"},
        },
        "benchmark_spy": {
            "history": history([("2026-01-02", 100), ("2026-02-02", 120),
                                ("2026-03-02", 130), ("2026-04-02", 140)]),
            "metrics": {"total_return": 0.40},
        },
    }
    source = tmp_path / "result.json"
    source.write_text(__import__("json").dumps(payload))
    monkeypatch.setattr(comparison, "REPO_ROOT", str(tmp_path))

    row = comparison.portfolio_row({"id": "x", "label": "X", "source": "result.json",
                                    "features": ["congressional disclosures"], "note": ""})

    assert row["excess_return_pct"] is None
    assert row["time_invested_pct"] == 33.33
    assert "misreport not being invested" in row["excess_return_withheld_reason"]
    assert any("held cash for the rest" in note for note in row["caveats"])


def test_a_missing_result_file_is_reported_rather_than_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison, "REPO_ROOT", str(tmp_path))

    row = comparison.portfolio_row({"id": "x", "label": "X", "source": "absent.json",
                                    "features": [], "note": ""})

    assert row["status"] == "unavailable"
    assert row["label"] == "X"


def test_feature_rollup_never_averages_across_different_success_definitions():
    methods = [
        {"label": "Portfolio", "status": "measured", "success_rate": 0.6,
         "success_rate_basis": "rebalance_periods_positive", "features": ["volume"]},
        {"label": "Options", "status": "measured", "success_rate": 0.3,
         "success_rate_basis": "trades_profitable", "features": ["volume"]},
    ]

    rollup = comparison.feature_rollup(methods)

    assert len(rollup) == 2
    assert {row["success_rate_basis"] for row in rollup} == {
        "rebalance_periods_positive", "trades_profitable"}
    assert all(row["methods"] == 1 for row in rollup)


def test_unmeasured_methods_are_excluded_from_the_feature_rollup():
    methods = [
        {"label": "Pending", "status": "insufficient_disclosure_history", "success_rate": 1.0,
         "success_rate_basis": "rebalance_periods_positive", "features": ["congressional disclosures"]},
        {"label": "Real", "status": "measured", "success_rate": 0.5,
         "success_rate_basis": "rebalance_periods_positive", "features": ["volume"]},
    ]

    rollup = comparison.feature_rollup(methods)

    assert [row["feature"] for row in rollup] == ["volume"]


def test_every_row_declares_a_comparable_group_and_a_success_basis():
    payload = comparison.build()

    for method in payload["methods"]:
        assert method["comparable_group"] in payload["comparable_groups"]
        if method.get("success_rate") is not None:
            assert method["success_rate_basis"] in payload["success_rate_definitions"]
