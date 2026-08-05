# ValueSignal application: complete functional and calculation breakdown

Last source review: 2026-08-05  
Application name in code: **ValueSignal**  
Repository: `Dash`

This file describes what the current application actually does, what every route displays, where its data comes from, how its scores and projections are calculated, and how the interface changes on phones. It is based on the current React, CSS, Firebase, Netlify, JSON, and Python source—not only on the text shown inside the product.

> ValueSignal is a research and portfolio-tracking application. Its company scores, screens, guidance, and projections are research aids, not individualized financial advice, brokerage execution, or promised returns.

## 1. Product summary

ValueSignal has four connected product areas:

1. **Investment research**
   - Ranks stocks on a 0–100 fundamentals-first research score.
   - Ranks ETFs separately within like-for-like peer groups.
   - Explains business quality, valuation, market behavior, sentiment, modifiers, confidence, and evidence gaps.
   - Publishes focused momentum, quality/value, earnings, structural/tactical, early-session, political-disclosure, shadow-portfolio, and validation screens.

2. **Personal portfolio tracking**
   - Stores signed-in holdings in Firebase/Firestore.
   - Calculates value, cost basis, gains, allocation, diversification, resilience, performance, stop-loss context, benchmark comparisons, and cash-flow-adjusted results.
   - Stores cash movements, earnings activity, and observed portfolio snapshots.

3. **Planning and personal finances**
   - Tracks monthly income/expenses, savings pools, retirement/investing accounts, and annual contribution room.
   - Produces a retirement projection with nominal and inflation-adjusted balances.
   - Produces a separate “if the last year repeated” portfolio illustration for 1, 5, 10 years and retirement age.

4. **Data operations and validation**
   - A Python pipeline fetches, normalizes, scores, validates, and publishes static JSON.
   - Authorized users can dispatch a GitHub Actions refresh or re-score through a Netlify function.
   - The UI shows freshness/provider health and continues using the last successful cached payload when possible.

## 2. Technology and runtime architecture

### Front end

- React 18 with Vite.
- React Router with browser-history routes.
- Plain CSS with shared design tokens; no component-framework dependency.
- Firebase Authentication and Firestore for user-specific information.
- Static JSON under `public/data` for published research and market datasets.
- A PWA manifest for standalone/mobile home-screen installation.
- Google-hosted Bricolage Grotesque, Instrument Sans, and IBM Plex Mono fonts.

The app mounts as:

```text
React.StrictMode
└── PreferencesProvider
    └── BrowserRouter
        └── Firebase AuthProvider
            └── application shell and routes
```

The Financial Report route is eagerly bundled because it is the cold-start route. Every other page is lazy-loaded and displayed behind a route-level loading state.

### Research/data backend

The research backend is not a conventional request/response application server. The Python pipeline writes versioned JSON snapshots that the deployed client fetches as static files. Major sources include Yahoo Finance, Alpha Vantage, Marketaux, FRED, SEC EDGAR, and Financial Modeling Prep where configured.

### Server-side functions

- `refresh-data.mjs` verifies a Firebase ID token, checks an email allowlist, prevents overlapping runs, and dispatches the GitHub `refresh-advisor.yml` workflow.
- `portfolio-prices.mjs` verifies a Firebase ID token and fetches current/pre/post-market Yahoo quotes for at most 50 validated holdings symbols.
- Server credentials remain in environment variables; they are not published in browser JSON.

### Deployment

- Netlify runs `npm run build` and publishes `dist`.
- All paths redirect to `index.html` for client-side routing.
- Node 22 is configured.
- The PWA launches at `/`, uses standalone display where supported, and is portrait-primary.

## 3. Application shell, navigation, and access

### Desktop navigation

Above 900 px, a sticky 248 px left rail fills the viewport height. It contains:

- ValueSignal brand/home link.
- Financial Report.
- Research.
- Search.
- Portfolio, when signed in.
- Watchlist.
- Finances, when signed in.
- Screens, linking initially to Momentum.
- Methodology.
- Glossary.
- Settings.
- A research-only disclaimer.
- Signed-in profile, account settings, password change, and sign-out controls.

### Mobile navigation

At 900 px or narrower, the rail disappears. The user gets:

- A top header with the brand.
- Signed-in alert button with a live unread-event badge and a link to the in-app alert center.
- Privacy-mode balance toggle.
- Settings link.
- A fixed five-destination bottom bar: Research, Search, Report, Portfolio, Watchlist.
- Report is the raised central item.

The mobile Portfolio item is always visible. If the user is signed out, the route renders the Financial Report/Dashboard instead, and the login modal normally remains on top.

### Authentication behavior

- Firebase email/password authentication is used.
- On startup, auth resolution stops blocking after 1.2 seconds even if Firebase is slow; research can render in a signed-out state.
- Unless development `?preview` mode is active, a signed-out user sees the Firebase login/profile-selection modal.
- Portfolio, Portfolio Insights, Diversification, and Finances are route-protected by rendering the Dashboard when no user is signed in.
- User profiles store display name, email, legacy family color theme, timestamps, and dark-mode metadata. Actual interface theming is now controlled by PreferencesContext, not the legacy profile theme.

### Accessibility and global interaction behavior

- A skip link targets the main content.
- The main content can receive focus.
- Icon-only controls generally have labels.
- Mobile header controls are 40–44 px; bottom navigation targets are at least 54 px high.
- Inputs preserve a 16 px mobile font size to avoid iOS zoom.
- Safe-area insets protect content around notches and the home indicator.
- The page reserves 104–112 px below content so the fixed bottom navigation does not cover it.
- `prefers-reduced-motion` and the explicit reduced-motion setting reduce animations to effectively zero.
- Modal background scroll is locked; Escape and overlay clicks close stock details.

## 4. Route map and what every page does

### `/` — Financial Report

