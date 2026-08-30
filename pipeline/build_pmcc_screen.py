"""Publishes the "Poor man's covered call" (PMCC) research screen.

A PMCC replaces the 100 shares a real covered call needs with a single deep-in-the-money,
long-dated LEAPS call (high delta, ~80, far expiration - 180-365 days out, targeting 270)
as a capital-efficient stock surrogate, then sells a near-dated out-of-the-money call
against it (~30 delta, ~15-45 days out, targeting 30) for income - the same "sell an OTM
call against a delta-1-ish long position" economics build_covered_call_screen.py already
ranks, just financed with a much cheaper option instead of the full share price. See that
module's WEIGHTS/sentiment-mode comment for the shared reasoning behind most of this
screen's ranking logic; this docstring focuses on what's actually different here.

This is the first screen in this pipeline that fetches TWO option chains, at TWO different
expirations, for the SAME ticker in the same row - one call for select_expiration() and one
call for ticker_obj.option_chain() per leg. Every other build_*_screen.py module reads
ticker_obj.options once and calls option_chain() exactly once; a PMCC genuinely needs both
a ~9-month chain (to price/select the LEAPS leg) and a ~1-month chain (to price/select the
short leg), since real option chains are quoted per-expiration, not across expirations.

Options-chain data is opt-in (ENABLE_PMCC_SCREEN=1): each ticker now costs TWO extra
options-chain requests on top of what fetch_advisor.py already pulls (double the per-ticker
cost of every single-expiration screen in this pipeline), the same opt-in tradeoff
fetch_advisor.py's own ENABLE_OPTIONS_VOLATILITY flag makes. This is a research screen, not
a trade instruction or order-routing feature - nothing in this codebase places option
orders or talks to a brokerage.
"""

import os
from datetime import datetime, timezone

import iv_archive
from backtest_common import CONTRACT_FEE, call_price, performance_stats, synthetic_chain, walk_periods
from common import LOG, load_json, save_json
from fetch_advisor import yahoo_history
from options_common import (MINIMUM_MARKET_CAP, MINIMUM_PRICE, expected_value_pct, expiration_spans_earnings,
                            iv_skew, liquidity_factor, next_earnings_date, put_call_oi_ratio,
                            realized_volatility_20d, realized_vol_percentile, research_universe_factors,
                            select_by_target_delta, select_expiration, single_expiration_gex,
                            transaction_cost_pct, trend_20d)
from peer_groups import peer_group
from research_screens_v2 import winsorize, zscores

# Near-dated short-call window/target: identical convention to build_covered_call_screen's
# own 15-45/30 monthly-income window (that screen's own docstring explains why this differs
# from build_options_screen.py's shorter 2-45/14 directional window) - a PMCC's short leg IS
# a covered call, just against a LEAPS instead of shares, so the same monthly-roll cadence
# applies.
NEAR_MIN_DAYS_TO_EXPIRATION = 15
NEAR_MAX_DAYS_TO_EXPIRATION = 45
NEAR_TARGET_DAYS_TO_EXPIRATION = 30
NEAR_TARGET_DELTA = 0.30

# LEAPS window/target: 180-365 days out, targeting 270 (~9 months) - long enough that the
# position has real time for the underlying thesis to play out and the LEAPS' own theta
# decay is slow (a LEAPS' extrinsic value decays far more slowly than a 30-day option's),
# short enough that it still trades with reasonable liquidity on most optionable names.
# target_delta=0.80: deep enough ITM that the LEAPS behaves like a high-delta stock
# surrogate (moves close to dollar-for-dollar with the underlying) while still costing a
# fraction of buying 100 shares outright - the entire point of a PMCC's capital efficiency.
LEAPS_MIN_DAYS_TO_EXPIRATION = 180
LEAPS_MAX_DAYS_TO_EXPIRATION = 365
LEAPS_TARGET_DAYS_TO_EXPIRATION = 270
LEAPS_TARGET_DELTA = 0.80

