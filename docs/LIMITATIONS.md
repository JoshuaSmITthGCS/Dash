# Limitations

Stated explicitly rather than left implicit. Cross-referenced to where each is discussed in
more depth.

## Data

- **No as-reported fundamentals history.** Yahoo serves restated statements only; a
  company's reported numbers as they stood on the actual filing date cannot be reconstructed
  retroactively (`docs/RESEARCH-CONTRACT.md`, `docs/DATA-LINEAGE.md`).
- **No delisting/survivorship data.** The PIT store logs universe membership changes
  (`pipeline/pit_store.py universe.jsonl`) but scoring does not replay a delisted name's
  history — delisted-name effects are not modeled.
- **12 of 32 scored fundamentals metrics have no formal `metric_registry.json` declaration**
  (`docs/FEATURE-REGISTRY.md`) — direction is still correct (sourced from `scorer.py`'s
  actual scoring code), but the formal definition/provider/period metadata is missing.
- **Analyst estimate coverage is a small subset** (`collect_estimates.py`, 8 tickers) — any
  catalyst/revision-based ranking is starved of data for the vast majority of the universe.
- **No quoted or effective bid-ask spread data from any provider.** `pipeline/costs.py` uses
  a labeled liquidity-tiered proxy, not measured spreads.
- **8-K, DEF 14A, and 10-K/10-Q filing signals are form/Item-code classifications, not
  text-parsed.** `pipeline/edgar_filing_signals.py` scores from SEC's own 8-K Item taxonomy
  and DEF 14A form variant (`DEFC14A`/`DEFA14A`) alone — never the filing's actual prose, exact
  say-on-pay vote percentages, or dollar figures. This is weaker, more mechanical evidence than
  Form 4 (which is parsed structured XBRL): a materially negative 8-K Item code is a reliable
  signal, but the absence of one is not evidence the underlying event was immaterial, only that
  it wasn't filed under a code this lookup recognizes.
- **Sector operating KPIs (ARPU/churn, comps, NIM/efficiency ratio, FFO/AFFO, ARR/NRR, rate
  base, capacity factor, book-to-bill, and similar) are not computed anywhere in the
  pipeline.** `business_profiles.json` names them as the intended replacement for a suppressed
  generic metric (e.g. a bank's `net_interest_margin`, a REIT's `funds_from_operations`) so the
  metric goes null instead of scoring the wrong thing, but no provider fetches or derives a
  value to fill that gap — these KPIs live in MD&A prose and 8-K earnings-release
  supplementals, not structured SEC XBRL, and this pipeline deliberately does not parse
  free-text filings (see the 8-K limitation above). Fixing this is a new text/table-extraction
  provider or a vendor feed, not a config change. `applicability_matrix.json` / `classify_profile()`
  (`pipeline/canonical_metrics.py`) do route more business profiles than this — including
  `mortgage_reit`, `homebuilder`, `independent_power_producer`, and `capital_markets_firm` — to
  suppress industrial-style metrics (P/E, EV/EBITDA, Altman Z, inventory/DSO days) that are
  actively misleading for that profile, which is real and load-bearing today; only the
  *replacement* KPI values remain unimplemented.

## Validation

- **The IC harness has not reached minimum history.** 0 of 24 eligible periods as of
  `docs/BASELINE-2026-08-06.md`. No IC, ICIR, deflated Sharpe, or PBO statistic in this repo
  represents a completed, statistically meaningful test. This gates component IC, score
  calibration, and any promotion.
- **The score has no empirical calibration.** `score_calibration.py` publishes
  `insufficient_data` for every bucket and `confidence_detail.historical_calibration` stays
  null. A score of 84 is a rank, not a statement about historical outcomes
  (`docs/ALGORITHM-RESEARCH-RESULTS.md` §11).
- **No signal has been promoted.** The five PROMOTE decisions in the registry are all defect
  fixes to existing behaviour, not new evidence; 51 variants have been tried across 14
  experiments (`pipeline/reports/experiment_registry.json`).
- **The factor-controlled evidence still points to a factor tilt, not proven residual alpha.**
  Six-factor annualized alpha is +3.06% at Newey-West |t| = 0.680. Six smaller-cap/breadth ETF
  legs are beaten with significant single-benchmark alpha, but SPY, VTV, the fixed size/value
  blend, and the six-factor model are not. That evidence comes from a survivorship-biased
  five-year backtest using
  approximated filing timestamps and raw (not sector-residual) returns, so it is the best
  available reading rather than a settled finding
  (`pipeline/reports/{factor_regression_p0,benchmark_alpha_regressions}.json`).
