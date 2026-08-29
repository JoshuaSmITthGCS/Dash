import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pre_breakout_signals as pbs


# ---------------- weight-dict invariants ----------------

def test_top_level_weights_are_equal_thirds_and_sum_to_one():
    assert abs(sum(pbs.PRE_BREAKOUT_WEIGHTS.values()) - 1.0) < 1e-9
    for weight in pbs.PRE_BREAKOUT_WEIGHTS.values():
        assert abs(weight - 1 / 3) < 1e-9


def test_every_subweight_dict_sums_to_one():
    for subweights in pbs.SUBWEIGHTS_BY_LEG.values():
        assert abs(sum(subweights.values()) - 1.0) < 1e-9


def test_every_subfactor_is_declared_in_exactly_one_leg_with_a_matching_subweight():
    for leg, subfactors in pbs.PRE_BREAKOUT_SUBFACTORS.items():
        names = [name for name, _negate in subfactors]
        assert set(names) == set(pbs.SUBWEIGHTS_BY_LEG[leg])


# ---------------- signed_path_smoothness ----------------

def test_signed_path_smoothness_follows_momentum_direction():
    assert pbs.signed_path_smoothness(0.9, momentum_12_1=0.15) == 0.9
    assert pbs.signed_path_smoothness(0.9, momentum_12_1=-0.15) == -0.9
    assert pbs.signed_path_smoothness(0.9, momentum_12_1=0.0) == 0.0


def test_signed_path_smoothness_is_none_without_both_inputs():
    assert pbs.signed_path_smoothness(None, 0.1) is None
    assert pbs.signed_path_smoothness(0.9, None) is None


# ---------------- short_interest_change ----------------

def test_short_interest_change_is_positive_on_a_decline_off_the_recent_high():
    history = [{"observed_at": "2026-01-01", "value": 5.0},
              {"observed_at": "2026-02-01", "value": 10.0},
              {"observed_at": "2026-03-01", "value": 6.0}]
    change = pbs.short_interest_change(history, as_of="2026-03-01")
    assert change == (10.0 - 6.0) / 10.0


def test_short_interest_change_never_sees_a_reading_after_as_of():
    history = [{"observed_at": "2026-01-01", "value": 5.0},
              {"observed_at": "2026-02-01", "value": 10.0},
              {"observed_at": "2026-03-01", "value": 1.0}]  # after the cutoff below
    change = pbs.short_interest_change(history, as_of="2026-02-01")
    # With the 2026-03-01 reading excluded, the only two visible points are 5.0 then 10.0:
    # a rise, not a decline, so the recent high (5.0, the only point before "current") is
    # exceeded rather than declined from.
    assert change == (5.0 - 10.0) / 5.0


def test_short_interest_change_needs_at_least_two_observations():
    assert pbs.short_interest_change([{"observed_at": "2026-01-01", "value": 5.0}],
                                     as_of="2026-01-01") is None
    assert pbs.short_interest_change([], as_of="2026-01-01") is None


# ---------------- classify_stage ----------------

def test_classify_stage_extended_when_momentum_is_far_above_the_cross_section():
    assert pbs.classify_stage(momentum_z=2.0, contraction_z=0.0) == "extended"


def test_classify_stage_breaking_out_when_momentum_is_meaningfully_positive_but_not_extended():
    assert pbs.classify_stage(momentum_z=0.5, contraction_z=0.0) == "breaking_out"
    # Right at the extended boundary itself reads extended, not breaking_out.
    assert pbs.classify_stage(momentum_z=1.5, contraction_z=0.0) == "extended"


def test_classify_stage_coiling_when_momentum_is_flat_but_tightly_contracted():
    assert pbs.classify_stage(momentum_z=0.0, contraction_z=0.8) == "coiling"
    # Right at the coiling boundary itself reads coiling.
    assert pbs.classify_stage(momentum_z=0.0, contraction_z=0.5) == "coiling"


def test_classify_stage_unclassified_when_neither_condition_is_met():
    assert pbs.classify_stage(momentum_z=0.0, contraction_z=0.0) == "unclassified"
    assert pbs.classify_stage(momentum_z=0.0, contraction_z=None) == "unclassified"


def test_classify_stage_unclassified_without_a_momentum_reading():
    # No momentum reading at all -- a squeeze alone, with no idea which way price has been
    # drifting, is not enough to call a stage.
    assert pbs.classify_stage(momentum_z=None, contraction_z=0.9) == "unclassified"


def test_classify_stage_never_scores_into_the_composite():
    """Structural guard: classify_stage must stay a pure, standalone read -- it must not
    appear in any leg's declared subfactors or weights."""
    declared_subfactor_names = {name for subfactors in pbs.PRE_BREAKOUT_SUBFACTORS.values()
                                for name, _negate in subfactors}
    assert "classification" not in declared_subfactor_names
    assert "stage" not in declared_subfactor_names