Data used: `report.json`, `advisor.json`, `etfs.json`, conditional `benchmark-report.json`, Firebase holdings/tracking, and live portfolio quotes.

If signed out or if there are no holdings, the route shows an empty-state prompt. Research, Market Pulse, focused screens, top signal, and watchlist support content can still appear around the personal-report gate.

With holdings, the page displays:

1. **Portfolio hero**
   - Current portfolio value.
   - Latest close-to-close dollar and percentage move.
   - After-hours move when real post-market Yahoo fields exist.
   - Manual after-hours refresh.
   - Position count and price coverage.
   - Total unrealized return.
   - Invested cost basis.

2. **Portfolio pulse**
   - A mood label based on contribution-adjusted return.
   - Today’s result.
   - Return versus contributions.
   - A consecutive benchmark-beating/trailing streak where available.

3. **Performance chart**
   - Periods: 1D, 1W, 1M, 3M, 6M, 1Y, All.
   - Up to three ETF benchmark proxies from SPY, QQQ, DIA, IWM, VTI, VEA, VWO, and VXUS.
   - Portfolio and benchmarks aligned to exactly the same dates and normalized to the same starting dollar value.
   - Current quantities are applied to historical closes; this is not reconstructed historical account value.
   - Charted earnings, charted high, observed intraday high, and tracked all-time earnings.

4. **Decision-quality scores**
   - Overall portfolio score.
   - Diversification.
   - Resilience.
   - Performance.
   - Expandable component explanation.

5. **Long-range outcome distribution**
   - 5,000 historical block-bootstrap paths.
   - 10th, 25th, median, 75th, and 90th percentile balances.
   - Observed trailing-year deposits when cash-flow history is complete; otherwise the manual annual-contribution preference.
   - Direct portfolio returns after 36 observed months, an explicitly disclosed annualized portfolio extension for shorter spans of at least 30 days, or the selected benchmark when the portfolio span is too short.
   - Explicit warning that simulated outcomes are not predictions.

6. **Opportunity cost**
   - Ending earnings for current holdings and each chosen benchmark from an identical start value and date window.

7. **Market Pulse**
   - FRED regime score and label.
   - 10-year Treasury, federal-funds rate, and inflation with observation dates.

8. **Focused screens**
   - Value near 52-week lows.
   - Recent momentum.
   - Short-term reversals.
   - Top ETFs.

9. **Support cards**
   - Current research leader.
   - Up to four saved watchlist matches.
   - Held names whose current production guidance is beyond Hold.

### `/research` — Company and ETF research library

Data used: `advisor.json`, `etfs.json`, and Firebase holdings.

The page combines stocks and normalized ETF rows in one library. Users can:

- Search ticker/company.
- Filter by sector.
- Filter stock versus ETF.
- Filter bought versus not bought.
- Sort by research score, 20-day return, sector valuation percentile, fundamentals, or confidence.
- Enter available funds for an illustrative score-weighted top-eight bucket plan.
- Add a $100 fractional-share record to the portfolio at the displayed price; this records a holding and does not send a brokerage order.
- Open the full stock/ETF detail modal.

Stocks retain the published research ordering unless the user changes sort. Momentum and reversal membership is added as a badge without changing the underlying score.

On desktop the results are a sticky-header table. On phones the table is completely hidden and replaced by cards showing rank, logo, ticker, name, score, stance/action, screen badges, ownership, fundamentals, 20-day return, confidence, sparkline, expandable evidence, and the $100 record action.

### `/search` — Global company discovery

Search merges, by ticker:

- Portfolio coverage.
- Screen universe.
- Published research.
- Configured universe tickers with minimal fallback records.

Input is debounced by 180 ms and results are limited to 60. Results are grouped in this priority:

1. In your portfolio.
2. Published research.
3. Watchlist.
4. Covered universe.

Recent searches are stored locally, capped at eight. A row can open details only when enough published/history data exists.

### `/market` — Market Pulse/news

This route exists but is intentionally not a primary desktop/mobile navigation item; the Financial Report links to it.

It shows:

- U.S. equity market status/session where supplied.
- News matching published research companies.
- Separate discovery news for other stronger broader-universe candidates.
- Source, ticker, optional research score/rank, title, summary, and outbound source link.

News is described as supporting evidence, not a substitute for business fundamentals.

### `/portfolio` — Portfolio management

Data used: `advisor.json`, `etfs.json`, `benchmark-report.json`, Firebase holdings/tracking, and live quote refreshes.

Main functions:

- Current value, gain/loss, score, diversification, holding count, cash, and other summary metrics.
- Uninvested cash tracker with deposits, withdrawals, sale proceeds, stock purchases, and manual reconciliation.
- Fidelity reference snapshot and optional supplied cash-flow import.
- Data refresh, reanalysis, quote refresh, reference-portfolio sync, JSON import/export, and clear-all operations.
- Earnings ledger for realized gain/loss, dividends, and fees.
- Cash-flow history and completeness confirmation.
- Suggested actions with company evidence plus position-specific stop rules.
- Concentration-risk display.
- Portfolio versus benchmark opportunity-cost chart.
- Add/edit/remove holding records.
- Sort by allocation, ticker/company, signal, shares, cost, price, value, gain, return, score, or trend.

The three view modes are:

1. **Holdings** — actual shares, cost, price, value, allocation, return, research guidance, stop levels, and trend.
2. **Since purchase / benchmark** — actual holding performance against the selected benchmark from each purchase date.
3. **Hypothetical** — a fixed-dollar stock-versus-index comparison from each holding’s purchase date.

On phones the 1,120 px desktop table is hidden and holding cards replace it. The cards preserve edit, remove, detail, values, metadata, trend, and action context. Sort controls stack vertically below 620 px.

### `/portfolio/diversification` — Diversification detail

Displays:

- 0–100 diversification score and provisional state.
- Data coverage.
- Concentration warnings.
- Sector donut/legend.
- Every score component with progress bars.
- Holdings ordered by allocation.
- Top industries.
- Explanation of the scoring assumptions and limits, including lack of ETF look-through.

### `/portfolio/insights` — Trader Insights

Displays:

- Portfolio mood and shareable daily recap.
- Today, contribution-adjusted return, biggest mover, and benchmark streak.
- Actual recorded account snapshots against a shadow account that invests the same deposits/withdrawals into the chosen benchmark.
- Each holding’s return versus the benchmark from its own purchase date.
- Realized-trade win rate, average win/loss, best/worst trade.
- Purchase-timing labels based on the pre-purchase trailing average.
- Account-value milestones and value streaks.

Web Share is used when available; otherwise the text is copied to the clipboard.

### `/watchlist` — Browser-local watchlist

- Defaults to AAPL and MSFT on first load.
- Tickers and sizing settings are stored only in this browser.
- Add/remove tickers.
- Refresh the watchlist’s data or reanalyze the last published data.
- Each covered card shows price, 20-day move, research score, sparkline, bull/bear thesis, buy-setup verdict, Yahoo consensus target/upside, and illustrative maximum allocation/shares.
- An unknown/unpublished ticker remains saved but shows an unavailable explanation.

### `/finances` — Personal finances

This signed-in Firestore-backed page has three tabs:

1. **Budget**
   - Add/remove monthly income and expenses.
   - Monthly leftover = income − expenses.
   - Copy positive leftover into the retirement monthly-contribution assumption.

2. **Auto-Split Pools**
   - Create named percentage pools.
   - Preview and log deposits.
   - Pool percentages are normalized against their combined total, so they do not need to sum to exactly 100.

3. **Retirement**
   - Set current age, retirement age, plan-end age, inflation, savings, monthly contribution, and monthly retirement spending.
   - Sync current savings from current holdings value.
   - Track 401(k)/403(b), Roth IRA, Traditional IRA, self/family HSA, and taxable accounts.
   - Show contribution progress against coded 2026 limits.
   - Optionally use tracked account contributions as the retirement contribution input.
   - Chart nominal percentile bands from the shared historical block-bootstrap model.
   - Show median retirement balance and the probability that savings last through the configured plan-end age.

### `/settings` — Interface and planning preferences

Settings are stored in browser localStorage and include:

- System/light/dark theme.
- Eight accent palettes.
- Outlined/soft/elevated surfaces.
- Compact/rounded/extra-rounded corners.
- Compact/comfortable/spacious density.
- Chart style, line weight, grid visibility, animation, default period, and up to three default benchmarks.
- Holding default sort.
- Annual contribution, birthdate-derived age, and retirement age.
- Number formatting.
- Privacy mode.
- Reduced motion, higher contrast, and larger chart labels.
- Appearance-only reset and confirmed full-preference reset.

### `/alerts` — In-app alerts and optional Web Push

This signed-in route stores private rules, events, subscriptions, and quiet-hour settings under `alerts/<uid>` in Firestore.

Supported rules:

- Price crosses above or below a level.
- One-day or five-day percentage move crosses a threshold.
- Trim or exit stop is reached.
- Research score enters or leaves a configured band.
- Guidance changes to Trim or Sell.
- Earnings is within a chosen number of days when the source publishes a date.
- The research pipeline is older than a configured number of hours.

Every fired rule creates an in-app event first. The Python evaluator runs after a scored workflow refresh, compares current conditions with each rule's stored `lastState`, and suppresses unchanged active conditions. It then groups new events by user and calls the server-only Netlify delivery function. Push is offered only after the user creates the first rule, never on page load. Quiet hours suppress device delivery but do not suppress the inbox event. Expired push subscriptions are removed after a 404 or 410 response.

### `/methodology` — Scoring explanation

Reads published weights from `advisor.json` so its primary 78/18/4 display follows the snapshot. It explains:

- Overall stock research score.
- Fundamental categories.
- Modifiers.
- Theme-screen separation.
- Point-in-time and out-of-sample validation.
- Production versus shadow recommendation policy.
- Same-dollar benchmark comparisons.
- Provider/parser capability status.

### `/glossary` — Static reference

A client-side searchable glossary covering valuation, profitability/cash, financial health, accounting quality, capital allocation, growth, ownership/positioning, market behavior, scoring/guidance, and finances. It reads no live data.

### Research-screen routes

All research screens have a horizontally scrollable chip navigation bar.

- `/screens/momentum` — exact month-end skip-month momentum, liquidity gates, hysteresis, and portfolio-level risk controls.
- `/screens/quality-value` — own-history/peer valuation with business-quality, distress, and forward-revision gates.
- `/screens/earnings` — revisions, earnings information, price confirmation, breadth, and tradability.
- `/screens/matrix` — keeps structural and tactical horizons separate.

The generic screen page supports sector, market cap, minimum confidence, minimum liquidity, structural score, tactical score, and membership filters. Desktop uses a table. At 900 px and below it uses shared result cards. The Mobile research view preference selects a compact visual summary or the complete detailed card fields.

- `/screens/early-session` — deliberately gated when extended-hours OHLCV or intraday bars are unavailable. Shows why the screen is killed, capability/freshness/granularity, permitted language, and zero candidates rather than fabricating a signal.
- `/screens/politics` — STOCK Act disclosures with chamber/flag/sort filters, summary KPIs, filing delay, transaction range, price return since eligible plain-stock purchases, and anomaly flags. Congressional trading is not used in the stock research score.
- `/screens/shadow` — prospective net-of-cost strategy results including return, CAGR, Sharpe, Sortino, drawdown, turnover, and evidence status.
- `/screens/validation` — controlled v2 provider-lineage validation with structural/timeliness scores, company and position decisions, applicability, provider conflicts, critical gaps, peer sample, and invariant failures. It never replaces production output.

## 5. Stock research score: exact live calculation