# select_by_target_delta's default moneyness bounds (0.0, 0.35) assume an OUT-of-the-money
# call search (moneyness = strike/price - 1, positive for OTM). The LEAPS leg is the
# opposite: deep IN-the-money, i.e. NEGATIVE moneyness (strike well below spot). These
# explicit bounds are what let the same delta-search helper find it - -0.60 comfortably
# covers a ~0.80-delta LEAPS on ordinary volatility names without wandering into
# near-worthless, illiquid deep-ITM strikes at the far end.
LEAPS_MONEYNESS_FLOOR = -0.60
LEAPS_MONEYNESS_CEILING = 0.0

MINIMUM_HISTORY_SESSIONS = 21

# WEIGHTS mirrors build_covered_call_screen.py's {expected_value_pct: .38, liquidity: .25,
# cushion: .21, news_sentiment: .06, research_confidence: .10} shape almost exactly - this
# is the same underlying trade (sell an OTM call against a long delta-heavy position) - with
# "cushion" renamed to "capital_efficiency" since a PMCC has no share-ownership downside
# cushion to speak of; what it DOES have, that a real covered call doesn't, is a capital-
# efficiency dimension (how much cheaper the LEAPS is than owning 100 shares outright), and
# that's the natural factor to fill the same slot in the weighting scheme with.
#
# sentiment_mode="inverse" for the same reason as the covered call screen: strong positive
# sentiment argues against capping upside into a live catalyst. That reasoning transfers
# directly here, arguably with LESS force - a PMCC's LEAPS leg still participates in the
# underlying's move up to the short strike exactly the way owned shares would in a real
# covered call, so being "capped" is no more painful here than there. It is not LESS capped
# (the short call's strike is the ceiling either way); the LEAPS merely makes the capped
# trade cheaper to put on, not less capped.
WEIGHTS = {"expected_value_pct": .38, "liquidity": .25, "capital_efficiency": .21,
          "news_sentiment": .06, "research_confidence": .10}


