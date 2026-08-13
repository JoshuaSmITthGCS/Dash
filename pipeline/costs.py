"""Transaction cost model (docs/RESEARCH-CONTRACT.md, docs/TRANSACTION-COSTS.md).

Replaces the single flat cost the validation harness has used until now
(settings.json validation.long_short_cost_bps, 10bps) with the
half_spread + fees + volatility_scaled_impact model the research contract specifies, across
three scenarios. This module does not change what ic_harness.py or any backtest currently
reports -- wiring a caller to use scenario-based costs instead of the flat rate is separate,
not-yet-done work; see docs/TRANSACTION-COSTS.md for exactly what is and isn't wired up.

No real bid-ask spread data is available from any current provider (Yahoo/Alpha Vantage
don't serve quoted spreads). Rather than fabricate one, this model uses a clearly labeled,
liquidity-tiered proxy -- see SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER below -- and every returned
breakdown says so explicitly via ``spread_source``.
"""

from common import load_json

DEFAULT_FEES_BPS = 0.0  # most US equity trades: exchange/broker fees are effectively zero for a retail research context

# No provider used in this pipeline serves quoted or effective spreads. These are a
# conservative, clearly-labeled proxy tiered by the same liquidity thresholds already used
# elsewhere (settings.json modifiers.liquidity; research_screens_v2.py's
# minimum_median_dollar_volume_60d) -- not a measured spread. Values widen as liquidity
# thins, which is directionally correct even though the exact bps are not empirical.
SPREAD_CAVEAT = (
    "The spread term is a liquidity-tiered proxy. It is not a measured quoted spread and it is "
    "not an effective spread. No provider in this pipeline serves either, so the tier values "
    "below are a conservative ordering rather than an empirical measurement, and every cost "
    "figure derived from them inherits that limitation.")

SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER = {
    "liquid": 2.0,      # >= thin_dollar_volume ($25M/day, settings.json modifiers.liquidity)
    "thin": 8.0,        # between illiquid and thin thresholds ($5M-$25M/day)
    "illiquid": 25.0,   # < illiquid_dollar_volume ($5M/day)
}

# Market-impact scaling: impact grows with a name's own realized volatility and with how
# large the trade is relative to its own liquidity (participation rate). The functional
# form (impact proportional to volatility * sqrt(participation)) follows the standard
# square-root market-impact law of the execution literature.
#
# Round 6 recalibration (docs/AUDIT-ROUND-6-FINDINGS.md, Task 4). The previous base
# coefficient of 15 implied 4.5bps of impact at 100% ADV participation for a 30%-vol
# name, which Round 5 measured as 15 to 40 times below the canonical law. The canonical
# form is impact of order DAILY volatility times sqrt(participation): with volatility
# supplied annualized, the equivalent coefficient is 1e4/sqrt(252) ~ 630. That is now the
# base scenario. The old base of 15 survives only as the clearly-labeled optimistic
# scenario, because every net-of-cost figure published in audit Rounds 3 through 5 used
# it and comparability requires it to stay computable.
IMPACT_SCENARIOS = {
    "optimistic": {"spread_multiplier": 0.5, "impact_coefficient": 15.0,
                   "label": "pre-Round-6 base, retained for comparability, understates impact by an order of magnitude at scale"},
    "base": {"spread_multiplier": 1.0, "impact_coefficient": 630.0,
             "label": "canonical square-root law, daily volatility times sqrt(participation)"},
    "stress": {"spread_multiplier": 2.0, "impact_coefficient": 1260.0,
               "label": "2x canonical"},
}


def liquidity_tier(median_dollar_volume_60d, *, thin_threshold=None, illiquid_threshold=None):
    """Classify a name's liquidity using the same thresholds the scoring modifier already
    uses (settings.json modifiers.liquidity), so this cost model and that modifier can never
    silently disagree about what counts as "thin" or "illiquid".
    """
    if thin_threshold is None or illiquid_threshold is None:
        settings = load_json("settings.json", from_config=True) or {}
        liquidity_cfg = (settings.get("modifiers") or {}).get("liquidity", {})
        thin_threshold = thin_threshold or liquidity_cfg.get("thin_dollar_volume", 25_000_000)
        illiquid_threshold = illiquid_threshold or liquidity_cfg.get("illiquid_dollar_volume", 5_000_000)
    if median_dollar_volume_60d is None:
        return None
    if median_dollar_volume_60d < illiquid_threshold:
        return "illiquid"
    if median_dollar_volume_60d < thin_threshold:
        return "thin"
    return "liquid"


