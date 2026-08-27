# CAPABILITY-LEDGER.md

Phase 0a deliverable of the twelve-medium interface rebuild (see `NOTES.md` for the naming
substitution: the rebuild calls the twelve presentations **mediums** in code, "theme" being
already taken by light/dark `data-theme` and by thematic equity screens). One row per
user-facing capability in the current build (behavior and data only — no appearance language).

**Row schema:**

```
| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
```

- **capabilityId** — dot-separated, kebab-case segments: `<class>.<scope>.<slug>`.
- **class** — one of: `metric` · `figure` · `chart` · `column` · `control` · `view` · `detail` ·
  `disclosure` · `state` · `export` · `link` · `alert` · `a11y` · `nav`.
- **disposition** — exactly one of `kept` / `moved` / `merged` / `demoted`.
  - `moved` / `merged` rows carry the exact new route in **destination** and, for `merged` rows,
    the exact selector value that reaches them in **selector**.
  - `demoted` rows carry the opening interaction in **selector** instead of a URL param.
- **interactions** — count of additional interactions from steady state needed to reach this
  capability post-consolidation (0 = visible on the destination as loaded; 1 = one tap/selector).
- **ID compatibility**: for `class=metric`, the slug is the `docs/METRIC_INVENTORY.md` /
  `signal_metrics.json` id with `_` → `-` (lossless — source ids match `[a-z0-9_]+`, no hyphens).
  `scripts/check-metric-preservation.mjs` keeps validating the doc directly; this ledger's metric
  section is generated from the same doc plus the live `signal_metrics.json` registry so the two
  never drift apart silently (see `NOTES.md` for the 24 live metrics newer than the doc).

**Destination legend** (see `ROUTE-INVENTORY.md` §2 for the full consolidation proposal):
`/` Home · `/research` Research (absorbs Search, Watchlist) · `/screens?recipe=<id>` Screens ·
`/portfolio?view=<v>` Portfolio (absorbs Finances, Planning) · `/markets?view=<v>` Markets
(absorbs News) · `/evidence?section=<s>` Evidence (absorbs Methodology, Glossary, Backtests,
Shadow, Validation) · `/alerts`, `/settings` demoted to persistent-chrome, one tap.

---

## 1 · Home (`/`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `figure.home.market-summary-strip` | figure | `Dashboard.jsx` `HomeMarketSummary` | market type, breadth %, hottest sector, biggest mover, research leader, macro regime | `report.json`, `advisor.json` | moved | `/markets` | `?view=indexes` | 1 | serves a different decision ("markets") than Home ("how am I doing"); first-viewport cut, see ROUTE-INVENTORY §3 |
| `figure.home.portfolio-hero` | figure | `HomePortfolioPanel` | invested value, today's $/%, total profit for period, top-5 holdings | `useFirebasePortfolio`, `usePortfolioTracking` | kept | `/` | — | 0 | primary destination, first viewport item 1 |
| `chart.home.growth-chart` | chart | `HomePortfolioPanel` 360px chart | portfolio value over selected period | `usePortfolioQuotes` | kept | `/` | — | 0 | |
| `control.home.chart-period` | control | select | 1H/1D/1W/1M/3M/1Y | preference `defaultChartPeriod` | kept | `/` | — | 0 | writes to prefs blob |
| `control.home.top5-rank-mode` | control | select | Today's performance / Biggest allocation | local state | kept | `/` | — | 0 | |
| `control.home.since-live-tracking` | control | switch | "Since live tracking started only" | local state | kept | `/` | — | 0 | scopes score gauges + evidence summary |
| `control.home.privacy-eye` | control | icon button (desktop) | show/hide balances | preference `privacyMode` | kept | `/` | — | 0 | duplicated in mobile header + Settings |
| `action.home.refresh-full-universe` | control | button (signed-in) | "Refresh full universe" | `useAdvisorRefresh` | kept | `/` | — | 0 | |
| `control.home.pull-to-refresh` | control | gesture | pull-to-refresh | `usePullToRefresh` | kept | `/` | — | 0 | |
| `link.home.reorder-widgets` | link | `<a href="/?customize=1">` | "Reorder widgets" | — | kept | `/` | `?customize=1` | 1 | full page reload on save today — becomes SPA nav in rebuild |
| `view.home.customizer` | view | `Customizer` aside | per-widget visibility switch, reorder, locked "Required" widgets | preference `widgets` | kept | `/` | `?customize=1` | 1 | |
| `link.home.portfolio-preview` | link | `?portfolioPreview=1` (dev) | swaps stored positions for fixtures | `pipeline/config/settings.json` | kept | `/` | `?portfolioPreview=1` | 0 | dev-only |
| `chart.home.score-gauges` | chart | `metric-grid` ×3 `ScoreCard` | Portfolio score / Diversification / Resilience dials | `portfolioAnalytics.js` | moved | `/research` | — | 1 | discovery decision, not status; first-viewport cut |
| `detail.home.score-composition` | detail | `<details>` under gauges | score-composition breakdown | same | kept | `/` | — | 0 | |
| `figure.home.performance-evidence-summary` | figure | `PerformanceEvidenceSummary` | evidence summary under gauges | `portfolioAnalytics.js` | kept | `/` | — | 0 | |
| `chart.home.allocation` | chart | `AllocationDonut` + sector bars | sector allocation | `etfs.json` look-through | kept | `/` | — | 0 | composition contract type in rebuild (donut retired, 3+ slices banned) |
| `figure.home.top-signal` | figure | `top-signal` widget | research leader + Sparkline | `report.json` | kept | `/` | — | 0 | |
| `figure.home.action-needed` | figure | `action-needed` widget | count of holdings beyond Hold | `portfolioAnalytics.js` | kept | `/` | — | 0 | |
| `figure.home.watchlist-preview` | figure | `watchlist-preview` widget | watchlist rows preview | `useWatchlist` | kept | `/` | — | 0 | |
| `chart.home.projection-panel` | chart | `ReportProjection` → `ProjectionPanel` | fan-chart projection + "Open Planning" link | `usePortfolioMonteCarloCalibration` | kept | `/` | — | 0 | link now points to `/portfolio?view=planning` |
| `figure.home.opportunity-cost` | figure | opportunity-cost card | benchmark potential earnings | `benchmark-report.json` | kept | `/` | — | 0 | |
| `chart.home.buying-the-dip` | chart | `BuyingTheDipChart` | dip-buying illustration | `report.json` | kept | `/` | — | 0 | |
| `figure.home.market-pulse-preview` | figure | `MarketPulsePreview` | FRED regime, 10Y, Fed funds, inflation + `DotPlot` | `advisor.json market` block | moved | `/markets` | `?view=indexes` | 1 | market decision, not status |
| `chart.home.market-heatmap` | chart | `MarketHeatmap` | sector/market heatmap | `report.json` | moved | `/markets` | `?view=indexes` | 1 | |
| `figure.home.focused-screen-cards` | figure | six `FocusedScreenCard`s | fast growth, value near lows, momentum, reversals, top ETFs previews | `screens/*.json` | kept | `/` | — | 0 | each card links into `/screens?recipe=<id>` |
| `figure.home.inside-information-card` | figure | `InsideInformationCard` | disclosed-positioning preview | `screens/inside-information.json` | kept | `/` | — | 0 | links to `/screens?recipe=inside-information` |
| `disclosure.home.as-of-eyebrow` | disclosure | eyebrow line | "Latest close · {date} · {n} names covered" | `report.json` | kept | `/` | — | 0 | serial-position: first-viewport item 1 |
| `disclosure.home.chart-resolution-note` | disclosure | inline note | 5-min/hourly/daily/weekly resolution or "still accumulating" | `usePortfolioQuotes` | kept | `/` | — | 0 | |
| `disclosure.home.last-quote` | disclosure | inline | "Last quote {time}" | live quotes | kept | `/` | — | 0 | |
| `disclosure.home.provisional-score` | disclosure | inline note | "The portfolio score remains provisional whenever a component is missing…" | — | kept | `/` | — | 0 | |
| `disclosure.home.research-prompts-only` | disclosure | footer note | "Research prompts only. Review the underlying evidence before acting." | — | kept | `/` | — | 0 | |
| `disclosure.home.hold-excluded` | disclosure | inline | "Hold positions are intentionally excluded." | — | kept | `/` | — | 0 | |
| `disclosure.home.screen-disclaimer` | disclosure | footer | "Research screens, not trade instructions…" | — | kept | `/` | — | 0 | |
| `disclosure.home.methodology-footer` | disclosure | footer note | historical-line methodology caveat (deposits/withdrawals/taxes/fees/dividends not reconstructed) | — | kept | `/` | — | 0 | protected disclosure — deposits-vs-return |
| `state.home.loading` | state | `<Loading/>` skeleton | — | — | kept | `/` | — | 0 | |
| `state.home.no-advisor-dataset` | state | `<Empty note="No advisor dataset is available yet."/>` | — | — | kept | `/` | — | 0 | |
| `state.home.no-holdings` | state | empty state | "Add holdings to unlock your report" | — | kept | `/` | — | 0 | |
| `state.home.cloud-offline` | state | empty state | "Cloud portfolio is offline" + Reconnect | `useAuth` | kept | `/` | — | 0 | |
| `state.home.chart-unavailable` | state | `.unavailable-panel` per chart | "{period} history is still building — two saved portfolio observations are needed" | — | kept | `/` | — | 0 | accumulating state |
| `state.home.screen-card-loading` | state | per focused-screen-card | "Loading this screen on the Report…" | — | kept | `/` | — | 0 | |
| `state.home.screen-card-empty` | state | per focused-screen-card | "No name clears this screen in the latest report." | — | kept | `/` | — | 0 | |
| `state.home.no-notable-activity` | state | inside-information card | "No notable disclosed activity right now." | — | kept | `/` | — | 0 | |
| `state.home.refresh-progress` | state | `RefreshProgress` + `role="status"` | refresh progress messages | `useAdvisorRefresh` | kept | `/` | — | 0 | |

## 2 · Research (`/research`) — absorbs Search, Watchlist

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.research.search-input` | control | text input | ticker/company search | local state | merged | `/research` | `?q=<term>` | 0 | absorbs `/search`; fixes the produced-but-never-read `?q=` param from Alerts |
| `control.research.sector-filter` | control | master toggle + checkbox group | filter by sector | local state | kept | `/research` | — | 0 | re-seeded all-checked on off→on transition |
| `control.research.sort` | control | select, 2 optgroups | 5 column sorts + N ranking models | local state | kept | `/research` | — | 0 | `InfoTag` explains active model |
| `control.research.asset-type` | control | select | Stocks & ETFs / Stocks / ETFs | local state | kept | `/research` | — | 0 | |
| `control.research.ownership-filter` | control | select | Bought & not bought / Bought / Not bought | local state | kept | `/research` | — | 0 | |
| `action.research.buy-100` | control | per-row button | "Buy $100" writes fractional Firestore position | `useFirebasePortfolio` | kept | `/research` | — | 0 | protected: never a real brokerage order |
| `control.research.watchlist-toggle` | control | per-row `WatchlistToggleButton` | add/remove watchlist | `useWatchlist` | kept | `/research` | — | 0 | |
| `alert.research.set-low-alert` | control | per-row button | "Set Low Alert · $X" creates `price_cross` below rule | `useAlerts` | kept | `/research` | — | 0 | one of 3 alert-creation surfaces |
| `control.research.secondary-metrics-toggle` | control | per-card expander | "Show/Hide secondary metrics" | local state | kept | `/research` | — | 0 | |
| `detail.research.open-stock-detail` | control | row chevron | opens Stock Detail Sheet | — | kept | `/research` | — | 0 | see §Stock Detail Sheet |
| `control.research.planner-funds` | control | number input | available-funds bucket planner | local state | kept | `/research` | — | 0 | |
| `control.research.planner-double-down` | control | switch | "Double down on positions I already own" | local state | kept | `/research` | — | 0 | |
| `figure.research.result-count` | figure | text | result count | — | kept | `/research` | — | 0 | |
| `figure.research.model-summary` | figure | `ModelSummary` coverage panel | qualified/scanned, composition, excluded + top-4 reasons | — | kept | `/research` | — | 0 | |
| `column.research.rank` | column | table | rank | `report.json` | kept | `/research` | — | 0 | |
| `column.research.stance` | column | table | stance | `report.json` | kept | `/research` | — | 0 | |
| `column.research.rating` | column | table | rating −5..+5 | `report.json` | kept | `/research` | — | 0 | |
| `column.research.model-score-why` | column | table | model score + "Why it ranks here" | `researchRating.js` | kept | `/research` | — | 0 | shown only when a model is active |
| `column.research.fundamentals` | column | table | fundamentals score | `report.json` | kept | `/research` | — | 0 | |
| `column.research.20d-return` | column | table | 20-day return | `report.json` | kept | `/research` | — | 0 | |
| `column.research.confidence` | column | table | confidence | `report.json` | kept | `/research` | — | 0 | |
| `column.research.timing` | column | table | entry timing | `entryTiming.js` | kept | `/research` | — | 0 | |
| `column.research.pct-portfolio` | column | table | % of my portfolio | `useFirebasePortfolio` | kept | `/research` | — | 0 | |
| `figure.research.mobile-card` | figure | `ResearchCard` | score/RatingBadge/chips/ModelWhy/metrics/Sparkline/buy row | — | kept | `/research` | — | 0 | mobile variant of table row |
| `figure.research.planner-bucket-list` | figure | allocation planner | ticker, style/sector tag, weight bar, $ amount + shares, per-bucket why | — | kept | `/research` | — | 0 | |
| `disclosure.research.thin-evidence-chip` | disclosure | `ThinEvidenceChip` | model-cap label / "Thin evidence" + resolved-% tooltip | — | kept | `/research` | — | 0 | |
| `disclosure.research.light-data-chip` | disclosure | `LightDataChip` | "Lighter data" | — | kept | `/research` | — | 0 | |
| `disclosure.research.as-of-line` | disclosure | per-card | "As of {last close}" or "Scored on the lighter universe data set" | — | kept | `/research` | — | 0 | |
| `disclosure.research.model-why-na` | disclosure | `ModelWhy` | "Not applicable to this company, weight redistributed rather than scored zero" | — | kept | `/research` | — | 0 | |
| `disclosure.research.score-capped` | disclosure | per-card | "Score capped at {limit}: {reason}" | — | kept | `/research` | — | 0 | |
| `disclosure.research.planner-notes` | disclosure | planner | style tilt / sector gap notes | — | kept | `/research` | — | 0 | |
| `disclosure.research.page-disclaimer` | disclosure | footer | universe counts, frozen-prior weights, "not measured optima", rating semantics, Buy-$100 caveat, "Rankings do not imply suitability" | — | kept | `/research` | — | 0 | protected disclosure |
| `state.research.loading` | state | `<Loading/>` | — | — | kept | `/research` | — | 0 | |
| `state.research.empty` | state | `<Empty/>` | — | — | kept | `/research` | — | 0 | |
| `state.research.etf-model-mismatch` | state | empty note | ETF + model mismatch | — | kept | `/research` | — | 0 | |
| `state.research.model-gate-not-cleared` | state | empty note | "the coverage panel above counts why" | — | kept | `/research` | — | 0 | |
| `state.research.no-filter-match` | state | empty note | "No companies match those filters." | — | kept | `/research` | — | 0 | |
| `state.research.buy-alert-status` | state | `role="status"` | per-ticker buy/alert status incl. "Reconnect Firebase to add this trade" | — | kept | `/research` | — | 0 | |
| `control.research.watchlist-search` | control | search input (was `/search`) | recent-search chips + Clear | localStorage `valuesignal.recent-searches` | merged | `/research` | `?view=picks` (search inline) | 0 | search absorbed as persistent chrome, 1 tap from anywhere, lands here |
| `figure.research.watchlist-lens-chips` | figure | lens filter chips (was Watchlist) | "All" + `STRATEGY_LENSES` with match count | localStorage `valuesignal.watchlistFilterSort` | merged | `/research` | `?view=watchlist` | 1 | |
| `control.research.watchlist-sort` | control | select (was Watchlist) | Recently added / Best buy for the price / Highest upside | localStorage | merged | `/research` | `?view=watchlist` | 1 | |
| `control.research.watchlist-sizing` | control | investable budget + max per stock inputs | position sizing card | localStorage `valuesignal.watchlistSizing` | merged | `/research` | `?view=watchlist` | 1 | |
| `control.research.watchlist-add-ticker` | control | input + button (was Watchlist) | add ticker to watchlist | `useWatchlist` | merged | `/research` | `?view=watchlist` | 1 | |
| `control.research.price-target-editor` | control | `PriceTargetEditor` | dip-buy / good-buy inputs, "Use suggested", save, "Alert me at dip price" | `watchlistPriceTargets.js` | merged | `/research` | `?view=watchlist` | 1 | third alert-creation surface |
| `disclosure.research.watchlist-sizing-note` | disclosure | inline | "Illustrative position sizing… Only a low-confidence block or published Sell forces $0." | — | merged | `/research` | `?view=watchlist` | 1 | |
| `state.research.watchlist-signed-out` | state | page-head variant | signed-out watchlist | — | merged | `/research` | `?view=watchlist` | 1 | |
| `state.research.watchlist-no-quote` | state | per-card note | "This ticker is saved, but no current quote or research record was published." | — | merged | `/research` | `?view=watchlist` | 1 | |
| `state.research.watchlist-empty` | state | empty state | no saved names | — | merged | `/research` | `?view=watchlist` | 1 | |
| `state.research.watchlist-no-filter-match` | state | empty state | "No saved names match this filter" + Clear filters | — | merged | `/research` | `?view=watchlist` | 1 | |

## 3 · Markets (`/markets`) — absorbs News

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.markets.time-range` | control | select | 1D/1W/1M/3M/1Y | local state | kept | `/markets` | `?view=indexes` | 0 | |
| `control.markets.direct-lookup` | control | search input | direct ticker lookup | local state | kept | `/markets` | `?view=indexes` | 0 | |
| `figure.markets.session-badge` | figure | badge | market type + breadth % | `report.json` | kept | `/markets` | `?view=indexes` | 0 | |
| `figure.markets.stat-cards` | figure | 5 `MarketStat` cards | index leader, hottest/weakest sector, top/worst stock | `report.json` | kept | `/markets` | `?view=indexes` | 0 | |
| `chart.markets.growth-chart` | chart | `GrowthChart` | selected index | `etf/{SPY,QQQ,DIA,IWM}.json` | kept | `/markets` | `?view=indexes` | 0 | |
| `figure.markets.index-strip` | figure | strip | index quotes | `usePortfolioQuotes` | kept | `/markets` | `?view=indexes` | 0 | |
| `figure.markets.lookup-result` | figure | result card | price, today, 20-day | — | kept | `/markets` | `?view=indexes` | 0 | |
| `link.markets.intraday-accumulation` | link | localStorage | 5-min observations, last 120 pts/index | localStorage `valuesignal.marketIntraday.v1` | kept | `/markets` | `?view=indexes` | 0 | default-only per URL-addressability rule |
| `disclosure.markets.live-observation-count` | disclosure | inline | "{n} live observations recorded today at five-minute intervals." vs fallback note | — | kept | `/markets` | `?view=indexes` | 0 | |
| `disclosure.markets.chart-caption` | disclosure | caption | "{ticker} adjusted closes through {date}." | — | kept | `/markets` | `?view=indexes` | 0 | |
| `state.markets.loading` | state | `<Loading/>` | — | — | kept | `/markets` | `?view=indexes` | 0 | |
| `state.markets.unavailable` | state | `<Empty note="Market data is unavailable in the latest refresh."/>` | — | — | kept | `/markets` | `?view=indexes` | 0 | |
| `state.markets.two-observations-needed` | state | empty note | "Two market observations are required to draw this range." | — | kept | `/markets` | `?view=indexes` | 0 | |
| `state.markets.no-lookup-match` | state | empty note | "No covered ticker matched '{query}'." | — | kept | `/markets` | `?view=indexes` | 0 | |
| `control.markets.news-sort` | control | `NewsSortToolbar` (was `/news`) | sort select + asc/desc toggle | `newsSort.js` | merged | `/markets` | `?view=news` | 1 | |
| `figure.markets.status-callout` | figure | callout | market-status | `advisor.json` | merged | `/markets` | `?view=news` | 1 | |
| `figure.markets.published-research-news` | figure | grid | news for published research | `advisor.json` | merged | `/markets` | `?view=news` | 1 | |
| `figure.markets.discovery-news` | figure | grid | "More companies to research" | `advisor.json` | merged | `/markets` | `?view=news` | 1 | |
| `disclosure.markets.news-supporting-evidence` | disclosure | page-sub | "Company news and sentiment are supporting evidence — not a substitute for…" | — | merged | `/markets` | `?view=news` | 1 | |
| `disclosure.markets.news-not-buy-signal` | disclosure | note | "News can surface an idea, but it is not a buy signal by itself." | — | merged | `/markets` | `?view=news` | 1 | |
| `state.markets.news-loading` | state | `<Loading/>` | — | — | merged | `/markets` | `?view=news` | 1 | |
| `state.markets.news-empty` | state | `<Empty/>` | — | — | merged | `/markets` | `?view=news` | 1 | |
| `state.markets.no-recent-articles` | state | empty note | "No recent articles matched the published research companies." | — | merged | `/markets` | `?view=news` | 1 | |
| `state.markets.no-company-news` | state | empty note | "No company news returned in this refresh." | — | merged | `/markets` | `?view=news` | 1 | |
| `link.markets.market-redirect` | link | `/market` → `/news` today | legacy singular redirect | — | merged | `/markets` | `?view=news` | 0 | collapses existing chain: `/market` → `/markets?view=news` directly |