### 5.1 Convert raw fundamentals to 0–100 metric scores

Raw ratios are mapped to discrete score bands:

- Higher-is-better metrics: 100 / 80 / 55 / 30 / 10.
- Lower-is-better metrics: 100 / 80 / 55 / 30 / 10.
- Positive valuation multiples: suspiciously low values score 60, cheap 100, healthy 80, elevated 45, expensive 15, and nonpositive 5.
- Range metrics such as capex/depreciation and asset growth score 100 inside the ideal range, 65 inside the acceptable range, and 25 outside it.
- Legacy `band_score` lower-is-better bands use 100 / 75 / 50 / 25 / 10, with negative/odd inputs normally scoring 15.

Every metric threshold is centralized in `pipeline/config/settings.json`.

### 5.2 Build six fundamental categories

Within a category, only available/applicable metrics are included and their weights are renormalized.

| Category | Overall fundamental weight | Metric weights inside the category |
|---|---:|---|
| Valuation | 28% | PEG 9%, forward P/E 15%, sales multiple 9%, P/B 5%, tangible P/B 5%, EV/EBITDA 27%, EV/EBIT 12%, EV/FCF 18% |
| Profitability and cash | 26% | ROIC 26%, gross profits/assets 22%, ROE 10%, FCF yield 16%, profit margin 10%, cash conversion 16% |
| Financial health | 15% | Interest coverage 30%, net debt/EBITDA 24%, debt/equity 18%, current ratio 10%, Altman Z 18% |
| Growth | 11% | Revenue growth 26%, earnings growth 20%, 3-year FCF growth 22%, operating-margin trend 16%, earnings surprise 16% |
| Capital allocation | 10% | Net buyback yield 34%, stock comp/revenue 28%, capex/depreciation 16%, asset growth 22% |
| Accounting quality | 10% | Accruals ratio 22%, Piotroski F 45%, DSO trend 17%, inventory-days trend 16% |

Sector applicability matters:

- Financial companies skip industrial-company leverage, liquidity, enterprise-multiple, Altman, capex, inventory, and gross-profit/assets metrics instead of failing them.
- Tangible book is used only for sectors where tangible assets are meaningful.
- EV/Sales is preferred; P/S is the fallback.
- Altman uses the manufacturer or non-manufacturer bands matching the calculated variant and is suppressed for financials.

### 5.3 Fundamental coverage penalty

Coverage is the answered applicable metric weight divided by total applicable metric weight.

```text
fundamental raw = weighted mean of available category scores
coverage multiplier = 0.65 + 0.35 × coverage
fundamental score = fundamental raw × coverage multiplier
```

Thus a company with sparse data cannot retain the same fundamental score as a fully covered company. Non-applicable metrics leave the denominator; truly missing applicable metrics reduce coverage.

### 5.4 Market-behavior score

The market-behavior score reweights available inputs using:

| Input | Weight | Transformation |
|---|---:|---|
| 12–1 momentum | 30% | `clamp(50 + momentum_pct × 1.2)`; 60-day return fallback lowers coverage |
| Risk-adjusted return | 26% | 65% Sortino score + 35% Sharpe score |
| 20-day relative strength vs SPY | 16% | `clamp(50 + relative_pct × 3)` |
| Drawdown resilience | 14% | Shared drawdown scoring, normally one-year maximum drawdown |
| Volume confirmation | 8% | `clamp(35 + (up/down volume ratio − 1) × 55)` |
| Low beta | 6% | Shared low-beta reward |

Coverage is the available subweight divided by all market-behavior weight.

### 5.5 News-sentiment score

- Only ticker-level news mentions in the last seven days are aggregated.
- No usable articles gives a neutral score of 50 but zero sentiment coverage.
- Otherwise: `sentiment score = clamp(50 + average ticker sentiment × 100)`.
- Coverage reaches 100% at five articles: `min(1, article_count / 5)`.

### 5.6 Blend, confidence, and base score

The current configured live blend is:

```text
raw evidence score =
    78% fundamentals
  + 18% market behavior
  +  4% news sentiment
```

Unavailable top-level components are reweighted rather than treated as zero.

```text
confidence =
    65% fundamental coverage
  + 25% market-behavior coverage
  + 10% sentiment coverage

base score = raw evidence score × (0.8 + 0.2 × confidence)
```

Even before modifiers, lower confidence shrinks the raw score by up to 20%.

### 5.7 Post-blend modifiers

The following are added to the base score and the final result is clamped to 0–100. Combined modifiers have a hard ±15 point cap.

- **Sector valuation: ±3.** `(sector percentile − 50) / 50 × 3`; changes smaller than 0.5 are ignored.
- **Short interest: 0 to −6.** At least 8% of float gives half the cap; at least 15% gives the cap; at least five days to cover can add 1.5 negative points up to the cap.
- **Insider activity: +5 to −3.** Only opportunistic Form 4 activity counts; routine scheduled activity scores zero. Fresh independent buy clusters are stronger than sells and decay over one to three months.
- **Liquidity: 0 to −3.** Below $5M average daily dollar volume gets −3; below $25M gets −1.5.
- **Analyst expectations: ±3.** Requires at least three analysts. Target upside ≥20% and rating ≤2.0 can each add 1.5; upside ≤−5% and rating ≥3.5 can each subtract 1.5.
- **Macro regime: ±3.** Requires at least 70% FRED factor coverage and weights rates, inflation, labor, and yield curve differently by sector.

```text
final research score = clamp(base score + capped modifier total, 0, 100)
```

### 5.8 Research stance

- Confidence below 45%: `INSUFFICIENT DATA`.
- Score 75 or more: `ATTRACTIVE`.
- Score 60–74.9: `PROMISING`.
- Score 45–59.9: `MIXED`.
- Score below 45: `CAUTION`.

## 6. Structural/timeliness v2 analysis

The v2 layer is published for validation and explanation alongside the legacy production score.

