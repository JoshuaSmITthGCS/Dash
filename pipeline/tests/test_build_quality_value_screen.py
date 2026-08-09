import build_quality_value_screen as screen

WEIGHTS = {"own_history_weight": 0.5, "peer_value_weight": 0.15, "quality_weight": 0.35}


def entry(ticker, forward_pe, quality=70, profile="general", altman_z=4.0):
    return {"ticker": ticker, "forward_pe": forward_pe, "price_to_book": 2.0,
            "free_cash_flow_yield": 0.06, "altman_z": altman_z, "confidence": 0.8,
            "analysis_v2": {"applicability_profile": profile,
                            "structural": {"effective_score": quality}},
            "estimate_detail": {}}


def history(ticker, metric, values):
    return {ticker: {metric: [{"observed_at": f"2026-08-{day:02d}", "value": value}
                              for day, value in enumerate(values, start=1)]}}


def test_a_ticker_cheap_against_its_own_history_scores_high():
    # Today's forward P/E of 10 is the cheapest reading in its own recorded history.
    histories = history("AAA", "forward_pe", [20, 18, 16, 15, 14, 13, 12, 11, 10.5, 10.2, 10.1, 10])
    rows = screen.collect([entry("AAA", 10)], histories)
    scored = screen.score_universe(rows, minimum_observations=12, weights=WEIGHTS)[0]
    assert scored["own_history_score"] >= 70
    assert scored["observations"] == 12


def test_history_shorter_than_the_declared_minimum_is_held_ineligible():
    histories = history("AAA", "forward_pe", [20, 18, 16])
    rows = screen.collect([entry("AAA", 10)], histories)
    scored = screen.score_universe(rows, minimum_observations=12, weights=WEIGHTS)[0]
    assert scored["eligibility"] is False
    assert scored["classification"] == "insufficient historical data"
    assert "INSUFFICIENT_HISTORICAL_DATA" in scored["reason_codes"]
    assert scored["observations"] == 3


def test_suppressed_metrics_do_not_count_toward_history_depth():
    # A bank's free cash flow yield is suppressed by the applicability matrix, so a long
    # history of it cannot stand in for the depth the applicable metrics still lack.
    histories = {"AAA": {"free_cash_flow_yield": [{"observed_at": "2026-08-01", "value": 0.05}] * 30,
                         "forward_pe": [{"observed_at": "2026-08-01", "value": 12}] * 3}}
    rows = screen.collect([entry("AAA", 10, profile="bank")], histories)
    assert rows[0]["applicability"]["free_cash_flow_yield"] == 0
    assert screen.observation_depth(rows[0]["metrics"], rows[0]["applicability"]) == 3


def test_a_distressed_company_is_never_actionable_value():
    histories = history("AAA", "forward_pe", [20] * 11 + [10])
    rows = screen.collect([entry("AAA", 5, quality=90, altman_z=1.0)], histories)
    scored = screen.score_universe(rows, minimum_observations=12, weights=WEIGHTS)[0]
    assert scored["classification"] == "distressed/value trap"
    assert scored["eligibility"] is False


def test_peer_value_needs_more_than_one_member_to_mean_anything():
    histories = history("AAA", "forward_pe", [20, 15, 10])
    rows = screen.collect([entry("AAA", 10)], histories)
    assert screen.peer_value_scores(rows) == {"AAA": None}

    paired = screen.collect([entry("AAA", 10), entry("BBB", 40)], histories)
    scores = screen.peer_value_scores(paired)
    # The cheaper of the two sits at the cheap end of its peer group.
    assert scores["AAA"] > scores["BBB"]


def test_composite_renormalizes_over_the_components_that_exist():
    histories = history("AAA", "forward_pe", [20, 15, 10])
    rows = screen.collect([entry("AAA", 10, quality=None)], histories)
    rows[0]["quality_score"] = None
    scored = screen.score_universe(rows, minimum_observations=1, weights=WEIGHTS)[0]
    # Quality is absent and peer value needs a second member, so the composite is the
    # own-history score alone rather than that score diluted by missing inputs.
    assert scored["peer_value_score"] is None
    assert scored["quality_value_score"] == round(scored["own_history_score"], 4)