# ---------------- leg / composite blending ----------------

def _row(ticker, raw_factors, **extra):
    return {"ticker": ticker, "price": 20, "market_cap": 5e9, "median_dollar_volume_60d": 1e7,
           "history_sessions": 300, "raw_factors": raw_factors, **extra}


def _full_coverage_factors(scale=1.0):
    return {
        "earnings_acceleration": 1.0 * scale, "revenue_acceleration": 1.0 * scale,
        "roa_delta": 1.0 * scale, "margin_turn": 1.0 * scale,
        "standardized_unexpected_earnings": 1.0 * scale,
        "momentum_12_1": 1.0 * scale, "path_smoothness": 1.0 * scale,
        "industry_relative_momentum": 1.0 * scale, "volatility_contraction": 1.0 * scale,
        "insider_cluster_score": 1.0 * scale, "short_interest_change": 1.0 * scale,
    }


def test_a_fully_resolved_row_is_eligible_and_scored_on_all_three_legs():
    rows = [_row("AAA", _full_coverage_factors(scale=2.0)),
           _row("BBB", _full_coverage_factors(scale=1.0)),
           _row("CCC", _full_coverage_factors(scale=-1.0)),
           _row("DDD", _full_coverage_factors(scale=-2.0))]
    scored = pbs.pre_breakout_scores(rows)

    top = next(row for row in scored if row["ticker"] == "AAA")
    assert top["eligibility"] is True
    assert top["legs_resolved"] == 3
    assert set(top["sub_scores"]) == {"fundamental_inflection", "momentum_rs", "flow_sentiment"}
    assert all(leg["applied"] for leg in top["sub_scores"].values())
    # AAA has the largest raw factors across the board, so it should rank highest.
    assert scored[0]["ticker"] == "AAA"
    assert all(row["classification"] in ("coiling", "breaking_out", "extended", "unclassified")
              for row in scored)


def test_classification_distinguishes_an_already_moving_row_from_a_coiled_one():
    """Composite-level regression for the gap that prompted classify_stage: a row with
    strong existing momentum and no squeeze must not read the same as a flat, tightly
    coiled one, even though the blended composite score alone cannot tell them apart."""
    rows = [
        _row("MOVER", {**_full_coverage_factors(), "momentum_12_1": 5.0, "volatility_contraction": 0.1}),
        _row("COILED", {**_full_coverage_factors(), "momentum_12_1": 0.0, "volatility_contraction": 5.0}),
        _row("FLAT", {**_full_coverage_factors(), "momentum_12_1": 0.0, "volatility_contraction": 0.0}),
        _row("MIDDLE", {**_full_coverage_factors(), "momentum_12_1": 1.0, "volatility_contraction": 1.0}),
    ]

    scored = pbs.pre_breakout_scores(rows)
    by_ticker = {row["ticker"]: row for row in scored}

    assert by_ticker["MOVER"]["classification"] in ("breaking_out", "extended")
    assert by_ticker["COILED"]["classification"] == "coiling"
    assert by_ticker["COILED"]["classification"] != by_ticker["MOVER"]["classification"]


def test_gates_apply_once_at_the_top_never_per_leg():
    cheap = _row("PENNY", _full_coverage_factors(), price=1)
    thin = _row("THIN", _full_coverage_factors(), market_cap=1e6)
    illiquid = _row("ILLIQUID", _full_coverage_factors(), median_dollar_volume_60d=1e5)
    young = _row("YOUNG", _full_coverage_factors(), history_sessions=10)
    scored = pbs.pre_breakout_scores([cheap, thin, illiquid, young])

    reasons = {row["ticker"]: row["reason_codes"] for row in scored}
    assert "MINIMUM_PRICE" in reasons["PENNY"]
    assert "MINIMUM_MARKET_CAP" in reasons["THIN"]
    assert "MINIMUM_LIQUIDITY" in reasons["ILLIQUID"]
    assert "INSUFFICIENT_HISTORY" in reasons["YOUNG"]
    for row in scored:
        assert row["eligibility"] is False
        # A gate failure must not have prevented the composite from being scored -- the row
        # still carries its score and full leg detail, only its eligibility flag changes.
        assert row["score"] is not None


def test_distress_gate_reuses_build_quality_value_screens_thresholds():
    distressed = _row("ZOMBIE", _full_coverage_factors(),
                      observed={"altman_z": 1.0, "interest_coverage": 5.0})
    healthy = _row("HEALTHY", _full_coverage_factors(),
                   observed={"altman_z": 4.0, "interest_coverage": 5.0})
    scored = pbs.pre_breakout_scores([distressed, healthy])

    zombie = next(row for row in scored if row["ticker"] == "ZOMBIE")
    healthy_row = next(row for row in scored if row["ticker"] == "HEALTHY")
    assert "DISTRESSED" in zombie["reason_codes"]
    assert "DISTRESSED" not in healthy_row["reason_codes"]