### Structural layer

- Uses canonical provider observations, metric applicability, lineage, stale dates, and conflicts.
- Coverage = available applicable weight / applicable weight.
- Provenance reliability is 0.72 with observation lineage and 0.55 for legacy scalar-only values.
- Conflict and stale penalties are each capped at 0.35.

```text
structural confidence = clamp(
  coverage × provenance reliability
  − conflict penalty
  − stale penalty,
  0, 1
)

effective structural score = 50 + confidence × (raw structural score − 50)
```

This explicitly shrinks uncertain results toward neutral 50.

Classification:

- Confidence <40%: insufficient evidence.
- Confidence 40–59%: review below 50, otherwise watch.
- Confidence ≥60%: strong business ≥75, quality watch ≥60, mixed ≥45, otherwise weak business.

### Timeliness layer

```text
revision score = clamp(50 + 5 × 30-day forward EPS revision)
surprise score = clamp(50 + 2 × earnings surprise)
timeliness raw = 70% revision score + 30% surprise score
timeliness confidence = available timing weight × (0.85 with observations, else 0.55)
timeliness effective = 50 + confidence × (raw − 50)
```

Classification is insufficient below 40% confidence, improving at 60+, weakening below 45, and stable otherwise.

## 7. Guidance, buy setup, and position rules

### Production Hold/Watch/Trim/Sell guidance

The pipeline groups concerns into three independent families:

1. Fundamentals: weak profitability, health, accounting, or growth category; low interest coverage; high accruals.
2. Market behavior: one-year drawdown below −30%, 20-day relative weakness below −10 points, or a sustained 20-/60-day decline.
3. Positioning: at least three sufficiently negative articles or at least 15% short float.

Decision:

- No concern groups: Hold.
- One group: Watch.
- At least two groups and score ≥45: Trim 33%; 50% when all three agree.
- At least two groups and score <45: Sell 100%.

The browser honors the published result. Older payloads fall back to a comparable client-side two-factor engine.

V2 structural-confidence gates can downgrade guidance:

- Structural confidence <40% always becomes Watch for insufficient evidence.
- Structural confidence <60% prevents a published Trim/Sell from remaining prescriptive; it becomes Watch.

### Bull/bear thesis displayed in watchlist/details

Available factors are renormalized:

- Fundamentals 40%.
- Price behavior 30%.
- News sentiment 20%, only when sentiment coverage exists.
- Risk quality 10%.

The weighted 0–100 composite is divided by ten and rounded to one decimal, where 5 is neutral.

### Watchlist “BUY SETUP”

All of these must be true:

- Bull/bear thesis ≥5.5/10.
- Research score ≥65.
- Confidence ≥50%.
- 20-day return >0.
- Published recommendation is not Trim or Sell.

If the setup fails, verdict is `DON'T BUY YET` and illustrative allocation is $0. If it passes, allocation is budget × capped max-position percentage, and shares are floored to 0.001 share.

### Portfolio stop rules

Position-specific rules are kept separate from company evidence:

- At or below −20% versus average cost: Sell.
- At or below −12% versus average cost: Trim.
- At or below −15% from the highest close since purchase: Trim/protect gains.

The more defensive action wins when combined with company guidance. A position stop does not rewrite the underlying company thesis.

## 8. ETF score

ETFs are never passed through company-accounting ratios. They are ranked primarily within like-for-like peer groups such as broad equity, equity income, international, sector, thematic, fixed income, commodity, and crypto. A peer group with fewer than four funds falls back to a pooled comparison and is marked cross-asset-class.

Within each peer group, raw values become 0–100 percentiles. Equal values share a rank; missing metrics remain neutral 50 rather than receiving a fabricated extreme.

Top-level weights:

- Performance 28%.
- Risk 27%.
- Total cost 17%.
- Liquidity 16%.
- Structural quality 12%.

Key construction details:

- Performance averages the configured return windows.
- Risk weights Sortino 38%, Sharpe 20%, maximum drawdown 24%, beta 18%.
- Cost weights expense ratio 40%, one-year tracking difference 40%, premium/discount 20%.
- Liquidity combines AUM, average dollar volume, and bid-ask spread percentiles.
- Quality starts with issuer quality and adjusts for AUM, leverage/inverse structure, synthetic replication, and aggressive securities lending.
- Rule 6c-11 median 30-day spread is preferred when configured; otherwise a quote spread is used.
- Tracking difference uses a configured like-for-like ETF proxy for the stated index, not an unlabelled generic benchmark.

Research-page ETF stance is UI-derived from ETF score: Attractive ≥80, Promising ≥70, Neutral ≥55, otherwise Caution.

## 9. Portfolio calculations

### Position and account values

```text
position total cost = shares × per-share cost basis
position current value = shares × current price
position gain = current value − total cost
position gain % = gain / total cost × 100
allocation % = current value / total priced portfolio value × 100
```

Current price uses published research price, then refreshed quote data where merged, then a stored snapshot fallback where applicable.

### Historical current-holdings series

For every shared date, the app applies today’s share quantities to that date’s historical close. A date is retained only when all tracked holdings have usable prices. This deliberately answers “what would today’s basket have looked like,” not “what was my actual account worth that day.”

### Same-start benchmark comparison

Portfolio and every benchmark are intersected to identical dates. Each benchmark is scaled to the portfolio’s first value:

```text
benchmark value on date t = shared starting value × benchmark close(t) / benchmark first close
potential earnings = ending value − shared starting value
difference vs portfolio = portfolio ending value − benchmark ending value
```

### Contribution-adjusted performance

Only settled deposits and withdrawals count. Pending/processing flows are excluded.

```text
net invested capital = deposits − withdrawals
contribution-adjusted earnings = account value − net invested capital
contribution-adjusted return = earnings / net invested capital × 100
```

This is a simple contribution-adjusted return, not a broker time-weighted return.

### Tracked all-time earnings

