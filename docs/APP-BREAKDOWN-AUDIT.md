# App Breakdown & Audit — ValueSignal, End to End

A single-document map of the whole product: what it is, how data moves from provider APIs to a
rendered screen, every route and what it does, and what's implemented versus what's a known
gap. This is the "entire app" companion to `docs/SCORING-METRICS-BREAKDOWN.md` (every score,
explained and distinguished), `docs/MOBILE-BREAKDOWN-AUDIT.md`, and
`docs/DESKTOP-BREAKDOWN-AUDIT.md` (the mobile- and desktop-specific slices of this same app).
An auto-generated, always-fresh sibling exists at `APP-COMPLETE-BREAKDOWN.md` (repo root,
regenerated via `npm run docs:breakdown` from live route/config/data-file introspection) — that
one is the source of truth for exact current counts; this one is the narrative walkthrough.

## 1. What ValueSignal is

A fundamentals-first equity, ETF, and portfolio research platform. Static JSON data, produced
by a Python pipeline on a schedule, is served to a client-side-only React app — there is no
backend API server for research data (`FULL-AUDIT-REPORT.md` flags this as a deliberate,
documented tradeoff, not an oversight: no SSR/SSG). User-specific state (portfolio holdings,
watchlist, planning inputs, alerts) lives in Firebase/Firestore behind auth.

Non-negotiable framing carried through every score and every page: **general research
information, not individualized investment advice.** Every label is a research tier
(HIGH CONVICTION / WATCH / NEUTRAL / ATTRACTIVE / PROMISING / MIXED / CAUTION), never "BUY."

## 2. Tech stack

| Layer | Choice |
|---|---|
| Frontend framework | React 18.3, Vite 8 (rolldown build, manual Firebase chunk-splitting — see `vite.config.js`) |
| Routing | `react-router-dom` v6, single `<Routes>` block in `src/App.jsx`; every page but `Dashboard` is `React.lazy()` + `<Suspense>` |
| Styling | One hand-rolled global stylesheet, `src/styles/global.css`, CSS custom-property design tokens, no CSS framework |
| Data pipeline | Python 3, 87 top-level scripts under `pipeline/` |
| Data transport | Static JSON published to `public/data/**`, fetched client-side via `src/lib/useData.js` (localStorage caching + schema migration, `src/lib/schemaMigrations.js`) |
| Auth / user data | Firebase Auth + Firestore, `src/lib/FirebaseAuthContext.jsx` |
| Charts | Recharts (see `docs/RECHARTS_3.md` for the v3 migration notes) |
| Virtualization | `@tanstack/react-virtual` (`ResultCards.jsx`, `MobileVirtualList.jsx`) for lists over 50 rows |
| Testing | Vitest + `@testing-library/react` + jsdom, co-located `*.test.jsx` files |
| Linting | ESLint flat config, `eslint.config.js` |
| Hosting | Netlify (`netlify.toml`), 3 serverless functions (`netlify/functions/`: `alert-push.mjs`, `portfolio-prices.mjs`, `refresh-data.mjs`) |
| CI / scheduling | GitHub Actions — `ci.yml` (build/test/lint), `refresh-advisor.yml` (full sweep + 3 intraday fast refreshes on trading days), `congress-trades.yml`, `demo-data.yml`, `marketstack-premarket.yml` |

## 3. Data flow — provider to pixel

```
Provider APIs (Yahoo, Alpha Vantage, Marketaux, FRED, SEC EDGAR, Financial Modeling Prep)
        │
        ▼
pipeline/*.py  (87 scripts: fetchers, scorers, screens, validators, explainability)
        │  point-in-time storage: pipeline/pit_store/
        │  config: pipeline/config/settings.json, advisor_universe.json, universe.json
        ▼
public/data/**.json  (advisor.json, etfs.json, screens/*.json, signals.json, factors/french.json, ...)
        │  every artifact stamped with: semantic_version, git_commit_sha, config_hash, generated_at
        ▼
src/lib/useData.js  (fetch + localStorage cache + schema migration)
        │
        ▼
React pages/components (this doc, §5) ── Firebase Auth/Firestore for user-owned state only
```

Refresh cadence: one full sweep plus three fast intraday refreshes at 07:00 / 12:00 / 15:00 ET
on trading days (`refresh-advisor.yml`). No same-close-execution guard — a signal's timestamp
is its own `generated_at`, not a promise about when it was tradeable.

