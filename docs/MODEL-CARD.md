# Model Card — ValueSignal Research Score

## What it predicts

The champion score is a cross-sectional rank of companies by evidence quality — fundamentals
(78%), market behavior (18%, includes the new technical_extended factor at ~6% of that
share), and news sentiment (4%, dropped from the denominator when a company has no qualifying
coverage). It is designed as a research-evidence summary, not a validated forecast of forward
returns.

**It is not a probability.** A score of 84 is a rank position, not an 84% chance of anything.
No score bucket has enough closed forward windows to carry an empirical meaning — see
"Validation state".

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
`SEC_USER_AGENT`), Financial Modeling Prep and the keyless public House/Senate disclosure
datasets (congressional disclosures, weekly). Statement
data typically lags 1-3 months after fiscal period end. See `docs/DATA-LINEAGE.md`.

## Confidence

Not a single number: `pipeline/confidence.py` publishes completeness, freshness,
source_reliability, peer_sample, and model_agreement components alongside the scalar.
`historical_calibration` is always `null` — the IC harness has not accumulated enough
prospective periods to report one (see "Validation state"). `score_calibration.py` will
populate it once at least one score band clears 30 closed observations, and refuses to before
then.

Confidence measures **how reliable the evidence behind a rank is**, never the probability of a
price move. The UI labels it "Evidence confidence" for that reason.

## Validation state

**No signal has been promoted.** The IC harness has observed 0 of the 24 eligible periods
`minimum_icir_periods` requires. No IC, Sharpe, drawdown, or hit-rate statistic reported
anywhere in this repository should be read as a validated result.

**What has been measured**, from a survivorship-biased five-year backtest that uses
approximated filing timestamps and raw rather than sector-residual returns
(`docs/ALGORITHM-RESEARCH-RESULTS.md`):

- Six-factor regression (Newey-West, 58 months): annualized alpha **−2.57%, |t| = 0.437**.
  Significant loadings are market (6.50), size (2.06) and momentum (2.50) — not the value and
  profitability the score is mostly built from.
- Against 14 tradeable style/size ETFs: **none beaten with statistically significant alpha**,
  largest |t| = 1.11. VTV returns more at lower volatility with a shallower drawdown.
- Regime-dependent: **+10.3pp** annualized against SPY in bear markets and in falling rates,
  **−16.9pp** in rising rates.

**Current classification: B — a transparent factor tilt with no demonstrated residual alpha**,
carrying a real Verdict D caveat because the contract's own target has never been measured.
Do not present SPY outperformance as this model's objective.

The forecast target is now implemented as specified: 63 **trading sessions**, sector-residual,
preregistered as primary. Deflation uses the honest trial count (44 variants across 12
experiments, `pipeline/reports/experiment_registry.json`), not the 5 configured shadow
strategies.

## Transaction costs

`pipeline/costs.py` models `half_spread + fees + volatility_scaled_impact` across three
scenarios, with a labeled (not measured) spread proxy — see `docs/TRANSACTION-COSTS.md`. Wired
into both `backtest_monthly.py` and `ic_harness.py` behind `validation.cost_model`, defaulting
to the original flat 10bps so prior results reproduce exactly.

At the realized 64.9% monthly turnover, the published 10bps costs **78bps a year**, or 7.0% of
gross return. A tiered model would need a rate above **35.7bps one-way** to give up 200bps more;
the worst rate the model produces without a volatility input is 25bps
(`pipeline/reports/cost_sensitivity.json`).

## Known limitations

See `docs/LIMITATIONS.md` for the full list. Headline items: no empirical score calibration,
no residual alpha demonstrated after factor controls, statement-derived metrics computed only
for a shortlist (no unenriched name reaches the top 100 —
`docs/ENRICHMENT-BIAS-ANALYSIS.md`), only 1 of 6 portfolio-construction methods built, 9 of 16
screen presets are specification-only.

## Promotion status

**Champion:** `bands_champion` (sector/industry-band fundamental scoring,
`advisor_engine.py`), in production.

**Challengers**, all shadow-only, published in `score_variants` alongside the champion but
never selected: `cross_sectional_normalization`, and the `signal_corrections` family
(`normalization`, `short_horizon`, `confidence_shrinkage`, `modifier_recalibration`,
cumulative). None have passed the promotion gates in `docs/RESEARCH-CONTRACT.md` — none have
been evaluated against them, because the IC harness has not reached minimum history.