Available only after the user confirms the historical ledger is complete:

```text
all-time earnings =
  current unrealized gain
  + recorded realized gains
  + recorded dividends
  − recorded fees
```

### Diversification score

Component formulas:

```text
position balance = clamp(100 − max(0, largest position % − 10) × 2.7)
top-five balance = clamp(100 − max(0, top-five % − 50) × 1.5)
sector balance = clamp(100 − max(0, largest sector % − 25) × 1.8)
industry balance = clamp(100 − max(0, largest industry % − 20) × 1.5)
meaningful positions = clamp(count of positions ≥2% / 12 × 100)

diversification =
    30% position balance
  + 20% top-five balance
  + 25% sector balance
  + 15% industry balance
  + 10% meaningful positions
```

Warnings trigger above 25% for one holding, above 35% for one sector, and above 70% for the top five. Fewer than five priced positions makes the score provisional.

### Resilience

Requires at least 20 daily values and is provisional below 60.

```text
drawdown score = clamp(100 + maximum drawdown % × 2.5)
volatility score = clamp(100 − max(0, annualized volatility % − 10) × 2.2)
resilience = 45% drawdown + 35% volatility + 20% diversification
```

Annualized volatility is sample standard deviation of daily returns × √252 × 100.

### Performance rating

```text
excess return = portfolio return − benchmark return
score = clamp(65 + 2 × excess return percentage points + 0.8 × max drawdown %)
```

Because drawdown is negative, it lowers the score. Letter grades are A ≥90, B ≥80, C ≥70, D ≥60, otherwise F.

### Concentration/liquidity

- Concentration score: `clamp(100 − max(0, largest allocation − 10) × 2.5)`.
- If average-dollar-volume coverage is below 80%, only concentration is returned provisionally.
- Otherwise liquidity estimates days to liquidate each holding at 10% of average daily dollar volume, allocation-weights that score, and blends 55% concentration / 45% liquidity.

### Overall portfolio score

```text
25% diversification
25% resilience
20% risk-adjusted performance
15% benchmark efficiency
10% concentration/liquidity
 5% data completeness
```

At least three real components are required. Available components are reweighted; missing ones are not zero. Any missing/provisional component or incomplete data makes the overall result provisional.

## 10. Long-range outcome distribution

The Financial Report and Finances page use the same historical block-bootstrap engine. It is a distribution of historically resampled outcomes, not a single smooth-rate forecast.

### Return-source selection

1. Daily values are reduced to one month-end value per calendar month.
2. Simple monthly returns are calculated as `current month-end / prior month-end - 1`.
3. With at least 36 observed portfolio monthly returns, the model uses the portfolio history directly.
4. With fewer than 36 monthly returns but a first-to-last portfolio span of at least 30 days, the app keeps the portfolio as the source:
   - It calculates the longest recorded total return from the first usable observation to the last.
   - It annualizes that return with `(ending / starting) ^ (365.25 / elapsed days) - 1`.
   - It converts the annualized result into a monthly geometric rate.
   - If observed month-to-month changes exist, it centers their log-return pattern around that monthly rate.
   - It repeats the centered pattern to 36 months so the 12-month block model can run.
   - The UI labels the source as an annualized portfolio-history extension and warns that percentile bands may cluster when little monthly variation has been observed.
5. If the portfolio spans fewer than 30 days, the selected benchmark is the disclosed fallback when it has at least 12 monthly returns.

### Simulation

- At least 5,000 paths are run in a Web Worker.
- Each path samples consecutive 12-month historical blocks. This preserves the order within each sampled year rather than treating every month as independent.
- For saving months, `next balance = max(0, current balance × (1 + sampled return) + monthly contribution)`.
- For withdrawal months, the inflation-adjusted withdrawal replaces the contribution.
- Nominal and real 10th, 25th, 50th, 75th, and 90th percentile balances are calculated.
- Finances reports the share of paths whose balance survives the full withdrawal period.
- The chart displays the 10th-to-90th band, 25th-to-75th band, and median path.

The 36-month gate therefore still distinguishes an observed portfolio model from an extension, but it no longer hides the outcome distribution for a shorter usable portfolio history.

## 11. Focused-screen calculations

### Financial Report client-side screen previews

- **Value turnarounds:** near the 52-week low, sufficient quality, and a positive latest week; sorted by screen-specific value/quality logic.
- **Momentum:** requires positive recent windows and ranks recent momentum candidates.
- **Reversal:** looks for a meaningful 20-day pullback followed by a positive latest week and recovery evidence.
- **Growing ETFs:** ranks eligible funds using their ETF data, emphasizing growth/performance fields.

These previews are separate from the main company score.

### Pipeline research screens

The Python v2 screen models add explicit liquidity, data-quality, history, membership, peer, hysteresis, rebalance, and risk constraints. Examples include:

- Month-end 12–1, 6–1, industry-relative, and residual momentum families.
- Own-history robust valuation percentiles plus peer value, quality, revision, and distress gates.
- Structural versus tactical matrices rather than one mixed-horizon label.
- ATR/account-risk sizing and liquidity caps that size positions without changing signal score.

Screen ranks are hypotheses for prospective validation and do not alter the main research score unless explicitly published as a different model.

## 12. Mobile behavior in detail

### Breakpoints

- **Above 1180 px:** full layouts; watchlist can use wider grids.
- **1100 px and below:** several four-column/gridded areas reduce to two columns; portfolio summary becomes narrower.
- **900 px and below:** phone/tablet application shell activates.
- **620–680 px and below:** phone-specific stacking, cards, simplified rows, and full-width controls.
- **360–380 px and below:** compact navigation/type/card refinements.

### What always changes at 900 px

