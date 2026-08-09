from datetime import date, datetime, timezone

import options_common as module

TODAY = date(2024, 3, 10)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=200):
    return {"strike": strike, "bid": bid, "ask": ask, "openInterest": open_interest,
            "impliedVolatility": iv, "volume": volume}


def test_normal_cdf_matches_known_values():
    assert abs(module.normal_cdf(0) - 0.5) < 1e-9
    assert abs(module.normal_cdf(1.959964) - 0.975) < 1e-4
    assert abs(module.normal_cdf(-1.959964) - 0.025) < 1e-4


def test_call_delta_is_near_half_at_the_money():
    delta = module.call_delta(price=100, strike=100, iv=0.3, dte=30)
    assert 0.45 < delta < 0.65  # slightly above .5 from the drift term, still centered


def test_call_delta_falls_as_strike_moves_further_otm():
    near = module.call_delta(price=100, strike=105, iv=0.3, dte=30)
    far = module.call_delta(price=100, strike=130, iv=0.3, dte=30)
    assert near > far


def test_put_delta_is_negative_and_near_the_money_around_minus_half():
    delta = module.put_delta(price=100, strike=100, iv=0.3, dte=30)
    assert -0.65 < delta < -0.35


def test_bs_helpers_return_none_for_degenerate_inputs():
    assert module.bs_d1_d2(price=None, strike=100, iv=0.3, dte=30) == (None, None)
    assert module.bs_d1_d2(price=100, strike=100, iv=0, dte=30) == (None, None)
    assert module.bs_d1_d2(price=100, strike=100, iv=0.3, dte=0) == (None, None)
    assert module.call_delta(price=100, strike=100, iv=0.3, dte=0) is None


def test_probability_above_and_below_sum_to_one():
    above = module.probability_above(price=100, strike=105, iv=0.35, dte=20)
    below = module.probability_below(price=100, strike=105, iv=0.35, dte=20)
    assert above is not None and below is not None
    assert abs((above + below) - 1.0) < 1e-9


def test_probability_above_decreases_as_strike_rises():
    near = module.probability_above(price=100, strike=101, iv=0.3, dte=30)
    far = module.probability_above(price=100, strike=150, iv=0.3, dte=30)
    assert near > far


def test_select_expiration_prefers_nearest_to_target_within_window():
    from datetime import date
    expirations = ["2024-03-02", "2024-03-15", "2024-04-20", "2024-03-25"]
    expiration, dte = module.select_expiration(expirations, min_dte=2, max_dte=45, target_dte=14,
                                               as_of=date(2024, 3, 1))
    assert expiration == "2024-03-15"
    assert dte == 14


def test_contract_liquidity_rejects_illiquid_or_wide_spread_rows():
    liquid = contract(strike=100, bid=2.0, ask=2.1, open_interest=500)
    illiquid = contract(strike=100, bid=2.0, ask=2.1, open_interest=5)
    wide_spread = contract(strike=100, bid=1.0, ask=1.8, open_interest=500)
    assert module.contract_liquidity(liquid, price=100) is not None
    assert module.contract_liquidity(illiquid, price=100) is None
    assert module.contract_liquidity(wide_spread, price=100) is None


def test_liquidity_factor_rewards_open_interest_and_penalizes_spread():
    tight = module.contract_liquidity(contract(strike=100, bid=2.0, ask=2.05, open_interest=1000), price=100)
    wide = module.contract_liquidity(contract(strike=100, bid=2.0, ask=2.09, open_interest=1000), price=100)
    thin = module.contract_liquidity(contract(strike=100, bid=2.0, ask=2.05, open_interest=60), price=100)
    assert module.liquidity_factor(tight) > module.liquidity_factor(wide)
    assert module.liquidity_factor(tight) > module.liquidity_factor(thin)
    assert module.liquidity_factor(None) is None


def test_select_by_target_delta_picks_contract_nearest_target():
    frame = FakeFrame([
        contract(strike=100, bid=4.0, ask=4.2, iv=0.35),    # ~ATM, delta near .5-.6
        contract(strike=110, bid=1.2, ask=1.26, iv=0.32),   # further OTM, lower delta
        contract(strike=120, bid=0.3, ask=0.4, iv=0.30),    # far OTM, low delta
    ])
    best = module.select_by_target_delta(frame, price=100, dte=30, side="call", target_delta=0.30)
    assert best is not None
    assert best["strike"] == 110


