"""Earnings-only catalyst / expected-move screen: formulas, gates and evidence. No I/O.

Scoped to scheduled earnings only, per the two-track factor-validation research this
implements (Claude Research, 2026-09, run for this codebase's own docs/PRE-BREAKOUT-SCREEN-
RESEARCH.md-style prospective-clock process): scheduled earnings is the one catalyst type
where liquid option chains, a well-documented volatility risk premium, and firm dates
converge. FDA/PDUFA, court rulings, index reconstitution and government-contract awards were
explicitly excluded from that research's recommendation (contested pricing, illiquid single-
name chains, soft/slippable dates, or - for index reconstitution - a price effect that has
largely disappeared: Greenwood & Sammon, Journal of Finance 2025, find S&P 500 addition
abnormal returns fell from ~7.4% in the 1990s to under 1% over the past decade). If a
broader multi-catalyst calendar is ever built, it is a new screen against a new date source
for each catalyst type, not an extension of this one - this module has no concept of any
catalyst type but earnings.

Expected move is computed by the variance-difference isolation method
pipeline/options_common.py's own module-level comment names as the correct tool for "a
genuinely catalyst-timed earnings screen" (Dubinsky, Johannes, Kaeck & Seeger 2019, "Option
Pricing of Earnings Announcement Risk", Review of Financial Studies): differencing the
expiry that spans earnings ("post") against the expiry just before it ("pre") isolates the
event-attributable variance from the ambient/diffusive variance both expiries otherwise
share over the same period. See event_isolated_expected_move_pct.

This screen never scores "sell the expected move" as a directional edge, and never treats
PEAD as a stand-alone tradeable signal:

* The market-wide volatility risk premium (Tier A: Coval & Shumway, Journal of Finance 2001;
  Bakshi & Kapadia, Review of Financial Studies 2003 - implied vol exceeds subsequent
  realized vol on average) does NOT transfer cleanly to scheduled earnings specifically.
  Gao, Xing & Zhang (Journal of Financial and Quantitative Analysis 2018) find at-the-money
  straddles bought three days before an earnings announcement earn a highly significant
  3.34% return through the announcement - i.e. options on average UNDER-price earnings
  uncertainty, the opposite of the general premium, and the effect is larger for smaller,
  more volatile, less-covered names. The expected move published here is a sizing/framing
  number, never a claim that it is rich or cheap.
* PEAD (Tier CONTESTED): the classic Bernard-Thomas drift has compressed toward
  insignificance in large caps since roughly 2005-2006 (Martineau, Journal of Financial
  Economics 2022 replication); residual drift concentrates in small, illiquid,
  low-coverage names where transaction costs consume most of the paper return (Chordia,
  Goyal, Sadka, Sadka & Shivakumar, Journal of Financial Economics 2009, report costs
  eating 70-100% of the earnings-momentum long-short profit). Not scored; not published at
  all by this module, since this screen's earnings-drift equivalent already lives in
  pre_breakout_signals.py's standardized_unexpected_earnings subfactor.

Gates are hard exclusions only, same policy as pre_breakout_signals.py and swing_signals.py:
a name with an untrustworthy quote is excluded from the list entirely rather than scored
with a penalty, because a noisy expected-move number is not a weaker signal - it is not a
signal at all (see meets_liquidity_floor).
"""

from __future__ import annotations

import math
from datetime import date, datetime