def build_row(entry, yf, as_of=None, generated_at=None):
    """One candidate PMCC row per ticker, or None if it doesn't clear both legs."""
    ticker = entry.get("ticker")
    if not ticker or yf is None:
        return None
    history = yahoo_history(ticker, yf)
    closes = history["closes"]
    if len(closes) < MINIMUM_HISTORY_SESSIONS:
        return None
    price = closes[-1]
    realized = realized_volatility_20d(closes)
    trend = trend_20d(closes)

    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: options unavailable ({type(exc).__name__})")
        return None

    # One read of the flat expirations list, two independent window selections from it -
    # NOT two separate ticker_obj.options reads. The near/LEAPS windows (15-45 vs 180-365
    # days) are disjoint by construction, so the same expiration should never satisfy both,
    # but the equality guard below is cheap defense against a pathological expirations list
    # (e.g. a single expiration whose dte happens to be reachable by both selections under
    # some future window-constant edit) rather than assuming today's constants forever hold.
    leaps_expiration, leaps_dte = select_expiration(expirations, LEAPS_MIN_DAYS_TO_EXPIRATION,
                                                    LEAPS_MAX_DAYS_TO_EXPIRATION,
                                                    LEAPS_TARGET_DAYS_TO_EXPIRATION, as_of)
    near_expiration, near_dte = select_expiration(expirations, NEAR_MIN_DAYS_TO_EXPIRATION,
                                                  NEAR_MAX_DAYS_TO_EXPIRATION,
                                                  NEAR_TARGET_DAYS_TO_EXPIRATION, as_of)
    if leaps_expiration is None or near_expiration is None:
        return None
    if leaps_expiration == near_expiration:
        LOG.warn(f"{ticker}: LEAPS and near-dated windows resolved to the same expiration "
                 f"({leaps_expiration}), skipping a degenerate PMCC")
        return None

    # Earnings blackout applies to the NEAR expiration only. A single earnings print
    # meaningfully distorts a ~30-day option's pricing (the IV-crush trap
    # expiration_spans_earnings() exists to dodge) - it does not meaningfully distort a
    # ~9-month LEAPS' pricing, since that option sits through many quarters of earnings
    # prints regardless of which one is "next", and no single date drives its extrinsic
    # value the way it drives a 30-day contract's.
    earnings_date = next_earnings_date(ticker_obj, ticker, as_of)
    if expiration_spans_earnings(near_expiration, earnings_date, as_of):
        LOG.info(f"{ticker}: excluded, near expiration {near_expiration} spans earnings on {earnings_date}")
        return None

    try:
        leaps_chain = ticker_obj.option_chain(leaps_expiration)
        near_chain = ticker_obj.option_chain(near_expiration)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{ticker}: option chain unavailable ({type(exc).__name__})")
        return None

    leaps_call = select_by_target_delta(leaps_chain.calls, price, leaps_dte, side="call",
                                        target_delta=LEAPS_TARGET_DELTA,
                                        moneyness_floor=LEAPS_MONEYNESS_FLOOR,
                                        moneyness_ceiling=LEAPS_MONEYNESS_CEILING)
    if leaps_call is None:
        return None
    short_call = select_by_target_delta(near_chain.calls, price, near_dte, side="call",
                                        target_delta=NEAR_TARGET_DELTA)
    if short_call is None:
        return None
    # The short call must sit ABOVE the LEAPS strike. If it didn't, the "spread" between the
    # two strikes would be negative and max_profit_if_assigned below would be nonsensical -
    # this isn't a real capped-upside PMCC at that point, it's a busted setup (most likely a
    # very illiquid/thin near-dated chain producing a nonsense target-delta match).
    if short_call["strike"] <= leaps_call["strike"]:
        LOG.info(f"{ticker}: excluded, short call strike {short_call['strike']} <= "
                 f"LEAPS strike {leaps_call['strike']}")
        return None

    # net_debit/capital_required are the whole point of a PMCC: capital_required here is
    # the LEAPS' own premium (times the 100-share contract multiplier), not price * 100 the
    # way a real covered call's capital_required is - substituting a few-thousand-dollar
    # LEAPS for tens of thousands of dollars of stock is the entire capital-efficiency case
    # for this strategy over a plain covered call.
    net_debit = leaps_call["mid"] - short_call["mid"]
    capital_required = net_debit * 100

    # max_profit_if_assigned is the capped upside if the short call finishes ITM: the
    # strike-to-strike spread, less what it cost to put the whole two-leg trade on. Same
    # shape as a real covered call's "capped gain to the strike, net of premium collected"
    # logic, just measured against the LEAPS strike (the effective "cost basis" this
    # strategy actually owns) instead of the stock's purchase price.
    max_profit_if_assigned = (short_call["strike"] - leaps_call["strike"]) - net_debit
    # Denominator is the LEAPS premium (capital actually deployed), NOT the stock price. A
    # real covered call's max_return_if_assigned_pct divides by price because price*100 IS
    # the capital at risk; dividing this screen's dollar profit by price instead of by the
    # LEAPS premium would understate a PMCC's real ROI by orders of magnitude and defeat the
    # purpose of reporting a capital-efficient trade's return on the capital it actually uses.
    max_return_if_assigned_pct = max_profit_if_assigned / leaps_call["mid"] if leaps_call["mid"] else None

    probability_assigned = short_call.get("delta")
    # Same capital-actually-deployed convention as max_return_if_assigned_pct: yield on the
    # LEAPS premium, not on the stock price.
    annualized_premium_yield = ((short_call["mid"] / leaps_call["mid"]) * (365 / near_dte)
                                if leaps_call["mid"] and near_dte else None)

    # unfavorable_return_pct (the short call expires worthless / not assigned): just the
    # premium yield on capital, short_call["mid"] / leaps_call["mid"]. This is a REAL,
    # STATED simplification specific to PMCC that build_covered_call_screen.py does not
    # need to make: a real covered call's "unassigned" outcome keeps 100 owned shares whose
    # value doesn't decay merely from the passage of time, so that screen's downside_cushion_pct
    # (premium/price) is a complete description of the unassigned outcome. A PMCC's "unassigned"
    # outcome instead still owns a LEAPS call whose own extrinsic value erodes over the SAME
    # ~30 days the short call is outstanding, and whose intrinsic value also moves with the
    # underlying between now and near expiration - real P&L this pipeline has no clean way to
    # model in a per-row simplification (it would need its own Black-Scholes repricing of the
    # LEAPS at a future date under an assumed price path, which is exactly the kind of
    # model-on-a-model compounding this screen's live build_row intentionally avoids; see
    # run_backtest() below for where that repricing DOES get done, deliberately flagged as
    # approximate there too). Treating the unassigned outcome as "just the premium yield"
    # therefore ignores the LEAPS' own theta decay and delta-driven P&L over the same window -
    # stated here plainly, the same way options_common.py's r=0 Black-Scholes docstring and
    # expected_value_pct's "flat from here" comment are stated.
    unfavorable_return = (short_call["mid"] / leaps_call["mid"]) if leaps_call["mid"] else None
    cost_pct = transaction_cost_pct(leaps_call, price) + transaction_cost_pct(short_call, price)
    expected_value = expected_value_pct(probability_assigned, max_return_if_assigned_pct,
                                        unfavorable_return, cost_pct)
    # suggested_position_pct is deliberately NOT computed here - it's quarter-Kelly sized off
    # the same two-outcome probability/payoff pair expected_value_pct just used, so it
    # inherits that same unassigned-outcome simplification; publishing it would dress up an
    # already-approximate input as if it were a fully-modeled position-sizing recommendation.
    # Covered call/protective put publish it because their unassigned/hedge outcomes are
    # complete descriptions of what actually happens; this screen's isn't, so it stays out
    # of `metrics` rather than implying a precision the inputs don't support.

    skew = iv_skew(near_chain.calls, near_chain.puts, price, near_dte)
    pc_oi_ratio = put_call_oi_ratio(near_chain.calls, near_chain.puts)
    gex = single_expiration_gex(near_chain.calls, near_chain.puts, price, near_dte)
    vol_percentile = realized_vol_percentile(closes)
    research_factors = research_universe_factors(entry, generated_at, as_of, direction=1, sentiment_mode="inverse")

    # capital_efficiency factor: how much cheaper the PMCC's capital outlay is than buying
    # 100 shares outright. net_debit*100 / (price*100) is the fraction of a real covered
    # call's capital this position actually uses - smaller is better (more efficient), so
    # the factor is negated to keep this module's "higher factor value = better candidate"
    # convention (every other WEIGHTS field here follows that convention too).
    capital_efficiency = -(net_debit * 100) / (price * 100) if price else None

    group_id, group_label = peer_group(entry)
    return {
        "ticker": ticker, "peer_group": group_id, "peer_group_label": group_label,
        "sector": entry.get("sector"), "price": price, "market_cap": entry.get("market_cap"),
        "history_sessions": len(closes), "structural_score": entry.get("score"),
        "data_coverage": entry.get("data_coverage"),
        "trend_20d": round(trend, 4) if trend is not None else None,
        "realized_volatility_20d": round(realized, 4) if realized is not None else None,
        # Row-level expiration/days_to_expiration report the NEAR leg - that's the one that
        # actually needs monitoring/rolling on a monthly cadence, the same way a real
        # covered call's short leg is the one that gets managed. The LEAPS leg's own
        # expiration/days_to_expiration are still published per-leg inside `legs` below.
        "expiration": near_expiration, "days_to_expiration": near_dte,
        "leaps_expiration": leaps_expiration, "leaps_days_to_expiration": leaps_dte,
        "capital_required": round(capital_required, 2),
        "leaps_call": leaps_call, "short_call": short_call,
        "metrics": {
            "net_debit": round(net_debit, 4), "capital_required": round(capital_required, 2),
            "max_profit_if_assigned": round(max_profit_if_assigned, 4),
            "max_return_if_assigned_pct": (round(max_return_if_assigned_pct, 4)
                                           if max_return_if_assigned_pct is not None else None),
            "annualized_premium_yield": (round(annualized_premium_yield, 4)
                                         if annualized_premium_yield is not None else None),
            "expected_value_pct": round(expected_value, 4) if expected_value is not None else None,
            "probability_assigned": round(probability_assigned, 4) if probability_assigned is not None else None,
            "iv_skew": skew, "put_call_oi_ratio": pc_oi_ratio, "realized_volatility_percentile": vol_percentile,
            # Read-only - see build_options_screen.py's identical comment: only
            # build_options_strategies.py's shared fetch writes to iv_archive.
            "iv_percentile": iv_archive.iv_percentile(ticker), "single_expiration_gex": gex,
            "news_sentiment": round(research_factors["news_sentiment"], 4) if research_factors["news_sentiment"] is not None else None,
            "research_confidence": round(research_factors["research_confidence"], 4) if research_factors["research_confidence"] is not None else None,
        },
        "factors": {
            "expected_value_pct": expected_value,
            "liquidity": liquidity_factor(short_call),
            "capital_efficiency": capital_efficiency,
            **research_factors,
        },
    }


