# Model Card — ValueSignal Research Score

## What it predicts

The champion score is a cross-sectional rank of companies by evidence quality — fundamentals
(78%), market behavior (18%, includes the new technical_extended factor at ~6% of that
share), and news sentiment (4%). It is designed as a research-evidence summary, not a
validated forecast of forward returns. See "Validation state" below for what has and hasn't
been tested.

## What it does not predict

- A specific price target, timing, or magnitude of a future move.
- Short-term (intraday, next-session) price direction.
- Outcomes for a specific holding period — no target horizon is bound to the champion score
  itself (individual sleeves in `pipeline/sleeves/` do declare a `target_horizon_days`, but
  the production composite does not).
- Anything for ETFs — ETFs are scored by a completely separate model
  (`pipeline/fetch_etfs.py`) and are ineligible for every stock sleeve.

## Universe

910 configured symbols (`pipeline/config/advisor_universe.json`), 40 published per refresh.
Eligibility thresholds: $5 minimum price, $300M minimum market cap, $2M minimum 60-day median
dollar volume, 253 minimum trading sessions (`docs/RESEARCH-CONTRACT.md`). No IPO-seasoning
window, no delisted-security replay in scoring.

## Rebalance / refresh assumptions

No fixed rebalance cadence. `refresh-advisor.yml` runs a full sweep once and two fast
refreshes on trading days (07:00, 12:00, 15:00 ET). Signal timestamp is the refresh's own
`generated_at`; there is no same-close-execution guard.

## Data sources and availability lags

Yahoo Finance (price/quote/statements — restated only, no as-reported history), Alpha
Vantage (max 5 symbols/refresh, overview/earnings/macro), Marketaux (news sentiment,
opt-in), FRED (macro regime, opt-in), SEC EDGAR (Form 4 insider, theme signals — needs
`SEC_USER_AGENT`), Financial Modeling Prep (congressional disclosures, weekly). Statement
data typically lags 1-3 months after fiscal period end. See `docs/DATA-LINEAGE.md`.

## Confidence

Not a single number: `pipeline/confidence.py` publishes completeness, freshness,
source_reliability, peer_sample, and model_agreement components alongside the scalar.
`historical_calibration` is always `null` — the IC harness has not accumulated enough
prospective periods to report one (see "Validation state").

## Validation state

**No promotion has occurred.** As of `docs/BASELINE-2026-08-06.md`, the IC harness had
observed 0 of the 24 eligible periods `minimum_icir_periods` requires, across 6 refreshes.
No IC, Sharpe, drawdown, or hit-rate statistic reported anywhere in this repository should be
read as a validated result — see `pipeline/reports/stability.json` and
`docs/VALIDATION-METHODOLOGY.md` for what the harness actually measures once it has enough
history.

## Transaction costs

`pipeline/costs.py` models `half_spread + fees + volatility_scaled_impact` across three
scenarios, with a labeled (not measured) spread proxy — see `docs/TRANSACTION-COSTS.md`. Not
yet wired into the validation harness, which still uses a flat 10bps assumption.

## Known limitations

See `docs/LIMITATIONS.md` for the full list. Headline items: no sector-residual forecast
target implemented (raw forward return only), only 1 of 6 portfolio-construction methods
built, 9 of 16 screen presets are specification-only, 12 of 32 scored fundamentals metrics
have no formal `metric_registry.json` declaration yet.

## Promotion status

**Champion:** `bands_champion` (sector/industry-band fundamental scoring,
`advisor_engine.py`), in production.

**Challengers**, all shadow-only, published in `score_variants` alongside the champion but
never selected: `cross_sectional_normalization`, and the `signal_corrections` family
(`normalization`, `short_horizon`, `confidence_shrinkage`, `modifier_recalibration`,
cumulative). None have passed the promotion gates in `docs/RESEARCH-CONTRACT.md` — none have
been evaluated against them, because the IC harness has not reached minimum history.