CATALYST_EVIDENCE = {
    "event_isolated_expected_move_pct": {
        "label": "Event-isolated expected move (variance-difference between the expiry "
                "spanning earnings and the one just before it)",
        "horizon": "through the earnings date",
        "direction": "n/a - a sizing number, never a directional or over/underpriced claim",
        "citation": "Dubinsky, Johannes, Kaeck & Seeger, Review of Financial Studies 2019 "
                    "(\"Option Pricing of Earnings Announcement Risk\"); identity between the "
                    "straddle and IV formulations: Brenner & Subrahmanyam, Financial Analysts "
                    "Journal 1988",
        "effect": "Isolates the incremental variance the market prices into the extra days "
                  "the event-spanning expiry adds beyond the prior expiry - the "
                  "catalyst-attributable component, net of ambient daily volatility both "
                  "expiries otherwise share.",
        "caveat": "None when the isolation fails to resolve cleanly (no prior expiry, "
                  "non-positive isolated variance, or either leg's IV/liquidity gate "
                  "fails) rather than falling back to a cruder single-expiry number - see "
                  "event_isolated_expected_move_pct and meets_liquidity_floor.",
    },
    "volatility_risk_premium": {
        "label": "Market-wide volatility risk premium",
        "horizon": "n/a - background context for reading the expected move, never scored",
        "direction": "n/a",
        "citation": "Coval & Shumway, Journal of Finance 2001; Bakshi & Kapadia, Review of "
                    "Financial Studies 2003",
        "effect": "Implied volatility exceeds subsequent realized volatility on average "
                  "market-wide.",
        "caveat": "Does NOT transfer cleanly to scheduled earnings specifically - Gao, Xing "
                  "& Zhang (JFQA 2018) find pre-earnings ATM straddles earn a significant "
                  "3.34% return, i.e. earnings uncertainty is on average UNDER-priced, not "
                  "over-priced. Never scored; published as reading context only.",
    },
    "pead": {
        "label": "Post-earnings-announcement drift",
        "horizon": "n/a - not published by this module",
        "direction": "n/a",
        "citation": "Martineau, Journal of Financial Economics 2022; Chordia, Goyal, Sadka, "
                    "Sadka & Shivakumar, Journal of Financial Economics 2009",
        "effect": "Classic drift has compressed toward insignificance in large caps since "
                  "roughly 2005-2006; residual drift in small/illiquid names is "
                  "largely consumed by transaction costs.",
        "caveat": "CONTESTED and not scored anywhere in this module. This codebase's PEAD "
                  "reading already lives in pre_breakout_signals.py's "
                  "standardized_unexpected_earnings subfactor - this screen does not "
                  "duplicate it.",
    },
}

DEFAULT_CONFIG = {
    # Same numbers options_common.py's screens use for the shared price/cap floor, plus a
    # dollar-volume floor of this screen's own (not an importable shared constant anywhere in
    # this codebase today - each screen module declares its own copy, same convention
    # pre_breakout_signals.DEFAULT_CONFIG documents).
    "minimum_price": 5,
    "minimum_market_cap": 300_000_000,
    "minimum_underlying_dollar_volume": 5_000_000,
    # The window this screen is scoped to: earnings due today through 14 calendar days out.
    "minimum_days_to_earnings": 0,
    "maximum_days_to_earnings": 14,
    # Stricter than options_common.py's shared MINIMUM_OPEN_INTEREST=50: that floor gates a
    # single contract a screen might trade outright, while this screen's entire output is one
    # derived number built from TWO contracts (the pre- and post-earnings ATM straddles) that
    # is only as trustworthy as the thinner of the two quotes. 500 OI is the practitioner
    # consensus floor cited in the validating research; no peer-reviewed calibration exists
    # for it (report Track B, Finding 4) - treat it as a hypothesis to recalibrate against
    # this screen's own fill-quality data, not a validated constant.
    "minimum_open_interest": 500,
}


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def days_between(as_of, target):
    """Calendar days from ``as_of`` to ``target`` (both date, datetime or ISO-string), or
    None if either is missing/unparseable."""
    as_of_date, target_date = _as_date(as_of) or date.today(), _as_date(target)
    if target_date is None:
        return None
    return (target_date - as_of_date).days