def test_select_by_target_delta_respects_moneyness_bounds():
    frame = FakeFrame([contract(strike=200, bid=0.05, ask=0.08, iv=0.9)])  # 100% OTM, outside default ceiling
    best = module.select_by_target_delta(frame, price=100, dte=30, side="call", target_delta=0.30)
    assert best is None


def test_select_by_target_moneyness_picks_nearest_signed_target():
    puts = FakeFrame([contract(strike=90, bid=1.0, ask=1.1), contract(strike=93, bid=1.55, ask=1.60),
                      contract(strike=95, bid=2.0, ask=2.1)])
    best = module.select_by_target_moneyness(puts, price=100, target_moneyness=-0.075)
    assert best["strike"] == 93.0


def test_select_by_target_moneyness_returns_none_outside_tolerance():
    puts = FakeFrame([contract(strike=50, bid=0.1, ask=0.15)])  # 50% OTM, way outside tolerance
    assert module.select_by_target_moneyness(puts, price=100, target_moneyness=-0.075) is None


def test_snapshot_staleness_discount_is_full_for_a_same_day_snapshot():
    assert module.snapshot_staleness_discount(datetime(2024, 3, 10, 9, tzinfo=timezone.utc).isoformat(), TODAY) == 1.0


def test_snapshot_staleness_discount_decays_linearly():
    # 2 days old, RESEARCH_SNAPSHOT_MAX_AGE_DAYS=5 -> 1 - 2/5 = 0.6
    assert module.snapshot_staleness_discount(datetime(2024, 3, 8, tzinfo=timezone.utc).isoformat(), TODAY) == 0.6


def test_snapshot_staleness_discount_floors_at_zero_past_the_max_age():
    assert module.snapshot_staleness_discount(datetime(2024, 2, 1, tzinfo=timezone.utc).isoformat(), TODAY) == 0.0


def test_snapshot_staleness_discount_none_for_missing_or_unparseable_generated_at():
    assert module.snapshot_staleness_discount(None, TODAY) is None
    assert module.snapshot_staleness_discount("not-a-date", TODAY) is None


def test_snapshot_staleness_discount_full_for_a_future_dated_snapshot():
    # Clock skew between machines shouldn't make a same-run snapshot read as stale.
    assert module.snapshot_staleness_discount(datetime(2024, 3, 11, tzinfo=timezone.utc).isoformat(), TODAY) == 1.0


def test_research_universe_factors_signed_mode_rewards_agreeing_sentiment():
    entry = {"score": 70, "data_coverage": 0.8,
            "sentiment_detail": {"average": 0.5, "coverage": 0.6, "article_count": 4}}
    bullish = module.research_universe_factors(entry, None, TODAY, direction=1, sentiment_mode="signed")
    bearish = module.research_universe_factors(entry, None, TODAY, direction=-1, sentiment_mode="signed")
    assert bullish["news_sentiment"] == 0.5 * 0.6
    assert bearish["news_sentiment"] == -0.5 * 0.6
    assert bullish["research_confidence"] == (70 - 50) * 0.8
    assert bearish["research_confidence"] == -(70 - 50) * 0.8


def test_research_universe_factors_inverse_mode_flips_sentiment_sign_only():
    entry = {"score": 40, "data_coverage": 0.5,
            "sentiment_detail": {"average": 0.4, "coverage": 0.5, "article_count": 3}}
    result = module.research_universe_factors(entry, None, TODAY, direction=1, sentiment_mode="inverse")
    assert result["news_sentiment"] == -0.4 * 0.5
    assert result["research_confidence"] == (40 - 50) * 0.5


