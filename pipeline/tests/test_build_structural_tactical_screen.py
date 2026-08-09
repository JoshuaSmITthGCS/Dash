import build_structural_tactical_screen as screen


def entry(ticker, revision, breadth, structural, volume=5_000_000, beta=1.0):
    return {
        "ticker": ticker,
        "score": structural,
        "confidence": 0.8,
        "average_dollar_volume": volume,
        "beta": beta,
        "analysis_v2": {"structural": {"effective_score": structural},
                        "applicability_profile": "general"},
        "estimate_detail": {"eps_revision_30d_pct": revision, "revision_breadth_30d": breadth,
                            "net_upgrades_90d": 2, "target_change_30d_pct": 0.01,
                            "revision_period": "0y"},
    }


def test_percentile_ranks_average_ties_and_ignore_missing():
    ranks = screen.percentile_ranks({"A": 1, "B": 3, "C": 3, "D": None})
    assert ranks["A"] == 16.6667
    assert ranks["B"] == ranks["C"] == 66.6667
    assert "D" not in ranks


def test_factors_are_ranked_cross_sectionally_and_blended():
    universe = [entry("AAA", 0.10, 0.9, 80), entry("BBB", 0.01, 0.1, 40),
                entry("CCC", 0.05, 0.5, 60)]
    collected = screen.collect_factors(universe, momentum_rows=[])
    scored = {row["ticker"]: row for row in screen.score_universe(collected)}
    # AAA has the strongest revisions in the cross-section, so it must outrank the weakest.
    assert scored["AAA"]["tactical_score"] > scored["BBB"]["tactical_score"]
    assert scored["AAA"]["classification"] == "high-conviction candidate"


def sparse(ticker, revision):
    """Only one of the fifteen declared factors is observable for this ticker."""
    return {"ticker": ticker, "score": 70,
            "analysis_v2": {"structural": {"effective_score": 70}},
            "estimate_detail": {"eps_revision_30d_pct": revision, "revision_period": "0y"}}


def test_missing_factors_reduce_coverage_rather_than_defaulting_to_neutral():
    collected = screen.collect_factors([sparse("AAA", 0.10), sparse("BBB", 0.01)],
                                       momentum_rows=[])
    scored = screen.score_universe(collected)[0]
    # One factor carrying 0.12 of the declared weight is scored on its own merits, not
    # padded to a full book with neutral 50s.
    assert scored["tactical_score"] is not None
    assert scored["coverage"] < screen.MINIMUM_COVERAGE
    result = screen.to_result(1, scored)
    assert result["eligibility"] is False
    assert "INSUFFICIENT_FACTOR_COVERAGE" in result["reason_codes"]


def test_a_ticker_with_no_observable_factors_is_reported_as_such():
    collected = screen.collect_factors(
        [{"ticker": "AAA", "score": 70, "estimate_detail": {}}], momentum_rows=[])
    result = screen.to_result(1, screen.score_universe(collected)[0])
    assert result["tactical_score"] is None
    assert result["eligibility"] is False
    assert "NO_TACTICAL_FACTORS_AVAILABLE" in result["reason_codes"]


def test_momentum_factors_are_carried_in_from_the_shared_price_pass():
    universe = [entry("AAA", 0.10, 0.9, 80), entry("BBB", 0.01, 0.1, 40)]
    momentum_rows = [{"ticker": "AAA", "factors": {"momentum_12_1": 0.4, "momentum_6_1": 0.2,
                                                   "high_52w_proximity": 0.95}},
                     {"ticker": "BBB", "factors": {"momentum_12_1": -0.1, "momentum_6_1": -0.2,
                                                   "high_52w_proximity": 0.40}}]
    collected = screen.collect_factors(universe, momentum_rows)
    assert collected["AAA"]["factors"]["momentum_12_1"] == 0.4
    scored = {row["ticker"]: row for row in screen.score_universe(collected)}
    assert scored["AAA"]["coverage"] > scored["AAA"]["coverage"] - 1  # coverage is defined
    assert "momentum_12_1" in scored["AAA"]["contribution_by_factor"]


def test_a_missing_revision_snapshot_flags_rather_than_withholds_the_score():
    unflagged = entry("AAA", 0.1, 0.5, 70)
    unflagged["estimate_detail"].pop("revision_period")
    collected = screen.collect_factors([unflagged, entry("BBB", 0.01, 0.1, 40)], [])
    scored = {row["ticker"]: row for row in screen.score_universe(collected)}
    assert scored["AAA"]["tactical_score"] is not None
    assert "REVISION_BACKTEST_UNAVAILABLE" in scored["AAA"]["quality_flags"]