def build_rows(universe, yf, as_of=None, generated_at=None):
    return [row for row in (build_row(entry, yf, as_of, generated_at) for entry in universe) if row is not None]


def score_rows(rows, config=None):
    """Winsorized z-score composite among eligible rows, ranked into a percentile."""
    config = config or {}
    fields = list(WEIGHTS)
    standardized = {field: zscores(winsorize([(row["factors"] or {}).get(field) for row in rows]))
                     for field in fields}
    output = []
    for index, row in enumerate(rows):
        reasons = []
        if (row.get("price") or 0) < config.get("minimum_price", MINIMUM_PRICE):
            reasons.append("MINIMUM_PRICE")
        if (row.get("market_cap") or 0) < config.get("minimum_market_cap", MINIMUM_MARKET_CAP):
            reasons.append("MINIMUM_MARKET_CAP")
        if row.get("realized_volatility_20d") is None:
            reasons.append("INSUFFICIENT_HISTORY")
        contributions = {field: (standardized[field][index] or 0) * WEIGHTS[field] for field in fields}
        score = sum(contributions.values())
        output.append({**row, "score": round(score, 4),
                       "standardized_factors": {field: standardized[field][index] for field in fields},
                       "contribution_by_factor": {field: round(value, 4) for field, value in contributions.items()},
                       "eligibility": not reasons, "reason_codes": reasons})
    eligible = sorted((row for row in output if row["eligibility"]), key=lambda row: row["score"])
    for rank, row in enumerate(eligible):
        row["percentile"] = round(100 * rank / max(1, len(eligible) - 1), 2)
    for row in output:
        row.setdefault("percentile", None)
    return sorted(output, key=lambda row: row["score"], reverse=True)