def test_research_universe_factors_calm_mode_ignores_sign_and_direction():
    entry = {"sentiment_detail": {"average": -0.7, "coverage": 0.9, "article_count": 5}}
    positive_average = {"sentiment_detail": {"average": 0.7, "coverage": 0.9, "article_count": 5}}
    negative = module.research_universe_factors(entry, None, TODAY, sentiment_mode="calm")
    positive = module.research_universe_factors(positive_average, None, TODAY, sentiment_mode="calm")
    assert negative["news_sentiment"] == positive["news_sentiment"] == -0.7 * 0.9


def test_research_universe_factors_attention_mode_uses_coverage_regardless_of_polarity():
    entry = {"sentiment_detail": {"average": -0.9, "coverage": 0.4, "article_count": 6}}
    result = module.research_universe_factors(entry, None, TODAY, sentiment_mode="attention")
    assert result["news_sentiment"] == 0.4


def test_research_universe_factors_zero_articles_is_none_not_neutral():
    entry = {"sentiment_detail": {"average": 0.0, "coverage": 0.0, "article_count": 0}}
    result = module.research_universe_factors(entry, None, TODAY, sentiment_mode="signed")
    assert result["news_sentiment"] is None


def test_research_universe_factors_missing_sentiment_detail_is_none():
    result = module.research_universe_factors({}, None, TODAY, sentiment_mode="signed")
    assert result["news_sentiment"] is None
    assert result["research_confidence"] is None


def test_research_universe_factors_missing_score_or_confidence_is_none():
    only_score = module.research_universe_factors({"score": 60}, None, TODAY)
    only_confidence = module.research_universe_factors({"data_coverage": 0.5}, None, TODAY)
    assert only_score["research_confidence"] is None
    assert only_confidence["research_confidence"] is None


def test_transaction_cost_pct_charges_a_quarter_spread_plus_flat_fee():
    contract_row = {"spread_pct": 0.04, "mid": 2.0}
    # quarter-spread per share = 0.04 * 2.0 / 4 = 0.02; fee per share = 0.65 / 100 = 0.0065
    cost = module.transaction_cost_pct(contract_row, price_basis=100)
    assert abs(cost - (0.02 + 0.0065) / 100) < 1e-9


def test_transaction_cost_pct_zero_without_contract_or_price():
    assert module.transaction_cost_pct(None, 100) == 0.0
    assert module.transaction_cost_pct({"spread_pct": 0.04, "mid": 2.0}, 0) == 0.0


def test_expected_value_pct_weights_outcomes_by_probability_net_of_cost():
    ev = module.expected_value_pct(probability_favorable=0.7, favorable_return_pct=0.05,
                                    unfavorable_return_pct=-0.20, cost_pct=0.01)
    assert abs(ev - (0.7 * 0.05 + 0.3 * -0.20 - 0.01)) < 1e-9


def test_expected_value_pct_none_when_probability_unknown():
    assert module.expected_value_pct(None, 0.05, -0.20) is None
    assert module.expected_value_pct(0.5, None, -0.20) is None


def test_kelly_fraction_positive_for_a_genuine_edge():
    fraction = module.kelly_fraction(probability_favorable=0.7, favorable_return_pct=0.10,
                                      unfavorable_return_pct=-0.05)
    assert fraction is not None and fraction > 0


def test_kelly_fraction_none_when_inputs_missing_or_no_variance():
    assert module.kelly_fraction(None, 0.1, -0.05) is None
    assert module.kelly_fraction(0.7, 0.1, 0.1) is None  # identical outcomes -> no variance


def test_suggested_position_pct_is_quarter_kelly_capped_at_two_percent():
    # A very large edge should still be capped, not scaled up without bound.
    capped = module.suggested_position_pct(probability_favorable=0.95, favorable_return_pct=1.0,
                                           unfavorable_return_pct=-0.5)
    assert capped == 0.02


def test_suggested_position_pct_scales_down_a_modest_edge():
    modest = module.suggested_position_pct(probability_favorable=0.51, favorable_return_pct=0.5,
                                           unfavorable_return_pct=-0.5)
    full = module.kelly_fraction(0.51, 0.5, -0.5)
    assert modest == max(0.0, min(full * 0.25, 0.02))
    assert modest < 0.02


def test_suggested_position_pct_never_negative_for_a_losing_bet():
    result = module.suggested_position_pct(probability_favorable=0.2, favorable_return_pct=0.05,
                                           unfavorable_return_pct=-0.20)
    assert result == 0.0


