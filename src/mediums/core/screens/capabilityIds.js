/**
 * Per-screen capabilityId constants mirroring CAPABILITY-LEDGER.md. Screens reference these
 * instead of typing ledger ids inline, so a rename in the ledger is a one-line fix here rather
 * than a grep-and-replace across every medium.
 *
 * Scope note (NOTES.md has the full judgment call): this file currently covers what the six
 * core screens actually render as of Phase 2a — the Home first-viewport slice in full, and a
 * representative structural slice of Research/Screens/Portfolio/Markets/Evidence. It grows as
 * each screen is built out further in Phase 2b/2c; every id added here must already exist as a
 * row in CAPABILITY-LEDGER.md, never the other way around.
 */
export const HOME_IDS = Object.freeze({
  portfolioHero: 'figure.home.portfolio-hero',
  growthChart: 'chart.home.growth-chart',
  asOfEyebrow: 'disclosure.home.as-of-eyebrow',
  provenanceStrip: 'disclosure.chrome.no-signal-promoted',
  loading: 'state.home.loading',
  noAdvisorDataset: 'state.home.no-advisor-dataset',
})

export const RESEARCH_IDS = Object.freeze({
  searchInput: 'control.research.search-input',
  resultCount: 'figure.research.result-count',
  loading: 'state.research.loading',
  empty: 'state.research.empty',
})

export const SCREENS_IDS = Object.freeze({
  recipeNav: 'nav.chrome.mobile-tab-bar', // placeholder host; per-recipe ids come from the recipe config itself
  loading: 'state.screens.generic-loading',
  unavailable: 'state.screens.generic-unavailable',
})

export const PORTFOLIO_IDS = Object.freeze({
  kpiRow: 'figure.portfolio.kpi-row',
  summaryGrowthChart: 'chart.portfolio.summary-growth-chart',
  loading: 'state.portfolio.summary-chart-building',
})

export const MARKETS_IDS = Object.freeze({
  sessionBadge: 'figure.markets.session-badge',
  growthChart: 'chart.markets.growth-chart',
  unavailable: 'state.markets.unavailable',
})

export const EVIDENCE_IDS = Object.freeze({
  signalMetricsPanel: 'chart.evidence.validation-signal-metrics-panel',
  noSignalPromoted: 'disclosure.evidence.validation-no-signal-promoted',
  icUnavailable: 'state.evidence.validation-ic-unavailable',
})

// CAPABILITY-LEDGER.md §14 · Stock Detail Sheet — all 37 rows, copied verbatim. Opened from 7
// routes (Research, Search/Research, Portfolio Summary + suggested actions, FastGrowth,
// Options/Strategy, ThemeExposure/Screens); see src/mediums/core/screens/StockDetailSheet.jsx.
export const STOCK_DETAIL_IDS = Object.freeze({
  dialogShell: 'detail.stock.dialog-shell',
  copyData: 'export.stock.copy-data',
  watchlistStar: 'control.stock.watchlist-star',
  close: 'action.stock.close',
  asOfLine: 'disclosure.stock.as-of-line',
  researchScoreDial: 'figure.stock.research-score-dial',
  dataCoverage: 'figure.stock.data-coverage',
  guidance: 'figure.stock.guidance',
  themeExposure: 'figure.stock.theme-exposure',
  evidenceExpander: 'control.stock.evidence-expander',
  actionGuidance: 'figure.stock.action-guidance',
  setupQualityBreakdown: 'figure.stock.setup-quality-breakdown',
  factorBars: 'chart.stock.factor-bars',
  kpiGrid: 'figure.stock.kpi-grid',
  dipWatchBadge: 'figure.stock.dip-watch-badge',
  bullBearThesisTrack: 'figure.stock.bull-bear-thesis-track',
  recommendationShadowPanel: 'figure.stock.recommendation-shadow-panel',
  peerValuation: 'figure.stock.peer-valuation',
  tabs: 'nav.stock.tabs',
  evidenceTabCollapsedNote: 'figure.stock.evidence-tab-collapsed-note',
  scoreExplainability: 'chart.stock.score-explainability',
  fundamentalCategories: 'figure.stock.fundamental-categories',
  evidenceRisksLists: 'figure.stock.evidence-risks-lists',
  insiderActivity: 'figure.stock.insider-activity',
  insideInformationView: 'figure.stock.inside-information-view',
  scoreModifiers: 'figure.stock.score-modifiers',
  metricSections: 'chart.stock.metric-sections',
  etfComparisonPanel: 'figure.stock.etf-comparison-panel',
  growthVsSpy: 'chart.stock.growth-vs-spy',
  hypotheticalKpiGrid: 'figure.stock.hypothetical-kpi-grid',
  riskKpiGrid: 'figure.stock.risk-kpi-grid',
  scoreWaterfall: 'chart.stock.score-waterfall',
  waterfallDivergence: 'disclosure.stock.waterfall-divergence',
  metricLevelEvidence: 'figure.stock.metric-level-evidence',
  scoreHistory: 'chart.stock.score-history',
  anomalies: 'figure.stock.anomalies',
  footerDisclaimer: 'disclosure.stock.footer-disclaimer',
})
