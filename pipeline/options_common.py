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
# Was 0.35 (35%). A retail evidence review (see docs on this pipeline's options screens)
# found open-interest-only gating leaves contracts with wide double-digit spreads through,
# and that realistic effective spreads are what actually erode published options-strategy
# edges (Muravyev & Pearson 2020). Tightened to the review's own recommended ceiling and
# paired with MINIMUM_VOLUME below, since open interest alone measures accumulated
# positions, not current two-sided depth - a contract can carry heavy OI and still show no
# size at the mid.
MAXIMUM_SPREAD_PCT = 0.05
MAXIMUM_ABSOLUTE_SPREAD = 0.10  # dollars - see contract_liquidity's use for why this exists
MINIMUM_VOLUME = 100
MINIMUM_HISTORY_SESSIONS = 21
MINIMUM_PRICE = 5
MINIMUM_MARKET_CAP = 300_000_000
RESEARCH_SNAPSHOT_MAX_AGE_DAYS = 5
CONTRACT_FEE = 0.65  # dollars per contract - matches Fidelity's disclosed per-contract options fee
# Floor for realized_vol_percentile: never rank today's vol against a handful of rolling
# observations and call the result a percentile - see that function's docstring.
MINIMUM_VOL_PERCENTILE_SAMPLES = 60


def realized_volatility_20d(closes):
    if len(closes) < 21 or any(value <= 0 for value in closes[-21:]):
        return None
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
    return statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None


def realized_vol_percentile(closes, lookback=252, window=20):
    """Where today's rolling `window`-session realized vol sits (0-100) among its own
    trailing `lookback`-session distribution - the "volatility cone" percentile technique,
    applied to REALIZED (not implied) volatility.

    This is deliberately NOT an IV rank. A real IV rank - (current IV - 52wk low) / (52wk
    high - 52wk low) - needs a persisted year of implied-volatility history per ticker,
    which this pipeline doesn't collect: option chains are fetched fresh and unstored on
    every run (see MODULE docstring). Building that collector is infrastructure on the
    scale of the PIT store (see research/STATE.md), not a screen tweak. This function is
    the honest substitute available from data already fetched - the ticker's own price
    history - and every caller must publish it as `realized_volatility_percentile`, never
    relabel it `iv_rank`.

    Requires at least MINIMUM_VOL_PERCENTILE_SAMPLES rolling observations or returns None -
    a name with a short trading history (recent IPO/spin-off) gets no fabricated percentile
    off a handful of points.
    """
    if len(closes) < window + 1:
        return None
    series = []
    for end in range(window + 1, len(closes) + 1):
        window_closes = closes[end - window - 1:end]
        if any(value <= 0 for value in window_closes):
            continue
        returns = [math.log(window_closes[index] / window_closes[index - 1]) for index in range(1, len(window_closes))]
        if len(returns) > 1:
            series.append(statistics.stdev(returns) * math.sqrt(252))
    series = series[-lookback:]  # most recent `lookback` rolling observations only
    if len(series) < MINIMUM_VOL_PERCENTILE_SAMPLES:
        return None
    current = series[-1]
    return round(100 * sum(1 for value in series if value <= current) / len(series), 2)


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


def option_gamma(price, strike, iv, dte, r=0.0):
    """Black-Scholes gamma - identical for a call and a put at the same strike/expiration,
    which is what makes summing it across a whole chain (see single_expiration_gex below)
    meaningful regardless of which side a given open-interest figure sits on.
    """
    d1, _ = bs_d1_d2(price, strike, iv, dte, r)
    if d1 is None:
        return None
    t = dte / 365
    return math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) / (price * iv * math.sqrt(t))


def probability_above(price, strike, iv, dte, r=0.0):
    """Risk-neutral probability the stock finishes above `strike` at expiration."""
    _, d2 = bs_d1_d2(price, strike, iv, dte, r)
    return None if d2 is None else normal_cdf(d2)