- Desktop rail is removed.
- Mobile header and bottom navigation appear.
- Main content is centered at a maximum 680 px and receives safe-area-aware padding.
- Source-health pills in the data status are hidden, while its live/demo/warning summary remains.
- Page headers stack; page actions can horizontally scroll or wrap.
- Generic grids reduce toward one or two columns.
- Desktop-only privacy button disappears because privacy moves to the header.
- The active route is visibly highlighted in the bottom bar.

### Financial Report on mobile

The currently rendered component remains the Financial Report; it is not replaced by a separate mobile-only Dashboard component.

At 900 px:

- Portfolio hero spans both columns; its three supporting metrics form two columns.
- Score cards become two columns.
- Support cards become two columns, with actions full-width.
- Market Pulse becomes two columns.

At 620 px:

- Hero and all report metrics become a vertical stack.
- Balance uses a smaller responsive font.
- Today/after-hours pills and after-hours refresh become full-width.
- Period buttons remain in a horizontally scrollable single row.
- Benchmark selection opens in a bottom sheet while retaining up to three selections.
- Touch scrubbing moves a crosshair and updates the chart value header.
- Pulling from the top reloads the report data and held-symbol quotes.
- Chart summary, portfolio scores, screen cards, support cards, opportunity/planning cards, and Market Pulse become single-column.
- The scenario basis becomes vertical.
- Each 1/5/10-year horizon becomes a compact horizontal mini-table: year label plus conservative/base/optimistic columns.

### Research library on mobile

- Desktop table is hidden at 900 px.
- Detailed cards become the only result representation, and lists over 50 results are window-virtualized.
- Search plus every filter use a one-column layout below 620 px.
- Evidence columns collapse to one.
- Horizontal overflow is avoided except intentional controls/carousels.

### Portfolio on mobile

- Desktop holdings table is hidden at 900 px.
- Holding cards become the only representation.
- Cards display identity, value, gain/return, allocation/metadata, trend, and available edit/action controls.
- Summary uses a prominent full-width value card plus smaller KPI cards; below 620 px it becomes entirely one column in the later responsive rules.
- Cash, Fidelity, activity, and benchmark sections collapse from grids into one-column forms/cards.
- Sorting opens in a bottom sheet.
- Holding edits open in a bottom sheet with explicit Cancel and Save changes actions.
- Pulling from the top refreshes held-symbol quotes.

### Search on mobile

- Search input remains 16 px.
- Result rows hide stance at 900 px.
- At 620 px they also hide the score badge, retaining logo, company identity, current market data, and open chevron.

### Diversification on mobile

- Hero becomes centered and vertical.
- Sector/score panels stack.
- Holding allocation bars and dollar-value sublabels hide at 620 px; ticker/company and percentage remain.

### Settings on mobile

- Rows stack vertically.
- Selects/buttons become full-width.
- Accent choices reduce from four to two columns.
- Benchmark choices reduce to two columns.
- Switches remain aligned to the right where practical.

### Finances on mobile

- The three headline KPI cards collapse to one column through the generic grid rules.
- Retirement assumption fields also collapse to one column.
- Budget, pool, deposit, and account forms become one-column forms below 620 px.
- Pool rows and the deposit preview wrap, but the exact experience depends on the entered label lengths.

### Stock details on mobile

- At 620 px the centered modal becomes a bottom sheet with rounded top corners and no lower corner radius.
- Maximum height is 92 dynamic viewport height and content scrolls internally.
- Score/metric grids reduce to two columns or one based on their generic grid rules.

### Mobile validation status

- ResearchScreen, Congress Trades, and Shadow Portfolios use the shared `ResultCards` representation below 900 px.
- Congress summary KPIs reflow from five columns to three, then two columns.
- The `mobileResearchView` preference controls compact versus detailed cards.
- Dead `.desktop-dashboard`, `.mobile-dashboard`, and unused dedicated-mobile-home CSS has been removed.
- Automated browser captures verify exact 390 px and 430 px viewports in light and dark themes with no horizontal overflow, a fully visible bottom navigation, and full-row phone filters.

## 13. Data loading, caching, migrations, and freshness

### Static data loading

`useData(file)`:

- Reads `BASE_URL/data/<file>?v=<timestamp>` with `cache: no-store`.
- Deduplicates simultaneous requests per file.
- Migrates known advisor/ETF schemas before display.
- Stores the last successful payload in memory and localStorage.
- Shows cached data immediately and revalidates quietly.
- Retains current/cached data when a refresh fails and exposes the error.

### Pipeline status

- Research is stale at 36 hours.
- Status combines demo/live mode, generated time, advisor-stage state, and Alpha Vantage degradation.
- Desktop shows provider/source pills; mobile hides those pills but keeps the summary and expandable generated time.

### Current published snapshot shape

At the time of this review, the committed artifacts contain approximately:

- 40 published stock research rows.
- 36–37 explicit portfolio-coverage rows.
- 323 screen-universe rows.
- 125 ETFs.
- 75 momentum-screen rows.
- 8 shadow strategies.
- 10 live-v2 validation cases.

Counts change when the pipeline refreshes and should not be treated as application limits.

## 14. Persistence model

### Browser localStorage

- UI preferences.
- Watchlist and watchlist sizing.
- Recent searches.
- Last successful static JSON payload cache.
- One-time migration flags.

### Firestore

- `users/<uid>`: profile metadata.
- `portfolios/<uid>/positions/*`: holdings.
- `portfolios/<uid>/activity/*`: holding events, cash flows, realized gains/losses, dividends, fees, and adjustments.
- `portfolios/<uid>/intradaySnapshots/*`: recorded portfolio values.
- `portfolios/<uid>/tracking/state`: ledger/cash/history state.
- `finances/<uid>`: retirement assumptions.
- `finances/<uid>/budgetItems/*`: budget rows.
- `finances/<uid>/pools/*`: named savings pools and balances.
- `finances/<uid>/accounts/*`: retirement/investing accounts and annual contributions.