def test_a_row_missing_one_whole_leg_renormalizes_over_the_remaining_two():
    factors = _full_coverage_factors()
    # Blank out every flow_sentiment subfactor - the row should still resolve 2 of 3 legs
    # and clear the default minimum_legs_resolved=2 floor.
    factors["insider_cluster_score"] = None
    factors["short_interest_change"] = None
    partial = _row("PARTIAL", factors)
    full = _row("FULL", _full_coverage_factors())
    scored = pbs.pre_breakout_scores([partial, full])

    partial_row = next(row for row in scored if row["ticker"] == "PARTIAL")
    assert partial_row["legs_resolved"] == 2
    assert partial_row["sub_scores"]["flow_sentiment"]["applied"] is False
    assert partial_row["sub_scores"]["fundamental_inflection"]["applied"] is True
    assert partial_row["sub_scores"]["momentum_rs"]["applied"] is True
    assert partial_row["score"] is not None
    assert partial_row["eligibility"] is True
    assert partial_row["renormalization_factor"] > 1.0


def test_a_row_below_the_minimum_legs_resolved_floor_is_ineligible_but_still_scored():
    factors = _full_coverage_factors()
    for name in pbs.SUBWEIGHTS_BY_LEG["momentum_rs"]:
        factors[name] = None
    for name in pbs.SUBWEIGHTS_BY_LEG["flow_sentiment"]:
        factors[name] = None
    thin = _row("ONELEG", factors)
    scored = pbs.pre_breakout_scores([thin])

    row = scored[0]
    assert row["legs_resolved"] == 1
    assert "INSUFFICIENT_LEGS_RESOLVED" in row["reason_codes"]
    assert row["eligibility"] is False
    assert row["score"] is not None  # still scored on the one leg that did resolve


def test_percentile_and_hysteresis_only_apply_to_eligible_rows():
    rows = [_row(f"T{i}", _full_coverage_factors(scale=i)) for i in range(1, 11)]
    scored = pbs.pre_breakout_scores(rows, current_members={"T6": True},
                                     config={"entry_percentile": 90, "exit_percentile": 50})
    by_ticker = {row["ticker"]: row for row in scored}
    assert all(row["percentile"] is not None for row in scored if row["eligibility"])
    # T10 has the largest raw factors across every subfactor and was never a member: its
    # percentile clears the entry threshold, so it must be selected in.
    assert by_ticker["T10"]["percentile"] >= 90
    assert by_ticker["T10"]["current_membership"] is True
    # T6 was already a member; its own percentile clears the lower exit threshold but not the
    # higher entry one, so hysteresis must keep it in rather than requiring it to re-clear the
    # entry bar it would need if it were a fresh candidate.
    assert 50 <= by_ticker["T6"]["percentile"] < 90
    assert by_ticker["T6"]["current_membership"] is True
    # T1, the lowest-scoring row and never a member, must not be pulled in by either bar.
    assert by_ticker["T1"]["current_membership"] is False


def test_dropping_volatility_contraction_from_momentum_rs_still_produces_a_well_defined_score():
    """The concrete regression test for the module's central design claim: removing the
    weakest-evidence subfactor from its leg's subweights (and renormalizing the rest) is the
    only change needed anywhere - no other code path changes."""
    reduced_subweights = {name: weight for name, weight in pbs.MOMENTUM_RS_SUBWEIGHTS.items()
                          if name != "volatility_contraction"}
    total = sum(reduced_subweights.values())
    reduced_subweights = {name: weight / total for name, weight in reduced_subweights.items()}
    assert abs(sum(reduced_subweights.values()) - 1.0) < 1e-9

    reduced_subfactors = tuple((name, negate) for name, negate in pbs.PRE_BREAKOUT_SUBFACTORS["momentum_rs"]
                               if name != "volatility_contraction")

    rows = [_row("AAA", _full_coverage_factors(scale=2.0)), _row("BBB", _full_coverage_factors(scale=1.0))]
    standardized = pbs._standardized_subfactors(rows, {"momentum_rs": reduced_subfactors})
    score, contributions, resolved, coverage, renorm = pbs._leg_score(
        0, standardized, reduced_subfactors, reduced_subweights)

    assert score is not None
    assert resolved == 3  # momentum_12_1, path_smoothness, industry_relative_momentum
    assert abs(coverage - 1.0) < 1e-9
    assert renorm == 1.0
