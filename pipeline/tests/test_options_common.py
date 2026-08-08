import options_common as module


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def contract(strike, bid, ask, open_interest=200, iv=0.4, volume=10):
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
    wide = module.contract_liquidity(contract(strike=100, bid=2.0, ask=2.3, open_interest=1000), price=100)
    thin = module.contract_liquidity(contract(strike=100, bid=2.0, ask=2.05, open_interest=60), price=100)
    assert module.liquidity_factor(tight) > module.liquidity_factor(wide)
    assert module.liquidity_factor(tight) > module.liquidity_factor(thin)
    assert module.liquidity_factor(None) is None


def test_select_by_target_delta_picks_contract_nearest_target():
    frame = FakeFrame([
        contract(strike=100, bid=4.0, ask=4.2, iv=0.35),   # ~ATM, delta near .5-.6
        contract(strike=110, bid=1.2, ask=1.4, iv=0.32),   # further OTM, lower delta
        contract(strike=120, bid=0.3, ask=0.4, iv=0.30),   # far OTM, low delta
    ])
    best = module.select_by_target_delta(frame, price=100, dte=30, side="call", target_delta=0.30)
    assert best is not None
    assert best["strike"] == 110


def test_select_by_target_delta_respects_moneyness_bounds():
    frame = FakeFrame([contract(strike=200, bid=0.05, ask=0.08, iv=0.9)])  # 100% OTM, outside default ceiling
    best = module.select_by_target_delta(frame, price=100, dte=30, side="call", target_delta=0.30)
    assert best is None


def test_select_by_target_moneyness_picks_nearest_signed_target():
    puts = FakeFrame([contract(strike=90, bid=1.0, ask=1.1), contract(strike=93, bid=1.5, ask=1.6),
                      contract(strike=95, bid=2.0, ask=2.1)])
    best = module.select_by_target_moneyness(puts, price=100, target_moneyness=-0.075)
    assert best["strike"] == 93.0


def test_select_by_target_moneyness_returns_none_outside_tolerance():
    puts = FakeFrame([contract(strike=50, bid=0.1, ask=0.15)])  # 50% OTM, way outside tolerance
    assert module.select_by_target_moneyness(puts, price=100, target_moneyness=-0.075) is None