Portfolio listeners are real-time, so changes on another signed-in device appear without reload. Finance data currently loads on mount and updates optimistically but is not subscribed with `onSnapshot`.

## 15. Refresh workflows

### Scheduled pipeline

The documented schedule targets shortly after 07:00, 12:00, and 15:00 Eastern on weekdays with daylight-saving-aware gating. The morning run can perform the broader/provider-heavy sweep; later runs can refresh cheaper sources.

### Manual refresh

- Requires a signed-in Firebase user whose email is in the server allowlist.
- Valid ticker symbols are deduplicated and limited to 50.
- `data` mode dispatches a fast data-only refresh over the prior top set plus supplied portfolio/watchlist symbols, carrying forward the rest.
- `rescore` mode recalculates from last published data without new provider calls.
- The client polls the exact GitHub Actions run and presents weighted stage progress.
- Duplicate active runs are rejected.

### After-hours quotes

- The app schedules a quiet local 9 p.m. refresh boundary and also provides a manual button.
- Only held symbols are sent.
- Post-market results are shown only when Yahoo supplies real post-market fields; absence is not converted into a fake zero move.

## 16. Validation and guardrails

- JSON schemas define advisor, ETF, news, price, signal, trade, status, and recommendation contracts.
- Schema migrations let a newly deployed client consume older committed snapshots.
- Point-in-time observations, revisions, and universe membership are stored for future honest backtests.
- Evaluation uses rank information coefficient, ICIR, quantile spreads/monotonicity, deflated Sharpe, and overfitting checks rather than one appealing equity curve.
- Shadow models do not replace production merely because they are implemented.
- Early-session signals emit an unavailable/gated result when source granularity is inadequate.
- Theme exposure is independent from the main score; price momentum contributes exactly zero to the theme score.
- Congressional disclosure data is excluded from the stock advisor score.
- Missing evidence is reweighted within a category and then reduces confidence; it is not silently treated as bad evidence.

## 17. Source-of-truth notes and current inconsistencies

These details matter when maintaining or explaining the app:

1. **Live stock weights are 78% fundamentals, 18% market behavior, and 4% news.** The Glossary’s Research Score definition and one Methodology modifier-introduction paragraph still say 75/15/10. The pipeline config, README, calculation code, published methodology snapshot, and primary Methodology weight display use 78/18/4.
2. **Report customization currently persists but does not control rendering.** `DEFAULT_WIDGETS`, the `?customize=1` panel, ordering, visibility, and save behavior exist, but the Dashboard renders its sections directly without consulting `preferences.widgets`.
3. **The mobile research-view preference is currently inert.** It is validated/stored, but Picks always switches based on CSS breakpoint, not that preference.
4. **Dedicated mobile-dashboard styles are currently inert.** No current Dashboard element uses `.desktop-dashboard` or `.mobile-dashboard`.
5. **Some older modules are compatibility/roadmap code, not active product behavior.** Examples include the non-Firebase `AuthContext`, score-band helpers, security/Fidelity connector stubs, and some earlier dashboard styling. Active imports and routes determine live behavior.
6. **The watchlist is browser-local, not Firestore-backed.** Holdings and Finances are cloud-backed; watchlist/recent searches/preferences are not synchronized across devices.
7. **“Buy $100” does not buy anything.** It creates a fractional holding record using the current displayed price and today’s date.
8. **Portfolio historical charts are not broker statements.** The main report applies current quantities to historic closes, while the Insights shadow chart uses recorded snapshots and settled cash flows. These answer different questions.
9. **ETF scores are peer-relative.** An overall ETF score should be interpreted as quality relative to funds doing a similar job, not as an absolute comparison between a bond fund and a technology ETF.

## 18. Key source map

| Concern | Primary source |
|---|---|
| Route shell/navigation | `src/App.jsx` |
| Responsive/mobile rules | `src/styles/global.css` |
| Theme/design tokens | `src/styles/variables.css`, `src/lib/PreferencesContext.jsx` |
| Financial Report | `src/pages/Dashboard.jsx` |
| Research library | `src/pages/Picks.jsx` |
| Portfolio | `src/pages/Portfolio.jsx` |
| Diversification/overall portfolio formulas | `src/lib/portfolioAnalytics.js` |
| Benchmark alternatives | `src/lib/portfolioPerformance.js`, `src/lib/traderInsights.js` |
| Stock detail modal | `src/components/StockDetailModal.jsx` |
| Production recommendation adapter | `src/lib/recommendation.js` |
| Position stop rules | `src/lib/positionRisk.js` |
| Watchlist setup rule | `src/lib/watchlistGuidance.js` |
| Stock fundamental bands/categories | `pipeline/scorer.py`, `pipeline/config/settings.json` |
| Final research blend/modifiers | `pipeline/advisor_engine.py` |
| Structural/timeliness v2 | `pipeline/scoring_v2.py` |
| Shadow recommendation policy | `pipeline/recommendation_policy_v2.py`, its config |
| ETF scoring | `pipeline/fetch_etfs.py`, `pipeline/config/universe.json` |
| Focused screens | `pipeline/research_screens_v2.py`, screen builders, `src/lib/researchScreens.js` |
| Static data loader/cache | `src/lib/useData.js` |
| Firebase holdings | `src/lib/useFirebasePortfolio.js` |
| Firebase finance data | `src/lib/useFirebaseFinances.js` |
| Cash/snapshot ledger | `src/lib/usePortfolioTracking.js` |
| Retirement projection | `src/lib/retirementCalculator.js` |
| Manual refresh | `netlify/functions/refresh-data.mjs` |
| Live portfolio quote refresh | `netlify/functions/portfolio-prices.mjs` |

## 19. One-line mental model

ValueSignal takes published company/fund evidence, converts it into transparent confidence-aware research scores, keeps personal holdings and cash-flow context separate in Firebase, and then presents both through a responsive report—while clearly separating historical illustrations, company theses, position rules, and unvalidated shadow research.