- **The strategy's returns are regime-dependent.** Strongly positive in falling rates and
  drawdowns, negative in rising rates (−6.7pp annualized against SPY). Full-sample
  statistics average over a split this wide.
- **The score's predictive sign flipped with the March 2021 market rotation, and only one
  such transition has ever been observed.** The Round 11 regime diagnosis
  (`pipeline/regime_diagnosis.py`; `research/audit/round11/regime_diagnosis.json`) found a
  significant break in the champion's monthly rank IC at 2021-03 (permutation p = 0.019,
  scan-adjusted): mean IC −0.023 before, +0.038 after; anti-predictive every year 2018–2020.
  Consequences stated plainly: (a) every full-panel backtest statistic in this repository
  mixes an era where the score worked backwards with one where it worked, (b) the
  post-2021 positive read is post hoc — the era was identified in the same data it is
  measured on, (c) with n = 1 regime transition, no regime-switching or regime-detection
  model can be built falsifiably from this history, and (d) the edge, such as it is, is
  conditional on the current regime persisting. The `rolling_ic_regime` metric in
  `public/data/validation/signal_metrics.json` is the monitoring line for a future turn; it
  is a detector of decay after the fact, not a predictor of it.
- **No sector-specific weighting beats the uniform champion weights on this panel.** Two
  500-candidate-per-sector out-of-sample searches (full universe and growth/quality-filtered)
  returned 0 of 11 sectors clearing pre-registered gates (Round 11,
  `research/audit/round11/`). This is evidence the uniform weighting is adequate per sector
  on the available data — not evidence that sector economics are identical.

*Closed in this pass:* the sector-residual, trading-session forecast target is now implemented
(`docs/RESEARCH-CONTRACT.md` §2), as are purge/embargo controls.

## Model coverage

- **Only 2 of 14 specified alpha sleeves are wired: value, quality, growth** (plus a partial
  momentum factor table). The other 11 (short/long reversal, mean reversion, GARP, catalyst,
  dividend, low-volatility, trend, insider/political, multi-factor composite) are not built as
  standalone sleeve modules — some of their underlying factors exist elsewhere in the
  codebase (`research_screens_v2.py`), but nothing combines them into the sleeve interface yet.
- **9 of 16 screen presets are specification-only** — declared with their exact ranking/filter
  rules but no scoring function exists (`docs/SCREEN-PRESETS.md`).
- **Only 1 of 6 portfolio-construction methods is built** (score-weighted top-N;
  `docs/PORTFOLIO-CONSTRUCTION.md`). Four turnover controls exist as tested challengers
  (`portfolio_construction.py`), now measured in-sample on the 360-symbol price cache
  (`pipeline/reports/turnover_control_matrix.json`) but with no walk-forward evidence, and
  none promoted. The results are non-monotonic in their own parameters, which is the usual
  signature of noise.
- **Portfolio size and weighting matrices cannot be evaluated from committed data.** The
  backtest artifact stores only each rebalance's top-20 picks — no full ranking and no per-name
  returns — so top-10/40/60 and alternative weighting schemes cannot be replayed offline.
- **The bounded technical-indicator family is 4 indicators**, not the broader set discussed in
  the literature review that motivated this — declined as likely data-snooping evidence
  (`technical_indicators.py`'s module docstring).
- **The 4 technical indicators' cross-sectional correlation has not been measured** — chosen
  for economic-family diversity, not verified independence (`feature_registry.json`
  `correlation_dedup_policy`).

## Portfolio attribution

- **No sector-index factor decomposition.** The portfolio move explanation
  (`portfolioAttribution.js`) splits market vs. stock-specific by beta, and separately groups
  the stock-specific component by sector *within the user's own holdings* — this is not a
  comparison against a market sector benchmark, because no daily sector-index return is
  fetched anywhere in this codebase.
- **No catalyst/news attribution.** Linking a portfolio move to a specific headline needs
  event classification work that was not built in this pass.

## Verification

- **This sandbox's outbound proxy blocks Firebase entirely** (confirmed by a pre-existing
  `auth/invalid-api-key` test failure, unrelated to this upgrade). Every Firebase-authenticated
  flow added or changed in this upgrade (the portfolio move explanation, the watchlist
  migration and price targets) was verified via unit tests on the underlying pure logic,
  lint, and build — **not** via an actual browser session with a signed-in user. A real
  end-to-end check of these flows has not been performed.
- **No live production refresh was run.** All Python-side fixes (the enrichment bug, the
  confidence redesign, the stability diagnostics) were verified against the real committed
  historical data and offline/mocked reproductions, not a fresh live pipeline run — this
  sandbox also cannot reach Yahoo Finance (same outbound proxy restriction).