## 4. Scoring and research pipeline — summary (full detail in `SCORING-METRICS-BREAKDOWN.md`)

Nine distinct scores run through this pipeline and are never silently blended into one
another: the champion research score (fundamentals 78% / market behavior 18% / news 4%), a v2
structural/timeliness shadow model, a standalone cross-sectional Momentum screen, a Tactical
(earnings-timeliness) screen, a Quality-Value screen, a congressional-trading political score,
a completely separate ETF composite model, a Watchlist quality score, and a Confidence
reliability multiplier that scales but never replaces evidence. Two production/shadow policy
engines (`recommendation_policy_v1`-equivalent `action_for()`, and `recommendation_policy_v2.py`)
decide sell/trim/watch/hold guidance; only the legacy policy controls production actions today.
See `docs/SCORING-METRICS-BREAKDOWN.md` for every formula, weight, and file:line reference.

## 5. Route map — every page and what it does

Source of truth: `src/App.jsx` (`NAV` and `MOBILE_NAV` arrays, `<Routes>` block).

| Route | Page component | Auth required | Purpose |
|---|---|---|---|
| `/` | `Dashboard.jsx` (eager-loaded, not lazy) | No | Landing "Financial Report" — home signal digest, theme exposure, refresh status |
| `/research` | `Picks.jsx` | No | Ranked research score leaderboard, stock and ETF results |
| `/search` | `Search.jsx` | No | Ticker/company search across the published universe |
| `/market` | `PolicyRadar.jsx` | No | Sector/policy-catalyst radar |
| `/portfolio` | `Portfolio.jsx` | **Yes** | User's held positions, performance analytics, benchmark comparison |
| `/portfolio/diversification` | `Diversification.jsx` | **Yes** | HHI concentration, effective-bets, diversification ratio analytics |
| `/portfolio/insights` | `Insights.jsx` | **Yes** | Portfolio-level factor and risk insights |
| `/finances` | `Finances.jsx` | **Yes** | Net worth / account tracking |
| `/planning` | `Planning.jsx` | **Yes** (or dev-only `?preview`) | Monte Carlo retirement/goal projection (5,000-path block resampling) |
| `/screens/fast-growth` | `FastGrowthScreen.jsx` | No | Fast-growth candidate screen |
| `/screens/momentum` | `ResearchScreen.jsx` (`screens/momentum.json`) | No | Standalone cross-sectional Momentum screen — see scoring doc §4 |
| `/screens/quality-value` | `ResearchScreen.jsx` (`screens/quality-value.json`) | No | Cheap-vs-own-history + quality screen — scoring doc §6 |
| `/screens/earnings` | `ResearchScreen.jsx` (`screens/earnings-timeliness.json`) | No | Tactical earnings-timeliness screen — scoring doc §5 |
| `/screens/matrix` | `ResearchScreen.jsx` (`screens/structural-tactical.json`) | No | Structural × tactical 2-axis matrix |
| `/screens/early-session` | `EarlySessionResearch.jsx` | No | Early-session research view |
| `/screens/politics` | `CongressTrades.jsx` | No | Congressional trading signal — scoring doc §3 |
| `/screens/shadow` | `ShadowPortfolios.jsx` | No | Shadow-policy backtested portfolios (v2 recommendation policy) |
| `/screens/validation` | `LiveValidation.jsx` | No | Per-ticker structural/timeliness validation, IC/ICIR diagnostics, quintile bucket returns |
| `/watchlist` | `Watchlist.jsx` | No | Watchlist with quality score, dip-buy/good-buy price targets |
| `/methodology` | `Methodology.jsx` | No | Plain-language explanation of the champion research score, live-config-driven |
| `/glossary` | `Glossary.jsx` | No | Term definitions |
| `/settings` | `Settings.jsx` | No | Theme, privacy mode, notification preferences |
| `/alerts` | `Alerts.jsx` | **Yes** | User alert rules (price move, earnings notice, pipeline staleness) |

Navigation is defined twice on purpose — `NAV` (12 items, desktop sidebar) and `MOBILE_NAV`
(5 items, bottom tab bar: Research / Search / Report / Portfolio / Planning) — because a phone
screen cannot fit the same information density as a sidebar. See `docs/MOBILE-BREAKDOWN-AUDIT.md`
and `docs/DESKTOP-BREAKDOWN-AUDIT.md` for the full split.