def call_price(price, strike, iv, dte, r=0.0):
    """Black-Scholes theoretical call price. Used to price backtests, never a live quote."""
    d1, d2 = bs_d1_d2(price, strike, iv, dte, r)
    if d1 is None:
        return None
    t = dte / 365
    return price * normal_cdf(d1) - strike * math.exp(-r * t) * normal_cdf(d2)


def put_price(price, strike, iv, dte, r=0.0):
    """Black-Scholes theoretical put price. Used to price backtests, never a live quote."""
    d1, d2 = bs_d1_d2(price, strike, iv, dte, r)
    if d1 is None:
        return None
    t = dte / 365
    return strike * math.exp(-r * t) * normal_cdf(-d2) - price * normal_cdf(-d1)


def probability_below(price, strike, iv, dte, r=0.0):
    above = probability_above(price, strike, iv, dte, r)
    return None if above is None else 1 - above


def _finite(value, default=None):
    """``value`` as a float, or ``default`` when it is missing or not a real number.

    Yahoo returns NaN rather than a null for an option field it has no value for, and NaN
    poisons every gate below by silently answering False to all of them: ``NaN < MINIMUM``
    is False, so a row with no open interest at all passes the liquidity floor, and the
    ``int(NaN)`` at the end then raises and takes down the whole screen build. Coercing to
    a real number here is what lets the gates reject the row instead.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def contract_liquidity(contract, price):
    """Bid/ask/OI/spread/volume fields for one contract row, or None if it fails basic gates.

    Open interest alone measures accumulated positions, not current two-sided depth, so
    MINIMUM_VOLUME is gated separately and on top of it - a contract can carry heavy OI and
    still show no fills today.
    """
    strike = _finite(contract.get("strike"))
    bid, ask = _finite(contract.get("bid")), _finite(contract.get("ask"))
    price = _finite(price)
    # A missing count is genuinely zero contracts, so it fails the floors below rather than
    # being treated as unknown-and-therefore-acceptable.
    open_interest = _finite(contract.get("openInterest"), 0)
    volume = _finite(contract.get("volume"), 0)
    if not strike or not price:
        return None
    if not bid or not ask or bid <= 0 or ask <= 0 or ask < bid:
        return None
    if open_interest < MINIMUM_OPEN_INTEREST or volume < MINIMUM_VOLUME:
        return None
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / mid if mid else None
    if spread_pct is None:
        return None
    # A far-OTM/cheap contract's relative spread is inflated by the minimum tick size
    # regardless of how "liquid" it really is - a one-cent-wide $0.02 spread on a $0.15
    # contract prices out at 13%+ relative, but it's a trivial two-dollar-per-contract
    # cost. Gate on whichever bound the contract actually clears: the percentage ceiling
    # for contracts where relative cost is the real risk, or the absolute-dollar ceiling
    # for cheap legs where a percentage figure overstates the real execution cost.
    if spread_pct > MAXIMUM_SPREAD_PCT and (ask - bid) > MAXIMUM_ABSOLUTE_SPREAD:
        return None
    implied_volatility = _finite(contract.get("impliedVolatility"))
    # Fill assumption for anything downstream that prices an entry off this contract: mid
    # plus a quarter of the spread, not mid itself - a screen is not a fill guarantee, and
    # modeling perfect mid execution is exactly the optimism the transaction-cost review
    # flagged. fill_price is the buyer's side (ask-leaning); a seller nets mid minus the
    # same quarter-spread, i.e. 2*mid - fill_price.
    fill_price = mid + spread_pct * mid / 4
    return {
        "strike": float(strike), "bid": float(bid), "ask": float(ask), "mid": round(mid, 4),
        "spread_pct": round(spread_pct, 4), "fill_price": round(fill_price, 4),
        "implied_volatility": implied_volatility if implied_volatility else None,
        "open_interest": int(open_interest), "volume": int(volume),
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


def atm_iv(calls, puts, price):
    """Mean of the near-the-money call's and put's implied vol - a direction-neutral "ATM
    IV" reading for a chain, independent of whichever side a screen's own directional pick
    lands on. Same averaging build_advanced_options_screen.build_straddle_row already does
    inline; factored out so the daily iv_archive writer (build_options_strategies.py) and
    the straddle screen share one definition. None if neither leg has a usable IV.
    """
    call = select_contract(calls, price)
    put = select_contract(puts, price)
    values = [c["implied_volatility"] for c in (call, put) if c and c["implied_volatility"] is not None]
    return statistics.mean(values) if values else None


def single_expiration_gex(calls, puts, price, dte, r=0.0):
    """Net dealer gamma exposure for ONE expiration's chain, in dollars of underlying a
    delta-hedging dealer must trade per 1% move (gamma x open interest x 100-share
    multiplier x spot^2 x 0.01), calls positive and puts negative.

    Two honest simplifications, both stated here rather than left implicit:

    1. Sign convention. Positive/calls, negative/puts is the "naive" dealer-inventory
       assumption (dealers end up net long the calls and net short the puts retail
       customers buy) that a 2026 SSRN paper ("Sign of Dealer Gamma") formalized as
       exactly that - an assumption, not an observed fact. Real market-making desks carry
       inventory this pipeline has no visibility into; this is the same convention
       SqueezeMetrics' 2016 GEX methodology popularized, not a claim that it is always
       correct.
    2. Single expiration, not the full term structure. Vendor GEX products (SpotGamma,
       SqueezeMetrics) sum across every listed expiration for a ticker. This pipeline only
       ever fetches ONE expiration's chain per screen, so this is a proxy for that one
       expiration's contribution, not the ticker's aggregate net gamma - a screen with a
       7-day window and one with a 30-day window will read different numbers for the same
       ticker on the same day, and that's expected, not a bug.

    Sums across the FULL chain (every strike with usable IV and open interest), not just
    the near-the-money contracts the rest of this module selects from - real dealer gamma
    comes from accumulated positioning at every strike, not only the liquid ones. None if
    `price`/`dte` themselves are unusable; a chain with no usable contracts on either side
    returns 0.0, not None (a real, if boring, dealer-gamma reading of "no measurable
    exposure found").
    """
    if not price or not dte or dte <= 0:
        return None

    def side_notional(frame, sign):
        total = 0.0
        for _, contract in frame.iterrows():
            iv = _finite(contract.get("impliedVolatility"))
            open_interest = _finite(contract.get("openInterest"), 0)
            strike = _finite(contract.get("strike"))
            if not iv or iv <= 0 or open_interest <= 0 or not strike:
                continue
            gamma = option_gamma(price, strike, iv, dte, r)
            if gamma is None:
                continue
            total += sign * gamma * open_interest * 100 * price ** 2 * 0.01
        return total

    return round(side_notional(calls, 1) + side_notional(puts, -1))


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


def iv_skew(calls, puts, price, dte, target_delta=0.25):
    """Put IV minus call IV at matched ~target_delta wings, from the option chain a caller
    already has in scope (no extra network call). Positive means the put is priced richer
    than the call - the reverse-skew pattern equities have carried since the 1987 crash,
    read as persistent hedging demand rather than a symmetric view on up/down moves.
    Skew flattening toward multi-year lows has preceded volatility spikes (e.g. late
    January 2018, ahead of the Feb 5 2018 VIX explosion) - informational context here, not
    a scoring input, since a single-day reading says nothing about whether it's flattening
    or steepening. None if either wing can't be found with adequate liquidity.
    """
    put = select_by_target_delta(puts, price, dte, side="put", target_delta=target_delta)
    call = select_by_target_delta(calls, price, dte, side="call", target_delta=target_delta)
    if put is None or call is None or put["implied_volatility"] is None or call["implied_volatility"] is None:
        return None
    return round(put["implied_volatility"] - call["implied_volatility"], 4)


def put_call_oi_ratio(calls, puts):
    """Total put open interest / total call open interest across the full chain frames at
    the selected expiration - context only, never a scoring factor. The literature this
    pipeline draws on (Wall Street Courier/Koch, CBOE equity P/C 2007-2022) treats the raw
    ratio as a weak, contrarian signal that only means anything at its own historical
    extremes, not something with an established edge to rank candidates by; a single day's
    reading here has no such history to compare against. None if there's no call open
    interest to divide by.
    """
    def total_open_interest(frame):
        return sum(_finite(contract.get("openInterest"), 0) for _, contract in frame.iterrows())

    call_oi = total_open_interest(calls)
    if call_oi <= 0:
        return None
    return round(total_open_interest(puts) / call_oi, 4)


def snapshot_staleness_discount(generated_at, as_of=None):
    """1.0 for an advisor.json snapshot published today, decaying linearly to 0.0 by
    RESEARCH_SNAPSHOT_MAX_AGE_DAYS. None if `generated_at` is missing/unparseable.

    The research-universe score/confidence and news-sentiment factors below come from
    advisor.json, a separately-scheduled publish - not the live option-chain fetch these
    screens otherwise use. A screen run against a days-old snapshot should trust that
    snapshot's tilt less, not treat it as equally fresh as one run minutes after
    advisor.json republished. Day-granularity (not an hourly half-life) deliberately
    matches the precision `as_of` already carries everywhere else in this module - a date,
    not a datetime.
    """
    if not generated_at:
        return None
    try:
        published = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None
    today = as_of or date.today()
    age_days = (today - published).days
    if age_days < 0:
        return 1.0
    return max(0.0, 1 - age_days / RESEARCH_SNAPSHOT_MAX_AGE_DAYS)


def next_earnings_date(ticker_obj, symbol, as_of=None, cache=None):
    """Nearest known upcoming earnings date for `symbol`, or None if unavailable/none known.

    Selling into (or buying) an expiration that spans an earnings date is a mechanical
    trap, not an edge: implied volatility inflates ahead of the print and collapses after
    ("IV crush"), so anything ranked by raw premium/annualized yield gravitates straight to
    event-contaminated contracts. Every screen in this pipeline hard-excludes a candidate
    whose chosen expiration spans a known earnings date rather than trying to price the
    event component in - see expiration_spans_earnings().

    Reuses yfinance's `earnings_dates` frame - the same endpoint
    fundamentals_extended.earnings_surprise_rows() already reads - but keeps the opposite
    subset: that function keeps only reported quarters (a real surprise value); this keeps
    only not-yet-reported ones (NaN surprise), since a future row in that scraped calendar
    is what a blackout gate needs. yfinance exposes no "confirmed vs. estimated" flag the
    way institutional calendar providers (Wall Street Horizon, FactSet) do, so every date
    returned here is treated as if confirmed - the conservative reading for a screen that
    is trying to AVOID the event, not trade it (unconfirmed dates should still blackout).

    Cached on disk (7-day TTL via the "statements" namespace, same policy as the sibling
    earnings-surprise fetch) so that when more than one options screen runs against the
    same ticker on the same day, only the first pays for the network request.
    """
    from cache import CACHE as _default_cache
    cache = cache or _default_cache
    as_of = as_of or date.today()

    def produce():
        try:
            frame = ticker_obj.earnings_dates
        except Exception:  # noqa: BLE001 - a missing/broken calendar must not sink the ticker
            return None
        if frame is None or getattr(frame, "empty", True):
            return None
        column = next((name for name in frame.columns if "surprise" in str(name).lower()), None)
        if column is None:
            return None
        upcoming = []
        for index, value in zip(frame.index, frame[column].tolist()):
            try:
                reported = float(value) == float(value)  # not NaN
            except (TypeError, ValueError):
                reported = False
            if reported:
                continue
            try:
                upcoming.append(datetime.strptime(str(index)[:10], "%Y-%m-%d").date().isoformat())
            except ValueError:
                continue
        return min(upcoming) if upcoming else None

    try:
        value = cache.fetch("statements", f"earnings_calendar:{symbol}", produce, source="yahoo")
    except Exception:  # noqa: BLE001 - same non-fatal contract as every other per-ticker lookup here
        return None
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= as_of else None


def expiration_spans_earnings(expiration, earnings_date, as_of=None):
    """True if a contract entered at `as_of` and held to `expiration` would sit through
    `earnings_date` - i.e. as_of < earnings_date <= expiration."""
    if earnings_date is None or not expiration:
        return False
    as_of = as_of or date.today()
    try:
        expiration_date = datetime.strptime(expiration, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return as_of < earnings_date <= expiration_date


# On NOT implementing Dubinsky/Johannes/Kaeck/Seeger-style earnings-jump-vol decomposition:
#
# A rigorous treatment of an event-spanning expiration would decompose its total implied
# variance into a diffusive component and an earnings-jump component (DJKS 2019, "Option
# Pricing of Earnings Announcement Risk"), calibrated by differencing two expirations that
# bracket the event. That is the right tool if this pipeline wanted to KEEP event-spanning
# contracts and price the event component explicitly - e.g. a dedicated earnings-play
# screen ranking straddles by how cheap the jump component is relative to the historical
# earnings-day move.
#
# This pipeline doesn't have that screen. Every current screen either isn't meant to be a
# catalyst-timed trade (the Advanced-strategies straddle explicitly says so in its own
# module docstring) or is an income/directional idea for which an earnings-inflated premium
# is a distortion to avoid, not a component to price. Given that, expiration_spans_earnings'
# hard exclusion is the correct tool here, not an incomplete stand-in for one: it removes
# the contamination at the source, at the cost of a second live option-chain fetch per
# ticker (bracketing expirations) that a full decomposition would require and this design
# doesn't need to pay for. If a genuinely catalyst-timed earnings screen gets built later,
# implement DJKS decomposition then, against that screen specifically - don't retrofit it
# onto screens that were never trying to price the event in the first place.


def transaction_cost_pct(contract, price_basis):
    """Estimated execution-cost drag, as a fraction of `price_basis` (the underlying price
    for a share-denominated screen, or the strike for a collateral-denominated one): a
    quarter of the contract's own quoted spread - the same slippage contract_liquidity's
    fill_price already assumes, just expressed as a rate rather than a price - plus the
    flat per-contract fee spread over 100 shares.

    A screen-level ranking estimate, not a fill guarantee: real execution quality depends
    on order type, time of day, and market conditions this pipeline has no visibility into.
    """
    if not contract or not price_basis:
        return 0.0
    spread_cost_per_share = (contract.get("spread_pct") or 0) * (contract.get("mid") or 0) / 4
    fee_per_share = CONTRACT_FEE / 100
    return (spread_cost_per_share + fee_per_share) / price_basis


def expected_value_pct(probability_favorable, favorable_return_pct, unfavorable_return_pct, cost_pct=0.0):
    """Probability-weighted expected return (as a fraction of capital), net of an
    estimated transaction-cost drag.

    Ranking by a single best-case return (e.g. "premium annualized to 113.8%") is
    statistically misleading for a fat-tailed, non-normal payoff: it extrapolates one
    realization as if it compounds smoothly, and it silently prefers whichever contract
    happens to have the highest headline number without weighing how likely that outcome
    actually is. This is the two-outcome expected value instead - probability times the
    favorable-scenario return, plus the complementary probability times the
    unfavorable-scenario return, minus the modeled cost of putting the trade on. Returns
    None if `probability_favorable` is unknown (never fabricates a 50/50 guess).
    """
    if probability_favorable is None or favorable_return_pct is None or unfavorable_return_pct is None:
        return None
    return (probability_favorable * favorable_return_pct
            + (1 - probability_favorable) * unfavorable_return_pct - cost_pct)


def kelly_fraction(probability_favorable, favorable_return_pct, unfavorable_return_pct):
    """Continuous-approximation Kelly fraction (mean over variance) for a two-outcome bet -
    NOT scaled down for real use. Full Kelly assumes the probability/payoff inputs are
    exactly right, which a modeled estimate like this one never is, and betting past the
    true Kelly fraction can make the long-run geometric growth rate negative even with a
    genuine edge - see suggested_position_pct for the actually-recommended, discounted
    number. None if either outcome is unknown or the two outcomes are identical (no
    variance to size against).
    """
    if probability_favorable is None or favorable_return_pct is None or unfavorable_return_pct is None:
        return None
    spread = favorable_return_pct - unfavorable_return_pct
    variance = probability_favorable * (1 - probability_favorable) * spread ** 2
    if variance <= 0:
        return None
    mean = probability_favorable * favorable_return_pct + (1 - probability_favorable) * unfavorable_return_pct
    return mean / variance


def suggested_position_pct(probability_favorable, favorable_return_pct, unfavorable_return_pct,
                           kelly_multiplier=0.25, max_position_pct=0.02):
    """Quarter-Kelly (by default) position size as a fraction of capital, hard-capped at
    max_position_pct - the 0.5%-5% per-trade risk budget this pipeline's own risk notes
    already describe in words, expressed here as an actual number instead of left to the
    reader. Full Kelly is inappropriate for a modeled, fat-tailed options bet; practitioners
    commonly use quarter- to half-Kelly plus a hard cap regardless of what the formula says,
    which is what this applies. Never negative - a negative-EV candidate suggests 0%, not a
    short position this app doesn't support or recommend.
    """
    full_kelly = kelly_fraction(probability_favorable, favorable_return_pct, unfavorable_return_pct)
    if full_kelly is None:
        return None
    return max(0.0, min(full_kelly * kelly_multiplier, max_position_pct))


def research_universe_factors(entry, generated_at, as_of=None, *, direction=1, sentiment_mode="signed"):
    """News-sentiment and research-confidence scoring factors sourced from the ticker's
    already-published advisor.json row, discounted by how stale that snapshot is.

    Returns {"news_sentiment": float|None, "research_confidence": float|None} - matching
    the factors dict shape every screen already builds, so a caller just does
    ``row["factors"].update(research_universe_factors(...))``.

    `direction`: +1 when this screen's chosen leg/mechanism is bullish-aligned, -1 when
    bearish-aligned (ignored by the "calm"/"attention" sentiment modes, since those don't
    pick a side). `research_confidence` is always signed by `direction` too, so on
    directional screens it reads as conviction-confirmation, not an independent factor.

    `sentiment_mode`:
      - "signed": average*coverage*direction - rewards sentiment agreeing with the trade
        direction already chosen (multi-day options, vertical spread, cash-secured put -
        see this function's callers for the per-screen rationale on each).
      - "inverse": -average*coverage*direction - rewards calm/opposite sentiment (covered
        call, collar, protective put: don't cap upside into a hot catalyst; a bearish tilt
        modestly raises the case for insurance).
      - "calm": -abs(average)*coverage - rewards low-controversy names regardless of sign
        (iron condor: the risk is an unexpected large move either direction).
      - "attention": coverage alone, unsigned - rewards active news volume regardless of
        polarity (straddle: the strategy needs a real move, not a direction).

    A ticker with zero article coverage contributes None (excluded from that row's
    z-score), never a fabricated neutral value - see news_intelligence.py's identical
    reasoning for why "no coverage" and "coverage confirming neutral" must stay distinct.
    """
    discount = snapshot_staleness_discount(generated_at, as_of)
    discount = 1.0 if discount is None else discount
    detail = entry.get("sentiment_detail") or {}
    average, coverage, article_count = detail.get("average"), detail.get("coverage"), detail.get("article_count")

    sentiment = None
    if sentiment_mode == "attention":
        if coverage is not None:
            sentiment = coverage * discount
    elif article_count and average is not None and coverage is not None:
        if sentiment_mode == "signed":
            sentiment = average * coverage * direction * discount
        elif sentiment_mode == "inverse":
            sentiment = -average * coverage * direction * discount
        elif sentiment_mode == "calm":
            sentiment = -abs(average) * coverage * discount

    score, data_coverage = entry.get("score"), entry.get("data_coverage")
    research_confidence = None
    if score is not None and data_coverage is not None:
        research_confidence = (score - 50) * data_coverage * direction * discount

    return {"news_sentiment": sentiment, "research_confidence": research_confidence}
