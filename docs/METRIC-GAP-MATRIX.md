# Metric Gap Matrix

Every candidate metric from the merged master-audit prompt's §10 (portfolio analytics) and
adjacent sections, classified against actual code as of this verification pass (see
`docs/AUDIT-VERIFICATION-RESULTS.md` for full evidence). Classification key:

- **Exists** — implemented, tested, and wired into a page the user can actually see.
- **Exists, dead code** — implemented and unit-tested, but never imported by any page. Cheapest
  category to close: no new math, just a missing import and a UI slot.
- **Exists, weak** — implemented but incomplete, wrongly scoped, or silently disabled by a wiring
  bug.
- **Can derive locally** — no new data source needed; can be built from data already in the
  pipeline/frontend.
- **Requires new free source** — needs a provider not currently wired in (see
  `docs/API-DATA-SOURCE-PLAN.md`).
- **Requires paid data** — no free-tier source covers it.
- **Not worth adding** — flagged as a candidate in the merged prompt but this pass found no
  investment-decision this would improve beyond what already exists.

| Metric | Classification | Evidence | Note |
|---|---|---|---|
| HHI concentration | Exists | `src/lib/portfolioAnalytics.js:568-569` | — |
| Effective holdings count | Exists | `:572-575` | — |
| Correlation analytics (252d/60-obs) | Exists | `:777-823`; config `pipeline/config/settings.json:237-238` | — |
| Effective bets (eigenvalue) | Exists | `:790-795` | — |
| Diversification ratio | Exists | `:796-816` | — |
| ETF look-through w/ unresolved disclosure | Exists | `:616-670` | — |
| Marginal/percent risk contribution (→100%) | Exists | `:843-867` | — |
| Historical Expected Shortfall (worst 5%) | Exists | `:826-830`; second impl at `portfolioStatistics.js:274-299` | — |
| Tracking error | Exists | `:872-880`; `portfolioStatistics.js:452` | — |
| Active-share gating (constituents + 80% coverage) | Exists | `:883-897`; `settings.json:256` | — |
| Information ratio | Exists | `:1096-1102,1115` | Shown on "Data overview," not `/portfolio/performance` |
| Realized/unrealized gain-loss | Exists | `usePortfolioForms.js:112-126` | Average-cost only, no lot selection |
| Current drawdown | Exists | `:1093-1095,1118` | — |
| MWR/XIRR | **Exists — wired this session** | `portfolioAnalytics.js` `solveXirr`/`portfolioReturnSummary`; rendered in `src/pages/portfolio/Performance.jsx` | Needs recorded account-value history + settled cash flows to show a real (non-"accumulating") number; both now capturable via the cash-flow ledger form and auto-snapshot effect built this session |
| Performance reconciliation / P&L bridge | **Exists — built this session** | `portfolioAnalytics.js::portfolioReconciliationBridge`, rendered in `Performance.jsx` | Now a true bridge (deposits/withdrawals/dividends/fees/realized+unrealized gain, FX/taxes/trading-costs explicitly disclosed as untracked) with a cent-tolerance reconciliation check, not just `trackedAllTimeEarnings`'s simpler all-time total (which remains dead code — superseded, not wired) |
| Days-to-liquidate | Exists, weak | `:1125-1138` | Computed but only feeds a blended composite score, never surfaced standalone |
| Transaction-cost drag | Exists, weak | `portfolioStatistics.js:513-524` | Hardcoded permanently `available:false` stub |
| User portfolio turnover | **Fixed this session** | `portfolioStatistics.js::executionStatistics`, now called with a real rebalance ledger (`usePortfolioForms.js` captures before/after cost-basis weights on every add/edit/remove/sell) | Was a wiring bug (called with no args); now backed by real, tested data |
| Current drawdown *duration* | Exists, weak | depth exists, duration (days-in-drawdown) not found | — |
| Data-quality panel (pipeline-wide) | Exists, weak | `src/components/DataStatus.jsx`, global | Pipeline/research-wide, not scoped to the user's own holdings |
| Data-quality panel (holdings-scoped) | **Exists — built this session** | `src/pages/portfolio/HoldingsDataQuality.jsx`, wired into `DataOverview.jsx` | Reads per-ticker `data_coverage`/`data_quality_violations`/`last_polled_at` the pipeline already publishes (`portfolio_coverage`) but no page surfaced before |
| Full performance attribution (Brinson-style) | Exists, weak | `src/lib/portfolioAttribution.js` | Self-documented as single-factor CAPM-style, not sector/style decomposition |
| Rolling metric stability | Exists, weak | `portfolioStatistics.js:314,412-413` | Sharpe only, 60/120d only (not 63/126/252d; no vol/beta/TE/correlation/drawdown) |
| Weighted ETF expense ratio (user's holdings) | **Exists — built this session** | `src/lib/portfolioAnalytics.js::weightedExpenseRatio`, rendered via `src/pages/portfolio/FundCostOverview.jsx` on Data overview | Dollar-weighted by current value across held funds only; per-fund `expense_ratio` already published (`Picks.jsx:139`), this just aggregates it against real position sizes |
| Benchmark policy (constructed multi-asset) | **Exists — built this session** | `src/lib/portfolioStatistics.js::constructedBenchmarkFit`, rendered as new "Constructed benchmark" rows in the existing Benchmark Fit metric group | Non-negative weights across the same 4 candidates (`portfolioModels.js:203-232`) summing to 1, fit by minimizing tracking error against the portfolio's own returns (returns-based style analysis) — alongside, not replacing, the existing single best-fit index |
| Tax-lot ledger | Requires new architecture | none found | Needs a new per-lot data model, not just a new metric — see Model Risk Register |
| Wash-sale warning engine | Requires new architecture, blocked | none found | Blocked on the tax-lot ledger existing first |
| FX exposure/attribution | Not currently material | no international-equity-specific handling found | Revisit if international equities/ETFs become material holdings |
| Fixed-income duration/yield/credit | Not currently material | generic equity-style treatment only | Revisit if bonds become material holdings |
| Options Greeks beyond delta (gamma/theta/vega) | Requires new free source or paid data | only delta computed internally (Black-Scholes, r=0), not surfaced; no gamma/theta/vega anywhere | `pipeline/options_common.py:81-127` |
| IV term structure/skew | Requires paid data | single-expiration IV only from the existing yfinance chain snapshot | — |
| Historical VaR alongside ES | Not worth adding yet | ES (a stricter tail measure per Basel FRTB's own migration rationale) already exists | Add only if a specific consumer needs VaR's percentile framing ES doesn't provide |
| Ulcer index / Omega ratio | Not worth adding yet | no clear investment decision identified that Sharpe/Sortino/Calmar + drawdown don't already inform | Revisit only if a specific gap in the existing risk suite is identified |

## External vs. internal data need (Master Remediation Prompt v3, Part C)

Full detail and provider-by-provider evidence in `docs/API-DATA-SOURCE-PLAN.md`. Summary of which
KPIs above genuinely need a new external data source vs. which don't:

| Needs no new external source (build from what exists) | Needs a new external source |
|---|---|
| XIRR/MWR, P&L reconciliation bridge, turnover — all built this session from transactions + recorded NAV, no market-data API involved | Independent corporate-action truth (B4) — needs an event source distinct from the vendor-adjusted price series |
| Realized/unrealized lot P&L, wash-sale warnings — need transaction/identity logic (B3), not a market API | As-filed fundamentals spine — SEC EDGAR already partially wired as a fallback (`edgar_enrichment.py`); the real task is a precedence inversion, not new ingestion |
| Current drawdown/duration, weighted ETF expense ratio, risk-contribution HHI | Vintage-aware macro (FRED realtime/vintage parameters, not currently used) |
| Holdings-level data-quality display — built this session entirely from fields the pipeline already publishes | Short interest cross-check (FINRA), fund-holdings validation (SEC N-PORT) |

## Duplicate/divergent implementations found (not a gap, but worth tracking)

| Concept | Implementation A | Implementation B | Status |
|---|---|---|---|
| `momentum_12_1` | `pipeline/risk_metrics.py:36` (champion score, daily-offset) | `pipeline/research_screens_v2.py:39-54` (standalone Momentum screen, calendar-month-end resample) | Genuinely separate; can diverge around trading-calendar gaps. See `docs/AUDIT-ROADMAP.md` item 27. |
| Confidence-shrinkage formula | `advisor_engine.py` top-level (`0.8+0.2×coverage`, retired from the champion 2026-08-12) | `scorer.py::_band_valuation_score` (fundamentals-category, `0.65+0.35×coverage`) | Both are bypassed by the champion's published score (confirmed this session — `build_research()` uses `raw_score`, not either multiplied value). The category-level one still drives `fetch_advisor.py::enrich()`'s enrichment-priority sort key. See roadmap item 8. |
| Monte Carlo simulators | `src/lib/projectionEngine.js` (user planning, JS, block bootstrap) | `pipeline/evaluation.py`/`pipeline/validation/deflated_sharpe.py` (strategy validation, Python, CSCV/PBO) / `pipeline/monte_carlo_projection.py` (strategy forward-projection) | Intentional separation of concerns, not confusion — no action needed. |
