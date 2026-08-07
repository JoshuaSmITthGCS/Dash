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

## Validation

- **The IC harness has not reached minimum history.** 0 of 24 eligible periods as of
  `docs/BASELINE-2026-08-06.md`. No IC, ICIR, deflated Sharpe, or PBO statistic in this repo
  represents a completed, statistically meaningful test. This gates component IC, score
  calibration, and any promotion.
- **The score has no empirical calibration.** `score_calibration.py` publishes
  `insufficient_data` for every bucket and `confidence_detail.historical_calibration` stays
  null. A score of 84 is a rank, not a statement about historical outcomes
  (`docs/ALGORITHM-RESEARCH-RESULTS.md` §11).
- **No promotion has occurred.** Three defect fixes shipped to the champion; no new signal has
  been promoted, and 47 variants have been tried across 12 experiments
  (`pipeline/reports/experiment_registry.json`).
- **The only measured evidence points to a factor tilt, not alpha.** Six-factor annualized
  alpha −2.57% at Newey-West |t| = 0.437; none of 14 tradeable benchmarks beaten with
  significant alpha. That evidence comes from a survivorship-biased five-year backtest using
  approximated filing timestamps and raw (not sector-residual) returns, so it is the best
  available reading rather than a settled finding (`docs/ALGORITHM-RESEARCH-RESULTS.md`).
- **The strategy's returns are regime-dependent.** Strongly positive in falling rates and
  drawdowns, strongly negative in rising rates (−16.9pp annualized against SPY). Full-sample
  statistics average over a split this wide.

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
  (`portfolio_construction.py`) but have never been measured against a backtest.
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