## 4 · Portfolio (`/portfolio`) — absorbs Finances, Planning

Shell (all views): `PortfolioNavigation` sub-tabs, "Refresh prices", "Data actions" popover
(prices-updated timestamp, "Refresh all research", "Reanalyze portfolio", "Reapply Aug 25
Fidelity snapshot", "Export portfolio" JSON, `ImportHoldings`), pull-to-refresh, sort persisted
to preference `holdingSort`, analytics scope in sessionStorage `valuesignal.analytics.scope`,
`StockTickerTape`, Firebase sync-state pill, `#sell-signals` anchor, `RefreshProgress`.

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `nav.portfolio.sub-tabs` | nav | `PortfolioNavigation` | sub-tab bar | — | kept | `/portfolio` | `?view=<v>` | 0 | becomes the URL-addressable view selector itself |
| `action.portfolio.refresh-prices` | control | button | "Refresh prices" | `usePortfolioQuotes` | kept | `/portfolio` | — | 0 | |
| `control.portfolio.data-actions-menu` | control | `<details>` popover | Data actions (refresh all, reanalyze, reapply snapshot, export, import) | — | kept | `/portfolio` | — | 0 | |
| `export.portfolio.export-json` | export | button in popover | "Export portfolio" JSON download | `useFirebasePortfolio.exportPortfolio` | kept | `/portfolio` | — | 0 | |
| `control.portfolio.import-holdings` | control | `ImportHoldings` | upload holdings file | `portfolioImport.js` | kept | `/portfolio` | — | 0 | |
| `link.portfolio.sell-signals-anchor` | link | `href="#sell-signals"` | in-page anchor to suggested actions | — | kept | `/portfolio` | `#sell-signals` | 0 | |
| `disclosure.portfolio.firebase-sync-pill` | disclosure | pill | "Firebase live sync on / unavailable" | `useAuth` | kept | `/portfolio` | — | 0 | |
| `disclosure.portfolio.hold-not-shown` | disclosure | inline | "Hold positions are not shown here." | — | kept | `/portfolio` | — | 0 | |
| `link.portfolio.preview` | link | `?portfolioPreview=1` (dev) | fixture positions | — | kept | `/portfolio` | `?portfolioPreview=1` | 0 | dev-only |
| `control.portfolio.summary-time-range` | control | select | 1H/1D/1W/1M/3M/1Y | local state | kept | `/portfolio` | `?view=summary` | 0 | |
| `control.portfolio.summary-essential-only` | control | switch | "Essential only" | local state | kept | `/portfolio` | `?view=summary` | 0 | |
| `nav.portfolio.summary-view-tabs` | nav | 3 tabs | My Holdings / Vs S&P 500 / ${basis} Calculator | local state | kept | `/portfolio` | `?view=summary` | 0 | |
| `control.portfolio.add-position` | control | toggle → form | ticker, shares, cost basis ($/share vs Total $), purchase date | `useFirebasePortfolio` | kept | `/portfolio` | `?view=summary` | 0 | |
| `control.portfolio.sort-toolbar` | control | `PortfolioSortToolbar` | sort select + asc/desc | preference `holdingSort` | kept | `/portfolio` | `?view=summary` | 0 | desktop panel + mobile MobileSheet |
| `action.portfolio.per-card-actions` | control | per-card buttons | Research / Edit / Sell / Sell-across-lots / Remove | — | kept | `/portfolio` | `?view=summary` | 0 | Edit/Sell open MobileSheet forms |
| `control.portfolio.lot-sell-preview` | control | `LotSellSheet` | FIFO depletion preview | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `control.portfolio.suggested-actions-toggle` | control | `<details>` | suggested-actions expander | preference `suggestedActionsDefault` | kept | `/portfolio` | `?view=summary` | 0 | |
| `column.portfolio.comparison-purchase-date` | column | inline date input | purchase date, inside both comparison tables | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `figure.portfolio.kpi-row` | figure | KPI row | invested value (AnimatedNumber), today, total profit | `portfolioAnalytics.js` | kept | `/portfolio` | `?view=summary` | 0 | |
| `chart.portfolio.summary-growth-chart` | chart | 390px `GrowthChart` | current quantities vs historical prices | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `figure.portfolio.holdings-grid` | figure | grid | holdings cards | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `figure.portfolio.suggested-actions-list` | figure | list | ActionPill, trim size, "Why" opens modal | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `figure.portfolio.concentration-risk-card` | figure | card | concentration risk | `positionRisk.js` | kept | `/portfolio` | `?view=summary` | 0 | |
| `chart.portfolio.allocation-section` | chart | bars + `AllocationDonut` | asset allocation + sector | `portfolioSectorTilt.js` | kept | `/portfolio` | `?view=summary` | 0 | links to `?view=diversification` |
| `column.portfolio.benchmark-table` | column | `DataTable` | benchmark comparison rows | `portfolioBenchmarkComparison.js` | kept | `/portfolio` | `?view=summary` | 0 | TOTAL row |
| `column.portfolio.fixed-basis-table` | column | `DataTable` | ${basis} calculator rows | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.summary-chart-caption` | disclosure | caption | "Current quantities applied to historical prices; only invested holdings are included." | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.concentration-guideline` | disclosure | note | "Illustrative guidelines only ({maxPositionPct}%/{maxSectorPct}%) — not a rule to force a sale" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.allocation-classification-note` | disclosure | note | short-term vs long-term classification note | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.stop-loss-note` | disclosure | `StopLossNote` | "Stop $X · N% away / N% past it" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.comparison-footnote` | disclosure | footnote | positions before benchmark window show "–" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.fair-comparison-callout` | disclosure | callout | "The only fair comparison:" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `disclosure.portfolio.basis-calculator-callout` | disclosure | callout | "${basis} calculator:" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.summary-chart-building` | state | unavailable panel | "{period} history is still building — two five-minute account observations are needed" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.sector-unavailable` | state | note | "Sector data unavailable" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.no-positions` | state | empty | "No positions yet. Add a position to start tracking." | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.no-sell-actions` | state | empty | "No sell actions need review." | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.import-error` | state | `role="alert"` | "This file cannot be imported" + error list | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.import-no-changes` | state | status | "No changes" | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `state.portfolio.import-replace-warning` | state | `role="alert"` | "Replacing deletes N stored holdings. Switch to Merge to keep them." | — | kept | `/portfolio` | `?view=summary` | 0 | |
| `control.portfolio.performance-compare-over` | control | select | 1W/1M/3M/1Y/All | local state | kept | `/portfolio` | `?view=performance` | 0 | |
| `control.portfolio.cash-flow-ledger` | control | form | Deposit/Withdrawal/Dividend/Fee + amount/date | `taxLots.js` | kept | `/portfolio` | `?view=performance` | 0 | |
| `control.portfolio.ledger-complete-checkbox` | control | checkbox | "This ledger has every deposit/withdrawal since tracking started" | — | kept | `/portfolio` | `?view=performance` | 0 | gates money-weighted return |
| `control.portfolio.opportunity-cost-details` | control | `<details>` | opportunity-cost expander | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `figure.portfolio.twr-kpis` | figure | KPI row | TWR vs benchmark vs difference | `portfolioPerformance.js` | kept | `/portfolio` | `?view=performance` | 0 | first-viewport item 2 (primary performance work) |
| `chart.portfolio.indexed-growth-chart` | chart | `GrowthChart` | indexed, both lines start at 0% | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `figure.portfolio.xirr-kpi` | figure | KPI | money-weighted XIRR | `portfolioAnalytics.js` | kept | `/portfolio` | `?view=performance` | 0 | |
| `figure.portfolio.reconciliation-bridge` | figure | bridge | Beginning NAV → flows → ending NAV → residual, RECONCILED/failed status | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `chart.portfolio.opportunity-cost-chart` | chart | 3-series chart | holdings / S&P same-basis / cost-basis-flat | `portfolioBenchmarkComparison.js` | kept | `/portfolio` | `?view=performance` | 0 | never conflates deposits with return (protected) |
| `disclosure.portfolio.twr-immune-to-flows` | disclosure | header comment made visible | TWR reprices exact share count, immune to cash-flow timing | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `disclosure.portfolio.xirr-accumulating` | disclosure | note | "Money-weighted return (XIRR) is accumulating: {reason}" | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `disclosure.portfolio.bridge-accumulating` | disclosure | note | "Reconciliation bridge is accumulating: {reason}" | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `disclosure.portfolio.bridge-not-tracked` | disclosure | labels | FX/taxes/trading-costs "(not tracked)" | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `disclosure.portfolio.opp-cost-caption` | disclosure | caption | tracked vs untracked position counts | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `state.portfolio.performance-building` | state | unavailable panel | "Comparison history is still building — Two shared market dates are needed" | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `state.portfolio.ledger-validation` | state | inline error | "Enter a positive amount and a date." | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `state.portfolio.ledger-save-error` | state | inline error | "Could not save: {error}" | — | kept | `/portfolio` | `?view=performance` | 0 | |
| `export.portfolio.data-overview-menu` | export | `ExportMetricsMenu` | copy-all / download-JSON | `exportSnapshot.js` | kept | `/portfolio` | `?view=data` | 0 | protected capability — data-overview copy |
| `control.portfolio.attribution-period` | control | selector | attribution period | `PortfolioMoveExplanation` | kept | `/portfolio` | `?view=data` | 0 | |
| `control.portfolio.analytics-scope` | control | select | All history / Since activation / Live only / Backtest period | sessionStorage `valuesignal.analytics.scope` | kept | `/portfolio` | `?view=data&scope=<s>` | 0 | URL-addressability rule: read from param first |
| `nav.portfolio.analytics-view-tabs` | nav | tabs | overview / all / algorithm / historical | sessionStorage `valuesignal.analytics.view` | kept | `/portfolio` | `?view=data&analytics=<a>` | 0 | algorithm view auto-narrows scope |
| `figure.portfolio.move-explanation` | figure | `PortfolioMoveExplanation` | plain-language move explanation | — | kept | `/portfolio` | `?view=data` | 0 | |
| `chart.portfolio.scenario-sensitivity` | chart | `ScenarioSensitivityPanel` | scenario sensitivity | `scenarioSensitivity.js`, `signal_metrics.json` scenario_* | kept | `/portfolio` | `?view=data` | 0 | |
| `figure.portfolio.auto-overview-line` | figure | `AutoOverviewLine` | plain-language brief with tone | — | kept | `/portfolio` | `?view=data` | 0 | |
| `figure.portfolio.holdings-data-quality` | figure | `HoldingsDataQuality` | per-ticker coverage%/age/violation flags | — | kept | `/portfolio` | `?view=data` | 0 | "N of M need attention", "Not in the scored universe" |
| `figure.portfolio.fund-cost-overview` | figure | `FundCostOverview` | fund cost overview | `etfs.json` | kept | `/portfolio` | `?view=data` | 0 | |
| `figure.portfolio.time-to-valid-metric` | figure | `TimeToValidMetric` | "{observations} of {floor} observations collected" countdown | `SAMPLE_SIZE_WARNING_FLOOR` | kept | `/portfolio` | `?view=data` | 0 | accumulating state |
| `figure.portfolio.performance-metrics-overview` | figure | `PerformanceMetrics` overview | Overall evidence, Risk & performance, Vs benchmark, Short-term view, Evidence matrix | `docs/METRIC_INVENTORY.md` §1-2 rows | kept | `/portfolio` | `?view=data` | 0 | see §Metrics for individual rows |
| `figure.portfolio.all-metrics-tearsheet` | figure | "All metrics" tear-sheet | — | — | kept | `/portfolio` | `?view=data&analytics=all` | 0 | |
| `figure.portfolio.prospective-clock` | figure | algorithm view | "Prospective clock 0 / 24 periods" | `research_evidence.json` | kept | `/portfolio` | `?view=data&analytics=algorithm` | 0 | |
| `figure.portfolio.baseline-comparison` | figure | algorithm view | baseline comparison | — | kept | `/portfolio` | `?view=data&analytics=algorithm` | 0 | "This is observational, not a causal claim." |
| `chart.portfolio.signal-metrics-embed` | chart | `SignalMetricsPanel` embed | 64-metric report | `signal_metrics.json` | kept | `/portfolio` | `?view=data&analytics=algorithm` | 0 | ALSO rendered at `/evidence?section=validation` — same component, two mounts |
| `chart.portfolio.monte-carlo-panel-embed` | chart | `MonteCarloProjectionPanel` embed | Monte Carlo panel | `validation/monte_carlo_projection.json` | kept | `/portfolio` | `?view=data&analytics=algorithm` | 0 | |
| `chart.portfolio.rolling-sharpe-historical` | chart | historical view | rolling 60-day Sharpe chart | — | kept | `/portfolio` | `?view=data&analytics=historical` | 0 | |
| `state.portfolio.holdings-quality-count` | state | note | "N of M need attention" | — | kept | `/portfolio` | `?view=data` | 0 | |
| `disclosure.portfolio.scope-rationale` | disclosure | inline | scope-switch rationale | `portfolio/format.js` | kept | `/portfolio` | `?view=data` | 0 | |
| `disclosure.portfolio.sample-note` | disclosure | inline | "{n} daily returns · {start} to {end} · {n}% weekday coverage" | — | kept | `/portfolio` | `?view=data` | 0 | |

## 5 · Portfolio — Diversification (`/portfolio?view=diversification`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `figure.diversification.score-dial` | figure | dial | "You hold N positions / M effective bets" | `portfolioAnalytics.js` | kept | `/portfolio` | `?view=diversification` | 1 | |
| `figure.diversification.effective-bet-summary` | figure | summary | raw holdings, effective bets, effective holdings (1/HHI) | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `chart.diversification.sector-allocation` | chart | `AllocationDonut` | look-through sector allocation | `etfs.json` | kept | `/portfolio` | `?view=diversification` | 1 | |
| `chart.diversification.score-components` | chart | `<progress>` bars | score components | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `chart.diversification.correlation-heatmap` | chart | `CorrelationHeatmap` | pairwise correlation | `portfolioAnalytics.js` | kept | `/portfolio` | `?view=diversification` | 1 | |
| `figure.diversification.risk-decomposition` | figure | table | ES 95%, tracking error, active share + per-holding weight vs share-of-risk | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `chart.diversification.factor-loadings` | chart | table | FF5+momentum loadings, NW HAC SE, annualized alpha + t-stat, R² | `factorAnalytics.js`, `factors/french.json` | kept | `/portfolio` | `?view=diversification` | 1 | protected: |t|<2 statistically meaningless |
| `chart.diversification.theme-exposure-grid` | chart | grid | theme exposure | `advisor.json theme_screen` | kept | `/portfolio` | `?view=diversification` | 1 | |
| `chart.diversification.holdings-by-allocation` | chart | bars | holdings by allocation | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `figure.diversification.industry-concentration` | figure | list | industry concentration | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `detail.diversification.info-tags` | detail | ~7 `InfoTag` popovers | effective bets, look-through, score components, correlation, risk decomposition, factor exposure, theme exposure, holdings, industry concentration | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `disclosure.diversification.provisional-label` | disclosure | label | "Provisional score" | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `disclosure.diversification.coverage-note` | disclosure | note | "Coverage: N% of entered positions have a current price. This score is descriptive…" | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `disclosure.diversification.unresolved-etf-lookthrough` | disclosure | note | "${x} is unresolved ETF exposure because published look-through data is unavailable." | — | kept | `/portfolio` | `?view=diversification` | 1 | protected disclosure |
| `disclosure.diversification.multiple-testing-hurdle` | disclosure | note | "The registered multiple-testing evidence hurdle is a positive t-statistic above 3." | — | kept | `/portfolio` | `?view=diversification` | 1 | protected disclosure |
| `disclosure.diversification.active-share-coverage` | disclosure | note | "Active share — shown only with sufficient benchmark constituent coverage" | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `disclosure.diversification.lookthrough-provisional` | disclosure | note | "Missing look-through stays visible as unavailable and makes the result provisional." | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.loading` | state | `<Loading/>` | — | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.no-holdings` | state | `<Empty note="Add portfolio holdings before calculating diversification."/>` | — | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.factor-history-accumulating` | state | panel | "Factor history is accumulating — {reason}" | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.no-concentration-warnings` | state | note | "No concentration warnings in covered holdings." | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.theme-exposure-unavailable` | state | note | "Theme exposure is unavailable in the current research snapshot." | — | kept | `/portfolio` | `?view=diversification` | 1 | |
| `state.diversification.risk-reason` | state | note | `risk.reason` when decomposition unavailable | — | kept | `/portfolio` | `?view=diversification` | 1 | |

## 6 · Portfolio — Insights (`/portfolio?view=insights`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `export.insights.share-today` | export | button | "Share today" — `navigator.share`/clipboard fallback | — | kept | `/portfolio` | `?view=insights` | 1 | announces "Copied to clipboard." |
| `figure.insights.mood-hero` | figure | hero | emoji + label + blurb + recap stats | `portfolioAnalytics.js` | kept | `/portfolio` | `?view=insights` | 1 | |
| `chart.insights.vs-indexes-chart` | chart | `GrowthChart` | cash-flow-aware vs SPY/QQQ/DIA/IWM | `benchmark-report.json` | kept | `/portfolio` | `?view=insights` | 1 | |
| `figure.insights.holdings-vs-benchmark` | figure | list | per-ticker delta vs benchmark | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `figure.insights.as-a-trader` | figure | stats | win rate, avg win/loss, best/worst trade | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `figure.insights.purchase-timing` | figure | list | per-position entry-quality | `entryTiming.js` | kept | `/portfolio` | `?view=insights` | 1 | |
| `disclosure.insights.index-comparison-methodology` | disclosure | InfoTag | index comparison methodology, pending transfers excluded | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `disclosure.insights.chart-caption` | disclosure | caption | start value/date + each index's counterfactual ending value | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `state.insights.loading` | state | `<Loading/>` (also while `!currentUser`) | — | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `state.insights.no-holdings` | state | `<Empty note="Add portfolio holdings to see how you're doing…"/>` | — | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `state.insights.not-enough-history` | state | note | "Not enough history yet — cash-flow-aware comparison needs two shared market dates" | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `state.insights.no-realized-sales` | state | note | "Record position sales on the Portfolio page to build realized win-rate…" | — | kept | `/portfolio` | `?view=insights` | 1 | |
| `state.insights.entry-timing-insufficient` | state | note | "Not enough price history around your purchase dates yet to judge entry timing." | — | kept | `/portfolio` | `?view=insights` | 1 | |

## 7 · Portfolio — Finances (`/portfolio?view=finances`, was `/finances`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `nav.finances.tabs` | nav | 3 tabs | Budget / Auto-Split Pools / Retirement | local state | merged | `/portfolio` | `?view=finances&tab=<t>` | 1 | |
| `control.finances.budget-add-form` | control | form | name, monthly amount, type + Remove | `useFirebaseFinances` | merged | `/portfolio` | `?view=finances&tab=budget` | 1 | |
| `action.finances.use-as-retirement-contribution` | control | text button | "Use as retirement contribution" | — | merged | `/portfolio` | `?view=finances&tab=budget` | 1 | |
| `control.finances.pool-add-form` | control | form | name, percent + Remove | — | merged | `/portfolio` | `?view=finances&tab=pools` | 1 | |
| `control.finances.deposit-split-preview` | control | form | amount-to-split with live per-pool preview | — | merged | `/portfolio` | `?view=finances&tab=pools` | 1 | |
| `control.finances.retirement-assumptions` | control | inputs | age, retirement age, inflation %, current savings, monthly contribution, plan-through age, monthly spend | `useFirebaseFinances` settings | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | writes straight to Firestore |
| `control.finances.return-target-slider` | control | range input | annual-return-target, commits on pointerup/keyup | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `action.finances.sync-savings-from-portfolio` | control | button | "Sync current savings from portfolio ($X)" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `control.finances.account-add-form` | control | form | name, type from `ACCOUNT_TYPES` | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | per-account annual-contribution input |
| `nav.finances.account-tabs` | nav | tab nav | scrollIntoView per account | `#finance-account-{id}` | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `figure.finances.kpi-row` | figure | 3 KPIs | monthly leftover, saved in pools, median at retirement | `coastFire.js` | merged | `/portfolio` | `?view=finances&tab=budget` | 1 | |
| `chart.finances.pool-bars` | chart | bars | pool allocation | — | merged | `/portfolio` | `?view=finances&tab=pools` | 1 | |
| `chart.finances.contribution-room-bars` | chart | bars | per-account contribution room vs IRS limit | `retirementLimits.js` | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `figure.finances.retirement-kpi-row` | figure | KPIs | median at retirement, in today's dollars, savings-last probability | `projectionEngine.js` | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `chart.finances.projection-panel` | chart | `ProjectionPanel` | retirement projection fan chart | `useProjectionSimulation` | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `disclosure.finances.irs-limit-note` | disclosure | note | "Track contribution room against the 2026 IRS limits… Roth IRA room can phase out…" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `disclosure.finances.bootstrap-paths-note` | disclosure | note | "From 5,000 historical return paths" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `disclosure.finances.dotted-median-note` | disclosure | note | "The dotted median targets {x}% annually. Historical monthly returns determine the range." | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `disclosure.finances.return-target-evidence-range` | disclosure | note | "{ytd}% year to date to {1y}% trailing one year" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `state.finances.loading` | state | `<Loading/>` | — | — | merged | `/portfolio` | `?view=finances` | 1 | |
| `state.finances.simulating` | state | KPI placeholder | "Simulating…" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `state.finances.no-income-items` | state | empty | "No income items yet." | — | merged | `/portfolio` | `?view=finances&tab=budget` | 1 | |
| `state.finances.no-expense-items` | state | empty | "No expense items yet." | — | merged | `/portfolio` | `?view=finances&tab=budget` | 1 | |
| `state.finances.no-pools` | state | empty | "Add at least one pool to start splitting deposits." | — | merged | `/portfolio` | `?view=finances&tab=pools` | 1 | |
| `state.finances.no-accounts` | state | empty | "Add a 401(k), IRA, HSA, or taxable account…" | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |

## 8 · Portfolio — Planning (`/portfolio?view=planning`, was `/planning`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.planning.track-current-holdings` | control | checkbox | "Track my current-holdings return" (disables return-target slider) | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.track-coast-fire` | control | checkbox | "Track Coast FIRE status" | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | |
| `action.planning.recalibrate` | control | button | "Recalibrate now" | `usePortfolioMonteCarloCalibration` | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.return-target-lever` | control | range | annual return target | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | commits on pointerup/keyup, records probability delta |
| `control.planning.contribution-lever` | control | range | monthly contribution | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.retirement-age-lever` | control | range | target retirement age | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.withdrawal-lever` | control | range | annual retirement withdrawal | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.aggressiveness-select` | control | select | allocation aggressiveness | Firestore settings | merged | `/portfolio` | `?view=planning` | 1 | |
| `control.planning.goal-form` | control | form | name, target amount, target date, funding-pool select | — | merged | `/portfolio` | `?view=planning` | 1 | + goal chip list selection |
| `chart.planning.success-probability-gauge` | chart | gauge | success probability + band verdict | `projectionEngine.js` | merged | `/portfolio` | `?view=planning` | 1 | dial contract type, labeled scale |
| `figure.planning.contribution-lever-comparison` | figure | sentence | contribution-lever comparison | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `figure.planning.dotted-median-target-panel` | figure | panel | dotted-median-target | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `chart.planning.monte-carlo-calibration` | chart | panel | Sharpe, Sortino, Lo-adjusted Sortino, Calmar | `usePortfolioMonteCarloCalibration` | merged | `/portfolio` | `?view=planning` | 1 | |
| `figure.planning.coast-fire-panel` | figure | panel | target at retirement, needed today, projected balance | `coastFire.js` | merged | `/portfolio` | `?view=planning` | 1 | |
| `figure.planning.lever-deltas` | figure | section | per-lever percentage-point deltas | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `chart.planning.projection-fan-chart` | chart | `ProjectionFanChart` | fan chart | `projectionWorker.js` | merged | `/portfolio` | `?view=planning` | 1 | Planning worker <400ms budget |
| `chart.planning.sequence-risk-panel` | chart | `SequenceRiskPanel` | two same-average paths, different endings | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `figure.planning.goals-section` | figure | section | per-goal probability | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `disclosure.planning.assumption-not-forecast` | disclosure | repeated note | "This is a planning assumption, not a forecast." | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `disclosure.planning.distribution-solved-algebraically` | disclosure | note | "solved algebraically from these ratios, not resampled" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `disclosure.planning.last-calibrated` | disclosure | note | "Last calibrated {date} from {n} daily returns through {date}" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `disclosure.planning.lo-sortino-insufficient` | disclosure | note | "Lo-adjusted Sortino — Insufficient" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `disclosure.planning.historical-paths-count` | disclosure | note | "{n} historical paths through age {end}" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.loading` | state | `<Loading/>` gate | — | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.projection-running` | state | "…" placeholder | — | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.waiting-on-history` | state | note | "Waiting on enough daily history — at least 20 daily portfolio observations are required…" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.two-dated-values-needed` | state | note | "unavailable until there are at least two dated market values" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.set-retirement-age-first` | state | note | "Set a retirement age and an annual retirement withdrawal above to see this." | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.move-lever-to-compare` | state | note | "Move this lever to compare outcomes" | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.goal-calculating` | state | status | "Calculating" goal probability | — | merged | `/portfolio` | `?view=planning` | 1 | |
| `state.planning.updated-in-ms` | state | status | "Updated in {n} ms" | — | merged | `/portfolio` | `?view=planning` | 1 | |

## 9 · Screens (`/screens?recipe=<id>`) — absorbs 12 ranked-list screen families

### 9a. Swing (`?recipe=swing`) — richest disclosure set

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `nav.screens.swing-tier-tablist` | nav | `role="tablist"` | three horizon-book tabs, `aria-selected` | `screens/swing.json` | merged | `/screens` | `?recipe=swing&tier=<t>` | 1 | |
| `control.screens.swing-how-this-works` | control | `<details>` | "How this works" | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `control.screens.swing-filters` | control | `ResponsiveControlPanel` | Sector, Market cap, Min liquidity ($M), Min signal coverage (%), Membership, Short interest (Show/Hide/Only suppressed) | local state | merged | `/screens` | `?recipe=swing&...` | 1 | 6 filters, URL-addressable |
| `control.screens.swing-column-view-toggle` | control | toggle, `aria-pressed` | Simple vs "Every number" | local state | merged | `/screens` | `?recipe=swing&cols=<c>` | 1 | |
| `figure.screens.swing-tier-headline` | figure | `TierHeadline` | hold N sessions, N names qualify, N of M clear cost | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `figure.screens.swing-tier-economics` | figure | `TierEconomics` | round trips/yr, median bps, assumed alpha, median net edge, names clearing cost, break-even alpha/month | — | merged | `/screens` | `?recipe=swing` | 1 | "assumed alpha" labeled as assumption |
| `figure.screens.swing-evidence-panel` | figure | `EvidencePanel` | per-leg weight/horizon/direction, % payoff in window, resolved-on-%, effect, citation, caveat + negative screen | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `figure.screens.swing-cost-panel` | figure | `CostPanel` | median round trip by book size, cost ceiling | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `column.screens.swing-table` | column | `DataTable` | per-leg z-scores, composite, percentile, verdict (Worth buying/Maybe/Don't buy), net edge bps, signal coverage, short interest, flags | `screens/swing.json` | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-shortfall-caveat` | disclosure | note | "the median name in the book costs more to round trip than the tier assumes it earns" | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-decay-haircut` | disclosure | note | decay haircut: "{n}% lower out of sample, {n}% lower after publication" | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-spread-proxy` | disclosure | note | "Spread is a liquidity-tiered proxy, not a measured spread" | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-unfillable-leg` | disclosure | note | a leg a row can't fill contributes nothing rather than rescaling | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-footer-versions` | disclosure | footer | schema/model/config versions, scored/eligible/suppressed counts | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `disclosure.screens.swing-frozen-priors` | disclosure | InfoTag | "Frozen starting priors" — 2026-09-01 clock, 24 monthly periods, 45% technical, "no technical sub-signal clearing its noise standard" | — | merged | `/screens` | `?recipe=swing` | 1 | protected disclosure |
| `disclosure.screens.swing-absent-indicators` | disclosure | list | deliberately-absent RSI/MACD/Bollinger/VWAP/OBV/candlesticks | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `state.screens.swing-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `state.screens.swing-snapshot-unavailable` | state | `role="alert"` | "Screen snapshot unavailable" | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `state.screens.swing-unavailable-reason` | state | `<Empty note={'Unavailable: ' + reason_code}/>` | — | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `state.screens.swing-no-filter-match` | state | empty | "No name matches these filters." | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `state.screens.swing-cell-not-resolvable` | state | per-cell "–" | tooltip | — | merged | `/screens` | `?recipe=swing` | 1 | |

### 9b. Fast Growth (`?recipe=fast-growth`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.screens.fastgrowth-screen-select` | control | select | Breakout in progress / Emerging growth (unvalidated) | `researchScreens.js` | merged | `/screens` | `?recipe=fast-growth&sub=<s>` | 1 | |
| `control.screens.fastgrowth-sector-filter` | control | select | sector filter | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `column.screens.fastgrowth-breakout-columns` | column | table | 5-day, 20-day, acceleration, score | `report.json` | merged | `/screens` | `?recipe=fast-growth&sub=breakout` | 1 | |
| `column.screens.fastgrowth-emerging-columns` | column | table | revenue growth, relative strength, volatility contracting | `report.json` | merged | `/screens` | `?recipe=fast-growth&sub=emerging` | 1 | |
| `figure.screens.fastgrowth-mobile-cards` | figure | `BreakoutCard`/`EmergingGrowthCard` | mobile cards with Sparkline | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `disclosure.screens.fastgrowth-unvalidated` | disclosure | `role="note"` panel | "Prospective and unvalidated." No backtest/rank-IC/track record | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `disclosure.screens.fastgrowth-footer` | disclosure | footer | "A breakout screen flags a change in pace, not a guaranteed continuation." | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `state.screens.fastgrowth-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `state.screens.fastgrowth-unavailable` | state | `role="alert"` | "Screen snapshot unavailable" | — | merged | `/screens` | `?recipe=fast-growth` | 1 | |
| `state.screens.fastgrowth-empty-breakout` | state | note | breakout-view empty | — | merged | `/screens` | `?recipe=fast-growth&sub=breakout` | 1 | |
| `state.screens.fastgrowth-empty-emerging` | state | note | emerging-view empty | — | merged | `/screens` | `?recipe=fast-growth&sub=emerging` | 1 | |

### 9c. Options + 7 strategies (`?recipe=options&strategy=<id>`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `nav.screens.options-sub-nav` | nav | `OptionsNavigation` | 8 sub-tabs | `strategyScreenConfigs.js` | merged | `/screens` | `?recipe=options&strategy=<id>` | 1 | already-consolidated model preserved |
| `control.screens.options-direction-select` | control | select | Calls & puts / Calls / Puts | local state | merged | `/screens` | `?recipe=options` | 1 | index only |
| `control.screens.options-strategy-select` | control | select (when >1) | strategy picker | — | merged | `/screens` | `?recipe=options` | 1 | |
| `control.screens.options-sector-filter` | control | select | sector | — | merged | `/screens` | `?recipe=options` | 1 | |
| `control.screens.options-trade-ticket` | control | per-card expander | "How to enter this in your broker" → `TradeTicketReference` | — | merged | `/screens` | `?recipe=options&strategy=<id>` | 1 | action/quantity/expiration/strike/type, bid/mid/ask, order type/price/TIF |
| `control.screens.options-watchlist-toggle` | control | `WatchlistToggleButton` | per-row | `useWatchlist` | merged | `/screens` | `?recipe=options` | 1 | |
| `column.screens.options-table` | column | table | rank, ticker, sector, side/strategy, strike/legs, expiration, DTE, IV, IV/RV, spread, open interest, capital required, score | `screens/options*.json` | merged | `/screens` | `?recipe=options` | 1 | |
| `figure.screens.options-mobile-cards` | figure | mobile idea cards | confidence bar + plain-language reasons | — | merged | `/screens` | `?recipe=options` | 1 | |
| `figure.screens.options-cross-strategy-comparison` | figure | `CrossStrategyComparison` (index only) | — | — | merged | `/screens` | `?recipe=options` | 1 | |
| `figure.screens.options-backtest-summary` | figure | `BacktestSummary` | per-strategy backtest | `screens/*-backtest.json` | merged | `/screens` | `?recipe=options&strategy=<id>` | 1 | |
| `disclosure.screens.options-not-instruction` | disclosure | panel | "Research screen, not a trade instruction." leverage/decay/expiry/no-brokerage-connection | — | merged | `/screens` | `?recipe=options` | 1 | |
| `disclosure.screens.options-footer` | disclosure | footer | schema/model/config + "IV, spreads, OI are snapshots… Black-Scholes at 0% risk-free rate, a stated simplification" | — | merged | `/screens` | `?recipe=options` | 1 | |
| `state.screens.options-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=options` | 1 | |
| `state.screens.options-unavailable` | state | `role="alert"` | "Screen snapshot unavailable" | — | merged | `/screens` | `?recipe=options` | 1 | |
| `state.screens.options-chain-unavailable` | state | note | "Options-chain data is unavailable in this snapshot." | — | merged | `/screens` | `?recipe=options` | 1 | |
| `state.screens.options-no-clearing-ticker` | state | note | "No ticker currently clears…" | — | merged | `/screens` | `?recipe=options` | 1 | |
| `state.screens.options-no-filter-match` | state | note | "No candidate matches the current filters." | — | merged | `/screens` | `?recipe=options` | 1 | |
| `link.screens.options-legacy-redirects` | link | 7 flat redirects | `/screens/<strategy>` → `/screens/options/<strategy>` today | — | merged | `/screens` | `?recipe=options&strategy=<id>` | 0 | chain-collapses to the new URL directly |

### 9d. Generic ResearchScreen family — Momentum, Quality-at-lows, Earnings timeliness, Structural/tactical matrix

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.screens.generic-filters` | control | `ResponsiveControlPanel` | Sector, Market cap, Min confidence, Min liquidity, Min structural, Min tactical, Membership | `screens/{momentum,quality-value,earnings-timeliness,structural-tactical}.json` | merged | `/screens` | `?recipe=<momentum\|quality-value\|earnings\|matrix>` | 1 | shared filter panel across all four |
| `chart.screens.generic-quadrant-scatter` | chart | `ScatterChart` | structural vs tactical, median splits, 4-tone classification | — | merged | `/screens` | `?recipe=matrix` | 1 | scatter contract type; shown only when both axes present |
| `column.screens.generic-table` | column | table | rank, ticker, classification, peer group, percentile, structural, tactical, confidence, warnings/reason codes | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `figure.screens.generic-mobile-card` | figure | card | `preferences.mobileResearchView` visual(3)/detailed(6) fields | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `disclosure.screens.generic-coverage-note` | disclosure | `role="note"` | `data.coverage_note` | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `disclosure.screens.generic-footer` | disclosure | footer | "Schema {v} · model {v} · config {v}. Rankings are hypotheses for prospective validation, not claims of outperformance." | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `disclosure.screens.quality-value-window-note` | disclosure | route description | "own-history window is only as deep as the collected point-in-time record, every row publishes its window" | — | merged | `/screens` | `?recipe=quality-value` | 1 | |
| `state.screens.generic-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `state.screens.generic-unavailable` | state | `role="alert"` | "Screen snapshot unavailable" | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `state.screens.generic-reason-code` | state | `<Empty>` | `Unavailable: {reason_code}` | — | merged | `/screens` | `?recipe=<id>` | 1 | |
| `state.screens.generic-no-filter-match` | state | empty | "No results match these filters." | — | merged | `/screens` | `?recipe=<id>` | 1 | |

### 9e. Theme Exposure (`?recipe=themes`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `action.screens.themes-rerank-button` | control | button | "Re-rank these N names" | `useAdvisorRefresh` | merged | `/screens` | `?recipe=themes` | 1 | |
| `control.screens.themes-hide-holdings` | control | checkbox | "Hide my holdings (N)" | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `nav.screens.themes-index` | nav | index list | theme index with trend verdicts | `theme-peers.json` | merged | `/screens` | `?recipe=themes` | 1 | |
| `figure.screens.themes-cross-theme-section` | figure | section | cross-theme names | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `figure.screens.themes-per-theme-blocks` | figure | blocks | trend/verdict, supply-chain relative strength, largest members, Leaders, Connected-not-yet-rerated | `advisor.json theme_screen` | merged | `/screens` | `?recipe=themes` | 1 | `GroupCount` "Showing N of M" |
| `detail.screens.themes-info-tags` | detail | InfoTags | Reading the index, Where themes cross, Columns, Built by, Leaders, Connected, Research rating | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `disclosure.screens.themes-momentum-excluded` | disclosure | note | "Price momentum contributes nothing to this ranking by design" | — | merged | `/screens` | `?recipe=themes` | 1 | protected: theme-screen anti-hype guardrail |
| `disclosure.screens.themes-hide-holdings-note` | disclosure | `role="status"` | trend reading deliberately not recomputed on subset | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `disclosure.screens.themes-supply-chain-note` | disclosure | note | "Median relative strength per stage of the supply chain" | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `state.screens.themes-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `state.screens.themes-unavailable` | state | `role="alert"` | "Theme screen unavailable" | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `state.screens.themes-unavailable-reason` | state | `<Empty>` | `theme_screen.unavailable_reason` | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `state.screens.themes-no-leader` | state | note | "No published leader or holding cleared this theme's signal minimum yet." | — | merged | `/screens` | `?recipe=themes` | 1 | |
| `state.screens.themes-no-connected` | state | note | "No sector-connected candidate cleared this theme's signal minimum in the latest report." | — | merged | `/screens` | `?recipe=themes` | 1 | |

### 9f. Early Session (`?recipe=early-session`) — read-only

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `figure.screens.earlysession-gate-summary` | figure | summary | "Current verdict: Gated · 0 live candidates" | `screens/early-session.json` | merged | `/screens` | `?recipe=early-session` | 1 | |
| `figure.screens.earlysession-gate-cards` | figure | per-screen cards | premarket_reversal / first-hour, "Killed by data gate", reason, fallback + candidate count | — | merged | `/screens` | `?recipe=early-session` | 1 | |
| `figure.screens.earlysession-capability-matrix` | figure | Phase 0 matrix | capability, provider, granularity, freshness, verdict (Available/Conditional/Unavailable) | — | merged | `/screens` | `?recipe=early-session` | 1 | |
| `disclosure.screens.earlysession-guardrail` | disclosure | aside | "Killed screens are a successful research outcome, not a pipeline error." + permitted-labels guardrail | — | merged | `/screens` | `?recipe=early-session` | 1 | gated state is a feature, not an error |
| `disclosure.screens.earlysession-footer` | disclosure | footer | `data.disclaimer` + schema/model version | — | merged | `/screens` | `?recipe=early-session` | 1 | |
| `state.screens.earlysession-unavailable` | state | `role="alert"` | "Capability report unavailable" | — | merged | `/screens` | `?recipe=early-session` | 1 | |

### 9g. Politics (`?recipe=politics`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `action.screens.politics-rerun` | control | button (signed-in) | "Re-run collection" | `useScreenRefresh('congress')` | merged | `/screens` | `?recipe=politics` | 1 | |
| `control.screens.politics-filters` | control | `ResponsiveControlPanel` | Chamber, Flag (8), Sort by | `screens/congress-trades.json` | merged | `/screens` | `?recipe=politics` | 1 | |
| `control.screens.politics-identity-reveal` | control | `<details>` | reveals issuer/filer names | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `figure.screens.politics-signals-panel` | figure | `SignalsPanel` | top-5 disclosed signals | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `figure.screens.politics-top-tickers` | figure | `TopTickersPanel` | top-10 unusual stocks | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `figure.screens.politics-kpi-cards` | figure | 5 KPIs | trades, filings estimated, volume ceiling, politicians, issuers | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `chart.screens.politics-bar-timeline` | chart | `BarTimeline` | monthly disclosed volume (amount-range midpoints) | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `column.screens.politics-table` | column | `DataTable` | main disclosure table | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `disclosure.screens.politics-flags-note` | disclosure | note | "Flags are computed directly from the disclosure data… not a claim that any trade was improper." | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `disclosure.screens.politics-not-a-score` | disclosure | note | "not a score, not advice" on both leaderboards | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `disclosure.screens.politics-stock-act-ranges` | disclosure | note | "Reported amounts are STOCK Act ranges, not exact figures." | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `disclosure.screens.politics-since-purchase-caveat` | disclosure | note | "'Since purchase' only appears for a plain stock purchase…" | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `disclosure.screens.politics-accumulated-days` | disclosure | note | "{n} day(s) of accumulated history" | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `state.screens.politics-loading` | state | `<Loading/>` | — | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `state.screens.politics-unavailable` | state | `role="alert"` | "Political trades screen unavailable" | — | merged | `/screens` | `?recipe=politics` | 1 | |
| `state.screens.politics-partial` | state | `role="alert"` | "Collected from some sources only" + failures list | `status: "partial"` | merged | `/screens` | `?recipe=politics` | 1 | |
| `state.screens.politics-empty-note` | state | 3-way empty note | feed-unavailable / no-disclosures-in-window / not-yet-collected | — | merged | `/screens` | `?recipe=politics` | 1 | |

### 9h. Institutional (`?recipe=institutional`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `action.screens.institutional-rerun` | control | button | "Re-run collection" | `useScreenRefresh('institutional')` | merged | `/screens` | `?recipe=institutional` | 1 | |
| `control.screens.institutional-filters` | control | `ResponsiveControlPanel` | Flag (4), Sort by | `screens/institutional-13f.json` | merged | `/screens` | `?recipe=institutional` | 1 | |
| `figure.screens.institutional-kpis` | figure | 4 KPIs | managers reviewed/configured, tickers flagged, CUSIPs mapped/awaiting, amendments seen | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `column.screens.institutional-table` | column | table | ticker, CUSIP, managers added/dropped, share change %, flag, filed date | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `disclosure.screens.institutional-curated-list` | disclosure | note | "a curated list of publicly traded, actively managed institutional filers — not the full 13F universe…" | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `disclosure.screens.institutional-flag-not-prediction` | disclosure | note | "A flag reports how many curated managers added or cut a position; it is not a prediction" | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `disclosure.screens.institutional-cusip-note` | disclosure | note | unmapped holdings absent from table | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `state.screens.institutional-unavailable` | state | `role="alert"` | "Institutional screen unavailable" | — | merged | `/screens` | `?recipe=institutional` | 1 | |
| `state.screens.institutional-collection-incomplete` | state | `role="alert"` | "Collection did not run/complete" + `degraded_reason` | `status !== 'success'` | merged | `/screens` | `?recipe=institutional` | 1 | |
| `state.screens.institutional-empty-success` | state | note | "the last collection run did not complete, so this is not a statement that no manager moved a position" | `results: [], status: 'success'` | merged | `/screens` | `?recipe=institutional` | 1 | success-with-empty-results nuance |

### 9i. Inside Information (`?recipe=inside-information`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `action.screens.insideinfo-rerun` | control | button | "Re-run merge" | `useScreenRefresh('inside-information')` | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `control.screens.insideinfo-sort` | control | select | Combined score / Institutional points / Congressional points | `screens/inside-information.json` | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `figure.screens.insideinfo-kpis` | figure | 2 KPIs | tickers with disclosed activity, notable shown | — | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `column.screens.insideinfo-table` | column | table | ticker, combined score, institutional flag, congressional flags, members buying, managers added | — | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `disclosure.screens.insideinfo-flagged-only` | disclosure | note | "shown only where the underlying screen already flagged the activity as rare or notable… Not a claim that any of this was informed or improper" | — | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `state.screens.insideinfo-unavailable` | state | `role="alert"` | "Merge did not run/complete" | — | merged | `/screens` | `?recipe=inside-information` | 1 | |
| `state.screens.insideinfo-no-activity` | state | empty | "No notable activity right now — most disclosed trading is routine…" | — | merged | `/screens` | `?recipe=inside-information` | 1 | |

## 10 · Evidence (`/evidence?section=<s>`) — absorbs Backtests, Shadow, Validation, Methodology, Glossary

### 10a. Backtests (`?section=backtests`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.evidence.backtests-coverage-expander` | control | expander | "Show/Hide what each backtest cannot measure (N methods)" | `screens/backtest-comparison.json` | merged | `/evidence` | `?section=backtests` | 1 | |
| `figure.evidence.backtests-coverage-cards` | figure | 4 cards | methods measured, comparable groups, features tracked, generated | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `chart.evidence.backtests-dotplots` | chart | `DotPlot` ×4 groups | Held portfolios / ongoing contributions / options / ranking quality | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `column.evidence.backtests-method-tables` | column | `MethodTable` ×4 groups | per-group method rows | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `figure.evidence.backtests-success-rollup` | figure | table | "Success rate by feature" rollup | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `disclosure.evidence.backtests-basis-column` | disclosure | column | success-rate basis ("periods positive"/"trades profitable"/"periods ranked correctly"/"not measurable") | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `disclosure.evidence.backtests-within-group-only` | disclosure | note | "success rates rank only within a group" | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `disclosure.evidence.backtests-cooccurrence-note` | disclosure | note | "This is co-occurrence across methods, not attribution" | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `disclosure.evidence.backtests-status-chips` | disclosure | chips | "Not yet run" / "Insufficient history" | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `disclosure.evidence.backtests-footer` | disclosure | footer | "Every figure here is retrospective and simulated… Prospective, forward-only results are on the shadow portfolios screen, and those govern promotion." | — | merged | `/evidence` | `?section=backtests` | 1 | protected disclosure |
| `state.evidence.backtests-unavailable` | state | `role="alert"` | "Backtest comparison unavailable" | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `state.evidence.backtests-nothing-to-rollup` | state | note | "No method has published a success rate yet, so there is nothing to roll up." | — | merged | `/evidence` | `?section=backtests` | 1 | |
| `state.evidence.backtests-held-cash-n-periods` | state | note | "Held cash in N of M periods" in place of a rate | — | merged | `/evidence` | `?section=backtests` | 1 | |

### 10b. Shadow (`?section=shadow`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `figure.evidence.shadow-overview` | figure | `AutoOverviewLine` | ranking overview | `screens/shadow-portfolios.json` | merged | `/evidence` | `?section=shadow` | 1 | |
| `figure.evidence.shadow-my-portfolio-overlay` | figure | `MyPortfolioVsShadow` | your return over aligned window + hypothetical rank | `report.json` | merged | `/evidence` | `?section=shadow` | 1 | informational-only, never affects promotion |
| `figure.evidence.shadow-summary-cards` | figure | 4 cards | reporting now, immutable snapshots, comparable window, implementation cost bps | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `chart.evidence.shadow-scatter` | chart | `ScatterChart` | max drawdown vs aligned net return | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `column.evidence.shadow-strategies-table` | column | table | aligned/own-window return, CAGR, Sharpe, Sortino, max DD, turnover, coverage change, observations/snapshots, evidence status | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `disclosure.evidence.shadow-promotion-gate` | disclosure | note | "Immutable, net-of-cost observations. No strategy is promoted from implementation alone." | — | merged | `/evidence` | `?section=shadow` | 1 | protected disclosure |
| `disclosure.evidence.shadow-aligned-window-explanation` | disclosure | note | aligned-window explanation | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `disclosure.evidence.shadow-informational-only` | disclosure | note | "Informational only: never writes into the shadow strategy registry, plays no part in promotion" | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `disclosure.evidence.shadow-annualization-gate` | disclosure | footer | "Annualized statistics remain gated until {n} matched returns exist; promotion remains gated until 36 monthly observations." | — | merged | `/evidence` | `?section=shadow` | 1 | protected disclosure |
| `state.evidence.shadow-unavailable` | state | `role="alert"` | "Shadow results unavailable" | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `state.evidence.shadow-per-cell-status` | state | per-cell | "Not started" / "First return pending" / "{n}/{min} returns" / "Outside shared window" | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `state.evidence.shadow-no-comparable-ranking` | state | note | "No comparable ranking yet…" | — | merged | `/evidence` | `?section=shadow` | 1 | |
| `state.evidence.shadow-mine-4-branches` | state | 4 branches | not signed in / no positions / not enough history / result | — | merged | `/evidence` | `?section=shadow` | 1 | |

### 10c. Validation (`?section=validation`) — hosts the 64-metric report

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `detail.evidence.validation-applicability-lineage` | detail | `<details>` per ticker | "Applicability and lineage" | `validation/live_v2_validation.json` | merged | `/evidence` | `?section=validation` | 1 | |
| `figure.evidence.validation-rank-ic-overview` | figure | `AutoOverviewLine` | rank-IC overview | `validation/ic_validation.json` | merged | `/evidence` | `?section=validation` | 1 | |
| `chart.evidence.validation-signal-metrics-panel` | chart | `SignalMetricsPanel` | the 64-metric report | `validation/signal_metrics.json` | merged | `/evidence` | `?section=validation` | 1 | ALSO embedded at `/portfolio?view=data&analytics=algorithm` — see §Metrics for individual metric rows |
| `figure.evidence.validation-research-evidence` | figure | `ResearchEvidence` | promotion-state summary | `validation/research_evidence.json` | merged | `/evidence` | `?section=validation` | 1 | |
| `chart.evidence.validation-champion-challenger` | chart | `PairedBarChart` | mean rank IC by horizon (1M/3M/6M/12M) | `validation/ic_validation.json` | merged | `/evidence` | `?section=validation` | 1 | |
| `figure.evidence.validation-variant-cards` | figure | cards | periods accumulated, mean IC, 95% CI, ICIR, quintile bucket chart | — | merged | `/evidence` | `?section=validation` | 1 | |
| `figure.evidence.validation-per-ticker-cards` | figure | cards | structural/timeliness/company evidence/position rule layers, peer sample, percentile status, profile confidence, failed invariants | `validation/live_v2_validation.json` | merged | `/evidence` | `?section=validation` | 1 | |
| `disclosure.evidence.validation-never-replaces-production` | disclosure | note | "This view never replaces production output." | — | merged | `/evidence` | `?section=validation` | 1 | |
| `disclosure.evidence.validation-icir-hidden` | disclosure | note | "ICIR stays hidden until 24 monthly periods exist." | — | merged | `/evidence` | `?section=validation` | 1 | |
| `disclosure.evidence.validation-lookahead-exclusion` | disclosure | note | "Historical reconstruction is excluded because current-as-reported fundamentals would introduce look-ahead contamination." | — | merged | `/evidence` | `?section=validation` | 1 | |
| `disclosure.evidence.validation-live-only-span` | disclosure | note | "Live-only evidence spans N days." | — | merged | `/evidence` | `?section=validation` | 1 | numbers move daily — always read live, never hardcode |
| `disclosure.evidence.validation-no-signal-promoted` | disclosure | (currently docs-only; NEW UI surface) | classification B, "no signal has been promoted", 0 of 24 IC periods | `validation/research_evidence.json.headline` | kept | `/evidence` | `?section=validation` | 1 | **currently exists only in docs — closes a gap, still `kept` since the underlying data capability exists today, just unsurfaced; see NOTES.md** |
| `state.evidence.validation-ic-unavailable` | state | note | "IC validation unavailable — Run the prospective validation harness" | — | merged | `/evidence` | `?section=validation` | 1 | |
| `state.evidence.validation-artifact-unavailable` | state | note | "Validation artifact unavailable — Run pipeline/live_v2_validation.py" | — | merged | `/evidence` | `?section=validation` | 1 | |
| `state.evidence.validation-quintile-pending` | state | note | "Quintile returns appear after the first complete forward period." | — | merged | `/evidence` | `?section=validation` | 1 | |
| `state.evidence.validation-flags` | state | flags | "Accumulating" / "Not monotonic" | — | merged | `/evidence` | `?section=validation` | 1 | |

### 10d. Methodology (`?section=methodology`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `export.evidence.methodology-download-docs` | export | button | "Download full docs (.md)" — `APP-COMPLETE-BREAKDOWN.md` + `MASTER-METHODOLOGY.md` | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-weight-stack` | figure | stack | overall score weight stack | `advisor.json methodology` | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-category-cards` | figure | cards | per-category weight cards | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-modifiers-list` | figure | list | modifiers with published ranges | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-version-card` | figure | card | semantic version, git commit, config hash, generated timestamp | `model_metadata` | merged | `/evidence` | `?section=methodology` | 1 | protected disclosure — model version/config hash/as-of |
| `figure.evidence.methodology-active-vs-shadow` | figure | explanation | active-guidance-vs-shadow-policy | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-benchmark-rationale` | figure | text | benchmark comparison rationale | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `figure.evidence.methodology-capability-grid` | figure | grid | provider/parser capabilities (available/available_next_refresh/opt_in/provider_required/shadow_only) | `capability_status` | merged | `/evidence` | `?section=methodology` | 1 | |
| `disclosure.evidence.methodology-blend-from-snapshot` | disclosure | note | "Read the blend from the snapshot so this page cannot drift from the config that produced the scores" | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `disclosure.evidence.methodology-shadow-not-controlling` | disclosure | note | "Shadow results do not control production actions." | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `disclosure.evidence.methodology-pre-window-unavailable` | disclosure | note | "Positions bought before the published benchmark window are shown as unavailable" | — | merged | `/evidence` | `?section=methodology` | 1 | |
| `disclosure.evidence.methodology-general-research-fallback` | disclosure | fallback | "General research only. Not individualized investment advice." | `data.disclaimer` | merged | `/evidence` | `?section=methodology` | 1 | |
| `state.evidence.methodology-pending-refresh` | state | note | "The scoring blend will appear after the first published research refresh." / "Pending refresh" | — | merged | `/evidence` | `?section=methodology` | 1 | |

### 10e. Glossary (`?section=glossary`)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.evidence.glossary-search` | control | search input | filters terms and definitions | — | merged | `/evidence` | `?section=glossary` | 1 | |
| `figure.evidence.glossary-count` | figure | text | "N of M terms" | — | merged | `/evidence` | `?section=glossary` | 1 | |
| `figure.evidence.glossary-groups` | figure | `<dl>` groups | static term/definition pairs + optional per-group notes | — | merged | `/evidence` | `?section=glossary` | 1 | |
| `figure.evidence.glossary-research-score-def` | figure | definition | "Research score" rewritten from live weights | `advisor.json` | merged | `/evidence` | `?section=glossary` | 1 | only live-data-dependent entry |
| `state.evidence.glossary-no-match` | state | empty | "No terms matched '{query}'." | — | merged | `/evidence` | `?section=glossary` | 1 | |
| `disclosure.evidence.glossary-footer` | disclosure | footer | disclaimer footer | — | merged | `/evidence` | `?section=glossary` | 1 | |

## 11 · Alerts (`/alerts`) — demoted, 1 tap from AlertBadge

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `alert.rule.price-cross` | alert | rule type | ticker, direction, threshold → "{T} price {dir} ${x}" | `alertRules.js` | demoted | `/alerts` | tap AlertBadge in persistent chrome | 1 | |
| `alert.rule.percent-move` | alert | rule type | ticker, direction, threshold %, periodDays (1/5) → "{T} {n}-day move {dir} {x}%" | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `alert.rule.stop-trigger` | alert | rule type | ticker, stopKind (trim/exit), threshold → "{T} {kind} stop at ${x}" | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `alert.rule.score-band` | alert | rule type | ticker, direction, band ∈ ATTRACTIVE/NEUTRAL/CAUTIOUS/UNATTRACTIVE | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `alert.rule.guidance-change` | alert | rule type | ticker, guidanceActions ⊂ {TRIM, SELL} | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `alert.rule.earnings-upcoming` | alert | rule type | ticker, daysAhead 1–90 | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `alert.rule.pipeline-stale` | alert | rule type | no ticker, staleHours 1–168 | — | demoted | `/alerts` | tap AlertBadge | 1 | only rule with no ticker |
| `control.alerts.type-select` | control | select | 7 alert types, type-conditional `RuleFields` | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `action.alerts.create-rule` | control | button | "Create alert" | `useAlerts.createRule` | demoted | `/alerts` | tap AlertBadge | 1 | returns `{success,id,firstRule}` |
| `control.alerts.rule-toggle` | control | per-rule toggle | enable/disable, `aria-pressed` | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `action.alerts.delete-rule` | control | per-rule button | delete | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `action.alerts.mark-all-read` | control | button | "Mark all read" | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `control.alerts.push-offer` | control | offer (after first rule) | "Enable push" / "Not now" | `pushNotifications.js` | demoted | `/alerts` | tap AlertBadge | 1 | |
| `control.alerts.quiet-hours` | control | switch + 2 time inputs | quiet-hours enabled, start, end | Firestore `alerts/{uid}/settings` | demoted | `/alerts` | tap AlertBadge | 1 | |
| `figure.alerts.rules-used-counter` | figure | text | "N of {max} rules used" | `alertConfig.maximum_rules_per_user` | demoted | `/alerts` | tap AlertBadge | 1 | |
| `figure.alerts.event-inbox` | figure | list | event inbox, newest-first | Firestore `alerts/{uid}/events` | demoted | `/alerts` | tap AlertBadge | 1 | |
| `link.alerts.event-destination-routing` | link | per-event link | `pipeline_stale`→`/`, else `?q={ticker}` on Research | — | demoted | `/alerts` | tap AlertBadge | 1 | marks read on click; destination updated for the merged Research route |
| `disclosure.alerts.push-optional` | disclosure | note | "Push notifications are optional." | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `disclosure.alerts.evaluated-after-refresh` | disclosure | note | "Alert created. It will be evaluated after each research refresh." | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `disclosure.alerts.guidance-fire-condition` | disclosure | note | "Fires when published guidance changes to Trim or Sell." | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `disclosure.alerts.quiet-hours-push-suppressed` | disclosure | note | "In-app events still arrive. Device push is suppressed during this window." | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `disclosure.alerts.active-paused-status` | disclosure | status | "Active after each refresh" / "Paused" | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.cloud-offline` | state | empty | cloud-offline empty state | `useAuth` | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.loading` | state | `<Loading/>` | — | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.error` | state | `role="alert"` | error banner | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.status-live-region` | state | `role="status"` + `sr-only aria-live` mirror | status messages | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.no-events` | state | empty | "No alert events yet — Events appear here after a refresh crosses one of your saved rules." | — | demoted | `/alerts` | tap AlertBadge | 1 | |
| `state.alerts.no-rules` | state | empty | "No saved rules." | — | demoted | `/alerts` | tap AlertBadge | 1 | |

## 12 · Settings (`/settings`) — demoted, nav utility slot in every medium

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `control.settings.theme-choice` | control | buttons + previews | system/light/dark | preference `theme` | demoted | `/settings` | nav utility slot | 1 | becomes the 12-medium picker in rebuild (live miniature previews) |
| `control.settings.accent-swatches` | control | 8 swatches | accent color | preference `accentColor` | demoted | `/settings` | nav utility slot | 1 | Classic-only in rebuild (`acceptsAccent`) |
| `control.settings.surface-style` | control | select | Surface style | preference `surfaceStyle` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.corner-style` | control | select | Corner style | preference `cornerStyle` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.density` | control | select | Interface density | preference `density` | demoted | `/settings` | nav utility slot | 1 | |
| `figure.settings.widget-count` | figure | text | visible-widget count | preference `widgets` | demoted | `/settings` | nav utility slot | 1 | |
| `link.settings.customize-report` | link | link | "Customize report" → `/?customize=1` | — | demoted | `/settings` | nav utility slot | 1 | |
| `action.settings.reset-report` | control | button | "Reset report" | — | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.default-benchmarks` | control | checkbox grid (max 3) | default benchmarks, first = primary | preference `defaultBenchmarks` | demoted | `/settings` | nav utility slot | 1 | disabled at limit |
| `control.settings.holdings-order` | control | select | default holdings order | preference `holdingSort` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.suggested-actions-default` | control | select | suggested-actions default | preference `suggestedActionsDefault` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.chart-defaults` | control | selects ×5 | default period, chart style, line weight, grid, animation | preference `chart*` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.planning-inputs` | control | inputs | annual contribution, birthdate, retirement age select, mobile research view, watchlist sizing method | preference `forecast*` | demoted | `/settings` | nav utility slot | 1 | computed current age read-only |
| `control.settings.number-format` | control | select | number format | preference `numberFormat` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.privacy-mode` | control | switch | "Hide balances" | preference `privacyMode` | demoted | `/settings` | nav utility slot | 1 | duplicated in mobile header + Home |
| `control.settings.reduced-motion` | control | select | reduced motion | preference `reducedMotion` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.higher-contrast` | control | switch | higher-contrast | preference `higherContrast` | demoted | `/settings` | nav utility slot | 1 | |
| `control.settings.larger-chart-labels` | control | switch | larger chart labels | preference `largerChartLabels` | demoted | `/settings` | nav utility slot | 1 | |
| `action.settings.reset-appearance` | control | button | "Reset appearance" | — | demoted | `/settings` | nav utility slot | 1 | |
| `action.settings.reset-all` | control | button, `window.confirm` | "Reset all settings" | — | demoted | `/settings` | nav utility slot | 1 | |
| `disclosure.settings.local-device-only` | disclosure | note | "Appearance and data presentation stay on this device." | — | demoted | `/settings` | nav utility slot | 1 | |
| `disclosure.settings.touch-target-floor` | disclosure | note | "Touch targets always remain at least 44px." | — | demoted | `/settings` | nav utility slot | 1 | |
| `disclosure.settings.formatting-never-alters-source` | disclosure | note | "Formatting preferences never alter source values." | — | demoted | `/settings` | nav utility slot | 1 | |
| `disclosure.settings.bootstrap-paths-note` | disclosure | note | "5,000 paths use a 12-month historical block bootstrap. Simulated outcomes are not predictions." | — | demoted | `/settings` | nav utility slot | 1 | |
| `disclosure.settings.age-auto-calculated` | disclosure | note | "Your age is calculated automatically and used only for retirement planning." | — | demoted | `/settings` | nav utility slot | 1 | |
| `a11y.settings.change-announcements` | a11y | `sr-only aria-live="polite"` | every setting change announced | — | demoted | `/settings` | nav utility slot | 1 | benchmark guard: "Keep at least one comparison benchmark selected." |

## 13 · `/hud-demo` and `CommandCenter.jsx` — non-route orphans

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `n/a.hud-demo` | n/a | `HUDDemo.jsx`, DEV-only route | HUD widget gallery, `setInterval(Math.random())` | none — randomized | n/a | — | — | — | **leave exactly as-is, unlinked, DEV-only** per master instruction; see NOTES.md |
| `n/a.command-center` | n/a | `CommandCenter.jsx`, unrouted | fork of Dashboard rendered via `hudUltra.jsx`, dead controls (frozen `useState`, no setters) | real data, no live consumers | n/a | — | — | — | fully orphaned, no route/import anywhere; see NOTES.md |

---

## 14 · Stock Detail Sheet (opened from 7 routes: Research, Search/Research, Portfolio Summary + suggested actions, FastGrowth, Options/Strategy, ThemeExposure/Screens)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `detail.stock.dialog-shell` | detail | `role="dialog" aria-modal aria-labelledby`, `useDialog` | focus trap, initial focus, Esc close, focus restore | `useBodyScrollLock` | kept | (opened from) | — | 0 | opens from report.json, upgrades from advisor.json on arrival |
| `export.stock.copy-data` | export | icon button | `CopyDataButton` → `buildStockCopyText()` to clipboard | `stockCopyText.js` | kept | (opened from) | — | 0 | can never emit a number the panel withheld (shares `resolvedMetricSections`) |
| `control.stock.watchlist-star` | control | icon button | watchlist toggle | `useWatchlist` | kept | (opened from) | — | 0 | |
| `action.stock.close` | control | icon button | close | — | kept | (opened from) | — | 0 | |
| `disclosure.stock.as-of-line` | disclosure | header | "As of {date}" | — | kept | (opened from) | — | 0 | |
| `figure.stock.research-score-dial` | figure | `CoverageScoreDial` | lead concept 1 — arc dash/gap/opacity modulate with data coverage | — | kept | (opened from) | — | 0 | unmeasured coverage = unmodulated arc, never zero styling |
| `figure.stock.data-coverage` | figure | lead concept 2 | % or "Not measured — This is not a reading of zero." | — | kept | (opened from) | — | 0 | protected — zero vs unavailable distinction |
| `figure.stock.guidance` | figure | lead concept 3 | recommendation action + summary | — | kept | (opened from) | — | 0 | |
| `figure.stock.theme-exposure` | figure | lead concept 4 | primary theme + score/100 + other themes | — | kept | (opened from) | — | 0 | "stays independent from the research score" |
| `control.stock.evidence-expander` | control | `aria-expanded` toggle | "Explore the evidence" / "Hide full research detail" | — | kept | (opened from) | — | 0 | gates the whole detail block |
| `figure.stock.action-guidance` | figure | `ActionGuidance` | — | — | kept | (opened from) | — | 0 | |
| `figure.stock.setup-quality-breakdown` | figure | `SetupQualityBreakdown` | — | — | kept | (opened from) | — | 0 | |
| `chart.stock.factor-bars` | chart | `FactorBars` (`ScoreExplainability.jsx`) | one bar per `explainability.factor_bars` entry | — | kept | (opened from) | — | 0 | **data-driven count, not fixed six**; represents the 53-feature registry in aggregate — see NOTES.md |
| `figure.stock.kpi-grid` | figure | 4-up grid | price, market cap, 20-day move, 1-year move (+ earnings-vs-estimate) | — | kept | (opened from) | — | 0 | |
| `figure.stock.dip-watch-badge` | figure | `DipWatchBadge` | — | — | kept | (opened from) | — | 0 | |
| `figure.stock.bull-bear-thesis-track` | figure | track | 0 bearish · 5 neutral · 10 bullish, weighting breakdown | — | kept | (opened from) | — | 0 | "40% fundamentals · 30% price · 20% news · 10% risk. N% of inputs were available." |
| `figure.stock.recommendation-shadow-panel` | figure | `RecommendationShadowPanel` + `AnalysisLayers` | Business thesis / Earnings timeliness layers | — | kept | (opened from) | — | 0 | "Insufficient evidence" warning below 40% |
| `figure.stock.peer-valuation` | figure | line | tier phrase + valid-peer count, or "No peer comparison published" | — | kept | (opened from) | — | 0 | |
| `nav.stock.tabs` | nav | 3 tabs | Evidence / All metrics / Vs S&P 500 | — | kept | (opened from) | — | 0 | |
| `figure.stock.evidence-tab-collapsed-note` | figure | note | collapsed when `showMore` off | — | kept | (opened from) | — | 0 | |
| `chart.stock.score-explainability` | chart | `ScoreExplainability` | champion/challenger switch, `ResearchRadarChart`, score-component bars | — | kept | (opened from) | — | 0 | radar retired to `profile` contract type in rebuild |
| `figure.stock.fundamental-categories` | figure | bars | fundamental categories + "{used}/{applicable} metrics" | — | kept | (opened from) | — | 0 | |
| `figure.stock.evidence-risks-lists` | figure | lists | Evidence-for / Risks-gaps | — | kept | (opened from) | — | 0 | |
| `figure.stock.insider-activity` | figure | `InsiderActivityView` | buy-vs-sell bar + counts | — | kept | (opened from) | — | 0 | "raw counts, not the scored signal" |
| `figure.stock.inside-information-view` | figure | `InsideInformationView` | institutional flag + congress flags + combined score + link | `screens/inside-information.json` | kept | (opened from) | — | 0 | links to `/screens?recipe=inside-information` |
| `figure.stock.score-modifiers` | figure | list | applied modifiers | — | kept | (opened from) | — | 0 | "never outweigh the fundamentals behind it" |
| `chart.stock.metric-sections` | chart | `MetricSections` (8 groups) | Valuation, Profitability & cash, Financial health, Accounting quality, Capital allocation, Growth, Ownership & positioning, Behaviour & tradability | — | kept | (opened from) | — | 0 | unresolved metrics omitted, never dashed |
| `figure.stock.etf-comparison-panel` | figure | `ETFComparisonPanel` + legacy `<details>` | ETF vs benchmark | `etf/{ticker}.json` | kept | (opened from) | — | 0 | ETF branch of tab 3 |
| `chart.stock.growth-vs-spy` | chart | zoomable `GrowthChart` | "Growth of $500: {ticker} vs S&P 500" | — | kept | (opened from) | — | 0 | stock branch of tab 3; scoped to purchase date when position passed |
| `figure.stock.hypothetical-kpi-grid` | figure | 4-KPI grid | $ in ticker, $ in S&P, dollars ahead, excess return | — | kept | (opened from) | — | 0 | |
| `figure.stock.risk-kpi-grid` | figure | 4-KPI grid | max drawdown 1y, volatility, vs SPY 20d, beta, Accel vs market (σ) | — | kept | (opened from) | — | 0 | "Needs two quarters of history against the index" fallback |
| `chart.stock.score-waterfall` | chart | `Waterfall` | start-from-neutral baseline, per-evidence-line + modifier rows incl. confidence shrinkage | — | kept | (opened from) | — | 0 | waterfall contract type |
| `disclosure.stock.waterfall-divergence` | disclosure | note | reconciles the variant, not the published score, when they differ ≥0.05 | — | kept | (opened from) | — | 0 | |
| `figure.stock.metric-level-evidence` | figure | list | peer percentile + direction meaning | — | kept | (opened from) | — | 0 | "peer percentile is accumulating" state |
| `chart.stock.score-history` | chart | SVG | stance-change dots, "Score moved from A to B, driven mainly by {category}" | — | kept | (opened from) | — | 0 | accumulating: "{stored} of {required} stored months" |
| `figure.stock.anomalies` | figure | section | "Divergence flags → Patterns worth reviewing" | — | kept | (opened from) | — | 0 | severity-classed |
| `disclosure.stock.footer-disclaimer` | disclosure | footer | "Algorithmic research from quantitative metrics, not financial advice. Verify the filings and your own suitability before acting." | — | kept | (opened from) | — | 0 | protected disclosure |

## 15 · Metrics (generated section — see `docs/METRIC_INVENTORY.md` §Preservation baseline: 130 IDs, + 24 live metrics newer than the doc)

The rows below are generated mechanically from `docs/METRIC_INVENTORY.md` (three tables, 130
canonical IDs) plus `public/data/validation/signal_metrics.json` (64 live IDs, of which 24 are
not yet documented in METRIC_INVENTORY.md — see `NOTES.md`). Destination is derived from the
render-site file using the mapping table below; every row's `disposition` is `kept` because a
metric's underlying capability is unchanged by consolidation — only its container route moves.

**Render-site → destination mapping** (used to classify every row below):
`PortfolioReturnSummary.jsx`, `Portfolio.jsx` (summary block) → `/portfolio?view=summary` ·
`portfolio/Performance.jsx` → `/portfolio?view=performance` ·
`PerformanceMetrics.jsx` → `/portfolio?view=data` ·
`Diversification.jsx` → `/portfolio?view=diversification` ·
`BacktestSummary.jsx`, `BacktestComparison.jsx` → `/evidence?section=backtests` ·
`ShadowPortfolios.jsx` → `/evidence?section=shadow` ·
`LiveValidation.jsx`, `SignalMetricsPanel.jsx` → `/evidence?section=validation`.

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `metric.report.strategy-return-twr` | metric | `PortfolioReturnSummary.jsx:9-13`; `Portfolio.jsx:578-583` | Strategy return (time-weighted) | `portfolioAnalytics.js:225-301` | kept | /portfolio | `view=summary` | 1 | group: Return & Compounding |
| `metric.report.money-weighted-xirr` | metric | `PortfolioReturnSummary.jsx:14-18` | Your return (money-weighted) | `portfolioAnalytics.js:303-403` | kept | /portfolio | `view=summary` | 1 | group: Return & Compounding |
| `metric.report.portfolio-score` | metric | `Portfolio.jsx:585-590` | Portfolio Score | `portfolioAnalytics.js:986-995` | kept | /portfolio | `view=summary` | 1 | group: Exposure & Construction |
| `metric.report.versus-sp500-return` | metric | `Portfolio.jsx:591-603` | Vs S&P 500 | `portfolioPerformance.js:108-153` | kept | /portfolio | `view=summary` | 1 | group: Relative Performance |
| `metric.report.annualized-return` | metric | calculated but not rendered in Standard Measures | Annualized return | `portfolioAnalytics.js:900-902,931` | kept | /portfolio | `view=data` | 1 | group: Return & Compounding |
| `metric.report.sharpe-naive` | metric | `PerformanceMetrics.jsx:40,89,92` | Sharpe ratio | `portfolioAnalytics.js:927-945` | kept | /portfolio | `view=data` | 1 | group: Risk-Adjusted Return |
| `metric.report.sortino-naive` | metric | `PerformanceMetrics.jsx:93` | Sortino ratio | `portfolioAnalytics.js:927-945` | kept | /portfolio | `view=data` | 1 | group: Risk-Adjusted Return |
| `metric.report.calmar` | metric | `PerformanceMetrics.jsx:94` | Calmar ratio | `portfolioAnalytics.js:931-946` | kept | /portfolio | `view=data` | 1 | group: Risk-Adjusted Return |
| `metric.report.maximum-drawdown` | metric | `PerformanceMetrics.jsx:40,95`; `BacktestSummary.jsx:18`; `BacktestComparison.jsx:65,80,159`; `ShadowPortfolios.jsx:55,61-62` | Maximum drawdown | `portfolioAnalytics.js:816,932` | kept | /portfolio | `view=data` | 1 | group: Drawdown |
| `metric.report.current-drawdown` | metric | `PerformanceMetrics.jsx:96` | Current drawdown | `portfolioAnalytics.js:933-934` | kept | /portfolio | `view=data` | 1 | group: Drawdown |
| `metric.report.longest-underwater` | metric | `PerformanceMetrics.jsx:99-110` | Longest underwater | `portfolioAnalytics.js:829-882` | kept | /portfolio | `view=data` | 1 | group: Drawdown |
| `metric.report.current-underwater` | metric | calculated but not independently rendered | Current underwater duration | `portfolioAnalytics.js:868-880` | kept | /portfolio | `view=data` | 1 | group: Drawdown |
| `metric.report.deepest-drawdown` | metric | calculated; maximum drawdown is its duplicate measurement | Deepest drawdown | `portfolioAnalytics.js:859-878` | kept | /portfolio | `view=data` | 1 | duplicate render of `maximum_drawdown`; group: Drawdown |
| `metric.report.recovery-deepest` | metric | calculated but not rendered | Recovery time for deepest drawdown | `portfolioAnalytics.js:841-877` | kept | /portfolio | `view=data` | 1 | group: Drawdown |
| `metric.report.information-ratio-spy` | metric | `PerformanceMetrics.jsx:122-125` | Information ratio | `portfolioAnalytics.js:935-954` | kept | /portfolio | `view=data` | 1 | group: Relative Performance |
| `metric.report.acceleration` | metric | `PerformanceMetrics.jsx:126-134` | Acceleration | `portfolioAcceleration.js:70-153` | kept | /portfolio | `view=data` | 1 | group: Relative Performance |
| `metric.report.acceleration-pct` | metric | supporting text in `PerformanceMetrics.jsx:132` | Acceleration percentage-point change | `portfolioAcceleration.js:129-150` | kept | /portfolio | `view=data` | 1 | duplicate render of `acceleration`; group: Relative Performance |
| `metric.report.acceleration-beta` | metric | methodology/supporting text | Acceleration fitted beta | `portfolioAcceleration.js:100-151` | kept | /portfolio | `view=data` | 1 | group: Benchmark Fit |
| `metric.report.up-capture-spy` | metric | `PerformanceMetrics.jsx:137` | Up capture | `portfolioBenchmarkComparison.js:23-74` | kept | /portfolio | `view=data` | 1 | group: Capture Profile |
| `metric.report.down-capture-spy` | metric | `PerformanceMetrics.jsx:138` | Down capture | `portfolioBenchmarkComparison.js:23-74` | kept | /portfolio | `view=data` | 1 | group: Capture Profile |
| `metric.report.capture-spread-spy` | metric | `PerformanceMetrics.jsx:139-149` | Capture spread | `portfolioBenchmarkComparison.js:23-74` | kept | /portfolio | `view=data` | 1 | group: Capture Profile |
| `metric.report.batting-average-spy` | metric | `PerformanceMetrics.jsx:115,150-158` | Batting average | `portfolioBenchmarkComparison.js:81-121` | kept | /portfolio | `view=data` | 1 | group: Consistency |
| `metric.report.batting-wins-losses` | metric | supporting text in `PerformanceMetrics.jsx:155-157` | Winning / losing months | `portfolioBenchmarkComparison.js:96-119` | kept | /portfolio | `view=data` | 1 | duplicate render of `batting_average_spy`; group: Consistency |
| `metric.report.relative-payoff` | metric | supporting text in `PerformanceMetrics.jsx:156` | Win/loss size ratio | `portfolioBenchmarkComparison.js:101-116` | kept | /portfolio | `view=data` | 1 | group: Consistency |
| `metric.report.average-relative-win` | metric | calculated but not rendered | Average winning-month excess | `portfolioBenchmarkComparison.js:101-115` | kept | /portfolio | `view=data` | 1 | group: Consistency |
| `metric.report.average-relative-loss` | metric | calculated but not rendered | Average losing-month excess | `portfolioBenchmarkComparison.js:101-115` | kept | /portfolio | `view=data` | 1 | group: Consistency |
| `metric.report.week-excess` | metric | `PerformanceMetrics.jsx:172-181` | Past week vs index | `portfolioShortTermView.js:65-116` | kept | /portfolio | `view=data` | 1 | group: Recent Performance |
| `metric.report.month-excess` | metric | `PerformanceMetrics.jsx:182-191` | Past month vs index | `portfolioShortTermView.js:65-116` | kept | /portfolio | `view=data` | 1 | group: Recent Performance |
| `metric.report.week-portfolio-return` | metric | supporting text in `PerformanceMetrics.jsx:179` | Week portfolio return | `portfolioShortTermView.js:100-108` | kept | /portfolio | `view=data` | 1 | duplicate render of `week_excess`; group: Recent Performance |
| `metric.report.week-benchmark-return` | metric | supporting text in `PerformanceMetrics.jsx:179` | Week index return | `portfolioShortTermView.js:100-108` | kept | /portfolio | `view=data` | 1 | duplicate render of `week_excess`; group: Recent Performance |
| `metric.report.month-portfolio-return` | metric | supporting text in `PerformanceMetrics.jsx:189` | Month portfolio return | `portfolioShortTermView.js:100-108` | kept | /portfolio | `view=data` | 1 | duplicate render of `month_excess`; group: Recent Performance |
| `metric.report.month-benchmark-return` | metric | supporting text in `PerformanceMetrics.jsx:189` | Month index return | `portfolioShortTermView.js:100-108` | kept | /portfolio | `view=data` | 1 | duplicate render of `month_excess`; group: Recent Performance |
| `metric.report.noise-floor-week` | metric | calculated, used for week tone, not rendered | Week noise floor | `portfolioShortTermView.js:52-63,97-112` | kept | /portfolio | `view=data` | 1 | group: Signal Strength |
| `metric.report.noise-floor-month` | metric | `PerformanceMetrics.jsx:193-199` | Noise floor (month) | `portfolioShortTermView.js:52-63,97-112` | kept | /portfolio | `view=data` | 1 | group: Signal Strength |
| `metric.report.excess-streak` | metric | `PerformanceMetrics.jsx:200-208` | Current streak | `portfolioShortTermView.js:118-130` | kept | /portfolio | `view=data` | 1 | group: Portfolio Behavior |
| `metric.report.recent-tracking-risk` | metric | `PerformanceMetrics.jsx:209-217` | Recent tracking risk | `portfolioShortTermView.js:132-143` | kept | /portfolio | `view=data` | 1 | group: Risk Change |
| `metric.report.baseline-tracking-risk` | metric | supporting text in `PerformanceMetrics.jsx:214-216` | Baseline tracking risk | `portfolioShortTermView.js:73-84,134-147` | kept | /portfolio | `view=data` | 1 | duplicate render of `recent_tracking_risk`; group: Risk Change |
| `metric.report.short-term-beta` | metric | methodology header in `PerformanceMetrics.jsx:169` | Fast-read fitted beta | `portfolioShortTermView.js:37-49,73-83` | kept | /portfolio | `view=data` | 1 | group: Benchmark Fit |
| `metric.report.diversification-score` | metric | `Diversification.jsx:48-57` | Diversification score | `portfolioAnalytics.js:755-813` | kept | /portfolio | `view=diversification` | 1 | duplicate render of `portfolio_score component`; group: Exposure & Construction |
| `metric.report.raw-holding-count` | metric | `Diversification.jsx:48,57` | Raw holdings | `portfolioAnalytics.js:807` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.hhi` | metric | explained at `Diversification.jsx:123`; value implicit | Herfindahl concentration | `portfolioAnalytics.js:770,805` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.effective-holdings` | metric | `Diversification.jsx:57` | Effective holdings | `portfolioAnalytics.js:806` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.effective-bets` | metric | `Diversification.jsx:48-57` | Effective bets | `portfolioAnalytics.js:633-686,775-812` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.diversification-ratio` | metric | `Diversification.jsx:73,81` | Diversification ratio | `portfolioAnalytics.js:600-686,778-810` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.holding-breadth-score` | metric | `Diversification.jsx:66-73` | Holding HHI score component | `portfolioAnalytics.js:770-785` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.sector-breadth-score` | metric | `Diversification.jsx:66-73` | Sector HHI score component | `portfolioAnalytics.js:766-785` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.industry-breadth-score` | metric | `Diversification.jsx:66-73` | Industry HHI score component | `portfolioAnalytics.js:768-785` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.pairwise-correlation` | metric | `Diversification.jsx:74-81` | Pairwise correlation matrix | `portfolioAnalytics.js:600-686` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.sector-allocation` | metric | `Diversification.jsx:58-66` | Look-through sector allocation | `portfolioAnalytics.js:512-598,766-803` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.industry-allocation` | metric | `Diversification.jsx:116-123` | Industry concentration | `Diversification.jsx:14-15` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.position-weight` | metric | `Diversification.jsx:109-115` | Holdings by allocation | `portfolioAnalytics.js:759-760` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.portfolio-volatility` | metric | calculated but not rendered in covariance panel | Portfolio volatility | `portfolioAnalytics.js:690-752` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.expected-shortfall-95` | metric | `Diversification.jsx:82-90` | Expected shortfall 95% | `portfolioAnalytics.js:688,748` | kept | /portfolio | `view=diversification` | 1 | group: Tail Risk |
| `metric.report.tracking-error-selected` | metric | `Diversification.jsx:90`; duplicate supporting value in `PerformanceMetrics.jsx:123-125` | Tracking error | `portfolioAnalytics.js:717-725` | kept | /portfolio | `view=data` | 1 | group: Benchmark Fit |
| `metric.report.active-share` | metric | `PerformanceMetrics.jsx:220-228`; `Diversification.jsx:90` | Active share | `portfolioAnalytics.js:728-741` | kept | /portfolio | `view=data` | 1 | group: Portfolio Behavior |
| `metric.report.risk-contribution` | metric | `Diversification.jsx:90` | Share of total risk | `portfolioAnalytics.js:690-714` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.marginal-risk-contribution` | metric | calculated but not rendered | Marginal contribution to risk | `portfolioAnalytics.js:703-714` | kept | /portfolio | `view=data` | 1 | group: Exposure & Construction |
| `metric.report.standalone-volatility` | metric | calculated but not rendered | Standalone holding volatility | `portfolioAnalytics.js:643,706` | kept | /portfolio | `view=data` | 1 | group: Exposure & Construction |
| `metric.report.factor-alpha` | metric | `Diversification.jsx:91-99` | Annualized factor alpha | `factorAnalytics.js:65-114` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.factor-alpha-t` | metric | `Diversification.jsx:99` | Factor alpha t-statistic | `factorAnalytics.js:97-112` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.factor-r-squared` | metric | `Diversification.jsx:99` | Factor R² | `factorAnalytics.js:94-113` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.market-loading` | metric | `Diversification.jsx:99` | Market factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.size-loading` | metric | `Diversification.jsx:99` | Size factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.value-loading` | metric | `Diversification.jsx:99` | Value factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.profitability-loading` | metric | `Diversification.jsx:99` | Profitability factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.investment-loading` | metric | `Diversification.jsx:99` | Investment factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.momentum-loading` | metric | `Diversification.jsx:99` | Momentum factor loading | `factorAnalytics.js:4,99-109` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.factor-loading-se` | metric | `Diversification.jsx:99` | Factor loading standard errors | `factorAnalytics.js:97-110` | kept | /portfolio | `view=diversification` | 1 | group: Factor Attribution |
| `metric.report.theme-exposure-score` | metric | `Diversification.jsx:100-108` | Theme exposure | `factorAnalytics.js:117-140` | kept | /portfolio | `view=diversification` | 1 | group: Exposure & Construction |
| `metric.report.theme-coverage` | metric | `Diversification.jsx:108` | Theme portfolio coverage | `factorAnalytics.js:136-140` | kept | /portfolio | `view=diversification` | 1 | duplicate render of `theme_exposure_score`; group: Exposure & Construction |
| `metric.report.backtest-total-return` | metric | `BacktestComparison.jsx:61-83,75,155` | Total return | `pipeline/build_backtest_comparison.py:193-252` | kept | /evidence | `section=backtests` | 1 | group: Return & Compounding |
| `metric.report.backtest-cagr` | metric | `BacktestComparison.jsx:63,78,157`; `ShadowPortfolios.jsx:52,61-62` | CAGR | `same` | kept | /evidence | `section=backtests` | 1 | group: Return & Compounding |
| `metric.report.backtest-excess-spy` | metric | `BacktestComparison.jsx:62,76,156` | vs SPY | `same` | kept | /evidence | `section=backtests` | 1 | group: Relative Performance |
| `metric.report.backtest-success-rate` | metric | `BacktestComparison.jsx:59,73,152` | Success rate | `pipeline/build_backtest_comparison.py:130-178` | kept | /evidence | `section=backtests` | 1 | group: Consistency |
| `metric.report.backtest-beat-spy` | metric | `BacktestComparison.jsx:60,74,154` | Beat SPY | `same` | kept | /evidence | `section=backtests` | 1 | group: Consistency |
| `metric.report.backtest-sharpe` | metric | `BacktestSummary.jsx:16`; `BacktestComparison.jsx:64,79,158`; `ShadowPortfolios.jsx:53,61-62` | Sharpe | `strategy producers via `pipeline/backtest_common.py:158-204` | kept | /evidence | `section=backtests` | 1 | duplicate render of `sharpe_naive`; group: Risk-Adjusted Return |
| `metric.report.backtest-dsr` | metric | `BacktestSummary.jsx:17,50-54`; BacktestComparison fallback | Deflated Sharpe | `pipeline/backtest_common.py:104-153` | kept | /evidence | `section=backtests` | 1 | group: Statistical Confidence |
| `metric.report.backtest-win-rate` | metric | `BacktestSummary.jsx:19` | Win rate | `pipeline/backtest_common.py:158-204` | kept | /evidence | `section=backtests` | 1 | group: Consistency |
| `metric.report.average-pnl-trade` | metric | `BacktestSummary.jsx:20` | Avg P/L per trade | `strategy backtest producers` | kept | /evidence | `section=backtests` | 1 | group: Consistency |
| `metric.report.trade-count` | metric | `BacktestSummary.jsx:21` | Trades | `strategy backtest producers` | kept | /evidence | `section=backtests` | 1 | group: Algorithm Diagnostics |
| `metric.report.shadow-aligned-net-return` | metric | `ShadowPortfolios.jsx:50,61-62` | Aligned net return | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | group: Relative Performance |
| `metric.report.shadow-net-return` | metric | `ShadowPortfolios.jsx:51,61-62` | Net return (own window) | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | group: Return & Compounding |
| `metric.report.shadow-sortino` | metric | `ShadowPortfolios.jsx:54,61-62` | Sortino | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | duplicate render of `sortino_naive`; group: Risk-Adjusted Return |
| `metric.report.shadow-turnover` | metric | `ShadowPortfolios.jsx:56,61-62` | Turnover | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | group: Cost & Capacity |
| `metric.report.shadow-coverage-change` | metric | `ShadowPortfolios.jsx:57,61-62` | Coverage change | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | group: Algorithm Diagnostics |
| `metric.report.shadow-observations` | metric | `ShadowPortfolios.jsx:58,61-64` | Observations / snapshots | `pipeline/shadow_portfolios.py` | kept | /evidence | `section=shadow` | 1 | group: Robustness & Validation |
| `metric.report.prospective-mean-ic` | metric | `LiveValidation.jsx:77` | Mean rank IC | `pipeline/validation/ic_harness.py` | kept | /evidence | `section=validation` | 1 | group: Robustness & Validation |
| `metric.report.prospective-ic-ci` | metric | `LiveValidation.jsx:78` | IC 95% CI | `same` | kept | /evidence | `section=validation` | 1 | group: Robustness & Validation |
| `metric.report.prospective-icir` | metric | `LiveValidation.jsx:79` | ICIR | `same` | kept | /evidence | `section=validation` | 1 | group: Robustness & Validation |
| `metric.report.prospective-quintile-return` | metric | `LiveValidation.jsx:52-62,83-91` | Quintile mean forward return | `same` | kept | /evidence | `section=validation` | 1 | group: Robustness & Validation |
| `metric.report.rank-ic-1d` | metric | `SignalMetricsPanel.jsx:18-79` | Rank IC (1d) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Algorithm Diagnostics |
| `metric.report.rank-ic-5d` | metric | same | Rank IC (5d) | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.rank-ic-21d` | metric | same | Rank IC (21d) | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.rank-ic-63d` | metric | same | Rank IC (63d) | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.ic-ir` | metric | same | IC-IR (annualized) | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.ic-decay` | metric | same | IC decay curve | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.per-leg-ic` | metric | same | Per-leg IC | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.drop-one-leg` | metric | same | Drop-one-leg delta IC | `same` | kept | /portfolio | `view=data` | 1 | group: Robustness & Validation |
| `metric.report.leg-correlation` | metric | same | Leg correlation matrix | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.quantile-spread` | metric | same | Quantile spread and monotonicity | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.score-autocorrelation` | metric | same | Score autocorrelation | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.factor-betas` | metric | same | FF5 + momentum loadings | `pipeline/signal_metrics.py:construction_metrics` | kept | /portfolio | `view=data` | 1 | duplicate render of `factor loadings above`; group: Factor Attribution |
| `metric.report.effective-n` | metric | same | Effective N | `same` | kept | /portfolio | `view=data` | 1 | duplicate render of `effective_holdings`; group: Exposure & Construction |
| `metric.report.top-10-weight` | metric | same | Top-10 weight | `same` | kept | /portfolio | `view=data` | 1 | group: Exposure & Construction |
| `metric.report.rolling-beta-60d` | metric | same | Rolling 60-day beta | `same` | kept | /portfolio | `view=data` | 1 | group: Benchmark Fit |
| `metric.report.net-exposure-drift` | metric | same | Net exposure drift | `same` | kept | /portfolio | `view=data` | 1 | group: Exposure & Construction |
| `metric.report.sector-active-weights` | metric | same | Sector active weights | `same` | kept | /portfolio | `view=data` | 1 | group: Exposure & Construction |
| `metric.report.breakeven-gross-alpha` | metric | same | Breakeven gross alpha | `pipeline/signal_metrics.py:cost_metrics` | kept | /portfolio | `view=data` | 1 | group: Cost & Capacity |
| `metric.report.alpha-cost-crossover` | metric | same | Alpha versus cost crossover | `same` | kept | /portfolio | `view=data` | 1 | group: Cost & Capacity |
| `metric.report.percent-of-adv` | metric | same | Position as a share of ADV | `same` | kept | /portfolio | `view=data` | 1 | group: Cost & Capacity |
| `metric.report.implementation-shortfall` | metric | same | Implementation shortfall | `same` | kept | /portfolio | `view=data` | 1 | group: Cost & Capacity |
| `metric.report.fill-rate` | metric | same | Fill rate | `same` | kept | /portfolio | `view=data` | 1 | group: Cost & Capacity |
| `metric.report.unpositioned-signals` | metric | same | Signals never positioned | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.deflated-sharpe` | metric | same | Deflated Sharpe ratio | `pipeline/signal_metrics.py:honesty_metrics` | kept | /portfolio | `view=data` | 1 | duplicate render of `backtest_dsr`; group: Statistical Confidence |
| `metric.report.probabilistic-sharpe` | metric | same | Probabilistic Sharpe ratio | `same` | kept | /portfolio | `view=data` | 1 | group: Statistical Confidence |
| `metric.report.min-track-record-length` | metric | same | Minimum track record length | `same` | kept | /portfolio | `view=data` | 1 | group: Statistical Confidence |
| `metric.report.pbo` | metric | same | Probability of backtest overfitting | `same` | kept | /portfolio | `view=data` | 1 | group: Robustness & Validation |
| `metric.report.omega` | metric | same | Omega ratio | `pipeline/signal_metrics.py:701-739` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.ulcer-index` | metric | same | Ulcer index | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.martin-ratio` | metric | same | Martin ratio | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.cvar-95` | metric | same | CVaR-95 | `same` | kept | /portfolio | `view=data` | 1 | duplicate render of `expected_shortfall_95`; group: Tail Risk |
| `metric.report.skew` | metric | same | Skew | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.excess-kurtosis` | metric | same | Excess kurtosis | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.tail-ratio` | metric | same | Tail ratio | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.gain-to-pain` | metric | same | Gain to pain | `same` | kept | /portfolio | `view=data` | 1 | group: Tail Risk |
| `metric.report.live-vs-backtest-ic` | metric | same | Rolling 60-day live IC vs backtest | `pipeline/signal_metrics.py:monitoring_metrics` | kept | /portfolio | `view=data` | 1 | group: Robustness & Validation |
| `metric.report.feature-psi` | metric | same | Feature distribution PSI | `same` | kept | /portfolio | `view=data` | 1 | group: Robustness & Validation |
| `metric.report.live-vs-backtest-divergence` | metric | same | Live vs backtest return divergence | `same` | kept | /portfolio | `view=data` | 1 | group: Robustness & Validation |
| `metric.report.data-quality-counters` | metric | same | Data quality counters | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.position-reconciliation` | metric | same | Position reconciliation | `same` | kept | /portfolio | `view=data` | 1 | group: Algorithm Diagnostics |
| `metric.report.ic-bootstrap-ci` | metric | `SignalMetricsPanel.jsx` | Bootstrap IC confidence interval | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Signal quality; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.rolling-ic-regime` | metric | `SignalMetricsPanel.jsx` | Rolling 12-period IC (regime monitor) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Signal quality; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.rolling-beta-swing` | metric | `SignalMetricsPanel.jsx` | Rolling beta swing (60d window) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Construction diagnostics; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.sector-classification-coverage` | metric | `SignalMetricsPanel.jsx` | Sector classification coverage | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Construction diagnostics; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.sector-allocation-effect` | metric | `SignalMetricsPanel.jsx` | Sector allocation effect | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Construction diagnostics; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.sector-selection-effect` | metric | `SignalMetricsPanel.jsx` | Sector selection effect | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Construction diagnostics; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.order-rejection-rate` | metric | `SignalMetricsPanel.jsx` | Order rejection rate | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Cost and capacity; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.realized-vs-expected-slippage` | metric | `SignalMetricsPanel.jsx` | Realized vs. expected slippage | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Cost and capacity; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.bootstrap-ci` | metric | `SignalMetricsPanel.jsx` | Bootstrap return/Sharpe confidence interval | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Statistical honesty; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.reality-check-spa` | metric | `SignalMetricsPanel.jsx` | White's Reality Check / SPA test | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Statistical honesty; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.rolling-sharpe-60d` | metric | `SignalMetricsPanel.jsx` | Rolling 60-day Sharpe | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Statistical honesty; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.var-backtest-95` | metric | `SignalMetricsPanel.jsx` | VaR backtest (95%) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Statistical honesty; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.var-backtest-99` | metric | `SignalMetricsPanel.jsx` | VaR backtest (99%) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Statistical honesty; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.treynor-ratio` | metric | `SignalMetricsPanel.jsx` | Treynor ratio | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Classic risk-adjusted return; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.jensens-alpha` | metric | `SignalMetricsPanel.jsx` | Jensen's alpha (single-factor CAPM) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Classic risk-adjusted return; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.after-tax-return` | metric | `SignalMetricsPanel.jsx` | After-tax return | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.stress-test-2022` | metric | `SignalMetricsPanel.jsx` | 2022 rate-shock stress window | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.stress-test-2020` | metric | `SignalMetricsPanel.jsx` | 2020 COVID-crash stress window | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.rate-beta` | metric | `SignalMetricsPanel.jsx` | Beta to long Treasuries (rate sensitivity) | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Construction diagnostics; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.scenario-gfc-2008` | metric | `SignalMetricsPanel.jsx` | 2008 Global Financial Crisis | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.scenario-covid-2020` | metric | `SignalMetricsPanel.jsx` | March 2020 COVID crash | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.scenario-rate-shock-2022` | metric | `SignalMetricsPanel.jsx` | 2022 rate-hike drawdown | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.scenario-hypothetical-spy` | metric | `SignalMetricsPanel.jsx` | Hypothetical: SPY -30% | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |
| `metric.report.scenario-hypothetical-rates` | metric | `SignalMetricsPanel.jsx` | Hypothetical: rates +200bp | `pipeline/signal_metrics.py` | kept | /evidence | `section=validation` | 1 | group: Tax and stress; live-registry metric, not yet in docs/METRIC_INVENTORY.md — NOTES.md |

---

## 16 · Copy & export surfaces

(`export.insights.share-today`, listed in §6 Portfolio Insights, is the seventh export surface —
not repeated here to keep capabilityIds unique.)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `export.global.stock-copy-data` | export | `CopyDataButton` in Stock Detail Sheet | `buildStockCopyText()` — header, price, 20d move, METRICS by section, insider activity, disclosed positioning, evidence-for, risks/gaps | `stockCopyText.js` | kept | (in detail sheet) | — | 0 | see §14 |
| `export.data-overview.copy-metrics` | export | `ExportMetricsMenu` | "Copy all metrics to clipboard" | `exportSnapshot.js` | kept | `/portfolio` | `?view=data` | 0 | **protected: data-overview copy affordance** |
| `export.data-overview.download-json` | export | `ExportMetricsMenu` | "Download all metrics (JSON)" | `buildExportSnapshot()` — `{exported_at, export_purpose, analytics_scope, holdings, portfolio_analytics, benchmark_comparisons, signal_metrics_report, monte_carlo_projection}` | kept | `/portfolio` | `?view=data` | 0 | filename `valuesignal-metrics-{scope}-{date}.json`; `annotateSmallSample` injects `sample_size_warning` below the observation floor |
| `state.export.data-overview-status` | state | `role="status"` | "Copied to clipboard" / "Copy failed" / "Download started" / "Download failed" | — | kept | `/portfolio` | `?view=data` | 0 | 2.5s reset |
| `export.portfolio.export-portfolio-json` | export | "Export portfolio" (Data actions popover) | JSON download | `useFirebasePortfolio.exportPortfolio` | kept | `/portfolio` | — | 0 | |
| `export.evidence.methodology-docs` | export | "Download full docs (.md)" | two bundled markdown files | — | kept | `/evidence` | `?section=methodology` | 1 | |

## 17 · Persistence & URL state

Per the URL-addressability rule (ROUTE-INVENTORY §2), every item below becomes **default-only**:
read from `useSearchParams` first, storage supplies the value only when the param is absent.

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `link.persistence.preferences-blob` | link | localStorage | `valuesignal.ui-preferences.v1`, v5 | `PreferencesContext.jsx` | kept | (cross-app) | — | 0 | migrates to v6 in rebuild (adds `medium` key) |
| `link.persistence.sidebar-collapsed` | link | localStorage | `vs-sidebar-collapsed` | `App.jsx` | kept | (nav chrome) | — | 0 | |
| `link.persistence.recent-searches` | link | localStorage | `valuesignal.recent-searches`, max 8 | `Search.jsx` | merged | `/research` | `?view=picks` | 0 | |
| `link.persistence.watchlist-sizing` | link | localStorage | `valuesignal.watchlistSizing` | `Watchlist.jsx` | merged | `/research` | `?view=watchlist` | 1 | |
| `link.persistence.watchlist-filter-sort` | link | localStorage | `valuesignal.watchlistFilterSort` | `Watchlist.jsx` | merged | `/research` | `?view=watchlist` | 1 | |
| `link.persistence.market-intraday` | link | localStorage | `valuesignal.marketIntraday.v1` | `Markets.jsx` | kept | `/markets` | `?view=indexes` | 0 | |
| `link.persistence.watchlist-migration` | link | localStorage | `valuesignal.watchlist` legacy + `valuesignal.watchlistMigrated.{uid}` | `useWatchlist.js` | kept | (data layer) | — | 0 | one-time Firestore migration, no UI surface |
| `link.persistence.data-cache` | link | localStorage + Cache API | `dash:last-refresh:{file}`, `dash-data-cache-v1` | `useData.js` | kept | (data layer) | — | 0 | fetch-failure fallback only, never fresh paint |
| `link.persistence.analytics-scope` | link | sessionStorage | `valuesignal.analytics.scope` | `Portfolio.jsx` | kept | `/portfolio` | `?view=data&scope=<s>` | 0 | |
| `link.persistence.analytics-view` | link | sessionStorage | `valuesignal.analytics.view` | `PerformanceMetrics.jsx` | kept | `/portfolio` | `?view=data&analytics=<a>` | 0 | |
| `link.deeplink.search-q-param` | link | `/search?q={ticker}` | produced by Alerts, never read today | — | merged | `/research` | `?q=<term>` | 0 | **bug fix in rebuild**: param is now read |
| `link.anchor.sell-signals` | link | `#sell-signals` | in-page anchor | — | kept | `/portfolio` | `?view=summary#sell-signals` | 0 | |
| `link.anchor.skip-link` | link | `#main-content` | skip-link target | — | kept | (global chrome) | — | 0 | |
| `link.anchor.finance-account` | link | `#finance-account-{id}` | scrollIntoView target | — | merged | `/portfolio` | `?view=finances&tab=retirement` | 1 | |
| `link.redirect.options-legacy` | link | 7 flat redirects | `/screens/<strategy>` → `/screens/options/<strategy>` | — | merged | `/screens` | `?recipe=options&strategy=<id>` | 0 | see §9c |
| `link.redirect.market-singular` | link | `/market` → `/news` | legacy singular route | — | merged | `/markets` | `?view=news` | 0 | see §3 |

## 18 · Accessibility affordances

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `a11y.global.skip-link` | a11y | `<a class="skip-link" href="#main-content">` | skip to content | — | kept | (global chrome) | — | 0 | every medium's nav landmark contract |
| `a11y.global.dialog-focus-trap` | a11y | `useDialog(open, onClose)` | initial focus, Tab/Shift+Tab trap, Esc close, focus restore | `useDialog.js` | kept | (shared) | — | 0 | only Esc handler in the app; excludes controls inside collapsed `<details>` structurally |
| `a11y.global.mobile-sheet-dialog` | a11y | `MobileSheet` | `role="dialog" aria-modal aria-labelledby`, handle, labelled close, guarded backdrop | — | kept | (shared) | — | 0 | reused for More menu, edit/sell sheets, lot-sell, import preview |
| `a11y.global.body-scroll-lock` | a11y | `useBodyScrollLock` | stock modal scroll lock | — | kept | (shared) | — | 0 | |
| `a11y.global.aria-live-status` | a11y | `aria-live="polite"` regions | refresh/trade/alert/settings/chart-summary announcements | — | kept | (cross-app, 17 files) | — | 0 | |
| `a11y.global.role-alert-discipline` | a11y | `role="alert"` | reserved for genuine failures (fetch errors, partial collection, import removals, auth error) | — | kept | (cross-app) | — | 0 | |
| `a11y.global.role-status-discipline` | a11y | `role="status"` | progress/success messaging | — | kept | (cross-app) | — | 0 | |
| `a11y.global.progressbar` | a11y | `role="progressbar"` `aria-valuenow/valuetext` | `RefreshProgress` | — | kept | (cross-app) | — | 0 | |
| `a11y.screens.swing-tablist` | a11y | `role="tablist"`/`role="tab"`/`aria-selected` | Swing tier switcher | — | merged | `/screens` | `?recipe=swing` | 1 | |
| `a11y.global.aria-pressed-toggles` | a11y | `aria-pressed` | Settings choices, Swing column view, alert rule enable, privacy eye | — | kept | (cross-app) | — | 0 | |
| `a11y.global.analytics-view-current` | a11y | `aria-current="page"` | analytics view selector | — | kept | `/portfolio` | `?view=data` | 0 | |
| `a11y.global.more-menu-popup` | a11y | `aria-haspopup="dialog"` `aria-expanded` | mobile More button | — | kept | (nav chrome) | — | 0 | |
| `a11y.global.expand-buttons` | a11y | `aria-expanded` | every expand-button app-wide | — | kept | (cross-app) | — | 0 | |
| `a11y.global.chart-img-role` | a11y | `role="img"` + `aria-label` | every hand-rolled SVG chart | — | kept | (cross-app) | — | 0 | score dial, score history, sequence risk, insider bar, etc. |
| `a11y.global.sr-only-labels` | a11y | `sr-only` | every unlabelled select/search input | — | kept | (cross-app) | — | 0 | |
| `a11y.global.figure-aria-label` | a11y | `<figure>` + descriptive `aria-label` | charts | — | kept | (cross-app) | — | 0 | |
| `a11y.gap.search-row-buttons` | a11y | `div role="button" tabIndex={0}` | Search result rows (manual Enter/Space) | — | kept | `/research` | `?q=<term>` | 0 | known gap — rebuild upgrades to real `<button>`; fix noted in NOTES.md |
| `a11y.gap.watchlist-add-form` | a11y | manual Enter handler | watchlist add-ticker input, not a real `<form>` | — | kept | `/research` | `?view=watchlist` | 1 | known gap — fix noted in NOTES.md |
| `a11y.gap.filter-tab-groups` | a11y | plain buttons, no `role="tab"` | Finances tabs, Holdings view tabs (no roving tabindex) | — | kept | `/portfolio` | various | 0/1 | known gap — fix noted in NOTES.md |

## 19 · Global chrome (persistent across every route)

| capabilityId | class | surfaceToday | element | dataSource | disposition | destination | selector | interactions | notes |
|---|---|---|---|---|---|---|---|---|---|
| `nav.chrome.desktop-rail` | nav | `<aside class="rail">` | collapsible rail, brand lockup, nav groups | — | kept | (global) | — | 0 | replaced per-medium by the manifest `nav.model` |
| `nav.chrome.mobile-tab-bar` | nav | `<nav class="mobile-nav">` | 5-item tab bar (Home/Portfolio/Research/Markets/More) | `MOBILE_NAV` | kept | (global) | — | 0 | becomes the six-destination bar |
| `nav.chrome.mobile-more-sheet` | nav | `MobileMoreMenu` | grouped remaining destinations | — | kept | (global) | — | 0 | absorbed into the six-destination model — no "more" residue once all routes map to 6 |
| `figure.chrome.data-status-banner` | figure | `DataStatus` | mode/age/provider pills | `status.json` | kept | (global) | — | 0 | derives `level = demo\|warning\|live` from `data_mode` + 36h staleness + `stages.advisor.status` |
| `figure.chrome.model-version-footer` | figure | `ModelVersionFooter` | model version footer | `model_metadata` | kept | (global) | — | 0 | |
| `control.chrome.alert-badge` | control | `AlertBadge` | unread count, "99+" cap | `useAlerts` | kept | (global) | — | 0 | opens `/alerts`, 1-tap chrome |
| `control.chrome.privacy-eye-mobile` | control | icon button | mobile header privacy toggle | preference `privacyMode` | kept | (global) | — | 0 | duplicate of Home + Settings controls |
| `figure.chrome.profile-panel` | figure | `ProfilePanel` | avatar, display name, settings link | `useAuth` | kept | (global) | — | 0 | |
| `state.chrome.cloud-session-error` | state | `role="alert"` | "Cloud data is offline." + Try again | `useAuth` | kept | (global) | — | 0 | |
| `state.chrome.route-loading` | state | `RouteLoading` | per-route loading label | — | kept | (global) | — | 0 | |
| `state.chrome.error-boundary` | state | `ErrorBoundary` keyed on pathname | per-page error recovery | — | kept | (global) | — | 0 | |
| `disclosure.chrome.no-signal-promoted` | disclosure | **NEW chrome surface, closes docs-only gap** | classification B / "no signal has been promoted" | `validation/research_evidence.json.headline` | kept | (global — every medium's ProvenanceStrip) | — | 0 | protected disclosure #6, currently docs-only — see NOTES.md |

---

## Scale summary

- §15 Metrics (generated from `docs/METRIC_INVENTORY.md` + live `signal_metrics.json`): **154 rows**
- §1–14, §16–19 (hand-authored from the route/capability census): **606 rows**
- Non-route orphans (§13, disposition `n/a`): **2 rows**
- **Total: 762 rows** — above the ~500–560 estimate in the execution plan; the plan flagged
  *under*-500 as the signal of a missed class, so the higher count favors completeness. Class
  distribution: metric 154 · figure 119 · state 119 · disclosure 114 · control 111 · chart 41 ·
  link 25 · column 22 · a11y 20 · nav 12 · export 10 · alert 7 · detail 5 · view 1 · n/a 2.
- Disposition distribution: kept 440 · merged 262 · demoted 54 · moved 4 · n/a 2. Zero blanks —
  every row was placed into one of the four dispositions the master permits, or explicitly
  marked `n/a` with a NOTES.md pointer (`/hud-demo`, `CommandCenter.jsx` — neither is a route).
- Every capabilityId is unique (verified: `grep -oP '^\| \`\K[a-z0-9.-]+(?=\`)' CAPABILITY-LEDGER.md | sort | uniq -d` returns nothing).

See `NOTES.md` for every judgment call this ledger makes.
