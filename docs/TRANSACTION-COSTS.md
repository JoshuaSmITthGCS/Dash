# Transaction Costs

Machine-readable model: `pipeline/costs.py`.

## The model

```
cost_bps = half_spread_bps + fees_bps + volatility_scaled_impact_bps
```

Three scenarios (`optimistic`, `base`, `stress`) scale both the spread and the impact
coefficient, per `pipeline/costs.py`'s `IMPACT_SCENARIOS`.

## What's real and what's a labeled proxy

**Real:** the liquidity tiering (`liquidity_tier()`) uses the exact same thresholds already
enforced elsewhere in this pipeline (`settings.json modifiers.liquidity`:
`illiquid_dollar_volume` $5M, `thin_dollar_volume` $25M) — this model cannot silently
disagree with the scoring modifier about what counts as illiquid. The market-impact
functional form (impact ∝ volatility × √participation) is the standard square-root
market-impact heuristic from the execution literature, and participation rate is computed
from a real trade size against real median dollar volume when both are supplied.

**Labeled proxy, not measured:** no provider used anywhere in this pipeline (Yahoo, Alpha
Vantage) serves quoted or effective bid-ask spreads. `SPREAD_PROXY_BPS_BY_LIQUIDITY_TIER`
(2bps liquid / 8bps thin / 25bps illiquid) is a conservative, directionally-correct estimate,
not an empirical one. Every result from `estimate_cost_bps()` carries
`"spread_source": "liquidity_tiered_proxy_not_measured"` so a consumer can never mistake it
for real spread data. The impact coefficients (5.0 / 15.0 / 40.0 across the three scenarios)
are labeled research defaults, not fitted or measured values.

## What is and isn't wired up

`pipeline/costs.py` exists and is tested (`pipeline/tests/test_costs.py`) but **is not yet
called by `pipeline/validation/ic_harness.py`**, which still uses the flat
`settings.json validation.long_short_cost_bps` (10bps) for every net-of-cost calculation.
Wiring the harness to use scenario-based, liquidity-aware costs instead of a flat rate is
real follow-up work, not done as part of this pass — stated here rather than left implicit.

## ADV participation cap

`max_trade_for_adv_participation()` implements the research contract's default: no one-way
trade should exceed 2% of 60-day median dollar volume. This is a suggested research default,
configurable, not investment advice.