def to_result(rank, row):
    leaps_call = row.get("leaps_call") or {}
    short_call = row.get("short_call") or {}
    return {
        "rank": rank, "ticker": row["ticker"], "eligibility": row["eligibility"],
        "sector": row.get("sector"), "peer_group": row.get("peer_group_label") or row.get("peer_group"),
        "percentile": row.get("percentile"), "score": row.get("score"),
        "structural_score": row.get("structural_score"), "data_coverage": row.get("data_coverage"),
        "price": row.get("price"), "trend_20d": row.get("trend_20d"),
        # Row-level expiration is the NEAR leg's - see build_row's comment on why. Each leg
        # below still carries its OWN expiration/days_to_expiration, since (unlike every
        # other screen here) the two legs of this trade don't share one expiration.
        "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration"),
        "capital_required": row.get("capital_required"),
        "legs": [
            {"action": "buy", "option_type": "call", "strike": leaps_call.get("strike"),
             "bid": leaps_call.get("bid"), "ask": leaps_call.get("ask"), "mid": leaps_call.get("mid"),
             "spread_pct": leaps_call.get("spread_pct"), "implied_volatility": leaps_call.get("implied_volatility"),
             "open_interest": leaps_call.get("open_interest"), "delta": leaps_call.get("delta"),
             "expiration": row.get("leaps_expiration"), "days_to_expiration": row.get("leaps_days_to_expiration")},
            {"action": "sell", "option_type": "call", "strike": short_call.get("strike"),
             "bid": short_call.get("bid"), "ask": short_call.get("ask"), "mid": short_call.get("mid"),
             "spread_pct": short_call.get("spread_pct"), "implied_volatility": short_call.get("implied_volatility"),
             "open_interest": short_call.get("open_interest"), "delta": short_call.get("delta"),
             "expiration": row.get("expiration"), "days_to_expiration": row.get("days_to_expiration")},
        ],
        "metrics": row.get("metrics", {}),
        "reason_codes": row.get("reason_codes", []),
    }