def estimate_cost_bps(*, median_dollar_volume_60d, annualized_volatility=None,
                      trade_dollar_value=None, scenario="base", fees_bps=DEFAULT_FEES_BPS):
    """One-way transaction cost estimate in basis points:
    ``cost = half_spread + fees + volatility_scaled_market_impact``.

    Every input can be missing -- a name with no liquidity or volatility data gets the most
    conservative tier's spread and zero impact (since impact needs both a trade size and a
    volatility reading to estimate), never a silently invented number.
    """
    if scenario not in IMPACT_SCENARIOS:
        raise ValueError(f"unsupported cost scenario: {scenario}")
    params = IMPACT_SCENARIOS[scenario]

    tier = liquidity_tier(median_dollar_volume_60d)
    spread_bps = SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER.get(tier, SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER["illiquid"])
    half_spread_bps = (spread_bps / 2) * params["spread_multiplier"]

    # Spec amendment SA-2026-08-12-06. Participation is no longer clamped at 100% of ADV.
    #
    # The clamp was a silent inconsistency in the published cost curve: past one day's volume
    # the quoted impact stopped rising with size, so the round-trip figures quoted across
    # portfolio sizes did not all sit on the same square-root law, and the largest of them
    # understated cost by exactly the amount the clamp removed. Two figures under one heading
    # obeying two different models is worse than one figure the reader knows is extrapolated.
    #
    # The law is therefore applied as written at every size, and ``beyond_measured_domain``
    # marks the region where it is an extrapolation rather than a calibration. Nothing should
    # be traded there anyway: participation_check rejects a position over the cap long before
    # this point, which is the control that makes the extrapolated region unreachable rather
    # than merely disclosed.
    impact_bps = 0.0
    participation = None
    if annualized_volatility is not None and trade_dollar_value and median_dollar_volume_60d:
        participation = trade_dollar_value / median_dollar_volume_60d
        impact_bps = params["impact_coefficient"] * annualized_volatility * (participation ** 0.5)

    total_bps = round(half_spread_bps + fees_bps + impact_bps, 2)
    return {
        "scenario": scenario,
        "total_bps": total_bps,
        "half_spread_bps": round(half_spread_bps, 2),
        "fees_bps": round(fees_bps, 2),
        "impact_bps": round(impact_bps, 2),
        "liquidity_tier": tier,
        "participation_rate": round(participation, 4) if participation is not None else None,
        # True where the position exceeds the participation ceiling, which is where the
        # square-root law is being extrapolated past the order flow it was estimated on.
        "beyond_measured_domain": bool(participation is not None
                                       and participation > MAX_ADV_PARTICIPATION_CEILING),
        "spread_source": "liquidity_tiered_proxy_not_measured",
        "spread_caveat": SPREAD_CAVEAT,
        # trade_dollar_value is one trade in one name. It is never a book size. A caller that
        # passes a whole portfolio here gets the cost of trading that portfolio as a single
        # position, which is a different and much larger number than the cost of the book.
        "size_basis": "single_position_one_way_trade",
    }


def cost_scenarios(*, median_dollar_volume_60d, annualized_volatility=None,
                   trade_dollar_value=None, fees_bps=DEFAULT_FEES_BPS):
    """All three scenarios at once, for a report that wants to show the full range rather
    than commit to one assumption.
    """
    return {
        scenario: estimate_cost_bps(
            median_dollar_volume_60d=median_dollar_volume_60d,
            annualized_volatility=annualized_volatility,
            trade_dollar_value=trade_dollar_value,
            scenario=scenario,
            fees_bps=fees_bps,
        )
        for scenario in IMPACT_SCENARIOS
    }


# Spec amendment SA-2026-08-12-06. Share of trailing 20-day ADV a single round trip may take.
# The default is deliberately well inside the ceiling: the square-root impact law is estimated
# on institutional order flow at low single-digit participation, and quoting a cost at 40% of
# a day's volume extrapolates the law far past where anyone measured it. The ceiling is a hard
# stop, not a suggestion -- a configured cap above it raises rather than clamping, because a
# silently clamped cap reads as if the requested size was accepted.
DEFAULT_MAX_ADV_PARTICIPATION = 0.05
MAX_ADV_PARTICIPATION_CEILING = 0.10


def participation_check(*, trade_dollar_value, adv_20d_dollar_volume,
                        max_participation=DEFAULT_MAX_ADV_PARTICIPATION,
                        ceiling=MAX_ADV_PARTICIPATION_CEILING,
                        adv_source="trailing_20d_mean_dollar_volume"):
    """Whether one round trip fits inside the ADV participation cap.

    Returns the participation rate, the cap it was measured against, whether it breaches, and
    the largest position that would not. A breaching position is reported as untradable. It is
    not quoted with a cost, because the cost model cannot price it: the impact term saturates
    participation at 100% of ADV, so past the cap the quoted number stops rising with size and
    would understate the true cost of a position nobody can actually put on.

    ``adv_20d_dollar_volume`` is the trailing 20-session mean, which is the window the cap is
    written against. ``adv_source`` records what actually answered, so a row that fell back to
    a 60-day median is identifiable rather than presented as if it were the 20-day figure.
    """
    if max_participation is None or max_participation <= 0:
        raise ValueError("max_participation must be a positive share of ADV")
    if max_participation > ceiling:
        raise ValueError(
            f"max_participation {max_participation} exceeds the hard ceiling {ceiling}. "
            "The cap is a constraint on the impact model's domain of validity, so it is "
            "raised by amending the ceiling deliberately, never by passing a larger value.")
    if not adv_20d_dollar_volume or not trade_dollar_value:
        return {"participation_rate": None, "max_participation": max_participation,
                "ceiling": ceiling, "breaches_cap": False, "max_position_dollar_value": None,
                "adv_20d_dollar_volume": adv_20d_dollar_volume, "adv_source": adv_source,
                "status": "unknown_participation_no_adv_or_no_size"}
    rate = trade_dollar_value / adv_20d_dollar_volume
    return {
        "participation_rate": round(rate, 6),
        "max_participation": max_participation,
        "ceiling": ceiling,
        "breaches_cap": rate > max_participation,
        "max_position_dollar_value": round(adv_20d_dollar_volume * max_participation, 2),
        "adv_20d_dollar_volume": adv_20d_dollar_volume,
        "adv_source": adv_source,
        "status": "over_cap" if rate > max_participation else "within_cap",
    }


def max_trade_for_adv_participation(adv_dollar_volume,
                                    max_participation=DEFAULT_MAX_ADV_PARTICIPATION):
    """The largest one-way trade the participation cap allows against this name's ADV.

    The cap is written against trailing 20-day ADV. Callers that can only supply a 60-day
    median dollar volume get an answer computed against that instead and are responsible for
    labelling which one they passed -- ``participation_check`` carries an ``adv_source`` field
    for exactly that.
    """
    if not adv_dollar_volume:
        return None
    return round(adv_dollar_volume * max_participation, 2)