def straddle_expected_move_pct(call_mid, put_mid, spot):
    """Raw ATM-straddle expected move: straddle x sqrt(2/pi) (Brenner & Subrahmanyam 1988).

    Published as a cross-check against event_isolated_expected_move_pct, never scored on its
    own: it is not event-isolated, so a name with elevated ambient (non-earnings) volatility
    reads as a bigger "expected move" even when nothing catalyst-specific is priced in.
    """
    if call_mid is None or put_mid is None or not spot or spot <= 0:
        return None
    straddle = call_mid + put_mid
    return (straddle / spot) * math.sqrt(2 / math.pi) * 100


def iv_implied_move_pct(iv, dte):
    """Single-expiry IV-based expected move: iv * sqrt(dte/365).

    The same identity as straddle_expected_move_pct under Black-Scholes (Brenner &
    Subrahmanyam 1988) - published for the same cross-check reason, never scored, and never
    event-isolated on its own.
    """
    if iv is None or dte is None or iv <= 0 or dte <= 0:
        return None
    return iv * math.sqrt(dte / 365) * 100


def event_isolated_expected_move_pct(pre_iv, pre_dte, post_iv, post_dte):
    """The screen's headline number: variance-difference isolation (DJKS 2019 - see module
    docstring) between the expiry spanning earnings (``post``) and the expiry just before it
    (``pre``). Both expiries share the same ambient/diffusive variance up to ``pre_dte``; the
    incremental variance over the extra ``post_dte - pre_dte`` days is what is attributable
    to the earnings event itself.

    None whenever the isolation cannot resolve cleanly, rather than falling back to a
    cruder single-expiry number: non-positive IV inputs, ``post_dte`` not actually
    longer-dated than ``pre_dte``, or the isolated variance itself coming out non-positive
    (the "event" expiry pricing no more variance than the ambient one - a real, if
    uninformative, outcome that should read as "no signal" rather than a fabricated move).
    """
    if None in (pre_iv, pre_dte, post_iv, post_dte):
        return None
    if pre_iv <= 0 or post_iv <= 0 or post_dte <= pre_dte:
        return None
    variance_pre = (pre_iv ** 2) * (pre_dte / 365)
    variance_post = (post_iv ** 2) * (post_dte / 365)
    isolated_variance = variance_post - variance_pre
    if isolated_variance <= 0:
        return None
    return math.sqrt(isolated_variance) * 100


def meets_liquidity_floor(contract, config=None):
    """Hard gate on top of (not a replacement for) options_common.contract_liquidity's own
    shared floor - see DEFAULT_CONFIG's comment on why this screen needs a stricter open-
    interest minimum. A contract failing this is excluded from the screen entirely.
    """
    config = config or DEFAULT_CONFIG
    if not contract:
        return False
    open_interest = contract.get("open_interest")
    return open_interest is not None and open_interest >= config["minimum_open_interest"]


def gate_reasons(row, config=None):
    """Hard exclusions only - liquidity, price, cap, dollar volume, and window fit. Never
    gates on the expected-move number itself: a small or large expected move is information
    for the reader, not a reason to hide the row.
    """
    config = config or DEFAULT_CONFIG
    reasons = []
    if (row.get("price") or 0) < config["minimum_price"]:
        reasons.append("MINIMUM_PRICE")
    if (row.get("market_cap") or 0) < config["minimum_market_cap"]:
        reasons.append("MINIMUM_MARKET_CAP")
    if (row.get("median_dollar_volume_60d") or 0) < config["minimum_underlying_dollar_volume"]:
        reasons.append("MINIMUM_LIQUIDITY")
    days_to_earnings = row.get("days_to_earnings")
    if days_to_earnings is None:
        reasons.append("NO_CONFIRMED_EARNINGS_DATE")
    elif not (config["minimum_days_to_earnings"] <= days_to_earnings <= config["maximum_days_to_earnings"]):
        reasons.append("OUTSIDE_CATALYST_WINDOW")
    if row.get("expected_move_pct") is None:
        reasons.append("EXPECTED_MOVE_UNRESOLVED")
    return reasons
