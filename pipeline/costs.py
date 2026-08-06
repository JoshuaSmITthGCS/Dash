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
SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER = {
    "liquid": 2.0,      # >= thin_dollar_volume ($25M/day, settings.json modifiers.liquidity)
    "thin": 8.0,        # between illiquid and thin thresholds ($5M-$25M/day)
    "illiquid": 25.0,   # < illiquid_dollar_volume ($5M/day)
}

# Market-impact scaling: impact grows with a name's own realized volatility and with how
# large the trade is relative to its own liquidity (participation rate). The functional form
# (impact proportional to volatility * sqrt(participation)) follows the standard square-root
# market-impact heuristic used across the execution literature; the specific proportionality
# constant below is a labeled research default, not a fitted or measured value.
IMPACT_SCENARIOS = {
    "optimistic": {"spread_multiplier": 0.5, "impact_coefficient": 5.0},
    "base": {"spread_multiplier": 1.0, "impact_coefficient": 15.0},
    "stress": {"spread_multiplier": 2.0, "impact_coefficient": 40.0},
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

    impact_bps = 0.0
    participation = None
    if annualized_volatility is not None and trade_dollar_value and median_dollar_volume_60d:
        participation = min(1.0, trade_dollar_value / median_dollar_volume_60d)
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
        "spread_source": "liquidity_tiered_proxy_not_measured",
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


def max_trade_for_adv_participation(median_dollar_volume_60d, max_participation=0.02):
    """The largest one-way trade this model will size before ADV participation itself
    becomes the binding constraint, per the research contract's default cap (2% of 20-day
    ADV -- the research contract cites 60-day median dollar volume, used consistently here).
    """
    if not median_dollar_volume_60d:
        return None
    return round(median_dollar_volume_60d * max_participation, 2)
