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
  represents a completed, statistically meaningful test.
- **No sector-residual forecast target is implemented.** The research contract's primary
  target (63-trading-day forward sector-residual return) is specified but not built;
  `ic_harness.py` scores raw forward return over calendar-day horizons instead
  (`docs/RESEARCH-CONTRACT.md`).
- **No promotion has occurred**, and none is being proposed by this upgrade.

## Model coverage

- **Only 2 of 14 specified alpha sleeves are wired: value, quality, growth** (plus a partial
  momentum factor table). The other 11 (short/long reversal, mean reversion, GARP, catalyst,
  dividend, low-volatility, trend, insider/political, multi-factor composite) are not built as
  standalone sleeve modules — some of their underlying factors exist elsewhere in the
  codebase (`research_screens_v2.py`), but nothing combines them into the sleeve interface yet.
- **9 of 16 screen presets are specification-only** — declared with their exact ranking/filter
  rules but no scoring function exists (`docs/SCREEN-PRESETS.md`).
- **Only 1 of 6 portfolio-construction methods is built** (score-weighted top-N;
  `docs/PORTFOLIO-CONSTRUCTION.md`).
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