def unavailable(reason_code, generated_at):
    return {
        "schema_version": "1.0.0", "model_version": "pmcc-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at,
        "status": "unavailable", "reason_code": reason_code, "results": [],
    }


def run(as_of=None):
    if os.getenv("ENABLE_PMCC_SCREEN", "").lower() not in {"1", "true", "yes"}:
        LOG.info("PMCC screen: opt-in flag not set, skipping (set ENABLE_PMCC_SCREEN=1)")
        return None
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    snapshot_generated_at = payload.get("generated_at")
    generated_at = datetime.now(timezone.utc).isoformat()
    if not universe:
        LOG.warn("PMCC screen: no published universe to score, skipping")
        result = unavailable("NO_PUBLISHED_UNIVERSE", generated_at)
        save_json("screens/pmcc.json", result)
        return result

    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = unavailable("YFINANCE_UNAVAILABLE", generated_at)
        save_json("screens/pmcc.json", result)
        return result

    rows = build_rows(universe, yf, as_of, snapshot_generated_at)
    if not rows:
        result = unavailable("NO_QUALIFYING_CONTRACTS", generated_at)
        save_json("screens/pmcc.json", result)
        return result

    scored = score_rows(rows)
    results = [to_result(rank + 1, row) for rank, row in enumerate(scored)]
    result = {
        "schema_version": "1.0.0", "model_version": "pmcc-v1.0.0",
        "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
        "window": {"near_min_days_to_expiration": NEAR_MIN_DAYS_TO_EXPIRATION,
                   "near_max_days_to_expiration": NEAR_MAX_DAYS_TO_EXPIRATION,
                   "near_target_days_to_expiration": NEAR_TARGET_DAYS_TO_EXPIRATION,
                   "near_target_delta": NEAR_TARGET_DELTA,
                   "leaps_min_days_to_expiration": LEAPS_MIN_DAYS_TO_EXPIRATION,
                   "leaps_max_days_to_expiration": LEAPS_MAX_DAYS_TO_EXPIRATION,
                   "leaps_target_days_to_expiration": LEAPS_TARGET_DAYS_TO_EXPIRATION,
                   "leaps_target_delta": LEAPS_TARGET_DELTA},
        "results": results,
    }
    save_json("screens/pmcc.json", result)
    LOG.info(f"PMCC screen: scored {len(results)} tickers "
             f"({sum(1 for row in results if row['eligibility'])} eligible)")
    return result