def test_suggested_position_pct_none_when_kelly_fraction_is_none():
    assert module.suggested_position_pct(None, 0.05, -0.05) is None


class DirectCache:
    """Bypasses disk persistence entirely so earnings-calendar tests stay hermetic."""

    def fetch(self, namespace, key, producer, source=None):
        return producer()


class FakeColumn:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class FakeEarningsFrame:
    def __init__(self, rows):
        # rows: list of (date_str, surprise_value_or_nan)
        self.index = [row[0] for row in rows]
        self.columns = ["Surprise(%)"]
        self.empty = not rows
        self._surprises = [row[1] for row in rows]

    def __getitem__(self, column):
        return FakeColumn(self._surprises)


class FakeEarningsTicker:
    def __init__(self, frame=None, raise_on_access=False):
        self._frame = frame
        self._raise_on_access = raise_on_access

    @property
    def earnings_dates(self):
        if self._raise_on_access:
            raise RuntimeError("boom")
        return self._frame


NAN = float("nan")


def test_next_earnings_date_returns_nearest_unreported_row_on_or_after_as_of():
    ticker = FakeEarningsTicker(FakeEarningsFrame([
        ("2024-02-15", 3.2),   # reported quarter, excluded
        ("2024-05-10", NAN),   # upcoming
        ("2024-08-09", NAN),   # further upcoming
    ]))
    result = module.next_earnings_date(ticker, "AAA", as_of=TODAY, cache=DirectCache())
    assert result == date(2024, 5, 10)


def test_next_earnings_date_ignores_upcoming_rows_before_as_of():
    ticker = FakeEarningsTicker(FakeEarningsFrame([("2024-01-01", NAN)]))
    assert module.next_earnings_date(ticker, "AAA", as_of=TODAY, cache=DirectCache()) is None


def test_next_earnings_date_none_when_frame_missing_or_empty():
    assert module.next_earnings_date(FakeEarningsTicker(None), "AAA", as_of=TODAY, cache=DirectCache()) is None
    assert module.next_earnings_date(FakeEarningsTicker(FakeEarningsFrame([])), "AAA", as_of=TODAY,
                                     cache=DirectCache()) is None


def test_next_earnings_date_none_when_calendar_raises():
    ticker = FakeEarningsTicker(raise_on_access=True)
    assert module.next_earnings_date(ticker, "AAA", as_of=TODAY, cache=DirectCache()) is None


def test_expiration_spans_earnings_true_only_strictly_between_as_of_and_expiration():
    assert module.expiration_spans_earnings("2024-03-15", date(2024, 3, 12), TODAY) is True
    assert module.expiration_spans_earnings("2024-03-15", date(2024, 3, 15), TODAY) is True  # on expiration day
    assert module.expiration_spans_earnings("2024-03-15", date(2024, 3, 16), TODAY) is False  # after expiration
    assert module.expiration_spans_earnings("2024-03-15", TODAY, TODAY) is False  # on as_of itself, already past
    assert module.expiration_spans_earnings("2024-03-15", None, TODAY) is False
    assert module.expiration_spans_earnings(None, date(2024, 3, 10), TODAY) is False


def test_research_universe_factors_applies_staleness_discount():
    entry = {"score": 80, "data_coverage": 1.0,
            "sentiment_detail": {"average": 1.0, "coverage": 1.0, "article_count": 10}}
    stale_generated_at = datetime(2024, 3, 8, tzinfo=timezone.utc).isoformat()  # 2 days old -> 0.6 discount
    result = module.research_universe_factors(entry, stale_generated_at, TODAY, direction=1, sentiment_mode="signed")
    assert result["news_sentiment"] == 1.0 * 1.0 * 0.6
    assert result["research_confidence"] == (80 - 50) * 1.0 * 0.6

    fully_stale = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
    zeroed = module.research_universe_factors(entry, fully_stale, TODAY, direction=1, sentiment_mode="signed")
    assert zeroed["news_sentiment"] == 0.0
    assert zeroed["research_confidence"] == 0.0