## 6. Feature inventory by area

- **Research & screens** — champion research score, 5 dedicated cross-sectional screens
  (momentum, quality-value, earnings-timeliness, structural-tactical matrix, fast-growth),
  early-session research, live shadow-model validation with IC/ICIR/quintile diagnostics.
- **Portfolio** — holdings tracking, Modified-Dietz performance, Sharpe/Sortino/Calmar/max
  drawdown, diversification scoring (HHI + effective bets + diversification ratio), factor
  exposure (Fama-French), correlation matrix (power-iteration eigenvalue decomposition).
- **Congressional trading** — 6-factor political score, cooling list (heavy selling clusters),
  committee-relevance mapping, cluster detection.
- **ETF research** — separate 5-bucket composite model, peer-group-relative percentiles,
  sector/holdings look-through, structural quality (issuer, leverage, replication, securities
  lending).
- **Planning** — Monte Carlo retirement projection (5,000 paths, 12-month block resampling to
  preserve return dependence), configurable allocation scenarios, sequence-of-returns example,
  goal planning.
- **Finances** — net worth and account tracking, separate from brokerage portfolio.
- **Watchlist** — sigmoid-blended quality score, ATR/volatility-scaled dip-buy targets,
  valuation-percentile-based good-buy targets.
- **Alerts** — price-move thresholds, earnings notices, pipeline-staleness alerts, quiet hours,
  push notification grouping (via `netlify/functions/alert-push.mjs`).
- **Explainability** — waterfall score attribution (`pipeline/explainability.py` →
  `ScoreExplainability.jsx`), anomaly-rule detection (e.g., margin/growth divergence,
  cash/earnings divergence), score history.
- **Auth & personalization** — Firebase email/password auth, theme customization, privacy mode
  (balance hiding), notification preferences.

## 7. Data sources and known lags

Yahoo Finance (price/quote/statements, restated only — no as-reported history), Alpha Vantage
(rate-limited to 5 symbols/refresh; overview, earnings, macro), Marketaux (news sentiment,
opt-in), FRED (macro regime, opt-in), SEC EDGAR (Form 4 insider activity, theme signals —
requires `SEC_USER_AGENT`), Financial Modeling Prep (congressional disclosures, weekly).
Statement data typically lags 1–3 months after fiscal period end. Full lineage:
`docs/DATA-LINEAGE.md`.

## 8. Universe and scale

910 configured symbols (`pipeline/config/advisor_universe.json`), 40 published per research
refresh (see `docs/MODEL-CARD.md` for the exact current counts, which the auto-generated
`APP-COMPLETE-BREAKDOWN.md` refreshes on every run). No IPO-seasoning window; no delisted-name
replay in live scoring, though point-in-time storage retains delisted membership for backtests.

## 9. Deliberate limitations (by design, not oversight)

- No SSR/SSG — first paint depends on client-side JS execution.
- No fixed rebalance cadence for the research score; it reflects whatever the last refresh saw.
- No score on the platform is a validated forward-return forecast — see "Validation state" in
  `docs/MODEL-CARD.md`: the IC harness has not yet accumulated enough prospective periods to
  promote any signal out of shadow status.
- ETFs and stocks are scored by two structurally incompatible models on purpose — corporate
  accounting ratios are not comparable to fund holdings.
- The v2 structural/timeliness model and v2 recommendation policy are shadow-only; they do not
  control production actions until they clear prospective, net-of-cost validation.

Full, itemized limitations: `docs/LIMITATIONS.md`. Historical (stale, retained for context
only) SEO/accessibility findings: `FULL-AUDIT-REPORT.md`. Formal root-cause audit of the
scoring pipeline: `docs/INVESTMENT_PLATFORM_AUDIT_V2.md`.

## 10. Where to look next

- Every score, formula, and weight: `docs/SCORING-METRICS-BREAKDOWN.md`
- Mobile-specific implementation: `docs/MOBILE-BREAKDOWN-AUDIT.md`
- Desktop-specific implementation: `docs/DESKTOP-BREAKDOWN-AUDIT.md`
- Live, auto-refreshed route/data-footprint counts: `APP-COMPLETE-BREAKDOWN.md` (repo root,
  regenerate with `npm run docs:breakdown`)
- Data provenance: `docs/DATA-LINEAGE.md`
- Model card (what the score does and does not predict): `docs/MODEL-CARD.md`