def backtest_universe(universe, yf, as_of=None):
    """Simulated walk-forward PMCC backtest, pooled across every ticker in `universe`.

    This is the most approximate backtest of this pipeline's options screens - it compounds
    two simplifications neither build_covered_call_screen.py's nor build_protective_put_screen.py's
    backtests need to make (see run_backtest()'s published `methodology` string for the full
    disclosure). Briefly:

    1. Shared IV input across two very different-dated instruments. Both the LEAPS chain and
       the near-dated chain are synthesized from the SAME trailing-realized-vol `iv` reading
       at entry (backtest_common.py gives this pipeline exactly one realized-vol series per
       ticker, not a term structure) - a real LEAPS' implied-vol term structure genuinely
       differs from a 30-day option's, and this backtest does not model that difference.
    2. Mark-to-model exit for the LEAPS leg. At the near leg's settlement date, the short
       call settles/rolls against the REAL historical close (same convention as every other
       screen's backtest), but the LEAPS call has no real quoted price at that date to read -
       Yahoo serves only the CURRENT chain (see backtest_common.py's module docstring), so
       there's no historical LEAPS quote to look up. It gets marked to its OWN Black-Scholes
       model value at the settlement date/price, using the SAME entry `iv` input as before -
       a second application of the same shared-IV simplification, not an independent
       verification of it. A real position wouldn't necessarily be closed out at that point,
       but this walk-forward design needs SOME way to compute a period P&L, and marking to
       model at the near-leg's roll date is the same "assume some model is right" approach
       every backtest here already leans on for entry pricing.
    """
    period_returns, trade_pnls = [], []
    remaining_leaps_dte = LEAPS_TARGET_DAYS_TO_EXPIRATION - NEAR_TARGET_DAYS_TO_EXPIRATION
    for entry in universe:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        closes = yahoo_history(ticker, yf)["closes"]
        for entry_index, expiry_index in walk_periods(closes, NEAR_TARGET_DAYS_TO_EXPIRATION):
            price, settle_price = closes[entry_index], closes[expiry_index]
            iv = realized_volatility_20d(closes[:entry_index + 1])
            if not iv or not price:
                continue
            leaps_calls, _ = synthetic_chain(price, iv, LEAPS_TARGET_DAYS_TO_EXPIRATION)
            near_calls, _ = synthetic_chain(price, iv, NEAR_TARGET_DAYS_TO_EXPIRATION)
            leaps_call = select_by_target_delta(leaps_calls, price, LEAPS_TARGET_DAYS_TO_EXPIRATION,
                                                side="call", target_delta=LEAPS_TARGET_DELTA,
                                                moneyness_floor=LEAPS_MONEYNESS_FLOOR,
                                                moneyness_ceiling=LEAPS_MONEYNESS_CEILING)
            if leaps_call is None:
                continue
            short_call = select_by_target_delta(near_calls, price, NEAR_TARGET_DAYS_TO_EXPIRATION,
                                                side="call", target_delta=NEAR_TARGET_DELTA)
            if short_call is None or short_call["strike"] <= leaps_call["strike"]:
                continue

            leaps_entry_cost = leaps_call["mid"]
            short_premium_collected = short_call["mid"]
            fee_per_contract_pair = 2 * CONTRACT_FEE / 100  # two legs opened

            # Short call's payoff at settlement: real historical close, capped at its own
            # strike the way any short call's assignment payoff is (mirrors
            # build_covered_call_screen.backtest_universe's min(settle_price, strike) logic,
            # expressed here as an explicit payout rather than folded into a min()).
            short_payout = max(0.0, settle_price - short_call["strike"])

            # LEAPS exit value: mark-to-model at the settlement date/price, same entry IV
            # input (see docstring point 2 above) and the LEAPS' own remaining time to its
            # OWN expiration (LEAPS_TARGET_DAYS_TO_EXPIRATION - NEAR_TARGET_DAYS_TO_EXPIRATION
            # days still outstanding at this point, not zero - the LEAPS itself hasn't
            # expired yet at the near leg's roll date).
            leaps_exit_value = call_price(settle_price, leaps_call["strike"], iv, remaining_leaps_dte)
            if leaps_exit_value is None:
                continue

            pnl = ((leaps_exit_value - leaps_entry_cost) + (short_premium_collected - short_payout)) * 100
            pnl -= CONTRACT_FEE * 2  # two legs opened this period
            period_return = pnl / (leaps_entry_cost * 100) if leaps_entry_cost else None
            if period_return is None:
                continue
            period_returns.append(period_return)
            trade_pnls.append(pnl)
    return performance_stats(period_returns, periods_per_year=365 / NEAR_TARGET_DAYS_TO_EXPIRATION,
                             trade_pnls=trade_pnls)


