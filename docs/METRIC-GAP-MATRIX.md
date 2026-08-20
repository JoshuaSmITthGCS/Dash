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
| MWR/XIRR | Exists, dead code | `:448-488` (`solveXirr`), tested at `portfolioAnalytics.test.js:137` | Never imported by any page |
| Performance reconciliation / P&L bridge | Exists, dead code | `:559-566` (`trackedAllTimeEarnings`), tested at `:326-328` | Never called outside its test; also not a true bridge (no FX/tax line) |
| Days-to-liquidate | Exists, weak | `:1125-1138` | Computed but only feeds a blended composite score, never surfaced standalone |
| Transaction-cost drag | Exists, weak | `portfolioStatistics.js:513-524` | Hardcoded permanently `available:false` stub |
| User portfolio turnover | Exists, weak | `portfolioStatistics.js:496-521`, called with no args at `portfolioAnalyticsModel.js:115` | Wiring bug — always evaluates an empty rebalance list |
| Current drawdown *duration* | Exists, weak | depth exists, duration (days-in-drawdown) not found | — |
| Data-quality panel | Exists, weak | `src/components/DataStatus.jsx`, global | Pipeline/research-wide, not scoped to the user's own holdings |
| Full performance attribution (Brinson-style) | Exists, weak | `src/lib/portfolioAttribution.js` | Self-documented as single-factor CAPM-style, not sector/style decomposition |
| Rolling metric stability | Exists, weak | `portfolioStatistics.js:314,412-413` | Sharpe only, 60/120d only (not 63/126/252d; no vol/beta/TE/correlation/drawdown) |
| Weighted ETF expense ratio (user's holdings) | Can derive locally | per-fund `expense_ratio` already published (`Picks.jsx:139`) | Just needs aggregation across the user's actual positions — no new data |
| Benchmark policy (constructed multi-asset) | Can derive locally | `portfolioModels.js:203-232` has 4 fixed single-index candidates | Needs a blended-weight construction on top of existing benchmark data |
| Tax-lot ledger | Requires new architecture | none found | Needs a new per-lot data model, not just a new metric — see Model Risk Register |
| Wash-sale warning engine | Requires new architecture, blocked | none found | Blocked on the tax-lot ledger existing first |
| FX exposure/attribution | Not currently material | no international-equity-specific handling found | Revisit if international equities/ETFs become material holdings |
| Fixed-income duration/yield/credit | Not currently material | generic equity-style treatment only | Revisit if bonds become material holdings |
| Options Greeks beyond delta (gamma/theta/vega) | Requires new free source or paid data | only delta computed internally (Black-Scholes, r=0), not surfaced; no gamma/theta/vega anywhere | `pipeline/options_common.py:81-127` |
| IV term structure/skew | Requires paid data | single-expiration IV only from the existing yfinance chain snapshot | — |
| Historical VaR alongside ES | Not worth adding yet | ES (a stricter tail measure per Basel FRTB's own migration rationale) already exists | Add only if a specific consumer needs VaR's percentile framing ES doesn't provide |
| Ulcer index / Omega ratio | Not worth adding yet | no clear investment decision identified that Sharpe/Sortino/Calmar + drawdown don't already inform | Revisit only if a specific gap in the existing risk suite is identified |

## Duplicate/divergent implementations found (not a gap, but worth tracking)

| Concept | Implementation A | Implementation B | Status |
|---|---|---|---|
| `momentum_12_1` | `pipeline/risk_metrics.py:36` (champion score, daily-offset) | `pipeline/research_screens_v2.py:39-54` (standalone Momentum screen, calendar-month-end resample) | Genuinely separate; can diverge around trading-calendar gaps. See `docs/AUDIT-ROADMAP.md` item 27. |
| Confidence-shrinkage formula | `advisor_engine.py:962` (top-level, `0.8+0.2×coverage`, retired 2026-08-12) | `scorer.py:642,680` (fundamentals-category, `0.65+0.35×coverage`, still live) | Top level fixed; category level is not. See roadmap item 8. |
| Monte Carlo simulators | `src/lib/projectionEngine.js` (user planning, JS, block bootstrap) | `pipeline/evaluation.py`/`pipeline/validation/deflated_sharpe.py` (strategy validation, Python, CSCV/PBO) / `pipeline/monte_carlo_projection.py` (strategy forward-projection) | Intentional separation of concerns, not confusion — no action needed. |
