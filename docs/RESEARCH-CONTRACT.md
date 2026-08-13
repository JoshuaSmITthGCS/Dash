# Research Contract

Machine-readable version: `pipeline/config/research_contract.json`. This document explains
it; the JSON file is the source of truth a script can actually load.

This contract exists to centralize thresholds and definitions that were previously scattered
across `settings.json`, `research_screens_v2.py`, and `advisor_universe.json` — and, just as
importantly, to say plainly where the contract and the current implementation disagree. A
contract that silently overstates what's implemented is worse than no contract.

## 1. Investable universe

The configured universe is 910 symbols (`pipeline/config/advisor_universe.json`), of which 40
are published per refresh (`publish_limit`) and 21 are portfolio holdings tracked regardless
of rank. ETFs are classified separately (`pipeline/config/universe.json`) and are **ineligible
for stock sleeves** — a fund carries no per-security fundamentals, so it cannot legitimately
clear a screen built on `fundamental_categories`/`technical_detail` shaped for one company.
Reason code: `unsupported_security_type`.

Eligibility thresholds already enforced today (in `research_screens_v2.py`'s momentum
screen):

| Rule | Value | Where enforced |
|---|---|---|
| Minimum price | $5 | `momentum_scores()` `MINIMUM_PRICE` |
| Minimum market cap | $300M | `momentum_scores()` `MINIMUM_MARKET_CAP` |
| Minimum 60-day median dollar volume | $2M | `momentum_scores()` `MINIMUM_LIQUIDITY` |
| Minimum trading history | 253 sessions | `momentum_scores()` `INSUFFICIENT_HISTORY` |

Separately, a **liquidity score modifier** (not a hard gate) exists in `settings.json`:
below $5M dollar volume is "illiquid" (penalized), below $25M is "thin" (smaller penalty).
These are two different mechanisms for two different purposes — don't conflate a modifier
threshold with an eligibility threshold.

**Gaps**, stated honestly rather than glossed over: no IPO-seasoning window, no delisted-
security replay in scoring (the PIT store's `universe.jsonl` logs membership changes but
scoring doesn't yet use that log to keep a delisted name in historical analysis), and no
independent corporate-action event log — the pipeline relies on provider-adjusted prices.

## 2. Forecast targets

**Primary target, as specified:** a 63-trading-day forward sector-residual total return —
`stock_return(t→t+63) − sector_or_risk_adjusted_return(t→t+63)`.

**Primary target, as implemented: the same thing.** This gap is closed.
`pipeline/validation/ic_harness.py` now measures `residual_forward_return` — a name's return
over the window minus the equal-weight mean return of its own sector over the same window —
and counts the horizon in **trading sessions** off a real exchange calendar
(`pipeline/validation/trading_calendar.py`, 8,437 observed NYSE sessions read from the
committed `public/data/etf/SPY.json` series).

Horizons are configured in `settings.json validation.horizons_sessions` as 21/63/126/252
sessions. **`3M` (63 sessions) is the preregistered primary**
(`validation.primary_horizon`); the other three are published as diagnostics and
`secondary_horizons_are_diagnostic_only` is set in the artifact so none of them can be
promoted to primary after the numbers are visible.

Two details worth stating rather than assuming:

- **Why the old bug was invisible.** The medians line up exactly — 21 sessions spans 30
  calendar days, 63 spans 91, 126 spans 182, 252 spans 365, which are the previous
  `horizons_days` constants. The error was in the variance, not the centre: a fixed 91-day
  window is 62 sessions in one part of the year and 64 in another, so the label's length
  drifted. `horizons_days` is retained in config as the labelled pre-correction
  approximation.
- **Sector fallback is reported, not hidden.** A sector with fewer than
  `validation.sector_residual_minimum_peers` (3) names in a period cannot supply a
  meaningful mean, so those names residualize against the universe mean instead and are
  flagged `residual_basis: "universe_fallback"`. Each variant publishes
  `sector_residual_fallback_share`, so a period that mostly fell back — and is therefore
  measuring something closer to a market-residual target — is readable as such.

**Purge and embargo.** `validation_framework.walk_forward_splits` accepts `purge_periods` and
`embargo_periods`, and `evaluation.walk_forward` accepts `purge_periods`. Both default to
zero, preserving prior behaviour. The correct purge is derived, not guessed:
`label_overlap_periods(63, sessions_per_period=21) == 2`, because a 63-session label observed
monthly is still resolving two periods later. Because these splits are strictly expanding,
both controls act on the trailing edge of training; the post-test embargo band of
combinatorial cross-validation has no analogue here, since no path exists by which post-test
data reaches a training fold.

## 3. Execution assumptions

Signal timestamp is the refresh's own `generated_at`. There is currently **no same-close
execution guard** — nothing yet prevents a backtest from using a feature that would not have
been available before the price it's tested against. Transaction costs are a flat 10bps
(`settings.json validation.long_short_cost_bps`), not the
`half_spread + fees + volatility_scaled_impact` model with optimistic/base/stress scenarios
this contract calls for (see `docs/TRANSACTION-COSTS.md`).

## 4. Champion / challenger governance

Champion: `bands_champion` (sector/industry-band fundamental scoring), in production.
Challengers: `cross_sectional_normalization` and the `signal_corrections` family
(`normalization`, `short_horizon`, `confidence_shrinkage`, `modifier_recalibration`,
cumulative) — all shadow-only, published in `score_variants` alongside the champion but never
selected for the champion role.

**No promotion has occurred and none is being proposed.** The IC harness has not reached
`minimum_icir_periods` (24; see `settings.json validation`) — as of the 2026-08-06 baseline it
had observed 0 of 24 eligible periods across 6 refreshes. See
`docs/BASELINE-2026-08-06.md` and `pipeline/reports/stability.json`.

## 5. What this contract does and doesn't change

This file and its JSON counterpart are a **documentation and centralization layer**. Adding
them does not, by itself, change any score, any threshold, or any published number — every
value cited here already governs production behavior at the file/line noted in
`enforced_in`. Where the contract states a target this codebase doesn't yet meet (trading-day
horizons, sector-residual labels, tiered transaction costs), that gap is recorded as
`"implementation_status": "not_implemented"`, not silently assumed away.