def run_backtest(as_of=None):
    """Same shape as run(), but with no ENABLE_PMCC_SCREEN gate: the backtest needs no live
    option-chain data (see backtest_common.py), so it always attempts to run when called - a
    separate runner script decides when that is.
    """
    payload = load_json("advisor.json") or {}
    universe = [*payload.get("research", []), *payload.get("portfolio_coverage", [])]
    generated_at = datetime.now(timezone.utc).isoformat()
    methodology = ("APPROXIMATE, more so than this pipeline's other options backtests: two "
                   "simplifications compound here rather than one. (1) The LEAPS leg and the "
                   "near-dated short leg are both priced with Black-Scholes off the SAME "
                   "trailing realized-volatility input at entry, even though a real LEAPS' "
                   "implied-vol term structure genuinely differs from a 30-day option's - this "
                   "backtest has no separate IV series for the two tenors and does not model "
                   "that difference. (2) At each period's settlement, the short call is settled "
                   "against the real historical closing price, but the LEAPS leg has no real "
                   "historical quote to read (Yahoo serves only the current chain), so it is "
                   "marked to its OWN Black-Scholes model value at that date, using the SAME "
                   "entry implied-volatility input - a real position would not necessarily be "
                   "closed out at that point, and real implied volatility would very likely "
                   "have moved by then. Real historical bid/ask spreads, open interest, and "
                   "fill quality are not modeled at all. Trade settlement price is real for "
                   "the short leg; the LEAPS leg's value at that date is a model estimate, not "
                   "a quote. The live screen's ranking also factors in news sentiment and the "
                   "ticker's broader research-universe score/confidence; this backtest does "
                   "not, since no point-in-time history of those signals exists yet to "
                   "backtest against without look-ahead risk.")
    if not universe:
        result = {"schema_version": "1.0.0", "model_version": "pmcc-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "NO_PUBLISHED_UNIVERSE", "methodology": methodology}
        save_json("screens/pmcc-backtest.json", result)
        return result
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    if yf is None:
        result = {"schema_version": "1.0.0", "model_version": "pmcc-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "YFINANCE_UNAVAILABLE", "methodology": methodology}
        save_json("screens/pmcc-backtest.json", result)
        return result
    stats = backtest_universe(universe, yf, as_of)
    if stats is None:
        result = {"schema_version": "1.0.0", "model_version": "pmcc-backtest-v1.0.0",
                  "config_version": "screens-v1.0.0", "generated_at": generated_at,
                  "status": "unavailable", "reason_code": "INSUFFICIENT_HISTORY", "methodology": methodology}
        save_json("screens/pmcc-backtest.json", result)
        return result
    result = {"schema_version": "1.0.0", "model_version": "pmcc-backtest-v1.0.0",
              "config_version": "screens-v1.0.0", "generated_at": generated_at, "status": "success",
              "methodology": methodology, "universe_tickers": len(universe),
              "window": {"near_min_days_to_expiration": NEAR_MIN_DAYS_TO_EXPIRATION,
                         "near_max_days_to_expiration": NEAR_MAX_DAYS_TO_EXPIRATION,
                         "near_target_days_to_expiration": NEAR_TARGET_DAYS_TO_EXPIRATION,
                         "near_target_delta": NEAR_TARGET_DELTA,
                         "leaps_min_days_to_expiration": LEAPS_MIN_DAYS_TO_EXPIRATION,
                         "leaps_max_days_to_expiration": LEAPS_MAX_DAYS_TO_EXPIRATION,
                         "leaps_target_days_to_expiration": LEAPS_TARGET_DAYS_TO_EXPIRATION,
                         "leaps_target_delta": LEAPS_TARGET_DELTA},
              "backtest": stats}
    save_json("screens/pmcc-backtest.json", result)
    LOG.info(f"PMCC backtest: {stats['num_trades']} trades, "
             f"{stats['annualized_return']*100:.1f}% annualized, {stats['win_rate']*100:.0f}% win rate")
    return result


if __name__ == "__main__":
    run()
