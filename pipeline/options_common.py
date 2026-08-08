"""Shared option-chain math and selection helpers for the options strategy screens.

Every build_*_screen.py script pulls the same kind of Yahoo option-chain data through a
different lens (directional bet, income sale, hedge, spread, range-bound credit, ...).
This module holds the parts that don't change across that lens: expiration selection
inside a days-to-expiration window, realized volatility/trend from price history, and a
plain Black-Scholes delta / probability-of-finishing-above-strike approximation.

The Black-Scholes helpers hold the risk-free rate at 0 by default. That's a real
simplification - Fidelity's own margin-cost discussion of ~10% APR makes clear the
riskfree/borrow rate is not actually zero - but this pipeline has no live risk-free
rate series wired in (unlike fred.py's macro factors, which aren't per-option-chain
inputs), and for the short (2-45 day) windows these screens use, r=0 changes the
resulting probabilities by a fraction of a percentage point. Treat every probability
here as a rough, stated-assumption estimate, not a quote-derived one.
"""

import math
import statistics
from datetime import date, datetime

ATM_TOLERANCE = 0.10
MINIMUM_OPEN_INTEREST = 50
MAXIMUM_SPREAD_PCT = 0.35
MINIMUM_HISTORY_SESSIONS = 21
MINIMUM_PRICE = 5
MINIMUM_MARKET_CAP = 300_000_000


def realized_volatility_20d(closes):
    if len(closes) < 21 or any(value <= 0 for value in closes[-21:]):
        return None
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
    return statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None


def trend_20d(closes):
    if len(closes) < 21 or closes[-21] <= 0:
        return None
    return closes[-1] / closes[-21] - 1


def days_to_expiration(expiration, as_of=None):
    as_of = as_of or date.today()
    try:
        expiration_date = datetime.strptime(expiration, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (expiration_date - as_of).days


def select_expiration(expirations, min_dte=2, max_dte=45, target_dte=14, as_of=None):
    """Nearest expiration to target_dte inside [min_dte, max_dte]."""
    candidates = []
    for expiration in expirations or []:
        dte = days_to_expiration(expiration, as_of)
        if dte is not None and min_dte <= dte <= max_dte:
            candidates.append((abs(dte - target_dte), expiration, dte))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0])
    _, expiration, dte = candidates[0]
    return expiration, dte


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_d1_d2(price, strike, iv, dte, r=0.0):
    """Black-Scholes d1/d2, or (None, None) if any input makes them undefined."""
    if not price or not strike or not iv or iv <= 0 or not dte or dte <= 0:
        return None, None
    t = dte / 365
    d1 = (math.log(price / strike) + (r + iv ** 2 / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    return d1, d2


def call_delta(price, strike, iv, dte, r=0.0):
    d1, _ = bs_d1_d2(price, strike, iv, dte, r)
    return None if d1 is None else normal_cdf(d1)


def put_delta(price, strike, iv, dte, r=0.0):
    d1, _ = bs_d1_d2(price, strike, iv, dte, r)
    return None if d1 is None else normal_cdf(d1) - 1


def probability_above(price, strike, iv, dte, r=0.0):
    """Risk-neutral probability the stock finishes above `strike` at expiration."""
    _, d2 = bs_d1_d2(price, strike, iv, dte, r)
    return None if d2 is None else normal_cdf(d2)


def probability_below(price, strike, iv, dte, r=0.0):
    above = probability_above(price, strike, iv, dte, r)
    return None if above is None else 1 - above


def contract_liquidity(contract, price):
    """Bid/ask/OI/spread fields for one contract row, or None if it fails basic gates."""
    strike = contract.get("strike")
    bid, ask = contract.get("bid"), contract.get("ask")
    open_interest = contract.get("openInterest") or 0
    if not strike or not price:
        return None
    if not bid or not ask or bid <= 0 or ask <= 0 or ask < bid:
        return None
    if open_interest < MINIMUM_OPEN_INTEREST:
        return None
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / mid if mid else None
    if spread_pct is None or spread_pct > MAXIMUM_SPREAD_PCT:
        return None
    implied_volatility = contract.get("impliedVolatility")
    return {
        "strike": float(strike), "bid": float(bid), "ask": float(ask), "mid": round(mid, 4),
        "spread_pct": round(spread_pct, 4),
        "implied_volatility": float(implied_volatility) if implied_volatility else None,
        "open_interest": int(open_interest), "volume": int(contract.get("volume") or 0),
        "moneyness": round(strike / price - 1, 4),
    }


def select_contract(frame, price):
    """Tightest-spread near-the-money contract among adequately liquid rows."""
    best = None
    for _, contract in frame.iterrows():
        candidate = contract_liquidity(contract, price)
        if candidate is None or abs(candidate["moneyness"]) > ATM_TOLERANCE:
            continue
        if best is None or candidate["spread_pct"] < best["spread_pct"]:
            best = candidate
    return best


def liquidity_factor(contract):
    """Higher is better: rewards open interest, penalizes a wide bid/ask spread."""
    if not contract:
        return None
    return math.log10(max(contract.get("open_interest") or 1, 1)) - (contract.get("spread_pct") or 0)


def select_by_target_moneyness(frame, price, target_moneyness, tolerance=0.03):
    """Liquid contract whose signed moneyness (strike/price - 1) is nearest the target.

    Signed, so a put 7.5% below spot is target_moneyness=-0.075 - the same convention
    contract_liquidity() already uses, which is what lets this work on either a calls or
    a puts frame without a side argument.
    """
    best = None
    for _, contract in frame.iterrows():
        candidate = contract_liquidity(contract, price)
        if candidate is None or abs(candidate["moneyness"] - target_moneyness) > tolerance:
            continue
        distance = abs(candidate["moneyness"] - target_moneyness)
        if best is None or distance < best[0]:
            best = (distance, candidate)
    return best[1] if best else None


def select_by_target_delta(frame, price, dte, side, target_delta, moneyness_floor=0.0, moneyness_ceiling=0.35):
    """Liquid contract whose Black-Scholes delta is nearest target_delta.

    moneyness_floor/ceiling bound how far out-of-the-money a candidate may sit (as a
    fraction of spot) - keeps the delta search from wandering into illiquid deep-OTM or
    near-worthless strikes that happen to produce a delta near the target by IV noise.
    """
    best = None
    for _, contract in frame.iterrows():
        candidate = contract_liquidity(contract, price)
        if candidate is None or candidate["implied_volatility"] is None:
            continue
        moneyness = candidate["moneyness"] if side == "call" else -candidate["moneyness"]
        if not (moneyness_floor <= moneyness <= moneyness_ceiling):
            continue
        delta_fn = call_delta if side == "call" else put_delta
        delta = delta_fn(price, candidate["strike"], candidate["implied_volatility"], dte)
        if delta is None:
            continue
        candidate["delta"] = round(delta, 4)
        distance = abs(abs(delta) - target_delta)
        if best is None or distance < best[0]:
            best = (distance, candidate)
    return best[1] if best else None
