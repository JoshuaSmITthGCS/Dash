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
